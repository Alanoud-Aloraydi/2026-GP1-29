/* Administrator page that compares published judge benchmark reports. */
(() => {
  'use strict';
  const api = window.HARASS_API;
  const view = window.HARASS;
  const comparison = window.HARASS_JUDGES;

  async function judgesPage () {
    const list = document.getElementById('reports');
    const detail = document.getElementById('reportDetail');
    const button = document.getElementById('reload');

    function fail (error) {
      view.showError(
        error.status === 403
          ? 'هذه الصفحة للمشرفين فقط.'
          : error.message
      );
    }

    async function open (id) {
      view.clearError();
      try {
        detail.innerHTML = comparison.detail(await api.judgeReport(id));
        detail.focus();
      } catch (error) {
        fail(error);
      }
    }

    async function load () {
      view.busy(button, true);
      view.clearError();
      try {
        const reports = await api.judgeReports();
        list.innerHTML = reports.length
          ? comparison.summaryTable(reports)
          : view.empty(
            'لا توجد تقارير بعد',
            'انشر تقريرًا بالأمر harass-judge-benchmark publish ليظهر هنا.'
          );
      } catch (error) {
        list.textContent = 'تعذّر تحميل التقارير.';
        fail(error);
      } finally {
        view.busy(button, false);
      }
    }

    list.addEventListener('click', (event) => {
      const target = event.target.closest('[data-report]');
      if (target) open(target.dataset.report);
    });
    button.addEventListener('click', load);
    await load();
  }

  Object.assign((window.HARASS_PAGES ||= {}), { judges: judgesPage });
})();
