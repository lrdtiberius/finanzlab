const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const app = fs.readFileSync(path.join(root, 'app/static/app.js'), 'utf8');
const archive = fs.readFileSync(
  path.join(root, 'app/static/credit-archive.js'),
  'utf8',
);
const index = fs.readFileSync(path.join(root, 'app/static/index.html'), 'utf8');

function section(source, start, end) {
  const from = source.indexOf(start);
  const through = source.indexOf(end, from + start.length);
  assert.notEqual(from, -1, `missing section start: ${start}`);
  assert.notEqual(through, -1, `missing section end: ${end}`);
  return source.slice(from, through);
}

test('startup uses the core lazy loadAll implementation', () => {
  assert.doesNotMatch(archive, /loadAll\s*=\s*async function/);
  assert.doesNotMatch(archive, /originalLoadAllV15/);

  const loadAll = section(app, 'async function loadAll()', 'function ensureSelections');
  assert.match(loadAll, /forecastDashboard\(householdId/);
  assert.match(loadAll, /&summary=1/);
  assert.match(loadAll, /state\.archivedCredits=credits\.archived_items\|\|\[\]/);
  assert.doesNotMatch(loadAll, /api\(`\/api\/diagnostics/);
  assert.doesNotMatch(loadAll, /api\('\/api\/backups/);
  assert.doesNotMatch(loadAll, /api\(`\/api\/interest/);
  assert.doesNotMatch(loadAll, /api\(`\/api\/integrations\/energylab/);
});

test('dashboard reuses server-calculated credit summaries', () => {
  const forecast = section(app, 'function forecastDashboard', 'function forecastPreview');
  assert.match(forecast, /dashboard\.credit_items/);
  assert.match(forecast, /simulate_future=1&summary=1/);
  assert.doesNotMatch(forecast, /Promise\.all/);
});

test('settings-only data stays in the lazy supplemental loader', () => {
  const loader = section(
    app,
    'async function loadSettingsSupplemental',
    'function summaryCard',
  );
  assert.match(loader, /\/api\/diagnostics/);
  assert.match(loader, /\/api\/integrations\/energylab\?/);
  assert.match(loader, /\/api\/integrations\/energylab\/status\?/);
  assert.match(loader, /api\('\/api\/backups'\)/);
});

test('interest requests are lazy and coalesced', () => {
  assert.match(archive, /async function loadInterest\(force=false\)/);
  assert.match(archive, /interestPending\?\.key===key/);
  assert.match(archive, /forecastCache\.revision/);
  assert.doesNotMatch(archive, /await originalLoadAllV15/);
});

test('summary credits always load full details before payment history is used', () => {
  assert.match(
    archive,
    /openCredit=async function\(item=null\).*?\/api\/credits\/\$\{encodeURIComponent\(item\.id\)\}/s,
  );
  const paymentHandler = section(
    app,
    "$('#credit-edit-payment-submit')",
    "$('#credit-form').addEventListener",
  );
  assert.match(paymentHandler, /const updated=await api\(`\/api\/credits\//);
  assert.match(paymentHandler, /state\.editingCreditSnapshot=updated/);
});

test('legacy compatibility observer is scoped to its one target', () => {
  assert.doesNotMatch(app, /document\.querySelectorAll\('\*'\)/);
  const compatibility = section(
    app,
    'function hideLegacyFinancingError1613',
    "if(document.readyState==='loading')",
  );
  assert.match(compatibility, /querySelector\('#credit-plan-check'\)/);
  assert.match(compatibility, /observer\.observe\(target/);
  assert.doesNotMatch(compatibility, /observer\.observe\(document\.body/);
});

test('HTML branding and asset cache keys are supplied by the server', () => {
  assert.match(index, /<title>\{\{ENV_TITLE_PREFIX\}\}Haushaltsplaner/);
  assert.match(index, /\{\{TEST_BANNER\}\}/);
  assert.equal((index.match(/\?v=\{\{APP_VERSION\}\}/g) || []).length, 4);
  assert.doesNotMatch(index, /2\.5\.7/);
});
