"""Internal research archival inside the report transaction."""

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from harass.infrastructure.persistence.tables import GeneratedPromptRow, PromptFindingRow, RunRow
from harass.infrastructure.persistence.upsert import insert_for


def archive_findings(session: Session, run: RunRow, document: dict[str, Any]) -> None:
    """Archive generated scored defects once per observation, retaining exact prompt bytes."""
    now = datetime.now(UTC)
    for outcome in document["outcomes"]:
        if not _is_generated_defect(outcome):
            continue
        text = outcome["transcript"]["sent_prompt"]
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        session.execute(
            insert_for(session, GeneratedPromptRow)
            .values(content_sha256=digest, text=text, created_at=now)
            .on_conflict_do_nothing(index_elements=["content_sha256"])
        )
        stored = session.get(GeneratedPromptRow, digest)
        if stored is None or stored.text != text:
            raise ValueError("Generated prompt hash does not identify the exact stored text.")
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


def _is_generated_defect(outcome: dict[str, Any]) -> bool:
    variant = outcome.get("variant")
    transcript = outcome.get("transcript")
    if (
        outcome["variant_name"] == "baseline"
        or outcome.get("error") is not None
        or outcome.get("response_category") not in {"FUL", "PRF", "REF", "UNC"}
        or not variant
        or not transcript
        or not (variant.get("template_name") or variant.get("transform_names"))
        or transcript["sent_prompt"] == outcome["original_prompt"]
    ):
        return False
    return (outcome["axis"] == "AT" and outcome.get("attack_succeeded") is True) or (
        outcome["axis"] == "OR" and outcome["response_category"] in {"PRF", "REF"}
    )
