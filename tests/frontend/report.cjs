/* Unsafe evidence stays text while adaptive and control metrics remain distinct. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext({window: {}, URLSearchParams, location: {search: ''}});
for (const file of ['core/ui.js', 'views/run.js', 'views/report-evidence.js', 'views/report.js']) {
  vm.runInContext(fs.readFileSync(require('node:path').join(process.argv[2], file), 'utf8'), context);
}
const view = context.window.HARASS;
view.configureLabels({axes: {AT: "AT", OR: "OR"}, labels: {}, dialects: {}});
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
