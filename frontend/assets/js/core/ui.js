/* Escaped markup, shared formats and page feedback used by every view. */
const entities = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export const escape = (value) =>
  String(value ?? '').replace(/[&<>"']/g, (character) => entities[character]);

// Markup built by html`` stays as markup when nested; any other value is
// escaped, so a view cannot insert API text unescaped by forgetting a call.
class Markup {
  constructor (text) { this.text = text; }
  toString () { return this.text; }
}

function render (value) {
  if (value instanceof Markup) return value.text;
  if (Array.isArray(value)) return value.map(render).join('');
  return value === null || value === undefined || value === false ? '' : escape(value);
}

export const html = (strings, ...values) =>
  new Markup(strings.reduce((markup, text, index) => markup + render(values[index - 1]) + text));

// Labels for taxonomy codes, filled once from the evaluation options.
export const catalogue = { axes: {}, dialects: {}, labels: {}, owaspCategories: [], transforms: [] };

export function configureCatalogue (options) {
  Object.assign(catalogue.axes, options.axes);
  Object.assign(catalogue.dialects, options.dialects);
  Object.assign(catalogue.labels, options.labels);
  catalogue.owaspCategories.push(...options.owasp_categories);
  catalogue.transforms.push(...(options.agentic?.transforms || []));
}

const isNumber = (value) => typeof value === 'number' && Number.isFinite(value);

export const number = (value, digits = 2) =>
  isNumber(value) ? html`<span class="number">${value.toFixed(digits)}</span>` : '—';

export const count = (value) => html`<span class="number">${value ?? '—'}</span>`;

export const percent = (rate, digits = 0) =>
  isNumber(rate) ? html`<span class="number">${(rate * 100).toFixed(digits)}%</span>` : '—';

export const share = (part) => part?.total
  ? html`${percent(part.count / part.total)} <small class="number">(${part.count} / ${part.total})</small>`
  : '—';

export const range = ([low, high], digits = 0) =>
  html`<span class="number">${(low * 100).toFixed(digits)}–${(high * 100).toFixed(digits)}%</span>`;

export const bdi = (value) =>
  value === null || value === undefined || value === '' ? '—' : html`<bdi>${value}</bdi>`;

export const date = (value) => value
  ? new Date(value).toLocaleString('ar-SA-u-ca-gregory', { dateStyle: 'medium', timeStyle: 'short' })
  : '—';

const statuses = {
  pending: 'قيد الانتظار',
  running: 'جارٍ التقييم',
  completed: 'اكتمل التقييم',
  failed: 'تعذّر إكمال التقييم',
  cancelled: 'أُلغي التقييم',
  connected: 'اتصال ناجح',
  not_tested: 'لم يُختبر',
  testing: 'جارٍ الاختبار'
};

export const status = (value, context = 'run') => html`
  <span class="status-label status-${value}">${
    context === 'connection' && value === 'failed' ? 'تعذّر الاتصال' : statuses[value] || value
  }</span>`;

export const link = (path, label, primary = false) =>
  html`<a class="btn btn-sm${primary ? ' btn-primary' : ''}" href="${path}">${label}</a>`;

export const empty = (title, description, path, label) => html`
  <div class="empty-state">
    <h2>${title}</h2>
    <p>${description}</p>
    ${path && link(path, label)}
  </div>`;

/**
 * Draw a table from column descriptions: each column has a title, a cell
 * function and an optional help text shown as a hover definition. The first
 * column heads its row.
 */
export const table = (caption, columns, items) => html`
  <div class="table-region" role="region" tabindex="0" aria-label="${caption}">
    <table>
      <caption>${caption}</caption>
      <thead><tr>${columns.map(heading)}</tr></thead>
      <tbody>${items.map((item) => html`<tr>${columns.map((column, index) => cell(column, item, index))}</tr>`)}</tbody>
    </table>
  </div>`;

const heading = ({ title, help }) => html`<th scope="col">${
  help ? html`<span class="has-definition" title="${help}">${title}</span>` : title
}</th>`;

const cell = (column, item, index) => index
  ? html`<td>${column.cell(item)}</td>`
  : html`<th scope="row"><bdi>${column.cell(item)}</bdi></th>`;

// A two-column table of [label, value] pairs.
export const facts = (caption, pairs, [labelTitle, valueTitle] = ['البند', 'القيمة']) => table(
  caption,
  [{ title: labelTitle, cell: ([label]) => label }, { title: valueTitle, cell: ([, value]) => value }],
  pairs
);

// Headline figures shown side by side, each a value over its label.
export const figures = (pairs) =>
  pairs.map(([value, label]) => html`<div><strong>${value}</strong><span>${label}</span></div>`);

export const reportButton = (reportId) =>
  html`<button class="btn btn-sm btn-secondary" type="button" data-report="${reportId}">عرض</button>`;

export const PAGE_SIZE = 50;

export function pageControls (offset, total, prefix) {
  if (total <= PAGE_SIZE) return '';
  return html`
    <div class="section-toolbar">
      <button type="button" class="btn btn-secondary" id="${prefix}Previous" ${!offset && 'disabled'}>السابق</button>
      <span>${offset + 1}–${Math.min(offset + PAGE_SIZE, total)} من ${total}</span>
      <button type="button" class="btn btn-secondary" id="${prefix}Next" ${offset + PAGE_SIZE >= total && 'disabled'}>
        التالي
      </button>
    </div>`;
}

export function busy (button, loading) {
  button.disabled = loading;
  button.classList.toggle('btn-loading', loading);
}

export function showError (message) {
  const box = document.getElementById('pageError');
  if (!box) return;
  box.textContent = message;
  box.hidden = false;
  box.focus();
}

export function clearError () {
  const box = document.getElementById('pageError');
  if (!box) return;
  box.hidden = true;
  box.textContent = '';
}

const returnPages = new Set([
  'account.html', 'dashboard.html', 'connections.html', 'model-configuration.html',
  'evaluation-setup.html', 'evaluation-run.html', 'history.html', 'judges.html'
]);

// Only an application page may follow login, never another site or a fragment.
export function safeReturn () {
  const destination = new URLSearchParams(location.search).get('return');
  const allowed = destination && !destination.includes('#') && returnPages.has(destination.split('?')[0]);
  return allowed ? destination : 'dashboard.html';
}

// The page policy forbids inline style attributes, so bar widths travel as
// data-fill and are applied through the style object.
function fillBars () {
  document.querySelectorAll('[data-fill]').forEach((bar) => { bar.style.width = bar.dataset.fill + '%'; });
}
new MutationObserver(fillBars).observe(document.documentElement, { childList: true, subtree: true });
fillBars();
