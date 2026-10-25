/* Validate native HTML while allowing named checkbox groups. */
module.exports = {
  extends: ['html-validate:recommended'],
  rules: {
    'form-dup-name': ['error', { shared: ['radio', 'checkbox', 'submit', 'button', 'reset'] }]
  }
};
