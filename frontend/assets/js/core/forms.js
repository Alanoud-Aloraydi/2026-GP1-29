/* Shared form validation, submission and page navigation behavior. */
(() => {
  const view = window.HARASS;
  function bindSubmit (form, action) {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      view.clearError();
      if (!form.reportValidity()) return;
      const button = form.querySelector('button[type=submit]');
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

  window.HARASS_FORMS = { bindSubmit, formError, bindPages };
})();
