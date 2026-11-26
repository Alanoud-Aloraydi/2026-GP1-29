/* Unsafe evidence stays text while adaptive and control metrics remain distinct. */
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
  const { runProgress } = await load('views/run.js');
  const { reportBody } = await load('views/report.js');
  ui.configureCatalogue({ axes: { AT: 'AT', OR: 'OR' }, labels: {}, dialects: {}, owasp_categories: [] });

  const progress = String(runProgress({ total_cases: 10, completed_cases: 3, completed_attempts: 17 }));
  assert(progress.includes('max="10" value="3"'));
  assert(progress.includes('المحاولات المحفوظة: 17'));
  assert(!progress.includes('17 من 10'));
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
    run_type: 'agentic',
    outcomes: [{
      case_id: unsafe,
      axis: 'AT',
      variant_name: 'draft',
      attempt_number: 1,
      original_prompt: unsafe,
      transcript: { response: unsafe, category_rationale: unsafe }
    }],
    primary_metrics: { adversarial: { attack_success: { rate: 0.5, count: 1, total: 2 } } },
    baseline_metrics: { adversarial: { attack_success: { rate: 0, count: 0, total: 2 } } }
  };
  const output = String(reportBody(report));
  assert(!output.includes('<img'));
  assert(output.includes('&lt;img'));
  assert(output.includes('50.0%'));
  assert(output.includes('0.0%'));
  assert(output.includes('الطلبات الأصلية للمقارنة'));
  report.run_type = 'baseline';
  assert(!String(reportBody(report)).includes('الطلبات الأصلية للمقارنة'));
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
