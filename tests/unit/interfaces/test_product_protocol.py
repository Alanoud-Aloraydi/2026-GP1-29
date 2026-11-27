"""Behavioral tests for the evaluation request protocol and browser contracts."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from harass.domain.taxonomy import ArabicVariety, Axis
from harass.interfaces.api.connections.schemas import ConnectionRequest
from harass.interfaces.api.evaluations.mapping import run_parameters
from harass.interfaces.api.evaluations.schemas import RunRequest


def test_a_run_request_keeps_the_selected_axis_and_varieties() -> None:
    """Verify the chosen axis and varieties reach the run parameters."""
    body = RunRequest(
        connection_id="connection",
        selection={"axis": "OR", "varieties": ["NAJ"]},  # type: ignore[arg-type]
    )
    parameters = run_parameters(body)
    assert parameters.selection.axis is Axis.OVER_REFUSAL
    assert parameters.selection.varieties == {ArabicVariety.NAJDI}


def test_an_agentic_request_defaults_to_three_rounds_of_twenty() -> None:
    """Verify an agentic request carries its rounds and bounds them."""
    body = RunRequest(connection_id="connection", kind="agentic")
    assert (body.agentic.rounds, body.agentic.prompts_per_round) == (3, 20)
    with pytest.raises(ValidationError):
        RunRequest(connection_id="connection", kind="agentic", agentic={"rounds": 6})  # type: ignore[arg-type]


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
    markup = (root / "frontend" / "model-configuration.html").read_text(encoding="utf-8")
    options = re.findall(r"<option\b([^>]*)>", markup)
    assert len(options) == 2
    assert 'value="openai_compatible"' in options[0]
    assert "disabled" in options[1]


def test_browser_report_escapes_evidence() -> None:
    """Verify the browser report escapes evidence and shows run progress."""
    _run_frontend_contract("report")


def test_browser_prevents_native_submission_before_account_loads() -> None:
    """Verify browser prevents native submission before account loads."""
    _run_frontend_contract("initialization")


def test_shared_header_switches_between_public_and_account_navigation() -> None:
    """Verify shared header switches between public and account navigation."""
    _run_frontend_contract("shell")


def _run_frontend_contract(name: str) -> None:
    """Execute an isolated browser contract using Node's standard library."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Frontend contract checks require Node.js.")
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [node, str(root / "tests/frontend" / (name + ".cjs")), str(root / "frontend/assets/js")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
