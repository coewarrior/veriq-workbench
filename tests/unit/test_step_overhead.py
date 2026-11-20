"""Isolated protocol/observation checks; no business browser or model calls."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from api_test_tool.managed_browser import ManagedBrowser
from api_test_tool.orchestration import Conflict, digest
from test_direct_execution import setup, claim_ready


def test_inline_begin_is_durable_and_preserves_unknown_guard(tmp_path):
    c, s, owner, project, clock, task = setup(tmp_path)
    ids = claim_ready(c, s, owner, task())
    with c.transaction() as (_, state):
        state['runners']['host']['evidence']['inline_operation_begin'] = 1
    args = {**ids, 'action': 'browser', 'request_id': 'once',
            'browser_action': 'fill', 'parameters': {'selector': 'input', 'value': 'fixture'}}
    s.direct.call(owner, args)
    auth = {'owner': owner, 'host_id': 'host'}
    command = s.host_call(auth, 'direct_poll', {'lease_id': ids['lease_id']})['command']
    assert command['begin_receipt']['execute'] is True
    # A lost delivery never gives this command to a second executor/poll.
    assert s.host_call(auth, 'direct_poll', {'lease_id': ids['lease_id']}) == {}
    op = {'lease_id': ids['lease_id'], 'operation_id': 'once', 'action': 'fill',
          'hash': digest([command['account_id'], 'fill', args['parameters']])}
    assert s.host_call(auth, 'operation_begin', op)['execute'] is False
    with pytest.raises(Conflict):
        s.host_call(auth, 'operation_begin', {**op, 'operation_id': 'other'})
    with pytest.raises(PermissionError):
        s.host_call({'owner': owner, 'host_id': 'other'}, 'direct_poll', {'lease_id': ids['lease_id']})


def test_summary_skips_full_page_but_explicit_observation_is_retained(tmp_path):
    async def run():
        broker = ManagedBrowser(None, tmp_path)
        field = SimpleNamespace(fill=AsyncMock(), aria_snapshot=AsyncMock(return_value='field result'))
        page = SimpleNamespace(url='https://fixture.test', title=AsyncMock(return_value='title'),
                               locator=lambda selector: field)
        broker.pages[('l', 'a')] = page
        broker.contexts[('l', 'a')] = SimpleNamespace(pages=[page])
        broker.active['l'] = {'mode': 'exclusive', 'revoked': False}
        broker._sent = set()
        result = await broker._operate('l', 'a', 'fill', {'selector': 'input', 'value': 'x', 'response': 'summary'}, 'one')
        page.title.assert_not_awaited()
        field.aria_snapshot.assert_not_awaited()
        assert 'tabs' not in result and 'title' not in result
        assert result['observation_omitted'] is True
        assert set(result['timing']) == {'browser_action_seconds', 'observation_seconds', 'session_guard_seconds'}
        scoped = await broker._operate('l', 'a', 'fill', {'selector': 'input', 'value': 'x',
                                      'response': 'summary', 'snapshot_selector': 'input'}, 'two')
        assert scoped['snapshot'] == 'field result'
        full = await broker._operate('l', 'a', 'snapshot', {}, 'three')
        assert full['snapshot'] == 'field result' and full['title'] == 'title' and full['tabs']
    asyncio.run(run())


def test_prefetched_begin_removes_only_duplicate_request(tmp_path):
    async def run():
        broker = ManagedBrowser(None, tmp_path)
        broker.active['l'] = {'mode': 'exclusive', 'revoked': False}
        broker.call = AsyncMock(return_value={'saved': True})
        broker._operate = AsyncMock(return_value={'url': 'https://fixture.test'})
        result = await broker.operate('l', 'a', 'fill', {'value': 'x'}, 'same',
                                     begin_receipt={'execute': True, 'mode': 'exclusive'})
        assert [a.args[0] for a in broker.call.await_args_list] == ['operation_complete']
        assert result['timing']['begin_piggybacked'] is True
        assert broker.last_operation_timing['l']['operation_complete_seconds'] >= 0
        broker._operate.reset_mock()
        result = await broker.operate('l', 'a', 'fill', {'value': 'x'}, 'same',
                                     begin_receipt={'execute': False, 'state': 'confirmed', 'result': {'saved': 'old'}})
        assert result == {'saved': 'old'}
        broker._operate.assert_not_awaited()
    asyncio.run(run())
