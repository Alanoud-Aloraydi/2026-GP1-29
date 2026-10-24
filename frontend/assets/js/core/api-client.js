/* Same-origin API transport with bounded requests and serialized session renewal. */
(() => {
  'use strict';

  const errors = {
    400: 'تعذّر قبول البيانات. راجع الحقول ثم أعد المحاولة.',
    401: 'انتهت الجلسة أو بيانات الدخول غير صحيحة.',
    403: 'لا يسمح حسابك بهذا الإجراء.',
    404: 'لم يعد هذا السجل متاحًا.',
    409: 'يتعارض الطلب مع سجل موجود. راجع البيانات ثم أعد المحاولة.',
    413: 'حجم الطلب يتجاوز الحد المسموح.',
    503: 'الخدمة غير متاحة مؤقتًا. أعد المحاولة لاحقًا.',
    422: 'راجع البيانات المطلوبة وصيغتها ثم أعد المحاولة.',
    429: 'تجاوزت عدد المحاولات المسموح. انتظر قليلًا ثم أعد المحاولة.'
  };

  let renewal;

  async function fetchBounded (path, options) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      return await fetch(path, { ...options, signal: controller.signal });
    } finally {
      clearTimeout(timeout);
    }
  }

  function refreshSession () {
    if (renewal) return renewal;
    const rotate = async () => {
      const current = await fetchBounded('/auth/me', {
        credentials: 'same-origin'
      });
      if (current.ok) return true;
      const response = await fetchBounded('/auth/refresh', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-Harass-Request': '1' }
      });
      return response.ok;
    };
    renewal = (
      navigator.locks
        ? navigator.locks.request('harass-session-renewal', rotate)
        : rotate()
    ).finally(() => {
      renewal = null;
    });
    return renewal;
  }

  async function request (
    method,
    path,
    body,
    withCounts = false,
    renewed = false
  ) {
    const headers = { 'Content-Type': 'application/json' };
    // The API requires this header for cookie-authenticated mutations.
    if (method !== 'GET') headers['X-Harass-Request'] = '1';
    let response;
    try {
      response = await fetchBounded(path, {
        method,
        headers,
        credentials: 'same-origin',
        body: body === undefined ? undefined : JSON.stringify(body)
      });
    } catch (error) {
      if (error.name === 'AbortError') {
        throw new Error(
          path === '/runs' && method === 'POST'
            ? 'تعذّر التأكد من بدء التقييم. راجع السجل قبل المحاولة مجددًا.'
            : 'انتهت مهلة الاتصال. أعد المحاولة.'
        );
      }
      throw new Error(
        'تعذّر الوصول إلى الخدمة. تحقق من الاتصال ثم أعد المحاولة.'
      );
    }
    if (
      response.status === 401 &&
      !renewed &&
      !['/auth/login', '/auth/signup', '/auth/refresh'].includes(path)
    ) {
      if (await refreshSession()) { return request(method, path, body, withCounts, true); }
    }
    const payload = await response.json().catch(() => null);
    if (response.ok) {
      if (!withCounts) return payload;
      const counts = JSON.parse(
        response.headers.get('X-Status-Counts') || '{}'
      );
      return {
        items: payload,
        counts,
        total: Object.values(counts).reduce((sum, value) => sum + value, 0)
      };
    }
    const error = new Error(
      errors[response.status] || 'حدث خطأ في الخدمة. أعد المحاولة لاحقًا.'
    );
    error.status = response.status;
    if (payload?.code === 'password_rejected') { error.message = 'اختر كلمة مرور أقل شيوعًا؛ يمكنك استخدام عبارة طويلة.'; }
    if (payload?.code === 'account_link_invalid') {
      error.message = 'انتهت صلاحية الرابط أو استُخدم من قبل. اطلب رابطًا جديدًا.';
    }
    if (payload?.code === 'active_run') {
      error.message = 'لديك تقييم لم ينتهِ. أكمله أو ألغِه قبل بدء تقييم آخر.';
      error.activeRunId = payload.active_run_id;
    }
    if (
      response.status === 401 &&
      path !== '/auth/login' &&
      path !== '/auth/signup'
    ) {
      const destination = location.pathname.split('/').pop() + location.search;
      location.href = 'login.html?return=' + encodeURIComponent(destination);
    }
    throw error;
  }

  const connectionPath = (id) => '/connections/' + encodeURIComponent(id);
  const runPath = (id) => '/runs/' + encodeURIComponent(id);
  window.HARASS_API = Object.freeze({
    options: () => request('GET', '/evaluation-options'),
    features: () => request('GET', '/auth/features'),
    forgotPassword: (email) => request('POST', '/auth/password/forgot', { email }),
    resetPassword: (token, password) => request('POST', '/auth/password/reset', { token, new_password: password }),
    verifyEmail: (token) => request('POST', '/auth/email/verify', { token }),
    requestVerification: () => request('POST', '/auth/email/request-verification'),
    me: () => request('GET', '/auth/me'),
    signup: (body) => request('POST', '/auth/signup', body),
    login: (body) => request('POST', '/auth/login', body),
    logout: () => request('POST', '/auth/logout'),
    sessions: () => request('GET', '/auth/sessions'),
    revokeSession: (id) =>
      request('DELETE', '/auth/sessions/' + encodeURIComponent(id)),
    logoutAll: () => request('POST', '/auth/logout-all'),
    changePassword: (body) => request('POST', '/auth/password', body),
    listConnections: async () => {
      const items = [];
      let offset = 0;
      let total;
      do {
        const page = await request(
          'GET',
          '/connections?limit=50&offset=' + offset,
          undefined,
          true
        );
        items.push(...page.items);
        total = page.total;
        offset += 50;
        if (!page.items.length) break;
      } while (offset < total);
      return items;
    },
    getConnection: (id) => request('GET', connectionPath(id)),
    connectionPage: (offset = 0) =>
      request(
        'GET',
        '/connections?limit=50&offset=' + offset,
        undefined,
        true
      ),
    addConnection: (body) => request('POST', '/connections', body),
    updateConnection: (id, body) => request('PUT', connectionPath(id), body),
    verifyConnection: (id) => request('POST', connectionPath(id) + '/verify'),
    startRun: (body) => request('POST', '/runs', body),
    resumeRun: (id) => request('POST', runPath(id) + '/resume'),
    cancelRun: (id) => request('POST', runPath(id) + '/cancel'),
    runPage: (offset = 0) =>
      request('GET', '/runs?limit=50&offset=' + offset, undefined, true),
    getRun: (id) => request('GET', runPath(id)),
    getReport: (id) => request('GET', runPath(id) + '/report'),
    getOutcomes: (id, offset = 0) =>
      request('GET', runPath(id) + '/outcomes?limit=50&offset=' + offset),
    reportExportUrl: (id) => runPath(id) + '/report/export'
  });
})();
