/* Page that lists the six baseline models, one card each. */
import { start } from '../core/bootstrap.js';
import { modelCards } from '../views/baseline-models.js';

start(() => {
  document.getElementById('models').innerHTML = modelCards();
});
