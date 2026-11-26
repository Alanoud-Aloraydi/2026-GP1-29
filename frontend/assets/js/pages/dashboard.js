/* Dashboard: account totals, latest runs and the next step. */
import { api } from '../core/api-client.js';
import { start } from '../core/bootstrap.js';
import { empty, figures, html, link } from '../core/ui.js';
import { runTable } from '../views/run.js';

function nextStep (runs, connectionTotal) {
  if (runs.length) return runTable(runs.slice(0, 5), 'آخر التقييمات');
  return connectionTotal
    ? empty('ابدأ أول تقييم', 'اختر اتصالًا محفوظًا لتقييم النموذج.', 'evaluation-setup.html', 'تقييم جديد')
    : empty('ابدأ بإعداد اتصال نموذج', 'احفظ بيانات الاتصال واختبر الوصول.', 'model-configuration.html', 'إضافة اتصال');
}

async function dashboardPage () {
  const [connections, history] = await Promise.all([api.connectionPage(), api.runPage()]);
  const totals = [
    [connections.total, 'اتصالات محفوظة'],
    [connections.counts.connected || 0, 'اجتازت اختبار الوصول'],
    [history.total, 'تقييمات في السجل']
  ];
  document.getElementById('overview').innerHTML = html`
    <div class="section-toolbar">
      ${link('evaluation-setup.html', 'تقييم جديد', true)}
      ${link('connections.html', 'إدارة الاتصالات')}
    </div>
    <div class="overview-strip">${figures(totals)}</div>
    ${nextStep(history.items, connections.total)}`;
}

start(dashboardPage);
