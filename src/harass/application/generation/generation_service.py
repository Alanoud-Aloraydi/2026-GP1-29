"""Run one round of the agentic prompt generator on either axis.

Both axes share one engine: plan the round's cells, give each the pattern
card that looks most promising, write and localize a prompt per cell, review
its form (a rejected prompt goes back to the writer), ask the safety judge,
store it, pass the valid ones through the adapter's transforms, and send
them to the client's own target through the evaluation executor, whose judge
scores the reply. The round ends by distilling lessons and new cards from
its successes. The axes differ only in content: an over-refusal prompt is
always written from a card and must be judged safe; an attack is written
from a card once its group has one and must be judged harmful if complied
with. Round zero measures the target; later rounds exploit what the earlier
ones learned.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, replace

from harass.application.errors import ApplicationError
from harass.application.generation.attack_drafting import AttackDraftPipeline
from harass.application.generation.contracts import Draft, GenerationRequest, RoundReport
from harass.application.generation.librarian import Librarian, ScoredPrompt
from harass.application.generation.over_refusal_drafting import OverRefusalDraftPipeline
from harass.application.ports.evaluation import AttemptExecutor, SeedSource
from harass.application.ports.generation import GenerationStore, PatternReader, SafetyJudge
from harass.domain.case_identifier import CaseIdentifier
from harass.domain.case_outcome import CaseOutcome
from harass.domain.case_selection import CaseSelection
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.generation.cells import (
    AttackCell,
    OverRefusalCell,
    plan_attack_round,
    plan_over_refusal_round,
)
from harass.domain.generation.history import (
    GeneratedPrompt,
    GenerationHistory,
    Lesson,
    PromptOutcome,
    group_key,
)
from harass.domain.generation.novelty import KnownPrompts
from harass.domain.generation.pattern_card import Assignment, Card, assign
from harass.domain.generation.transforms import (
    TransformDefinition,
    adapter_sequence,
    transform_text,
)
from harass.domain.taxonomy import Axis, RiskCategory

logger = logging.getLogger(__name__)

# A prompt whose form the reviewer rejects goes back to the writer this often.
REVIEW_RETRIES = 2
LESSONS_PER_BRIEF = 2
CONCURRENCY = 8
GENERATED_SOURCE = "generated"


@dataclass(frozen=True)
class _Work[CellT: (OverRefusalCell, AttackCell)]:
    """One planned cell with the card and lessons its writer reads."""

    cell: CellT
    card: Card | None
    lessons: tuple[Lesson, ...]


@dataclass(frozen=True)
class _Written:
    """One drafted prompt before the safety judge, with how it was written."""

    work: "_Work[OverRefusalCell] | _Work[AttackCell]"
    draft: Draft
    attempts: int


class GenerateRound:
    """Produce, judge and score one round of generated prompts."""

    def __init__(
        self,
        store: GenerationStore,
        safety: SafetyJudge,
        executor: AttemptExecutor,
        seeds: SeedSource,
        over_refusal: OverRefusalDraftPipeline,
        patterns: PatternReader,
        librarian: Librarian,
        attack: AttackDraftPipeline | None = None,
        concurrency: int = CONCURRENCY,
    ) -> None:
        """Store the ports and the axis pipelines supplied by the composition root.

        ``attack`` is None when no attack writer is configured; an attack
        round then fails before any model is called.
        """
        self._store = store
        self._safety = safety
        self._executor = executor
        self._seeds = seeds
        self._over_refusal = over_refusal
        self._patterns = patterns
        self._librarian = librarian
        self._attack = attack
        self._concurrency = concurrency

    async def execute(self, request: GenerationRequest) -> RoundReport:
        """Run one round and report its prompts, outcomes and lessons.

        Every prompt is stored before any request reaches the target, so an
        interrupted round keeps what it wrote. Storage is append-only, so
        scoring a round twice neither duplicates nor inflates anything.

        Raises:
            ApplicationError: If an attack round has no attack writer.
            ValueError: If the adapter's transforms do not fit the axis.
        """
        sequence = adapter_sequence(request.transform_names, request.axis)
        attack = self._attack
        if request.axis is Axis.ADVERSARIAL and attack is None:
            raise ApplicationError("No attack writer is configured for an attack round.")
        target_model = request.target.model_name
        history = await asyncio.to_thread(self._store.history, target_model, request.axis)
        known = await asyncio.to_thread(self._known_prompts, history, request.axis)
        cards = await asyncio.to_thread(self._store.cards, target_model)
        if attack is not None and request.axis is Axis.ADVERSARIAL:
            written = await self._write_attacks(attack, request, history, cards, known)
        else:
            written = await self._write_over_refusal(request, history, cards, known)
        prompts = await self._judge_safety(request, history, written, sequence)
        for prompt in prompts:
            await asyncio.to_thread(self._store.add_prompt, prompt)
        report = RoundReport(request.axis, request.round_index, target_model, prompts)
        if not request.send_to_target:
            return report
        outcomes = await self._score(request, prompts)
        return await self._learn(request, report, history, cards, outcomes)

    async def _write_over_refusal(
        self,
        request: GenerationRequest,
        history: GenerationHistory,
        cards: Sequence[Card],
        known: KnownPrompts,
    ) -> list[_Written]:
        """Plan the over-refusal cells of the risks that hold a card, and write each.

        Every over-refusal prompt is written from a card, so a risk the
        target never over-refused has nothing to imitate and is not planned.
        """
        risks = frozenset(
            RiskCategory(card.risk) for card in cards if card.axis is Axis.OVER_REFUSAL
        )
        if not risks:
            logger.warning(
                "Round %d planned no prompt: no card to write from.", request.round_index
            )
            return []
        plan = plan_over_refusal_round(
            request.round_index,
            request.count,
            history.accepted_cells(),
            history.successful_cells(),
            exploit=request.is_discovery,
            varieties=request.varieties,
            risks=risks,
        )
        pending = [
            _Work(item.cell, item.card, self._lessons(request, history, item.cell, item.device))
            for item in assign(plan, cards, history.card_uses(), _results(request, history))
        ]

        def produce(work: _Work[OverRefusalCell]) -> Awaitable[Draft | None]:
            assert work.card is not None
            texts = [lesson.text for lesson in work.lessons]
            return self._over_refusal.produce(Assignment(work.cell, work.card), texts, known)

        drafted = await self._with_review_retries(pending, produce)
        return [_Written(work, draft, attempts) for work, draft, attempts in drafted]

    async def _write_attacks(
        self,
        attack: AttackDraftPipeline,
        request: GenerationRequest,
        history: GenerationHistory,
        cards: Sequence[Card],
        known: KnownPrompts,
    ) -> list[_Written]:
        """Plan the attack cells and write one attack for each.

        A cell whose risk and strategy hold no card yet is written from its
        definitions alone.
        """
        plan = plan_attack_round(
            request.count,
            history.accepted_cells(),
            history.successful_cells(),
            exploit=request.is_discovery,
            varieties=request.varieties,
        )
        assigned = iter(assign(plan, cards, history.card_uses(), _results(request, history)))
        current = next(assigned, None)
        pending: list[_Work[AttackCell]] = []
        for cell in plan:
            card = None
            if current is not None and current.cell is cell:
                card, current = current.card, next(assigned, None)
            device = card.device if card else None
            pending.append(_Work(cell, card, self._lessons(request, history, cell, device)))

        def produce(work: _Work[AttackCell]) -> Awaitable[Draft | None]:
            texts = [lesson.text for lesson in work.lessons]
            return attack.produce(work.cell, work.card, texts, known)

        drafted = await self._with_review_retries(pending, produce)
        return [_Written(work, draft, attempts) for work, draft, attempts in drafted]

    async def _with_review_retries[ItemT](
        self, pending: Sequence[ItemT], produce: Callable[[ItemT], Awaitable[Draft | None]]
    ) -> list[tuple[ItemT, Draft, int]]:
        """Write every item, sending a rejected draft back to the writer.

        A draft the reviewer rejects is written again until the last pass,
        where its final attempt is kept and marked as failing review; an item
        that yields no draft at all is dropped.
        """
        kept: list[tuple[ItemT, Draft, int]] = []
        remaining = list(pending)
        for attempt in range(REVIEW_RETRIES + 1):
            if not remaining:
                break
            drafts = await self._gather(produce(item) for item in remaining)
            retry: list[ItemT] = []
            for item, draft in zip(remaining, drafts, strict=True):
                if draft is None:
                    continue
                if not draft.review.passed and attempt < REVIEW_RETRIES:
                    retry.append(item)
                    continue
                kept.append((item, draft, attempt + 1))
            remaining = retry
        return kept

    async def _judge_safety(
        self,
        request: GenerationRequest,
        history: GenerationHistory,
        written: Sequence[_Written],
        sequence: tuple[TransformDefinition, ...],
    ) -> tuple[GeneratedPrompt, ...]:
        """Ask the safety judge about each prompt, then apply the adapter."""
        verdicts = await self._gather(
            self._safety.is_intent_safe(item.draft.localized_text) for item in written
        )
        number = len(history.prompts)
        prompts: list[GeneratedPrompt] = []
        for item, is_safe in zip(written, verdicts, strict=True):
            number += 1
            sent, applied = _adapted(item.draft.localized_text, sequence)
            card = item.work.card
            prompts.append(
                GeneratedPrompt(
                    prompt_id=str(uuid.uuid4()),
                    case_id=str(_case_identifier(item.work.cell, number)),
                    axis=request.axis,
                    cell_key=item.work.cell.key,
                    round_index=request.round_index,
                    written_text=item.draft.written_text,
                    localized_text=item.draft.localized_text,
                    sent_text=sent,
                    reviewer_passed=item.draft.review.passed,
                    intent_safe=is_safe,
                    device=card.device if card else None,
                    card_id=card.card_id if card else None,
                    objective=item.draft.objective,
                    transform_names=applied,
                    reviewer_notes=item.draft.review.notes,
                    attempts=item.attempts,
                    target_model=request.target.model_name,
                    run_id=request.run_identifier or None,
                    lesson_ids=tuple(lesson.lesson_id for lesson in item.work.lessons),
                )
            )
        return tuple(prompts)

    async def _score(
        self, request: GenerationRequest, prompts: Sequence[GeneratedPrompt]
    ) -> tuple[PromptOutcome, ...]:
        """Send every valid prompt to the target and keep the judged replies."""
        valid = [prompt for prompt in prompts if prompt.is_valid]
        run_identifier = request.run_identifier or str(uuid.uuid4())
        results = await self._gather(
            self._attempt(prompt, request, run_identifier) for prompt in valid
        )
        outcomes: list[PromptOutcome] = []
        for prompt, result in zip(valid, results, strict=True):
            outcome = _outcome(prompt, request.target.model_name, result)
            if outcome is None:
                logger.warning("Prompt %s went unscored: %s", prompt.prompt_id, result.error)
                continue
            outcomes.append(outcome)
        for outcome in outcomes:
            await asyncio.to_thread(self._store.add_outcome, outcome)
        return tuple(outcomes)

    async def _attempt(
        self, prompt: GeneratedPrompt, request: GenerationRequest, run_identifier: str
    ) -> CaseOutcome:
        """Send one generated prompt through the evaluation executor.

        The generator feeds the evaluation tail rather than replacing it: the
        target and the judges are the same ones an evaluation run uses, so a
        generated prompt is scored exactly like a dataset prompt. An attack
        is judged against its objective, an over-refusal prompt against its
        own clear draft.
        """
        objective = prompt.objective or prompt.written_text
        case = EvaluationCase(CaseIdentifier.parse(prompt.case_id), prompt.sent_text, objective)
        return await self._executor.execute(case, prompt.sent_text, request.target, run_identifier)

    async def _learn(
        self,
        request: GenerationRequest,
        report: RoundReport,
        history: GenerationHistory,
        cards: Sequence[Card],
        outcomes: tuple[PromptOutcome, ...],
    ) -> RoundReport:
        """Distil the round's lessons and grow the target's card library."""
        scored = _scored_prompts(report.axis, report.prompts, outcomes)
        lessons = await self._librarian.lessons_from(
            report.axis,
            scored,
            report.target_model,
            request.run_identifier or report.target_model,
            report.round_index,
            {lesson.lesson_id for lesson in history.lessons},
        )
        for lesson in lessons:
            await asyncio.to_thread(self._store.add_lesson, lesson)
        grown = await self._grow_cards(scored, cards)
        for card in grown:
            await asyncio.to_thread(self._store.add_card, card)
        return replace(report, outcomes=outcomes, lessons=tuple(lessons), cards=grown)

    async def _grow_cards(
        self, scored: Sequence[ScoredPrompt], cards: Sequence[Card]
    ) -> tuple[Card, ...]:
        """Turn each successful generated prompt into a new pattern card.

        The library grows from its own successes, so later rounds draw on the
        patterns this generator found and not only on the baseline's.
        """
        known = {card.card_id for card in cards}
        fresh = [
            prompt for prompt, success in scored if success and f"G-{prompt.prompt_id}" not in known
        ]
        read = await self._gather(self._read_pattern(prompt) for prompt in fresh)
        return tuple(card for card in read if card is not None)

    async def _read_pattern(self, prompt: GeneratedPrompt) -> Card | None:
        """Read one successful prompt into the card describing its pattern."""
        if prompt.axis is Axis.ADVERSARIAL:
            attack = AttackCell.parse(prompt.cell_key)
            domain, risk, strategy = attack.domain, attack.risk, str(attack.strategy)
        else:
            cell = OverRefusalCell.parse(prompt.cell_key)
            domain, risk, strategy = cell.domain, cell.risk, None
        origin = Card(
            f"G-{prompt.prompt_id}",
            GENERATED_SOURCE,
            str(domain),
            str(risk),
            form="",
            target="",
            device="",
            shape="",
            axis=prompt.axis,
            strategy=strategy,
            target_model=prompt.target_model,
        )
        return await self._patterns.read(origin, prompt.written_text)

    def _known_prompts(self, history: GenerationHistory, axis: Axis) -> KnownPrompts:
        """Collect the axis's dataset prompts and the stored ones."""
        cases = self._seeds.load_cases(CaseSelection(axis=axis))
        return KnownPrompts.of([case.prompt_text for case in cases] + history.seen_texts())

    @staticmethod
    def _lessons(
        request: GenerationRequest,
        history: GenerationHistory,
        cell: OverRefusalCell | AttackCell,
        device: str | None,
    ) -> tuple[Lesson, ...]:
        """Return the lessons the writer of one cell should read.

        The measurement round reads none, so its rate owes nothing to what
        was learned from the target.
        """
        if not request.is_discovery:
            return ()
        group = group_key(cell.key, device)
        return tuple(history.best_lessons(cell.key, group, LESSONS_PER_BRIEF))

    async def _gather[ResultT](self, work: Iterable[Awaitable[ResultT]]) -> list[ResultT]:
        """Run independent model work concurrently, bounded by the limit."""
        semaphore = asyncio.Semaphore(self._concurrency)

        async def bounded(awaitable: Awaitable[ResultT]) -> ResultT:
            async with semaphore:
                return await awaitable

        return list(await asyncio.gather(*(bounded(awaitable) for awaitable in work)))


