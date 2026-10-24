/* History page interactions and error recovery. */
(() => {
  'use strict';
  const api = window.HARASS_API;
  const view = window.HARASS;
  const { bindPages } = window.HARASS_FORMS;
  async function historyPage () {
    const container = document.getElementById('history');
    const button = document.getElementById('reload');
    let offset = 0;
    async function load () {
      view.busy(button, true);
      view.clearError();
      try {
        const page = await api.runPage(offset);
        const runs = page.items;
        container.innerHTML = runs.length
          ? view.runTable(runs)
          : view.empty(
            'لا توجد تقييمات بعد',
            'ابدأ أول تقييم ليظهر تقريره هنا.',
            'evaluation-setup.html',
            'تقييم جديد'
          );
        container.insertAdjacentHTML(
          'beforeend',
          view.pageControls(offset, page.total, 'history')
        );
        bindPages('history', offset, (value) => {
          offset = value;
          load();
        });
      } catch (error) {
        view.showError(error.message);
        container.textContent =
          'تعذّر تحميل السجل. استخدم تحديث السجل لإعادة المحاولة.';
      } finally {
        view.busy(button, false);
      }
    }
    button.addEventListener('click', load);
    await load();
  }

  Object.assign((window.HARASS_PAGES ||= {}), { history: historyPage });
})();
