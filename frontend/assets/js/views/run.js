/* Evaluation lifecycle, progress and bounded page navigation. */
(() => {
  'use strict';
  const { escape, date, link, status, table, tableRow } = window.HARASS;
  const runActions = { completed: 'فتح التقرير', running: 'متابعة التقدم' };
  const ELAPSED_LABEL = 'الوقت منذ بدء التنفيذ';
  const WORKER_OFFLINE = 'العامل غير متصل. سيستأنف التنفيذ عند تشغيله.';
  const EVENTS = {
    created: 'أُنشئ',
    started: 'بدأ',
    suspended: 'توقف',
    resumed: 'استؤنف',
    completed: 'اكتمل',
    failed: 'فشل',
    cancelled: 'أُلغي'
  };

  // Hours and minutes from the start until the end, or until now.
  function elapsed (run) {
    const end = run.finished_at ? new Date(run.finished_at) : new Date();
    const minutes = Math.max(0, Math.floor((end - new Date(run.started_at)) / 60000));
    return Math.floor(minutes / 60) + ' س ' + (minutes % 60) + ' د';
  }

  function progressLabel (run, completed, total) {
    if (total) return 'الحالات المكتملة: ' + completed + ' من ' + total;
    return run.status === 'running' ? 'جارٍ تجهيز الحالات' : 'لم يبدأ تنفيذ الحالات';
  }

  function completedCases (run, total) {
    return Math.min(total, Math.max(0, Number(run.completed_cases) || 0));
  }

  function runTable (runs, caption = 'تقييمات حسابك') {
    return (
      '<section class="card">' +
      table(
        caption,
        ['النموذج', 'تاريخ الإنشاء', 'الحالة', 'التقرير'],
        runs.map((run) =>
          tableRow(run.target_model, [
            escape(date(run.created_at)),
            status(run.status),
            link(
              'evaluation-run.html?run_id=' + encodeURIComponent(run.run_id),
              runActions[run.status] || 'عرض التفاصيل'
            )
          ])
        )
      ) +
      '</section>'
    );
  }

  function runHeading (run) {
    return (
      '<div class="report-heading card"><div><h2><bdi>' +
      escape(run.target_model) +
      '</bdi></h2>' +
      runTimes(run) +
      '</div>' +
      status(run.status) +
      '</div>'
    );
  }

  function runTimes (run) {
    const rows = [
      ['أُنشئ', run.created_at && date(run.created_at)],
      ['بدأ التنفيذ', run.started_at && date(run.started_at)],
      ['انتهى', run.finished_at && date(run.finished_at)],
      [ELAPSED_LABEL, run.started_at && elapsed(run)]
    ];
    return (
      '<dl class="run-times">' +
      rows
        .filter(([, value]) => value)
        .map(
          ([label, value]) =>
            '<div><dt>' + label + '</dt><dd>' + escape(value) + '</dd></div>'
        )
        .join('') +
      '</dl>' +
      (run.lifecycle_events?.length
        ? '<details><summary>سجل التشغيل</summary><ol>' +
          run.lifecycle_events
            .map(
              (event) =>
                '<li>' +
                escape(EVENTS[event.event] || event.event) +
                ' · ' +
                escape(date(event.at)) +
                '</li>'
            )
            .join('') +
          '</ol></details>'
        : '')
    );
  }

  function runProgress (run) {
    const total = Math.max(0, Number(run.total_cases) || 0);
    const completed = completedCases(run, total);
    const percent = total ? Math.floor((completed / total) * 100) : 0;
    return (
      '<div class="run-progress-row card"><label for="evaluationProgress">' +
      progressLabel(run, completed, total) +
      '</label><progress id="evaluationProgress" max="' +
      (total || 1) +
      '" value="' +
      completed +
      '">' +
      percent +
      '%</progress>' +
      '<p class="hint">المحاولات المحفوظة: ' +
      escape(run.completed_attempts || 0) +
      '</p>' +
      (run.worker_available === false &&
      ['pending', 'running'].includes(run.status)
        ? '<p class="coverage-warning">' + WORKER_OFFLINE + '</p>'
        : '') +
      '</div>'
    );
  }

  function updateRunProgress (container, run) {
    const total = Math.max(0, Number(run.total_cases) || 0);
    const completed = completedCases(run, total);
    const progress = container.querySelector('#evaluationProgress');
    progress.max = total || 1;
    progress.value = completed;
    container.querySelector('label[for="evaluationProgress"]').textContent =
      progressLabel(run, completed, total);
    container.querySelector('.run-progress-row .hint').textContent =
      'المحاولات المحفوظة: ' + run.completed_attempts;
    const warning = container.querySelector(
      '.run-progress-row .coverage-warning'
    );
    if (run.worker_available === false && !warning) {
      const notice = document.createElement('p');
      notice.className = 'coverage-warning';
      notice.textContent = WORKER_OFFLINE;
      progress.parentElement.append(notice);
    } else if (run.worker_available !== false) warning?.remove();
    const elapsedTerm = [...container.querySelectorAll('.run-times dt')].find(
      (item) => item.textContent === ELAPSED_LABEL
    );
    if (elapsedTerm && run.started_at) {
      elapsedTerm.nextElementSibling.textContent = elapsed(run);
    }
  }

  window.HARASS = Object.freeze({
    ...window.HARASS,
    runTable,
    runHeading,
    runProgress,
    updateRunProgress
  });
})();
