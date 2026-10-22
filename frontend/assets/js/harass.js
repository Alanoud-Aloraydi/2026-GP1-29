(() => {
  "use strict";

  const dialects = {
    MSA: "الفصحى",
    NAJ: "النجدية",
    HIJ: "الحجازية",
    EGY: "المصرية",
    LEV: "الشامية",
  };
  const axes = { AT: "الهجمات الخصومية", OR: "الرفض المفرط" };
  const statuses = {
    pending: "قيد الانتظار",
    running: "جارٍ التقييم",
    completed: "اكتمل التقييم",
    failed: "تعذّر إكمال التقييم",
    cancelled: "أُلغي التقييم",
    connected: "اتصال ناجح",
    not_tested: "لم يُختبر",
    testing: "جارٍ الاختبار",
  };
  const labels = {
    DIN: "الدين والشريعة",
    TBB: "الطب والصحة",
    SIY: "السياسة والشؤون العامة",
    IJT: "المجتمع والعلاقات",
    HSB: "الحوسبة والأمن السيبراني",
    VIO: "العنف والضرر",
    HAT: "الكراهية والتمييز",
    PRV: "الخصوصية",
    FRD: "الاحتيال",
    MIS: "المعلومات المضللة",
    CRM: "الاعتداء على الممتلكات والأنظمة",
    LLM01: "حقن التعليمات",
    LLM02: "كشف معلومات حساسة",
    LLM07: "معلومات مضللة",
    LLM08: "كشف سياق مخفي",
    NAP: "لا ينطبق",
  };
  const entities = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  };

  function escape(value) {
    return String(value ?? "").replace(
      /[&<>"']/g,
      (character) => entities[character],
    );
  }

  function date(value) {
    return value
      ? new Date(value).toLocaleString("ar-SA-u-ca-gregory", {
          dateStyle: "medium",
          timeStyle: "short",
        })
      : "—";
  }

  function mountShell(publicPage) {
    const header = document.querySelector("[data-shell-header]");
    if (!header) return;
    const navigation = [
      ["dashboard.html", "نظرة عامة"],
      ["connections.html", "اتصالات النماذج"],
      ["evaluation-setup.html", "تقييم جديد"],
      ["history.html", "سجل التقييمات"],
    ];
    const brand =
      '<a class="brand" href="' +
      (publicPage ? "index.html" : "dashboard.html") +
      '"><img src="assets/images/harass-logo.png" alt=""><span>HARASS</span></a>';
    const menu = publicPage
      ? ""
      : '<nav class="main-nav" aria-label="التنقل الرئيسي">' +
        navigation
          .map(([path, label]) => '<a href="' + path + '">' + label + "</a>")
          .join("") +
        "</nav>";
    const actions = publicPage
      ? link("login.html", "تسجيل الدخول") + link("signup.html", "إنشاء حساب")
      : "<span data-user-name></span>" +
        '<button class="btn btn-sm" data-logout type="button">تسجيل الخروج</button>';
    header.className = publicPage ? "public-header" : "app-header";
    header.innerHTML =
      '<div class="container">' +
      brand +
      menu +
      '<div class="header-actions">' +
      actions +
      "</div></div>";
    const footer = document.querySelector("[data-shell-footer]");
    footer.innerHTML =
      '<div class="container"><p>حَرَس · تقييم سلامة النماذج العربية</p>' +
      "<p>© 2026 HARASS</p></div>";
  }

  function busy(button, loading) {
    button.disabled = loading;
    button.classList.toggle("btn-loading", loading);
  }

  function showError(message) {
    const box = document.getElementById("pageError");
    if (!box) return;
    box.textContent = message;
    box.hidden = false;
    box.focus();
  }

  function clearError() {
    const box = document.getElementById("pageError");
    if (!box) return;
    box.hidden = true;
    box.textContent = "";
  }

  function safeReturn() {
    const destination = new URLSearchParams(location.search).get("return");
    const allowedPages = [
      "dashboard.html",
      "connections.html",
      "model-configuration.html",
      "evaluation-setup.html",
      "evaluation-run.html",
      "history.html",
    ];
    return destination &&
      !destination.includes("#") &&
      allowedPages.includes(destination.split("?")[0])
      ? destination
      : "dashboard.html";
  }

  function link(path, label) {
    return (
      '<a class="btn btn-sm" href="' +
      escape(path) +
      '">' +
      escape(label) +
      "</a>"
    );
  }

  function empty(title, description, path, label) {
    return (
      '<div class="empty-state"><h2>' +
      escape(title) +
      "</h2><p>" +
      escape(description) +
      "</p>" +
      (path ? link(path, label) : "") +
      "</div>"
    );
  }

  function status(value) {
    return (
      '<span class="status-label status-' +
      escape(value) +
      '">' +
      escape(statuses[value] || value) +
      "</span>"
    );
  }

  function tableRow(label, cells) {
    return (
      '<tr><th scope="row"><bdi>' +
      escape(label) +
      "</bdi></th>" +
      cells.map((content) => "<td>" + content + "</td>").join("") +
      "</tr>"
    );
  }

  // Rows contain markup produced here; escape all API values before inserting them.
  function table(caption, columns, rows) {
    const headings = columns.map(
      (column) => '<th scope="col">' + escape(column) + "</th>",
    );
    return (
      '<div class="table-region" role="region" tabindex="0" aria-label="' +
      escape(caption) +
      '"><table><caption>' +
      escape(caption) +
      "</caption><thead><tr>" +
      headings.join("") +
      "</tr></thead><tbody>" +
      rows.join("") +
      "</tbody></table></div>"
    );
  }

  function runTable(runs, caption = "تقييمات حسابك") {
    return table(
      caption,
      ["النموذج", "تاريخ البدء", "الحالة", "التقرير"],
      runs.map((run) =>
        tableRow(run.target_model, [
          escape(date(run.created_at)),
          status(run.status),
          link(
            "evaluation-run.html?run_id=" + encodeURIComponent(run.run_id),
            run.status === "completed" ? "فتح التقرير" : "عرض التقييم",
          ),
        ]),
      ),
    );
  }

  function runHeading(run) {
    return (
      '<div class="report-heading"><div><h2><bdi>' +
      escape(run.target_model) +
      "</bdi></h2>" +
      runTimes(run) +
      "</div>" +
      status(run.status) +
      "</div>"
    );
  }

  function runTimes(run) {
    const rows = [
      ["أُنشئ", run.created_at],
      ["بدأ التنفيذ", run.started_at],
      ["انتهى", run.finished_at],
    ];
    if (run.started_at) {
      const seconds = Math.max(
        0,
        Math.floor(
          ((run.finished_at ? new Date(run.finished_at) : new Date()) -
            new Date(run.started_at)) /
            1000,
        ),
      );
      rows.push([
        "الوقت منذ بدء التنفيذ",
        Math.floor(seconds / 3600) +
          " س " +
          Math.floor((seconds % 3600) / 60) +
          " د",
      ]);
    }
    const events = {
      created: "أُنشئ",
      started: "بدأ",
      suspended: "توقف",
      resumed: "استؤنف",
      completed: "اكتمل",
      failed: "فشل",
      cancelled: "أُلغي",
    };
    return (
      '<dl class="run-times">' +
      rows
        .filter(([, value]) => value)
        .map(
          ([label, value]) =>
            "<div><dt>" +
            label +
            "</dt><dd>" +
            escape(label === "الوقت منذ بدء التنفيذ" ? value : date(value)) +
            "</dd></div>",
        )
        .join("") +
      "</dl>" +
      (run.lifecycle_events?.length
        ? "<details><summary>سجل التشغيل</summary><ol>" +
          run.lifecycle_events
            .map(
              (event) =>
                "<li>" +
                escape(events[event.event] || event.event) +
                " · " +
                escape(date(event.at)) +
                "</li>",
            )
            .join("") +
          "</ol></details>"
        : "")
    );
  }

  function rate(metric) {
    return metric?.rate == null
      ? "لا توجد نتائج محسومة"
      : (metric.rate * 100).toFixed(1) +
          "% · " +
          metric.count +
          " من " +
          metric.total;
  }

  function runProgress(run) {
    const total = Math.max(0, Number(run.total_cases) || 0);
    const completed = Math.min(
      total,
      Math.max(0, Number(run.completed_cases) || 0),
    );
    const percent = total ? Math.floor((completed / total) * 100) : 0;
    return (
      '<div class="run-progress-row"><label for="evaluationProgress">' +
      (total
        ? "الحالات المكتملة: " + completed + " من " + total
        : run.status === "running"
          ? "جارٍ تجهيز الحالات"
          : "لم يبدأ تنفيذ الحالات") +
      '</label><progress id="evaluationProgress" max="' +
      (total || 1) +
      '" value="' +
      completed +
      '">' +
      percent +
      "%</progress>" +
      '<p class="hint">المحاولات المحفوظة: ' +
      escape(run.completed_attempts || 0) +
      "</p>" +
      (run.worker_available === false &&
      ["pending", "running"].includes(run.status)
        ? '<p class="coverage-warning">العامل غير متصل. سيستأنف التنفيذ عند تشغيله.</p>'
        : "") +
      "</div>"
    );
  }

  function pageControls(offset, total, prefix, limit = 50) {
    if (total <= limit) return "";
    return (
      '<div class="report-actions"><button type="button" class="btn btn-secondary" id="' +
      prefix +
      'Previous"' +
      (offset ? "" : " disabled") +
      ">السابق</button><span>" +
      (offset + 1) +
      "–" +
      Math.min(offset + limit, total) +
      " من " +
      total +
      '</span><button type="button" class="btn btn-secondary" id="' +
      prefix +
      'Next"' +
      (offset + limit < total ? "" : " disabled") +
      ">التالي</button></div>"
    );
  }

  function metricCell(metric, confidence = false) {
    let content = escape(rate(metric));
    if (!confidence) return content;
    const interval = metric?.clustered_95;
    const description =
      interval && interval[1] > interval[0]
        ? "فترة 95% مجمعة بحسب الطلب: " +
          (interval[0] * 100).toFixed(1) +
          "%–" +
          (interval[1] * 100).toFixed(1) +
          "%"
        : "فترة الثقة المجمعة غير متاحة لهذه النتيجة.";
    return content + '<p class="hint">' + escape(description) + "</p>";
  }

  function axisMetric(metrics, axis) {
    return axis === "AT"
      ? metrics?.adversarial?.attack_success
      : metrics?.over_refusal?.over_refusal;
  }

  function metricTable(report) {
    const adaptive = report.run_type === "agentic";
    const available = Object.keys(axes).filter(
      (axis) =>
        axisMetric(report.primary_metrics, axis) ||
        report.outcomes.some((outcome) => outcome.axis === axis),
    );
    const rows = available.map((axis) => {
      const cells = [
        metricCell(axisMetric(report.primary_metrics, axis), true),
      ];
      if (adaptive)
        cells.push(metricCell(axisMetric(report.baseline_metrics, axis), true));
      return tableRow(axes[axis], cells);
    });
    const columns = [
      "المحور",
      adaptive ? "المحاولات التكيفية" : "الاختبار الأساسي",
    ];
    if (adaptive) columns.push("الطلبات الأصلية للمقارنة");
    return table(
      adaptive
        ? "مقارنة المحاولات مع الطلبات الأصلية"
        : "نتائج الطلبات الأصلية",
      columns,
      rows,
    );
  }

  function adaptiveTable(report) {
    if (report.run_type !== "agentic" || !report.adaptive) return "";
    const rows = Object.entries(report.adaptive).map(([axis, summary]) => {
      const point = summary.defect_within_k?.[report.attempt_budget];
      return tableRow(axes[axis] || axis, [
        escape(summary.defects_detected + " من " + summary.cases),
        escape(summary.attempts_submitted),
        escape(point?.undetermined ?? "—"),
      ]);
    });
    return (
      table(
        "اكتشاف الخلل على مستوى الحالة",
        [
          "المحور",
          "حالات اكتُشف فيها خلل",
          "المحاولات المسجلة",
          "حالات غير محسومة",
        ],
        rows,
      ) +
      '<p class="hint">الاكتشاف خلال ' +
      escape(report.attempt_budget) +
      " محاولات كحد أقصى لكل حالة؛ يختلف عن معدل نجاح المحاولات المفردة.</p>"
    );
  }

  function breakdownTable(report, dimension, caption, names) {
    const metrics = report.primary_metrics || {};
    const attacks = metrics.adversarial_breakdowns?.[dimension] || {};
    const refusals = metrics.over_refusal_breakdowns?.[dimension] || {};
    const keys = [
      ...new Set([...Object.keys(attacks), ...Object.keys(refusals)]),
    ];
    if (!keys.length) return "";
    return table(
      caption,
      ["التصنيف", "نجاح الهجوم · AT", "الرفض المفرط · OR"],
      keys.map((key) =>
        tableRow(names[key] || key, [
          metricCell(attacks[key]?.attack_success),
          metricCell(refusals[key]?.over_refusal),
        ]),
      ),
    );
  }

function coverageTable(report) {
  const headers = [
    "المحور",
    "المحاولات المسجلة",
    "أحكام نجاح الهجوم المتاحة",
    "تصنيفات الرد المتاحة",
    "حالات لم تكتمل كل أحكامها",
    "ردود غير مفهومة · UNC",
  ];

  const hint =
    '<p class="hint">لكل مقياس مقام مستقل: ASR يستخدم أحكام نجاح الهجوم المتاحة، ' +
    "ومعدل الرفض يستخدم تصنيفات الرد المتاحة. " +
    "قد تدخل الحالة في أحد المقياسين فقط. " +
    "UNC يبقى ضمن مقام مقاييس التصنيف. " +
    "«غير متاح» يعني أن التقرير القديم لا يحفظ هذا العدد.</p>";

  if (report.coverage) {
    const rows = Object.entries(report.coverage).map(([axis, counts]) =>
      tableRow(axes[axis], [
        escape(counts.submitted),
        axis === "AT"
          ? escape(counts.attack_scored ?? "غير متاح")
          : "لا ينطبق",
        escape(counts.category_scored ?? "غير متاح"),
        escape(counts.unscored),
        escape(counts.unclear),
      ]),
    );

    return table("تغطية الأحكام", headers, rows) + hint;
  }

  const baseline = report.run_type === "baseline";
  const outcomes = (report.outcomes || []).filter(
    (outcome) => (outcome.variant_name === "baseline") === baseline,
  );

  const usable = (outcome) =>
    !outcome.technical_error && !outcome.submission_uncertain;

  const rows = Object.keys(axes).flatMap((axis) => {
    const items = outcomes.filter((outcome) => outcome.axis === axis);
    if (!items.length) return [];

    const attackScored = items.filter(
      (outcome) =>
        usable(outcome) && outcome.attack_succeeded != null,
    ).length;

    const categoryScored = items.filter(
      (outcome) =>
        usable(outcome) && outcome.response_category != null,
    ).length;

    const missing = items.filter(
      (outcome) =>
        outcome.error ||
        !outcome.response_category ||
        (axis === "AT" && outcome.attack_succeeded == null),
    ).length;

    const unclear = items.filter(
      (outcome) =>
        usable(outcome) && outcome.response_category === "UNC",
    ).length;

    return [
      tableRow(axes[axis], [
        escape(items.length),
        axis === "AT" ? escape(attackScored) : "لا ينطبق",
        escape(categoryScored),
        escape(missing),
        escape(unclear),
      ]),
    ];
  });

  return table("تغطية الأحكام", headers, rows) + hint;
}

  function classificationTables(report) {
    const dimensions = {
      subject_domain: "المجال",
      risk_category: "فئة الخطر",
      owasp_category: "فئة OWASP لأصل الحالة",
    };
    const content = Object.entries(dimensions)
      .map(([dimension, label]) =>
        breakdownTable(report, dimension, "النتائج حسب " + label, labels),
      )
      .join("");
    return content
      ? '<details class="case-evidence"><summary>' +
          'عرض نتائج المجالات والمخاطر وOWASP</summary><div class="evidence-content">' +
          content +
          "</div></details>"
      : "";
  }

  function evidenceField(label, value, sample = false) {
    return (
      "<dt>" +
      escape(label) +
      "</dt><dd" +
      (sample ? ' class="sample"' : "") +
      ">" +
      escape(value) +
      "</dd>"
    );
  }

  function attemptEvidence(outcome) {
    const transcript = outcome.transcript || {};
    const variant = outcome.variant || {};
        const targetMetadata = transcript.target_metadata || {};
    const finishReasons = {
      stop: "انتهى الرد بصورة طبيعية",
      length: "وصل إلى حد التوكنز؛ قد يكون الرد ناقصًا",
      content_filter: "توقف بسبب تصفية المحتوى",
      tool_calls: "توقف لطلب استخدام أداة",
    };
    const tokenLabels = {
      input_tokens: "توكنز الإدخال",
      output_tokens: "توكنز الإخراج، بما فيها التفكير إن وُجد",
      total_tokens: "إجمالي التوكنز",
      reasoning_tokens: "توكنز التفكير",
      cached_tokens: "توكنز الإدخال المخزنة مؤقتًا",
    };
    const targetFields =
      evidenceField(
        "سبب توقف النموذج",
        finishReasons[targetMetadata.finish_reason] ||
          targetMetadata.finish_reason ||
          "غير متاح في بيانات هذا التقرير",
      ) +
      Object.entries(targetMetadata)
        .filter(([key]) => key.startsWith("token_usage_"))
        .map(([key, value]) => {
          const name = key.slice("token_usage_".length);
          return evidenceField(
            tokenLabels[name] || "إحصائية إضافية للتوكنز",
            typeof value === "object" ? JSON.stringify(value) : value,
          );
        })
        .join("");
    const title =
      outcome.attempt_number === 0
        ? "الطلب الأصلي"
        : "المحاولة " + outcome.attempt_number;
    const verdict = outcome.error
      ? "غير محسوم"
      : [outcome.attack_outcome_label, outcome.response_category_label]
          .filter(Boolean)
          .join(" · ");
    const fields =
      targetFields +
      evidenceField(
        "الطلب المرسل",
        transcript.sent_prompt ||
          variant.sent_prompt ||
          outcome.original_prompt,
        true,
      ) +
      evidenceField(
        "رد النموذج",
        transcript.response || "لا يوجد رد محفوظ",
        true,
      ) +
      evidenceField(
        "تعليل المحكّم",
        transcript.category_rationale || "لا يوجد تعليل محفوظ",
      ) +
      (outcome.error
        ? evidenceField("سبب عدم اكتمال الحكم", failureReason(outcome))
        : "") +
      (outcome.elapsed_seconds != null
        ? evidenceField(
            "مدة المحاولة",
            Math.round(outcome.elapsed_seconds) + " ثانية",
          )
        : "") +
      (outcome.judge_requests?.length
        ? evidenceField("استدعاءات المحكّم", outcome.judge_requests.length) +
          evidenceField(
            "ردود المحكّم المقتطعة",
            outcome.judge_requests.filter(
              (request) => request.finish_reason === "length",
            ).length,
          )
        : "") +
      (transcript.attack_rationale
        ? evidenceField("تعليل نجاح الهجوم", transcript.attack_rationale)
        : "");
    const recipe =
      outcome.attempt_number === 0
        ? ""
        : '<p class="hint">' +
          escape(
            "القالب: " +
              (variant.template_name || "دون قالب") +
              " · التحويلات: " +
              (variant.transform_names?.join(", ") || "دون تحويل") +
              " · الاستراتيجيات الفعلية: " +
              (variant.effective_strategies?.join(", ") || "—") +
              " · المراجعة: " +
              (variant.review_status || "—"),
          ) +
          "</p>";
    return (
      '<article class="evidence-attempt"><h3>' +
      escape(title) +
      "</h3><p><strong>الحكم:</strong> " +
      escape(verdict || "غير محسوم") +
      "</p><dl>" +
      fields +
      "</dl>" +
      recipe +
      "</article>"
    );
  }
function failureReason(outcome) {
  if (outcome.submission_uncertain)
    return "انقطع التنفيذ قبل تثبيت النتيجة؛ حالة الإرسال غير مؤكدة.";

  if (outcome.needs_review)
    return "يحتاج الحكم إلى مراجعة بشرية بسبب انخفاض ثقة المحكّم.";

  if (outcome.error?.includes("no majority"))
    return "لم تتفق أغلبية أصوات المحكّم.";

  if (
    outcome.technical_error === "timeout" ||
    outcome.error?.includes("configured execution timeout")
  )
    return "انتهت المهلة قبل اكتمال الحكم.";

  if (outcome.technical_error === "invalid_judge_output")
    return "تعذّر قراءة حكم صالح من رد المحكّم.";

  return "تعذّر إكمال المحاولة بسبب خطأ تقني.";
}

  function evidence(report) {
    if (report.evidence_paged)
      return '<section id="attemptEvidence" class="report-section" aria-live="polite"></section>';
    const groups = Object.groupBy(
      report.outcomes,
      (outcome) => outcome.case_id,
    );
    const cases = Object.entries(groups).map(
      ([identifier, outcomes]) =>
        '<details class="case-evidence"><summary><bdi>' +
        escape(identifier) +
        "</bdi><span>" +
        escape(axes[outcomes[0].axis]) +
        " · محاولات ظاهرة: " +
        outcomes.length +
        '</span></summary><div class="evidence-content">' +
        outcomes.map(attemptEvidence).join("") +
        "</div></details>",
    );
    return (
      '<section class="report-section"><h2>تفاصيل الحالات والأدلة</h2>' +
      '<p class="hint">افتح الحالة لعرض الطلب والرد وتعليل المحكّم. ' +
      "قد تتضمن النصوص محتوى حساسًا.</p>" +
      cases.join("") +
      "</section>"
    );
  }

  function evidencePage(page) {
    const first = page.total ? page.offset + 1 : 0;
    const last = page.offset + page.items.length;
    return (
      evidence({ outcomes: page.items }) +
      '<div class="section-toolbar"><p>' +
      escape("المحاولات " + first + "–" + last + " من " + page.total) +
      '</p><button type="button" class="btn" id="evidencePrevious" ' +
      (page.offset === 0 ? "disabled" : "") +
      ">السابق</button>" +
      '<button type="button" class="btn" id="evidenceNext" ' +
      (last >= page.total ? "disabled" : "") +
      ">التالي</button></div>"
    );
  }

  function reportBody(report) {
    const modes = {
      baseline: "أساسي · Baseline",
      agentic: "تكيفي · Agentic",
      static: "تعداد ثابت",
    };
    const scope = report.selection?.varieties
      ?.map((code) => dialects[code] || code)
      .join("، ");
    const unscored = report.metrics?.unscored_outcomes || 0;
    const toolbar =
      '<div class="section-toolbar"><p>' +
      escape(
        (modes[report.run_type] || "—") +
          " · " +
          (scope || "النطاق موضح في الحالات"),
      ) +
      '</p><button class="btn" id="exportReport" type="button">' +
      "تنزيل التقرير · JSON</button></div>";
    const notice =
      '<div class="report-notice"><strong>قراءة النتائج</strong>' +
      "<p>المعدل الأقل أفضل ضمن نطاق الاختبار. " +
      "الأحكام آلية إلى حين التحقق بالمراجعة البشرية.</p>" +
      (unscored
        ? '<p class="coverage-warning">الأحكام غير المكتملة تحدّ من تفسير معدلات النتائج؛ راجع تغطية الأحكام.</p>'
        : "") +
      "</div>";
    return (
      toolbar +
      notice +
      metricTable(report) +
      adaptiveTable(report) +
      breakdownTable(report, "variety", "النتائج حسب اللغة واللهجة", dialects) +
      coverageTable(report) +
      classificationTables(report) +
      evidence(report)
    );
  }

  window.HARASS = Object.freeze({
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
    runTable,
    runHeading,
    runProgress,
    pageControls,
    reportBody,
    evidencePage,
  });
})();
