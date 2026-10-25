/* Dashboard page interactions and error recovery. */
(() => {
  'use strict';
  const api = window.HARASS_API;
  const view = window.HARASS;

  async function dashboardPage () {
    const container = document.getElementById('overview');
    const [connections, history] = await Promise.all([
      api.connectionPage(),
      api.runPage()
    ]);
    const runs = history.items;
    const ready = connections.counts.connected || 0;
    const counts = [
      [connections.total, 'اتصالات محفوظة'],
      [ready, 'اجتازت اختبار الوصول'],
      [history.total, 'تقييمات في السجل']
    ];
    container.innerHTML =
      '<div class="overview-strip">' +
      counts
        .map(
          ([count, label]) =>
            '<div><strong>' +
            count +
            '</strong><span>' +
            label +
            '</span></div>'
        )
        .join('') +
      '</div><div class="section-toolbar">' +
      view.link('evaluation-setup.html', 'تقييم جديد') +
      view.link('connections.html', 'إدارة الاتصالات') +
      '</div>' +
      (runs.length
        ? view.runTable(runs.slice(0, 5), 'آخر التقييمات')
        : connections.total
          ? view.empty(
            'ابدأ أول تقييم',
            'اختر اتصالًا محفوظًا لتقييم النموذج.',
            'evaluation-setup.html',
            'تقييم جديد'
          )
          : view.empty(
            'ابدأ بإعداد اتصال نموذج',
            'احفظ بيانات الاتصال واختبر الوصول.',
            'model-configuration.html',
            'إضافة اتصال'
          ));
  }

  Object.assign((window.HARASS_PAGES ||= {}), { dashboard: dashboardPage });
})();
