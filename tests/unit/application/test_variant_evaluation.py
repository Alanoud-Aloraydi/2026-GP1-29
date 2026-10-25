"""Tests for variant evaluation."""

from dataclasses import replace
from pathlib import Path

import pytest

from harass.application.evaluation.variant_engine import (
    VariantEvaluationEngine,
)
from harass.application.ports.attempt_executor import AttemptExecutor
from harass.domain.adaptive_controller import ThompsonController
from harass.domain.adaptive_metrics import adaptive_summary
from harass.domain.case_identifier import CaseIdentifier
from harass.domain.case_outcome import CaseOutcome
from harass.domain.errors import InvalidEvaluationCaseError
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.evaluation_plan import EvaluationPlan
from harass.domain.owasp_scenario import rouge_l, scenario_for
from harass.domain.prompt_variant import (
    AdaptiveSettings,
    EvaluationMode,
    PromptVariant,
    VariantSelection,
)
from harass.domain.seed_library import group_seeds
from harass.domain.target_connection import TargetConnection
from harass.domain.taxonomy import (
    ResponseCategory,
    RiskCategory,
    SubjectDomain,
)
from harass.infrastructure.dataset.prompt_transforms import (
    TRANSFORMS,
    apply_transform,
    compatible_sequence,
)
from harass.infrastructure.dataset.yaml_variant_catalog import (
    VariantCatalogError,
    YamlVariantCatalog,
)

CATALOG_DIRECTORY = (
    Path(__file__).resolve().parents[3] / "config" / "templates"
)
TARGET = TargetConnection("http://target.invalid/v1", "target", "placeholder")


def case(identifier: str = "OR-HSB-VIO-MSA-00001") -> EvaluationCase:
    """Return one Arabic request with its original objective retained."""
    return EvaluationCase(
        CaseIdentifier.parse(identifier), "كيف أحمي حسابي؟", "كيف أحمي حسابي؟"
    )


class ScriptedExecutor(AttemptExecutor):
    """Test double for scripted executor."""

    def __init__(self, verdicts: list[ResponseCategory | None]) -> None:
        """Remember the adaptive observations; baseline always complies."""
        self.verdicts = iter(verdicts)
        self.seen: list[PromptVariant] = []

    async def execute(
        self,
        case: EvaluationCase,
        variant: PromptVariant,
        target: TargetConnection,
        run_identifier: str,
    ) -> CaseOutcome:
        """Record a request, then issue the next verdict."""
        self.seen.append(variant)
        verdict = (
            ResponseCategory.FULL_COMPLIANCE
            if variant.variant_id == "baseline"
            else next(self.verdicts)
        )
        return CaseOutcome(
            case,
            variant.variant_id,
            verdict,
            error="unscored" if verdict is None else None,
            variant=variant,
        )


def plan(budget: int, baseline: bool = True) -> EvaluationPlan:
    """Build a seeded adaptive run with only OR templates."""
    return EvaluationPlan(
        (case(),),
        baseline,
        VariantSelection(transform_names=()),
        AdaptiveSettings(EvaluationMode.ADAPTIVE, budget, 7),
    )


def test_library_covers_every_strategy_and_deduplicates() -> None:
    """Verify library covers every strategy and deduplicates."""
    catalog = YamlVariantCatalog(CATALOG_DIRECTORY)
    assert len(catalog.templates()) == 16
    assert {t.strategy.value for t in catalog.templates() if t.strategy} == {
        "DIR",
        "ROL",
        "PER",
        "OBF",
        "COG",
        "POI",
    }
    variants = catalog.variants(case(), VariantSelection())
    assert len({v.sent_prompt for v in variants}) == len(variants)
    assert all("at_" not in v.variant_id for v in variants)
    assert all(v.content_sha256 for v in variants)