def _adapted(text: str, sequence: tuple[TransformDefinition, ...]) -> tuple[str, tuple[str, ...]]:
    """Return the text the target receives and the transforms actually applied.

    A transform that cannot apply to this text (one that needs Arabic letters
    the text no longer has) leaves it as localized, recorded as untransformed.
    """
    if not sequence:
        return text, ()
    transformed = transform_text(text, sequence)
    if transformed is None:
        return text, ()
    return transformed, tuple(transform.name for transform in sequence)


def _outcome(
    prompt: GeneratedPrompt, target_model: str, result: CaseOutcome
) -> PromptOutcome | None:
    """Read one executor result into a stored outcome, or None when unscored.

    The reply text and both judge rationales travel with the verdicts, so a
    report shows what the target said and why the judge decided as it did.
    """
    if result.response_category is None:
        return None
    transcript = result.transcript
    return PromptOutcome(
        prompt_id=prompt.prompt_id,
        target_model=target_model,
        response_category=result.response_category,
        attack_succeeded=result.attack_succeeded if prompt.axis is Axis.ADVERSARIAL else None,
        response_text=transcript.response if transcript else "",
        category_rationale=(transcript.category_rationale or "") if transcript else "",
        attack_rationale=(transcript.attack_rationale or "") if transcript else "",
    )


