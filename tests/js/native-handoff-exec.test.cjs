const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync('api_test_tool/static/native-handoff-exec.js', 'utf8'), context);
const run = context.completeNativeHandoff;
const original = {action:'finish', holder_id:'worker', lease_id:'original-lease', arguments:{browser_stopped:true}};

function fixture() {
  let state = 'pending', beginCount = 0;
  const calls = [];
  const event = () => ({id:'release', delivery_state:state, message_tool:'send_message_to_thread',
    message_arguments:{threadId:'original-thread', prompt:'consume original event'}});
  const call = async args => {
    const status = args.arguments?.handoff_delivery?.state;
    calls.push(status || 'read');
    if (status === 'sending') {
      const authorized = state === 'pending';
      if (authorized) { state = status; beginCount++; }
      return {handoff:{...event(), send_authorized:authorized}};
    }
    if (status) state = status;
    return {handoff:event()};
  };
  return {call, calls, state:()=>state, begins:()=>beginCount};
}

test('one real send and one confirmed receipt happen in the same execution', async () => {
  const f = fixture(); let messages = 0;
  await run(f.call, original, async args => { messages++; return {threadId:args.threadId}; });
  assert.deepEqual(f.calls, ['read','sending','sent']);
  assert.equal(messages, 1);
  assert.equal(f.state(), 'sent');
});

test('publication survives delivery ACK without resubmitting final observations', async () => {
  const f = fixture();
  const publication = {phase:'published', revision:4, report:{id:'report'}};
  let first = true;
  const result = await run(async args => {
    if (first) {
      first = false;
      assert.equal(args.arguments.final_report.summary, 'observed');
      return {...await f.call(args), publication};
    }
    assert.equal(args.arguments.final_report, undefined);
    return f.call(args);
  }, {...original, arguments:{...original.arguments, final_report:{summary:'observed'}}},
  async args => ({threadId:args.threadId}));
  assert.equal(result.publication, publication);
  assert.deepEqual(f.calls, ['read','sending','sent']);
});

test('lost begin cannot send', async () => {
  let messages = 0;
  const result = await run(async args => {
    if (args.arguments.handoff_delivery) throw Error('lost response');
    return fixture().call(args);
  }, original, async () => { messages++; });
  assert.equal(messages, 0);
  assert.equal(result.needs_handoff, true);
  assert.equal(result.handoff_failures[0].failure_stage, 'delivery_begin');
  assert.equal(result.handoff_failures[0].failure_persisted, false);
});

test('unknown desktop response is persisted and never resent', async () => {
  const f = fixture(); let messages = 0;
  const send = async () => { messages++; return {threadId:'original-thread', status:'unknown'}; };
  await run(f.call, original, send);
  await run(f.call, original, send);
  assert.equal(f.state(), 'unknown');
  assert.equal(messages, 1);
});

test('rejection wins over target echo and is never retried', async () => {
  const f = fixture(); let messages = 0;
  const send = async () => { messages++; return {threadId:'original-thread', isError:true}; };
  await run(f.call, original, send);
  await run(f.call, original, send);
  assert.equal(f.state(), 'blocked');
  assert.equal(messages, 1);
});

test('lost receipt leaves durable sending fence, not another send', async () => {
  const f = fixture(); let messages = 0;
  const call = async args => {
    if (args.arguments.handoff_delivery?.state === 'sent') throw Error('lost receipt');
    return f.call(args);
  };
  const send = async () => { messages++; return {threadId:'original-thread'}; };
  await run(call, original, send);
  await run(call, original, send);
  assert.equal(f.state(), 'sending');
  assert.equal(messages, 1);
});

test('no available successor does not invoke desktop messaging', async () => {
  let messages = 0;
  await run(async () => ({accepted:true, continuation:null}), {action:'dispatch'},
    async () => { messages++; });
  assert.equal(messages, 0);
});

test('one execution sends each admitted successor once and never repeats module offers', async () => {
  const states = {first:'pending', second:'pending'}, messages = [];
  const call = async args => {
    const update = args.arguments?.handoff_delivery;
    if (update) {
      assert.equal(args.arguments.modules, undefined);
      states[update.event_id] = update.state;
    }
    return {send_authorized: update?.state === 'sending',
      continuations: Object.entries(states).map(([id, delivery_state]) => ({
        id, delivery_state, message_tool:'send_message_to_thread',
        message_arguments:{threadId:id, prompt:'resume original worker'}
      }))};
  };
  const result = await run(call, {action:'dispatch', arguments:{handoff_ack:{}, modules:[{node_id:'original'}]}},
    async args => { messages.push(args.threadId); return {threadId:args.threadId}; });
  assert.deepEqual(messages, ['first','second']);
  assert.equal(result.needs_handoff, false);
});


test('bound closeout delivers successor before report publication', async () => {
  const f = fixture(), order = [];
  const publication = {phase:'published', revision:4};
  const initial = {...original, arguments:{browser_stopped:true, publish_saved:true,
    publication_binding:{project_id:'project', execution_id:'execution', revision:3}}};
  const result = await run(async args => {
    if (args.record_action === 'publish') {
      order.push('publish');
      assert.equal(args.arguments.execution_id, 'execution');
      assert.equal(args.lease_id, original.lease_id);
      return {publication};
    }
    if (!args.arguments.handoff_delivery) {
      order.push('release');
      assert.equal(args.arguments.publish_saved, false);
      assert.equal(args.arguments.report_pending, true);
    }
    return {...await f.call(args), released:true};
  }, initial, async args => {order.push('notify');return {threadId:args.threadId};});
  assert.deepEqual(order, ['release','notify','publish']);
  assert.equal(result.publication, publication);
});

test('confirmed publication survives failure beginning its final notification', async () => {
  const publication = {phase:'published', revision:4};
  let published = false;
  const initial = {...original, arguments:{browser_stopped:true, publish_saved:true,
    publication_binding:{project_id:'project', execution_id:'execution', revision:3}}};
  const result = await run(async args => {
    if (args.record_action === 'publish') {
      published = true;
      return {publication, handoff:{id:'summary', delivery_state:'pending',
        message_tool:'send_message_to_thread', message_arguments:{threadId:'coordinator'}}};
    }
    if (published) throw Error('lost delivery begin');
    return {released:true};
  }, initial, async () => {throw Error('must not send after lost begin');});
  assert.equal(result.publication, publication);
  assert.equal(result.needs_handoff, true);
  assert.equal(result.handoff_failures[0].failure_stage, 'delivery_begin');
  assert.equal(result.handoff_failures[0].failure_persisted, false);
});
