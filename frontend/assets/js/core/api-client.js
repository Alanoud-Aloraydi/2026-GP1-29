/* Same-origin API transport with bounded requests and serialized session renewal. */
const REQUEST_TIMEOUT_MS = 20000;

const statusMessages = {
  400: 'تعذّر قبول البيانات. راجع الحقول ثم أعد المحاولة.',
  401: 'انتهت الجلسة أو بيانات الدخول غير صحيحة.',
  403: 'لا يسمح حسابك بهذا الإجراء.',
  404: 'لم يعد هذا السجل متاحًا.',
  409: 'يتعارض الطلب مع سجل موجود. راجع البيانات ثم أعد المحاولة.',
  413: 'حجم الطلب يتجاوز الحد المسموح.',
  422: 'راجع البيانات المطلوبة وصيغتها ثم أعد المحاولة.',
  429: 'تجاوزت عدد المحاولات المسموح. انتظر قليلًا ثم أعد المحاولة.',
  503: 'الخدمة غير متاحة مؤقتًا. أعد المحاولة لاحقًا.'
};

// Messages for specific failures the API names in its body.
const codeMessages = {
  password_rejected: 'اختر كلمة مرور أقل شيوعًا؛ يمكنك استخدام عبارة طويلة.',
  account_link_invalid: 'انتهت صلاحية الرابط أو استُخدم من قبل. اطلب رابطًا جديدًا.',
  active_run: 'لديك تقييم لم ينتهِ. أكمله أو ألغِه قبل بدء تقييم آخر.'
};

const CREDENTIAL_PATHS = new Set(['/auth/login', '/auth/signup', '/auth/refresh']);

async function fetchBounded (path, options) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(path, { ...options, credentials: 'same-origin', signal: controller.signal });
  } finally {
    clearTimeout(timeout);
  }
}

// Tabs share one renewal, so a rotated refresh token is never used twice.
let renewal = null;
function renewSession () {
  const rotate = async () => (await fetchBounded('/auth/me')).ok ||
    (await fetchBounded('/auth/refresh', { method: 'POST', headers: { 'X-Harass-Request': '1' } })).ok;
  renewal ??= (navigator.locks ? navigator.locks.request('harass-session-renewal', rotate) : rotate())
    .finally(() => { renewal = null; });
  return renewal;
}

async function send (method, path, body) {
  // The API requires this header for cookie-authenticated mutations.
  const headers = { 'Content-Type': 'application/json', ...(method !== 'GET' && { 'X-Harass-Request': '1' }) };
  try {
    return await fetchBounded(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch (error) {
    if (error.name !== 'AbortError') throw new Error('تعذّر الوصول إلى الخدمة. تحقق من الاتصال ثم أعد المحاولة.');
    throw new Error(path === '/runs' && method === 'POST'
      ? 'تعذّر التأكد من بدء التقييم. راجع السجل قبل المحاولة مجددًا.'
      : 'انتهت مهلة الاتصال. أعد المحاولة.');
  }
}

function failure (response, payload) {
  const error = new Error(codeMessages[payload?.code] || statusMessages[response.status] ||
    'حدث خطأ في الخدمة. أعد المحاولة لاحقًا.');
  error.status = response.status;
  if (payload?.code === 'active_run') error.activeRunId = payload.active_run_id;
  return error;
}

async function request (method, path, body) {
  let response = await send(method, path, body);
  if (response.status === 401 && !CREDENTIAL_PATHS.has(path) && await renewSession()) {
    response = await send(method, path, body);
  }
  const payload = await response.json().catch(() => null);
  if (response.ok) return { payload, response };
  if (response.status === 401 && !CREDENTIAL_PATHS.has(path)) {
    const current = location.pathname.split('/').pop() + location.search;
    location.href = 'login.html?return=' + encodeURIComponent(current);
  }
  throw failure(response, payload);
}

const call = async (method, path, body) => (await request(method, path, body)).payload;

// A list page also reports how many records exist in each status.
async function page (path, offset) {
  const { payload, response } = await request('GET', `${path}?limit=50&offset=${offset}`);
  const counts = JSON.parse(response.headers.get('X-Status-Counts') || '{}');
  return { items: payload, counts, total: Object.values(counts).reduce((sum, value) => sum + value, 0) };
}

const connection = (id) => '/connections/' + encodeURIComponent(id);
const run = (id) => '/runs/' + encodeURIComponent(id);

async function listConnections () {
  const items = [];
  let current;
  do {
    current = await page('/connections', items.length);
    items.push(...current.items);
  } while (current.items.length && items.length < current.total);
  return items;
}

export const api = Object.freeze({
  options: () => call('GET', '/evaluation-options'),
  features: () => call('GET', '/auth/features'),
  forgotPassword: (email) => call('POST', '/auth/password/forgot', { email }),
  resetPassword: (token, password) => call('POST', '/auth/password/reset', { token, new_password: password }),
  verifyEmail: (token) => call('POST', '/auth/email/verify', { token }),
  requestVerification: () => call('POST', '/auth/email/request-verification'),
  me: () => call('GET', '/auth/me'),
  signup: (credentials) => call('POST', '/auth/signup', credentials),
  login: (credentials) => call('POST', '/auth/login', credentials),
  logout: () => call('POST', '/auth/logout'),
  logoutAll: () => call('POST', '/auth/logout-all'),
  sessions: () => call('GET', '/auth/sessions'),
  revokeSession: (id) => call('DELETE', '/auth/sessions/' + encodeURIComponent(id)),
  updateProfile: (profile) => call('PATCH', '/auth/me', profile),
  connectionPage: (offset = 0) => page('/connections', offset),
  listConnections,
  getConnection: (id) => call('GET', connection(id)),
  addConnection: (body) => call('POST', '/connections', body),
  updateConnection: (id, body) => call('PUT', connection(id), body),
  verifyConnection: (id) => call('POST', connection(id) + '/verify'),
  runPage: (offset = 0) => page('/runs', offset),
  startRun: (body) => call('POST', '/runs', body),
  getRun: (id) => call('GET', run(id)),
  resumeRun: (id) => call('POST', run(id) + '/resume'),
  cancelRun: (id) => call('POST', run(id) + '/cancel'),
  getReport: (id) => call('GET', run(id) + '/report'),
  getOutcomes: (id, offset = 0) => call('GET', `${run(id)}/outcomes?limit=50&offset=${offset}`),
  getPrompts: (id, offset = 0) => call('GET', `${run(id)}/prompts?limit=50&offset=${offset}`),
  reportExportUrl: (id) => run(id) + '/report/export',
  judgeReports: () => call('GET', '/admin/judge-benchmarks'),
  judgeReport: (id) => call('GET', '/admin/judge-benchmarks/' + encodeURIComponent(id))
});
