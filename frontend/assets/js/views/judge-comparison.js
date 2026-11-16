/* Judge benchmark comparison markup; every API value is escaped here. */
(() => {
  'use strict';
  const { escape, date, table, tableRow, dialects } = window.HARASS;
  const categories = ['FUL', 'PRF', 'REF', 'UNC'];
  // Facts about each judge model that its reports do not carry.
  const catalogue = {
    'LiquidAI/d1-2B': {
      size: '1.9B',
      base: 'LFM3-VL-2B',
      license: 'ترخيص خاص (LiquidAI)',
      note: 'نموذج قرارات عام يعطي احتمالات لكل خيار.'
    },
    'Omartificial-Intelligence-Space/ara-jev-Faisal': {
      size: '4.7B',
      base: 'Qwen3.5-4B',
      license: 'CC BY-NC 4.0 (بحثي فقط)',
      note: 'نموذج عربي لقرارات الخيارات؛ يصنّف فئات الرد الأربع. ترخيصه لا يسمح بالاستخدام التجاري.'
    },
    'Qwen/Qwen3Guard-Gen-4B': {
      size: '4.4B',
      base: 'Qwen3-4B',
      license: 'Apache 2.0',
      note: 'المحكّم المعتمد في المنتج. نموذج مراقبة محتوى يحكم على الضرر العام، ورفضه نعم أو لا فلا يميّز PRF وUNC.'
    },
    'Qwen/Qwen3Guard-Gen-0.6B': {
      size: '0.75B',
      base: 'Qwen3-0.6B',
      license: 'Apache 2.0',
      note: 'النسخة الصغيرة من Qwen3Guard: أسرع بكثير وأضعف في استرجاع الاختراقات.'
    },
    'Qwen/Qwen3Guard-Gen-0.6B then Qwen/Qwen3Guard-Gen-4B': {
      size: '0.75B + 4.4B',
      base: 'Qwen3-0.6B و Qwen3-4B',
      license: 'Apache 2.0',
      note: 'يحكم الصغير أولًا، ويُصعَّد للكبير ما لم يؤكد الصغير اختراقًا في محور مقاومة الاختراق.'
    },
    'mistralai/Shieldstral-1.0-3B': {
      size: '3.8B',
      base: 'Ministral-3-3B',
      license: 'Apache 2.0',
      note: 'يحكم بأسئلة نعم أو لا مكتوبة بحرية ويعطي احتمالًا حقيقيًا لكل سؤال؛ جُرّب كمرشح ولم يتفوق على Qwen3Guard.'
    },
    'deepseek-r1:8b': {
      size: '8.2B',
      base: 'DeepSeek-R1-0528-Qwen3-8B',
      license: 'MIT',
      precision: 'Q4_K_M (Ollama)',
      note: 'نموذج استدلال محلي بثلاثة أصوات لكل حالة، وكان محكّم المنتج قبل الانتقال إلى Qwen3Guard.'
    }
  };
  const verdicts = ['TRUE', 'FALSE'];
  // Development cases were used to choose a judge; test cases were kept
  // unseen and run once.
  const splits = { dev: 'تطوير', test: 'اختبار', all: 'الكل' };
  const splitLabel = (split) => splits[split] || split;

  function number (value, digits = 2) {
    return typeof value === 'number'
      ? '<span class="number">' + value.toFixed(digits) + '</span>'
      : '—';
  }

  function interval (score) {
    const range = score?.kappa_interval;
    return Array.isArray(range) && range.length === 2
      ? number(score.kappa) +
        ' <small class="number">(' +
        range[0].toFixed(2) +
        '–' +
        range[1].toFixed(2) +
        ')</small>'
      : number(score?.kappa);
  }

  function count (value) {
    return '<span class="number">' + escape(value ?? '—') + '</span>';
  }

  function perHour (value) {
    return typeof value === 'number' ? count(Math.round(value)) : '—';
  }

  function percent (value) {
    return typeof value === 'number'
      ? '<span class="number">' + (value * 100).toFixed(0) + '%</span>'
      : '—';
  }

  function verdictLabel (passes) {
    if (typeof passes !== 'boolean') return '—';
    return passes
      ? '<span class="status-label status-completed">يحقق</span>'
      : '<span class="status-label status-failed">لا يحقق</span>';
  }

  // The combined judge reports its parts joined by an English word.
  const joined = (text) => String(text).replace(' then ', ' ثم ');

  function sizeAndPrecision (report) {
    const known = catalogue[report.judge_model] || {};
    return [known.size, report.quantization || known.precision]
      .filter(Boolean)
      .map((part) => '<bdi>' + escape(joined(part)) + '</bdi>')
      .join(' · ') || '—';
  }

  function summaryTable (reports) {
    return (
      '<section class="card">' +
      table(
        'تقارير المحكّمين',
        [
          ['المحكّم', 'النموذج الذي يحكم على ردود النماذج المقيَّمة.'],
          ['الحجم والدقة', 'عدد معاملات النموذج، وعدد البتات التي يُخزَّن بها كل معامل.'],
          ['الترخيص', 'شروط استخدام النموذج.'],
          ['المجموعة', 'حالات القياس: تطوير أو اختبار مخفي، وعدد الحالات × المحاولات.'],
          ['الاتفاق مع البشر في الرفض المفرط (kappa)', 'اتفاقه مع الإنسان في تصنيف الرد بعد استبعاد الصدفة. المطلوب 0.70 فأكثر.'],
          ['الاتفاق مع البشر في الاختراق (kappa)', 'اتفاقه مع الإنسان في تصنيف ردود الاختراق بعد استبعاد الصدفة. المطلوب 0.70 فأكثر.'],
          ['اكتشاف الاختراقات (الاسترجاع)', 'نسبة الاختراقات الناجحة التي اكتشفها. المطلوب 0.80 فأكثر.'],
          ['حالة في الساعة', 'سرعة الحكم. المطلوب 1000 فأكثر.'],
          ['بوابات القبول', 'يحقق إذا اجتاز الشروط الأربعة كلها.'],
          ['التفاصيل', 'التقرير الكامل لهذا القياس.']
        ],
        reports.map((report) =>
          tableRow(joined(report.judge_model), [
            sizeAndPrecision(report),
            escape(catalogue[report.judge_model]?.license || '—'),
            '<strong>' +
              escape(splitLabel(report.split)) +
              '</strong> ' +
              count(report.cases + ' × ' + report.trials),
            number(report.category_kappa?.OR),
            number(report.category_kappa?.AT),
            number(report.attack_recall),
            perHour(report.cases_per_hour),
            verdictLabel(report.passes_gate),
            '<button class="btn btn-sm btn-secondary" type="button" data-report="' +
              escape(report.report_id) +
              '">عرض</button>'
          ])
        )
      ) +
      '</section>'
    );
  }

  function gateTable (report) {
    const gate = report.gate || {};
    const rows = [
      [
        'الاتفاق مع البشر في الرفض المفرط (kappa)',
        interval(report.category?.OR),
        '≥ ' + number(gate.kappa_floor),
        gate.category_kappa_ok?.OR
      ],
      [
        'الاتفاق مع البشر في الاختراق (kappa)',
        interval(report.category?.AT),
        '≥ ' + number(gate.kappa_floor),
        gate.category_kappa_ok?.AT
      ],
      [
        'اكتشاف الاختراقات (الاسترجاع)',
        number(report.attack_success?.labels?.TRUE?.recall),
        '≥ ' + number(gate.attack_recall_floor),
        gate.attack_recall_ok
      ],
      [
        'الحالات في الساعة',
        perHour(report.cost?.cases_per_hour),
        '≥ ' + count(gate.throughput_floor_per_hour),
        gate.throughput_ok
      ]
    ];
    return table(
      'بوابات القبول',
      ['المقياس', 'القيمة', 'الحد الأدنى', 'النتيجة'],
      rows.map(([label, value, floor, ok]) =>
        tableRow(label, [value, floor, verdictLabel(ok)])
      )
    );
  }

  function matrix (caption, names, confusion) {
    const rows = names.map((gold) =>
      '<tr><th scope="row"><bdi>' +
      escape(gold) +
      '</bdi></th>' +
      names
        .map(
          (predicted) =>
            '<td class="' +
            'matrix-cell ' + (gold === predicted ? 'matrix-diagonal' : '') +
            '"><span class="number">' +
            escape(confusion?.[gold]?.[predicted] ?? 0) +
            '</span></td>'
        )
        .join('') +
      '</tr>'
    );
    return table(
      caption,
      ['الوسم المرجعي ↓ / حكم المحكّم →', ...names],
      rows
    );
  }

  function dialectTable (accuracy) {
    const entries = Object.entries(accuracy || {});
    if (!entries.length) return '';
    return table(
      'الدقة حسب اللهجة',
      ['اللهجة', 'الدقة'],
      entries.map(([key, value]) => tableRow(dialects[key] || key, [percent(value)]))
    );
  }

  function coverageTable (report) {
    const coverage = report.coverage || {};
    const rows = [
      ['رفض زائد أو تصنيف بلا حكم', coverage.unjudged_category],
      ['اختراق بلا حكم (امتناع أو فشل)', coverage.unjudged_attack],
      ['وسوم مرجعية ممتنعة', coverage.gold_abstain],
      ['ردود مقطوعة', coverage.gold_truncated]
    ];
    return table(
      'التغطية',
      ['البند', 'العدد'],
      rows.map(([label, value]) =>
        tableRow(label, [count(value)])
      )
    );
  }

  function costTable (report) {
    const cost = report.cost || {};
    const stability = report.stability || {};
    const rows = [
      ['متوسط زمن الحالة (ثانية)', number(cost.mean_seconds)],
      ['نداءات المحكّم لكل حالة', number(cost.judge_calls_per_case)],
      ['أخطاء تقنية', count(cost.failures)],
      ['تغيّر التصنيف بين المحاولات', percent(stability.category_flip_rate)],
      ['تغيّر حكم الاختراق بين المحاولات', percent(stability.attack_flip_rate)]
    ];
    return table('الكلفة والثبات', ['المقياس', 'القيمة'], rows.map(([label, value]) => tableRow(label, [value])));
  }

  function judgeTable (record) {
    const known = catalogue[record.judge_model] || {};
    const judge = record.report.judge || {};
    const rows = [
      ['النموذج الأساسي', known.base],
      ['الحجم', known.size],
      ['الدقة', record.quantization || known.precision],
      ['الترخيص', known.license],
      ['إصدار النموذج', judge.revision && String(judge.revision).slice(0, 12)],
      ['عدد الأصوات لكل حالة', judge.votes],
      ['ملاحظة', known.note]
    ].filter(([, value]) => value !== undefined && value !== null && value !== '');
    return table(
      'تفاصيل المحكّم',
      ['البند', 'القيمة'],
      rows.map(([label, value]) => tableRow(label, ['<bdi>' + escape(value) + '</bdi>']))
    );
  }

  function sampleNotice (report) {
    const pairs = [
      ['الرفض المفرط', report.category?.OR?.paired],
      ['مقاومة الاختراق', report.category?.AT?.paired],
      ['نجاح الاختراق', report.attack_success?.paired]
    ]
      .map(([label, count]) => escape(label) + ': ' + escape(count ?? '—') + ' حالة')
      .join(' · ');
    return (
      '<p class="report-notice"><strong>حجم العينة المقارَنة</strong>' + pairs + '</p>'
    );
  }

  function detail (record) {
    const report = record.report;
    return (
      '<section class="card judge-detail"><div class="report-heading"><div><h2><bdi>' +
      escape(joined(record.judge_model)) +
      '</bdi></h2><p>' +
      escape(splitLabel(record.split)) +
      ' · ' +
      escape(record.cases) +
      ' حالة · ' +
      escape(record.trials) +
      ' محاولات · ' +
      escape(date(record.created_at)) +
      '</p><p>نسخة التعليمات: <bdi class="number">' +
      escape(record.rubric_fingerprint) +
      '</bdi></p></div>' +
      verdictLabel(record.passes_gate) +
      '</div>' +
      sampleNotice(report) +
      judgeTable(record) +
      gateTable(report) +
      '<div class="judge-columns">' +
      matrix('مصفوفة الالتباس: الرفض المفرط', categories, report.category?.OR?.confusion) +
      matrix('مصفوفة الالتباس: نجاح الاختراق', verdicts, report.attack_success?.confusion) +
      '</div><div class="judge-columns">' +
      dialectTable(report.accuracy_by_dialect) +
      coverageTable(report) +
      costTable(report) +
      '</div></section>'
    );
  }

  window.HARASS_JUDGES = Object.freeze({ summaryTable, detail });
})();
