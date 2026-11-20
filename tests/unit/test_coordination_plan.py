"""Notification planning is state based; these tests never send desktop messages."""
from copy import deepcopy

from api_test_tool.module_dispatch import coordination_plan, dispatch_view
from test_native_handoff import consume, environment


def node(key, state='running', **extra):
    return {'id': key, 'task_id': 'task', 'state': state,
            'executor_dispatch': {'holder_id': 'holder-' + key,
                                  'executor_ref': 'thread-' + key}, **extra}


def test_sibling_identity_issue_never_interrupts_running_modules():
    nodes = [node('skills', 'blocked', reason='当前身份尚未核实'),
             node('knowledge'), node('jd'), node('career')]
    original = deepcopy(nodes)
    plan = coordination_plan(nodes)
    assert not plan['worker_actions'] and not plan['continuations']
    assert [item['node_id'] for item in plan['coordinator_only']] == ['skills']
    assert [item['node_id'] for item in plan['keep_running']] == ['knowledge', 'jd', 'career']
    assert nodes == original
    assert plan['automatic_delivery'] is False


def test_stop_controls_cover_every_affected_worker_but_do_not_repeat_received():
    nodes = [node(key, 'stopping', executor_controls={key: {
        'id': key, 'action': 'stop', 'state': 'pending', 'holder_id': 'holder-' + key,
        'executor_ref': 'thread-' + key}}) for key in ('knowledge', 'jd', 'career', 'skills')]
    plan = coordination_plan(nodes)
    assert {item['node_id'] for item in plan['worker_actions']} == {item['id'] for item in nodes}
    assert all(item['action'] == 'stop' for item in plan['worker_actions'])
    nodes[0]['executor_controls']['knowledge']['state'] = 'received'
    next_plan = coordination_plan(nodes)
    assert len(next_plan['worker_actions']) == 3
    assert next_plan['coordinator_only'][0]['node_id'] == 'knowledge'
    assert next_plan['coordinator_only'][0]['control_ids'] == ['knowledge']
    # The plan is read-only: a receipt is never fabricated by generating it.
    assert nodes[0]['executor_controls']['knowledge']['state'] == 'received'


def test_pause_and_timeout_are_not_filtered_as_normal_chatter():
    nodes = [node(key, executor_controls={key: {
        'id': key, 'action': key, 'state': 'pending', 'holder_id': key}})
        for key in ('pause', 'timeout')]
    plan = coordination_plan(nodes)
    assert {item['action'] for item in plan['worker_actions']} == {'pause', 'timeout'}
    assert not plan['keep_running']


def test_only_original_pending_resume_is_a_target_no_unknown_replay():
    events = [{'id': state, 'task_id': 'task', 'node_id': state,
               'kind': 'resume_original_worker', 'delivery_state': state,
               'delivery_required': True, 'message_arguments': {'threadId': state}}
              for state in ('pending', 'sending', 'unknown', 'sent', 'received', 'obsolete')]
    nodes = [node(event['node_id'], 'queued') for event in events]
    plan = coordination_plan(nodes, events)
    assert [item['id'] for item in plan['continuations']] == ['pending']
    assert not plan['worker_actions']
    assert all(item['node_id'] != 'pending' for item in plan['coordinator_only'])
    assert {item['node_id'] for item in plan['coordinator_only']} == {
        'sending', 'unknown', 'sent', 'received', 'obsolete'}


def test_dependency_wait_is_not_a_wakeup_or_reason_to_message_other_workers():
    nodes = [node('source', 'blocked'), node('dependent', 'queued', depends_on=['source']),
             node('unrelated')]
    plan = coordination_plan(nodes)
    assert not plan['worker_actions'] and not plan['continuations']
    assert [item['node_id'] for item in plan['keep_running']] == ['unrelated']
    assert [item['node_id'] for item in plan['coordinator_only']] == ['source', 'dependent']


def test_dispatch_and_consumed_handoff_expose_current_plan(tmp_path):
    c, service, owner, _, _, requests, finish = environment(tmp_path)
    view = dispatch_view(c, owner, finish['task_id'])
    assert [item['node_id'] for item in view['coordination_plan']['keep_running']] == [requests[0]['node_id']]
    event = service.direct.call(owner, finish)['handoff']
    result = consume(c, owner, finish, event)
    assert result['coordination_plan']['policy'] == 'targeted_state_change_only'
    assert not result['coordination_plan']['worker_actions']
    assert not result['coordination_plan']['keep_running']
    assert result['handoff']['delivery_state'] == 'received'
