const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const app = fs.readFileSync(path.join(root, 'app/static/app.js'), 'utf8');
const index = fs.readFileSync(path.join(root, 'app/static/index.html'), 'utf8');
const styles = fs.readFileSync(path.join(root, 'app/static/styles.css'), 'utf8');

function section(source, start, end) {
  const from = source.indexOf(start);
  const through = source.indexOf(end, from + start.length);
  assert.notEqual(from, -1, `missing section start: ${start}`);
  assert.notEqual(through, -1, `missing section end: ${end}`);
  return source.slice(from, through);
}

test('dashboard hero contains selected account balances for today', () => {
  assert.match(index, /id="dashboard-today-balance-list"/);
  assert.match(index, /HEUTIGE KONTOSTÄNDE/);
  assert.match(styles, /\.dashboard-today-balance-list\s*\{[^}]*repeat\(2,/s);
  assert.match(styles, /\.today-balance-card\s*\{/);
  assert.match(styles, /@media\(max-width:760px\)[\s\S]*?\.hero\s*\{[^}]*grid-template-columns:1fr/s);
});

test('Excel export remains first and today balance selection follows it', () => {
  const exportPanel = index.indexOf('class="panel export-panel"');
  const todayPanel = index.indexOf('class="panel today-balances-settings-panel"');
  const assistantPanel = index.indexOf('class="panel assistant-prefs-panel"');

  assert.ok(exportPanel >= 0);
  assert.ok(todayPanel > exportPanel);
  assert.ok(assistantPanel > todayPanel);
  assert.match(styles, /\.today-balances-settings-panel\s*\{[^}]*grid-column:1\/-1/s);
});

test('today balances use the server forecast for the actual current date', () => {
  const loader = section(
    app,
    'async function loadTodayBalances()',
    'function renderDashboard()',
  );

  assert.match(loader, /const asOf=today\(\)/);
  assert.match(loader, /api\('\/api\/dashboard\/simulation'/);
  assert.match(loader, /as_of:asOf/);
  assert.match(loader, /account_ids:accountIds/);
  assert.doesNotMatch(loader, /dashboardMonth/);
});

test('selection is household specific, limited to four and never empty', () => {
  const selection = section(
    app,
    'function ensureTodayBalanceSelection()',
    'function saveTodayBalanceSelection()',
  );
  const handler = section(
    app,
    "$('#settings-today-balance-accounts').addEventListener",
    "$('#preview-account-selectors').addEventListener",
  );

  assert.match(app, /TODAY_BALANCE_SELECTION_PREFIX/);
  assert.match(app, /TODAY_BALANCE_ACCOUNT_LIMIT=4/);
  assert.match(selection, /liquidDashboardAccounts\(\)/);
  assert.match(selection, /slice\(0,TODAY_BALANCE_ACCOUNT_LIMIT\)/);
  assert.match(handler, /selected\.size<=1/);
  assert.match(handler, /selected\.size>=TODAY_BALANCE_ACCOUNT_LIMIT/);
  assert.match(handler, /loadTodayBalances\(\)/);
});
