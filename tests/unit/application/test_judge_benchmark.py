"""Tests for running and reporting a judge benchmark."""

import json

import pytest

from harass.application.judge_benchmark import (
    benchmark_report,
    run_benchmark,
)
from harass.application.ports.response_judge import ResponseJudge
from harass.domain.judge_benchmark import (
    AttackVerdict,
    GoldCase,
    JudgeVerdict,
)
from harass.domain.taxonomy import Axis, ResponseCategory

FUL = ResponseCategory.FULL_COMPLIANCE
PRF = ResponseCategory.PARTIAL_REFUSAL
REF = ResponseCategory.FULL_REFUSAL


class ScriptedJudge(ResponseJudge):
    """Return the next scripted verdict for each case key."""

    def __init__(self, script: dict[str, list[JudgeVerdict]]) -> None:
        """Store the verdicts to hand out in order."""
        self._script = {key: iter(items) for key, items in script.items()}
        self.calls: list[str] = []

    async def judge(self, case: GoldCase) -> JudgeVerdict:
        """Return the next verdict scripted for the case."""
        self.calls.append(case.key)
        return next(self._script[case.key])


def verdict(
    category: ResponseCategory | None,
    attack: bool | None = None,
    *,
    seconds: float = 1.0,
    calls: int = 3,
    failure: str | None = None,
) -> JudgeVerdict:
    """Build a judge verdict."""
    return JudgeVerdict(category, attack, calls, seconds, failure)


def case(
    key: str,
    category: ResponseCategory,
    *,
    axis: Axis = Axis.OVER_REFUSAL,
    attack: AttackVerdict | None = None,
    dialect: str = "MSA",
    response: str = "short",
    truncated: bool = False,
) -> GoldCase:
    """Build a gold case whose family is the key's first part."""
    return GoldCase(
        key=key,
        family=key.split("|")[0],
        axis=axis,
        dialect=dialect,
        request="q",
        response=response,
        criterion="c" if axis is Axis.ADVERSARIAL else None,
        category=category,
        attack_success=attack,
        truncated=truncated,
    )


async def test_every_case_is_judged_once_per_trial_in_order() -> None:
    """Cases run sequentially, repeating each one for every trial."""
    cases = [case("a|1", FUL), case("b|1", REF)]
    judge = ScriptedJudge(
        {
            "a|1": [verdict(FUL), verdict(FUL)],
            "b|1": [verdict(REF), verdict(REF)],
        }
    )

    results = await run_benchmark(cases, judge, trials=2)

    assert judge.calls == ["a|1", "a|1", "b|1", "b|1"]
    assert [len(result.verdicts) for result in results] == [2, 2]


async def test_zero_trials_are_rejected() -> None:
    """A benchmark needs at least one judgment per case."""
    with pytest.raises(ValueError, match="trial"):
        await run_benchmark([], ScriptedJudge({}), trials=0)


async def test_a_perfect_judge_passes_the_gate() -> None:
    """Matching every gold label gives kappa one and clears the floors."""
    cases = [
        case("a|1", FUL),
        case("b|1", REF),
        case("c|1", FUL),
        case("d|1", REF),
        case("e|1", PRF),
        case("f|1", REF, axis=Axis.ADVERSARIAL, attack=AttackVerdict.FALSE),
        case("g|1", FUL, axis=Axis.ADVERSARIAL, attack=AttackVerdict.TRUE),
        case("h|1", FUL, axis=Axis.ADVERSARIAL, attack=AttackVerdict.TRUE),
    ]
    judge = ScriptedJudge(
        {
            "a|1": [verdict(FUL)],
            "b|1": [verdict(REF)],
            "c|1": [verdict(FUL)],
            "d|1": [verdict(REF)],
            "e|1": [verdict(PRF)],
            "f|1": [verdict(REF, False)],
            "g|1": [verdict(FUL, True)],
            "h|1": [verdict(FUL, True)],
        }
    )

    report = benchmark_report(
        await run_benchmark(cases, judge),
        judge={"model": "m"},
        split="test",
        resamples=50,
    )

    assert report["category"]["OR"]["kappa"] == pytest.approx(1.0)
    assert report["attack_success"]["labels"]["TRUE"]["recall"] == 1.0
    assert report["gate"]["passes"] is True
    assert (
        report["over_refusal_rates"]["gold"]
        == report["over_refusal_rates"]["judge"]
    )
    json.dumps(report)


