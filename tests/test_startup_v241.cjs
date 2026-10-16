const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(
  'app/static/app.js',
  'utf8'
);

const start = source.indexOf('async function api(');
const forecastStart = source.indexOf(
  'const FORECAST_MONTHS=12;', start
);
const end = forecastStart >= 0
  ? forecastStart
  : source.indexOf('function toast(', start);

assert.ok(start >= 0, 'API-Funktion fehlt');
assert.ok(end > start, 'API-Funktionsende fehlt');

const apiCode = source.slice(start, end);

function createApi(fetchMock) {
  const timers = [];

  const context = {
    fetch: fetchMock,
    AbortController,

    setTimeout(callback, delay) {
      const timer = { callback, delay };
      timers.push(timer);
      return timer;
    },

    clearTimeout(timer) {
      timer.cleared = true;
    }
  };

  const api = vm.runInNewContext(
    apiCode + '\napi',
    context
  );

  return { api, timers };
}

function response(data, ok = true) {
  return {
    ok,
    json: async () => data
  };
}

test('GET-Anfrage funktioniert', async () => {
  const { api } = createApi(async () =>
    response({ status: 'ok' })
  );

  const result = await api('/api/households');

  assert.equal(result.status, 'ok');
});

test('API-Fehler werden weitergegeben', async () => {
  const { api } = createApi(async () =>
    response({ error: 'Serverfehler' }, false)
  );

  await assert.rejects(
    api('/api/households'),
    /Serverfehler/
  );
});

test('GET-Timeout nach 60 Sekunden', async () => {
  const { api, timers } = createApi(
    async (url, options) =>
      new Promise((resolve, reject) => {
        options.signal.addEventListener(
          'abort',
          () => reject(new Error('Aborted')),
          { once: true }
        );
      })
  );

  const pending = api('/api/households');

  assert.equal(timers.length, 1);
  assert.equal(timers[0].delay, 60000);

  timers[0].callback();

  await assert.rejects(
    pending,
    /Zeitüberschreitung/
  );
});

test('Startfehler entfernt Ladebildschirm', () => {
  const start = source.indexOf(
    'boot().catch(error=>{'
  );

  assert.ok(start >= 0, 'Startfehlerbehandlung fehlt');

  const end = source.indexOf('});', start);

  assert.ok(end > start, 'Startfehlerbehandlung unvollständig');

  const handler = source.slice(start, end + 3);

  assert.match(
    handler,
    /startupLoader\(false\)/
  );
});
