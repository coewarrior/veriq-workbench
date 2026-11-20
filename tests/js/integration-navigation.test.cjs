const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../../api_test_tool/static/integration-back.js'), 'utf8');

function loadPage(historyLength) {
  const back = { onclick: null };
  let backCalls = 0;
  const document = { querySelector: selector => selector === '[data-integration-back]' ? back : null };
  const history = { length: historyLength, back: () => { backCalls += 1; } };
  vm.runInNewContext(source, { document, history });
  return { back, backCalls: () => backCalls };
}

test('integration settings return to the actual previous page when browser history exists', () => {
  const page = loadPage(2);
  let prevented = false;
  page.back.onclick({ preventDefault: () => { prevented = true; } });
  assert.equal(prevented, true);
  assert.equal(page.backCalls(), 1);
});

test('integration settings keep the home href fallback without a previous page', () => {
  const page = loadPage(1);
  let prevented = false;
  page.back.onclick({ preventDefault: () => { prevented = true; } });
  assert.equal(prevented, false);
  assert.equal(page.backCalls(), 0);
});
