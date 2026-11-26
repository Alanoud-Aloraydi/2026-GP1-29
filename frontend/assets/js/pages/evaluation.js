/* New evaluation form with a live summary of the choices. */
import { api } from '../core/api-client.js';
import { start } from '../core/bootstrap.js';
import { bindSubmit, formError } from '../core/forms.js';
import { busy, showError } from '../core/ui.js';

async function evaluationForm () {
  const form = document.getElementById('evaluationForm');
  const button = document.getElementById('start');
  const checked = (name) => form.querySelector(`[name=${name}]:checked`);
  const chosenTitle = (name) => checked(name).closest('label').querySelector('strong').textContent;
  const varieties = () => Array.from(form.querySelectorAll('[name=variety]:checked'), (input) => input.value);
  const summary = {
    connection: () => form.connection.selectedOptions[0].textContent,
    run_type: () => chosenTitle('run_type'),
    axis: () => chosenTitle('axis'),
    variety: () => `${varieties().length} من ${form.querySelectorAll('[name=variety]').length}`
  };
  const updateSummary = () => document.querySelectorAll('[data-summary]').forEach((element) => {
    element.textContent = summary[element.dataset.summary]();
  });

  busy(button, true);
  const connections = (await api.listConnections()).filter((item) => item.status === 'connected');
  form.connection.replaceChildren(
    new Option('اختر اتصالًا', ''),
    ...connections.map((item) => new Option(item.model_name, item.connection_id))
  );
  form.addEventListener('change', updateSummary);
  updateSummary();
  if (!connections.length) {
    showError('لا يوجد اتصال جاهز. أضف اتصالًا واختبره من صفحة اتصالات النماذج.');
    return;
  }
  busy(button, false);
  bindSubmit(form, async () => {
    if (!varieties().length) formError('اختر لغة أو لهجة واحدة على الأقل.', form.querySelector('[name=variety]'));
    const axis = checked('axis').value;
    const run = await api.startRun({
      connection_id: form.connection.value,
      run_type: checked('run_type').value,
      selection: { axis: axis === 'all' ? null : axis, varieties: varieties() }
    });
    location.href = 'evaluation-run.html?run_id=' + encodeURIComponent(run.run_id);
  });
}

start(evaluationForm);
