/* Shared page layout, account initialization and page-controller start. */
import { api } from './api-client.js';
import { runBusy } from './forms.js';
import { configureCatalogue, html, link, showError } from './ui.js';

const page = document.body.dataset.page;
const isPublic = document.body.hasAttribute('data-public');

const publicNavigation = [
  ['#measure', 'ماذا نقيس'], ['#dialects', 'اللهجات'], ['#how', 'كيف يعمل'], ['#evidence', 'التقرير']
];
const accountNavigation = [
  ['dashboard.html', 'نظرة عامة'], ['connections.html', 'اتصالات النماذج'],
  ['evaluation-setup.html', 'تقييم جديد'], ['history.html', 'سجل التقييمات'],
  ['models.html', 'النماذج الأساسية']
];
// The server enforces the role; this only decides whether to offer the links.
const adminNavigation = [['judges.html', 'مقارنة المحكّمين']];
// A page that belongs to another section marks that section's link.
const section = { 'model-configuration': 'connections', model: 'models' }[page] || page;

const navigationLink = ([path, label]) => {
  const current = path === section + '.html' && (section === page ? 'page' : 'location');
  return html`<a href="${path}" ${current && html`aria-current="${current}"`}>${label}</a>`;
};

const accountActions = html`
  <a class="user-link" href="account.html" aria-label="أمان الحساب">
    <span class="avatar" data-user-initial aria-hidden="true"></span><span data-user-name></span>
  </a>
  <button class="btn btn-sm" data-logout type="button">تسجيل الخروج</button>`;

export function mountShell (publicPage) {
  const header = document.querySelector('[data-shell-header]');
  if (!header) return;
  const showMenu = !publicPage || page === 'home';
  header.className = publicPage ? 'public-header' : 'app-header';
  header.innerHTML = html`
    <div class="container">
      <a class="brand" href="${publicPage ? 'index.html' : 'dashboard.html'}">
        <img src="assets/images/harass-logo.png" alt="HARASS">
      </a>
      ${showMenu && html`<nav class="main-nav" aria-label="التنقل الرئيسي">${
        (publicPage ? publicNavigation : accountNavigation).map(navigationLink)
      }</nav>`}
      <div class="header-actions">${publicPage
        ? [link('login.html', 'تسجيل الدخول'), link('signup.html', 'إنشاء حساب', true)]
        : accountActions}</div>
    </div>`;
  document.querySelector('[data-shell-footer]').innerHTML = html`
    <div class="container"><p>حَرَس · تقييم سلامة النماذج العربية</p><p>© 2026 HARASS</p></div>`;
}

async function initializeAccount () {
  const user = await api.me();
  if (user.role === 'admin') {
    document.querySelector('.main-nav')?.insertAdjacentHTML('beforeend', html`${adminNavigation.map(navigationLink)}`);
  }
  document.querySelectorAll('[data-user-name]').forEach((element) => { element.textContent = user.full_name; });
  document.querySelectorAll('[data-user-initial]').forEach((element) => {
    element.textContent = user.full_name.trim().charAt(0);
  });
  document.querySelectorAll('[data-logout]').forEach((button) => button.addEventListener('click', () =>
    runBusy(button, async () => {
      await api.logout();
      location.href = 'login.html';
    })
  ));
  configureCatalogue(await api.options());
}

/**
 * Mount the layout, load the account on private pages, then run the page
 * controller. Forms are blocked first so no field can be submitted natively
 * while initialization is pending.
 */
export async function start (controller) {
  document.querySelectorAll('form').forEach((form) => {
    form.addEventListener('submit', (event) => event.preventDefault());
  });
  mountShell(isPublic);
  // A page restored from the back-forward cache would show stale data.
  window.addEventListener('pageshow', (event) => { if (event.persisted) location.reload(); });
  try {
    if (!isPublic) await initializeAccount();
    await controller?.();
  } catch (error) {
    showError(error.message || 'تعذّر تحميل الصفحة. أعد تحميلها للمحاولة مجددًا.');
  }
}

// The home page has no controller of its own, so it loads this module alone.
if (page === 'home') start();
