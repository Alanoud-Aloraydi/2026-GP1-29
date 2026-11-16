/* Shared navigation, escaped markup and accessible UI primitives. */
(() => {
  'use strict';
  const dialects = {};
  const axes = {};
  const owaspCategories = [];
  const statuses = {
    pending: 'قيد الانتظار',
    running: 'جارٍ التقييم',
    completed: 'اكتمل التقييم',
    failed: 'تعذّر إكمال التقييم',
    cancelled: 'أُلغي التقييم',
    connected: 'اتصال ناجح',
    not_tested: 'لم يُختبر',
    testing: 'جارٍ الاختبار'
  };
  const labels = {};
  const entities = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  };

  function escape (value) {
    return String(value ?? '').replace(
      /[&<>"']/g,
      (character) => entities[character]
    );
  }

  function date (value) {
    return value
      ? new Date(value).toLocaleString('ar-SA-u-ca-gregory', {
        dateStyle: 'medium',
        timeStyle: 'short'
      })
      : '—';
  }

  function mountShell (publicPage) {
    const header = document.querySelector('[data-shell-header]');
    if (!header) return;
    const navigation = publicPage
      ? [
          ['#measure', 'ماذا نقيس'],
          ['#dialects', 'اللهجات'],
          ['#how', 'كيف يعمل'],
          ['#evidence', 'التقرير']
        ]
      : [
          ['dashboard.html', 'نظرة عامة'],
          ['connections.html', 'اتصالات النماذج'],
          ['evaluation-setup.html', 'تقييم جديد'],
          ['history.html', 'سجل التقييمات']
        ];
    const brand =
      '<a class="brand" href="' +
      (publicPage ? 'index.html' : 'dashboard.html') +
      '"><img src="assets/images/harass-logo.png" alt="HARASS"></a>';
    const menu = publicPage && document.body.dataset.page !== 'home'
      ? ''
      : '<nav class="main-nav" aria-label="التنقل الرئيسي">' +
        navigation
          .map(([path, label]) => '<a href="' + path + '">' + label + '</a>')
          .join('') +
        '</nav>';
    const actions = publicPage
      ? link('login.html', 'تسجيل الدخول') + link('signup.html', 'إنشاء حساب', true)
      : '<a class="user-link" href="account.html" aria-label="أمان الحساب">' +
        '<span class="avatar" data-user-initial aria-hidden="true"></span>' +
        '<span data-user-name></span></a>' +
        '<button class="btn btn-sm" data-logout type="button">تسجيل الخروج</button>';
    header.className = publicPage ? 'public-header' : 'app-header';
    header.innerHTML =
      '<div class="container">' +
      brand +
      menu +
      '<div class="header-actions">' +
      actions +
      '</div></div>';
    const footer = document.querySelector('[data-shell-footer]');
    footer.innerHTML =
      '<div class="container"><p>حَرَس · تقييم سلامة النماذج العربية</p>' +
      '<p>© 2026 HARASS</p></div>';
  }

  // The server enforces the role; this only decides whether to offer the link.
  function showAdminNavigation (user) {
    const navigation = document.querySelector('.main-nav');
    if (user.role !== 'admin' || !navigation) return;
    const current = document.body.dataset.page === 'judges';
    navigation.insertAdjacentHTML(
      'beforeend',
      '<a href="judges.html"' +
        (current ? ' aria-current="page"' : '') +
        '>مقارنة المحكّمين</a>'
    );
  }

  // The page policy forbids inline style attributes, so bar widths travel as
  // data-fill and are applied through the style object.
  function fillBars () {
    document.querySelectorAll('[data-fill]').forEach((bar) => {
      bar.style.width = bar.dataset.fill + '%';
    });
  }
  new MutationObserver(fillBars).observe(document.documentElement, {
    childList: true,
    subtree: true
  });
  document.addEventListener('DOMContentLoaded', fillBars);

  function busy (button, loading) {
    button.disabled = loading;
    button.classList.toggle('btn-loading', loading);
  }

  function showError (message) {
    const box = document.getElementById('pageError');
    if (!box) return;
    box.textContent = message;
    box.hidden = false;
    box.focus();
  }

  function clearError () {
    const box = document.getElementById('pageError');
    if (!box) return;
    box.hidden = true;
    box.textContent = '';
  }

  function safeReturn () {
    const destination = new URLSearchParams(location.search).get('return');
    const allowedPages = [
      'account.html',
      'dashboard.html',
      'connections.html',
      'model-configuration.html',
      'evaluation-setup.html',
      'evaluation-run.html',
      'history.html',
      'judges.html'
    ];
    return destination &&
      !destination.includes('#') &&
      allowedPages.includes(destination.split('?')[0])
      ? destination
      : 'dashboard.html';
  }

  function link (path, label, primary = false) {
    return (
      '<a class="btn btn-sm' +
      (primary ? ' btn-primary' : '') +
      '" href="' +
      escape(path) +
      '">' +
      escape(label) +
      '</a>'
    );
  }

  function empty (title, description, path, label) {
    return (
      '<div class="empty-state"><h2>' +
      escape(title) +
      '</h2><p>' +
      escape(description) +
      '</p>' +
      (path ? link(path, label) : '') +
      '</div>'
    );
  }

  function status (value, context = 'run') {
    return (
      '<span class="status-label status-' +
      escape(value) +
      '">' +
      escape(
        context === 'connection' && value === 'failed'
          ? 'تعذّر الاتصال'
          : statuses[value] || value
      ) +
      '</span>'
    );
  }

  function tableRow (label, cells) {
    return (
      '<tr><th scope="row"><bdi>' +
      escape(label) +
      '</bdi></th>' +
      cells.map((content) => '<td>' + content + '</td>').join('') +
      '</tr>'
    );
  }

  // Rows contain markup produced here; escape all API values before inserting them.
  // A column given as [label, definition] shows its definition on hover.
  function table (caption, columns, rows) {
    const headings = columns.map((column) =>
      Array.isArray(column)
        ? '<th scope="col"><span class="has-definition" title="' +
          escape(column[1]) +
          '">' +
          escape(column[0]) +
          '</span></th>'
        : '<th scope="col">' + escape(column) + '</th>'
    );
    return (
      '<div class="table-region" role="region" tabindex="0" aria-label="' +
      escape(caption) +
      '"><table><caption>' +
      escape(caption) +
      '</caption><thead><tr>' +
      headings.join('') +
      '</tr></thead><tbody>' +
      rows.join('') +
      '</tbody></table></div>'
    );
  }

  function pageControls (offset, total, prefix, limit = 50) {
    if (total <= limit) return '';
    return (
      '<div class="report-actions"><button type="button" class="btn btn-secondary" id="' +
      prefix +
      'Previous"' +
      (offset ? '' : ' disabled') +
      '>السابق</button><span>' +
      (offset + 1) +
      '–' +
      Math.min(offset + limit, total) +
      ' من ' +
      total +
      '</span><button type="button" class="btn btn-secondary" id="' +
      prefix +
      'Next"' +
      (offset + limit < total ? '' : ' disabled') +
      '>التالي</button></div>'
    );
  }

  function configureLabels (metadata) {
    Object.assign(dialects, metadata.dialects);
    Object.assign(axes, metadata.axes);
    Object.assign(labels, metadata.labels);
    owaspCategories.push(...metadata.owasp_categories);
  }

  window.HARASS = Object.freeze({
    configureLabels,
    owaspCategories,
    pageControls,
    escape,
    mountShell,
    showAdminNavigation,
    date,
    busy,
    showError,
    clearError,
    safeReturn,
    link,
    empty,
    status,
    table,
    tableRow,
    dialects,
    axes,
    labels
  });
})();
