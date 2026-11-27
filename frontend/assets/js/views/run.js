/* Evaluation lifecycle, progress and the list of runs. */
import { date, html, link, status, table } from '../core/ui.js';

const runActions = { completed: 'فتح التقرير', running: 'متابعة التقدم' };
const ELAPSED_LABEL = 'الوقت منذ بدء التنفيذ';
const WORKER_OFFLINE = 'العامل غير متصل. سيستأنف التنفيذ عند تشغيله.';
const events = {
  created: 'أُنشئ',
  started: 'بدأ',
  suspended: 'توقف',
  resumed: 'استؤنف',
  completed: 'اكتمل',
  failed: 'فشل',
  cancelled: 'أُلغي'
};

// Hours and minutes from the start until the end, or until now.
function elapsed (run) {
  const end = run.finished_at ? new Date(run.finished_at) : new Date();
  const minutes = Math.max(0, Math.floor((end - new Date(run.started_at)) / 60000));
  return `${Math.floor(minutes / 60)} س ${minutes % 60} د`;
}

// A baseline run counts dataset cases; an agentic run counts rounds per axis.
const units = {
  baseline: { done: 'الحالات المكتملة', preparing: 'جارٍ تجهيز الحالات', waiting: 'لم يبدأ تنفيذ الحالات' },
  agentic: {
    done: 'الجولات المكتملة على المحاور المختارة',
    preparing: 'جارٍ استخراج الأنماط من التقييم الأساسي',
    waiting: 'لم تبدأ الجولات'
  }
};

function progress (run) {
  const total = Math.max(0, Number(run.total_cases) || 0);
  const completed = Math.min(total, Math.max(0, Number(run.completed_cases) || 0));
  const words = units[run.kind] || units.baseline;
  const label = run.awaits_run_id
    ? 'بانتظار اكتمال التقييم الأساسي'
    : total
      ? `${words.done}: ${completed} من ${total}`
      : run.status === 'running' ? words.preparing : words.waiting;
  return { total, completed, label };
}

// Why an agentic run waits for, or stopped with, the baseline run it starts from.
export function baselineNotice (run) {
  if (!run.awaits_run_id || !['pending', 'failed'].includes(run.status)) return '';
  const baseline = 'evaluation-run.html?run_id=' + encodeURIComponent(run.awaits_run_id);
  return run.status === 'pending'
    ? html`<div class="report-notice">
        <p>يبدأ هذا الاختبار الوكيلي تلقائيًا بعد اكتمال التقييم الأساسي لهذا الاتصال، لأنه يبني أنماطه الأولى من نتائج التقييم الأساسي ويقارن كل جولة بمعدّله.</p>
        ${link(baseline, 'متابعة التقييم الأساسي')}
      </div>`
    : html`<div class="report-notice">
        <p>لم يبدأ الاختبار الوكيلي لأن التقييم الأساسي الذي كان ينتظره أُلغي أو فشل. ابدأ اختبارًا وكيليًا جديدًا ليُشغَّل تقييم أساسي آخر قبله.</p>
        ${link(baseline, 'عرض التقييم الأساسي')}
        ${link('evaluation-setup.html', 'تقييم جديد', true)}
      </div>`;
}

export const kindLabel = (run) => run.kind === 'agentic' ? 'اختبار وكيلي' : 'اختبار أساسي';

const workerOffline = (run) => run.worker_available === false && ['pending', 'running'].includes(run.status);

const runColumns = [
  { title: 'النموذج', cell: (run) => run.target_model },
  { title: 'الطريقة', cell: (run) => html`<span class="chip">${kindLabel(run)}</span>` },
  { title: 'تاريخ الإنشاء', cell: (run) => date(run.created_at) },
  { title: 'الحالة', cell: (run) => status(run.status) },
  {
    title: 'التقرير',
    cell: (run) => link('evaluation-run.html?run_id=' + encodeURIComponent(run.run_id),
      runActions[run.status] || 'عرض التفاصيل')
  }
];

export const runTable = (runs, caption = 'تقييمات حسابك') =>
  html`<section class="card">${table(caption, runColumns, runs)}</section>`;

function runTimes (run) {
  const times = [
    ['أُنشئ', run.created_at && date(run.created_at)],
    ['بدأ التنفيذ', run.started_at && date(run.started_at)],
    ['انتهى', run.finished_at && date(run.finished_at)],
    [ELAPSED_LABEL, run.started_at && elapsed(run)]
  ].filter(([, value]) => value);
  return html`
    <dl class="run-times">${times.map(([label, value]) => html`<div><dt>${label}</dt><dd>${value}</dd></div>`)}</dl>
    ${run.lifecycle_events?.length && html`
      <details>
        <summary>سجل التشغيل</summary>
        <ol>${run.lifecycle_events.map((item) =>
          html`<li>${events[item.event] || item.event} · ${date(item.at)}</li>`)}</ol>
      </details>`}`;
}

export const runHeading = (run) => html`
  <div class="report-heading card">
    <div><h2><bdi>${run.target_model}</bdi> <span class="chip">${kindLabel(run)}</span></h2>${runTimes(run)}</div>
    ${status(run.status)}
  </div>`;

export function runProgress (run) {
  const { total, completed, label } = progress(run);
  return html`
    <div class="run-progress-row card">
      <label for="evaluationProgress">${label}</label>
      <progress id="evaluationProgress" max="${total || 1}" value="${completed}">
        ${total ? Math.floor((completed / total) * 100) : 0}%
      </progress>
      ${workerOffline(run) && html`<p class="coverage-warning">${WORKER_OFFLINE}</p>`}
    </div>`;
}

// Update a shown progress row in place, so polling keeps focus and scroll.
export function updateRunProgress (container, run) {
  const { total, completed, label } = progress(run);
  const bar = container.querySelector('#evaluationProgress');
  bar.max = total || 1;
  bar.value = completed;
  container.querySelector('label[for="evaluationProgress"]').textContent = label;
  const warning = container.querySelector('.run-progress-row .coverage-warning');
  if (workerOffline(run) && !warning) {
    bar.parentElement.insertAdjacentHTML('beforeend', html`<p class="coverage-warning">${WORKER_OFFLINE}</p>`);
  } else if (!workerOffline(run)) {
    warning?.remove();
  }
  const terms = [...container.querySelectorAll('.run-times dt')];
  const elapsedTerm = terms.find((term) => term.textContent === ELAPSED_LABEL);
  if (elapsedTerm && run.started_at) elapsedTerm.nextElementSibling.textContent = elapsed(run);
}
