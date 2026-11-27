/* Pending initialization cannot send credential fields through a native form request. */
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

let listener;
const form = { addEventListener: (name, callback) => { listener = callback; } };
// The account request never answers, so initialization stays pending.
globalThis.fetch = () => new Promise(() => {});
globalThis.window = { addEventListener () {} };
globalThis.MutationObserver = class { observe () {} };
globalThis.document = {
  documentElement: {},
  body: { dataset: { page: 'model-configuration' }, hasAttribute: () => false },
  addEventListener () {},
  querySelector: () => null,
  querySelectorAll: (selector) => selector === 'form' ? [form] : []
};

(async () => {
  const { start } = await import(pathToFileURL(path.join(process.argv[2], 'core/bootstrap.js')).href);
  start(() => {});
  assert.equal(typeof listener, 'function');
  let prevented = false;
  listener({ preventDefault: () => { prevented = true; } });
  assert(prevented);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
