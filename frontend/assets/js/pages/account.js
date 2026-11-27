/* Profile, activity summary and the account's sessions. */
import { api } from '../core/api-client.js';
import { start } from '../core/bootstrap.js';
import { bindSubmit, runBusy } from '../core/forms.js';
import { date, figures, html, table } from '../core/ui.js';

const element = (id) => document.getElementById(id);
const runLink = (run) => 'evaluation-run.html?run_id=' + encodeURIComponent(run.run_id);

const sessionColumns = [
  { title: 'الجلسة', cell: (session) => session.current ? 'الجلسة الحالية' : 'جلسة أخرى' },
  { title: 'أُنشئت', cell: (session) => date(session.created_at) },
  { title: 'تنتهي', cell: (session) => date(session.expires_at) },
  {
    title: 'الإجراء',
    cell: (session) => session.current
      ? '—'
      : html`<button class="btn btn-sm" type="button" data-revoke="${session.session_id}">إنهاء الجلسة</button>`
  }
];

async function sessions () {
  const container = element('sessions');
  const load = async () => {
    container.innerHTML = table('جلسات حسابك', sessionColumns, await api.sessions());
  };
  container.addEventListener('click', (event) => {
    const button = event.target.closest('[data-revoke]');
    if (button) {
      runBusy(button, async () => {
        await api.revokeSession(button.dataset.revoke);
        await load();
      });
    }
  });
  element('logoutAll').addEventListener('click', (event) => runBusy(event.currentTarget, async () => {
    await api.logoutAll();
    location.href = 'login.html';
  }));
  await load();
}

function nameEditor (user) {
  const form = element('nameForm');
  const editButton = element('editName');
  const input = element('fullName');
  const toggle = (editing) => {
    form.hidden = !editing;
    editButton.hidden = editing;
    if (editing) input.value = user.full_name;
    (editing ? input : editButton).focus();
  };
  editButton.addEventListener('click', () => toggle(true));
  element('cancelName').addEventListener('click', () => toggle(false));
  bindSubmit(form, async () => {
    await api.updateProfile({ full_name: input.value });
    location.reload();
  });
}

async function identity () {
  const [user, features] = await Promise.all([api.me(), api.features()]);
  const verifiable = features.account_email_enabled;
  const badges = [
    user.role === 'admin' && 'مسؤول',
    verifiable && (user.email_verified ? 'البريد موثّق' : 'البريد غير موثّق')
  ].filter(Boolean);
  element('profileEmail').textContent = user.email;
  element('profileBadges').innerHTML = html`${badges.map((badge) => html`<span class="chip">${badge}</span>`)}`;
  if (user.created_at) element('profileSince').textContent = 'عضو منذ ' + date(user.created_at);
  nameEditor(user);
  const verify = element('sendVerification');
  verify.hidden = !verifiable || user.email_verified;
  verify.addEventListener('click', () => runBusy(verify, async () => {
    await api.requestVerification();
    verify.textContent = 'أُرسل رابط التحقق إلى بريدك';
  }));
}

async function activity () {
  const [connections, history] = await Promise.all([api.connectionPage(), api.runPage()]);
  const latest = history.items[0];
  const activityFigures = [
    [connections.total, 'اتصالات محفوظة'],
    [history.total, 'تقييمات في السجل'],
    [latest ? html`<a href="${runLink(latest)}">${date(latest.created_at)}</a>` : '—', 'آخر تقييم']
  ];
  element('activity').innerHTML = html`${figures(activityFigures)}`;
}

start(() => Promise.all([identity(), activity(), sessions()]));
