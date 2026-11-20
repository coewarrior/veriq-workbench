"""Desktop Codex owns browser actions. The platform allocates accounts and stores results.

There is deliberately no browser command transport, action permission endpoint,
heartbeat, or model wake-up loop here. S1 exit receipts are explicitly reports,
not claims that this server cancelled a desktop turn.
"""
from __future__ import annotations

import copy
import time
from contextlib import contextmanager

from .orchestration import Conflict, text
from .resource_projection import copy_node
from .orchestration_storage import read_entries, read_metadata_without_history


class NativeExecution:
    RECORD_ACTIONS = {
        'record', 'cases', 'assets', 'publish', 'reference',
        'requirements', 'save_requirements', 'dependency', 'fixture',
    }

    def __init__(self, direct):
        self.direct = direct
        self.service = direct.service
        self.c = direct.c

    def applies(self, owner, args):
        with self.c.connect() as db:
            # Keep the original lease -> settlement -> node -> task fallback,
            # returning only routing fields rather than archived case bodies.
            db.execute('BEGIN')
            nid = args.get('node_id')
            if args.get('lease_id') is not None:
                for section in ('leases', 'direct_settlements'):
                    entry = next(iter(read_entries(db, section, keys=[args['lease_id']]).values()), {})
                    value = entry.get('node_id')
                    if value is not None and value != '' and value != 0:
                        nid = value
                        break
            tid = args.get('task_id')
            if nid is not None:
                node = next(iter(read_entries(db, 'nodes', keys=[nid]).values()), {})
                value = node.get('task_id')
                if value is not None and value != '' and value != 0:
                    tid = value
            task = next(iter(read_entries(db, 'tasks', keys=[tid]).values()), {}) if tid is not None else {}
        return bool(task and task.get('owner') == owner and task.get('execution_route') == 'native_browser')

    @contextmanager
    def _authorization_state(self, *, writable, timing=None, work_records=False, baseline_lease_id=None):
        if writable:
            started = time.perf_counter()
            with self.c.transaction(work_records=work_records) as (_, state):
                if timing is not None:
                    timing['authorization_wait_and_read_seconds'] = round(time.perf_counter() - started, 6)
                try:
                    yield state
                finally:
                    body_finished = time.perf_counter()
            if timing is not None:
                timing['authorization_commit_seconds'] = round(time.perf_counter() - body_finished, 6)
        else:
            # These actions only check the holder here; the host call retains
            # its own current lease check. Do not serialize all scheduler state
            # twice or acquire a write lock for this read-only authorization.
            started = time.perf_counter()
            with self.c.connect() as db:
                db.execute('BEGIN')
                state = read_metadata_without_history(db)
                if state.get('version') != 1:
                    raise Conflict('调度数据版本不兼容，拒绝写入；需按迁移方案恢复')
                if baseline_lease_id is not None:
                    binding = state['leases'].get(baseline_lease_id) or state.get('direct_settlements', {}).get(baseline_lease_id, {})
                    node = state['nodes'].get(binding.get('node_id'))
                    if node:
                        state['tasks'].update(read_entries(db, 'tasks', keys=[node['task_id']],
                            include_baseline=True, baseline_fields=('cases', 'sources')))
                if timing is not None:
                    timing['authorization_wait_and_read_seconds'] = round(time.perf_counter() - started, 6)
                    timing['authorization_commit_seconds'] = 0.0
                yield state

    @staticmethod
    def status(node, lease):
        from .module_dispatch import node_dispatch
        from .native_state import browser_launch_policy
        from .native_handoff import execution_contract
        ready = bool(lease and not lease.get('revoked') and node['state'] == 'running')
        binding = copy.deepcopy((lease or {}).get('native_context_binding') or {})
        result = {
            'mode': 'native_browser', 'executor': 'current_codex',
            'task_id': node['task_id'], 'node_id': node['id'], 'state': node['state'],
            'reason': node.get('reason', ''), 'lease_id': lease['id'] if lease else None,
            'account_ids': list(lease['account_ids']) if lease else [],
            'resource_mode': lease.get('mode') if lease else None,
            'account_ready': ready,
            # Allocation is not evidence that a browser was opened.
            'browser_ready': ready and binding.get('login_state') == 'verified',
            'context_reserved': bool(ready and binding),
            'native_context_binding': binding,
            'login_state': binding.get('login_state', 'unverified'),
            'browser_launch': browser_launch_policy(binding),
            'handoff_execution': execution_contract(node),
            'business_started': bool(node.get('business_started_at')),
            'next_action': 'context' if ready else 'end_turn_until_resources',
            **node_dispatch(node),
        }
        if not lease and node.get('execution_disposition') == 'multi_account_excluded':
            from .testing_policy import excluded_response
            result.update(excluded_response())
        if not lease and node['state'] == 'queued' and not result.get('excluded'):
            result['resource_wait'] = {
                **node.get('resource_wait', {}), 'end_turn': True,
                'task_id': node['task_id'], 'node_id': node['id'],
                'instruction': '结束当前轮次。资源可用后再唤醒原会话领取，不轮询、不反复 claim。',
            }
        if (node.get('native_executor_status') or {}).get('state') == 'unavailable':
            result.update(model_ready=False, next_action='resolve_existing_hold' if lease else 'end_turn_until_model_available')
        if lease and lease.get('revoked'):
            result.update(next_action='desktop_manual_stop', manual_stop_required=True,
                          released=False, authority_revoked=True)
        return result

    def claim(self, owner, args, holder):
        from .module_dispatch import receive
        from .resource_holds import settle
        settle(self.c)
        started = time.perf_counter()
        with self.c.transaction(work_records=True) as (db, state):
            locked = time.perf_counter()
            task = self.c.owned(state['tasks'], owner, args.get('task_id'))
            if task['intent'] != 'run':
                raise Conflict('任务已停止或暂停；领取账号不会恢复测试')
            nodes = [state['nodes'][nid] for nid in task['node_ids']
                     if not state['nodes'][nid].get('child_ids')]
            if args.get('node_id'):
                nodes = [node for node in nodes if node['id'] == args['node_id']]
                from .testing_policy import node_excluded, excluded_response
                if nodes and node_excluded(nodes[0], state):
                    return excluded_response(node_id=nodes[0]['id'], task_id=task['id'])
            nodes = [node for node in nodes if node.get('control_intent', 'run') == 'run'
                     and node['state'] in {'queued', 'running'}]
            mine = [node for node in nodes if node.get('direct_holder') == holder]
            free = [node for node in nodes if not node.get('direct_holder')]
            node = next(iter(mine or free), None)
            if node is None:
                return {'mode': 'native_browser', 'state': 'unavailable',
                        'resource_wait': {'end_turn': True},
                        'next_action': 'end_turn_until_resources'}
            self.c.sessions.assert_available(state, task, [node['id']])
            if node.get('checkpoint', {}).get('work_plan'):
                from .native_work_plan import validate_token, apply_selection, TOKEN_FIELDS
                selected = validate_token(self.c, state, node, (args.get('arguments') or {}).get('work_token'))
                if selected['eligibility'] == 'excluded':
                    from .testing_policy import excluded_response
                    return excluded_response(node_id=node['id'], task_id=task['id'])
                active = next((l for l in state['leases'].values() if l['node_id'] == node['id']), None)
                protected = node.get('work_protection') if node.get('protected') else None
                if ((active and any((node.get('work_selection') or {}).get(k) != selected[k] for k in TOKEN_FIELDS))
                        or (protected and any(protected.get(k) != selected[k] for k in TOKEN_FIELDS))):
                    raise Conflict('原租约或公平保护属于其他阶段；在实际资源边界申请，不通过重复领取改写阶段')
                apply_selection(node, selected)
                node['_work_claim_token'] = copy.deepcopy((args.get('arguments') or {})['work_token'])
            requested = args.get('account_ids')
            if requested is not None:
                if not isinstance(requested, list) or len(set(requested)) != len(requested):
                    raise ValueError('account_ids 必须是无重复列表')
                project_id = task.get('account_project_id') or task['project_id']
                if any(aid not in state['accounts'] or state['accounts'][aid]['owner'] != owner
                       or project_id not in state['accounts'][aid]['projects'] for aid in requested):
                    raise PermissionError('账号不属于当前项目')
                from .resource_scheduler import apply_account_selection
                selection = (args.get('arguments') or {}).get('account_selection', args.get('account_selection') or 'required')
                planned = copy_node(node)
                apply_account_selection(planned, requested, selection)
                from .testing_policy import resource_excluded, excluded_response
                if resource_excluded(planned, state):
                    return excluded_response(node_id=node['id'], task_id=task['id'])
                if node['state'] != 'queued' and any(planned.get(key, []) != node.get(key, [])
                        for key in ('requested_account_ids', 'preferred_account_ids')):
                    raise Conflict('已领取后在实际资源边界申请完整账号集合')
                if node.get('checkpoint', {}).get('work_plan'):
                    if node.get('requested_account_ids') and set(requested) != set(node['requested_account_ids']):
                        raise Conflict('领取账号与阶段完整集合不一致')
                else:
                    apply_account_selection(node, requested, selection)
            from .testing_policy import node_excluded, excluded_response
            if node_excluded(node, state):
                return excluded_response(node_id=node['id'], task_id=task['id'])
            receive(state, node, holder, self.c.clock(),
                    executor_ref=args.get('executor_ref', ''),
                    coordinator_ref=args.get('coordinator_ref', ''),
                    dispatch_id=args.get('dispatch_id', ''))
            from .native_executor_status import received
            received(node, self.c.clock())
            from .native_handoff import consume_on_claim
            consume_on_claim(state, node, self.c.clock())
            node['direct_holder'] = holder
            existing = next((l for l in state['leases'].values() if l['node_id'] == node['id']), None)
            values = args.get('arguments') or {}
            environments = values.get('browser_environments')
            if environments is None:
                environments = [values['browser_environment']] if values.get('browser_environment') else []
            if not isinstance(environments, list):
                raise ValueError('browser_environments 必须是实际浏览器环境列表')
            replacement = values.get('native_environment_replacement')
            if replacement and existing:
                if not isinstance(replacement, dict) or replacement.get('lease_id') != existing['id']:
                    raise Conflict('环境替换不属于当前原租约；不能覆盖其他活动绑定')
                from .native_contexts import replace_exited_environment
                replace_exited_environment(state, node, existing, owner,
                    {k: copy.deepcopy(v) for k, v in replacement.items() if k != 'lease_id'}, self.c.clock())
            if (not existing and task.get('native_browser_policy') == 'direct_isolated'
                    and node.get('requires_account') is not False and node.get('phase') != 'report'):
                registered = [state.get('native_browser_environments', {}).get(key, {})
                              for key in node.get('native_environment_keys', [])]
                candidates = environments or registered
                if not candidates or any(not isinstance(e, dict) or e.get('isolation') != 'isolated' for e in candidates):
                    raise ValueError('新任务默认直接隔离浏览器；先执行当前 native-run-kit 返回的 environment_setup，'
                                     '再用原 prepare 领取账号。无需用户填写浏览器配置，不回退共享 IAB。')
            # In-flight legacy leases keep their existing scene. Every new
            # allocation must account for actual login context capacity.
            if not existing:
                node['native_context_protocol'] = 1
            if environments and (not existing or existing.get('native_context_binding')):
                from .native_contexts import register_environment
                if not existing:
                    node['native_environment_keys'] = []
                    node.pop('native_environment', None)
                for environment in environments:
                    register_environment(state, node, owner, environment)
            if node['state'] == 'queued' and not any(l['node_id'] == node['id'] for l in state['leases'].values()):
                node['native_claim_pending'] = True
            nid = node['id']
            self.c._schedule_in_transaction(db, state)
            node.pop('_work_claim_token', None)
            lease = next((item for item in state['leases'].values() if item['node_id'] == nid), None)
            result = self.status(state['nodes'][nid], lease)
            decided = time.perf_counter()
        result['server_processing_timing'] = {
            'snapshot_and_lock_wait_seconds': round(locked - started, 6),
            'transaction_decision_seconds': round(decided - locked, 6),
            'commit_seconds': round(time.perf_counter() - decided, 6)}
        return result

    def call(self, owner, args):
        action = args.get('action')
        holder = text(args.get('holder_id'), 'holder_id', 160)
        if action == 'work_plan':
            from .native_source_plan import call
            return call(self, owner, args)
        if action == 'cleanup':
            from .native_cleanup import call
            return call(self, owner, args)
        if action == 'claim':
            return self.claim(owner, args, holder)
        if action == 'dispatch':
            from .module_dispatch import offer_modules
            return offer_modules(self.c, owner, args)
        if action == 'context' and not args.get('lease_id'):
            if (args.get('arguments') or {}).get('work_token') is not None:
                return self.work_ready(owner, args)
            return self.direct._context_without_lease(owner, args)
        if action == 'finish' and not args.get('lease_id'):
            return {**self.direct.finish_unallocated(owner, args), 'mode': 'native_browser'}
        if action not in {'context', 'credentials', 'record', 'checkpoint', 'request_resources', 'finish'}:
            raise ValueError('原生路线由 Codex 直接操作浏览器；平台仅提供 claim/context/credentials/record/checkpoint/request_resources/finish，不中转浏览器动作或轮询')
        released_scope = None
        reconciled_from = None
        server_timing = {} if action == 'finish' else None
        needs_baseline = ((action == 'finish' and (args.get('arguments') or {}).get('final_report') is not None)
                          or (action == 'record' and args.get('record_action') == 'publish'))
        with self._authorization_state(writable=action == 'checkpoint', timing=server_timing,
                work_records=action == 'checkpoint' and 'work_plan' in (args.get('checkpoint') or {}),
                baseline_lease_id=args.get('lease_id') if needs_baseline else None) as state:
            ended = state.get('direct_settlements', {}).get(args.get('lease_id'))
            if ended and action == 'record':
                released_scope = self.released_report_scope(state, owner, args, ended)
            elif ended and action == 'finish':
                if ended['owner'] != owner or ended['holder_id'] != holder:
                    raise PermissionError('回执不属于当前聊天')
            else:
                lease, node, task = self.direct._owned(
                    state, owner, args, active=(action in {'credentials', 'request_resources'} or
                        (action == 'context' and bool((args.get('arguments') or {}).get('reconcile_from_lease_id'))) or
                        (action == 'checkpoint' and 'native_environment_replacement' in (args.get('checkpoint') or {}))))
                lid, hid = lease['id'], lease['runner_id']
                prior_id = (args.get('arguments') or {}).get('reconcile_from_lease_id') if action == 'context' else None
                if prior_id:
                    from .native_identity import same_executor_ref
                    prior = state.get('direct_settlements', {}).get(prior_id) or {}
                    bound = prior.get('report_binding') or {}
                    dispatch = node.get('executor_dispatch') or {}
                    if (prior.get('owner') != owner or prior.get('holder_id') != holder
                            or prior.get('node_id') != node['id'] or not prior.get('native_browser')
                            or node.get('record_successor_node_id')
                            or args.get('task_id') != task['id'] or args.get('node_id') != node['id']
                            or bound.get('task_id') != task['id']
                            or bound.get('dispatch_id') != dispatch.get('dispatch_id')
                            or args.get('dispatch_id') != dispatch.get('dispatch_id')
                            or not same_executor_ref(args.get('executor_ref'), dispatch.get('executor_ref'))
                            or bound.get('executor_ref') and not same_executor_ref(bound['executor_ref'], dispatch.get('executor_ref'))
                            or bound.get('project_id') != node.get('record_project_id')
                            or bound.get('execution_id') != node.get('record_execution_id')):
                        raise Conflict('reclaim_binding_unconfirmed: 原交还回执、当前执行者或报告绑定无法确认；不重放领取')
                    reconciled_from = prior_id
                if action == 'checkpoint':
                    checkpoint = copy.deepcopy(args.get('checkpoint') or {})
                    if 'work_plan' in checkpoint:
                        from .native_work_plan import record_view, update_work_plan
                        checkpoint['work_plan'] = update_work_plan(self.c, state, node,
                            checkpoint['work_plan'], record_view(state, node))
                    if 'native_environment_replacement' in checkpoint:
                        from .native_contexts import replace_exited_environment
                        checkpoint['native_environment_replacement'] = replace_exited_environment(
                            state, node, lease, owner, checkpoint['native_environment_replacement'], self.c.clock())
                    if 'native_login' in checkpoint:
                        from .native_login import record_login
                        checkpoint['native_login'] = record_login(state, node, lease, checkpoint['native_login'], self.c.clock())
                    node['checkpoint'] = {**node.get('checkpoint', {}), **checkpoint}
                    return {'saved': True, **self.status(node, lease),
                            **({'work_plan': copy.deepcopy(checkpoint['work_plan'])} if 'work_plan' in checkpoint else {})}
                if action == 'credentials':
                    aid = self.direct._account(lease, args)
                if action == 'context' and lease.get('revoked'):
                    return self.status(node, lease)
        if ended and action == 'finish':
            # Delivery receipts mutate the existing handoff. Re-read their
            # authority under the original writer; the first read is no grant.
            with self._authorization_state(writable=True, timing=server_timing, work_records=True) as state:
                ended = state.get('direct_settlements', {}).get(args['lease_id'])
                if not ended:
                    raise Conflict('原交还回执已变化，沿原租约核对')
                if ended['owner'] != owner or ended['holder_id'] != holder:
                    raise PermissionError('回执不属于当前聊天')
                from .native_handoff import settlement_response
                started = time.perf_counter()
                handoff = settlement_response(
                    self.c, state, state['nodes'][ended['node_id']], args['lease_id'],
                    (args.get('arguments') or {}).get('handoff_notification'),
                    (args.get('arguments') or {}).get('handoff_delivery'))
                server_timing['settlement_response_seconds'] = round(time.perf_counter() - started, 6)
                return {'mode': 'native_browser', 'released': True, 'state': ended['state'],
                        'node_id': ended['node_id'], 'server_processing_timing': server_timing, **handoff}
        if released_scope is not None:
            return self.record_after_release(owner, args, *released_scope)
        if action == 'request_resources':
            result = self.c.request_resources(owner, lid, args)
            return {**result, 'mode': 'native_browser', 'resource_mode': result.get('mode')}
        if action == 'finish':
            values = args.get('arguments') or {}
            if values.get('browser_stopped') is not True:
                return {'mode': 'native_browser', 'state': 'stopping', 'released': False,
                        'manual_stop_required': True, 'next_action': 'desktop_manual_stop',
                        'message': '先停止本任务浏览器操作并清理/关闭本任务页面，再以 browser_stopped=true 回报；平台不能取消桌面 Codex。'}
            reason = text(args.get('reason') or values.get('reason'), '退出依据', 4000)
            if 'result' in values and not isinstance(values['result'], str):
                raise ValueError('arguments.result 是 passed/failed/partial/blocked/not_run 字符串，不是统计对象；未保存收尾报告或交还')
            if values.get('final_report') is not None:
                # Only the original holder, after actual browser exit, can
                # combine final observations with this existing settlement.
                # Register the intent first so settlement publishes exactly it.
                from . import ui_finalization
                final = values['final_report']
                project = self.service.report_project(owner, node, task)
                if (not isinstance(final, dict) or final.get('project_id') != project['id']
                        or final.get('execution_id') != project.get('ui_execution_id')):
                    raise Conflict('收尾报告必须属于原租约的当前执行记录')
                ui_finalization.begin(self.service, owner, project, final)
            return self.finish(owner, lid, hid, holder, args, reason, 'executor_reported', server_timing=server_timing)
        auth = {'owner': owner, 'host_id': hid, 'native_record': action == 'record'}
        if action == 'context':
            from .native_handoff import execution_contract
            context = self.service.host_call(auth, 'read', {'lease_id': lid})
            return {'mode': 'native_browser', 'handoff_execution': execution_contract(node),
                    **({'reconciled_from_lease_id': reconciled_from} if reconciled_from else {}),
                    **context, 'native_context_binding': copy.deepcopy(
                        (context.get('lease') or {}).get('native_context_binding') or {})}
        if action == 'credentials':
            return self.service.host_call(auth, 'account_credentials', {'lease_id': lid, 'account_id': aid})
        method = args.get('record_action')
        if method not in self.RECORD_ACTIONS:
            raise ValueError('未知记录动作；原生共享操作约束由 Skill 执行，不提交共享请求策略')
        return self.service.host_call(auth, method, {**copy.deepcopy(args.get('arguments', {})), 'lease_id': lid})

    def work_ready(self, owner, args):
        """One read at a resource boundary, before any new browser setup."""
        from .native_work_plan import load_record_views, validate_token, TOKEN_FIELDS
        from .resource_scheduler import ResourceScheduler
        views = load_record_views(self.c, node_ids={args.get('node_id')})
        with self.c.connect() as db:
            state = read_metadata_without_history(db)
        state['_work_record_views'] = views
        node = self.c.owned(state['nodes'], owner, args.get('node_id'))
        task = self.c.owned(state['tasks'], owner, args.get('task_id'))
        if node['task_id'] != task['id']:
            raise PermissionError('阶段核对任务不匹配')
        binding = node.get('executor_dispatch') or node.get('dispatch_offer') or {}
        from .native_identity import same_executor_ref
        if binding and (binding.get('holder_id') != args.get('holder_id')
                or (binding.get('dispatch_id') or binding.get('id')) != args.get('dispatch_id')
                or not same_executor_ref(binding.get('executor_ref'), args.get('executor_ref'))):
            raise PermissionError('阶段核对不是原执行者')
        candidate = validate_token(self.c, state, node, (args.get('arguments') or {}).get('work_token'))
        if candidate['eligibility'] == 'excluded':
            from .testing_policy import excluded_response
            return excluded_response(work_token=(args.get('arguments') or {}).get('work_token'),
                                     node_id=node['id'], task_id=task['id'])
        self.c.sessions.assert_available(state, task, [node['id']])
        node['_work_claim_token'] = copy.deepcopy(args['arguments']['work_token'])
        scheduler = ResourceScheduler(self.c, state, self.c.clock())
        active = next((lease for lease in state['leases'].values() if lease['node_id'] == node['id']), None)
        if active:
            if (active.get('revoked') or active.get('revision') != node['revision']
                    or node.get('direct_holder') != args.get('holder_id') or node['state'] != 'running'
                    or any((node.get('work_selection') or {}).get(k) != candidate[k] for k in TOKEN_FIELDS)):
                raise Conflict('work_lease_changed: 活动租约已撤权或不属于原通知阶段；不能复用')
            projected = copy.deepcopy(candidate['projected_node'])
            requested = projected.get('requested_account_ids')
            if requested and set(requested) != set(active['account_ids']):
                raise Conflict('work_accounts_changed: 活动租约不包含原阶段完整账号集合')
            projected['requested_account_ids'] = list(active['account_ids'])
            # An existing shared lease may have legitimate peer holders. This
            # verifies its original complete set; it does not allocate anything.
            accounts = scheduler.bundle(projected, ignore_lease=active['id'], include_busy=True)
            selected = {**candidate, 'account_ids': accounts}
        else:
            selected = scheduler.select_work_candidate(node, views[node['id']]['record'], for_wake=True)
        ready = bool(selected and selected['unit_id'] == candidate['unit_id'] and selected['account_ids'] is not None)
        return {'stage_ready': ready, 'end_turn': not ready, 'work_token': (args['arguments']['work_token']),
                'account_ids': selected['account_ids'] if ready else [],
                'required_context_count': len(selected['account_ids']) if ready else 0,
                'runnable_case_ids': candidate['case_ids'], 'runnable_checkpoints': candidate['checkpoint_refs'],
                'project_id': node['record_project_id'], 'execution_id': node['record_execution_id'],
                'source_revision': candidate['source_revision']}

    def released_report_scope(self, state, owner, args, ended):
        """Report ownership survives account yield, never a new report writer."""
        from .native_identity import same_executor_ref
        if (ended.get('owner') != owner or ended.get('holder_id') != args.get('holder_id')
                or not ended.get('native_browser') or args.get('record_action') not in {'record', 'cases', 'publish'}):
            raise PermissionError('交还后的原绑定仅可读取、补保存或发布自己的报告')
        node = self.c.owned(state['nodes'], owner, ended['node_id'])
        task = self.c.owned(state['tasks'], owner, node['task_id'])
        bound = ended.get('report_binding') or {}
        values = args.get('arguments') or {}
        if (args.get('task_id') != task['id'] or args.get('node_id') != node['id']
                or bound.get('task_id') != task['id']):
            raise Conflict('report_task_mismatch: 报告请求与原任务/节点绑定不一致')
        if node.get('record_successor_node_id'):
            raise Conflict('report_writer_replaced: 原记录已交给正式后继；保留旧观察，不覆盖新执行者')
        dispatch = node.get('executor_dispatch') or node.get('dispatch_offer') or {}
        requested_dispatch = args.get('dispatch_id', bound.get('dispatch_id'))
        # MCP materializes this optional field as ''; HTTP may omit it.
        # Both use the original settlement, still checked against the current writer.
        if requested_dispatch == '':
            requested_dispatch = bound.get('dispatch_id')
        if (bound.get('dispatch_id') != (dispatch.get('dispatch_id') or dispatch.get('id'))
                or dispatch.get('holder_id') != ended['holder_id']
                or requested_dispatch != bound.get('dispatch_id')
                or bound.get('executor_ref') and not same_executor_ref(bound['executor_ref'], dispatch.get('executor_ref'))
                or args.get('executor_ref') and not same_executor_ref(args['executor_ref'], dispatch.get('executor_ref'))):
            raise Conflict('report_writer_replaced: 原派发或实际执行者已变化；旧写入者不能覆盖当前报告')
        # Old settlements did not persist executor_ref. They remain compatible
        # at their original revision; later writes need the original caller ref.
        if (not bound.get('executor_ref') and not args.get('executor_ref')
                and bound.get('node_revision') != node['revision']):
            raise Conflict('report_writer_unconfirmed: 旧回执缺少原执行者身份，不能确认变化后的报告写入者')
        if (any(not bound.get(key) or values.get(key) != bound[key]
                for key in ('project_id', 'execution_id'))
                or node.get('record_project_id') != bound.get('project_id')
                or node.get('record_execution_id') != bound.get('execution_id')):
            raise Conflict('report_binding_changed: 报告已换轮或记录绑定不一致；保留原观察')
        self.c.sessions.assert_available(state, task, [node['id']])
        if args['record_action'] == 'publish':
            self.require_report_settled(state, node)
        return node, task, state

    @staticmethod
    def require_report_settled(state, node):
        """Publication/continuation need real settlement, unlike observation writes."""
        if (node['state'] not in {'completed', 'blocked', 'stopped', 'paused'}
                or not node.get('native_browser_stopped')
                or any(lease['node_id'] == node['id'] for lease in state['leases'].values())):
            raise Conflict('report_not_settled: 原模块仍在等待、执行或退出尚未确认；可补存原观察，不能发布结束报告或正式续接')

    def record_after_release(self, owner, args, node, task, state):
        method, values = args['record_action'], args.get('arguments') or {}
        if method != 'publish':
            # Serialize the generation check with a concurrent redispatch. The
            # shared recorder reuses this transaction instead of nesting writers.
            with self.c.transaction(node_ids=[node['id']]) as (_, current):
                ended = current.get('direct_settlements', {}).get(args['lease_id'], {})
                node, task, _ = self.released_report_scope(current, owner, args, ended)
                return self.service.record_call(owner, None, node, task, current, method, values, write_state=current)
        from . import ui_finalization
        project = self.service.report_project(owner, node, task)
        @contextmanager
        def registration_guard():
            with self.c.transaction(node_ids=[node['id']]) as (_, current):
                ended = current.get('direct_settlements', {}).get(args['lease_id'], {})
                report_node, _, _ = self.released_report_scope(current, owner, args, ended)
                with self.service.store._lock:
                    latest = self.service.store.get_project(owner, values['project_id'])
                    if (latest.get('ui_execution_id') != values['execution_id']
                            or latest.get('ui_execution_revision') != values.get('revision')):
                        raise Conflict('发布修订与已保存结果不一致，沿原保存回执核对，不重跑业务')
                    yield latest
                    # Re-arm recovery only for this explicit, durably
                    # registered report request, never while waiting for prose.
                    report_node['finalization_pending'] = True
        published = ui_finalization.begin(self.service, owner, project, {
            'execution_id': values['execution_id'], 'revision': values['revision'],
            'request_id': 'native-report-' + args['lease_id'] + '-' + str(values['revision'])},
            settled_only=True, registration_guard=registration_guard)
        result = self.publication_view(published)
        if result.get('publication', {}).get('phase') == 'published':
            self.service.complete_published_settlement(owner, node, task, project, result['publication'])
            # The same release event wakes the coordinator only when reports
            # are ready. Already-delivered successor notices remain fenced.
            from .native_handoff import settlement_response
            with self.c.transaction() as (_, current):
                result.update(settlement_response(self.c, current, current['nodes'][node['id']], args['lease_id']))
        return {'mode': 'native_browser', 'released': True, **result}

    def finish(self, owner, lid, hid, holder, args, reason, source, *, server_timing=None):
        timing = server_timing if server_timing is not None else {}
        started = time.perf_counter()
        # Exit evidence and release are one transaction, including stale-S1 checks.
        result = self.c.return_account(owner, hid, {
            'lease_id': lid, 'executor_stopped': True, 'browser_stopped': True,
            'outcome': args.get('outcome', 'completed'), 'reason': reason,
            'native_exit_source': source, 'holder_id': holder,
            **({'control_revision': args['control_revision']} if 'control_revision' in args else {}),
            'result': args.get('arguments', {}).get('result', 'partial'),
            'coverage_complete': args.get('arguments', {}).get('coverage_complete', False),
            'report_pending': any((args.get('arguments') or {}).get(key) is True
                                  for key in ('report_pending', 'save_unconfirmed')),
            **({'checkpoint': args['checkpoint']} if 'checkpoint' in args else {}),
        })
        timing['return_account_seconds'] = round(time.perf_counter() - started, 6)
        # Resource release is the event that makes a sleeping successor ready.
        # Refresh the existing queue now, before returning its handoff.
        started = time.perf_counter()
        self.c.schedule(native_handoff_source={
            'node_id': result['node_id'], 'event_id': lid,
            'enable_direct': (args.get('arguments') or {}).get('handoff_route') == 'direct_successors'})
        timing['schedule_seconds'] = round(time.perf_counter() - started, 6)
        started = time.perf_counter()
        if result.get('handoff'):
            from .native_handoff import settlement_response
            with self.c.transaction(work_records=True) as (_, state):
                result.update(settlement_response(
                    self.c, state, state['nodes'][result['node_id']], lid,
                    enable_direct=(args.get('arguments') or {}).get('handoff_route') == 'direct_successors'))
        timing['settlement_response_seconds'] = round(time.perf_counter() - started, 6)
        started = time.perf_counter()
        final = (args.get('arguments') or {}).get('final_report') or {}
        publication = {}
        if (args.get('arguments') or {}).get('report_pending') is True:
            publication = {'publication': {'phase': 'awaiting_report', 'pending': False,
                'message': '浏览器已退出、账号已交还；原记录待补整理，可沿原绑定保存并发布，不重新领取账号。'}}
            try:
                if not self.service.reconcile_idle_settlement(owner, result['node_id']):
                    # An earlier explicit report request remains queued. Do
                    # not call it idle or run it ahead of the resource handoff.
                    with self.c.connect() as db:
                        current = read_metadata_without_history(db)
                    publication = self.publication(owner, current['nodes'][result['node_id']]) or publication
            except Exception:
                # Release is already durable; normal recovery retains its
                # queue marker if this optional reconciliation was interrupted.
                publication['publication']['warning'] = '资源已交还，收尾状态待原回执核对；不重跑业务。'
        elif (args.get('arguments') or {}).get('save_unconfirmed') is True:
            publication = {'publication': {'phase': 'blocked', 'pending': False,
                'message': '资源已交还；结果保存尚未确认，保留原观察与回执核对，未发布完整报告。'}}
        elif (args.get('arguments') or {}).get('publish_saved') is True:
            # The lease is already durably returned. Reporting cannot strand
            # the next module, and no model-written summary/identity is needed.
            try:
                from . import ui_finalization
                detail = timing['publication_detail_seconds'] = {}
                part_started = time.perf_counter()
                with self.c.connect() as db:
                    db.execute('BEGIN')
                    state = read_metadata_without_history(db)
                    node = state['nodes'][result['node_id']]
                    state['tasks'].update(read_entries(db, 'tasks', keys=[node['task_id']],
                        include_baseline=True, baseline_fields=('cases', 'sources')))
                detail['read_state'] = round(time.perf_counter() - part_started, 6)
                part_started = time.perf_counter()
                project = self.service.report_project(owner, node, state['tasks'][node['task_id']])
                detail['report_project'] = round(time.perf_counter() - part_started, 6)
                if project.get('ui_execution_id'):
                    part_started = time.perf_counter()
                    published = ui_finalization.begin(self.service, owner, project, {
                        'execution_id': project['ui_execution_id'],
                        'request_id': 'native-saved-' + lid})
                    detail['begin'] = round(time.perf_counter() - part_started, 6)
                    publication = self.publication_view(published)
                    part_started = time.perf_counter()
                    try:
                        confirmed = self.service.complete_published_settlement(
                            owner, node, state['tasks'][node['task_id']], project,
                            publication.get('publication', {}))
                        detail['settlement_marker'] = round(time.perf_counter() - part_started, 6)
                        # The successful marker transaction already checked
                        # current execution/revision/request under Store lock.
                        # Only a changed binding requires another status read.
                        if not confirmed:
                            part_started = time.perf_counter()
                            refreshed = self.publication(owner, {'record_project_id': project['id']})
                            if refreshed:
                                publication = refreshed
                            elif publication:
                                publication['publication']['warning'] = '原发布回执已保留；当前会话已不可读取，保留待收尾标记，不重跑业务。'
                            detail['status_refresh'] = round(time.perf_counter() - part_started, 6)
                    except Exception:
                        detail['settlement_marker'] = round(time.perf_counter() - part_started, 6)
                        # Publication is already committed. A pending-marker
                        # cleanup failure must not turn that fact into failed
                        # publication or cause a second business/report run.
                        publication.setdefault('publication', {})['warning'] = (
                            '原报告发布回执已保留；调度收尾标记未确认清除，保留原待收尾记录核对，不重跑业务。')
            except Exception:
                # Preserve the release and direct handoff even if publication
                # fails. Original cases are authoritative; do not replay them.
                publication = {'publication': {'phase': 'failed', 'pending': False,
                    'message': '资源已交还，已保存结果的报告处理失败；核对原报告，不重跑业务。'}}
        if not publication:
            self.service.finalize_settlement(owner, result['node_id'])
            self.service.notify_final_report(owner, result['node_id'])
        timing['publication_seconds'] = round(time.perf_counter() - started, 6)
        return {'mode': 'native_browser', 'exit_source': source, **result,
                'server_processing_timing': timing,
                **(publication or self.publication(owner, {'record_project_id': final.get('project_id')}))}

    def publication(self, owner, node):
        """Reuse persisted publication metadata; no report rewrite/full-case read."""
        pid = node.get('record_project_id')
        if not pid:
            return {}
        from . import ui_finalization
        try:
            current = ui_finalization.status(self.service.store.get_project(owner, pid))
        except FileNotFoundError:
            return {}
        return self.publication_view(current)

    @staticmethod
    def publication_view(current):
        if not current:
            return {}
        return {'publication': {key: current[key] for key in (
            'phase', 'pending', 'execution_id', 'revision', 'request_id', 'report',
            'error', 'message', 'next_action', 'processing_timing') if key in current}}

    def confirm_exit(self, owner, task_id, data):
        """S1: the user confirms a desktop stop they performed; never cancels it."""
        from .module_dispatch import observe_control
        if data.get('executor_stopped') is not True or data.get('browser_stopped') is not True:
            raise ValueError('须确认桌面会话和本任务浏览器操作均已停止')
        reason = text(data.get('reason'), '人工退出依据', 4000)
        ids = data.get('node_ids')
        if not isinstance(ids, list) or not ids or len(set(ids)) != len(ids):
            raise ValueError('指定已确认退出的模块')
        releases = []
        with self.c.transaction() as (_, state):
            task = self.c.owned(state['tasks'], owner, task_id)
            if task.get('execution_route') != 'native_browser':
                raise ValueError('仅原生桌面路线使用 S1 人工确认')
            if data.get('revision') != task['revision']:
                raise Conflict('任务已变化，请核对当前停止清单')
            for nid in ids:
                if nid not in task['node_ids']:
                    raise PermissionError('模块不属于当前任务')
                node = state['nodes'][nid]
                if node.get('control_intent', task['intent']) not in {'stop', 'pause'}:
                    raise Conflict('先停止平台调度，再确认桌面退出')
            for nid in ids:
                node = state['nodes'][nid]
                lease = next((item for item in state['leases'].values() if item['node_id'] == nid), None)
                if lease:
                    releases.append((lease['id'], lease['runner_id'], node['direct_holder']))
                else:
                    receipt = node.get('executor_dispatch') or node.get('dispatch_offer') or {}
                    observe_control(node, receipt.get('holder_id', ''), self.c.clock(), exited=True)
                    node['native_browser_stopped'] = True
                    from .native_contexts import invalidate
                    invalidate(node, 'exited', self.c.clock())
                    node['native_exit_evidence'] = {'source': 'user_confirmation', 'reason': reason, 'at': self.c.clock()}
        for lid, hid, holder in releases:
            self.finish(owner, lid, hid, holder, {
                'outcome': 'blocked', 'control_revision': data['revision']}, reason, 'user_confirmation')
        return self.c.snapshot(owner, task_id)
