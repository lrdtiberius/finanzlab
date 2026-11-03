const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const index = fs.readFileSync(path.join(root, 'app/static/index.html'), 'utf8');
const styles = fs.readFileSync(path.join(root, 'app/static/styles.css'), 'utf8');
const refinements = fs.readFileSync(
  path.join(root, 'app/static/refinements.css'),
  'utf8',
);
const app = fs.readFileSync(path.join(root, 'app/static/app.js'), 'utf8');
const archive = fs.readFileSync(
  path.join(root, 'app/static/credit-archive.js'),
  'utf8',
);

test('finance assistant spans the settings grid before household and people', () => {
  const assistant = index.indexOf('class="panel assistant-prefs-panel"');
  const household = index.indexOf('class="panel household-panel"');
  const people = index.indexOf('class="panel persons-panel"');
  assert.ok(assistant >= 0 && household > assistant && people > household);
  assert.match(
    refinements,
    /\.assistant-prefs-panel\s*\{\s*grid-column\s*:\s*1\s*\/\s*-1\s*\}/,
  );
});

test('backup cards stay three columns wide and only twelve are rendered', () => {
  assert.match(
    styles,
    /#backup-list\s*\{[^}]*grid-template-columns:\s*repeat\(3,/s,
  );
  assert.match(app, /state\.backups=\(backups\.items\|\|\[\]\)\.slice\(0,12\)/);
  assert.match(archive, /const backups=\(state\.backups\|\|\[\]\)\.slice\(0,12\)/);
  assert.match(index, /Aufbewahrt werden immer die 12/);
});
