/* One baseline model's page: its report tab and the release-two testing tab. */
import { start } from '../core/bootstrap.js';
import { empty } from '../core/ui.js';
import { findModel, releaseTwoNotice, reportSkeleton } from '../views/baseline-models.js';

function selectTab (tabs, chosen) {
  tabs.forEach((tab) => {
    const selected = tab === chosen;
    tab.setAttribute('aria-selected', String(selected));
    tab.tabIndex = selected ? 0 : -1;
    document.getElementById(tab.getAttribute('aria-controls')).hidden = !selected;
  });
}

// Arrow keys move between tabs, following the WAI-ARIA tabs pattern; the
// visual order is right to left, so the left arrow goes to the next tab.
function bindTabs () {
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => selectTab(tabs, tab));
    tab.addEventListener('keydown', (event) => {
      const step = { ArrowLeft: 1, ArrowRight: -1 }[event.key];
      if (!step) return;
      const next = tabs[(index + step + tabs.length) % tabs.length];
      selectTab(tabs, next);
      next.focus();
    });
  });
}

function modelPage () {
  const model = findModel(new URLSearchParams(location.search).get('model'));
  if (!model) {
    const missing = document.getElementById('modelMissing');
    missing.innerHTML =
      empty('النموذج غير موجود', 'اختر نموذجًا من قائمة النماذج الأساسية.', 'models.html', 'النماذج الأساسية');
    missing.hidden = false;
    return;
  }
  document.title = model.name + ' — HARASS';
  document.getElementById('modelTitle').textContent = model.name;
  document.getElementById('reportPanel').innerHTML = reportSkeleton();
  document.getElementById('testPanel').innerHTML = releaseTwoNotice();
  document.getElementById('modelTabs').hidden = false;
  bindTabs();
}

start(modelPage);
