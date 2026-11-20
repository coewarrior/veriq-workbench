'use strict';
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');

function page() {
  const context = vm.createContext({
    esc: value => String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;').replaceAll('"', '&quot;'),
    location: {origin: 'https://workspace.example'},
    URL,
  });
  for (const name of ['managed-workflow.js', 'ui-workflow.js']) {
    vm.runInContext(readFileSync(new URL(`../../api_test_tool/static/${name}`, `file://${__filename}`), 'utf8'), context);
  }
  return context;
}

test('platform stop preserves each missing desktop, browser and account acknowledgement', () => {
  const {ManagedWorkflow} = page();
  const html = ManagedWorkflow.renderDesktopStop({
    platform_scheduling_stopped: true,
    manual_stop_required: true,
    required_sessions: [{
      node_id: 'node',
      title: '模块',
      executor_ref: '01a1576c-6fb5-7ce3-9ade-3f4e6c5dab60',
      executor_exit_confirmed: false,
      browser_stopped: null,
      accounts_released: false,
    }],
  }, {id: 'task', revision: 3});
  assert.match(html, /平台已停止后续调度/);
  assert.match(html, /网页不能代替桌面取消模型回合/);
  assert.match(html, /执行者退出：待核实 · 浏览器退出：待核实 · 账号交还：待核实/);
  assert.match(html, /codex:\/\/threads\/01a1576c-6fb5-7ce3-9ade-3f4e6c5dab60/);
  assert.match(html, /data-native-exit="node"/);
  assert.doesNotMatch(html, /全部停止|全部退出|执行已结束/);
});

test('browser exit remains pending after only the executor acknowledges exit', () => {
  const html = page().ManagedWorkflow.renderDesktopStop({
    platform_scheduling_stopped: true,
    manual_stop_required: true,
    required_sessions: [{node_id: 'node', executor_exit_confirmed: true, browser_stopped: false, accounts_released: false}],
  }, {id: 'task', revision: 4});
  assert.match(html, /执行者退出：已确认 · 浏览器退出：待核实 · 账号交还：待核实/);
  assert.match(html, /data-native-exit="node"/);
});

test('unknown or malicious executor references are not turned into navigable links', () => {
  const html = page().ManagedWorkflow.renderDesktopStop({
    platform_scheduling_stopped: true,
    manual_stop_required: true,
    required_sessions: [{title: '<img src=x onerror=alert(1)>', executor_ref: 'javascript:alert(1)', thread_url: 'javascript:alert(1)'}],
  });
  assert.doesNotMatch(html, /href=|<img/);
  assert.match(html, /&lt;img/);
  assert.match(html, /未登记可打开的会话 ID/);
});

test('rendering cannot introduce a stop or release before the platform has stopped scheduling', () => {
  const {ManagedWorkflow} = page();
  assert.equal(ManagedWorkflow.renderDesktopStop({platform_scheduling_stopped: false, manual_stop_required: true}), '');
  const html = ManagedWorkflow.renderDesktopStop({
    platform_scheduling_stopped: true,
    manual_stop_required: false,
    required_sessions: [{node_id: 'node', executor_exit_confirmed: true, browser_stopped: true, accounts_released: true}],
  }, {id: 'task', revision: 4});
  assert.match(html, /账号交还：已交还/);
  assert.doesNotMatch(html, /data-native-exit/);
});

test('new handoff selects native direct browser execution and immediate independent results', () => {
  const {UIWorkflow} = page();
  const html = UIWorkflow.message({id: 'p', title: '目标', ui_target_url: 'https://example.com', task: {goal: '模块完整测试'}}, 'sample');
  assert.match(html, /start_session_test 使用 native_browser/);
  assert.match(html, /已知|已有步骤在一次原生工具调用/);
  assert.match(html, /每条用例独立判定完成后立即增量保存/);
  assert.match(html, /没有账号的会话结束当前回合/);
  assert.match(html, /停止采用 S1/);
  assert.doesNotMatch(html, /claim\(wait_seconds=45\)|lease_binding=|返回 local_browser 后/);
  assert.match(html, /执行中新发现的场景继续追加，不把首版基线当上限/);
});

test('existing runner route remains explicit and is not silently replaced by the native default', () => {
  const html = page().UIWorkflow.message({
    id: 'p', title: '原任务', execution_route: 'local_browser',
    ui_target_url: 'https://example.com', task: {goal: '原范围'},
  }, 'sample');
  assert.match(html, /返回 local_browser 后/);
  assert.match(html, /lease_binding=/);
  assert.doesNotMatch(html, /start_session_test 使用 native_browser/);
});
