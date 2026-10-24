/* Escaped attempt transcripts, verdict evidence and evidence pagination. */
(() => {
  'use strict';
  const { escape, axes } = window.HARASS;
  function evidenceField (label, value, sample = false) {
    return (
      '<dt>' +
      escape(label) +
      '</dt><dd' +
      (sample ? ' class="sample"' : '') +
      '>' +
      escape(value) +
      '</dd>'
    );
  }

  function attemptEvidence (outcome) {
    const transcript = outcome.transcript || {};
    const variant = outcome.variant || {};
    const title =
      outcome.attempt_number === 0
        ? 'الطلب الأصلي'
        : 'المحاولة ' + outcome.attempt_number;
    const verdict = outcome.error
      ? 'غير محسوم'
      : [outcome.attack_outcome_label, outcome.response_category_label]
          .filter(Boolean)
          .join(' · ');
    const fields =
      evidenceField(
        'الطلب المرسل',
        transcript.sent_prompt ||
          variant.sent_prompt ||
          outcome.original_prompt,
        true
      ) +
      evidenceField(
        'رد النموذج',
        transcript.response || 'لا يوجد رد محفوظ',
        true
      ) +
      evidenceField(
        'تعليل المحكّم',
        transcript.category_rationale || 'لا يوجد تعليل محفوظ'
      ) +
      (outcome.error
        ? evidenceField('سبب عدم اكتمال الحكم', failureReason(outcome))
        : '') +
      (outcome.elapsed_seconds != null
        ? evidenceField(
          'مدة المحاولة',
          Math.round(outcome.elapsed_seconds) + ' ثانية'
        )
        : '') +
      (outcome.judge_requests?.length
        ? evidenceField('استدعاءات المحكّم', outcome.judge_requests.length) +
          evidenceField(
            'ردود المحكّم المقتطعة',
            outcome.judge_requests.filter(
              (request) => request.finish_reason === 'length'
            ).length
          )
        : '') +
      (transcript.attack_rationale
        ? evidenceField('تعليل نجاح الهجوم', transcript.attack_rationale)
        : '');
    const recipe =
      outcome.attempt_number === 0
        ? ''
        : '<p class="hint">' +
          escape(
            'القالب: ' +
              (variant.template_name || 'دون قالب') +
              ' · التحويلات: ' +
              (variant.transform_names?.join(', ') || 'دون تحويل') +
              ' · الاستراتيجيات الفعلية: ' +
              (variant.effective_strategies?.join(', ') || '—') +
              ' · المراجعة: ' +
              (variant.review_status || '—')
          ) +
          '</p>';
    return (
      '<article class="evidence-attempt"><h3>' +
      escape(title) +
      '</h3><p><strong>الحكم:</strong> ' +
      escape(verdict || 'غير محسوم') +
      '</p><dl>' +
      fields +
      '</dl>' +
      recipe +
      '</article>'
    );
  }

  function failureReason (outcome) {
    if (outcome.submission_uncertain) { return 'انقطع التنفيذ قبل تثبيت النتيجة؛ حالة الإرسال غير مؤكدة.'; }
    if (outcome.error?.includes('no majority')) { return 'لم تتفق أغلبية أصوات المحكّم.'; }
    if (
      outcome.technical_error === 'timeout' ||
      outcome.error?.includes('configured execution timeout')
    ) { return 'انتهت المهلة قبل اكتمال الحكم.'; }
    if (outcome.technical_error === 'invalid_judge_output') { return 'تعذّر قراءة حكم صالح من رد المحكّم.'; }
    return 'تعذّر إكمال المحاولة بسبب خطأ تقني.';
  }

  function evidence (report) {
    if (report.evidence_paged) { return '<section id="attemptEvidence" class="report-section" aria-live="polite"></section>'; }
    const groups = Object.groupBy(
      report.outcomes,
      (outcome) => outcome.case_id
    );
    const cases = Object.entries(groups).map(
      ([identifier, outcomes]) =>
        '<details class="case-evidence"><summary><bdi>' +
        escape(identifier) +
        '</bdi><span>' +
        escape(axes[outcomes[0].axis]) +
        ' · محاولات ظاهرة: ' +
        outcomes.length +
        '</span></summary><div class="evidence-content">' +
        outcomes.map(attemptEvidence).join('') +
        '</div></details>'
    );
    return (
      '<section class="report-section"><h2>تفاصيل الحالات والأدلة</h2>' +
      '<p class="hint">افتح الحالة لعرض الطلب والرد وتعليل المحكّم. ' +
      'قد تتضمن النصوص محتوى حساسًا.</p>' +
      cases.join('') +
      '</section>'
    );
  }

  function evidencePage (page) {
    const first = page.total ? page.offset + 1 : 0;
    const last = page.offset + page.items.length;
    return (
      evidence({ outcomes: page.items }) +
      '<div class="section-toolbar"><p>' +
      escape('المحاولات ' + first + '–' + last + ' من ' + page.total) +
      '</p><button type="button" class="btn" id="evidencePrevious" ' +
      (page.offset === 0 ? 'disabled' : '') +
      '>السابق</button>' +
      '<button type="button" class="btn" id="evidenceNext" ' +
      (last >= page.total ? 'disabled' : '') +
      '>التالي</button></div>'
    );
  }

  window.HARASS = Object.freeze({ ...window.HARASS, evidence, evidencePage });
})();
