/* Password recovery and email verification forms with fragment-only link tokens. */
import { api } from '../core/api-client.js';
import { start } from '../core/bootstrap.js';
import { bindSubmit, formError } from '../core/forms.js';

const LINK_TOKEN = /^[A-Za-z0-9_-]{43}$/;

// Each page sends its form and returns the confirmation it shows.
const actions = {
  'forgot-password': async (form) => {
    await api.forgotPassword(form.email.value.trim());
    return 'إذا كان البريد مسجلًا، ستصلك رسالة لاستعادة كلمة المرور.';
  },
  'reset-password': async (form, token) => {
    if (form.newPassword.value !== form.confirmPassword.value) {
      formError('كلمتا المرور غير متطابقتين.', form.confirmPassword);
    }
    await api.resetPassword(token, form.newPassword.value);
    form.hidden = true;
    return 'حُفظت كلمة المرور. يمكنك تسجيل الدخول الآن.';
  },
  'verify-email': async (form, token) => {
    await api.verifyEmail(token);
    form.hidden = true;
    return 'تم التحقق من بريدك الإلكتروني.';
  }
};

async function accountEmailPage () {
  const page = document.body.dataset.page;
  const form = document.getElementById('accountActionForm');
  const result = document.getElementById('actionResult');
  // The token travels in the fragment so it never reaches server logs; it is
  // removed from the address bar at once.
  const token = new URLSearchParams(location.hash.slice(1)).get('token');
  history.replaceState(null, '', location.pathname + location.search);
  if (!(await api.features()).account_email_enabled) {
    result.textContent = 'هذه الخدمة غير متاحة حاليًا.';
    return;
  }
  if (page !== 'forgot-password' && !LINK_TOKEN.test(token || '')) {
    throw new Error('الرابط غير مكتمل. افتح الرابط الذي وصلك في البريد.');
  }
  form.hidden = false;
  bindSubmit(form, async () => {
    result.textContent = '';
    const confirmation = await actions[page](form, token);
    result.textContent = confirmation;
  });
}

start(accountEmailPage);
