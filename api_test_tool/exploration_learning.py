"""Live, account-exclusive preparation for the generic exploration pool.

The user explicitly accepts residual uncertainty from empirical verification.
These rules are labelled observed_read, never source-verified. The executing
model proposes only real navigation links; this broker performs the checks and
creates the request contract. No cached response is served to an explorer.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import re
from urllib.parse import parse_qs, unquote, urlsplit
from .browser_policy import origin

PROFILE = 'platform-observed-v1'
ENTRY_TIMEOUT_SECONDS = 15


def command_timeout(action, parameters):
    """A multi-entry verification is a batch, not one browser interaction.

    Keep each existing 15-second navigation bound and ordinary commands' 75
    seconds. Reserve two visits per unique entry (plus the source page), source
    drain/concurrent recheck, and the ordinary setup/receipt/cleanup allowance.
    """
    if action == 'batch':
        from .browser_batch import steps
        steps(parameters)
        # Each step owns its timeout and cancellation receipt. An outer timer
        # must not interrupt final receipt assembly and discard partial results.
        return None
    entries = parameters.get('entry_urls') if isinstance(parameters, dict) else None
    if action != 'prepare_exploration' or not isinstance(entries, list) or not all(isinstance(x,str) for x in entries):
        return 75
    return 75 + ENTRY_TIMEOUT_SECONDS * (2 * (len(set(entries)) + 1) + 2)
# An exclusion is not a safety proof. Candidates must also pass live comparisons.
MUTATION = re.compile(r'(?:^|[^a-z0-9])(?:logout|signout|delete|remove|destroy|create|save|update|submit|send|publish|execute|trigger|activate|deactivate|subscribe|unsubscribe|checkout|purchase|payment|approve|reject|mark|reset|switch|start|stop|cancel|enable|disable|grant|revoke)(?:$|[^a-z0-9])', re.I)
SECRET = re.compile(r'password|passwd|secret|token|authorization|session|signature|api.?key|credential|code', re.I)
READ_POST = re.compile(r'(?:^|/)(?:search|query|list|filter|page|detail|lookup)(?:/|$)', re.I)


def candidate(url, method, body, resource_type, target):
    """Produce an exact candidate, not permission to use it while shared."""
    try:
        parsed = urlsplit(url)
        destination = origin(url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        path = unquote(parsed.path)
    except (ValueError, TypeError):
        return None
    if (looks_mutating(path+'?'+unquote(parsed.query)) or '\\' in path
            or any(part in {'.','..'} for part in path.split('/'))
            or re.search(r'%2f|%5c|%25',parsed.path,re.I)
            or contains_secret(query)):
        return None
    if destination != target and resource_type not in {'script','stylesheet','image','font','xhr','fetch'}:
        return None
    payload = {}
    if method == 'POST':
        try:payload = json.loads(body or '')
        except (ValueError, TypeError):return None
        if not isinstance(payload, dict) or contains_secret(payload):return None
        graphql = payload.get('query')
        is_query = (isinstance(graphql, str) and re.match(r'^\s*(?:query\b|\{)', graphql)
                    and not re.search(r'\b(?:mutation|subscription)\b', graphql))
        if not is_query and not READ_POST.search(path):return None
        if looks_mutating(json.dumps(payload, ensure_ascii=False)):return None
    elif method != 'GET' or body:
        return None
    rule = dict(origin=destination, path=parsed.path, path_pattern=re.escape(parsed.path),
                method=method, effect='observed_read', query_hash=value_hash(query), body_hash=value_hash(payload))
    return rule


def looks_mutating(value):
    return bool(MUTATION.search(re.sub(r'([a-z0-9])([A-Z])',r'\1_\2',value))
                or re.search(r'删除|保存|提交|发送|发布|启用|停用|支付|注销|登出|标记|切换',value))


def value_hash(value):
    return signature(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode())


def contains_secret(value):
    if isinstance(value,dict):return any(SECRET.search(key) or contains_secret(item) for key,item in value.items())
    if isinstance(value,list):return any(contains_secret(item) for item in value)
    if isinstance(value,str):return bool(re.search(r'(?:password|secret|token|authorization)\s*[:=]|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.',value,re.I))
    return False


async def export_session(context, page):
    storage=await context.storage_state(indexed_db=True)
    storage['session_storage']={origin(page.url):await page.evaluate('() => Object.fromEntries(Object.entries(sessionStorage))')}
    return storage


async def install_session(context, storage):
    # A broker-owned initialization script; never a model-supplied expression.
    values=json.dumps(storage.get('session_storage',{}),ensure_ascii=False)
    await context.add_init_script('(() => { const values = '+values+'; const own = values[location.origin]; '
                                  'if (own) for (const [key,value] of Object.entries(own)) '
                                  'if (sessionStorage.getItem(key) === null) sessionStorage.setItem(key,value); })();')


def browser_storage(storage):
    return {key:storage.get(key,[]) for key in ('cookies','origins')}


def rule_key(rule):
    return json.dumps(rule, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def signature(content):
    return hashlib.sha256(content).hexdigest()


def view_signature(snapshot):
    return signature(re.sub(r'\s+', ' ', snapshot).strip().encode())


async def links(page, target):
    # Real DOM links only. This internal read never exposes evaluate to a model.
    entries = await page.locator('a[href]').evaluate_all("elements => elements.map(e => ({url:e.href,label:(e.innerText||e.getAttribute('aria-label')||'').trim()}))")
    out = {}
    for entry in entries:
        url = entry['url']
        if candidate(url, 'GET', None, 'document', target):
            try:
                if origin(url) == target:out[url] = entry['label']
            except ValueError:pass
    return [{'url':url, 'label':label} for url,label in out.items()]


async def visible_password(page):
    fields = page.locator('input[type=password]')
    return any([await fields.nth(i).is_visible() for i in range(await fields.count())])


async def rendered_view(page, url, expected=None):
    """Wait for a stable rendered view, not termination of background fetches.

    Keep the existing per-entry deadline. An expected source/peer view must
    actually appear; loading shells cannot substitute for that observation.
    """
    async with asyncio.timeout(ENTRY_TIMEOUT_SECONDS):
        await page.goto('about:blank')
        await page.goto(url,wait_until='domcontentloaded',timeout=ENTRY_TIMEOUT_SECONDS*1000)
        await page.wait_for_load_state('load')
        previous=None;unchanged_since=0
        loop=asyncio.get_running_loop()
        while True:
            if await visible_password(page) or page.url != url:
                raise ValueError('登录态不兼容或入口发生未核验跳转')
            snapshot=await page.locator('body').aria_snapshot()
            current=view_signature(snapshot)
            if current != previous:
                previous=current;unchanged_since=loop.time()
            if snapshot.strip() and (expected is None or current==expected) and loop.time()-unchanged_since>=0.5:
                return current
            await asyncio.sleep(0.1)


async def drain_source(broker, lid, aid, context, target, verified=None):
    """Quiesce login/background reads without forgetting unresolved writes.

    Stop admitting new requests locally, wait for pre-existing non-GET or
    unknown requests to finish normally, then dispose the context containing remaining read
    candidates. Context closure must complete before replacing its ledger;
    cancelled reads never become evidence for an observed_read rule.
    """
    broker.source_draining.add(lid)
    try:
        async with asyncio.timeout(ENTRY_TIMEOUT_SECONDS):
            while True:
                broker.network_changed[lid].clear()
                pending = [request for request in broker.inflight.get(lid, ())
                           if verified is None or not verified(request)]
                if not any(request.method != 'GET' or not candidate(
                        request.url, request.method, request.post_data, request.resource_type, target)
                           for request in pending):
                    break
                await broker.network_changed[lid].wait()
            restarted=False
            page=broker.pages[(lid,aid)]
            if pending:
                # Page.stopLoading cannot cancel keepalive fetches owned by a
                # previous document. Dispose the real context, not its ledger.
                storage=await export_session(context,page)
                context,page=await broker.restart_preparation_context(lid,aid,storage)
                restarted=True
            if restarted or verified is None:
                await broker.network_idle[lid].wait()
            return context,page,restarted
    finally:
        broker.source_draining.discard(lid)


async def drain_unverified(broker,lid,aid,context,target,policy):
    # Requests admitted by the final local policy may continue while sharing
    # opens. Only traffic predating that policy needs a transition boundary.
    def verified(request):
        try:
            return policy.match_request(request.url,request.method,request.post_data)['effect']=='observed_read'
        except (ValueError,PermissionError):
            return False
    if all(verified(request) for request in broker.inflight.get(lid,())):
        return context,broker.pages[(lid,aid)],False
    return await drain_source(broker,lid,aid,context,target,verified)


async def prepare(broker, lid, aid, entries, operation_id):
    key = (lid, aid)
    active = broker.active[lid]
    policy = broker.policy_documents[key]
    if (active.get('mode') != 'exclusive' or not active.get('exploration_bootstrap')
            or policy.get('automatic_profile') != PROFILE):
        raise ValueError('实时自动核验只在平台分配的独占准备阶段运行')
    if not isinstance(entries, list) or not entries or any(not isinstance(url, str) for url in entries):
        raise ValueError('entry_urls 须选择本轮模块对应的实际 navigation_links，不填写请求策略')
    page = broker.pages[key]
    target = policy['target_origin']
    available = {item['url'] for item in await links(page,target)} | {page.url} | set(broker.navigation_history.get(lid,{}))
    entries = list(dict.fromkeys(entries))
    if any(url not in available or origin(url) != target or not candidate(url,'GET',None,'document',target) for url in entries):
        raise ValueError('准备入口必须来自当前真实页面、属于本项目且不含已识别写入或凭据参数')
    if await visible_password(page) or not broker.login_associated.get(lid):
        return failure('当前账号的正常登录尚未完成；继续原现场登录后再准备探索池',pending=True)
    context = broker.contexts[key]
    seed = await export_session(context,page)
    if (not seed.get('cookies') and not any(item.get('localStorage') or item.get('indexedDB') for item in seed.get('origins',[]))
            and not any(seed.get('session_storage',{}).values())):
        return failure('当前页面没有可供独立浏览器核验的登录态')
    before = await page.locator('body').aria_snapshot()
    if not before.strip():return failure('当前页面尚未就绪，不能据此核验会话兼容',pending=True)
    original_url = page.url
    rules = {}; asset_checks = {}; accepted = []; excluded = []; blocked = set(); checks = []
    observed = {}; captures = set()
    probe = None
    stage = 'source_requests'
    broker.learning.add(lid)

    async def guard(route, request):
        if broker.active.get(lid,{}).get('revoked',True):
            await route.abort();return
        rule = candidate(request.url,request.method,request.post_data,request.resource_type,target)
        if rule is None or 'text/event-stream' in request.headers.get('accept',''):
            blocked.add((request.method,urlsplit(request.url).path))
            await route.abort();return
        broker._sent.add(operation_id)
        await route.continue_()

    async def capture(response, bucket):
        request = response.request
        rule = candidate(request.url,request.method,request.post_data,request.resource_type,target)
        if not rule or not 200 <= response.status < 300:return
        content_type = response.headers.get('content-type','').split(';')[0]
        if content_type == 'text/event-stream':return
        try:
            if request.resource_type == 'document':
                # The real rendered view is independently compared below.
                fingerprint = 'document:rendered-view-compared'
            else:
                content = await response.body()
                if 'json' in content_type:
                    content = json.dumps(json.loads(content),sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
                fingerprint = signature(content)
            k = rule_key(rule)
            bucket.setdefault(k, {'rule':rule,'fingerprints':set(),'asset':request.resource_type in {'script','stylesheet'}})['fingerprints'].add(fingerprint)
        except Exception:
            # A missing body is an unverified candidate, never a successful read.
            return

    def on_response(response):
        bucket = observed
        task = asyncio.create_task(capture(response,bucket))
        captures.add(task);task.add_done_callback(captures.discard)

    async def load(probe_page, url, expected=None):
        try:
            return await rendered_view(probe_page,url,expected)
        finally:
            # Never approve an unfinished body or hold page readiness hostage
            # to a long-poll/stream. Only completed captures populate rules.
            pending=[task for task in captures if not task.done()]
            for task in pending:task.cancel()
            if pending:await asyncio.gather(*pending,return_exceptions=True)

    try:
        # Cancel leftover read candidates from login using browser lifecycle
        # control; unknown/write requests must finish before that is permitted.
        context,page,restarted = await drain_source(broker,lid,aid,context,target)
        if restarted:
            stage = 'source_restore'
            broker._sent.add(operation_id)
            await rendered_view(page,original_url,view_signature(before))
            if page.url != original_url or await visible_password(page):
                raise ValueError('源登录上下文重建后无法恢复原页面')
            restored = await page.locator('body').aria_snapshot()
            if view_signature(restored) != view_signature(before):
                raise ValueError('源登录上下文重建后页面状态不同')
        seed = await export_session(context,page)
        before = await page.locator('body').aria_snapshot()
        stage = 'probe_context'
        # One additional context is reserved by the scheduler before preparation.
        probe = await broker.browsers[key].new_context(storage_state=browser_storage(seed),service_workers='block',accept_downloads=False)
        broker.probe_contexts[lid] = probe
        await install_session(probe,seed)
        await probe.route('**/*',guard)
        await probe.route_web_socket('**/*',lambda socket:socket.close())
        probe.on('response',on_response)
        probe_page = await probe.new_page()
        # Check the original landing view too; a public link alone cannot certify
        # the account's existing authenticated session.
        for url in list(dict.fromkeys([original_url,*entries])):
            stage = 'entry_comparison'
            rounds = []; views = []
            try:
                for _ in range(2):
                    observed = {}
                    views.append(await load(probe_page,url,view_signature(before) if url==original_url else (views[0] if views else None)))
                    rounds.append(observed)
                if views[0] != views[1]:raise ValueError('重复访问的实际页面状态不同')
                if url == original_url and views[0] != view_signature(before):
                    raise ValueError('独立会话与原已登录页面状态不同')
                stable = {}; stable_assets = {}
                for k, first in rounds[0].items():
                    second = rounds[1].get(k)
                    if second and len(first['fingerprints']) == 1 and first['fingerprints'] == second['fingerprints']:
                        stable[k] = first['rule']
                        if first['asset']:stable_assets[signature(k.encode())]=next(iter(first['fingerprints']))
                document = candidate(url,'GET',None,'document',target)
                if not document or rule_key(document) not in stable:
                    raise ValueError('入口请求未取得两次一致的真实响应')
                rules.update(stable)
                asset_checks.update(stable_assets)
                accepted.append(url)
                checks.append({'url':url,'accepted':True})
            except Exception as exc:
                excluded.append(url)
                # Never copy a browser exception's request headers/body. Keep
                # enough phase evidence to distinguish timeout from mismatch.
                reason = str(exc) if isinstance(exc,ValueError) else type(exc).__name__
                checks.append({'url':url,'accepted':False,'reason':reason})
                if url == original_url:
                    return {**failure('独立浏览器未能复现原登录页面；该账号暂不共享，保留原现场继续处理'), 'entry_checks':checks}
        # Confirm that using the copied session did not invalidate its source.
        stage = 'concurrent_sessions'
        _, peer_view = await asyncio.gather(rendered_view(page,original_url,view_signature(before)),
                                           load(probe_page,original_url,view_signature(before)))
        after = await page.locator('body').aria_snapshot()
        if (page.url != original_url or await visible_password(page) or view_signature(before) != view_signature(after)
                or peer_view != view_signature(before)):
            return failure('独立浏览器核验后原登录页面发生变化；不开放本批次共享')
        # Use the source's current session state after verification, not a stale
        # refresh-token copy from before its normal page reload.
        seed = await export_session(context,page)
        stage = 'session_material'
        if session_fingerprint(seed) != session_fingerprint(await export_session(probe,probe_page)):
            return failure('两个浏览器的登录材料发生变化，未证明可稳定共用；本批次转独占')
        if not any(url in accepted for url in entries):return failure('本轮所选模块入口均未通过实时核验')
        # Tighten the source gate before draining the final in-flight requests.
        # It stays tight while the probe closes and the platform commits sharing.
        from .browser_policy import BrowserPolicy
        document={**policy,'rules':list(rules.values()),'asset_fingerprints':asset_checks,'entry_urls':accepted}
        broker.policy_documents[key]=document
        broker.policies[key]=BrowserPolicy(broker.bound_accounts[key],document,active['context_id'])
        broker.prepared_local.add(lid)
        stage = 'verified_requests'
        context,page,final_restart = await drain_unverified(broker,lid,aid,context,target,broker.policies[key])
        if final_restart:
            stage = 'verified_source_restore'
            # Compare the current server state in both real sessions. The
            # pre-drain snapshot can legitimately age while reads are drained.
            _, restored_peer = await asyncio.gather(
                rendered_view(page,original_url),
                load(probe_page,original_url))
            if page.url != original_url or await visible_password(page):
                raise ValueError('最终共享规则下无法恢复原登录页面')
            if view_signature(await page.locator('body').aria_snapshot()) != restored_peer:
                raise ValueError('最终共享规则下源页面与同时核验页面不同')
            seed = await export_session(context,page)
            if session_fingerprint(seed) != session_fingerprint(await export_session(probe,probe_page)):
                raise ValueError('最终共享规则下两个浏览器登录材料不同')
            restarted=True
        return {'exploration_prepared':True,'verification_mode':'live_empirical',
                'residual_risk':'未观察到的服务端副作用仍可能存在；不作为业务用例通过证据',
                'accepted_entries':accepted,'exclusive_entries':excluded,'observed_request_count':len(rules),
                'source_context_restarted':restarted,
                'session_cookie_expires_at':min((cookie['expires'] for cookie in seed.get('cookies',[])
                    if cookie.get('httpOnly') and isinstance(cookie.get('expires'),(int,float))
                    and cookie['expires']>0),default=None),
                'entry_checks':checks,
                'blocked_request_count':len(blocked),'business_failure':False,
                '_exploration_policy':{'profile':PROFILE,'rules':list(rules.values()),'entry_urls':accepted,'asset_fingerprints':asset_checks,
                    'evidence':{'kind':'live_empirical','session_copy_checked':True,'source_session_checked':True,
                                'concurrent_session_checked':True,
                                'comparisons_per_entry':2,'entry_count':len(accepted),'blocked_request_count':len(blocked)}},
                '_exploration_seed':seed}
    except Exception as exc:
        # Preparation performs read-candidate verification, not a business
        # submission. An expected verification timeout is a known failed check,
        # not an unknown business operation. Cleanup must still succeed below.
        from playwright.async_api import TimeoutError as BrowserTimeout
        if not isinstance(exc,(TimeoutError,BrowserTimeout,ValueError)):
            raise
        pending = [{'method':request.method,'path':urlsplit(request.url).path,
                    'resource_type':request.resource_type}
                   for request in broker.inflight.get(lid,())]
        return {**failure('实时自动核验未完成；保留独占现场，未启用共享'),
                'preparation_stage':stage,'verification_error':type(exc).__name__,
                'verification_detail':str(exc) if isinstance(exc,ValueError) else type(exc).__name__,
                'entry_checks':checks,'pending_requests':pending}
    finally:
        for task in list(captures):task.cancel()
        if captures:await asyncio.gather(*list(captures),return_exceptions=True)
        if probe:
            try:await asyncio.wait_for(probe.close(),timeout=5)
            except Exception:
                # Do not release its reserved capacity while an unconfirmed
                # context could still be sending requests.
                await broker.fence(lid)
                raise RuntimeError('准备浏览器退出未确认，已停止本租约浏览器，原操作需核实') from None
        broker.probe_contexts.pop(lid,None)
        broker.learning.discard(lid)


def session_fingerprint(storage):
    # Ignore expiry metadata, not cookie values or authentication storage. A
    # rotating refresh family is not silently shared between contexts.
    # Include separate API/authentication origins too, not just the UI domain.
    cookies=sorted((item.get('domain'),item.get('path'),item.get('name'),item.get('value'))
                   for item in storage.get('cookies',[]))
    local=sorted((item['origin'],field['name'],field['value']) for item in storage.get('origins',[])
                 for field in item.get('localStorage',[]) if SECRET.search(field['name']) or 'auth' in field['name'].lower())
    session=sorted((host,key,value) for host,fields in storage.get('session_storage',{}).items() for key,value in fields.items()
                   if SECRET.search(key) or 'auth' in key.lower())
    indexed=sorted((item['origin'],json.dumps(item.get('indexedDB',[]),sort_keys=True)) for item in storage.get('origins',[])
                   if item.get('indexedDB'))
    return signature(json.dumps([cookies,local,session,indexed],sort_keys=True).encode())


def failure(reason, *, pending=False):
    return {'exploration_prepared':False,'verification_mode':'live_empirical','business_failure':False,
            'preparation_pending':pending,'requires_exclusive':not pending,'continue_exploration':True,'reason':reason}
