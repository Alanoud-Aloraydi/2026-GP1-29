/* Evaluation metrics, coverage and report composition. */
(() => {
  'use strict';
  const { escape, table, tableRow, dialects, axes, labels, rate, evidence } = window.HARASS;
  function metricCell (metric, confidence = false) {
    const content = escape(rate(metric));
    if (!confidence) return content;
    const interval = metric?.clustered_95;
    const description =
      interval && interval[1] > interval[0]
        ? 'فترة 95% مجمعة بحسب الطلب: ' +
          (interval[0] * 100).toFixed(1) +
          '%–' +
          (interval[1] * 100).toFixed(1) +
          '%'
        : 'فترة الثقة المجمعة غير متاحة لهذه النتيجة.';
    return content + '<p class="hint">' + escape(description) + '</p>';
  }

  function axisMetric (metrics, axis) {
    return axis === 'AT'
      ? metrics?.adversarial?.attack_success
      : metrics?.over_refusal?.over_refusal;
  }

  function metricTable (report) {
    const adaptive = report.run_type === 'agentic';
    const available = Object.keys(axes).filter(
      (axis) =>
        axisMetric(report.primary_metrics, axis) ||
        report.outcomes.some((outcome) => outcome.axis === axis)
    );
    const rows = available.map((axis) => {
      const cells = [
        metricCell(axisMetric(report.primary_metrics, axis), true)
      ];
      if (adaptive) {
        cells.push(
          metricCell(axisMetric(report.baseline_metrics, axis), true)
        );
      }
      return tableRow(axes[axis], cells);
    });
    const columns = [
      'المحور',
      adaptive ? 'المحاولات التكيفية' : 'الاختبار الأساسي'
    ];
    if (adaptive) columns.push('الطلبات الأصلية للمقارنة');
    return table(
      adaptive
        ? 'مقارنة المحاولات مع الطلبات الأصلية'
        : 'نتائج الطلبات الأصلية',
      columns,
      rows
    );
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
      table(
        'اكتشاف الخلل على مستوى الحالة',
        [
          'المحور',
          'حالات اكتُشف فيها خلل',
          'المحاولات المسجلة',
          'حالات غير محسومة'
        ],
        rows
      ) +
      '<p class="hint">الاكتشاف خلال ' +
      escape(report.attempt_budget) +
      ' محاولات كحد أقصى لكل حالة؛ يختلف عن معدل نجاح المحاولات المفردة.</p>'
    );
  }

  function breakdownTable (report, dimension, caption, names) {
    const metrics = report.primary_metrics || {};
    const attacks = metrics.adversarial_breakdowns?.[dimension] || {};
    const refusals = metrics.over_refusal_breakdowns?.[dimension] || {};
    const keys = [
      ...new Set([...Object.keys(attacks), ...Object.keys(refusals)])
    ];
    if (!keys.length) return '';
    return table(
      caption,
      ['التصنيف', 'نجاح الهجوم · AT', 'الرفض المفرط · OR'],
      keys.map((key) =>
        tableRow(names[key] || key, [
          metricCell(attacks[key]?.attack_success),
          metricCell(refusals[key]?.over_refusal)
        ])
      )
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
      table(
        'تغطية الأحكام',
        [
          'المحور',
          'المحاولات المسجلة',
          'أحكام غير مكتملة',
          'ردود غير مفهومة · UNC'
        ],
        Object.entries(counts).map(([axis, row]) =>
          tableRow(
            axes[axis],
            [row.submitted, row.unscored, row.unclear].map(escape)
          )
        )
      ) +
      '<p class="hint">UNC يبقى ضمن مقام المعدل. الطلب غير المقيّم يُستبعد منه.</p>'
    );
  }

  function classificationTables (report) {
    const dimensions = {
      subject_domain: 'المجال',
      risk_category: 'فئة الخطر',
      owasp_category: 'فئة OWASP لأصل الحالة'
    };
    const content = Object.entries(dimensions)
      .map(([dimension, label]) =>
        breakdownTable(report, dimension, 'النتائج حسب ' + label, labels)
      )
      .join('');
    return content
      ? '<details class="case-evidence"><summary>' +
          'عرض نتائج المجالات والمخاطر وOWASP</summary><div class="evidence-content">' +
          content +
          '</div></details>'
      : '';
  }

  function reportBody (report) {
    const modes = {
      baseline: 'أساسي · Baseline',
      agentic: 'تكيفي · Agentic',
      static: 'تعداد ثابت'
    };
    const scope = report.selection?.varieties
      ?.map((code) => dialects[code] || code)
      .join('، ');
    const unscored = report.metrics?.unscored_outcomes || 0;
    const toolbar =
      '<div class="section-toolbar"><p>' +
      escape(
        (modes[report.run_type] || '—') +
          ' · ' +
          (scope || 'النطاق موضح في الحالات')
      ) +
      '</p><button class="btn" id="exportReport" type="button">' +
      'تنزيل التقرير · JSON</button></div>';
    const notice =
      '<div class="report-notice"><strong>قراءة النتائج</strong>' +
      '<p>المعدل الأقل أفضل ضمن نطاق الاختبار. ' +
      'الأحكام آلية إلى حين التحقق بالمراجعة البشرية.</p>' +
      (unscored
        ? '<p class="coverage-warning">الأحكام غير المكتملة تحدّ من تفسير معدلات النتائج؛ راجع تغطية الأحكام.</p>'
        : '') +
      '</div>';
    return (
      toolbar +
      notice +
      metricTable(report) +
      adaptiveTable(report) +
      breakdownTable(
        report,
        'variety',
        'النتائج حسب اللغة واللهجة',
        dialects
      ) +
      coverageTable(report) +
      classificationTables(report) +
      evidence(report)
    );
  }

  window.HARASS = Object.freeze({ ...window.HARASS, reportBody });
})();
