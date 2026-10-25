/* Pending initialization cannot send credential fields through a native form request. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let prevented = false;
let listener;
const form = {addEventListener: (name, callback) => {listener = callback;}};
const context = vm.createContext({
  window: {
    HARASS_API: {me: () => new Promise(() => {})},
    HARASS: {mountShell: () => {}}, addEventListener: () => {}
  },
  document: {
    body: {dataset: {page: 'model-configuration'}},
    querySelectorAll: (selector) => selector === 'form' ? [form] : []
  }
});
vm.runInContext(fs.readFileSync(require('node:path').join(process.argv[2], 'core/bootstrap.js'), 'utf8'), context);
assert.equal(typeof listener, 'function');
listener({preventDefault: () => {prevented = true;}});
assert(prevented);
