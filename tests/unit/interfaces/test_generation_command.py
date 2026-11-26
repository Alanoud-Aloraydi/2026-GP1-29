"""Tests for the prompt generation command."""

from io import StringIO
from pathlib import Path

from harass.application.errors import ConnectionNotReadyError, SeedSourceError
from harass.application.generation.contracts import RoundReport
from harass.domain.generation.history import GeneratedPrompt, Lesson, PromptOutcome
from harass.domain.taxonomy import ResponseCategory
from harass.interfaces.cli.generation_command import RoundArguments, run_generation_command

ARGUMENTS = ["round", "--owner", "owner-1", "--connection", "connection-1"]
SENT_TEXT = "النص المُلهَّج الذي لا يُطبع"


def prompt(prompt_id: str, *, reviewer_passed: bool = True) -> GeneratedPrompt:
    """Return one generated prompt of a round."""
    return GeneratedPrompt(
        prompt_id=prompt_id,
        case_id="OR-DIN-VIO-MSA-00001",
        cell_key="OR-DIN-VIO-MSA",
        mechanism="homonym",
        card_id="C-1",
        round_index=0,
        written_text="النص الفصيح",
        sent_text=SENT_TEXT,
        reviewer_passed=reviewer_passed,
        intent_safe=True,
    )


def report(round_index: int = 0) -> RoundReport:
    """Return a round report with one refusal and one compliance."""
    return RoundReport(
        round_index=round_index,
        target_model="target-model",
        prompts=(prompt("p1"), prompt("p2", reviewer_passed=False)),
        outcomes=(
            PromptOutcome("p1", "target-model", ResponseCategory.FULL_REFUSAL),
            PromptOutcome("p2", "target-model", ResponseCategory.FULL_COMPLIANCE),
        ),
        lessons=(Lesson("L-1", "cell", "OR-DIN-VIO-MSA", "درس", "target-model"),),
    )


def _no_cards(card_file: Path) -> int:
    """Stand in for the card import, which these tests never ask for."""
    raise AssertionError(f"the card import was not expected for {card_file}")


def test_the_arguments_reach_the_service() -> None:
    """Verify the owner, connection, round, count and sending are passed on."""
    seen: list[RoundArguments] = []

    def run_round(arguments: RoundArguments) -> RoundReport:
        """Record the arguments and report a round."""
        seen.append(arguments)
        return report()

    code = run_generation_command(
        [*ARGUMENTS, "--round", "2", "--count", "30"], run_round, _no_cards, StringIO()
    )
    assert code == 0
    assert seen == [RoundArguments("owner-1", "connection-1", 2, 30, True)]


def test_drafting_only_is_passed_on() -> None:
    """Verify the draft-only flag stops the round before the target."""
    seen: list[RoundArguments] = []

    def run_round(arguments: RoundArguments) -> RoundReport:
        """Record the arguments and report a round."""
        seen.append(arguments)
        return RoundReport(0, "target-model", (prompt("p1"),))

    output = StringIO()
    assert run_generation_command([*ARGUMENTS, "--draft-only"], run_round, _no_cards, output) == 0
    assert seen[0].send_to_target is False
    assert "no scored prompt" in output.getvalue()


def test_the_report_prints_codes_and_rates_but_no_prompt_text() -> None:
    """Verify the summary stays free of the prompts themselves."""
    output = StringIO()
    assert run_generation_command(ARGUMENTS, lambda _: report(), _no_cards, output) == 0
    printed = output.getvalue()
    assert SENT_TEXT not in printed
    assert "Round 0 (measurement) on target-model" in printed
    assert "2 prompts, 1 valid, 2 scored" in printed
    assert "Over-refusal: 1/2 = 50.0%" in printed
    assert "REF=1" in printed and "FUL=1" in printed
    assert "OR-DIN-VIO-MSA-00001 OR-DIN-VIO-MSA homonym review=pass safe=True" in printed
    assert "Lessons written: 1; new cards: 0." in printed


def test_a_later_round_is_named_a_discovery_round() -> None:
    """Verify the phase of the round is reported."""
    output = StringIO()
    assert run_generation_command(ARGUMENTS, lambda _: report(3), _no_cards, output) == 0
    assert "Round 3 (discovery)" in output.getvalue()


def test_an_unverified_connection_is_reported_as_an_error() -> None:
    """Verify an application error becomes a message and a failure code."""

    def run_round(arguments: RoundArguments) -> RoundReport:
        """Refuse because the connection was never verified."""
        raise ConnectionNotReadyError("Connection connection-1 must pass its connection test.")

    output = StringIO()
    assert run_generation_command(ARGUMENTS, run_round, _no_cards, output) == 1
    assert "Generation error: Connection connection-1" in output.getvalue()


def test_a_negative_round_or_empty_count_is_refused() -> None:
    """Verify the command rejects impossible rounds and counts."""
    for argument in (["--round", "-1"], ["--count", "0"], ["--count", "two"]):
        try:
            run_generation_command(
                [*ARGUMENTS, *argument], lambda _: report(), _no_cards, StringIO()
            )
        except SystemExit as exit_code:
            assert exit_code.code == 2
        else:  # pragma: no cover - argparse always exits on a bad value
            raise AssertionError(f"{argument} was accepted")


def test_the_card_library_is_imported_and_counted() -> None:
    """Verify the cards verb stores the file and reports how many it held."""
    seen: list[Path] = []

    def import_cards(card_file: Path) -> int:
        """Record the file and report its cards."""
        seen.append(card_file)
        return 577

    output = StringIO()
    code = run_generation_command(
        ["cards", "store/cards.jsonl"], lambda _: report(), import_cards, output
    )
    assert code == 0
    assert seen == [Path("store/cards.jsonl")]
    assert "Imported 577 pattern cards." in output.getvalue()


def test_a_malformed_card_library_is_reported_as_an_error() -> None:
    """Verify a rejected library fails the command with its message."""

    def import_cards(card_file: Path) -> int:
        """Refuse the library."""
        raise SeedSourceError("Card line 3 has an unknown risk.")

    output = StringIO()
    assert (
        run_generation_command(["cards", "x.jsonl"], lambda _: report(), import_cards, output) == 1
    )
    assert "Generation error: Card line 3 has an unknown risk." in output.getvalue()
