/* Shared form validation, submission and page navigation behavior. */
(() => {
  const view = window.HARASS;
  function bindSubmit (form, action) {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      view.clearError();
      if (!form.reportValidity()) return;
      // A submit button may sit outside the form and point to it by id.
      const button =
        event.submitter || form.querySelector('button[type=submit]');
      view.busy(button, true);
      try {
        await action();
      } catch (error) {
        view.showError(error.message);
        if (error.activeRunId) {
          document
            .getElementById('pageError')
            .insertAdjacentHTML(
              'beforeend',
              view.link(
                'evaluation-run.html?run_id=' +
                  encodeURIComponent(error.activeRunId),
                'فتح التقييم الجاري'
              )
            );
        }
        error.field?.focus();
      } finally {
        view.busy(button, false);
      }
    });
  }

  function formError (message, field) {
    throw Object.assign(new Error(message), { field });
  }

  function bindPages (prefix, offset, load) {
    document
      .getElementById(prefix + 'Previous')
      ?.addEventListener('click', () => load(Math.max(0, offset - 50)));
    document
      .getElementById(prefix + 'Next')
      ?.addEventListener('click', () => load(offset + 50));
  }

  // A button marked data-reveal toggles the password field before it.
  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-reveal]');
    if (!button) return;
    const field = button.previousElementSibling;
    const hidden = field.type === 'password';
    field.type = hidden ? 'text' : 'password';
    button.textContent = hidden ? 'إخفاء' : 'إظهار';
    button.setAttribute('aria-pressed', String(hidden));
  });

  window.HARASS_FORMS = { bindSubmit, formError, bindPages };
})();
