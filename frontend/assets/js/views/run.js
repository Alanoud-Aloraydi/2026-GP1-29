/* Evaluation lifecycle, progress and bounded page navigation. */
(() => {
  'use strict';
  const { escape, date, link, status, table, tableRow } = window.HARASS;
  function runTable (runs, caption = 'تقييمات حسابك') {
    return table(
      caption,
      ['النموذج', 'تاريخ الإنشاء', 'الحالة', 'التقرير'],
      runs.map((run) =>
        tableRow(run.target_model, [
          escape(date(run.created_at)),
          status(run.status),
          link(
            'evaluation-run.html?run_id=' + encodeURIComponent(run.run_id),
            run.status === 'completed' ? 'فتح التقرير' : 'عرض التقييم'
          )
        ])
      )
    );
  }

  function runHeading (run) {
    return (
      '<div class="report-heading"><div><h2><bdi>' +
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
      ['أُنشئ', run.created_at],
      ['بدأ التنفيذ', run.started_at],
      ['انتهى', run.finished_at]
    ];
    if (run.started_at) {
      const seconds = Math.max(
        0,
        Math.floor(
          ((run.finished_at ? new Date(run.finished_at) : new Date()) -
            new Date(run.started_at)) /
            1000
        )
      );
      rows.push([
        'الوقت منذ بدء التنفيذ',
        Math.floor(seconds / 3600) +
          ' س ' +
          Math.floor((seconds % 3600) / 60) +
          ' د'
      ]);
    }
    const events = {
      created: 'أُنشئ',
      started: 'بدأ',
      suspended: 'توقف',
      resumed: 'استؤنف',
      completed: 'اكتمل',
      failed: 'فشل',
      cancelled: 'أُلغي'
    };
    return (
      '<dl class="run-times">' +
      rows
        .filter(([, value]) => value)
        .map(
          ([label, value]) =>
            '<div><dt>' +
            label +
            '</dt><dd>' +
            escape(label === 'الوقت منذ بدء التنفيذ' ? value : date(value)) +
            '</dd></div>'
        )
        .join('') +
      '</dl>' +
      (run.lifecycle_events?.length
        ? '<details><summary>سجل التشغيل</summary><ol>' +
          run.lifecycle_events
            .map(
              (event) =>
                '<li>' +
                escape(events[event.event] || event.event) +
                ' · ' +
                escape(date(event.at)) +
                '</li>'
            )
            .join('') +
          '</ol></details>'
        : '')
    );
  }

  function rate (metric) {
    return metric?.rate == null
      ? 'لا توجد نتائج محسومة'
      : (metric.rate * 100).toFixed(1) +
          '% · ' +
          metric.count +
          ' من ' +
          metric.total;
  }

  function runProgress (run) {
    const total = Math.max(0, Number(run.total_cases) || 0);
    const completed = Math.min(
      total,
      Math.max(0, Number(run.completed_cases) || 0)
    );
    const percent = total ? Math.floor((completed / total) * 100) : 0;
    return (
      '<div class="run-progress-row"><label for="evaluationProgress">' +
      (total
        ? 'الحالات المكتملة: ' + completed + ' من ' + total
        : run.status === 'running'
          ? 'جارٍ تجهيز الحالات'
          : 'لم يبدأ تنفيذ الحالات') +
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
        ? '<p class="coverage-warning">العامل غير متصل. سيستأنف التنفيذ عند تشغيله.</p>'
        : '') +
      '</div>'
    );
  }

  function updateRunProgress (container, run) {
    const completed = Math.min(
      run.total_cases,
      Math.max(0, run.completed_cases)
    );
    const progress = container.querySelector('#evaluationProgress');
    progress.max = run.total_cases || 1;
    progress.value = completed;
    container.querySelector('label[for="evaluationProgress"]').textContent =
      run.total_cases
        ? 'الحالات المكتملة: ' + completed + ' من ' + run.total_cases
        : run.status === 'running'
          ? 'جارٍ تجهيز الحالات'
          : 'لم يبدأ تنفيذ الحالات';
    container.querySelector('.run-progress-row .hint').textContent =
      'المحاولات المحفوظة: ' + run.completed_attempts;
    const warning = container.querySelector(
      '.run-progress-row .coverage-warning'
    );
    if (run.worker_available === false && !warning) {
      const notice = document.createElement('p');
      notice.className = 'coverage-warning';
      notice.textContent = 'العامل غير متصل. سيستأنف التنفيذ عند تشغيله.';
      progress.parentElement.append(notice);
    } else if (run.worker_available !== false) warning?.remove();
    const elapsed = [...container.querySelectorAll('.run-times dt')].find(
      (item) => item.textContent === 'الوقت منذ بدء التنفيذ'
    );
    if (elapsed && run.started_at) {
      const minutes = Math.max(
        0,
        Math.floor((Date.now() - new Date(run.started_at)) / 60000)
      );
      elapsed.nextElementSibling.textContent =
        Math.floor(minutes / 60) + ' س ' + (minutes % 60) + ' د';
    }
  }

  window.HARASS = Object.freeze({
    ...window.HARASS,
    runTable,
    runHeading,
    runProgress,
    rate,
    runTimes,
    updateRunProgress
  });
})();
