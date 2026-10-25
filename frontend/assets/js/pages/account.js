/* Password reauthentication and owner-scoped session management. */
(() => {
  'use strict';
  const api = window.HARASS_API;
  const view = window.HARASS;

  async function accountPage () {
    const container = document.getElementById('sessions');
    async function loadSessions () {
      const sessions = await api.sessions();
      container.innerHTML = view.table(
        'جلسات حسابك',
        ['الجلسة', 'أُنشئت', 'تنتهي', 'الإجراء'],
        sessions.map((session) =>
          view.tableRow(session.current ? 'الجلسة الحالية' : 'جلسة أخرى', [
            view.escape(view.date(session.created_at)),
            view.escape(view.date(session.expires_at)),
            session.current
              ? '—'
              : '<button class="btn btn-sm" data-revoke="' +
                view.escape(session.session_id) +
                '">إنهاء الجلسة</button>'
          ])
        )
      );
    }
    const form = document.getElementById('passwordForm');
    window.HARASS_FORMS.bindSubmit(form, async () => {
      if (form.newPassword.value !== form.confirmPassword.value) {
        window.HARASS_FORMS.formError(
          'كلمتا المرور غير متطابقتين.',
          form.confirmPassword
        );
      }
      await api.changePassword({
        current_password: form.currentPassword.value,
        new_password: form.newPassword.value
      });
      form.reset();
      document.getElementById('passwordResult').textContent =
        'حُفظت كلمة المرور وأُغلقت الجلسات السابقة.';
      await loadSessions();
    });
    container.addEventListener('click', async (event) => {
      const button = event.target.closest('[data-revoke]');
      if (!button) return;
      view.busy(button, true);
      try {
        await api.revokeSession(button.dataset.revoke);
        await loadSessions();
      } catch (error) {
        view.showError(error.message);
        view.busy(button, false);
      }
    });
    document
      .getElementById('logoutAll')
      .addEventListener('click', async (event) => {
        const button = event.currentTarget;
        view.busy(button, true);
        try {
          await api.logoutAll();
          location.href = 'login.html';
        } catch (error) {
          view.showError(error.message);
          view.busy(button, false);
        }
      });
    await loadSessions();
    await emailVerification();
  }

  async function emailVerification () {
    if (!(await api.features()).account_email_enabled) return;
    const user = await api.me();
    const status = document.getElementById('emailStatus');
    const button = document.getElementById('sendVerification');
    document.getElementById('emailVerification').hidden = false;
    status.textContent = user.email_verified ? 'بريدك الإلكتروني موثّق.' : 'لم يُتحقق من بريدك الإلكتروني بعد.';
    button.hidden = user.email_verified;
    button.addEventListener('click', async () => {
      view.busy(button, true);
      try {
        await api.requestVerification();
        status.textContent = 'طُلب إرسال رابط التحقق إلى بريدك الإلكتروني.';
      } catch (error) {
        view.showError(error.message);
      } finally {
        view.busy(button, false);
      }
    });
  }
  Object.assign((window.HARASS_PAGES ||= {}), { account: accountPage });
})();
