/* Mounting the shared layout replaces navigation without duplicating controls. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const header = {}, footer = {};
const context = vm.createContext({
  window: {},
  document: {querySelector: (selector) => selector === '[data-shell-header]' ? header : footer}
});
for (const file of ['core/ui.js', 'views/run.js', 'views/report-evidence.js', 'views/report.js']) {
  vm.runInContext(fs.readFileSync(require('node:path').join(process.argv[2], file), 'utf8'), context);
}
const view = context.window.HARASS;
view.configureLabels({axes: {AT: "AT", OR: "OR"}, labels: {}, dialects: {}});
view.mountShell(false);
const accountHeader = header.innerHTML;
assert(accountHeader.includes('data-logout'));
assert(accountHeader.includes('evaluation-setup.html'));
view.mountShell(false);
assert.equal(header.innerHTML, accountHeader);
view.mountShell(true);
assert(!header.innerHTML.includes('data-logout'));
assert(header.innerHTML.includes('login.html'));
assert(header.innerHTML.includes('signup.html'));
assert(footer.innerHTML.includes('HARASS'));
