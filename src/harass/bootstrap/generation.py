"""Composition root of the prompt generation command."""

import asyncio
import logging
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session, sessionmaker

from harass.application.connections import ManageConnections
from harass.application.generation.agentic_run import RunAgenticEvaluation
from harass.application.generation.attack_drafting import AttackDraftPipeline
from harass.application.generation.contracts import GenerationRequest, RoundReport
from harass.application.generation.generation_service import GenerateRound
from harass.application.generation.librarian import Librarian
from harass.application.generation.localization import VarietyLocalizer
from harass.application.generation.over_refusal_drafting import OverRefusalDraftPipeline
from harass.application.generation.seeding import SeedFromBaseline
from harass.application.ports.evaluation import AttemptExecutor
from harass.application.ports.runs import RunAdmission
from harass.bootstrap.database import database_sessions, load_environment
from harass.bootstrap.evaluation import DATASET_FILE, build_attempt_executor
from harass.domain.generation.attack_briefs import ATTACK_ECHO_PHRASES
from harass.infrastructure.dataset.card_file import read_cards
from harass.infrastructure.dataset.spreadsheet_seed_source import SpreadsheetSeedSource
from harass.infrastructure.http.generation_judges import (
    ModelAttackReviewer,
    ModelOverRefusalReviewer,
    ModelPatternReader,
    ModelSafetyJudge,
)
from harass.infrastructure.http.model_gateway import (
    GatewayBriefWriter,
    JudgingGateway,
    ModelGateway,
    ModelRoute,
)
from harass.infrastructure.http.openai_connection_verifier import OpenAIConnectionVerifier
from harass.infrastructure.persistence.sqlalchemy_connections import SqlAlchemyConnectionStore
from harass.infrastructure.persistence.sqlalchemy_generation import SqlAlchemyGenerationStore
from harass.infrastructure.persistence.sqlalchemy_runs import SqlAlchemyRunStore
from harass.infrastructure.security.fernet_secret_cipher import FernetSecretCipher
from harass.infrastructure.settings import (
    BackendSettings,
    GenerationModel,
    GenerationSettings,
    Settings,
)
from harass.interfaces.cli.generation_command import RoundArguments, run_generation_command

# Drafting samples widely so subjects stay new (attacks wider still, so the
# technique varies); rewriting into a variety must not wander; every judgment
# is greedy, or the same prompt passes one round and fails the next.
WRITER_TEMPERATURE = 0.7
ATTACKER_TEMPERATURE = 0.9
LOCALIZER_TEMPERATURE = 0.5
JUDGING_TEMPERATURE = 0.0
WRITING_TOKENS = 400
ATTACK_TOKENS = 1500
LESSON_TOKENS = 120
REVIEW_TOKENS = 600
ATTACK_REVIEW_TOKENS = 700
JUDGEMENT_TOKENS = 400
# The reviewing models hide their answer behind reasoning tokens unless the
# effort is low: at the default they returned reasoning and no content.
REASONING_EFFORT = "low"
# The attacker is a Venice reasoning model: thinking spent the whole attack
# budget and returned no text, so its writing and localizing skip thinking.
ATTACKER_EXTRA_BODY = {"venice_parameters": {"disable_thinking": True}}
GATEWAY_TIMEOUT_SECONDS = 180


def _writer(
    gateway: ModelGateway,
    model: GenerationModel,
    temperature: float,
    tokens: int,
    extra_body: Mapping[str, Any] | None = None,
) -> GatewayBriefWriter:
    """Bind one writing role to its model, its sampling settings and any provider options."""
    return GatewayBriefWriter(
        gateway,
        ModelRoute(
            model.endpoint,
            model.api_key,
            model.model,
            temperature,
            tokens,
            extra_body=extra_body or {},
        ),
    )


def _judge(model: GenerationModel, tokens: int) -> ModelRoute:
    """Bind one judging role to its model, greedily and with low reasoning."""
    return ModelRoute(
        model.endpoint,
        model.api_key,
        model.model,
        JUDGING_TEMPERATURE,
        tokens,
        reasoning_effort=REASONING_EFFORT,
    )


