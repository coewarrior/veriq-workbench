"""Resource decisions for the existing controller transaction.

No network/model calls: identity, complete sets, exploration admission and fairness
are decided together with the lease write. Browser policy enforcement is separate.
"""
from __future__ import annotations
import copy
from .resource_projection import copy_node
from .module_continuation import dependencies_completed
from .orchestration_storage import select_records
from urllib.parse import urlsplit


def physical_key(account):
    # An environment label or role does not create another real login identity.
    return (account['target'].rstrip('/').lower(), account['identity'].strip())


def account_matches(account, requirement):
    return (all(account.get(k, '').rstrip('/') == requirement.get(k, '').rstrip('/')
                for k in ('target', 'environment', 'tenant'))
            and requirement.get('role') in account.get('roles', []))


def pending_operations(state, lease_id):
    return select_records(state['operations'], lease_id=lease_id, state=('pending','unknown'))


def retention_conditions(node, lease):
    checkpoint = node.get('checkpoint', {})
    conditions = checkpoint.get('retained_conditions') or checkpoint.get('must_preserve') or []
    if checkpoint.get('retain_browser') or checkpoint.get('retain_scene'):
        conditions = conditions or ['保留原页面或业务现场']
    safety = checkpoint.get('resource_safety', {})
    if safety.get('retained') or safety.get('safe_to_release') is False:
        conditions = conditions or [safety.get('reason') or '本阶段业务条件需要保留']
    return conditions or lease.get('retained_conditions') or []


