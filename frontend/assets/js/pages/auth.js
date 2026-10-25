/* Auth page interactions and error recovery. */
(() => {
  'use strict';
  const api = window.HARASS_API;
  const view = window.HARASS;
  const page = document.body.dataset.page;
  const { bindSubmit, formError } = window.HARASS_FORMS;
  async function authenticationForm () {
    const form = document.getElementById('authForm');
    bindSubmit(form, async () => {
      const credentials = {
        email: form.email.value.trim(),
        password: form.password.value
      };
      if (page === 'signup') {
        if (form.confirm.value !== credentials.password) {
          formError(
            'كلمتا المرور غير متطابقتين. أعد إدخال التأكيد.',
            form.confirm
          );
        }
        credentials.full_name = form.full_name.value.trim();
        if (credentials.full_name.length < 2) {
          formError('أدخل اسمًا بين حرفين و100 حرف.', form.full_name);
        }
      }
      try {
        await (page === 'signup'
          ? api.signup(credentials)
          : api.login(credentials));
      } catch (error) {
        const messages = {
          401: 'البريد الإلكتروني أو كلمة المرور غير صحيحة. راجع بياناتك ثم أعد المحاولة.',
          409: 'هذا البريد مسجل بالفعل. يمكنك تسجيل الدخول بحسابك.'
        };
        throw new Error(messages[error.status] || error.message);
      }
      location.href = view.safeReturn();
    });
    const recovery = document.getElementById('forgotPasswordLink');
    if (recovery) {
      recovery.hidden = !(await api.features()).account_email_enabled;
    }
  }

  Object.assign((window.HARASS_PAGES ||= {}), {
    login: authenticationForm,
    signup: authenticationForm
  });
})();
