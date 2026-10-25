/* Account initialization and page-controller dispatch. */
(() => {
  'use strict';

  const api = window.HARASS_API;
  const view = window.HARASS;
  const page = document.body.dataset.page;
  const publicPages = ['home', 'login', 'signup', 'forgot-password', 'reset-password', 'verify-email'];
  const section =
    {
      'model-configuration': 'connections'
    }[page] || page;

  function initializeNavigation () {
    document.querySelectorAll('.main-nav a').forEach((anchor) => {
      if (anchor.getAttribute('href') === section + '.html') {
        anchor.setAttribute(
          'aria-current',
          section === page ? 'page' : 'location'
        );
      }
    });
    window.addEventListener('pageshow', (event) => {
      if (event.persisted) location.reload();
    });
  }

  async function initializeAccount () {
    const user = await api.me();
    document.querySelectorAll('[data-user-name]').forEach((element) => {
      element.textContent = user.full_name;
    });
    document.querySelectorAll('[data-logout]').forEach((button) => {
      button.addEventListener('click', async () => {
        view.busy(button, true);
        try {
          await api.logout();
          location.href = 'login.html';
        } catch {
          view.showError('تعذّر تسجيل الخروج. أعد المحاولة.');
          view.busy(button, false);
        }
      });
    });
  }

  async function start () {
    // Prevent native form submission while account and page initialization are pending.
    document.querySelectorAll('form').forEach((form) => {
      form.addEventListener('submit', (event) => event.preventDefault());
    });
    view.mountShell(publicPages.includes(page));
    initializeNavigation();
    if (page === 'home') return;
    if (publicPages.includes(page)) { return window.HARASS_PAGES[page](); }
    await initializeAccount();
    view.configureLabels(await api.options());
    await window.HARASS_PAGES[page]?.();
  }

  start().catch((error) =>
    view.showError(
      error.message || 'تعذّر تحميل الصفحة. أعد تحميلها للمحاولة مجددًا.'
    )
  );
})();
