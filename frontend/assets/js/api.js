(() => {
  "use strict";

  const errors = {
    400: "تعذّر قبول البيانات. راجع الحقول ثم أعد المحاولة.",
    401: "انتهت الجلسة أو بيانات الدخول غير صحيحة.",
    403: "لا يسمح حسابك بهذا الإجراء.",
    404: "لم يعد هذا السجل متاحًا.",
    409: "يتعارض الطلب مع سجل موجود. راجع البيانات ثم أعد المحاولة.",
    413: "حجم الطلب يتجاوز الحد المسموح.",
    503: "الخدمة غير متاحة مؤقتًا. أعد المحاولة لاحقًا.",
    422: "راجع البيانات المطلوبة وصيغتها ثم أعد المحاولة.",
    429: "تجاوزت عدد المحاولات المسموح. انتظر قليلًا ثم أعد المحاولة.",
  };

  async function request(method, path, body, withCounts = false) {
    const headers = { "Content-Type": "application/json" };
    // The API requires this header for cookie-authenticated mutations.
    if (method !== "GET") headers["X-Harass-Request"] = "1";
    let response;
    try {
      response = await fetch(path, {
        method,
        headers,
        credentials: "same-origin",
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new Error(
        "تعذّر الوصول إلى الخدمة. تحقق من الاتصال ثم أعد المحاولة.",
      );
    }
    const payload = await response.json().catch(() => null);
    if (response.ok) {
      if (!withCounts) return payload;
      const counts = JSON.parse(
        response.headers.get("X-Status-Counts") || "{}",
      );
      return {
        items: payload,
        counts,
        total: Object.values(counts).reduce((sum, value) => sum + value, 0),
      };
    }
    const error = new Error(
      errors[response.status] || "حدث خطأ في الخدمة. أعد المحاولة لاحقًا.",
    );
    error.status = response.status;
    if (payload?.code === "password_rejected")
      error.message = "اختر كلمة مرور أقل شيوعًا؛ يمكنك استخدام عبارة طويلة.";
    if (payload?.code === "active_run") {
      error.message = "لديك تقييم لم ينتهِ. أكمله أو ألغِه قبل بدء تقييم آخر.";
      error.activeRunId = payload.active_run_id;
    }
    if (
      response.status === 401 &&
      path !== "/auth/login" &&
      path !== "/auth/signup"
    ) {
      const destination = location.pathname.split("/").pop() + location.search;
      location.href = "login.html?return=" + encodeURIComponent(destination);
    }
    throw error;
  }

  const connectionPath = (id) => "/connections/" + encodeURIComponent(id);
  const runPath = (id) => "/runs/" + encodeURIComponent(id);
  window.HARASS_API = Object.freeze({
    me: () => request("GET", "/auth/me"),
    signup: (body) => request("POST", "/auth/signup", body),
    login: (body) => request("POST", "/auth/login", body),
    logout: () => request("POST", "/auth/logout"),
    listConnections: async () => {
      const items = [];
      let offset = 0;
      let total;
      do {
        const page = await request(
          "GET",
          "/connections?limit=50&offset=" + offset,
          undefined,
          true,
        );
        items.push(...page.items);
        total = page.total;
        offset += 50;
        if (!page.items.length) break;
      } while (offset < total);
      return items;
    },
    getConnection: (id) => request("GET", connectionPath(id)),
    connectionPage: (offset = 0) =>
      request("GET", "/connections?limit=50&offset=" + offset, undefined, true),
    addConnection: (body) => request("POST", "/connections", body),
    updateConnection: (id, body) => request("PUT", connectionPath(id), body),
    verifyConnection: (id) => request("POST", connectionPath(id) + "/verify"),
    startRun: (body) => request("POST", "/runs", body),
    resumeRun: (id) => request("POST", runPath(id) + "/resume"),
    cancelRun: (id) => request("POST", runPath(id) + "/cancel"),
    runPage: (offset = 0) =>
      request("GET", "/runs?limit=50&offset=" + offset, undefined, true),
    getRun: (id) => request("GET", runPath(id)),
    getReport: (id) => request("GET", runPath(id) + "/report"),
    getOutcomes: (id, offset = 0) =>
      request("GET", runPath(id) + "/outcomes?limit=50&offset=" + offset),
    reportExportUrl: (id) => runPath(id) + "/report/export",
  });
})();
