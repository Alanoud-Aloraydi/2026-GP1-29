/* Mounting the shared layout replaces navigation without duplicating controls. */
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

const header = {};
const footer = {};
globalThis.MutationObserver = class { observe () {} };
globalThis.document = {
  documentElement: {},
  body: { dataset: { page: 'home-test' }, hasAttribute: () => false },
  addEventListener () {},
  querySelectorAll: () => [],
  querySelector: (selector) => selector === '[data-shell-header]' ? header : footer
};

(async () => {
  const { mountShell } = await import(pathToFileURL(path.join(process.argv[2], 'core/bootstrap.js')).href);
  mountShell(false);
  const accountHeader = header.innerHTML;
  assert(String(accountHeader).includes('data-logout'));
  assert(String(accountHeader).includes('evaluation-setup.html'));
  mountShell(false);
  assert.equal(String(header.innerHTML), String(accountHeader));
  mountShell(true);
  assert(!String(header.innerHTML).includes('data-logout'));
  assert(String(header.innerHTML).includes('login.html'));
  assert(String(header.innerHTML).includes('signup.html'));
  assert(String(footer.innerHTML).includes('HARASS'));
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
