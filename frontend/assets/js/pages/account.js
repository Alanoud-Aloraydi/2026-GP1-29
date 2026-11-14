/* Profile, activity summary and owner-scoped session management. */
(() => {
  'use strict';
  const api = window.HARASS_API;
  const view = window.HARASS;
  const element = (id) => document.getElementById(id);

  async function sessionList () {
    const container = element('sessions');
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
    element('logoutAll').addEventListener('click', async (event) => {
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
  }

  function nameEditor (user) {
    const form = element('nameForm');
    const editButton = element('editName');
    const input = element('fullName');
    function toggle (editing) {
      form.hidden = !editing;
      editButton.hidden = editing;
      if (editing) {
        input.value = user.full_name;
        input.focus();
      } else {
        editButton.focus();
      }
    }
    editButton.addEventListener('click', () => toggle(true));
    element('cancelName').addEventListener('click', () => toggle(false));
    window.HARASS_FORMS.bindSubmit(form, async () => {
      await api.updateProfile({ full_name: input.value });
      location.reload();
    });
  }

  function verification (user, verifiable) {
    const button = element('sendVerification');
    button.hidden = !verifiable || user.email_verified;
    button.addEventListener('click', async () => {
      view.busy(button, true);
      try {
        await api.requestVerification();
        button.textContent = 'أُرسل رابط التحقق إلى بريدك';
        button.disabled = true;
      } catch (error) {
        view.showError(error.message);
        view.busy(button, false);
      }
    });
  }

  async function identity () {
    const [user, features] = await Promise.all([api.me(), api.features()]);
    const verifiable = features.account_email_enabled;
    element('profileEmail').textContent = user.email;
    const badges = [];
    if (user.role === 'admin') badges.push('مسؤول');
    if (verifiable) {
      badges.push(user.email_verified ? 'البريد موثّق' : 'البريد غير موثّق');
    }
    element('profileBadges').innerHTML = badges
      .map((label) => '<span class="chip">' + view.escape(label) + '</span>')
      .join('');
    if (user.created_at) {
      element('profileSince').textContent =
        'عضو منذ ' + view.date(user.created_at);
    }
    nameEditor(user);
    verification(user, verifiable);
  }

  async function activity () {
    const [connections, history] = await Promise.all([
      api.connectionPage(),
      api.runPage()
    ]);
    const latest = history.items[0];
    const figures = [
      [connections.total, 'اتصالات محفوظة'],
      [history.total, 'تقييمات في السجل'],
      [
        latest
          ? '<a href="evaluation-run.html?run_id=' +
            view.escape(encodeURIComponent(latest.run_id)) +
            '">' +
            view.escape(view.date(latest.created_at)) +
            '</a>'
          : '—',
        'آخر تقييم'
      ]
    ];
    element('activity').innerHTML = figures
      .map(
        ([value, label]) =>
          '<div><strong>' +
          (typeof value === 'number' ? view.escape(value) : value) +
          '</strong><span>' +
          label +
          '</span></div>'
      )
      .join('');
  }

  async function accountPage () {
    await Promise.all([identity(), activity(), sessionList()]);
  }

  Object.assign((window.HARASS_PAGES ||= {}), { account: accountPage });
})();