async def test_missing_attack_recall_fails_the_gate() -> None:
    """Failing to detect successful attacks fails the recall floor."""
    cases = [
        case("a|1", FUL, axis=Axis.ADVERSARIAL, attack=AttackVerdict.TRUE),
        case("b|1", FUL, axis=Axis.ADVERSARIAL, attack=AttackVerdict.TRUE),
        case("c|1", REF, axis=Axis.ADVERSARIAL, attack=AttackVerdict.FALSE),
    ]
    judge = ScriptedJudge(
        {
            "a|1": [verdict(FUL, True)],
            "b|1": [verdict(FUL, False)],
            "c|1": [verdict(REF, False)],
        }
    )

    report = benchmark_report(
        await run_benchmark(cases, judge),
        judge={},
        split="dev",
        resamples=20,
    )

    assert report["attack_success"]["labels"]["TRUE"]["recall"] == 0.5
    assert report["gate"]["attack_recall_ok"] is False
    assert report["gate"]["passes"] is False


async def test_coverage_counts_what_is_left_out() -> None:
    """Abstained, unjudged and truncated cases are counted, not dropped."""
    cases = [
        case("a|1", FUL, axis=Axis.ADVERSARIAL, attack=AttackVerdict.ABSTAIN),
        case("b|1", FUL, axis=Axis.ADVERSARIAL, attack=AttackVerdict.TRUE),
        case("c|1", FUL, truncated=True),
    ]
    judge = ScriptedJudge(
        {
            "a|1": [verdict(FUL, True)],
            "b|1": [verdict(None, None, failure="TimeoutError")],
            "c|1": [verdict(FUL)],
        }
    )

    report = benchmark_report(
        await run_benchmark(cases, judge),
        judge={},
        split="test",
        resamples=20,
    )

    assert report["coverage"] == {
        "unjudged_category": 1,
        "unjudged_attack": 1,
        "gold_abstain": 1,
        "gold_truncated": 1,
    }
    assert report["cost"]["failures"] == 1
    assert report["attack_success"] is None


async def test_judge_bias_in_refusal_rates_is_visible() -> None:
    """A judge that over-calls refusals inflates the judged rates."""
    cases = [case(f"f{index}|1", FUL) for index in range(4)]
    judge = ScriptedJudge(
        {
            "f0|1": [verdict(REF)],
            "f1|1": [verdict(PRF)],
            "f2|1": [verdict(FUL)],
            "f3|1": [verdict(FUL)],
        }
    )

    report = benchmark_report(
        await run_benchmark(cases, judge),
        judge={},
        split="test",
        resamples=20,
    )

    assert report["over_refusal_rates"]["gold"] == {
        "strict": 0.0,
        "broad": 0.0,
    }
    assert report["over_refusal_rates"]["judge"] == {
        "strict": 0.25,
        "broad": 0.5,
    }


async def test_accuracy_is_split_by_dialect_and_response_length() -> None:
    """Breakdowns expose dialect and verbosity effects."""
    cases = [
        case("a|1", FUL, dialect="MSA", response="x" * 10),
        case("b|1", FUL, dialect="NAJ", response="x" * 500),
        case("c|1", FUL, dialect="NAJ", response="x" * 2000),
    ]
    judge = ScriptedJudge(
        {
            "a|1": [verdict(FUL)],
            "b|1": [verdict(REF)],
            "c|1": [verdict(FUL)],
        }
    )

    report = benchmark_report(
        await run_benchmark(cases, judge),
        judge={},
        split="test",
        resamples=20,
    )

    assert report["accuracy_by_dialect"] == {"MSA": 1.0, "NAJ": 0.5}
    assert report["accuracy_by_response_length"] == {
        "301_to_1000": 0.0,
        "over_1000": 1.0,
        "up_to_300": 1.0,
    }


async def test_flip_rate_and_cost_use_every_trial() -> None:
    """Stability counts disagreeing trials; cost averages all verdicts."""
    cases = [case("a|1", FUL), case("b|1", FUL)]
    judge = ScriptedJudge(
        {
            "a|1": [verdict(FUL, seconds=2), verdict(REF, seconds=4)],
            "b|1": [verdict(FUL, seconds=2), verdict(FUL, seconds=4)],
        }
    )

    report = benchmark_report(
        await run_benchmark(cases, judge, trials=2),
        judge={},
        split="test",
        resamples=20,
    )

    assert report["stability"]["category_flip_rate"] == 0.5
    assert report["cost"]["mean_seconds"] == 3.0
    assert report["cost"]["cases_per_hour"] == 1200.0
    assert report["cost"]["judge_calls_per_case"] == 3.0
    assert report["gate"]["throughput_ok"] is True


async def test_slow_judge_fails_the_throughput_floor() -> None:
    """Fewer than the required cases per hour fails the gate."""
    judge = ScriptedJudge({"a|1": [verdict(FUL, seconds=10)]})

    report = benchmark_report(
        await run_benchmark([case("a|1", FUL)], judge),
        judge={},
        split="test",
        resamples=20,
    )

    assert report["gate"]["throughput_ok"] is False
    assert report["gate"]["passes"] is False
