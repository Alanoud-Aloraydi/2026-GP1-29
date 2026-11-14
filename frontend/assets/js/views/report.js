/* Evaluation metrics, coverage and report composition. */
(() => {
  'use strict';
  const {
    escape,
    table,
    tableRow,
    dialects,
    axes,
    labels,
    evidence,
    owaspCategories
  } = window.HARASS;

  const CATEGORY_ORDER = [
    ['FUL', 'أجاب عن الطلب'],
    ['PRF', 'أجاب جزئيًا'],
    ['REF', 'رفض الطلب'],
    ['UNC', 'رد غير واضح']
  ];

  function percent (metric) {
    return metric?.rate == null ? '—' : (metric.rate * 100).toFixed(1) + '%';
  }

  function fraction (metric) {
    return metric?.total ? metric.count + ' من ' + metric.total : '';
  }

  function interval (metric) {
    const bounds = metric?.clustered_95;
    return bounds && bounds[1] > bounds[0]
      ? 'النطاق المتوقع (95%): <span class="num">' +
          (bounds[0] * 100).toFixed(1) +
          '–' +
          (bounds[1] * 100).toFixed(1) +
          '%</span>'
      : '';
  }

  function fillWidth (metric) {
    return metric?.rate == null ? 0 : Math.round(metric.rate * 100);
  }

  function axisMetric (metrics, axis) {
    return axis === 'AT'
      ? metrics?.adversarial?.attack_success
      : metrics?.over_refusal?.over_refusal;
  }

  function metricCard (label, metric, helper, tone = '') {
    const lines = [escape(helper), interval(metric)].filter(Boolean);
    return (
      '<div class="metric-card' +
      (tone ? ' ' + tone : '') +
      '"><p class="metric-label">' +
      escape(label) +
      '</p><p class="metric-value"><span class="num">' +
      percent(metric) +
      '</span></p><div class="track' +
      (tone === 'attack' ? ' track-attack' : '') +
      '"><span data-fill="' +
      fillWidth(metric) +
      '"></span></div>' +
      (lines.length ? '<p class="hint">' + lines.join(' · ') + '</p>' : '') +
      '</div>'
    );
  }

  function discriminationCard (metrics) {
    const harmful = metrics?.adversarial?.refusal?.rate;
    const safe = metrics?.over_refusal?.over_refusal?.rate;
    if (harmful == null || safe == null) return '';
    const gap = (harmful - safe) * 100;
    return (
      '<div class="metric-card"><p class="metric-label">قدرة التمييز بين الضار والمشروع</p>' +
      '<p class="metric-value"><span class="num">' +
      gap.toFixed(1) +
      '</span> نقطة</p><p class="hint">' +
      escape(
        'رفض الطلبات الضارة ' +
          (harmful * 100).toFixed(1) +
          '% مقابل رفض الطلبات المشروعة ' +
          (safe * 100).toFixed(1) +
          '%. الأعلى أفضل.'
      ) +
      '</p></div>'
    );
  }

  function coverageCard (metrics) {
    const unscored = metrics?.unscored_outcomes || 0;
    return (
      '<div class="metric-card"><p class="metric-label">اكتمال التقييم</p>' +
      '<p class="metric-value"><span class="num">' +
      (unscored === 0 ? 'مكتمل' : unscored) +
      '</span></p><p class="hint">' +
      escape(
        unscored === 0
          ? 'كل الحالات حصلت على حكم.'
          : unscored + ' محاولة بلا حكم، مستبعدة من النسب.'
      ) +
      '</p></div>'
    );
  }

  function summaryCards (report) {
    const metrics = report.primary_metrics || {};
    const attack = axisMetric(metrics, 'AT');
    const refusal = axisMetric(metrics, 'OR');
    const cards = [];
    if (attack) {
      cards.push(
        metricCard(
          'معدل نجاح الاختراق',
          attack,
          'نفّذ النموذج الطلب الضار في ' + attack.count + ' من ' + attack.total + ' محاولة. الأقل أفضل.',
          'attack'
        )
      );
    }
    if (refusal) {
      cards.push(
        metricCard(
          'معدل الرفض المفرط',
          refusal,
          'رفض النموذج ' + refusal.count + ' من ' + refusal.total + ' طلبًا مشروعًا دون مبرر. الأقل أفضل.',
          'refusal'
        )
      );
    }
    cards.push(discriminationCard(metrics));
    cards.push(coverageCard(metrics));
    return '<section class="metric-grid">' + cards.filter(Boolean).join('') + '</section>';
  }

  function barRow (label, metric, attack) {
    return (
      '<div class="bar-row"><span class="bar-label">' +
      escape(label) +
      '</span><div class="track' +
      (attack ? ' track-attack' : '') +
      '"><span data-fill="' +
      fillWidth(metric) +
      '"></span></div><span class="num">' +
      percent(metric) +
      '</span><small>' +
      escape(fraction(metric)) +
      '</small></div>'
    );
  }

  function dialectCard (report) {
    const metrics = report.primary_metrics || {};
    const attacks = metrics.adversarial_breakdowns?.variety || {};
    const refusals = metrics.over_refusal_breakdowns?.variety || {};
    const keys = Object.keys({ ...attacks, ...refusals });
    if (!keys.length) return '';
    const section = (title, groups, picker, attack = false) =>
      Object.keys(groups).length
        ? '<h3>' +
          escape(title) +
          '</h3><div class="report-stack">' +
          keys
            .filter((key) => groups[key])
            .map((key) =>
              barRow(dialects[key] || key, picker(groups[key]), attack)
            )
            .join('') +
          '</div>'
        : '';
    return (
      '<section class="card"><h2>النتائج حسب اللهجة</h2>' +
      section('معدل نجاح الاختراق', attacks, (g) => g.attack_success, true) +
      section('معدل الرفض المفرط', refusals, (g) => g.over_refusal) +
      '</section>'
    );
  }

  function categoryDistribution (report) {
    const counts = report.response_categories || {};
    const bars = Object.entries(axes)
      .map(([axis, title]) => {
        const data = counts[axis] || {};
        const total = Object.values(data).reduce((sum, n) => sum + n, 0);
        if (!total) return '';
        const segments = CATEGORY_ORDER.filter(([code]) => data[code])
          .map(
            ([code]) =>
              '<span class="cat-' +
              code +
              '" data-fill="' +
              (data[code] / total) * 100 +
              '">' +
              escape(code + ' ' + data[code]) +
              '</span>'
          )
          .join('');
        return (
          '<div><div class="bar-head"><strong>' +
          escape(title) +
          '</strong><span class="hint">' +
          total +
          ' رد</span></div><div class="stacked-bar">' +
          segments +
          '</div></div>'
        );
      })
      .filter(Boolean)
      .join('');
    if (!bars) return '';
    const legend = CATEGORY_ORDER.map(
      ([code, name]) =>
        '<li><span class="swatch cat-' +
        code +
        '"></span>' +
        escape(code + ' ' + name) +
        '</li>'
    ).join('');
    return (
      '<section class="card"><h2>توزيع فئات الرد</h2>' +
      '<div class="report-stack">' +
      bars +
      '</div><ul class="legend">' +
      legend +
      '</ul></section>'
    );
  }

  function metricCell (metric) {
    return (
      '<span class="num">' +
      escape(percent(metric)) +
      '</span> <small>' +
      escape(fraction(metric)) +
      '</small>'
    );
  }

  function breakdownTable (report, dimension, caption, names) {
    const metrics = report.primary_metrics || {};
    const attacks = metrics.adversarial_breakdowns?.[dimension] || {};
    const refusals = metrics.over_refusal_breakdowns?.[dimension] || {};
    // OWASP risks apply to attacks only; show the ones with no cases too.
    const listed =
      dimension === 'owasp_category' && Object.keys(attacks).length
        ? owaspCategories
        : [];
    const keys = [
      ...new Set([...listed, ...Object.keys(attacks), ...Object.keys(refusals)])
    ];
    if (!keys.length) return '';
    const present = (key) => key in attacks || key in refusals;
    const columns = [
      Object.keys(attacks).length && [
        'معدل نجاح الاختراق',
        (key) => metricCell(attacks[key]?.attack_success)
      ],
      Object.keys(refusals).length && [
        'معدل الرفض المفرط',
        (key) => metricCell(refusals[key]?.over_refusal)
      ]
    ].filter(Boolean);
    return table(
      caption,
      ['التصنيف', ...columns.map(([title]) => title)],
      keys.map((key) =>
        tableRow(
          names[key] || key,
          present(key)
            ? columns.map(([, cell]) => cell(key))
            : columns.map((_, index) =>
              index ? '—' : '<span class="hint">لا توجد حالات</span>'
            )
        )
      )
    );
  }

  function baselineComparison (report) {
    if (report.run_type !== 'agentic') return '';
    const rows = Object.keys(axes)
      .filter((axis) => axisMetric(report.primary_metrics, axis))
      .map((axis) =>
        tableRow(axes[axis], [
          metricCell(axisMetric(report.primary_metrics, axis)),
          metricCell(axisMetric(report.baseline_metrics, axis))
        ])
      );
    return rows.length
      ? '<section class="card">' +
          table(
            'مقارنة المحاولات مع الطلبات الأصلية',
            ['المحور', 'المحاولات التكيفية', 'الطلبات الأصلية للمقارنة'],
            rows
          ) +
          '</section>'
      : '';
  }

  function adaptiveTable (report) {
    if (report.run_type !== 'agentic' || !report.adaptive) return '';
    const rows = Object.entries(report.adaptive).map(([axis, summary]) => {
      const point = summary.defect_within_k?.[report.attempt_budget];
      return tableRow(axes[axis] || axis, [
        escape(summary.defects_detected + ' من ' + summary.cases),
        escape(summary.attempts_submitted),
        escape(point?.undetermined ?? '—')
      ]);
    });
    return (
      '<section class="card">' +
      table(
        'اكتشاف الخلل على مستوى الحالة',
        ['المحور', 'حالات اكتُشف فيها خلل', 'المحاولات المسجلة', 'حالات غير محسومة'],
        rows
      ) +
      '<p class="hint">الاكتشاف خلال ' +
      escape(report.attempt_budget) +
      ' محاولات كحد أقصى لكل حالة.</p></section>'
    );
  }

  function coverageTable (report) {
    const counts = report.coverage || {};
    if (!report.coverage) {
      const baseline = report.run_type === 'baseline';
      for (const outcome of report.outcomes) {
        if ((outcome.variant_name === 'baseline') !== baseline) continue;
        const row = (counts[outcome.axis] ||= {
          submitted: 0,
          unscored: 0,
          unclear: 0
        });
        row.submitted++;
        row.unscored += Boolean(
          outcome.error ||
            !outcome.response_category ||
            (outcome.axis === 'AT' && outcome.attack_succeeded == null)
        );
        row.unclear += !outcome.error && outcome.response_category === 'UNC';
      }
    }
    return (
      '<section class="card">' +
      table(
        'اكتمال الأحكام',
        ['المحور', 'المحاولات المسجلة', 'أحكام غير مكتملة', 'ردود غير مفهومة · UNC'],
        Object.entries(counts).map(([axis, row]) =>
          tableRow(axes[axis], [row.submitted, row.unscored, row.unclear].map(escape))
        )
      ) +
      '<p class="hint">UNC يبقى ضمن مقام المعدل. الطلب غير المقيّم يُستبعد منه.</p></section>'
    );
  }

  function classificationTables (report) {
    const dimensions = {
      subject_domain: 'المجال',
      risk_category: 'فئة الخطر',
      strategy: 'استراتيجية التجاوز',
      owasp_category: 'فئة OWASP لأصل الحالة'
    };
    const content = Object.entries(dimensions)
      .map(([dimension, label]) =>
        breakdownTable(report, dimension, 'النتائج حسب ' + label, labels)
      )
      .join('');
    return content
      ? '<details class="case-evidence"><summary>عرض نتائج المجالات والمخاطر والاستراتيجيات وOWASP</summary>' +
          '<div class="evidence-content report-stack">' +
          content +
          '</div></details>'
      : '';
  }

  function reportBody (report) {
    const modes = {
      baseline: 'اختبار أساسي',
      agentic: 'اختبار تكيّفي',
      static: 'تعداد ثابت'
    };
    const scope = report.selection?.varieties
      ?.map((code) => dialects[code] || code)
      .join('، ');
    const unscored = report.metrics?.unscored_outcomes || 0;
    const toolbar =
      '<div class="section-toolbar"><div class="chip-row">' +
      '<span class="chip">' +
      escape(modes[report.run_type] || '—') +
      '</span><span class="chip">' +
      escape(scope || 'النطاق موضح في الحالات') +
      '</span></div>' +
      '<button class="btn btn-secondary" id="exportReport" type="button">تنزيل التقرير · JSON</button></div>';
    const notice =
      '<div class="report-notice"><strong>قراءة النتائج</strong>' +
      '<p>المعدل الأقل أفضل في المحورين. الأحكام آلية إلى حين التحقق بالمراجعة البشرية.' +
      (unscored
        ? ' <span class="coverage-warning">الأحكام غير المكتملة تحدّ من التفسير؛ راجع اكتمال الأحكام.</span>'
        : '') +
      '</p></div>';
    return (
      '<div class="report-stack">' +
      toolbar +
      notice +
      summaryCards(report) +
      baselineComparison(report) +
      adaptiveTable(report) +
      dialectCard(report) +
      categoryDistribution(report) +
      coverageTable(report) +
      classificationTables(report) +
      evidence(report) +
      '</div>'
    );
  }

  window.HARASS = Object.freeze({ ...window.HARASS, reportBody });
})();
