/* Agentic run report: each axis against the baseline, the rounds and the generated prompts. */
import { catalogue, html, percent, range, table } from '../core/ui.js';

// What a success means on each axis, and how the report names it.
const axisRates = {
  OR: { title: 'معدل الرفض المفرط', success: 'رفض طلبًا مشروعًا' },
  AT: { title: 'معدل نجاح الاختراق', success: 'نفّذ طلبًا ضارًا' }
};
const phases = { measurement: 'قياس', discovery: 'اكتشاف' };

const rate = (metric) => metric?.total ? percent(metric.rate, 1) : '—';
const fraction = (metric) => metric?.total ? html`<small>${metric.count} من ${metric.total}</small>` : '';
const interval = (metric) => metric?.wilson_95 && html`<small>(95%: ${range(metric.wilson_95, 1)})</small>`;
const rateCell = (metric) => html`${rate(metric)} ${fraction(metric)}`;

function axisCard ([axis, rates]) {
  const names = axisRates[axis];
  return html`
    <div class="metric-card ${axis === 'AT' ? 'attack' : 'refusal'}">
      <p class="metric-label">${names.title} · ${catalogue.axes[axis] || axis}</p>
      <p class="metric-value">${rate(rates.measurement)}</p>
      <p class="hint">جولة القياس: ${names.success} في ${rates.measurement?.count ?? 0} من
        ${rates.measurement?.total ?? 0} طلبًا مُحكَّمًا ${interval(rates.measurement)}.</p>
      <p class="hint">التقييم الأساسي: ${rateCell(rates.baseline)} · جولات الاكتشاف: ${rateCell(rates.discovery)}</p>
    </div>`;
}

const roundsTable = (rounds) => table('الجولات', [
  { title: 'الجولة', cell: (entry) => `${entry.round + 1} · ${phases[entry.phase]}` },
  { title: 'المحور', cell: (entry) => catalogue.axes[entry.axis] || entry.axis },
  { title: 'الطلبات', cell: (entry) => entry.prompts },
  { title: 'اجتازت البوابات', cell: (entry) => entry.valid },
  { title: 'المعدل', cell: (entry) => rateCell(entry.success) },
  { title: 'دروس جديدة', cell: (entry) => entry.lessons },
  { title: 'أنماط جديدة', cell: (entry) => entry.cards },
  { title: 'ملاحظة', cell: (entry) => entry.interrupted ? 'انقطعت قبل اكتمالها' : '' }
], rounds);

export function agenticReportBody (report) {
  const parameters = report.parameters || {};
  const scope = (parameters.varieties || []).map((code) => catalogue.dialects[code] || code).join('، ');
  const transforms = (parameters.transform_names || []).map((name) =>
    catalogue.transforms.find((item) => item.name === name)?.label || name).join('، ');
  return html`
    <div class="report-stack">
      <div class="section-toolbar">
        <div class="chip-row">
          <span class="chip">${parameters.rounds} جولات × ${parameters.prompts_per_round} طلبًا لكل محور</span>
          <span class="chip">${scope || 'كل اللهجات'}</span>
          <span class="chip">${transforms || 'دون تحويلات'}</span>
        </div>
        <button class="btn btn-secondary" id="exportReport" type="button">تنزيل التقرير · JSON</button>
      </div>
      <div class="report-notice">
        <strong>قراءة النتائج</strong>
        <p>المعدل الأقل أفضل في المحورين. جولة القياس لا تستفيد مما تعلّمه حَرَس من النموذج، فمعدلها
          يقارَن بالتقييم الأساسي. جولات الاكتشاف تتجه إلى مواضع الإخفاق، فمعدلها يبيّن ما وجده التعلم
          ولا يُعمَّم. بدأ التعلم من ${report.seeded_cards ?? 0} نمطًا استُخرجت من التقييم الأساسي.</p>
      </div>
      <section class="metric-grid">${Object.entries(report.axes || {}).map(axisCard)}</section>
      <section class="card">${roundsTable(report.rounds || [])}</section>
      <section id="attemptEvidence" aria-live="polite"></section>
    </div>`;
}