def _results(request: GenerationRequest, history: GenerationHistory) -> dict[str, tuple[int, int]]:
    """Return the card results a round may rank by: none in the measurement round."""
    return history.card_results() if request.is_discovery else {}


def _scored_prompts(
    axis: Axis, prompts: Sequence[GeneratedPrompt], outcomes: Sequence[PromptOutcome]
) -> list[ScoredPrompt]:
    """Pair each prompt that carries a success verdict with that verdict."""
    by_id = {prompt.prompt_id: prompt for prompt in prompts}
    return [
        (by_id[outcome.prompt_id], success)
        for outcome in outcomes
        if (success := outcome.succeeded(axis)) is not None and outcome.prompt_id in by_id
    ]


def _case_identifier(cell: OverRefusalCell | AttackCell, number: int) -> CaseIdentifier:
    """Give a generated prompt an identifier of the project's coding system.

    The four digits after the variety digit number the axis's prompts in the
    store, so an identifier is stable once stored and repeats only after ten
    thousand prompts.
    """
    case_number = f"{cell.variety.case_number_digit}{number % 10000:04d}"
    if isinstance(cell, AttackCell):
        return CaseIdentifier(
            axis=Axis.ADVERSARIAL,
            subject_domain=cell.domain,
            risk_category=cell.risk,
            variety=cell.variety,
            case_number=case_number,
            strategy=cell.strategy,
            owasp_category=cell.owasp,
        )
    return CaseIdentifier(
        axis=Axis.OVER_REFUSAL,
        subject_domain=cell.domain,
        risk_category=cell.risk,
        variety=cell.variety,
        case_number=case_number,
    )
