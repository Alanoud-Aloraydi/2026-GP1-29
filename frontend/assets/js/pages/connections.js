/* Model connections: the paged list and the add or edit form. */
import { api } from '../core/api-client.js';
import { start } from '../core/bootstrap.js';
import { bindSubmit, formError, pagedList, runBusy } from '../core/forms.js';
import { empty, html, link, showError, status } from '../core/ui.js';

const connectionCard = (connection) => html`
  <li class="card connection-card">
    <div class="connection-main">
      <strong><bdi>${connection.model_name}</bdi></strong>
      <span class="hint"><bdi>${connection.base_url}</bdi></span>
    </div>
    <div>
      ${status(connection.status, 'connection')}
      ${connection.status === 'failed' && html`<p class="hint">راجع العنوان والمفتاح ثم أعد الاختبار.</p>`}
    </div>
    <div class="row-actions">
      <button class="btn btn-sm" type="button" data-verify="${connection.connection_id}">اختبار الاتصال</button>
      ${link('model-configuration.html?id=' + encodeURIComponent(connection.connection_id), 'تعديل')}
    </div>
  </li>`;

async function connectionsPage () {
  const container = document.getElementById('connections');
  const load = pagedList({
    container,
    prefix: 'connections',
    fetchPage: api.connectionPage,
    render: (connections) => html`<ul class="connection-list">${connections.map(connectionCard)}</ul>`,
    empty: empty(
      'لا توجد اتصالات بعد', 'أضف اتصال النموذج الذي تريد تقييمه.', 'model-configuration.html', 'إضافة اتصال'
    ),
    failureText: 'تعذّر تحميل الاتصالات.'
  });
  container.addEventListener('click', (event) => {
    const button = event.target.closest('[data-verify]');
    if (!button) return;
    runBusy(button, async () => {
      await api.verifyConnection(button.dataset.verify);
      await load();
    });
  });
  await load();
}

function validEndpoint (value) {
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) && Boolean(url.hostname);
  } catch {
    return false;
  }
}

async function connectionForm () {
  const form = document.getElementById('connectionForm');
  const identifier = new URLSearchParams(location.search).get('id');
  let revision;
  form.apiKey.required = !identifier;
  if (identifier) {
    const connection = await api.getConnection(identifier);
    if (!connection) {
      showError('لم يعد الاتصال متاحًا. افتح قائمة الاتصالات.');
      form.hidden = true;
      return;
    }
    form.modelName.value = connection.model_name;
    form.endpoint.value = connection.base_url;
    revision = connection.revision;
    document.getElementById('apiKeyHint').textContent =
      'اترك الحقل فارغًا للإبقاء على المفتاح المحفوظ، أو أدخل مفتاحًا جديدًا.';
  }
  bindSubmit(form, async () => {
    const baseUrl = form.endpoint.value.trim();
    if (!validEndpoint(baseUrl)) formError('أدخل عنوانًا يبدأ بـ http:// أو https://.', form.endpoint);
    const body = {
      api_compatibility: 'openai_compatible',
      base_url: baseUrl,
      model_name: form.modelName.value.trim(),
      api_key: form.apiKey.value.trim() || null,
      revision
    };
    await (identifier ? api.updateConnection(identifier, body) : api.addConnection(body));
    form.apiKey.value = '';
    location.href = 'connections.html';
  });
}

start(document.body.dataset.page === 'connections' ? connectionsPage : connectionForm);
