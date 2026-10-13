"""Behavioral tests for the product's two fixed evaluation protocols."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from harass.domain.prompt_variant import EvaluationMode, VariantSelection
from harass.domain.taxonomy import ArabicVariety, Axis
from harass.interfaces.api.app import _parameters
from harass.interfaces.api.schemas import ConnectionRequest, RunRequest


def test_baseline_sends_only_original_requests_on_selected_axes_and_varieties() -> None:
    """Original-only mode cannot inherit adaptive settings from the advanced contract."""
    body = RunRequest(
        connection_id="connection",
        run_type="baseline",
        selection={"axis": "OR", "varieties": ["NAJ"]},  # type: ignore[arg-type]
        include_baseline=False,
        attempt_budget=99,
        template_names=["or_plain"],
    )
    parameters = _parameters(body)
    assert parameters.include_baseline
    assert parameters.selection.axis is Axis.OVER_REFUSAL
    assert parameters.selection.varieties == {ArabicVariety.NAJDI}
    assert parameters.variant_selection == VariantSelection((), ())
    assert parameters.adaptive_settings.mode is EvaluationMode.STATIC


def test_agentic_covers_both_axes_with_a_matched_control_and_fixed_budget() -> None:
    """Default full evaluation uses automatic libraries and the predeclared protocol."""
    parameters = _parameters(RunRequest(connection_id="connection", run_type="agentic"))
    assert parameters.selection.axis is None
    assert parameters.include_baseline
    assert parameters.variant_selection == VariantSelection()
    assert parameters.adaptive_settings.mode is EvaluationMode.ADAPTIVE
    assert parameters.adaptive_settings.attempt_budget == 8


def test_unsupported_connection_protocol_is_rejected() -> None:
    """The disabled Other choice cannot accidentally fall through to OpenAI semantics."""
    with pytest.raises(ValidationError):
        ConnectionRequest(
            base_url="https://api.invalid",
            model_name="model",
            api_compatibility="other",  # type: ignore[arg-type]
        )


def test_connection_form_disables_unsupported_protocols() -> None:
    """The form exposes one supported protocol and a separate disabled alternative."""
    root = Path(__file__).resolve().parents[3]
    markup = (root / "frontend" / "model-configuration.html").read_text(encoding="utf-8")
    options = re.findall(r"<option\b([^>]*)>", markup)
    assert len(options) == 2
    assert 'value="openai_compatible"' in options[0]
    assert "disabled" in options[1]


def test_browser_report_escapes_evidence_and_separates_control_rates() -> None:
    """Unsafe evidence stays text while adaptive and control metrics remain distinct."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Frontend rendering checks require Node.js.")
    root = Path(__file__).resolve().parents[3]
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext({window: {}, URLSearchParams, location: {search: ''}});
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
const view = context.window.HARASS;
const progress = view.runProgress({total_cases: 10, completed_cases: 3, completed_attempts: 17});
assert(progress.includes('max="10" value="3"'));
assert(progress.includes('المحاولات المحفوظة: 17'));
assert(!progress.includes('17 من 10'));
assert(view.runProgress({total_cases: 0}).includes('لم يبدأ تنفيذ الحالات'));
assert(view.runProgress({total_cases: 0, status: 'running'}).includes('جارٍ تجهيز الحالات'));
const unsafe = '<img src=x onerror="alert(1)">&';
assert.equal(view.escape(unsafe), '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;&amp;');
context.location.search = '?return=https%3A%2F%2Fexample.invalid';
assert.equal(view.safeReturn(), 'dashboard.html');
context.location.search = '?return=evaluation-run.html%3Frun_id%3Dtest';
assert.equal(view.safeReturn(), 'evaluation-run.html?run_id=test');
const report = {
  run_type: 'agentic',
  outcomes: [{case_id: unsafe, axis: 'AT', variant_name: 'draft', attempt_number: 1,
    original_prompt: unsafe, transcript: {response: unsafe, category_rationale: unsafe}}],
  primary_metrics: {adversarial: {attack_success: {rate: 0.5, count: 1, total: 2}}},
  baseline_metrics: {adversarial: {attack_success: {rate: 0, count: 0, total: 2}}}
};
const output = view.reportBody(report);
assert(!output.includes('<img'));
assert(output.includes('&lt;img'));
assert(output.includes('50.0%'));
assert(output.includes('0.0%'));
assert(output.includes('الطلبات الأصلية للمقارنة'));
report.run_type = 'baseline';
assert(!view.reportBody(report).includes('الطلبات الأصلية للمقارنة'));
"""
    subprocess.run(
        [node, "-e", script, str(root / "frontend" / "assets" / "js" / "harass.js")],
        check=True,
        capture_output=True,
        text=True,
    )


def test_browser_prevents_native_submission_before_account_loads() -> None:
    """Pending initialization cannot send credential fields through a native form request."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Frontend initialization checks require Node.js.")
    root = Path(__file__).resolve().parents[3]
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let prevented = false;
let listener;
const form = {addEventListener: (name, callback) => {listener = callback;}};
const context = vm.createContext({
  window: {
    HARASS_API: {me: () => new Promise(() => {})},
    HARASS: {mountShell: () => {}}, addEventListener: () => {}
  },
  document: {
    body: {dataset: {page: 'model-configuration'}},
    querySelectorAll: (selector) => selector === 'form' ? [form] : []
  }
});
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
assert.equal(typeof listener, 'function');
listener({preventDefault: () => {prevented = true;}});
assert(prevented);
"""
    subprocess.run(
        [node, "-e", script, str(root / "frontend" / "assets" / "js" / "app.js")],
        check=True,
        capture_output=True,
        text=True,
    )


def test_shared_header_switches_between_public_and_account_navigation() -> None:
    """Mounting the shared layout replaces navigation without duplicating controls."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Frontend layout checks require Node.js.")
    root = Path(__file__).resolve().parents[3]
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const header = {}, footer = {};
const context = vm.createContext({
  window: {},
  document: {querySelector: (selector) => selector === '[data-shell-header]' ? header : footer}
});
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
const view = context.window.HARASS;
view.mountShell(false);
const accountHeader = header.innerHTML;
assert(accountHeader.includes('data-logout'));
assert(accountHeader.includes('evaluation-setup.html'));
view.mountShell(false);
assert.equal(header.innerHTML, accountHeader);
view.mountShell(true);
assert(!header.innerHTML.includes('data-logout'));
assert(header.innerHTML.includes('login.html'));
assert(header.innerHTML.includes('signup.html'));
assert(footer.innerHTML.includes('HARASS'));
"""
    subprocess.run(
        [node, "-e", script, str(root / "frontend" / "assets" / "js" / "harass.js")],
        check=True,
        capture_output=True,
        text=True,
    )
