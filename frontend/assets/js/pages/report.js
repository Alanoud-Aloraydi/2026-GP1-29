/* Report page interactions and error recovery. */
(() => {
  'use strict';
  const api = window.HARASS_API;
  const view = window.HARASS;

  function downloadReport (identifier) {
    const anchor = document.createElement('a');
    anchor.href = api.reportExportUrl(identifier);
    anchor.download = 'harass-' + identifier + '.json';
    anchor.click();
  }

  async function reportPage () {
    const identifier = new URLSearchParams(location.search).get('run_id');
    const container = document.getElementById('report');
    if (!identifier) throw new Error('لم يُحدد التقييم المطلوب.');
    let active = true;
    let timer;
    let evidenceRevision = 0;
    async function loadEvidence (offset) {
      const revision = ++evidenceRevision;
      try {
        const result = await api.getOutcomes(identifier, offset);
        if (!active || revision !== evidenceRevision) return;
        document.getElementById('attemptEvidence').innerHTML =
          view.evidencePage(result);
        document
          .getElementById('evidencePrevious')
          ?.addEventListener('click', () =>
            loadEvidence(Math.max(0, offset - 50))
          );
        document
          .getElementById('evidenceNext')
          ?.addEventListener('click', () => loadEvidence(offset + 50));
      } catch (error) {
        view.showError(error.message);
      }
    }
    function bindRunAction (buttonId, action) {
      document.getElementById(buttonId).addEventListener('click', async () => {
        const button = document.getElementById(buttonId);
        view.busy(button, true);
        try {
          await action(identifier);
          await load();
        } catch (error) {
          view.showError(error.message);
          view.busy(button, false);
        }
      });
    }
    async function load () {
      clearTimeout(timer);
      view.clearError();
      try {
        const run = await api.getRun(identifier);
        if (!active) return;
        if (
          ['pending', 'running'].includes(run.status) &&
          container.dataset.status === run.status &&
          container.querySelector('#evaluationProgress')
        ) {
          view.updateRunProgress(container, run);
          timer = setTimeout(load, run.status === 'pending' ? 15000 : 10000);
          return;
        }
        container.dataset.status = run.status;
        const title =
          run.status === 'completed' ? 'تقرير التقييم' : 'تفاصيل التقييم';
        document.getElementById('evaluationTitle').textContent = title;
        document.title = title + ' — HARASS';
        const opened = [...container.querySelectorAll('details')].map(
          (item) => item.open
        );
        const focused = container.contains(document.activeElement)
          ? document.activeElement.id
          : null;
        container.innerHTML = view.runHeading(run);
        if (run.status === 'completed') {
          const report = await api.getReport(identifier);
          if (!active) return;
          container.insertAdjacentHTML('beforeend', view.reportBody(report));
          if (report.evidence_paged) await loadEvidence(0);
          document
            .getElementById('exportReport')
            .addEventListener('click', () => downloadReport(identifier));
        } else if (run.status === 'failed') {
          container.insertAdjacentHTML('beforeend', view.runProgress(run));
          container.insertAdjacentHTML(
            'beforeend',
            run.resumable
              ? '<p>توقف التقييم بعد أخطاء تقنية متكررة. تحقق من الاتصال وإعدادات المحكّم ثم استأنف.</p><button type="button" class="btn" id="resumeRun">استئناف التقييم</button>'
              : view.empty(
                'تعذّر إكمال التقييم',
                'راجع اتصال النموذج ثم ابدأ تقييمًا جديدًا.',
                'evaluation-setup.html',
                'تقييم جديد'
              )
          );
          if (run.resumable) bindRunAction('resumeRun', api.resumeRun);
        } else {
          container.insertAdjacentHTML('beforeend', view.runProgress(run));
          if (run.status !== 'cancelled') { timer = setTimeout(load, run.status === 'pending' ? 15000 : 10000); }
        }
        if (['pending', 'running'].includes(run.status) || run.resumable) {
          container.insertAdjacentHTML(
            'beforeend',
            '<button type="button" class="btn btn-secondary" id="cancelRun">إلغاء التقييم</button>'
          );
          bindRunAction('cancelRun', api.cancelRun);
        }
        container.insertAdjacentHTML(
          'beforeend',
          view.link('history.html', 'العودة إلى سجل التقييمات')
        );
        container.querySelectorAll('details').forEach((item, index) => {
          item.open = opened[index] || false;
        });
        if (focused) { document.getElementById(focused)?.focus({ preventScroll: true }); }
      } catch (error) {
        if (!active) return;
        view.showError(error.message);
        container.innerHTML =
          '<button type="button" class="btn" id="retryReport">إعادة المحاولة</button>';
        document.getElementById('retryReport').addEventListener('click', load);
      }
    }
    window.addEventListener('pagehide', () => {
      active = false;
      clearTimeout(timer);
    });
    await load();
  }

  Object.assign((window.HARASS_PAGES ||= {}), {
    'evaluation-run': reportPage
  });
})();
