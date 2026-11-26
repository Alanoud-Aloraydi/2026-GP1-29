/* Evaluation metrics, coverage and report composition. */
import { catalogue, html, percent, range, table } from '../core/ui.js';
import { evidence } from './report-evidence.js';

const categoryNames = [['FUL', 'أجاب عن الطلب'], ['PRF', 'أجاب جزئيًا'], ['REF', 'رفض الطلب'], ['UNC', 'رد غير واضح']];
const runModes = { baseline: 'اختبار أساسي', agentic: 'اختبار تكيّفي', static: 'تعداد ثابت' };
const dimensions = {
  subject_domain: 'المجال',
  risk_category: 'فئة الخطر',
  strategy: 'استراتيجية التجاوز',
  owasp_category: 'فئة OWASP لأصل الحالة'
};

const rate = (metric) => percent(metric?.rate, 1);
const fraction = (metric) => metric?.total ? `${metric.count} من ${metric.total}` : '';
const fill = (metric) => Math.round((metric?.rate ?? 0) * 100);
const meter = (metric, attack) =>
  html`<div class="track ${attack && 'track-attack'}"><span data-fill="${fill(metric)}"></span></div>`;
const rateCell = (metric) => html`${rate(metric)} <small>${fraction(metric)}</small>`;

function expectedRange (metric) {
  const bounds = metric?.clustered_95;
  return bounds && bounds[1] > bounds[0] && html`النطاق المتوقع (95%): ${range(bounds, 1)}`;
}

const axisMetric = (metrics, axis) => axis === 'AT'
  ? metrics?.adversarial?.attack_success
  : metrics?.over_refusal?.over_refusal;

const metricCard = ({ label, value, description, bar = '', tone = '' }) => html`
  <div class="metric-card ${tone}">
    <p class="metric-label">${label}</p>
    <p class="metric-value">${value}</p>
    ${bar}
    <p class="hint">${description}</p>
  </div>`;

const rateCard = (label, metric, description, tone) => {
  const bounds = expectedRange(metric);
  return metricCard({
    label,
    tone,
    value: rate(metric),
    bar: meter(metric, tone === 'attack'),
    description: html`${description}${bounds && html` · ${bounds}`}`
  });
};

function summaryCards (report) {
  const metrics = report.primary_metrics || {};
  const attack = axisMetric(metrics, 'AT');
  const refusal = axisMetric(metrics, 'OR');
  const harmful = metrics.adversarial?.refusal?.rate;
  const safe = metrics.over_refusal?.over_refusal?.rate;
  const unscored = metrics.unscored_outcomes || 0;
  const points = (value) => (value * 100).toFixed(1);
  return html`
    <section class="metric-grid">
      ${attack && rateCard('معدل نجاح الاختراق', attack,
        `نفّذ النموذج الطلب الضار في ${attack.count} من ${attack.total} محاولة. الأقل أفضل.`, 'attack')}
      ${refusal && rateCard('معدل الرفض المفرط', refusal,
        `رفض النموذج ${refusal.count} من ${refusal.total} طلبًا مشروعًا دون مبرر. الأقل أفضل.`, 'refusal')}
      ${harmful != null && safe != null && metricCard({
        label: 'قدرة التمييز بين الضار والمشروع',
        value: html`<span class="number">${points(harmful - safe)}</span> نقطة`,
        description: `رفض الطلبات الضارة ${points(harmful)}% مقابل رفض الطلبات المشروعة ${points(safe)}%. الأعلى أفضل.`
      })}
      ${metricCard({
        label: 'اكتمال التقييم',
        value: html`<span class="number">${unscored === 0 ? 'مكتمل' : unscored}</span>`,
        description: unscored === 0 ? 'كل الحالات حصلت على حكم.' : `${unscored} محاولة بلا حكم، مستبعدة من النسب.`
      })}
    </section>`;
}

const barRow = (label, metric, attack) => html`
  <div class="bar-row">
    <span class="bar-label">${label}</span>
    ${meter(metric, attack)}
    ${rate(metric)}<small>${fraction(metric)}</small>
  </div>`;

function dialectCard (metrics) {
  const groups = [
    ['معدل نجاح الاختراق', metrics.adversarial_breakdowns?.variety || {}, (group) => group.attack_success, true],
    ['معدل الرفض المفرط', metrics.over_refusal_breakdowns?.variety || {}, (group) => group.over_refusal, false]
  ].filter(([, byVariety]) => Object.keys(byVariety).length);
  if (!groups.length) return '';
  const varieties = Object.keys(Object.assign({}, ...groups.map(([, byVariety]) => byVariety)));
  return html`
    <section class="card">
      <h2>النتائج حسب اللهجة</h2>
      ${groups.map(([title, byVariety, pick, attack]) => html`
        <h3>${title}</h3>
        <div class="report-stack">${varieties.filter((code) => byVariety[code]).map((code) =>
          barRow(catalogue.dialects[code] || code, pick(byVariety[code]), attack))}</div>`)}
    </section>`;
}

function categoryDistribution (report) {
  const counts = report.response_categories || {};
  const bars = Object.entries(catalogue.axes).map(([axis, title]) => {
    const shares = counts[axis] || {};
    const total = Object.values(shares).reduce((sum, value) => sum + value, 0);
    return total > 0 && html`
      <div>
        <div class="bar-head"><strong>${title}</strong><span class="hint">${total} رد</span></div>
        <div class="stacked-bar">${categoryNames.filter(([code]) => shares[code]).map(([code]) =>
          html`<span class="cat-${code}" data-fill="${(shares[code] / total) * 100}">${code} ${shares[code]}</span>`
        )}</div>
      </div>`;
  }).filter(Boolean);
  if (!bars.length) return '';
  return html`
    <section class="card">
      <h2>توزيع فئات الرد</h2>
      <div class="report-stack">${bars}</div>
      <ul class="legend">${categoryNames.map(([code, name]) =>
        html`<li><span class="swatch cat-${code}"></span>${code} ${name}</li>`)}</ul>
    </section>`;
}

