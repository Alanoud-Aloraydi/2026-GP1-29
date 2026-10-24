/* Feature-gated recovery and verification forms with fragment-only link tokens. */
(() => {
  'use strict';
  const api = window.HARASS_API;
  const { bindSubmit, formError } = window.HARASS_FORMS;

  async function accountEmailPage () {
    const page = document.body.dataset.page;
    const form = document.getElementById('accountActionForm');
    const result = document.getElementById('actionResult');
    const token = new URLSearchParams(location.hash.slice(1)).get('token');
    history.replaceState(null, '', location.pathname + location.search);
    if (!(await api.features()).account_email_enabled) {
      result.textContent = 'هذه الخدمة غير متاحة حاليًا.';
      return;
    }
    if (page !== 'forgot-password' && !/^[A-Za-z0-9_-]{43}$/.test(token || '')) {
      throw new Error('الرابط غير مكتمل. افتح الرابط الذي وصلك في البريد.');
    }
    form.hidden = false;
    bindSubmit(form, async () => {
      result.textContent = '';
      if (page === 'forgot-password') {
        await api.forgotPassword(form.email.value.trim());
        result.textContent = 'إذا كان البريد مسجلًا، ستصلك رسالة لاستعادة كلمة المرور.';
      } else if (page === 'reset-password') {
        if (form.newPassword.value !== form.confirmPassword.value) {
          formError('كلمتا المرور غير متطابقتين.', form.confirmPassword);
        }
        await api.resetPassword(token, form.newPassword.value);
        result.textContent = 'حُفظت كلمة المرور. يمكنك تسجيل الدخول الآن.';
        form.hidden = true;
      } else {
        await api.verifyEmail(token);
        result.textContent = 'تم التحقق من بريدك الإلكتروني.';
        form.hidden = true;
      }
    });
  }

  Object.assign((window.HARASS_PAGES ||= {}), {
    'forgot-password': accountEmailPage,
    'reset-password': accountEmailPage,
    'verify-email': accountEmailPage
  });
})();
