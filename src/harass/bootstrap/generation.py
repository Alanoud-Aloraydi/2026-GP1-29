"""Composition root of the prompt generation command."""

import asyncio
import logging
import os
import sys
from pathlib import Path

import httpx
from sqlalchemy.orm import Session, sessionmaker

from harass.application.connections import ManageConnections
from harass.application.generation.contracts import GenerationRequest, RoundReport
from harass.application.generation.drafting import DraftPipeline
from harass.application.generation.generation_service import GenerateRound
from harass.application.generation.librarian import Librarian
from harass.application.ports.evaluation import AttemptExecutor
from harass.bootstrap.database import database_sessions, load_environment
from harass.bootstrap.evaluation import DATASET_FILE, build_attempt_executor
from harass.infrastructure.dataset.card_file import read_cards
from harass.infrastructure.dataset.spreadsheet_seed_source import SpreadsheetSeedSource
from harass.infrastructure.http.generation_judges import (
    ModelFormReviewer,
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
from harass.infrastructure.security.fernet_secret_cipher import FernetSecretCipher
from harass.infrastructure.settings import (
    BackendSettings,
    GenerationModel,
    GenerationSettings,
    Settings,
)
from harass.interfaces.cli.generation_command import RoundArguments, run_generation_command

# Drafting samples widely so subjects stay new; rewriting into a variety must
# not wander; every judgment is greedy, or the same prompt passes one round
# and fails the next.
WRITER_TEMPERATURE = 0.7
LOCALIZER_TEMPERATURE = 0.5
JUDGING_TEMPERATURE = 0.0
WRITING_TOKENS = 400
LESSON_TOKENS = 120
REVIEW_TOKENS = 600
JUDGEMENT_TOKENS = 400
# The reviewing models hide their answer behind reasoning tokens unless the
# effort is low: at the default they returned reasoning and no content.
REASONING_EFFORT = "low"
GATEWAY_TIMEOUT_SECONDS = 180


def _writer(
    gateway: ModelGateway, model: GenerationModel, temperature: float, tokens: int
) -> GatewayBriefWriter:
    """Bind one writing role to its model and its sampling settings."""
    return GatewayBriefWriter(
        gateway, ModelRoute(model.endpoint, model.api_key, model.model, temperature, tokens)
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
    """Assemble the generation service from its adapters."""
    judging = JudgingGateway(gateway)
    return GenerateRound(
        store=SqlAlchemyGenerationStore(factory),
        drafting=DraftPipeline(
            _writer(gateway, generation.writer, WRITER_TEMPERATURE, WRITING_TOKENS),
            _writer(gateway, generation.localizer, LOCALIZER_TEMPERATURE, WRITING_TOKENS),
            ModelFormReviewer(judging, _judge(generation.reviewer, REVIEW_TOKENS)),
        ),
        safety=ModelSafetyJudge(judging, _judge(generation.safety_judge, JUDGEMENT_TOKENS)),
        patterns=ModelPatternReader(judging, _judge(generation.reviewer, JUDGEMENT_TOKENS)),
        librarian=Librarian(_writer(gateway, generation.writer, WRITER_TEMPERATURE, LESSON_TOKENS)),
        executor=executor,
        seeds=SpreadsheetSeedSource(DATASET_FILE),
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
                        round_index=arguments.round_index,
                        count=arguments.count,
                        send_to_target=arguments.send_to_target,
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
