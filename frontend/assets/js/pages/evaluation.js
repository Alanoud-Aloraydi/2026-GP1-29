/* Evaluation page interactions and error recovery. */
(() => {
  'use strict';
  const api = window.HARASS_API;
  const view = window.HARASS;
  const { bindSubmit, formError } = window.HARASS_FORMS;
  async function evaluationForm () {
    const form = document.getElementById('evaluationForm');
    const button = document.getElementById('start');
    view.busy(button, true);
    const connections = (await api.listConnections()).filter(
      (item) => item.status === 'connected'
    );
    form.connection.replaceChildren(
      new Option('اختر اتصالًا', ''),
      ...connections.map(
        (item) => new Option(item.model_name, item.connection_id)
      )
    );
    const summary = {
      connection: () => form.connection.selectedOptions[0].textContent,
      run_type: () => chosenTitle('run_type'),
      axis: () => chosenTitle('axis'),
      variety: () =>
        form.querySelectorAll('[name=variety]:checked').length +
        ' من ' +
        form.querySelectorAll('[name=variety]').length
    };
    const chosenTitle = (name) =>
      form
        .querySelector('[name=' + name + ']:checked')
        .closest('label')
        .querySelector('strong').textContent;
    const updateSummary = () => {
      document.querySelectorAll('[data-summary]').forEach((element) => {
        element.textContent = summary[element.dataset.summary]();
      });
    };
    form.addEventListener('change', updateSummary);
    updateSummary();
    if (!connections.length) {
      view.showError(
        'لا يوجد اتصال جاهز. أضف اتصالًا واختبره من صفحة اتصالات النماذج.'
      );
      return;
    }
    view.busy(button, false);
    bindSubmit(form, async () => {
      const varieties = Array.from(
        form.querySelectorAll('[name=variety]:checked'),
        (input) => input.value
      );
      if (!varieties.length) {
        formError(
          'اختر لغة أو لهجة واحدة على الأقل.',
          form.querySelector('[name=variety]')
        );
      }
      const axis = form.querySelector('[name=axis]:checked').value;
      const run = await api.startRun({
        connection_id: form.connection.value,
        run_type: form.querySelector('[name=run_type]:checked').value,
        selection: { axis: axis === 'all' ? null : axis, varieties }
      });
      location.href =
        'evaluation-run.html?run_id=' + encodeURIComponent(run.run_id);
    });
  }

  Object.assign((window.HARASS_PAGES ||= {}), {
    'evaluation-setup': evaluationForm
  });
})();
