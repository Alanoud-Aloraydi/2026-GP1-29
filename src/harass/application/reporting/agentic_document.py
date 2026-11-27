"""Serialize an agentic run into the JSON document its report page reads."""

from collections.abc import Sequence
from typing import Any

from harass.application.evaluation.contracts import AgenticParameters
from harass.application.generation.contracts import MEASUREMENT_ROUND
from harass.domain.generation.history import GenerationHistory
from harass.domain.metrics import Proportion
from harass.domain.taxonomy import Axis

AGENTIC_FORMAT_VERSION = 1
# Where the baseline report keeps each axis's headline rate.
BASELINE_RATES = {
    Axis.OVER_REFUSAL: ("over_refusal", "over_refusal"),
    Axis.ADVERSARIAL: ("adversarial", "attack_success"),
}


def agentic_document(
    run_identifier: str,
    target_model: str,
    parameters: AgenticParameters,
    histories: Sequence[GenerationHistory],
    learned: Sequence[dict[str, Any]],
    baseline_metrics: dict[str, Any],
    seeded_cards: int,
) -> dict[str, Any]:
    """Return the rounds, each axis's rates and the baseline they compare with.

    ``histories`` hold each axis's prompts for the target, of which only this
    run's count; ``learned`` lists the lessons and cards each finished round
    added, in round order. The measurement round's rate is comparable with
    the baseline's; the discovery rounds' rate shows what learning found.
    """
    learned_by_unit = {(entry["axis"], entry["round"]): entry for entry in learned}
    rounds: list[dict[str, Any]] = []
    axes: dict[str, dict[str, Any]] = {}
    prompts_count = 0
    for history in histories:
        measured: list[bool] = []
        discovered: list[bool] = []
        for round_index in range(parameters.rounds):
            entry = _round(history, run_identifier, round_index)
            entry.update(_learned(learned_by_unit.get((str(history.axis), round_index))))
            rounds.append(entry)
            prompts_count += entry["prompts"]
            verdicts = _verdicts(history, run_identifier, round_index)
            (measured if round_index == MEASUREMENT_ROUND else discovered).extend(verdicts)
        axes[str(history.axis)] = {
            "baseline": _baseline(baseline_metrics, history.axis),
            "measurement": _proportion(Proportion(sum(measured), len(measured))),
            "discovery": _proportion(Proportion(sum(discovered), len(discovered))),
        }
    return {
        "kind": "agentic",
        "format_version": AGENTIC_FORMAT_VERSION,
        "run_identifier": run_identifier,
        "target_model": target_model,
        "parameters": parameters.document(),
        "seeded_cards": seeded_cards,
        "axes": axes,
        "rounds": sorted(rounds, key=lambda entry: (entry["round"], entry["axis"] != "OR")),
        "prompts_count": prompts_count,
    }


def _round(history: GenerationHistory, run_identifier: str, round_index: int) -> dict[str, Any]:
    """Count one round's prompts, valid prompts, verdicts and successes."""
    prompts = [
        prompt
        for prompt in history.prompts
        if prompt.run_id == run_identifier and prompt.round_index == round_index
    ]
    verdicts = _verdicts(history, run_identifier, round_index)
    return {
        "axis": str(history.axis),
        "round": round_index,
        "phase": "measurement" if round_index == MEASUREMENT_ROUND else "discovery",
        "prompts": len(prompts),
        "valid": sum(prompt.is_valid for prompt in prompts),
        "success": _proportion(Proportion(sum(verdicts), len(verdicts))),
    }


def _verdicts(history: GenerationHistory, run_identifier: str, round_index: int) -> list[bool]:
    """Return the success verdict of each judged prompt of one round."""
    verdicts: list[bool] = []
    for prompt in history.prompts:
        if prompt.run_id != run_identifier or prompt.round_index != round_index:
            continue
        outcome = history.outcomes.get(prompt.prompt_id)
        verdict = outcome.succeeded(history.axis) if outcome else None
        if verdict is not None:
            verdicts.append(verdict)
    return verdicts


def _learned(entry: dict[str, Any] | None) -> dict[str, Any]:
    """Return what a round added, marking a round interrupted before it ended."""
    if entry is None:
        return {"lessons": 0, "cards": 0, "interrupted": False}
    return {
        "lessons": entry["lessons"],
        "cards": entry["cards"],
        "interrupted": entry["interrupted"],
    }


def _baseline(metrics: dict[str, Any], axis: Axis) -> dict[str, Any] | None:
    """Return the baseline run's headline rate on one axis, if it covered it."""
    summary, name = BASELINE_RATES[axis]
    section = metrics.get(summary)
    return section.get(name) if section else None


def _proportion(proportion: Proportion) -> dict[str, Any]:
    """Serialize a count, its rate and its Wilson interval."""
    interval = proportion.wilson_interval()
    return {
        "count": proportion.count,
        "total": proportion.total,
        "rate": proportion.rate,
        "wilson_95": list(interval) if interval else None,
    }
