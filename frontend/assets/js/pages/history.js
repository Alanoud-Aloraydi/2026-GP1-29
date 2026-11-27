/* Paged list of the account's evaluations. */
import { api } from '../core/api-client.js';
import { start } from '../core/bootstrap.js';
import { pagedList } from '../core/forms.js';
import { busy, empty } from '../core/ui.js';
import { runTable } from '../views/run.js';

async function historyPage () {
  const button = document.getElementById('reload');
  const load = pagedList({
    container: document.getElementById('history'),
    prefix: 'history',
    fetchPage: api.runPage,
    render: runTable,
    empty: empty('لا توجد تقييمات بعد', 'ابدأ أول تقييم ليظهر تقريره هنا.', 'evaluation-setup.html', 'تقييم جديد'),
    failureText: 'تعذّر تحميل السجل.'
  });
  const reload = async () => {
    busy(button, true);
    await load();
    busy(button, false);
  };
  button.addEventListener('click', reload);
  await reload();
}

start(historyPage);
