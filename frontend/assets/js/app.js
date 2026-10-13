(() => {
  "use strict";

  const api = window.HARASS_API;
  const view = window.HARASS;
  const page = document.body.dataset.page;
  const section =
    {
      "model-configuration": "connections",
    }[page] || page;

  function initializeNavigation() {
    document.querySelectorAll(".main-nav a").forEach((anchor) => {
      if (anchor.getAttribute("href") === section + ".html") {
        anchor.setAttribute(
          "aria-current",
          section === page ? "page" : "location",
        );
      }
    });
    window.addEventListener("pageshow", (event) => {
      if (event.persisted) location.reload();
    });
  }

  async function initializeAccount() {
    const user = await api.me();
    document.querySelectorAll("[data-user-name]").forEach((element) => {
      element.textContent = user.full_name;
    });
    document.querySelectorAll("[data-logout]").forEach((button) => {
      button.addEventListener("click", async () => {
        view.busy(button, true);
        try {
          await api.logout();
          location.href = "login.html";
        } catch {
          view.showError("تعذّر تسجيل الخروج. أعد المحاولة.");
          view.busy(button, false);
        }
      });
    });
  }

  function bindSubmit(form, action) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      view.clearError();
      if (!form.reportValidity()) return;
      const button = form.querySelector("button[type=submit]");
      view.busy(button, true);
      try {
        await action();
      } catch (error) {
        view.showError(error.message);
        if (error.activeRunId)
          document
            .getElementById("pageError")
            .insertAdjacentHTML(
              "beforeend",
              view.link(
                "evaluation-run.html?run_id=" +
                  encodeURIComponent(error.activeRunId),
                "فتح التقييم الجاري",
              ),
            );
        error.field?.focus();
      } finally {
        view.busy(button, false);
      }
    });
  }

  function formError(message, field) {
    throw Object.assign(new Error(message), { field });
  }

  function authenticationForm() {
    const form = document.getElementById("authForm");
    bindSubmit(form, async () => {
      const credentials = {
        email: form.email.value.trim(),
        password: form.password.value,
      };
      if (page === "signup") {
        if (form.confirm.value !== credentials.password) {
          formError(
            "كلمتا المرور غير متطابقتين. أعد إدخال التأكيد.",
            form.confirm,
          );
        }
        credentials.full_name = form.full_name.value.trim();
        if (credentials.full_name.length < 2) {
          formError("أدخل اسمًا بين حرفين و100 حرف.", form.full_name);
        }
      }
      try {
        await (page === "signup"
          ? api.signup(credentials)
          : api.login(credentials));
      } catch (error) {
        const messages = {
          401: "البريد الإلكتروني أو كلمة المرور غير صحيحة. راجع بياناتك ثم أعد المحاولة.",
          409: "هذا البريد مسجل بالفعل. يمكنك تسجيل الدخول بحسابك.",
        };
        throw new Error(messages[error.status] || error.message);
      }
      location.href = view.safeReturn();
    });
  }

  function connectionRows(connections) {
    return connections.map((connection) =>
      view.tableRow(connection.model_name, [
        "<bdi>" + view.escape(connection.base_url) + "</bdi>",
        view.status(connection.status) +
          (connection.status === "failed"
            ? '<p class="hint">راجع العنوان والمفتاح ثم أعد الاختبار.</p>'
            : ""),
        '<div class="row-actions"><button class="btn btn-sm" data-verify="' +
          view.escape(connection.connection_id) +
          '">اختبار الاتصال</button>' +
          view.link(
            "model-configuration.html?id=" +
              encodeURIComponent(connection.connection_id),
            "تعديل",
          ) +
          "</div>",
      ]),
    );
  }

  function bindPages(prefix, offset, load) {
    document
      .getElementById(prefix + "Previous")
      ?.addEventListener("click", () => load(Math.max(0, offset - 50)));
    document
      .getElementById(prefix + "Next")
      ?.addEventListener("click", () => load(offset + 50));
  }

  async function connectionsPage() {
    const container = document.getElementById("connections");
    let offset = 0;
    async function load() {
      view.clearError();
      try {
        const page = await api.connectionPage(offset);
        const connections = page.items;
        container.innerHTML = connections.length
          ? view.table(
              "الاتصالات المحفوظة",
              ["النموذج", "نقطة الوصول", "الحالة", "الإجراءات"],
              connectionRows(connections),
            )
          : view.empty(
              "لا توجد اتصالات بعد",
              "أضف اتصال النموذج الذي تريد تقييمه.",
              "model-configuration.html",
              "إضافة اتصال",
            );
        container.insertAdjacentHTML(
          "beforeend",
          view.pageControls(offset, page.total, "connections"),
        );
        bindPages("connections", offset, (value) => {
          offset = value;
          load();
        });
      } catch (error) {
        container.innerHTML =
          "<p>تعذّر تحميل الاتصالات.</p>" +
          '<button type="button" class="btn" data-retry>إعادة المحاولة</button>';
        view.showError(error.message);
      }
    }
    container.addEventListener("click", async (event) => {
      const button = event.target.closest("button");
      if (button?.hasAttribute("data-retry")) return load();
      if (!button?.dataset.verify) return;
      view.busy(button, true);
      try {
        await api.verifyConnection(button.dataset.verify);
        await load();
      } catch (error) {
        view.showError(error.message);
        button.textContent = "إعادة الاختبار";
      } finally {
        view.busy(button, false);
      }
    });
    await load();
  }

  function validEndpoint(value) {
    try {
      const url = new URL(value);
      return (
        ["http:", "https:"].includes(url.protocol) && Boolean(url.hostname)
      );
    } catch {
      return false;
    }
  }

  async function connectionForm() {
    const form = document.getElementById("connectionForm");
    const identifier = new URLSearchParams(location.search).get("id");
    let connectionRevision;
    form.apiKey.required = !identifier;
    if (identifier) {
      const connection = await api.getConnection(identifier);
      if (!connection) {
        view.showError("لم يعد الاتصال متاحًا. افتح قائمة الاتصالات.");
        form.hidden = true;
        return;
      }
      form.modelName.value = connection.model_name;
      connectionRevision = connection.revision;
      form.endpoint.value = connection.base_url;
      document.getElementById("apiKeyHint").textContent =
        "اترك الحقل فارغًا للإبقاء على المفتاح المحفوظ، أو أدخل مفتاحًا جديدًا.";
    }
    bindSubmit(form, async () => {
      const baseUrl = form.endpoint.value.trim();
      if (!validEndpoint(baseUrl)) {
        formError("أدخل عنوانًا يبدأ بـ http:// أو https://.", form.endpoint);
      }
      const body = {
        api_compatibility: "openai_compatible",
        base_url: baseUrl,
        model_name: form.modelName.value.trim(),
        api_key: form.apiKey.value.trim() || null,
        revision: connectionRevision,
      };
      await (identifier
        ? api.updateConnection(identifier, body)
        : api.addConnection(body));
      form.apiKey.value = "";
      location.href = "connections.html";
    });
  }

  async function evaluationForm() {
    const form = document.getElementById("evaluationForm");
    const button = document.getElementById("start");
    view.busy(button, true);
    const connections = (await api.listConnections()).filter(
      (item) => item.status === "connected",
    );
    form.connection.replaceChildren(
      new Option("اختر اتصالًا", ""),
      ...connections.map(
        (item) => new Option(item.model_name, item.connection_id),
      ),
    );
    if (!connections.length) {
      view.showError(
        "لا يوجد اتصال جاهز. أضف اتصالًا واختبره من صفحة اتصالات النماذج.",
      );
      return;
    }
    view.busy(button, false);
    bindSubmit(form, async () => {
      const varieties = Array.from(
        form.querySelectorAll("[name=variety]:checked"),
        (input) => input.value,
      );
      if (!varieties.length) {
        formError(
          "اختر لغة أو لهجة واحدة على الأقل.",
          form.querySelector("[name=variety]"),
        );
      }
      const axis = form.querySelector("[name=axis]:checked").value;
      const run = await api.startRun({
        connection_id: form.connection.value,
        run_type: form.querySelector("[name=run_type]:checked").value,
        selection: { axis: axis === "all" ? null : axis, varieties },
      });
      location.href =
        "evaluation-run.html?run_id=" + encodeURIComponent(run.run_id);
    });
  }

  async function historyPage() {
    const container = document.getElementById("history");
    const button = document.getElementById("reload");
    let offset = 0;
    async function load() {
      view.busy(button, true);
      view.clearError();
      try {
        const page = await api.runPage(offset);
        const runs = page.items;
        container.innerHTML = runs.length
          ? view.runTable(runs)
          : view.empty(
              "لا توجد تقييمات بعد",
              "ابدأ أول تقييم ليظهر تقريره هنا.",
              "evaluation-setup.html",
              "تقييم جديد",
            );
        container.insertAdjacentHTML(
          "beforeend",
          view.pageControls(offset, page.total, "history"),
        );
        bindPages("history", offset, (value) => {
          offset = value;
          load();
        });
      } catch (error) {
        view.showError(error.message);
        container.textContent =
          "تعذّر تحميل السجل. استخدم تحديث السجل لإعادة المحاولة.";
      } finally {
        view.busy(button, false);
      }
    }
    button.addEventListener("click", load);
    await load();
  }

  async function dashboardPage() {
    const container = document.getElementById("overview");
    const [connections, history] = await Promise.all([
      api.connectionPage(),
      api.runPage(),
    ]);
    const runs = history.items;
    const ready = connections.counts.connected || 0;
    const counts = [
      [connections.total, "اتصالات محفوظة"],
      [ready, "اجتازت اختبار الوصول"],
      [history.total, "تقييمات في السجل"],
    ];
    container.innerHTML =
      '<div class="overview-strip">' +
      counts
        .map(
          ([count, label]) =>
            "<div><strong>" +
            count +
            "</strong><span>" +
            label +
            "</span></div>",
        )
        .join("") +
      '</div><div class="section-toolbar">' +
      view.link("evaluation-setup.html", "تقييم جديد") +
      view.link("connections.html", "إدارة الاتصالات") +
      "</div>" +
      (runs.length
        ? view.runTable(runs.slice(0, 5), "آخر التقييمات")
        : connections.total
          ? view.empty(
              "ابدأ أول تقييم",
              "اختر اتصالًا محفوظًا لتقييم النموذج.",
              "evaluation-setup.html",
              "تقييم جديد",
            )
          : view.empty(
              "ابدأ بإعداد اتصال نموذج",
              "احفظ بيانات الاتصال واختبر الوصول.",
              "model-configuration.html",
              "إضافة اتصال",
            ));
  }

  function downloadReport(identifier) {
    const anchor = document.createElement("a");
    anchor.href = api.reportExportUrl(identifier);
    anchor.download = "harass-" + identifier + ".json";
    anchor.click();
  }

  async function reportPage() {
    const identifier = new URLSearchParams(location.search).get("run_id");
    const container = document.getElementById("report");
    if (!identifier) throw new Error("لم يُحدد التقييم المطلوب.");
    let active = true;
    let timer;
    let evidenceRevision = 0;
    async function loadEvidence(offset) {
      const revision = ++evidenceRevision;
      try {
        const result = await api.getOutcomes(identifier, offset);
        if (!active || revision !== evidenceRevision) return;
        document.getElementById("attemptEvidence").innerHTML =
          view.evidencePage(result);
        document
          .getElementById("evidencePrevious")
          ?.addEventListener("click", () =>
            loadEvidence(Math.max(0, offset - 50)),
          );
        document
          .getElementById("evidenceNext")
          ?.addEventListener("click", () => loadEvidence(offset + 50));
      } catch (error) {
        view.showError(error.message);
      }
    }
    function bindRunAction(buttonId, action) {
      document.getElementById(buttonId).addEventListener("click", async () => {
        const button = document.getElementById(buttonId);
        view.busy(button, true);
        try {
          await action(identifier);
          await load();
        } catch (error) {
          view.showError(error.message);
          view.busy(button, false);
        }
      });
    }
    async function load() {
      clearTimeout(timer);
      view.clearError();
      try {
        const run = await api.getRun(identifier);
        if (!active) return;
        const title =
          run.status === "completed" ? "تقرير التقييم" : "تفاصيل التقييم";
        document.getElementById("evaluationTitle").textContent = title;
        document.title = title + " — HARASS";
        container.innerHTML = view.runHeading(run);
        if (run.status === "completed") {
          const report = await api.getReport(identifier);
          if (!active) return;
          container.insertAdjacentHTML("beforeend", view.reportBody(report));
          if (report.evidence_paged) await loadEvidence(0);
          document
            .getElementById("exportReport")
            .addEventListener("click", () => downloadReport(identifier));
        } else if (run.status === "failed") {
          container.insertAdjacentHTML("beforeend", view.runProgress(run));
          container.insertAdjacentHTML(
            "beforeend",
            run.resumable
              ? '<p>توقف التقييم بعد أخطاء تقنية متكررة. تحقق من الاتصال وإعدادات المحكّم ثم استأنف.</p><button type="button" class="btn" id="resumeRun">استئناف التقييم</button>'
              : view.empty(
                  "تعذّر إكمال التقييم",
                  "راجع اتصال النموذج ثم ابدأ تقييمًا جديدًا.",
                  "evaluation-setup.html",
                  "تقييم جديد",
                ),
          );
          if (run.resumable) bindRunAction("resumeRun", api.resumeRun);
        } else {
          container.insertAdjacentHTML("beforeend", view.runProgress(run));
          if (run.status !== "cancelled")
            timer = setTimeout(load, run.status === "pending" ? 15000 : 10000);
        }
        if (["pending", "running"].includes(run.status) || run.resumable) {
          container.insertAdjacentHTML(
            "beforeend",
            '<button type="button" class="btn btn-secondary" id="cancelRun">إلغاء التقييم</button>',
          );
          bindRunAction("cancelRun", api.cancelRun);
        }
        container.insertAdjacentHTML(
          "beforeend",
          view.link("history.html", "العودة إلى سجل التقييمات"),
        );
      } catch (error) {
        if (!active) return;
        view.showError(error.message);
        container.innerHTML =
          '<button type="button" class="btn" id="retryReport">إعادة المحاولة</button>';
        document.getElementById("retryReport").addEventListener("click", load);
      }
    }
    window.addEventListener("pagehide", () => {
      active = false;
      clearTimeout(timer);
    });
    await load();
  }

  async function start() {
    // Prevent native form submission while account and page initialization are pending.
    document.querySelectorAll("form").forEach((form) => {
      form.addEventListener("submit", (event) => event.preventDefault());
    });
    view.mountShell(["home", "login", "signup"].includes(page));
    initializeNavigation();
    if (page === "home") return;
    if (page === "login" || page === "signup") return authenticationForm();
    await initializeAccount();
    const pages = {
      connections: connectionsPage,
      "model-configuration": connectionForm,
      "evaluation-setup": evaluationForm,
      history: historyPage,
      dashboard: dashboardPage,
      "evaluation-run": reportPage,
    };
    await pages[page]?.();
  }

  start().catch((error) =>
    view.showError(
      error.message || "تعذّر تحميل الصفحة. أعد تحميلها للمحاولة مجددًا.",
    ),
  );
})();
