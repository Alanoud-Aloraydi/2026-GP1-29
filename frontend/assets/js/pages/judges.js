/* Administrator page that compares published judge benchmark reports. */
import { api } from '../core/api-client.js';
import { start } from '../core/bootstrap.js';
import { busy, clearError, empty, showError } from '../core/ui.js';
import { detail as reportDetail, summaryTable } from '../views/judge-comparison.js';

async function judgesPage () {
  const reports = document.getElementById('reports');
  const detail = document.getElementById('reportDetail');
  const button = document.getElementById('reload');
  const fail = (error) => showError(error.status === 403 ? 'هذه الصفحة للمشرفين فقط.' : error.message);

  async function show (reportId) {
    clearError();
    try {
      detail.innerHTML = reportDetail(await api.judgeReport(reportId));
      detail.focus();
    } catch (error) {
      fail(error);
    }
  }

  async function load () {
    busy(button, true);
    clearError();
    try {
      const summaries = await api.judgeReports();
      reports.innerHTML = summaries.length
        ? summaryTable(summaries)
        : empty('لا توجد تقارير بعد', 'انشر تقريرًا بالأمر harass-reports publish ليظهر هنا.');
    } catch (error) {
      reports.textContent = 'تعذّر تحميل التقارير.';
      fail(error);
    } finally {
      busy(button, false);
    }
  }

  reports.addEventListener('click', (event) => {
    const target = event.target.closest('[data-report]');
    if (target) show(target.dataset.report);
  });
  button.addEventListener('click', load);
  await load();
}

start(judgesPage);
