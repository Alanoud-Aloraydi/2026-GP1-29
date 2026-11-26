/* Shared form submission, busy buttons and list pagination. */
import { busy, clearError, html, link, pageControls, PAGE_SIZE, showError } from './ui.js';

// Run a button's action; the button is re-enabled only when the action
// fails, because success usually navigates away or redraws the button.
export async function runBusy (button, action) {
  busy(button, true);
  try {
    await action();
  } catch (error) {
    showError(error.message);
    busy(button, false);
  }
}

export function bindSubmit (form, action) {
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    clearError();
    if (!form.reportValidity()) return;
    // A submit button may sit outside the form and point to it by id.
    const button = event.submitter || form.querySelector('button[type=submit]');
    busy(button, true);
    try {
      await action();
    } catch (error) {
      showError(error.message);
      if (error.activeRunId) {
        const path = 'evaluation-run.html?run_id=' + encodeURIComponent(error.activeRunId);
        document.getElementById('pageError').insertAdjacentHTML('beforeend', link(path, 'فتح التقييم الجاري'));
      }
      error.field?.focus();
    } finally {
      busy(button, false);
    }
  });
}

export function formError (message, field) {
  throw Object.assign(new Error(message), { field });
}

/**
 * Return a loader that shows one page of a list with previous and next
 * controls. fetchPage returns {items, total}; render draws the items, and
 * empty is the markup shown when there are none.
 */
export function pagedList ({ container, prefix, fetchPage, render, empty, failureText }) {
  let offset = 0;
  async function load () {
    clearError();
    try {
      const page = await fetchPage(offset);
      container.innerHTML = page.items.length ? render(page.items) : empty;
      container.insertAdjacentHTML('beforeend', pageControls(offset, page.total, prefix));
      for (const [suffix, step] of [['Previous', -PAGE_SIZE], ['Next', PAGE_SIZE]]) {
        document.getElementById(prefix + suffix)?.addEventListener('click', () => {
          offset = Math.max(0, offset + step);
          load();
        });
      }
    } catch (error) {
      container.innerHTML = html`
        <p>${failureText}</p>
        <button type="button" class="btn" data-retry>إعادة المحاولة</button>`;
      container.querySelector('[data-retry]').addEventListener('click', load);
      showError(error.message);
    }
  }
  return load;
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