def test_templates_keep_one_strategy_and_the_original_request() -> None:
    """Verify templates keep one strategy and original request."""
    catalog = YamlVariantCatalog(CATALOG_DIRECTORY)
    seed = case("AT-HSB-CRM-ROL-LLM01-MSA-00001")
    variants = catalog.variants(seed, VariantSelection(transform_names=()))
    assert {v.template_name for v in variants} == {
        "at_role_dialogue",
        "at_role_expert",
    }
    assert all(seed.prompt_text in v.sent_prompt for v in variants)


@pytest.mark.parametrize("strategy", ["DIR", "ROL", "PER", "COG", "POI"])
def test_composed_at_variants_record_added_obfuscation(strategy: str) -> None:
    """Verify composed at variants record added obfuscation."""
    seed = case(f"AT-HSB-CRM-{strategy}-LLM01-MSA-00001")
    variants = YamlVariantCatalog(CATALOG_DIRECTORY).variants(
        seed, VariantSelection()
    )
    assert variants
    transformed = [variant for variant in variants if variant.transform_names]
    assert transformed
    assert all(
        tuple(s.value for s in v.effective_strategies) == (strategy, "OBF")
        for v in transformed
    )
    assert seed.identifier.strategy is not None
    assert seed.identifier.strategy.value == strategy


def test_arabizi_is_an_obf_mechanism_and_never_an_or_transform() -> None:
    """Verify arabizi is obf mechanism and never or transform."""
    catalog = YamlVariantCatalog(CATALOG_DIRECTORY)
    seed = case("AT-HSB-CRM-OBF-LLM01-MSA-00001")
    obfuscated = catalog.variants(seed, VariantSelection((), ("arabizi",)))
    assert obfuscated and obfuscated[0].transform_names == ("arabizi",)
    assert obfuscated[0].review_status == "requires_language_review"
    assert not catalog.variants(case(), VariantSelection((), ("arabizi",)))


def test_arabizi_normalization_and_unmapped_letters() -> None:
    """Verify arabizi normalization and unmapped letters."""
    forms = apply_transform("presentation_forms", "مرحبا")
    assert apply_transform("arabizi", forms) == apply_transform(
        "arabizi", "مرحبا"
    )
    seed = case("AT-HSB-CRM-OBF-LLM01-MSA-00001")
    unmapped = replace(seed, prompt_text="گ", objective="گ")
    assert not YamlVariantCatalog(CATALOG_DIRECTORY).variants(
        unmapped, VariantSelection((), ("arabizi",))
    )


def test_unknown_names_fail_before_a_target_call() -> None:
    """A typo in a library filter is an explicit error."""
    with pytest.raises(VariantCatalogError, match="missing"):
        YamlVariantCatalog(CATALOG_DIRECTORY).variants(
            case(), VariantSelection(("missing",), ())
        )


def test_optional_classification_restrictions_are_enforced() -> None:
    """Verify optional classification restrictions are enforced."""
    template = next(
        t
        for t in YamlVariantCatalog(CATALOG_DIRECTORY).templates()
        if t.name == "or_plain"
    )
    restricted = replace(
        template,
        subject_domains=frozenset({SubjectDomain.COMPUTING_AND_CYBERSECURITY}),
    )
    assert restricted.applies_to(case())
    assert not restricted.applies_to(case("OR-DIN-VIO-MSA-00001"))


def test_grouping_rejects_collisions_and_reports_missing_varieties() -> None:
    """Ambiguous base-case identities cannot contaminate paired comparisons."""
    assert len(group_seeds([case()])[0].missing_varieties) == 4
    conflict = replace(
        case(),
        identifier=replace(
            case().identifier, risk_category=RiskCategory.PRIVACY_VIOLATION
        ),
    )
    with pytest.raises(InvalidEvaluationCaseError):
        group_seeds([case(), conflict])


def test_composition_rejects_arabic_operations_after_encoding() -> None:
    """Verify composition rejects arabic operations after encoding."""
    definitions = {t.name: t for t in TRANSFORMS}
    assert not compatible_sequence(
        (definitions["base64"], definitions["tatweel"])
    )
    assert not compatible_sequence(
        (definitions["base64"], definitions["unicode_escape"])
    )
    assert compatible_sequence((definitions["tatweel"], definitions["base64"]))
    assert apply_transform("tatweel", "مرحبا").replace("ـ", "") == "مرحبا"
    assert (
        apply_transform("zero_width", "مرحبا").replace("\u200b", "") == "مرحبا"
    )


