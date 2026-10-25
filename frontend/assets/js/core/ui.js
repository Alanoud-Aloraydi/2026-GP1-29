/* Shared navigation, escaped markup and accessible UI primitives. */
(() => {
  'use strict';
  const dialects = {};
  const axes = {};
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
    const navigation = [
      ['dashboard.html', 'نظرة عامة'],
      ['connections.html', 'اتصالات النماذج'],
      ['evaluation-setup.html', 'تقييم جديد'],
      ['history.html', 'سجل التقييمات']
    ];
    const brand =
      '<a class="brand" href="' +
      (publicPage ? 'index.html' : 'dashboard.html') +
      '"><img src="assets/images/harass-logo.png" alt=""><span>HARASS</span></a>';
    const menu = publicPage
      ? ''
      : '<nav class="main-nav" aria-label="التنقل الرئيسي">' +
        navigation
          .map(([path, label]) => '<a href="' + path + '">' + label + '</a>')
          .join('') +
        '</nav>';
    const actions = publicPage
      ? link('login.html', 'تسجيل الدخول') + link('signup.html', 'إنشاء حساب')
      : '<a href="account.html" data-user-name aria-label="أمان الحساب"></a>' +
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
      'history.html'
    ];
    return destination &&
      !destination.includes('#') &&
      allowedPages.includes(destination.split('?')[0])
      ? destination
      : 'dashboard.html';
  }

  function link (path, label) {
    return (
      '<a class="btn btn-sm" href="' +
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
  function table (caption, columns, rows) {
    const headings = columns.map(
      (column) => '<th scope="col">' + escape(column) + '</th>'
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
  }

  window.HARASS = Object.freeze({
    configureLabels,
    pageControls,
    escape,
    mountShell,
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