class ResourceScheduler:
    def __init__(self, controller, state, now):
        self.c, self.s, self.now = controller, state, now
        self._targets = {}; self._eligible = {}
        from .account_projects import resource_project
        self.project = resource_project

    def target(self, node):
        cache_key = (node['owner'], node['project_id'])
        if cache_key in self._targets:
            return self._targets[cache_key]
        try:
            project = self.c.store.get_project(node['owner'], node['project_id'])
        except FileNotFoundError:
            # A deleted session can still have queued nodes. Do not let it abort
            # other owners' claims, or turn a missing target into any-account access.
            self._targets[cache_key] = None
            return None
        url = project.get('ui_target_url') or (node.get('requirements') or [{}])[0].get('target', '')
        parsed = urlsplit(url)
        target = f'{parsed.scheme}://{parsed.netloc.lower()}' if parsed.netloc else ''
        self._targets[cache_key] = target
        return target

    def eligible(self, node):
        target = self.target(node)
        if target is None:
            node['reason'] = '测试会话已删除或不存在；保留原任务，等待恢复原会话'
            return []
        key = (node['owner'], self.project(node), target)
        if key in self._eligible:
            return self._eligible[key]
        accounts = [a for a in self.s['accounts'].values()
                if a['owner'] == node['owner'] and self.project(node) in a['projects']
                and (not target or a['target'].rstrip('/') == target)
                and a.get('state') not in {'disabled', 'quarantined', 'isolated'}]
        self._eligible[key] = accounts
        return accounts

    def holders(self, aid, ignore_lease=None):
        key = physical_key(self.s['accounts'][aid])
        return [l for l in self.s['leases'].values() if l['id'] != ignore_lease
                and any(physical_key(self.s['accounts'][x]) == key for x in l['account_ids'])]

    def physical_accounts(self, aid):
        source = self.s['accounts'][aid]
        key = physical_key(source)
        return [account for account in self.s['accounts'].values()
                if account['owner'] == source['owner'] and physical_key(account) == key]

    def reserved(self, aid, node):
        key = physical_key(self.s['accounts'][aid])
        return any(other['id'] != node['id'] and other.get('reservation')
                   and any(physical_key(self.s['accounts'][x]) == key
                           for x in other['reservation']['accounts'] if x in self.s['accounts'])
                   for other in self.s['nodes'].values())

    def policy(self, node, aid):
        if self.s['tasks'][node['task_id']].get('execution_route') == 'native_browser':
            return None
        account = self.s['accounts'][aid]
        if not node.get('shared_policy'):
            from .exploration_profiles import provision
            provision(self.s, account)
        policy_id = node.get('shared_policy') or account.get('policy_id')
        policy = self.s['policies'].get(policy_id)
        if (not policy or not policy.get('enabled') or policy['owner'] != node['owner']
                or self.project(node) not in policy.get('projects', [policy.get('project_id')])
                or account.get('policy_id') != policy_id
                or (not policy.get('session_compatible', policy.get('login_compatible', False))
                    and policy.get('preparation') != 'pending')):
            return None
        return policy

    def preparation_gap(self, node, account_ids):
        policies=[self.s['policies'].get(node.get('shared_policy') or self.s['accounts'][aid].get('policy_id'),{})
                  for aid in account_ids]
        reasons=list(dict.fromkeys(p.get('preparation_reason') or ('共享授权已撤销' if p and not p.get('enabled')
                     else '当前共享授权或账号代次不匹配') for p in policies))
        return {'kind':'preparation_unavailable','responsibility':'platform','fallback':'exclusive_queue',
                'message':'；'.join(reasons)+'；保留现场沿独占队列继续，不能记为业务失败或探索池验收通过'}

    def can_share(self, node, aid, runner=None):
        if (node.get('phase') != 'exploration' or node.get('exclusive_exploration')
                or len(node.get('requirements', [])) > 1 or len(node.get('requested_account_ids', [])) > 1
                or node.get('locks') or node.get('exploration_complete')):
            return False
        if self.s['tasks'][node['task_id']].get('execution_route') == 'native_browser':
            # User-approved desktop sharing relies on the Skill's exploration
            # boundary, never on fabricated Runner interception/session checks.
            from .native_contexts import requires_context
            if requires_context(node):
                environments = self.s.get('native_browser_environments', {})
                if not any(environments.get(key, {}).get('isolation') == 'isolated'
                           for key in node.get('native_environment_keys', [])):
                    return False
            if any(account.get('exploration_batch', {}).get('state') == 'draining'
                   for account in self.physical_accounts(aid)):
                return False
            return all(lease.get('native_browser') and lease['mode'] == 'shared'
                       and self.s['nodes'][lease['node_id']]['owner'] == node['owner']
                       and self.project(self.s['nodes'][lease['node_id']]) == self.project(node)
                       and not lease.get('revoked') for lease in self.holders(aid))
        if runner and not runner.get('evidence', {}).get('shared_exploration'):
            return False
        policy = self.policy(node, aid)
        if not policy:
            return False
        if (runner and policy.get('automatic_profile')
                and runner.get('evidence', {}).get('automatic_exploration', 0) < policy.get('adapter_schema', 1)):
            return False
        from .exploration_learning import PROFILE
        holders = self.holders(aid)
        if policy.get('automatic_profile') == PROFILE:
            if not holders and runner and runner not in self.runner_candidates(node, 2):return False
            if holders and not policy.get('session_compatible'):return False
        account = self.s['accounts'][aid]
        batch = account.get('exploration_batch')
        if batch and batch.get('state') == 'draining':
            return False
        return all(l['mode'] == 'shared' and not l.get('revoked') and l.get('policy_id') == policy['id']
                   for l in holders)

    def exploration_in_progress(self, node):
        choices = self.candidate_sets(node, include_busy=True) or []
        compatible = {physical_key(self.s['accounts'][aid]) for group in choices for aid in group}
        return any((lease.get('exploration_bootstrap') or lease['mode'] == 'shared')
                   and self.project(self.s['nodes'][lease['node_id']]) == self.project(node)
                   and any(physical_key(self.s['accounts'][aid]) in compatible for aid in lease['account_ids'])
                   for lease in self.s['leases'].values())

    def candidate_sets(self, node, *, shared=False, ignore_lease=None, include_busy=False, runner=None):
        from .testing_policy import resource_excluded
        if resource_excluded(node, self.s):
            return None
        if node.get('requires_account') is False or node.get('phase') == 'report':
            return []
        accounts = self.eligible(node)
        requested = node.get('requested_account_ids', [])
        requirements = node.get('requirements', [])
        if requested:
            sets = [[a['id']] for aid in requested for a in accounts if a['id'] == aid]
            if len(sets) != len(requested):
                return None
            # A manually selected set must still meet every declared identity.
            if requirements and not self._assign([[a['id'] for a in accounts if a['id'] in requested and account_matches(a, r)]
                                                  for r in requirements]):
                return None
        elif requirements:
            sets = [[a['id'] for a in accounts if account_matches(a, r)] for r in requirements]
        else:
            sets = [[a['id'] for a in accounts]]
        if shared and len(sets) != 1:
            return None
        filtered = []
        for choices in sets:
            usable = []
            for aid in choices:
                if include_busy:
                    usable.append(aid)
                elif shared:
                    if not self.reserved(aid, node) and self.can_share(node, aid, runner):
                        usable.append(aid)
                elif not self.holders(aid, ignore_lease) and not self.reserved(aid, node):
                    usable.append(aid)
            filtered.append(usable)
        return filtered

    def _assign(self, choices, preference=None):
        if choices is None or any(not x for x in choices):
            return None
        ordered = sorted(range(len(choices)), key=lambda i: len(choices[i]))
        def visit(index, taken, identities):
            if index == len(ordered):
                return taken
            values = choices[ordered[index]]
            if preference:
                values = sorted(values, key=preference)
            for aid in values:
                identity = physical_key(self.s['accounts'][aid])
                if identity in identities:
                    continue
                result = visit(index + 1, taken + [aid], identities | {identity})
                if result is not None:
                    return result
            return None
        return visit(0, [], set())

    def bundle(self, node, *, shared=False, ignore_lease=None, include_busy=False, runner=None, peers=()):
        choices = self.candidate_sets(node, shared=shared, ignore_lease=ignore_lease,
                                      include_busy=include_busy, runner=runner)
        previous = node.get('preferred_account_ids') or node.get('checkpoint', {}).get('account_ids', [])
        current = self.s['leases'].get(ignore_lease, {}).get('account_ids', [])
        def preference(aid):
            account = self.s['accounts'][aid]
            competing = 0
            for other in peers:
                if other['id'] == node['id']:
                    continue
                candidates = self.candidate_sets(other, include_busy=True) or []
                # Preserve scarce identities for already waiting, compatible work.
                competing += sum(1 / len(c) for c in candidates if aid in c and c)
            return (bool(current) and aid not in current, competing,
                    bool(self.policy(node, aid)) if not shared and ignore_lease is None and not previous else False,
                    account.get('pool') != 'execution', aid not in previous,
                    account.get('created', 0), aid)
        return self._assign(choices, preference)

    def runnable(self, node):
        return (not node.get('child_ids') and node['state'] == 'queued'
                and self.s['tasks'][node['task_id']]['intent'] == 'run' and node.get('control_intent', 'run') == 'run'
                and dependencies_completed(self.s, node)
                and self.target(node) is not None)

    def runner_candidates(self, node, units, ignore_lease=None):
        direct = self.s['tasks'][node['task_id']].get('execution_route') == 'local_browser'
        runners = [r for r in self.s['runners'].values() if r['owner'] == node['owner'] and r['enabled']
                   and r.get('evidence', {}).get('simple_dispatch') == 1 and self.now - r['heartbeat'] <= 60
                   and (direct or not r.get('evidence', {}).get('platform_browser'))
                   and (not direct or r.get('evidence', {}).get('direct_execution') == 1)]
        result = []
        for runner in runners:
            machine = runner.get('evidence', {}).get('machine_id')
            same = [r for r in self.s['runners'].values()
                    if machine and r.get('evidence', {}).get('machine_id') == machine] or [runner]
            ids = {r['id'] for r in same}
            used = sum(l.get('browser_units', 1) for l in self.s['leases'].values() if l['runner_id'] in ids and l['id'] != ignore_lease)
            # Two connections to one machine must not double its admission budget.
            online = [r for r in same if r['enabled'] and self.now - r['heartbeat'] <= 60]
            budget = min(r['browser_slots'] for r in online)
            models = sum(l['runner_id'] == runner['id'] and not l.get('direct') and not l.get('waiting')
                         and not l.get('resource_hold') and l['id'] != ignore_lease for l in self.s['leases'].values())
            if used + units <= budget and (direct or models < runner['model_slots']):
                result.append(runner)
        return result

    def locks_conflict(self, node, ignore_lease=None):
        held = {key for l in self.s['leases'].values() if l['id'] != ignore_lease
                for key in self.s['nodes'][l['node_id']].get('locks', [])}
        reservations = {key for other in self.s['nodes'].values() if other['id'] != node['id']
                        and other.get('reservation') for key in other['reservation'].get('locks', [])}
        return bool((held | reservations).intersection(node.get('locks', [])))

    def refresh(self):
        from .testing_policy import exclude_unallocated_node
        leased = {lease['node_id'] for lease in self.s['leases'].values()}
        for node in self.s['nodes'].values():
            if node['id'] not in leased:
                exclude_unallocated_node(node, self.s)
            if node.get('native_handoffs'):
                from .native_handoff import refresh
                for handoff in node['native_handoffs'].values():
                    refresh(self.s, node, handoff, self.now)
            reservation = node.get('reservation')
            if reservation and (not self.runnable(node) or reservation['until'] <= self.now):
                if reservation['until'] <= self.now:
                    node['reservation_expirations'] = node.get('reservation_expirations', 0) + 1
                    self.c.notice(self.s, node, 'reservation_expired', '完整资源集合未及时齐备，已撤销未生效预留；保留等待顺位')
                node['reservation'] = None
        for account in self.s['accounts'].values():
            batch = account.get('exploration_batch')
            if not batch:
                continue
            holders = self.holders(account['id'])
            if not holders or batch.get('state')=='closed':
                policy=self.s['policies'].get(batch.get('policy_id'),{})
                if policy.get('session_batch_id')==batch.get('id'):
                    policy.pop('session_seed',None)
                    policy.pop('session_batch_id',None)
            shared = [l for l in holders if l['mode'] == 'shared']
            batch['members'] = [l['node_id'] for l in shared]
            target = self.s['nodes'].get(batch.get('target_node'))
            if target and (self.s['tasks'][target['task_id']]['intent'] != 'run'
                           or target['state'] in {'completed', 'blocked', 'stopped', 'paused'}
                           or any(l['node_id'] == target['id'] and account['id'] not in l['account_ids'] for l in self.s['leases'].values())):
                batch.update(state='open', target_node=None, reason='', revision=batch.get('revision', 1) + 1)
            if target and self.runnable(target) and self.bundle(target) is not None:
                batch.update(state='open', target_node=None, reason='交接需求已由其他可用资源满足', revision=batch.get('revision', 1) + 1)
            if not holders:
                # Closing is an event, not a heartbeat. Historical closed
                # batches must not force a metadata rewrite on every tick.
                if batch.get('state') != 'closed' or 'closed' not in batch:
                    batch['closed'] = self.now
                batch.update(state='closed', target_node=None)
                account['pool'] = 'execution'
            elif any(l.get('revoked') for l in shared):
                batch.update(state='draining', reason='成员撤权或结果待核实，停止接纳')

    def close_for_waiter(self, node, candidates):
        if not node.get('protected') and node.get('phase') == 'exploration' and not node.get('exclusive_exploration'):
            return
        for aid in {a for choices in (candidates or []) for a in choices}:
            batch = self.s['accounts'][aid].get('exploration_batch')
            if batch and batch['state'] in {'open', 'draining'}:
                old = self.s['nodes'].get(batch.get('target_node'))
                if old is None or (node.get('protected') and not old.get('protected')):
                    batch.update(state='draining', target_node=node['id'], reason='等待独占阶段或公平保护交接',
                                 revision=batch.get('revision', 1) + 1)

    def maybe_reserve(self, node, choices):
        from .orchestration import DEFAULTS, digest
        if (not node.get('protected') or node.get('reservation') or not choices or len(choices) < 2
                or node.get('reservation_expirations', 0) >= DEFAULTS['reservation_expirations']):
            return
        full = self._assign(choices)
        if not full:
            return
        free = [aid for aid in full if not self.holders(aid) and not self.reserved(aid, node)]
        missing = [l for aid in full if aid not in free for l in self.holders(aid)]
        if not free or not missing:
            return
        # Only actual observed exit/closeout is a short-release signal.
        if not all((l.get('release_ready') or l.get('direct_finish')) and not pending_operations(self.s, l['id'])
                   and not retention_conditions(self.s['nodes'][l['node_id']], l) for l in missing):
            return
        evidence = digest(sorted(l['id'] for l in missing))
        if evidence == node.get('last_reservation_evidence'):
            return
        node['reservation'] = {'accounts': free, 'locks': list(node.get('locks', [])),
                               'until': self.now + DEFAULTS['reservation_seconds']}
        node['last_reservation_evidence'] = evidence

    def queue(self):
        from .orchestration import queue_key
        from .native_work_plan import reconcile_protection
        for node in self.s['nodes'].values():
            if node['state'] == 'queued':
                reconcile_protection(self.s, node)
        ready = sorted((n for n in self.s['nodes'].values() if not n.get('child_ids')
                        and n['state'] == 'queued' and self.s['tasks'][n['task_id']]['intent'] == 'run'
                        and n.get('control_intent', 'run') == 'run'), key=queue_key)
        for node in ready:
            if self.target(node) is None:
                node['reason'] = '测试会话已删除或不存在；保留原任务，等待恢复原会话'
                node['reservation'] = None
        ready = [n for n in ready if self.target(n) is not None]
        projects = list(dict.fromkeys(self.project(n) for n in ready))
        if self.s.get('last_project') in projects:
            i = projects.index(self.s['last_project']) + 1
            projects = projects[i:] + projects[:i]
        groups = {p: [n for n in ready if self.project(n) == p] for p in projects}
        ordered = []
        while any(groups.values()):
            for project in projects:
                if groups[project]:
                    ordered.append(groups[project].pop(0))
        return [n for n in ordered if n.get('protected')] + [n for n in ordered if not n.get('protected')]

    def grant(self, db, node, account_ids, runner, shared=False):
        from .orchestration import uid
        if self.s['tasks'][node['task_id']].get('execution_route') == 'native_browser':
            from .native_contexts import lease_context_fields
            context_fields = lease_context_fields(self.s, node, account_ids)
            if context_fields is None:
                # The same transaction owns both the account set and its actual
                # browser contexts; a preview cannot grant missing capacity.
                return None
            lid = uid()
            identity = ','.join(sorted(account_ids))
            lease = dict(id=lid, node_id=node['id'], runner_id='native:' + node['direct_holder'],
                         account_ids=account_ids, mode='shared' if shared else 'exclusive', policy_id='',
                         native_browser=True, exploration_bootstrap=False,
                         shared_enforcement='skill_only' if shared else None,
                         revision=node['revision'], epoch=self.s['epoch'], revoked=False,
                         created=self.now, context_id=node.get('context_affinity', {}).get(identity, uid()),
                         browser_units=0, credential_execution=True, simple_dispatch=True,
                         direct=True, progress_at=self.now, actor_seen=self.now)
            lease.update(context_fields)
            # A new reservation must not inherit a previous account's login
            # assertion, even when the same browser profile is reused.
            previous_login = node.pop('native_login', None)
            checkpoint_login = node.get('checkpoint', {}).pop('native_login', None)
            if previous_login or checkpoint_login:
                node.setdefault('native_login_history', []).append(previous_login or checkpoint_login)
            self.s['leases'][lid] = lease
            self.s['last_project'] = self.project(node)
            for aid in account_ids:
                account = self.s['accounts'][aid]
                account.update(pool='exploration' if shared else 'execution', login_requested=False)
                if shared:
                    aliases = self.physical_accounts(aid)
                    batch = next((item['exploration_batch'] for item in aliases
                                  if item.get('exploration_batch', {}).get('state') == 'open'), None)
                    if batch is None:
                        batch = dict(id=uid(), state='open', policy_id='', created=self.now,
                                     native_browser=True, revision=1, target_node=None, reason='', members=[])
                    if node['id'] not in batch['members']:
                        batch['members'].append(node['id'])
                    for alias in aliases:
                        alias['exploration_batch'] = copy.deepcopy(batch)
                        alias['pool'] = 'exploration'
                    lease['exploration_batch_id'] = batch['id']
            node.update(state='running', native_browser=True, reason='账号已分配，由当前桌面 Codex 原生浏览器直接执行',
                        resource_planning=False, credential_execution=True, reservation=None)
            node.pop('resource_wait', None)
            node.pop('execution_ended', None)
            node.pop('native_browser_stopped', None)
            if node.get('protected'):
                node.setdefault('protection_history', []).append({'allocated': self.now, 'account_ids': account_ids})
                node['protected'] = False
            node['attempts'].append(dict(lease_id=lid, created=self.now, context_id=lease['context_id']))
            self.c.audit(db, node['owner'], 'lease.granted', lid,
                         'native desktop ' + lease['mode'] + ' account allocation')
            return {'lease_id': lid, 'node_id': node['id'], 'native_browser': True}
        direct = self.s['tasks'][node['task_id']].get('execution_route') == 'local_browser'
        policy = self.policy(node, account_ids[0]) if shared else None
        # The first explorer owns the account while the platform prepares it.
        # Generic live verification reserves its additional browser context;
        # the existing completion receipt opens the batch atomically.
        bootstrap = bool(shared and policy.get('automatic_profile') and not self.holders(account_ids[0]))
        from .exploration_learning import PROFILE
        verification_slot = bool(bootstrap and policy.get('automatic_profile') == PROFILE)
        lid = uid()
        identity = ','.join(sorted(account_ids))
        lease = dict(id=lid, node_id=node['id'], runner_id=runner['id'], account_ids=account_ids,
                     mode='shared' if shared and not bootstrap else 'exclusive', policy_id=policy['id'] if policy else '',
                     exploration_bootstrap=bootstrap,
                     revision=node['revision'], epoch=self.s['epoch'], revoked=False, created=self.now,
                     context_id=node.get('context_affinity', {}).get(identity, uid()), browser_units=len(account_ids)+int(verification_slot),
                     credential_execution=True, simple_dispatch=True, direct=direct, progress_at=self.now, actor_seen=self.now)
        self.s['leases'][lid] = lease
        self.s['last_project'] = self.project(node)
        for aid in account_ids:
            account = self.s['accounts'][aid]
            if shared and not bootstrap:
                batch = account.get('exploration_batch')
                if not batch or batch['state'] == 'closed':
                    batch = dict(id=uid(), state='open', policy_id=policy['id'], created=self.now, revision=1,
                                 target_node=None, reason='', members=[])
                    account['exploration_batch'] = batch
                batch['members'].append(node['id'])
                account['pool'] = 'exploration'
                lease['exploration_batch_id'] = batch['id']
            else:
                account['pool'] = 'execution'
            account.update(login_requested=False, login_attempt=uid())
        if node.get('protected'):
            node.setdefault('protection_history', []).append({'allocated': self.now, 'account_ids': account_ids})
            node['protected'] = False
        node.update(state='starting', reason='探索资源已分配' if shared else '账号已分配，Codex 正在接手',
                    resource_planning=False, credential_execution=True, reservation=None)
        node.pop('resource_wait', None)
        node.pop('execution_ended', None)
        if bootstrap:node['reason']='探索账号已分配，平台正在准备登录会话并核验实时探索入口'
        node['attempts'].append(dict(lease_id=lid, created=self.now, context_id=lease['context_id']))
        self.c.audit(db, node['owner'], 'lease.granted', lid, lease['mode'] + ' complete resource dispatch')
        return self.c.event(self.s, 'start', node, runner['id'], lid)

    def select_work_candidate(self, node, record_view, *, for_wake=False):
        from .execution_work_plan import project_work_candidates
        candidates = [c for c in project_work_candidates(node, record_view) if c['eligibility'] == 'ready']
        claim_token = node.get('_work_claim_token')
        if claim_token:
            from .native_work_plan import TOKEN_FIELDS
            candidates = [c for c in candidates if all(c[k] == claim_token.get(k) for k in TOKEN_FIELDS)]
        protected = node.get('work_protection') or (node.get('work_selection') if node.get('protected') else None)
        if node.get('protected'):
            pinned = next((c for c in candidates if protected and c['unit_id'] == protected['work_unit_id']
                           and c['unit_digest'] == protected.get('unit_digest')), None)
            if claim_token and protected and pinned is None:
                return None  # A stale notification must not borrow another stage's protection.
            candidates = [pinned] if pinned else candidates[:1]
        first = None
        for candidate in candidates:
            # Availability may drain exploration batches. Trial projections must
            # never mutate real protection, reservations or accounts.
            preview = {**self.s, 'nodes': {key: copy_node(value) for key, value in self.s['nodes'].items()},
                       'accounts': copy.deepcopy(self.s['accounts'])}
            projected = copy.deepcopy(candidate['projected_node'])
            preview['nodes'][node['id']] = projected
            trial = ResourceScheduler(self.c, preview, self.now)
            accounts, shared, reason = trial._native_availability(projected, for_wake=for_wake)
            result = {**candidate, 'account_ids': accounts, 'shared': shared, 'reason': reason}
            first = first or result
            if accounts is not None:
                return result
        return first

    def native_availability(self, node, *, for_wake=False):
        if node.get('checkpoint', {}).get('work_plan'):
            from .native_work_plan import record_view, apply_selection
            try:
                selected = self.select_work_candidate(node, record_view(self.s, node), for_wake=for_wake)
            except ValueError:
                return None, False, '阶段引用已变化；沿原记录核对阶段计划，不重复业务'
            if not selected:
                return None, False, '当前阶段无可推进项或原记录不可读；核对共同条件及原结果，不循环领取'
            apply_selection(node, selected)
        result = self._native_availability(node, for_wake=for_wake)
        if node.get('work_protection') and result[0] is None:
            self.maybe_reserve(node, self.candidate_sets(node, include_busy=True))
        return result

    def _native_availability(self, node, *, for_wake=False):
        """Keep account/fairness decisions shared; wake may precede environment setup."""
        accounts = None
        shared = False
        from .native_executor_status import unavailable
        if unavailable(node):
            return None, False, '模型不可用：' + node['native_executor_status']['reason']
        if not dependencies_completed(self.s, node):
            reason = '等待前置任务完成；当前会话结束等待，不轮询'
        elif self.locks_conflict(node):
            reason = '等待其他模块交还业务资源；当前会话结束等待，不轮询'
        else:
            required = self.candidate_sets(node, include_busy=True)
            if required is None or any(not group for group in required) or self._assign(required) is None:
                reason = '缺少本阶段匹配账号；当前会话结束等待，不轮询'
            else:
                accounts = self.bundle(node)
                if accounts and len(accounts) == 1 and self.can_share(node, accounts[0]):
                    free = {physical_key(self.s['accounts'][aid])
                            for group in (self.candidate_sets(node) or []) for aid in group}
                    peers = [other for other in self.s['nodes'].values()
                             if other['id'] != node['id'] and not other.get('child_ids')
                             and self.project(other) == self.project(node)
                             and self.s['tasks'][other['task_id']].get('execution_route') == 'native_browser'
                             and self.s['tasks'][other['task_id']]['intent'] == 'run'
                             and other.get('control_intent', 'run') == 'run'
                             and other['state'] in {'queued', 'running'}
                             and self.can_share(other, accounts[0])]
                    if len(free) == 1 and peers:
                        shared = True
                if accounts is None:
                    accounts = self.bundle(node, shared=True)
                    shared = accounts is not None
                if accounts is not None:
                    from .native_contexts import can_prepare_for_wake, choose_context, wait_reason
                    if choose_context(self.s, node, accounts) is None:
                        if for_wake and can_prepare_for_wake(self.s, node, accounts):
                            return accounts, shared, '账号资源可用，可唤醒原会话准备独立环境；平台尚未分配账号'
                        return None, False, wait_reason(node)
                ready = accounts is not None
                reason = ('账号资源可用，可唤醒原会话领取；平台尚未分配账号'
                          if ready else '等待其他模块交还账号；当前会话结束等待，不轮询')
                if not ready:
                    self.close_for_waiter(node, required)
        return accounts, shared, reason

    def schedule_native(self, db, node):
        """Allocate only on an explicit claim; sleeping desktop turns never get leases."""
        requested = node.pop('native_claim_pending', False)
        node.pop('exploration_gap', None)
        accounts, shared, reason = self.native_availability(node)
        ready = accounts is not None
        if requested and node.get('direct_holder') and ready:
            return self.grant(db, node, accounts, None, shared)
        node['reason'] = reason
        from .native_handoff import coordinator_ref, thread_id
        reference = coordinator_ref(node)
        node['resource_wait'] = {'end_turn': True, 'resources_available': ready,
                                 'wake_owner': 'coordinator_handoff' if thread_id(reference) else 'unbound',
                                 'coordinator_ref': reference, 'task_id': node['task_id'],
                                 'node_id': node['id'], 'reason': reason}
        from .native_contexts import requires_context
        from .native_executor_status import unavailable
        if unavailable(node):
            node['resource_wait']['kind'] = 'model_unavailable'
        elif not dependencies_completed(self.s, node):
            node['resource_wait']['kind'] = 'dependency_unavailable'
        elif self.locks_conflict(node):
            node['resource_wait']['kind'] = 'business_resource_busy'
        elif '缺少本阶段' in reason:
            node['resource_wait']['kind'] = 'account_configuration_missing'
        elif (requires_context(node) or self.s['tasks'][node['task_id']].get('native_browser_policy') == 'direct_isolated') and ('浏览器登录' in reason or '登录容量' in reason):
            node['resource_wait']['kind'] = 'native_environment_unavailable'
        else:
            node['resource_wait']['kind'] = 'account_available' if ready else 'account_busy'
        return None

    def schedule(self, db, *, native_handoff_source=None):
        self.refresh()
        ready = self.queue()
        grants = []
        for node in ready:
            if self.s['tasks'][node['task_id']].get('execution_route') == 'native_browser':
                grant = self.schedule_native(db, node)
                if grant:
                    grants.append(grant)
                continue
            candidates=self.eligible(node)
            peers=[n for n in ready if self.project(n)==self.project(node) and self.runnable(n)
                   and n.get('phase')=='exploration']
            if (node.get('phase')=='exploration' and len(peers)>len({physical_key(a) for a in candidates})
                    and candidates and not any(self.policy(node,a['id']) for a in candidates)):
                node['exploration_gap']=self.preparation_gap(node,[a['id'] for a in candidates])
            elif any(self.policy(node,a['id']) for a in candidates):node.pop('exploration_gap',None)
            direct = self.s['tasks'][node['task_id']].get('execution_route') == 'local_browser'
            if direct and (not node.get('direct_holder') or self.now - node.get('actor_seen', 0) > 600):
                node['reason'] = '等待当前 Codex 会话领取；不会启动后台 Codex'
                continue
            if not dependencies_completed(self.s, node):
                node['reason'] = '等待前置任务完成'
                continue
            if self.locks_conflict(node):
                node['reason'] = '等待共享业务资源释放'
                continue
            required = self.candidate_sets(node, include_busy=True)
            if required is None or any(not c for c in required) or self._assign(required) is None:
                node['reason'] = '资源配置不足：缺少本阶段匹配环境、租户、角色或完整账号集合'
                self.c.notice(self.s, node, 'resource_configuration', node['reason'])
                continue
            units = len(required)
            runners = self.runner_candidates(node, units)
            if not runners:
                node['reason'] = '等待无界面浏览器连接或机器容量；当前聊天不占后台 Codex 容量' if direct else '等待后台执行器或执行容量'
                continue
            allocated = False
            preparation_wait = False
            preparation_account_wait = False
            for runner in runners:
                accounts = self.bundle(node, runner=runner, peers=[n for n in ready if self.runnable(n)])
                shared = False
                if accounts and len(accounts) == 1 and not node.get('protected'):
                    aid = accounts[0]
                    free = {a for group in (self.candidate_sets(node) or []) for a in group}
                    explorers = [peer for peer in ready if peer['id'] != node['id']
                        and self.runnable(peer) and self.project(peer) == self.project(node)
                        and (self.s['tasks'][peer['task_id']].get('execution_route') != 'local_browser'
                             or (peer.get('direct_holder') and self.now-peer.get('actor_seen',0) <= 600))
                        and self.can_share(peer, aid)
                        and any(aid in group for group in (self.candidate_sets(peer, include_busy=True) or []))]
                    if (len(free) == 1 and len(explorers) > 1 and not self.can_share(node, aid)
                            and not self.exploration_in_progress(explorers[0])
                            and any(self.can_share(peer, aid, host) for peer in explorers
                                    for host in self.runner_candidates(peer, 2))):
                        # Exclusive queue heads must not consume the final account
                        # before overflow explorers get their preparation turn.
                        preparation_account_wait = True
                        continue
                # At the browser-capacity boundary, use an already prepared
                # batch rather than spend its released probe slot on another
                # exclusive account. This never preempts an existing holder.
                if accounts and runner not in self.runner_candidates(node, units + 1):
                    prepared = self.bundle(node, shared=True, runner=runner, peers=ready)
                    if prepared and self.holders(prepared[0]):
                        accounts, shared = prepared, True
                if accounts and len(accounts) == 1 and self.can_share(node, accounts[0]):
                    aid = accounts[0]
                    others = [n for n in ready if n['id'] != node['id'] and self.runnable(n)
                              and self.can_share(n, aid)
                              and any(aid in c for c in (self.candidate_sets(n, include_busy=True) or []))]
                    free = {a for c in (self.candidate_sets(node) or []) for a in c}
                    # Keep ordinary execution first while both it and the live
                    # probe fit. Account overflow must prepare before the last
                    # two browser units are consumed by ordinary leases.
                    from .exploration_learning import PROFILE
                    exclusive_peers = [n for n in ready if n['id'] != node['id'] and self.runnable(n)
                        and self.project(n) == self.project(node) and not self.can_share(n, aid)
                        and any(aid in group for group in (self.candidate_sets(n, include_busy=True) or []))]
                    exclusive_units = sum(len(self.candidate_sets(n, include_busy=True) or []) for n in exclusive_peers)
                    # A later exclusive-only member cannot prepare the last
                    # account. Prepare here when its demand would consume that
                    # opportunity, while keeping its own exclusive grant intact.
                    account_boundary = (len(others) + exclusive_units >= len(free)
                        and len(free) <= exclusive_units + 1)
                    preparation_boundary = (self.policy(node, aid).get('automatic_profile') == PROFILE
                        and (account_boundary or (len(others) + exclusive_units >= len(free)
                            and runner not in self.runner_candidates(node, units + 2 + exclusive_units))))
                    prepare_due = bool(others and not self.exploration_in_progress(node)
                        and (self.s['accounts'][aid].get('pool') == 'exploration'
                             or len(free) == 1 or preparation_boundary))
                    if prepare_due and self.can_share(node, aid, runner):
                        shared = True
                    elif prepare_due:
                        policy = self.policy(node, aid)
                        evidence = runner.get('evidence', {})
                        if (policy.get('automatic_profile') == PROFILE and evidence.get('shared_exploration')
                                and evidence.get('automatic_exploration', 0) >= policy.get('adapter_schema', 1)
                                and any(self.project(self.s['nodes'][l['node_id']]) == self.project(node)
                                        for l in self.s['leases'].values())):
                            # Do not consume the preparation opportunity one
                            # ordinary browser at a time as capacity recovers.
                            # Existing work continues; another host may fit it.
                            preparation_wait = True
                            continue
                if accounts is None:
                    accounts = self.bundle(node, shared=True, runner=runner, peers=ready)
                    if accounts and not self.holders(accounts[0]) and self.exploration_in_progress(node):
                        accounts = None
                    shared = accounts is not None
                if accounts is not None:
                    for earlier in ready[:ready.index(node)]:
                        if not self.runnable(earlier): continue
                        earlier_choices = self.candidate_sets(earlier, include_busy=True)
                        if earlier_choices and len(earlier_choices) > 1 and any(a in c for a in accounts for c in earlier_choices):
                            earlier['protected'] = True
                            earlier.setdefault('bypass_events', []).append({'at': self.now, 'by': node['id'],
                                'accounts': list(accounts), 'kind': 'complete_set_opportunity'})
                    grants.append(self.grant(db, node, accounts, runner, shared))
                    allocated = True
                    break
            if not allocated:
                self.close_for_waiter(node, required)
                self.maybe_reserve(node, required)
                node['reason'] = ('等待探索批次交接或本阶段完整账号集合' if any(self.holders(a) for c in required for a in c)
                                  else '等待匹配账号资源')
                if node.get('phase') == 'execution' and any(self.holders(a) for c in required for a in c):
                    node['reason'] = '等待其他模块交还本阶段所需的独占账号'
                if node.get('phase') == 'exploration' and not any(self.policy(node, a) for c in required for a in c):
                    node['exploration_gap']=self.preparation_gap(node,{a for c in required for a in c})
                    node['reason'] += '；'+node['exploration_gap']['message']
                else:
                    node.pop('exploration_gap', None)
                if preparation_account_wait:
                    node['reason'] = '等待探索批次准备及交接；最后一个可用账号保留给待探索模块，已分配任务继续'
                if preparation_wait:
                    node['reason'] = '等待原机器容量容纳探索准备及核验浏览器；已分配的独占任务继续'
        from .native_handoff import reconcile_resources
        reconcile_resources(self.c, self.s, preferred=native_handoff_source)
        return grants


