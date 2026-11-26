"""Import pattern cards, or run one round, with the services injected.

The command prints only codes, verdicts and counts: the prompts themselves
stay in the database, where the application reads them with their evidence.
"""

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TextIO

from harass.application.errors import ApplicationError
from harass.application.generation.contracts import RoundReport
from harass.domain.errors import DomainError


@dataclass(frozen=True)
class RoundArguments:
    """What one invocation asks the generator to do."""

    owner_id: str
    connection_id: str
    round_index: int
    count: int
    send_to_target: bool


type RunRound = Callable[[RoundArguments], RoundReport]
type ImportCards = Callable[[Path], int]


def run_generation_command(
    argv: Sequence[str], run_round: RunRound, import_cards: ImportCards, output: TextIO
) -> int:
    """Import a card library, or generate one round, and report the result.

    A round needs the cards the writer draws its patterns from, so the card
    import is a verb of the same command rather than a separate tool.
    """
    arguments = _parse(argv)
    try:
        if arguments.action == "cards":
            print(f"Imported {import_cards(arguments.file)} pattern cards.", file=output)
            return 0
        _print_report(run_round(_round_arguments(arguments)), output)
    except (OSError, ValueError, ApplicationError, DomainError) as error:
        print(f"Generation error: {error}", file=output)
        return 1
    return 0


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    """Read the verb and its options, rejecting impossible rounds and counts."""
    parser = argparse.ArgumentParser(
        prog="harass-generate",
        description="Generate over-refusal prompts for one round and score them.",
    )
    actions = parser.add_subparsers(dest="action", required=True)
    cards = actions.add_parser("cards", help="store the pattern cards of a JSON lines file")
    cards.add_argument("file", type=Path)
    round_action = actions.add_parser("round", help="generate and judge one round")
    round_action.add_argument("--owner", required=True, help="identifier of the owner")
    round_action.add_argument("--connection", required=True, help="identifier of the connection")
    round_action.add_argument(
        "--round", type=_number, default=0, help="0 measures, later rounds explore"
    )
    round_action.add_argument(
        "--count", type=partial(_number, minimum=1), default=5, help="cells to plan"
    )
    round_action.add_argument(
        "--draft-only",
        action="store_true",
        help="write and judge the prompts without sending any to the target",
    )
    return parser.parse_args(argv)


def _round_arguments(arguments: argparse.Namespace) -> RoundArguments:
    """Collect the round options the service needs."""
    return RoundArguments(
        owner_id=arguments.owner,
        connection_id=arguments.connection,
        round_index=arguments.round,
        count=arguments.count,
        send_to_target=not arguments.draft_only,
    )


def _print_report(report: RoundReport, output: TextIO) -> None:
    """Print the round's counts, its rate and one line per prompt."""
    phase = "discovery" if report.round_index else "measurement"
    proportion = report.over_refusal
    rate, interval = proportion.rate, proportion.wilson_interval()
    categories = " ".join(
        f"{category}={count}" for category, count in sorted(report.categories.items())
    )
    print(
        f"Round {report.round_index} ({phase}) on {report.target_model}: "
        f"{len(report.prompts)} prompts, {len(report.valid_prompts)} valid, "
        f"{len(report.outcomes)} scored.",
        file=output,
    )
    if rate is None or interval is None:
        print("Over-refusal: no scored prompt in this round.", file=output)
    else:
        print(
            f"Over-refusal: {proportion.count}/{proportion.total} = {rate:.1%} "
            f"[{interval[0]:.1%}, {interval[1]:.1%}]; {categories}.",
            file=output,
        )
    for prompt in report.prompts:
        print(
            f"  {prompt.case_id} {prompt.cell_key} {prompt.mechanism} "
            f"review={'pass' if prompt.reviewer_passed else 'fail'} "
            f"safe={prompt.intent_safe} attempts={prompt.attempts}",
            file=output,
        )
    print(f"Lessons written: {len(report.lessons)}; new cards: {len(report.cards)}.", file=output)


def _number(value: str, minimum: int = 0) -> int:
    """Parse a whole number of at least the minimum."""
    if not value.isdigit() or int(value) < minimum:
        raise argparse.ArgumentTypeError(f"Expected a whole number of {minimum} or more.")
    return int(value)
