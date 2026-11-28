/* New evaluation form with a live summary of the choices. */
import { api } from '../core/api-client.js';
import { start } from '../core/bootstrap.js';
import { bindSubmit, formError } from '../core/forms.js';
import { busy, catalogue, html, showError } from '../core/ui.js';

const transformOption = (transform) => html`
  <label>
    <input type="checkbox" name="transform" value="${transform.name}">
    ${transform.label}
    ${transform.attack_only && html`<span class="chip">الاختراق فقط</span>`}
  </label>`;

async function evaluationForm () {
  const form = document.getElementById('evaluationForm');
  const button = document.getElementById('start');
  const checked = (name) => form.querySelector(`[name=${name}]:checked`);
  const chosenTitle = (name) => checked(name).closest('label').querySelector('strong').textContent;
  const values = (name) => Array.from(form.querySelectorAll(`[name=${name}]:checked`), (input) => input.value);
  const agentic = () => checked('kind').value === 'agentic';
  const summary = {
    connection: () => form.connection.selectedOptions[0].textContent,
    kind: () => chosenTitle('kind'),
    axis: () => agentic()
      ? `${chosenTitle('axis')} · ${form.rounds.value} جولات × ${form.prompts_per_round.value} طلبًا`
      : chosenTitle('axis'),
    variety: () => `${values('variety').length} من ${form.querySelectorAll('[name=variety]').length}`
  };
  const update = () => {
    document.getElementById('agenticStep').hidden = !agentic();
    document.querySelectorAll('[data-summary]').forEach((element) => {
      element.textContent = summary[element.dataset.summary]();
    });
  };

  busy(button, true);
  const ready = (await api.listConnections()).filter((item) => item.status === 'connected');
  form.connection.replaceChildren(
    new Option('اختر اتصالًا', ''),
    ...ready.map((item) => new Option(item.model_name, item.connection_id))
  );
  document.getElementById('transforms').innerHTML = html`${catalogue.transforms.map(transformOption)}`;
  form.addEventListener('change', update);
  form.addEventListener('input', update);
  update();
  if (!ready.length) {
    showError('لا يوجد اتصال جاهز. أضف اتصالًا واختبره من صفحة اتصالات النماذج.');
    return;
  }
  busy(button, false);
  bindSubmit(form, async () => {
    if (!values('variety').length) formError('يرجى اختيار العربية الفصحى أو إحدى اللهجات العربية على الأقل قبل بدء التقييم.',form.querySelector('[name=variety]'));
    const selection = { axis: checked('axis').value === 'all' ? null : checked('axis').value, varieties: values('variety') };
    const run = await api.startRun(agentic()
      ? {
          connection_id: form.connection.value,
          kind: 'agentic',
          selection,
          agentic: {
            rounds: Number(form.rounds.value),
            prompts_per_round: Number(form.prompts_per_round.value),
            transform_names: values('transform')
          }
        }
      : { connection_id: form.connection.value, selection });
    location.href = 'evaluation-run.html?run_id=' + encodeURIComponent(run.run_id);
  });
}

start(evaluationForm);