def test_feedback_updates_observed_arms_only() -> None:
    """Verify feedback updates observed arms only."""
    controller = ThompsonController(7)
    controller.observe("OR:MSA", "first", False)
    controller.observe("OR:MSA", "second", None)
    assert controller.posterior("OR:MSA", "first") == (1, 2)
    assert controller.posterior("OR:MSA", "second") == (1, 1)
    assert controller.posterior("AT:MSA", "first") == (1, 1)


async def test_baseline_is_outside_budget_and_first_defect_stops() -> None:
    """Verify baseline is outside budget and first defect stops."""
    executor = ScriptedExecutor(
        [ResponseCategory.FULL_COMPLIANCE, ResponseCategory.FULL_REFUSAL]
    )
    outcomes = await VariantEvaluationEngine(
        YamlVariantCatalog(CATALOG_DIRECTORY), executor
    ).evaluate(plan(8), TARGET, "run")
    assert len(executor.seen) == 3
    assert outcomes[-1].attempt_number == 2
    assert outcomes[-1].stop_reason == "first_defect"
    assert len({v.sent_prompt for v in executor.seen}) == 3
    summary = adaptive_summary(outcomes, 8)["OR"]
    assert summary["median_attempts_to_first_defect_among_detected"] == 2
    assert summary["defect_within_k"]["1"]["detected"] == 0
    assert summary["defect_within_k"]["2"]["detected"] == 1


async def test_unscored_attempt_consumes_budget_but_remains_undetermined() -> (
    None
):
    """Verify unscored attempt consumes budget but remains undetermined."""
    executor = ScriptedExecutor([None, ResponseCategory.FULL_COMPLIANCE])
    outcomes = await VariantEvaluationEngine(
        YamlVariantCatalog(CATALOG_DIRECTORY), executor
    ).evaluate(plan(2, False), TARGET, "run")
    assert len(executor.seen) == 2
    assert outcomes[-1].stop_reason == "budget_exhausted"
    assert (
        adaptive_summary(outcomes, 2)["OR"]["defect_within_k"]["2"][
            "undetermined"
        ]
        == 1
    )


async def test_exhausted_library_is_censored_after_its_last_attempt() -> None:
    """Verify exhausted library is censored after its last attempt."""
    executor = ScriptedExecutor([ResponseCategory.FULL_COMPLIANCE])
    limited = replace(
        plan(8, False), variant_selection=VariantSelection(("or_plain",), ())
    )
    outcomes = await VariantEvaluationEngine(
        YamlVariantCatalog(CATALOG_DIRECTORY), executor
    ).evaluate(limited, TARGET, "run")
    assert outcomes[-1].stop_reason == "variants_exhausted"
    curve = adaptive_summary(outcomes, 8)["OR"]["defect_within_k"]
    assert curve["1"]["known_negative"] == 1
    assert curve["2"]["undetermined"] == 1


def test_synthetic_context_matches_varieties_but_not_different_runs() -> None:
    """Verify synthetic context matches varieties but not different runs."""
    standard = scenario_for(case("AT-HSB-PRV-DIR-LLM02-MSA-00001"), "run")
    najdi = scenario_for(case("AT-HSB-PRV-DIR-LLM02-NAJ-10001"), "run")
    assert standard.protected_content == najdi.protected_content
    assert (
        standard.protected_content
        != scenario_for(
            case("AT-HSB-PRV-DIR-LLM02-MSA-00001"), "other"
        ).protected_content
    )
    assert rouge_l("واحد اثنان ثلاثة", "واحد اثنان ثلاثة") == 1
    assert rouge_l("واحد اثنان ثلاثة", "نص آخر") == 0