def _service(
    factory: sessionmaker[Session],
    gateway: ModelGateway,
    generation: GenerationSettings,
    executor: AttemptExecutor,
) -> GenerateRound:
    """Assemble the generation service of both axes from its adapters."""
    judging = JudgingGateway(gateway)
    over_refusal = OverRefusalDraftPipeline(
        _writer(gateway, generation.writer, WRITER_TEMPERATURE, WRITING_TOKENS),
        VarietyLocalizer(
            _writer(gateway, generation.localizer, LOCALIZER_TEMPERATURE, WRITING_TOKENS)
        ),
        ModelOverRefusalReviewer(judging, _judge(generation.reviewer, REVIEW_TOKENS)),
    )
    return GenerateRound(
        store=SqlAlchemyGenerationStore(factory),
        safety=ModelSafetyJudge(judging, _judge(generation.safety_judge, JUDGEMENT_TOKENS)),
        executor=executor,
        seeds=SpreadsheetSeedSource(DATASET_FILE),
        over_refusal=over_refusal,
        patterns=ModelPatternReader(judging, _judge(generation.reviewer, JUDGEMENT_TOKENS)),
        librarian=Librarian(_writer(gateway, generation.writer, WRITER_TEMPERATURE, LESSON_TOKENS)),
        attack=_attack(gateway, judging, generation),
    )


def build_agentic(
    factory: sessionmaker[Session],
    gateway: ModelGateway,
    generation: GenerationSettings,
    executor: AttemptExecutor,
    evidence: RunAdmission,
) -> RunAgenticEvaluation | None:
    """Assemble the agentic run, or None when no attacker is configured.

    An agentic run plays both axes, so it needs the attack writer too.
    ``evidence`` reads the baseline run whose outcomes seed the cards.
    """
    if generation.attacker is None:
        return None
    store = SqlAlchemyGenerationStore(factory)
    reader = ModelPatternReader(
        JudgingGateway(gateway), _judge(generation.reviewer, JUDGEMENT_TOKENS)
    )
    return RunAgenticEvaluation(
        _service(factory, gateway, generation, executor),
        SeedFromBaseline(store, reader, evidence),
        store,
        SqlAlchemyRunStore(factory),
    )


def _attack(
    gateway: ModelGateway, judging: JudgingGateway, generation: GenerationSettings
) -> AttackDraftPipeline | None:
    """Assemble the attack pipeline, or None when no attacker is configured."""
    if generation.attacker is None:
        return None
    attacker = generation.attacker
    return AttackDraftPipeline(
        _writer(gateway, attacker, ATTACKER_TEMPERATURE, ATTACK_TOKENS, ATTACKER_EXTRA_BODY),
        VarietyLocalizer(
            _writer(gateway, attacker, LOCALIZER_TEMPERATURE, WRITING_TOKENS, ATTACKER_EXTRA_BODY),
            echo_phrases=ATTACK_ECHO_PHRASES,
        ),
        ModelAttackReviewer(judging, _judge(generation.reviewer, ATTACK_REVIEW_TOKENS)),
    )


def _import_cards(card_file: Path) -> int:
    """Store every pattern card of the file and return how many it held."""
    cards = read_cards(card_file)
    database_url = BackendSettings.from_environment(os.environ).database_url
    with database_sessions(database_url) as factory:
        store = SqlAlchemyGenerationStore(factory)
        for card in cards:
            store.add_card(card)
    return len(cards)


async def _generate(arguments: RoundArguments) -> RoundReport:
    """Run one round against the owner's verified connection."""
    from pyrit.setup import SQLITE, initialize_pyrit_async

    settings = Settings.from_environment(os.environ)
    backend = BackendSettings.from_environment(os.environ)
    generation = GenerationSettings.from_environment(os.environ)
    with database_sessions(backend.database_url) as factory:
        connections = ManageConnections(
            SqlAlchemyConnectionStore(factory),
            FernetSecretCipher(backend.encryption_key),
            OpenAIConnectionVerifier(),
        )
        target = connections.target_for_evaluation(arguments.owner_id, arguments.connection_id)
        await initialize_pyrit_async(memory_db_type=SQLITE, load_defaults=False, silent=True)
        executor, judge = build_attempt_executor(settings)
        async with httpx.AsyncClient() as client:
            try:
                service = _service(
                    factory, ModelGateway(client, GATEWAY_TIMEOUT_SECONDS), generation, executor
                )
                return await service.execute(
                    GenerationRequest(
                        target=target,
                        axis=arguments.axis,
                        round_index=arguments.round_index,
                        count=arguments.count,
                        send_to_target=arguments.send_to_target,
                        transform_names=arguments.transform_names,
                    )
                )
            finally:
                await judge.aclose()


def main() -> None:
    """Entry point of the ``harass-generate`` command."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    load_environment()
    # A missing setting is a ValueError, which the command reports itself.
    sys.exit(
        run_generation_command(
            sys.argv[1:],
            lambda arguments: asyncio.run(_generate(arguments)),
            _import_cards,
            sys.stdout,
        )
    )


if __name__ == "__main__":
    main()
