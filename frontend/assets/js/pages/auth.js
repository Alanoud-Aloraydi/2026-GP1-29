/* Login and signup forms. */
import { api } from '../core/api-client.js';
import { start } from '../core/bootstrap.js';
import { bindSubmit, formError } from '../core/forms.js';
import { safeReturn } from '../core/ui.js';

const signingUp = document.body.dataset.page === 'signup';
const credentialErrors = {
  401: 'البريد الإلكتروني أو كلمة المرور غير صحيحة. راجع بياناتك ثم أعد المحاولة.',
  409: 'هذا البريد مسجل بالفعل. يمكنك تسجيل الدخول بحسابك.'
};

async function authenticationForm () {
  const form = document.getElementById('authForm');
  bindSubmit(form, async () => {
    const credentials = { email: form.email.value.trim(), password: form.password.value };
    if (signingUp) {
      if (form.confirm.value !== credentials.password) {
        formError('كلمتا المرور غير متطابقتين. أعد إدخال التأكيد.', form.confirm);
      }
      credentials.full_name = form.full_name.value.trim();
      if (credentials.full_name.length < 2) formError('أدخل اسمًا بين حرفين و100 حرف.', form.full_name);
    }
    try {
      await (signingUp ? api.signup(credentials) : api.login(credentials));
    } catch (error) {
      throw new Error(credentialErrors[error.status] || error.message);
    }
    location.href = safeReturn();
  });
  const recovery = document.getElementById('forgotPasswordLink');
  if (recovery) recovery.hidden = !(await api.features()).account_email_enabled;
}

start(authenticationForm);
