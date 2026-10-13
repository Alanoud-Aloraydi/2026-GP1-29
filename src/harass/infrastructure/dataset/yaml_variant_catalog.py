"""File-extensible authored templates and deterministic, bounded variant composition."""

import hashlib
from itertools import permutations
from pathlib import Path

import yaml

from harass.application.errors import ApplicationError
from harass.application.ports.variant_catalog import VariantCatalog
from harass.domain.errors import DomainError
from harass.domain.evaluation_case import EvaluationCase
from harass.domain.prompt_variant import (
    PromptTemplate,
    PromptVariant,
    TransformDefinition,
    VariantSelection,
)
from harass.domain.taxonomy import (
    ArabicVariety,
    Axis,
    BypassStrategy,
    OwaspCategory,
    RiskCategory,
    SubjectDomain,
)
from harass.infrastructure.dataset.prompt_transforms import (
    TRANSFORMS,
    apply_transform,
    compatible_sequence,
    has_arabic,
)


class VariantCatalogError(ApplicationError):
    """A library definition or requested library name is invalid."""


class YamlVariantCatalog(VariantCatalog):
    """Load templates and compose deduplicated variants with at most two transforms."""

    def __init__(self, directory: Path) -> None:
        """Read every YAML template file, validating its declared applicability."""
        self._templates = tuple(_load_template(path) for path in sorted(directory.glob("*.yaml")))
        if not self._templates:
            raise VariantCatalogError(f"No template files found in {directory}.")
        names = [template.name for template in self._templates]
        if len(names) != len(set(names)):
            raise VariantCatalogError("Template names must be unique across files.")

    def templates(self) -> tuple[PromptTemplate, ...]:
        """Return all templates in stable filename order."""
        return self._templates

    def transforms(self) -> tuple[TransformDefinition, ...]:
        """Return the local, rule-based transform definitions."""
        return TRANSFORMS

    def variants(self, case: EvaluationCase, selection: VariantSelection) -> list[PromptVariant]:
        """Build eligible variants, retaining recipes and deduplicating actual request text."""
        template_names = _resolve_names(
            selection.template_names, tuple(t.name for t in self._templates)
        )
        transform_names = _resolve_names(
            selection.transform_names, tuple(t.name for t in TRANSFORMS)
        )
        templates: list[PromptTemplate | None] = [None]
        templates.extend(
            t for t in self._templates if t.name in template_names and t.applies_to(case)
        )
        transforms = tuple(
            t for t in TRANSFORMS if t.name in transform_names and t.applies_to(case)
        )
        sequences = [()] + [(t,) for t in transforms] + list(permutations(transforms, 2))
        variants: dict[str, PromptVariant] = {}
        for template in templates:
            for sequence in sequences:
                if not compatible_sequence(sequence):
                    continue
                text = case.prompt_text
                applicable = True
                for transform in sequence:
                    if transform.needs_arabic and not has_arabic(text):
                        applicable = False
                        break
                    text = apply_transform(transform.name, text)
                    if transform.removes_arabic and not transform.is_template and has_arabic(text):
                        applicable = False
                        break
                if not applicable:
                    continue
                if template:
                    text = template.text.replace("{seed}", text)
                if text == case.prompt_text:
                    continue
                names = tuple(t.name for t in sequence)
                recipe = "+".join((template.name if template else "seed", *names))
                digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
                variants.setdefault(
                    digest,
                    PromptVariant(
                        variant_id=recipe,
                        arm_id=template.name if template else f"transform:{names[0]}",
                        sent_prompt=text,
                        template_name=template.name if template else None,
                        template_revision=template.revision if template else None,
                        transform_names=names,
                        effective_strategies=tuple(
                            dict.fromkeys(
                                ([case.identifier.strategy] if case.identifier.strategy else [])
                                + (
                                    [BypassStrategy.OBFUSCATION]
                                    if names and case.axis is Axis.ADVERSARIAL
                                    else []
                                )
                            )
                        ),
                        content_sha256=digest,
                        review_status="requires_language_review"
                        if "arabizi" in names
                        else template.review_status
                        if template
                        else "rule_based",
                        source_urls=tuple(
                            dict.fromkeys(
                                ([template.source] if template else [])
                                + [t.source for t in sequence]
                            )
                        ),
                    ),
                )
        return list(variants.values())


def _resolve_names(
    requested: tuple[str, ...] | None, available: tuple[str, ...]
) -> tuple[str, ...]:
    names = available if requested is None else requested
    unknown = set(names) - set(available)
    if unknown:
        raise VariantCatalogError(f"Unknown library names: {', '.join(sorted(unknown))}.")
    return names


def _load_template(path: Path) -> PromptTemplate:
    try:
        entry = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(entry, dict):
            raise ValueError("Expected a mapping.")
        return PromptTemplate(
            name=str(entry["name"]),
            label=str(entry["label"]),
            text=str(entry["text"]),
            axis=Axis(entry["axis"]),
            strategy=BypassStrategy(entry["strategy"]) if entry.get("strategy") else None,
            varieties=frozenset(ArabicVariety(v) for v in entry["varieties"]),
            revision=str(entry["revision"]),
            source=str(entry["source"]),
            review_status=str(entry.get("review_status", "draft")),
            subject_domains=frozenset(SubjectDomain(v) for v in entry.get("subject_domains", [])),
            risk_categories=frozenset(RiskCategory(v) for v in entry.get("risk_categories", [])),
            owasp_categories=frozenset(
                OwaspCategory(v) for v in entry.get("owasp_categories", [])
            ),
        )
    except (OSError, yaml.YAMLError, ValueError, KeyError, TypeError, DomainError) as error:
        raise VariantCatalogError(f"Invalid template file {path}: {error}") from error
