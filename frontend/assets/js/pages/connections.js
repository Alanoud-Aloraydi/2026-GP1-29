/* Connections page interactions and error recovery. */
(() => {
  'use strict';
  const api = window.HARASS_API;
  const view = window.HARASS;
  const { bindSubmit, formError, bindPages } = window.HARASS_FORMS;
  function connectionRows (connections) {
    return connections.map((connection) =>
      view.tableRow(connection.model_name, [
        '<bdi>' + view.escape(connection.base_url) + '</bdi>',
        view.status(connection.status, 'connection') +
          (connection.status === 'failed'
            ? '<p class="hint">راجع العنوان والمفتاح ثم أعد الاختبار.</p>'
            : ''),
        '<div class="row-actions"><button class="btn btn-sm" data-verify="' +
          view.escape(connection.connection_id) +
          '">اختبار الاتصال</button>' +
          view.link(
            'model-configuration.html?id=' +
              encodeURIComponent(connection.connection_id),
            'تعديل'
          ) +
          '</div>'
      ])
    );
  }

  async function connectionsPage () {
    const container = document.getElementById('connections');
    let offset = 0;
    async function load () {
      view.clearError();
      try {
        const page = await api.connectionPage(offset);
        const connections = page.items;
        container.innerHTML = connections.length
          ? view.table(
            'الاتصالات المحفوظة',
            ['النموذج', 'نقطة الوصول', 'الحالة', 'الإجراءات'],
            connectionRows(connections)
          )
          : view.empty(
            'لا توجد اتصالات بعد',
            'أضف اتصال النموذج الذي تريد تقييمه.',
            'model-configuration.html',
            'إضافة اتصال'
          );
        container.insertAdjacentHTML(
          'beforeend',
          view.pageControls(offset, page.total, 'connections')
        );
        bindPages('connections', offset, (value) => {
          offset = value;
          load();
        });
      } catch (error) {
        container.innerHTML =
          '<p>تعذّر تحميل الاتصالات.</p>' +
          '<button type="button" class="btn" data-retry>إعادة المحاولة</button>';
        view.showError(error.message);
      }
    }
    container.addEventListener('click', async (event) => {
      const button = event.target.closest('button');
      if (button?.hasAttribute('data-retry')) return load();
      if (!button?.dataset.verify) return;
      view.busy(button, true);
      try {
        await api.verifyConnection(button.dataset.verify);
        await load();
      } catch (error) {
        view.showError(error.message);
        button.textContent = 'إعادة الاختبار';
      } finally {
        view.busy(button, false);
      }
    });
    await load();
  }

  function validEndpoint (value) {
    try {
      const url = new URL(value);
      return (
        ['http:', 'https:'].includes(url.protocol) && Boolean(url.hostname)
      );
    } catch {
      return false;
    }
  }

  async function connectionForm () {
    const form = document.getElementById('connectionForm');
    const identifier = new URLSearchParams(location.search).get('id');
    let connectionRevision;
    form.apiKey.required = !identifier;
    if (identifier) {
      const connection = await api.getConnection(identifier);
      if (!connection) {
        view.showError('لم يعد الاتصال متاحًا. افتح قائمة الاتصالات.');
        form.hidden = true;
        return;
      }
      form.modelName.value = connection.model_name;
      connectionRevision = connection.revision;
      form.endpoint.value = connection.base_url;
      document.getElementById('apiKeyHint').textContent =
        'اترك الحقل فارغًا للإبقاء على المفتاح المحفوظ، أو أدخل مفتاحًا جديدًا.';
    }
    bindSubmit(form, async () => {
      const baseUrl = form.endpoint.value.trim();
      if (!validEndpoint(baseUrl)) {
        formError('أدخل عنوانًا يبدأ بـ http:// أو https://.', form.endpoint);
      }
      const body = {
        api_compatibility: 'openai_compatible',
        base_url: baseUrl,
        model_name: form.modelName.value.trim(),
        api_key: form.apiKey.value.trim() || null,
        revision: connectionRevision
      };
      await (identifier
        ? api.updateConnection(identifier, body)
        : api.addConnection(body));
      form.apiKey.value = '';
      location.href = 'connections.html';
    });
  }

  Object.assign((window.HARASS_PAGES ||= {}), {
    connections: connectionsPage,
    'model-configuration': connectionForm
  });
})();
