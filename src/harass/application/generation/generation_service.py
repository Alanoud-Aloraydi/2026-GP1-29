"""Run one round of the agentic over-refusal prompt generator.

A round plans its cells, draws a pattern card for each, writes and localizes
a prompt, reviews its form, judges whether answering it would harm, sends the
survivors to the client's own target through the evaluation executor, and
finally distils lessons and new cards for the next round. Round zero measures
the target; later rounds exploit what the earlier ones learned.
"""

import asyncio
import hashlib
import logging
import uuid
from collections.abc import Awaitable, Iterable, Sequence

from harass.application.generation.contracts import GenerationRequest, RoundReport
from harass.application.generation.drafting import Draft, DraftPipeline, KnownPrompts
from harass.application.generation.librarian import Librarian, ScoredPrompt
from harass.application.ports.evaluation import AttemptExecutor, SeedSource
from harass.application.ports.generation import GenerationStore, PatternReader, SafetyJudge
from harass.domain.case_identifier import CaseIdentifier
from harass.domain.case_outcome import CaseOutcome
from harass.domain.case_selection import CaseSelection
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.generation.cells import Cell, plan_round
from harass.domain.generation.history import GeneratedPrompt, GenerationHistory, PromptOutcome
from harass.domain.generation.pattern_card import Assignment, Card, assign
from harass.domain.prompt_variant import PromptVariant
from harass.domain.taxonomy import Axis

logger = logging.getLogger(__name__)

# A prompt whose form the reviewer rejects goes back to the writer this often.
REVIEW_RETRIES = 2
LESSONS_PER_BRIEF = 2
CONCURRENCY = 8
GENERATED_VARIANT_NAME = "generated"
GENERATED_SOURCE = "generated"
type Attempted = tuple[Assignment, Draft, int]


