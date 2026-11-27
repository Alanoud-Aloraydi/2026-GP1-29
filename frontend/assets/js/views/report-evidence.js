/* Attempt transcripts, generated prompts, verdict evidence and evidence pagination. */
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

function attempt (outcome) {
  const transcript = outcome.transcript || {};
  const requests = outcome.judge_requests || [];
  const verdict = outcome.error
    ? 'غير محسوم'
    : [outcome.attack_outcome_label, outcome.response_category_label].filter(Boolean).join(' · ');
  return html`
    <article class="evidence-attempt">
      <p><strong>الحكم:</strong> ${verdict || 'غير محسوم'}</p>
      <dl>
        ${field('الطلب المرسل', transcript.sent_prompt || outcome.original_prompt, true)}
        ${field('رد النموذج', transcript.response || 'لا يوجد رد محفوظ', true)}
        ${field('تعليل المحكّم', transcript.category_rationale || 'لا يوجد تعليل محفوظ')}
        ${outcome.error && field('سبب عدم اكتمال الحكم', failureReason(outcome))}
        ${outcome.elapsed_seconds != null && field('مدة المحاولة', `${Math.round(outcome.elapsed_seconds)} ثانية`)}
        ${requests.length > 0 && field('استدعاءات المحكّم', requests.length)}
        ${transcript.attack_rationale && field('تعليل نجاح الاختراق', transcript.attack_rationale)}
      </dl>
    </article>`;
}

export function evidence (report) {
  if (report.evidence_paged) {
    return html`<section id="attemptEvidence" aria-live="polite"></section>`;
  }
  return html`
    <section>
      <h2>تفاصيل الحالات والأدلة</h2>
      <p class="hint">افتح الحالة لعرض الطلب والرد وتعليل المحكّم. قد تتضمن النصوص محتوى حساسًا.</p>
      ${report.outcomes.map((outcome) => html`
        <details class="case-evidence">
          <summary><bdi>${outcome.case_id}</bdi><span>${catalogue.axes[outcome.axis]}</span></summary>
          <div class="evidence-content">${attempt(outcome)}</div>
        </details>`)}
    </section>`;
}

function pageToolbar (page, noun) {
  const first = page.total ? page.offset + 1 : 0;
  const last = page.offset + page.items.length;
  return html`
    <div class="section-toolbar">
      <p>${noun} ${first}–${last} من ${page.total}</p>
      <button type="button" class="btn" id="evidencePrevious" ${page.offset === 0 && 'disabled'}>السابق</button>
      <button type="button" class="btn" id="evidenceNext" ${last >= page.total && 'disabled'}>التالي</button>
    </div>`;
}

export const evidencePage = (page) =>
  html`${evidence({ outcomes: page.items })}${pageToolbar(page, 'المحاولات')}`;

const categories = { FUL: 'أجاب عن الطلب', PRF: 'أجاب جزئيًا', REF: 'رفض الطلب', UNC: 'رد غير واضح' };

// A prompt is sent only after both gates: the form review, and the safety
// judge saying it is harmless (over-refusal) or harmful if fulfilled (attack).
function gates (prompt) {
  const intended = prompt.axis === 'AT' ? !prompt.intent_safe : prompt.intent_safe;
  const safety = prompt.axis === 'AT'
    ? (prompt.intent_safe ? 'لا يضر لو نُفّذ' : 'يضر لو نُفّذ')
    : (prompt.intent_safe ? 'آمن' : 'غير آمن');
  return html`مراجعة الصياغة: ${prompt.reviewer_passed ? 'اجتازت' : 'لم تجتز'} · حكم السلامة: ${safety}
    ${!(prompt.reviewer_passed && intended) && html` · <strong>لم يُرسل</strong>`}`;
}

function verdict (prompt) {
  const outcome = prompt.outcome;
  if (!outcome) return 'لا يوجد حكم';
  const attack = prompt.axis === 'AT' && outcome.attack_succeeded != null &&
    (outcome.attack_succeeded ? 'نجح الاختراق' : 'لم ينجح الاختراق');
  return [attack, categories[outcome.response_category] || outcome.response_category].filter(Boolean).join(' · ');
}

function generated (prompt) {
  const outcome = prompt.outcome || {};
  const transforms = prompt.transform_names.map((name) =>
    catalogue.transforms.find((item) => item.name === name)?.label || name).join('، ');
  return html`
    <article class="evidence-attempt">
      <p><strong>الحكم:</strong> ${verdict(prompt)}</p>
      <dl>
        ${field('الصياغة الأولى بالفصحى', prompt.written_text, true)}
        ${field('النص باللهجة', prompt.localized_text, true)}
        ${field(transforms ? `النص المرسل بعد التحويل (${transforms})` : 'النص المرسل', prompt.sent_text, true)}
        ${prompt.objective && field('الهدف الضار المطلوب', prompt.objective, true)}
        ${field('البوابات', gates(prompt))}
        ${prompt.device && field('النمط المستخدم', html`<bdi>${prompt.device}</bdi>`)}
        ${prompt.lesson_ids.length > 0 && field('دروس قرأها الكاتب', prompt.lesson_ids.length)}
        ${prompt.attempts > 1 && field('محاولات الكتابة', prompt.attempts)}
        ${prompt.outcome && field('رد النموذج', outcome.response_text || 'لا يوجد رد محفوظ', true)}
        ${outcome.category_rationale && field('تعليل المحكّم', outcome.category_rationale)}
        ${outcome.attack_rationale && field('تعليل نجاح الاختراق', outcome.attack_rationale)}
      </dl>
    </article>`;
}

export function promptEvidencePage (page) {
  return html`
    <section>
      <h2>الطلبات المولّدة والأدلة</h2>
      <p class="hint">افتح الطلب لعرض مراحل كتابته وبواباته ورد النموذج وتعليل المحكّم. قد تتضمن النصوص محتوى حساسًا.</p>
      ${page.items.map((prompt) => html`
        <details class="case-evidence">
          <summary><bdi>${prompt.case_id}</bdi><span>${catalogue.axes[prompt.axis]} · الجولة ${prompt.round + 1}</span></summary>
          <div class="evidence-content">${generated(prompt)}</div>
        </details>`)}
    </section>
    ${pageToolbar(page, 'الطلبات')}`;
}
