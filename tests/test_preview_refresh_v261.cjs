const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'app/static/app.js'), 'utf8');

function section(start, end) {
  const from = source.indexOf(start);
  const through = source.indexOf(end, from + start.length);
  assert.notEqual(from, -1, `missing section start: ${start}`);
  assert.notEqual(through, -1, `missing section end: ${end}`);
  return source.slice(from, through);
}

test('a movement change invalidates forecasts and reloads the visible preview', async () => {
  const helper = section(
    'async function refreshAfterMovementChange()',
    "$('#preview-day-list').addEventListener('change'",
  );
  const calls = [];
  const refresh = vm.runInNewContext(
    `${helper}\nrefreshAfterMovementChange`,
    {
      invalidateForecastCache() { calls.push('invalidate'); },
      async loadAll() { calls.push('dashboard'); },
      async loadPreview() { calls.push('preview'); },
    },
  );

  await refresh();

  assert.deepEqual(calls, ['invalidate', 'dashboard', 'preview']);
});

test('completion, omission and amount handlers all use the forecast refresh', () => {
  const handlers = section(
    "$('#preview-day-list').addEventListener('change'",
    "$('#dashboard-outlook-panel')",
  );
  assert.equal(
    (handlers.match(/await refreshAfterMovementChange\(\)/g) || []).length,
    3,
  );
  assert.match(handlers, /\/api\/movement-omission/);
  assert.match(handlers, /data-movement-omission/);
  assert.doesNotMatch(handlers, /await loadAll\(\)/);
});