class GenerateRound:
    """Produce, judge and score one round of generated prompts."""

    def __init__(
        self,
        store: GenerationStore,
        drafting: DraftPipeline,
        safety: SafetyJudge,
        patterns: PatternReader,
        librarian: Librarian,
        executor: AttemptExecutor,
        seeds: SeedSource,
        concurrency: int = CONCURRENCY,
    ) -> None:
        """Store the ports supplied by the composition root."""
        self._store = store
        self._drafting = drafting
        self._safety = safety
        self._patterns = patterns
        self._librarian = librarian
        self._executor = executor
        self._seeds = seeds
        self._concurrency = concurrency

    async def execute(self, request: GenerationRequest) -> RoundReport:
        """Run one round and report its prompts, outcomes and lessons.

        Every prompt is stored before any request reaches the target, so an
        interrupted round keeps what it wrote. Storage is append-only, so
        scoring a round twice neither duplicates nor inflates anything.
        """
        target_model = request.target.model_name
        history = await asyncio.to_thread(self._store.history, target_model)
        cards = await asyncio.to_thread(self._store.cards)
        known = await asyncio.to_thread(self._known_prompts, history)
        prompts = await self._write_prompts(request, history, cards, known)
        for prompt in prompts:
            await asyncio.to_thread(self._store.add_prompt, prompt)
        if not request.send_to_target:
            return RoundReport(request.round_index, target_model, prompts)
        outcomes = await self._score(request, prompts)
        scored = _scored_prompts(prompts, outcomes)
        lessons = await self._librarian.lessons_from(
            scored,
            target_model,
            request.round_index,
            {lesson.lesson_id for lesson in history.lessons},
        )
        for lesson in lessons:
            await asyncio.to_thread(self._store.add_lesson, lesson)
        grown = await self._grow_cards(scored, cards)
        for card in grown:
            await asyncio.to_thread(self._store.add_card, card)
        return RoundReport(
            request.round_index, target_model, prompts, outcomes, tuple(lessons), grown
        )

    async def _write_prompts(
        self,
        request: GenerationRequest,
        history: GenerationHistory,
        cards: list[Card],
        known: KnownPrompts,
    ) -> tuple[GeneratedPrompt, ...]:
        """Plan the round, then write, review and safety-judge its prompts."""
        plan = plan_round(
            request.round_index,
            request.count,
            history.accepted_cells(),
            history.refused_cells(),
            exploit=request.is_discovery,
        )
        pending = assign(plan, cards, history.card_uses(), history.card_results())
        if not pending:
            logger.warning(
                "Round %d planned no prompt: no card matches its cells.", request.round_index
            )
        attempted: list[Attempted] = []
        for attempt in range(REVIEW_RETRIES + 1):
            if not pending:
                break
            drafts = await self._gather(
                self._drafting.produce(assignment, self._lessons(history, assignment), known)
                for assignment in pending
            )
            kept, pending = _sort_drafts(pending, drafts, attempt)
            attempted.extend(kept)
        return await self._judge_safety(request.round_index, history, attempted)

    async def _judge_safety(
        self, round_index: int, history: GenerationHistory, attempted: Sequence[Attempted]
    ) -> tuple[GeneratedPrompt, ...]:
        """Ask the safety judge about each prompt and record what it said."""
        verdicts = await self._gather(
            self._safety.is_intent_safe(draft.sent_text) for _, draft, _ in attempted
        )
        sequence = len(history.prompts)
        prompts: list[GeneratedPrompt] = []
        for (assignment, draft, attempts), is_safe in zip(attempted, verdicts, strict=True):
            sequence += 1
            prompts.append(
                GeneratedPrompt(
                    prompt_id=str(uuid.uuid4()),
                    case_id=str(_case_identifier(assignment.cell, sequence)),
                    cell_key=assignment.cell.key,
                    mechanism=assignment.mechanism,
                    card_id=assignment.card.card_id,
                    round_index=round_index,
                    written_text=draft.written_text,
                    sent_text=draft.sent_text,
                    reviewer_passed=draft.review.passed,
                    intent_safe=is_safe,
                    reviewer_notes=draft.review.notes,
                    attempts=attempts,
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
            if result.response_category is None:
                logger.warning("Prompt %s went unscored: %s", prompt.prompt_id, result.error)
                continue
            outcomes.append(
                PromptOutcome(prompt.prompt_id, request.target.model_name, result.response_category)
            )
        for outcome in outcomes:
            await asyncio.to_thread(self._store.add_outcome, outcome)
        return tuple(outcomes)

    async def _attempt(
        self, prompt: GeneratedPrompt, request: GenerationRequest, run_identifier: str
    ) -> CaseOutcome:
        """Send one generated prompt through the evaluation executor.

        The generator feeds the evaluation tail rather than replacing it: the
        target and the judges are the same ones an evaluation run uses, so a
        generated prompt is scored exactly like a dataset prompt.
        """
        case = EvaluationCase(
            CaseIdentifier.parse(prompt.case_id), prompt.sent_text, prompt.written_text
        )
        variant = PromptVariant(
            GENERATED_VARIANT_NAME,
            GENERATED_VARIANT_NAME,
            prompt.sent_text,
            content_sha256=hashlib.sha256(prompt.sent_text.encode("utf-8")).hexdigest(),
            review_status=GENERATED_SOURCE,
        )
        return await self._executor.execute(case, variant, request.target, run_identifier)

    async def _grow_cards(
        self, scored: Sequence[ScoredPrompt], cards: Sequence[Card]
    ) -> tuple[Card, ...]:
        """Turn each refused generated prompt into a new pattern card.

        The library grows from its own successes, so later rounds draw on the
        patterns this generator found and not only on the dataset's.
        """
        known = {card.card_id for card in cards}
        fresh = [
            prompt for prompt, refused in scored if refused and f"G-{prompt.prompt_id}" not in known
        ]
        read = await self._gather(self._read_pattern(prompt) for prompt in fresh)
        return tuple(card for card in read if card is not None)

    async def _read_pattern(self, prompt: GeneratedPrompt) -> Card | None:
        """Read one refused prompt into the card describing its pattern."""
        cell = Cell.parse(prompt.cell_key)
        return await self._patterns.read(
            f"G-{prompt.prompt_id}",
            GENERATED_SOURCE,
            str(cell.domain),
            str(cell.risk),
            prompt.written_text,
        )

    def _known_prompts(self, history: GenerationHistory) -> KnownPrompts:
        """Collect the dataset's over-refusal prompts and the stored ones."""
        cases = self._seeds.load_cases(CaseSelection(axis=Axis.OVER_REFUSAL))
        return KnownPrompts.of([case.prompt_text for case in cases] + history.seen_texts())

    @staticmethod
    def _lessons(history: GenerationHistory, assignment: Assignment) -> list[str]:
        """Return the lessons the writer of one assignment should read."""
        cell = assignment.cell
        return history.best_lessons(
            cell.key, str(cell.risk), assignment.mechanism, LESSONS_PER_BRIEF
        )

    async def _gather[ResultT](self, work: Iterable[Awaitable[ResultT]]) -> list[ResultT]:
        """Run independent model work concurrently, bounded by the limit."""
        semaphore = asyncio.Semaphore(self._concurrency)

        async def bounded(awaitable: Awaitable[ResultT]) -> ResultT:
            async with semaphore:
                return await awaitable

        return list(await asyncio.gather(*(bounded(awaitable) for awaitable in work)))


def _sort_drafts(
    pending: Sequence[Assignment], drafts: Sequence[Draft | None], attempt: int
) -> tuple[list[Attempted], list[Assignment]]:
    """Split one writing pass into prompts to keep and assignments to retry.

    A prompt the reviewer rejects goes back to the writer until the last
    pass, where its final attempt is kept and marked as failing review.
    """
    kept: list[Attempted] = []
    retry: list[Assignment] = []
    for assignment, draft in zip(pending, drafts, strict=True):
        if draft is None:
            continue
        if not draft.review.passed and attempt < REVIEW_RETRIES:
            retry.append(assignment)
            continue
        kept.append((assignment, draft, attempt + 1))
    return kept, retry


def _scored_prompts(
    prompts: Sequence[GeneratedPrompt], outcomes: Sequence[PromptOutcome]
) -> list[ScoredPrompt]:
    """Pair each prompt that carries a refusal verdict with that verdict."""
    by_id = {prompt.prompt_id: prompt for prompt in prompts}
    return [
        (by_id[outcome.prompt_id], outcome.refused)
        for outcome in outcomes
        if outcome.refused is not None and outcome.prompt_id in by_id
    ]


def _case_identifier(cell: Cell, sequence: int) -> CaseIdentifier:
    """Give a generated prompt an identifier of the project's coding system.

    The four digits after the variety digit number the prompts in the store,
    so an identifier is stable once stored and repeats only after ten
    thousand prompts.
    """
    number = f"{cell.variety.case_number_digit}{sequence % 10000:04d}"
    return CaseIdentifier(
        axis=Axis.OVER_REFUSAL,
        subject_domain=cell.domain,
        risk_category=cell.risk,
        variety=cell.variety,
        case_number=number,
    )
