/* Unsafe evidence stays text and the report shows the run's metrics. */
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

// Enough of the browser for the modules to load outside one.
globalThis.location = { search: '' };
globalThis.MutationObserver = class { observe () {} };
globalThis.document = { documentElement: {}, querySelectorAll: () => [] };

const load = (file) => import(pathToFileURL(path.join(process.argv[2], file)).href);

(async () => {
  const ui = await load('core/ui.js');
  const { baselineNotice, runProgress } = await load('views/run.js');
  const { reportBody } = await load('views/report.js');
  const { agenticReportBody } = await load('views/agentic-report.js');
  const { promptEvidencePage } = await load('views/report-evidence.js');
  ui.configureCatalogue({
    axes: { AT: 'AT', OR: 'OR' },
    labels: {},
    dialects: {},
    owasp_categories: [],
    agentic: { transforms: [{ name: 'base64', label: 'ترميز Base64', attack_only: false }] }
  });

  const progress = String(runProgress({ total_cases: 10, completed_cases: 3 }));
  assert(progress.includes('max="10" value="3"'));
  assert(progress.includes('الحالات المكتملة: 3 من 10'));
  assert(String(runProgress({ total_cases: 0 })).includes('لم يبدأ تنفيذ الحالات'));
  assert(String(runProgress({ total_cases: 0, status: 'running' })).includes('جارٍ تجهيز الحالات'));

  const unsafe = '<img src=x onerror="alert(1)">&';
  assert.equal(ui.escape(unsafe), '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;&amp;');
  assert.equal(String(ui.html`<p>${unsafe}</p>`), '<p>' + ui.escape(unsafe) + '</p>');
  globalThis.location.search = '?return=https%3A%2F%2Fexample.invalid';
  assert.equal(ui.safeReturn(), 'dashboard.html');
  globalThis.location.search = '?return=evaluation-run.html%3Frun_id%3Dtest';
  assert.equal(ui.safeReturn(), 'evaluation-run.html?run_id=test');

  const report = {
    outcomes: [{
      case_id: unsafe,
      axis: 'AT',
      original_prompt: unsafe,
      transcript: { response: unsafe, category_rationale: unsafe }
    }],
    metrics: { adversarial: { attack_success: { rate: 0.5, count: 1, total: 2 } } }
  };
  const output = String(reportBody(report));
  assert(!output.includes('<img'));
  assert(output.includes('&lt;img'));
  assert(output.includes('50.0%'));

  const agenticProgress = String(runProgress({ kind: 'agentic', total_cases: 6, completed_cases: 2 }));
  assert(agenticProgress.includes('الجولات المكتملة على المحاور المختارة: 2 من 6'));
  const waiting = { kind: 'agentic', status: 'pending', awaits_run_id: 'base-1' };
  assert(String(runProgress(waiting)).includes('بانتظار اكتمال التقييم الأساسي'));
  assert(String(baselineNotice(waiting)).includes('evaluation-run.html?run_id=base-1'));
  assert(String(baselineNotice({ ...waiting, status: 'failed' })).includes('أُلغي أو فشل'));
  assert.equal(String(baselineNotice({ ...waiting, awaits_run_id: null })), '');

  const share = (count, total) => ({ count, total, rate: count / total, wilson_95: [0.1, 0.9] });
  const agentic = String(agenticReportBody({
    kind: 'agentic',
    parameters: { rounds: 2, prompts_per_round: 5, transform_names: ['base64'], varieties: [] },
    seeded_cards: 4,
    axes: { OR: { baseline: share(1, 10), measurement: share(1, 4), discovery: share(3, 4) } },
    rounds: [{
      axis: 'OR', round: 0, phase: 'measurement', prompts: 5, valid: 4, success: share(1, 4),
      lessons: 2, cards: 1, interrupted: false
    }]
  }));
  assert(agentic.includes('25.0%'));
  assert(agentic.includes('ترميز Base64'));
  assert(agentic.includes('attemptEvidence'));

  const prompts = String(promptEvidencePage({
    offset: 0,
    total: 1,
    items: [{
      case_id: unsafe,
      axis: 'AT',
      round: 0,
      written_text: unsafe,
      localized_text: unsafe,
      sent_text: unsafe,
      objective: unsafe,
      transform_names: ['base64'],
      reviewer_passed: true,
      intent_safe: false,
      device: 'persona',
      lesson_ids: ['L-1'],
      attempts: 1,
      outcome: { response_category: 'FUL', attack_succeeded: true, response_text: unsafe }
    }]
  }));
  assert(!prompts.includes('<img'));
  assert(prompts.includes('نجح الاختراق'));
  assert(!prompts.includes('لم يُرسل'));
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
