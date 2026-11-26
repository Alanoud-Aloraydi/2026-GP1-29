/* Evaluation page: live progress while a run works, then its report. */
import { api } from '../core/api-client.js';
import { start } from '../core/bootstrap.js';
import { runBusy } from '../core/forms.js';
import { clearError, empty, html, link, PAGE_SIZE, showError } from '../core/ui.js';
import { reportBody } from '../views/report.js';
import { evidencePage } from '../views/report-evidence.js';
import { runHeading, runProgress, updateRunProgress } from '../views/run.js';

// Waiting runs change slowly, so they are checked less often.
const POLL_MS = { pending: 15000, running: 10000 };
const ACTIVE = ['pending', 'running'];

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

  // Only the newest evidence request may draw, so fast paging cannot show an
  // older page after a newer one.
  async function loadEvidence (offset) {
    const request = ++evidenceRequest;
    try {
      const page = await api.getOutcomes(runId, offset);
      if (!active || request !== evidenceRequest) return;
      document.getElementById('attemptEvidence').innerHTML = evidencePage(page);
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
    const title = run.status === 'completed' ? 'تقرير التقييم' : 'تفاصيل التقييم';
    document.getElementById('evaluationTitle').textContent = title;
    document.title = title + ' — HARASS';
    container.innerHTML = runHeading(run);
    if (run.status === 'completed') {
      const report = await api.getReport(runId);
      if (!active) return;
      container.insertAdjacentHTML('beforeend', reportBody(report));
      document.getElementById('exportReport').addEventListener('click', () => downloadReport(runId));
      if (report.evidence_paged) await loadEvidence(0);
    } else {
      container.insertAdjacentHTML('beforeend', runProgress(run));
    }
    if (run.status === 'failed') {
      container.insertAdjacentHTML('beforeend', run.resumable
        ? html`<p>توقف التقييم بعد أخطاء تقنية متكررة. تحقق من الاتصال وإعدادات المحكّم ثم استأنف.</p>
            <button type="button" class="btn" id="resumeRun">استئناف التقييم</button>`
        : empty(
          'تعذّر إكمال التقييم', 'راجع اتصال النموذج ثم ابدأ تقييمًا جديدًا.', 'evaluation-setup.html', 'تقييم جديد'
        ));
      if (run.resumable) bindRunAction('resumeRun', api.resumeRun);
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
      if (ACTIVE.includes(run.status) && container.dataset.status === run.status && shownProgress) {
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
