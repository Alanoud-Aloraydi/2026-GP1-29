"""Behavioral tests for the product's two fixed evaluation protocols."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from harass.domain.prompt_variant import EvaluationMode, VariantSelection
from harass.domain.taxonomy import ArabicVariety, Axis
from harass.interfaces.api.connections.schemas import ConnectionRequest
from harass.interfaces.api.evaluations.mapping import run_parameters
from harass.interfaces.api.evaluations.schemas import RunRequest


def test_baseline_preserves_selected_axes_and_varieties() -> None:
    """Verify baseline preserves selected axes and varieties."""
    body = RunRequest(
        connection_id="connection",
        run_type="baseline",
        selection={"axis": "OR", "varieties": ["NAJ"]},  # type: ignore[arg-type]
        include_baseline=False,
        attempt_budget=99,
        template_names=["or_plain"],
    )
    parameters = run_parameters(body)
    assert parameters.include_baseline
    assert parameters.selection.axis is Axis.OVER_REFUSAL
    assert parameters.selection.varieties == {ArabicVariety.NAJDI}
    assert parameters.variant_selection == VariantSelection((), ())
    assert parameters.adaptive_settings.mode is EvaluationMode.STATIC


def test_agentic_uses_matched_controls_and_fixed_budget() -> None:
    """Verify agentic uses matched controls and fixed budget."""
    parameters = run_parameters(
        RunRequest(connection_id="connection", run_type="agentic")
    )
    assert parameters.selection.axis is None
    assert parameters.include_baseline
    assert parameters.variant_selection == VariantSelection()
    assert parameters.adaptive_settings.mode is EvaluationMode.ADAPTIVE
    assert parameters.adaptive_settings.attempt_budget == 8


def test_unsupported_connection_protocol_is_rejected() -> None:
    """Verify unsupported connection protocol is rejected."""
    with pytest.raises(ValidationError):
        ConnectionRequest(
            base_url="https://api.invalid",
            model_name="model",
            api_compatibility="other",  # type: ignore[arg-type]
        )


def test_connection_form_disables_unsupported_protocols() -> None:
    """Verify connection form disables unsupported protocols."""
    root = Path(__file__).resolve().parents[3]
    markup = (root / "frontend" / "model-configuration.html").read_text(
        encoding="utf-8"
    )
    options = re.findall(r"<option\b([^>]*)>", markup)
    assert len(options) == 2
    assert 'value="openai_compatible"' in options[0]
    assert "disabled" in options[1]


def test_browser_report_escapes_evidence_and_separates_control_rates() -> None:
    """Verify browser report escapes evidence and separates control rates."""
    _run_frontend_contract("report")


def test_browser_prevents_native_submission_before_account_loads() -> None:
    """Verify browser prevents native submission before account loads."""
    _run_frontend_contract("initialization")


def test_shared_header_switches_between_public_and_account_navigation() -> (
    None
):
    """Verify shared header switches between public and account navigation."""
    _run_frontend_contract("shell")


def _run_frontend_contract(name: str) -> None:
    """Execute an isolated browser contract using Node's standard library."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Frontend contract checks require Node.js.")
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [
            node,
            str(root / "tests/frontend" / (name + ".cjs")),
            str(root / "frontend/assets/js"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