def apply_account_selection(node, account_ids, selection='required'):
    from .orchestration import strings
    values = strings(account_ids, 'account_ids', 16)
    if len(set(values)) != len(values):
        raise ValueError('account_ids 必须是无重复列表')
    if selection not in {'required', 'preferred'}:
        raise ValueError('account_selection 必须为 required 或 preferred')
    node['requested_account_ids'] = values if selection == 'required' else []
    node['preferred_account_ids'] = values if selection == 'preferred' else []


def apply_request(node, request):
    node['policy_cleanup_unit_id'] = request.get('policy_cleanup_unit_id', '')
    if 'requirements' in request:
        node['requirements'] = copy.deepcopy(request['requirements'])
    if 'account_ids' in request:
        apply_account_selection(node, request['account_ids'], request.get('account_selection', 'required'))
    if 'locks' in request:
        node['locks'] = list(dict.fromkeys([*node.get('inherited_locks', []), *request['locks']]))
    if request.get('next_phase'):
        node['phase'] = request['next_phase']
        if request['next_phase'] != 'exploration':
            node['exploration_complete'] = True
    if request.get('exclusive_exploration'):
        node['exclusive_exploration'] = True
    if request.get('checkpoint'):
        node['checkpoint'] = {**node.get('checkpoint', {}), **copy.deepcopy(request['checkpoint'])}


