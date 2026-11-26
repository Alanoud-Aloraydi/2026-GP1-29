/* Attempt transcripts, verdict evidence and evidence pagination. */
import { catalogue, html } from '../core/ui.js';

const field = (label, value, sample = false) =>
  html`<dt>${label}</dt><dd ${sample && html`class="sample"`}>${value}</dd>`;

function failureReason (outcome) {
  if (outcome.submission_uncertain) return 'انقطع التنفيذ قبل تثبيت النتيجة؛ حالة الإرسال غير مؤكدة.';
  if (outcome.error?.includes('abstained')) return 'امتنع المحكّم عن الحكم لأن الرد ملتبس.';
  // Outcomes stored before technical errors were classified name it in the text.
  if (outcome.technical_error === 'timeout' || outcome.error?.includes('configured execution timeout')) {
    return 'انتهت المهلة قبل اكتمال الحكم.';
  }
  if (outcome.technical_error === 'invalid_judge_output') return 'تعذّر قراءة حكم صالح من رد المحكّم.';
  return 'تعذّر إكمال المحاولة بسبب خطأ تقني.';
}

function recipe (variant) {
  const parts = [
    ['القالب', variant.template_name || 'دون قالب'],
    ['التحويلات', variant.transform_names?.join(', ') || 'دون تحويل'],
    ['الاستراتيجيات الفعلية', variant.effective_strategies?.join(', ') || '—'],
    ['المراجعة', variant.review_status || '—']
  ];
  return html`<p class="hint">${parts.map(([label, value]) => `${label}: ${value}`).join(' · ')}</p>`;
}

function attempt (outcome) {
  const transcript = outcome.transcript || {};
  const variant = outcome.variant || {};
  const requests = outcome.judge_requests || [];
  const verdict = outcome.error
    ? 'غير محسوم'
    : [outcome.attack_outcome_label, outcome.response_category_label].filter(Boolean).join(' · ');
  return html`
    <article class="evidence-attempt">
      <h3>${outcome.attempt_number === 0 ? 'الطلب الأصلي' : `المحاولة ${outcome.attempt_number}`}</h3>
      <p><strong>الحكم:</strong> ${verdict || 'غير محسوم'}</p>
      <dl>
        ${field('الطلب المرسل', transcript.sent_prompt || variant.sent_prompt || outcome.original_prompt, true)}
        ${field('رد النموذج', transcript.response || 'لا يوجد رد محفوظ', true)}
        ${field('تعليل المحكّم', transcript.category_rationale || 'لا يوجد تعليل محفوظ')}
        ${outcome.error && field('سبب عدم اكتمال الحكم', failureReason(outcome))}
        ${outcome.elapsed_seconds != null && field('مدة المحاولة', `${Math.round(outcome.elapsed_seconds)} ثانية`)}
        ${requests.length > 0 && field('استدعاءات المحكّم', requests.length)}
        ${transcript.attack_rationale && field('تعليل نجاح الاختراق', transcript.attack_rationale)}
      </dl>
      ${outcome.attempt_number !== 0 && recipe(variant)}
    </article>`;
}

export function evidence (report) {
  if (report.evidence_paged) {
    return html`<section id="attemptEvidence" aria-live="polite"></section>`;
  }
  const cases = Object.entries(Object.groupBy(report.outcomes, (outcome) => outcome.case_id));
  return html`
    <section>
      <h2>تفاصيل الحالات والأدلة</h2>
      <p class="hint">افتح الحالة لعرض الطلب والرد وتعليل المحكّم. قد تتضمن النصوص محتوى حساسًا.</p>
      ${cases.map(([caseId, outcomes]) => html`
        <details class="case-evidence">
          <summary>
            <bdi>${caseId}</bdi><span>${catalogue.axes[outcomes[0].axis]} · محاولات ظاهرة: ${outcomes.length}</span>
          </summary>
          <div class="evidence-content">${outcomes.map(attempt)}</div>
        </details>`)}
    </section>`;
}

export function evidencePage (page) {
  const first = page.total ? page.offset + 1 : 0;
  const last = page.offset + page.items.length;
  return html`
    ${evidence({ outcomes: page.items })}
    <div class="section-toolbar">
      <p>المحاولات ${first}–${last} من ${page.total}</p>
      <button type="button" class="btn" id="evidencePrevious" ${page.offset === 0 && 'disabled'}>السابق</button>
      <button type="button" class="btn" id="evidenceNext" ${last >= page.total && 'disabled'}>التالي</button>
    </div>`;
}
