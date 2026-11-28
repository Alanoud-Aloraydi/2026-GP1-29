/* Cards and report layout for the baseline models, drawn from the shared model list. */
import { BASELINE_MODELS } from '../data/baseline-models.js';
import { bdi, empty, html } from '../core/ui.js';

const PENDING_DATASET = 'سيتوفر عند اكتمال مجموعة البيانات.';

const REPORT_SECTIONS = [
  'الملخص',
  'نقاط القوة',
  'نقاط الضعف',
  'محور الهجوم',
  'محور الرفض الزائد',
  'حسب اللهجة'
];

export const findModel = (id) => BASELINE_MODELS.find((model) => model.id === id);

export const modelCards = () => html`
  <ul class="model-grid">${BASELINE_MODELS.map((model) => html`
    <li>
      <a class="model-card" href="model.html?model=${encodeURIComponent(model.id)}">
        <h2>${bdi(model.name)}</h2>
        <span>عرض التقرير</span>
      </a>
    </li>`)}
  </ul>`;

export const reportSkeleton = () => html`
  <div class="model-report">${REPORT_SECTIONS.map((title) => empty(title, PENDING_DATASET))}</div>`;

export const releaseTwoNotice = () =>
  empty('قريبًا في الإصدار الثاني', 'ستتمكن هنا من اختبار هذا النموذج بنفسك بعد أن قيّمناه على مجموعة البيانات الأساسية.');