def request_resources(controller, db, state, lease, request):
    """A phase transition, never an extra check on ordinary browser actions."""
    from .orchestration import Conflict, strings, text, queue_key
    from .cleanup_capabilities import blockers
    node = state['nodes'][lease['node_id']]
    task = state['tasks'][node['task_id']]
    if lease.get('revoked') or task['intent'] != 'run' or node.get('control_intent', 'run') != 'run':
        raise Conflict('当前执行已撤权，不能申请下一阶段资源')
    planned = copy_node(node)
    normalized = {key: copy.deepcopy(request[key]) for key in
                  ('requirements', 'account_ids', 'account_selection', 'locks', 'next_phase', 'exclusive_exploration', 'checkpoint')
                  if key in request and request[key] is not None
                  and not (key in {'next_phase', 'locks'} and not request[key])}
    stage = None
    token = (request.get('arguments') or {}).get('work_token')
    if token is not None:
        from .native_work_plan import validate_token
        stage = validate_token(controller, state, node, token)
        if stage['eligibility'] == 'excluded':
            from .testing_policy import excluded_response
            return excluded_response()
        planned = copy.deepcopy(stage['projected_node'])
        requires = next(u['requires'] for u in node['checkpoint']['work_plan']['units'] if u['id'] == token['work_unit_id'])
        normalized = {**copy.deepcopy(requires), 'next_phase': requires['phase']}
        normalized.pop('phase')
    if 'account_selection' in normalized and 'account_ids' not in normalized:
        raise ValueError('account_selection 需同时明确 account_ids；不推断旧指定集合是偏好')
    if 'account_ids' in normalized:
        normalized['account_ids'] = strings(normalized['account_ids'], 'account_ids', 16)
    if 'locks' in normalized:
        normalized['locks'] = list(dict.fromkeys([*node.get('inherited_locks', node.get('locks', [])),
                                                *strings(normalized['locks'], '业务资源锁')]))
    if 'requirements' in normalized:
        requirements = normalized['requirements']
        if not isinstance(requirements, list) or not (0 if stage else 1) <= len(requirements) <= 16:
            raise ValueError('需要 1–16 个本阶段身份需求')
        normalized['requirements'] = [{k: text(r.get(k), k, 500) for k in ('target', 'environment', 'tenant', 'role')}
                                      for r in requirements]
    if normalized.get('next_phase') not in {None, 'exploration', 'execution', 'report'}:
        raise ValueError('阶段错误')
    if normalized.get('exclusive_exploration') and normalized.get('next_phase') not in {None, 'exploration'}:
        raise ValueError('尚需独占探索时不能同时声明探索完成；请使用 exploration 阶段')
    if task['mode'] == 'design' and normalized.get('next_phase') == 'execution':
        raise PermissionError('仅设计任务不能转入业务执行')
    normalized['policy_cleanup_unit_id'] = stage['projected_node'].get('policy_cleanup_unit_id', '') if stage else ''
    apply_request(planned, normalized)
    from .testing_policy import resource_excluded, excluded_response
    if resource_excluded(planned, state):
        return excluded_response()
    if blockers(state, lease, replacing=True):
        raise Conflict('原清理操作或真实现场仍待核实；保留原租约，不切换资源阶段')
    scheduler = ResourceScheduler(controller, state, controller.clock())
    eligible = {a['id'] for a in scheduler.eligible(planned)}
    if any(a not in eligible for a in [*planned.get('requested_account_ids', []), *planned.get('preferred_account_ids', [])]):
        raise PermissionError('资源集合包含本项目未授权或不属于目标的账号')
    target = scheduler.target(planned)
    if any(r['target'].rstrip('/') != target for r in planned.get('requirements', [])):
        raise PermissionError('身份需求越出当前测试目标')
    if normalized.get('checkpoint'):
        if 'work_plan' in normalized['checkpoint']:
            from .native_work_plan import record_view, update_work_plan
            normalized['checkpoint']['work_plan'] = update_work_plan(controller, state, node,
                normalized['checkpoint']['work_plan'], record_view(state, node))
        node['checkpoint'] = {**node.get('checkpoint', {}), **copy.deepcopy(normalized['checkpoint'])}
    if pending_operations(state, lease['id']):
        lease['resource_request'] = normalized
        return {'continued': False, 'release_required': False, 'state': 'waiting_resources',
                'reason': '原操作结果尚未核实，保留现场，不重复执行或交还账号'}
    accounts = scheduler.bundle(planned, ignore_lease=lease['id'])
    blocking_protection = []
    bypassed = []
    if lease['mode'] == 'shared':
        for other in state['nodes'].values():
            if other['id'] == node['id'] or not scheduler.runnable(other):
                continue
            if state['tasks'][other['task_id']].get('execution_route') in {'local_browser', 'native_browser'} and not other.get('direct_holder'):
                continue
            choices = scheduler.candidate_sets(other, include_busy=True) or []
            overlaps = any(any(physical_key(state['accounts'][a]) == physical_key(state['accounts'][held])
                               for held in lease['account_ids']) for c in choices for a in c)
            if not overlaps or scheduler.bundle(other) is not None:
                continue
            if other.get('protected'):
                blocking_protection.append(other['id'])
            else:
                bypassed.append(other)
    runner = state['runners'].get(lease['runner_id'], {})
    if lease.get('native_browser'):
        from .native_contexts import choose_context
        context = choose_context(state, planned, accounts, ignore_lease=lease['id']) if accounts is not None else None
        capacity = accounts is not None and context is not None
    else:
        capacity = accounts is not None and any(r['id'] == lease['runner_id']
            for r in scheduler.runner_candidates(planned, len(accounts), ignore_lease=lease['id']))
    same_accounts = accounts is not None and set(accounts) == set(lease['account_ids'])
    if same_accounts and capacity and not scheduler.locks_conflict(planned, lease['id']) and not blocking_protection:
        old_accounts = list(lease['account_ids'])
        apply_request(node, normalized)
        if stage:
            from .native_work_plan import apply_selection
            apply_selection(node, stage)
        for waiter in bypassed:
            waiter['protected'] = True
            waiter.setdefault('bypass_events', []).append({'at': controller.clock(), 'by': node['id'],
                                                           'accounts': old_accounts, 'kind': 'exploration_continuation'})
        lease.update(account_ids=accounts, browser_units=lease.get('browser_units', 0) if lease.get('native_browser') else len(accounts), mode='exclusive', policy_id='', exploration_bootstrap=False,
                     resource_version=lease.get('resource_version', 0) + 1)
        if lease.get('native_browser'):
            lease['shared_enforcement'] = None
        lease.pop('resource_request', None)
        node.pop('resource_wait', None)
        for aid in old_accounts:
            batch = state['accounts'][aid].get('exploration_batch')
            if batch and node['id'] in batch.get('members', []):
                batch.update(state='closed', members=[], target_node=None, closed=controller.clock())
            state['accounts'][aid]['pool'] = 'execution'
        node['reason'] = ''
        controller.audit(db, node['owner'], 'resources.transition', node['id'], 'atomic complete set; existing lease retained')
        return {'continued': True, 'state': node['state'], 'mode': 'exclusive', 'lease_id': lease['id'],
                'account_ids': accounts, 'resource_version': lease['resource_version']}
    # A resource boundary is not a reason to idle an otherwise useful lease.
    # Unknown operations were handled above; retained scenes and protected
    # contenders still take precedence over this continuation.
    work = node.get('checkpoint', {}).get('work_plan')
    if work and not retention_conditions(node, lease):
        from .execution_work_plan import select_next_work, project_work_candidates
        from .native_work_plan import record_view, RESOURCE_FIELDS
        view = record_view(state, node)
        protected_overlap = any(other['id'] != node['id'] and other.get('protected') and scheduler.runnable(other)
            and any(physical_key(state['accounts'][aid]) == physical_key(state['accounts'][held])
                    for group in (scheduler.candidate_sets(other, include_busy=True) or []) for aid in group
                    for held in lease['account_ids']) for other in state['nodes'].values())
        if view and not protected_overlap:
            remaining = select_next_work(view, work, {**lease, 'locks': node.get('locks', []),
                'work_unit_receipts': node.get('work_unit_receipts', {}),
                'accounts': [state['accounts'][aid] for aid in lease['account_ids']]})
            if remaining['runnable_unit_ids']:
                candidates = project_work_candidates(node, view)
                deferred = next((c['unit_id'] for c in candidates if all(
                    c['projected_node'].get(k) == planned.get(k, False if k in {'exclusive_exploration','exploration_complete'} else [])
                    for k in RESOURCE_FIELDS)), None)
                lease.pop('resource_request', None)
                node.pop('resource_wait', None)
                return {'continued': True, 'release_required': False, 'state': node['state'],
                    'next_action': 'continue_current_work', 'lease_id': lease['id'], 'mode': lease['mode'],
                    'account_ids': list(lease['account_ids']), 'deferred_work_unit_id': deferred,
                    **remaining}
    lease['resource_request'] = normalized
    choices = scheduler.candidate_sets(planned, include_busy=True)
    missing = choices is None or any(not c for c in choices) or scheduler._assign(choices) is None
    blockers = {holder['node_id'] for c in (choices or []) for aid in c for holder in scheduler.holders(aid, lease['id'])}
    blockers.update(l['node_id'] for l in state['leases'].values() if l['id'] != lease['id'] and
                    set(state['nodes'][l['node_id']].get('locks', [])).intersection(planned.get('locks', [])))
    blockers.update(blocking_protection)
    node['resource_wait'] = {'blockers': sorted(blockers), 'account_ids': planned.get('requested_account_ids', []),
                             'requirements': planned.get('requirements', []), 'since': node.get('resource_wait', {}).get('since', controller.clock())}
    for aid in lease['account_ids']:
        batch = state['accounts'][aid].get('exploration_batch')
        if lease['mode'] == 'shared' and batch:
            target_node = blocking_protection[0] if blocking_protection else node['id']
            if batch.get('state') != 'draining' or batch.get('target_node') != target_node:
                batch.update(state='draining', target_node=target_node,
                             reason='下一阶段需要独占，等待其他共享成员安全退出', revision=batch.get('revision', 1) + 1)
    def cycle(current, path):
        if current in path:
            return path[path.index(current):]
        for other in state['nodes'].get(current, {}).get('resource_wait', {}).get('blockers', []):
            found = cycle(other, path + [current])
            if found:
                return found
        return []
    conflict = cycle(node['id'], [])
    safe = not retention_conditions(node, lease) and not pending_operations(state, lease['id'])
    reason = ('资源配置不足，完整阶段集合无法由现有账号满足' if missing else
              '资源依赖成环；保留现场及顺位，需安全交还一方或补充资源' if conflict else
              '等待已受保护任务取得账号，当前阶段可安全交还' if blocking_protection else
              '下一阶段账号集合变化，安全交还原浏览器后按完整集合重新领取' if accounts is not None and not same_accounts else
              '等待本阶段完整资源集合或探索成员退出')
    node['reason'] = reason
    if conflict or missing:
        controller.notice(state, node, 'resource_conflict' if conflict else 'resource_configuration', reason)
    result = {'continued': False, 'release_required': safe, 'state': 'waiting_resources', 'reason': reason,
              'blockers': sorted(blockers), 'cycle': conflict, 'resource_configuration_missing': missing}
    if lease.get('native_browser'):
        result.update(next_action='finish_after_browser_stopped' if safe else 'resolve_existing_hold',
                      browser_stopped_required=True,
                      guidance='关闭本任务原生浏览器页面并确认操作停止后，以原 lease 调用 finish(outcome=yield,arguments={browser_stopped:true})；平台保留阶段需求和顺位，待账号可用后沿原节点 claim。不自动释放活跃浏览器，不重放业务动作。')
    return result
