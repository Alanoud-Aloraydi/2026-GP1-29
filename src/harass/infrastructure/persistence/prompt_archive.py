"""Internal research archival inside the report transaction."""

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from harass.domain.case_outcome import BASELINE_VARIANT_NAME
from harass.domain.taxonomy import Axis, ResponseCategory
from harass.infrastructure.persistence.tables import GeneratedPromptRow, PromptFindingRow, RunRow
from harass.infrastructure.persistence.upsert import insert_for

REFUSALS = {ResponseCategory.PARTIAL_REFUSAL, ResponseCategory.FULL_REFUSAL}


def archive_findings(session: Session, run: RunRow, document: dict[str, Any]) -> None:
    """Archive scored generated defects with exact prompt bytes."""
    now = datetime.now(UTC)
    for outcome in document["outcomes"]:
        if not _is_generated_defect(outcome):
            continue
        digest = _store_prompt(session, outcome["transcript"]["sent_prompt"])
        session.execute(
            insert_for(session, PromptFindingRow)
            .values(
                finding_id=str(uuid.uuid4()),
                content_sha256=digest,
                run_id=run.run_id,
                case_id=outcome["case_id"],
                variant_id=outcome["variant_name"],
                attempt_number=outcome["attempt_number"],
                axis=outcome["axis"],
                target_model=document.get("target_model", run.target_model),
                target_endpoint=document.get("target_endpoint", ""),
                recorded_at=now,
                evidence={"label_source": "automated_judge", "outcome": outcome},
            )
            .on_conflict_do_nothing(
                index_elements=["run_id", "case_id", "variant_id", "attempt_number"]
            )
        )


def _store_prompt(session: Session, text: str) -> str:
    """Store prompt text once by its hash and return that hash."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    session.execute(
        insert_for(session, GeneratedPromptRow)
        .values(content_sha256=digest, text=text, created_at=datetime.now(UTC))
        .on_conflict_do_nothing(index_elements=["content_sha256"])
    )
    stored = session.get(GeneratedPromptRow, digest)
    if stored is None or stored.text != text:
        raise ValueError("Generated prompt hash does not identify the exact stored text.")
    return digest


def _is_generated_defect(outcome: dict[str, Any]) -> bool:
    """Admit generated, scored defects with complete prompt provenance."""
    variant = outcome.get("variant")
    transcript = outcome.get("transcript")
    if (
        outcome["variant_name"] == BASELINE_VARIANT_NAME
        or outcome.get("error") is not None
        or outcome.get("response_category") not in set(ResponseCategory)
        or not variant
        or not transcript
        or not (variant.get("template_name") or variant.get("transform_names"))
        or transcript["sent_prompt"] == outcome["original_prompt"]
    ):
        return False
    if outcome["axis"] == Axis.ADVERSARIAL:
        return outcome.get("attack_succeeded") is True
    return outcome["response_category"] in REFUSALS