function breakdownTable (metrics, dimension, caption) {
  const attacks = metrics.adversarial_breakdowns?.[dimension] || {};
  const refusals = metrics.over_refusal_breakdowns?.[dimension] || {};
  const hasAttacks = Object.keys(attacks).length > 0;
  // OWASP risks apply to attacks only; the ones with no cases are shown too.
  const listed = dimension === 'owasp_category' && hasAttacks ? catalogue.owaspCategories : [];
  const keys = [...new Set([...listed, ...Object.keys(attacks), ...Object.keys(refusals)])];
  if (!keys.length) return '';
  const measured = (key) => key in attacks || key in refusals;
  const columns = [
    hasAttacks && { title: 'معدل نجاح الاختراق', metric: (key) => attacks[key]?.attack_success },
    Object.keys(refusals).length > 0 && { title: 'معدل الرفض المفرط', metric: (key) => refusals[key]?.over_refusal }
  ].filter(Boolean).map(({ title, metric }, index) => ({
    title,
    cell: (key) => measured(key) ? rateCell(metric(key)) : index ? '—' : html`<span class="hint">لا توجد حالات</span>`
  }));
  return table(caption, [{ title: 'التصنيف', cell: (key) => catalogue.labels[key] || key }, ...columns], keys);
}

function adaptiveSections (report) {
  if (report.run_type !== 'agentic') return '';
  const axes = Object.keys(catalogue.axes).filter((axis) => axisMetric(report.primary_metrics, axis));
  const adaptive = Object.entries(report.adaptive || {});
  return html`
    ${axes.length > 0 && html`<section class="card">${table('مقارنة المحاولات مع الطلبات الأصلية', [
      { title: 'المحور', cell: (axis) => catalogue.axes[axis] },
      { title: 'المحاولات التكيفية', cell: (axis) => rateCell(axisMetric(report.primary_metrics, axis)) },
      { title: 'الطلبات الأصلية للمقارنة', cell: (axis) => rateCell(axisMetric(report.baseline_metrics, axis)) }
    ], axes)}</section>`}
    ${adaptive.length > 0 && html`<section class="card">${table('اكتشاف الخلل على مستوى الحالة', [
      { title: 'المحور', cell: ([axis]) => catalogue.axes[axis] || axis },
      { title: 'حالات اكتُشف فيها خلل', cell: ([, summary]) => `${summary.defects_detected} من ${summary.cases}` },
      { title: 'المحاولات المسجلة', cell: ([, summary]) => summary.attempts_submitted },
      {
        title: 'حالات غير محسومة',
        cell: ([, summary]) => summary.defect_within_k?.[report.attempt_budget]?.undetermined ?? '—'
      }
    ], adaptive)}
    <p class="hint">الاكتشاف خلال ${report.attempt_budget} محاولات كحد أقصى لكل حالة.</p></section>`}`;
}

const coverageTable = (report) => html`
  <section class="card">
    ${table('اكتمال الأحكام', [
      { title: 'المحور', cell: ([axis]) => catalogue.axes[axis] },
      { title: 'المحاولات المسجلة', cell: ([, row]) => row.submitted },
      { title: 'أحكام غير مكتملة', cell: ([, row]) => row.unscored },
      { title: 'ردود غير مفهومة · UNC', cell: ([, row]) => row.unclear },
      { title: 'اشتباه عدم فهم · قواعد', cell: ([, row]) => row.suspected_unclear ?? 0 }
    ], Object.entries(report.coverage || {}))}
    <p class="hint">UNC يبقى ضمن مقام المعدل. الطلب غير المقيّم يُستبعد منه.
      اشتباه عدم الفهم علامة من قواعد بلا نموذج بجانب حكم المحكّم ولا تغيّره.</p>
  </section>`;

function classificationTables (metrics) {
  const tables = Object.entries(dimensions)
    .map(([dimension, label]) => breakdownTable(metrics, dimension, `النتائج حسب ${label}`))
    .filter(Boolean);
  return tables.length > 0 && html`
    <details class="case-evidence">
      <summary>عرض نتائج المجالات والمخاطر والاستراتيجيات وOWASP</summary>
      <div class="evidence-content report-stack">${tables}</div>
    </details>`;
}

export function reportBody (report) {
  const metrics = report.primary_metrics || {};
  const scope = report.selection?.varieties?.map((code) => catalogue.dialects[code] || code).join('، ');
  return html`
    <div class="report-stack">
      <div class="section-toolbar">
        <div class="chip-row">
          <span class="chip">${runModes[report.run_type] || '—'}</span>
          <span class="chip">${scope || 'النطاق موضح في الحالات'}</span>
        </div>
        <button class="btn btn-secondary" id="exportReport" type="button">تنزيل التقرير · JSON</button>
      </div>
      <div class="report-notice">
        <strong>قراءة النتائج</strong>
        <p>المعدل الأقل أفضل في المحورين. الأحكام آلية إلى حين التحقق بالمراجعة البشرية.
          ${report.metrics?.unscored_outcomes > 0 && html`
            <span class="coverage-warning">الأحكام غير المكتملة تحدّ من التفسير؛ راجع اكتمال الأحكام.</span>`}</p>
      </div>
      ${summaryCards(report)}
      ${adaptiveSections(report)}
      ${dialectCard(metrics)}
      ${categoryDistribution(report)}
      ${coverageTable(report)}
      ${classificationTables(metrics)}
      ${evidence(report)}
    </div>`;
}
