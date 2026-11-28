/* Evaluation page: live progress while a run works, then its report. */
import { api } from '../core/api-client.js';
import { start } from '../core/bootstrap.js';
import { runBusy } from '../core/forms.js';
import { clearError, empty, html, link, PAGE_SIZE, showError } from '../core/ui.js';
import { agenticReportBody, noMeasurementAxes, noVerdictSummary } from '../views/agentic-report.js';
import { reportBody } from '../views/report.js';
import { evidencePage, promptEvidencePage } from '../views/report-evidence.js';
import { baselineNotice, runHeading, runProgress, updateRunProgress } from '../views/run.js';

// Waiting runs change slowly, so they are checked less often.
const POLL_MS = { pending: 15000, running: 10000 };
const ACTIVE = ['pending', 'running'];
// A baseline run that sent every case and judged none stores this code; a sent
// case is never sent again, so resuming it cannot produce a verdict.
const NOTHING_TO_RESUME_CODE = 'baseline_no_verdict';
const NEW_RUN = ['evaluation-setup.html', 'تقييم جديد'];

const canResume = (run) => run.resumable && !run.error?.startsWith(NOTHING_TO_RESUME_CODE);

function failureNotice (run) {
  if (canResume(run)) {
    return html`<p>توقف التقييم بعد أخطاء تقنية متكررة. تحقق من الاتصال وإعدادات المحكّم ثم استأنف.</p>
      <button type="button" class="btn" id="resumeRun">استئناف التقييم</button>`;
  }
  if (run.resumable) {
    return empty('لا توجد محاولات متبقية للاستئناف',
      'أُرسلت كل الحالات وتعذّر الحكم عليها بسبب أخطاء تقنية، ولا يعيد الاستئناف إرسال حالة ' +
      'سبق إرسالها حتى لا يتلقاها النموذج مرتين. تحقّق من الاتصال بالنموذج والمحكّم ثم ابدأ تقييمًا جديدًا.',
      ...NEW_RUN);
  }
  const noVerdict = noVerdictSummary(run.error);
  if (noVerdict !== null) {
    return empty('لم يصل أي طلب إلى المحكّم', 'الأسباب: ' + (noVerdict || 'غير مسجّلة') + '.', ...NEW_RUN);
  }
  const unmeasured = noMeasurementAxes(run.error);
  if (unmeasured !== null) {
    return empty('لا توجد أحكام في جولة القياس',
      `لم تُحكَم أي محاولة في جولة القياس على محور ${unmeasured}، فلا يمكن مقارنة النتائج ` +
      'بالتقييم الأساسي. ابدأ تقييمًا وكيليًا جديدًا.', ...NEW_RUN);
  }
  return empty('تعذّر إكمال التقييم', 'راجع اتصال النموذج ثم ابدأ تقييمًا جديدًا.', ...NEW_RUN);
}

function downloadReport (runId) {
  const anchor = document.createElement('a');
  anchor.href = api.reportExportUrl(runId);
  anchor.download = `harass-${runId}.json`;
  anchor.click();
}

async function reportPage () {
  const runId = new URLSearchParams(location.search).get('run_id');
  if (!runId) throw new Error('لم يُحدد التقييم المطلوب.');
  const container = document.getElementById('report');
  let active = true;
  let timer;
  let evidenceRequest = 0;
  let drawEvidence = evidencePage;
  let fetchEvidence = api.getOutcomes;

  // Only the newest evidence request may draw, so fast paging cannot show an
  // older page after a newer one.
  async function loadEvidence (offset) {
    const request = ++evidenceRequest;
    try {
      const page = await fetchEvidence(runId, offset);
      if (!active || request !== evidenceRequest) return;
      document.getElementById('attemptEvidence').innerHTML = drawEvidence(page);
      document.getElementById('evidencePrevious')
        ?.addEventListener('click', () => loadEvidence(Math.max(0, offset - PAGE_SIZE)));
      document.getElementById('evidenceNext')?.addEventListener('click', () => loadEvidence(offset + PAGE_SIZE));
    } catch (error) {
      showError(error.message);
    }
  }

  function bindRunAction (id, action) {
    const button = document.getElementById(id);
    button.addEventListener('click', () => runBusy(button, async () => {
      await action(runId);
      await load();
    }));
  }

  async function drawRun (run) {
    container.dataset.status = run.status;
    container.dataset.awaits = run.awaits_run_id || '';
    const title = run.status === 'completed' ? 'تقرير التقييم' : 'تفاصيل التقييم';
    document.getElementById('evaluationTitle').textContent = title;
    document.title = title + ' — HARASS';
    container.innerHTML = runHeading(run);
    if (run.status === 'completed') {
      const report = await api.getReport(runId);
      if (!active) return;
      const agentic = report.kind === 'agentic';
      drawEvidence = agentic ? promptEvidencePage : evidencePage;
      fetchEvidence = agentic ? api.getPrompts : api.getOutcomes;
      container.insertAdjacentHTML('beforeend', agentic ? agenticReportBody(report) : reportBody(report));
      document.getElementById('exportReport').addEventListener('click', () => downloadReport(runId));
      if (report.evidence_paged) await loadEvidence(0);
    } else {
      container.insertAdjacentHTML('beforeend', baselineNotice(run) + runProgress(run));
    }
    if (run.status === 'failed' && !run.awaits_run_id) {
      container.insertAdjacentHTML('beforeend', failureNotice(run));
      if (canResume(run)) bindRunAction('resumeRun', api.resumeRun);
    }
    if (ACTIVE.includes(run.status) || run.resumable) {
      container.insertAdjacentHTML('beforeend',
        html`<button type="button" class="btn btn-secondary" id="cancelRun">إلغاء التقييم</button>`);
      bindRunAction('cancelRun', api.cancelRun);
    }
    container.insertAdjacentHTML('beforeend', link('history.html', 'العودة إلى سجل التقييمات'));
  }

  async function load () {
    clearError();
    clearTimeout(timer);
    try {
      const run = await api.getRun(runId);
      if (!active) return;
      const shownProgress = container.querySelector('#evaluationProgress');
      const sameWait = container.dataset.awaits === (run.awaits_run_id || '');
      if (ACTIVE.includes(run.status) && container.dataset.status === run.status && sameWait && shownProgress) {
        updateRunProgress(container, run);
      } else {
        // Redrawing must not close what the reader opened or move their focus.
        const opened = [...container.querySelectorAll('details')].map((item) => item.open);
        const focused = container.contains(document.activeElement) ? document.activeElement.id : null;
        await drawRun(run);
        container.querySelectorAll('details').forEach((item, index) => { item.open = opened[index] || false; });
        if (focused) document.getElementById(focused)?.focus({ preventScroll: true });
      }
      if (ACTIVE.includes(run.status)) timer = setTimeout(load, POLL_MS[run.status]);
    } catch (error) {
      if (!active) return;
      showError(error.message);
      container.innerHTML = html`<button type="button" class="btn" id="retryReport">إعادة المحاولة</button>`;
      document.getElementById('retryReport').addEventListener('click', load);
    }
  }

  window.addEventListener('pagehide', () => {
    active = false;
    clearTimeout(timer);
  });
  await load();
}

start(reportPage);
