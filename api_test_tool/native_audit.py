"""Read-only, deterministic full-cycle reconciliation and delivery report.

Two current reads; no replay, notification, rollout scan or inferred model timing.
"""
from api_test_tool.ui_case_scope import active_cases, is_superseded

def audit_native_cycle(client, binding_file, output_file, ack_file=None, timeline_file=None):
    import html
    import time
    from datetime import timezone
    started = time.monotonic()
    audit_started_at = datetime.now(timezone.utc).isoformat()
    binding_file, output_file = Path(binding_file), Path(output_file)
    root, page_file = binding_file.parent, output_file.with_suffix('.html')
    if (output_file.suffix != '.json' or output_file.resolve() == binding_file.resolve()
            or output_file.exists() or page_file.exists()):
        raise ValueError('核验输出使用新的 JSON/HTML 文件，不能覆盖原绑定或历史证据')
    def read(path):
        return json.loads(read_utf8(path))
    def optional(name):
        path = root / name
        return read(path) if path.exists() else {}
    binding = read(binding_file)
    if binding.get('workspace_url', client.url) != client.url:
        raise ValueError('核验绑定不属于当前测试台')
    ledger = optional('run-ledger.json')
    if ledger and any(ledger.get(k) != binding[k] for k in ('task_id', 'node_id')):
        raise ValueError('计时台账不属于当前任务与节点')
    # Exactly two fresh reads. Missing artifacts stay missing, without polling.
    state = client.call('get_managed_test', {'task_id': binding['task_id']})
    record = client.call('get_ui_test_cases', {'project_id': binding['project_id'],
                                            'execution_id': binding['execution_id']})
    node = next(n for n in state['nodes'] if n['id'] == binding['node_id'])
    cases = active_cases(record.get('cases') or [])
    receiver = optional('native-receiver.json')
    ack = read(ack_file) if ack_file else {}
    event = ack.get('handoff') or {}
    ack_matches = all(event.get(k) == v for k, v in (
        ('id', binding['lease_id']), ('task_id', binding['task_id']), ('node_id', binding['node_id'])))
    checks = {
        'node_terminal': node.get('state') in {'completed', 'blocked', 'stopped'},
        'no_active_lease': not any(l['node_id'] == binding['node_id'] for l in state.get('leases', [])),
        'receiver_stopped': receiver.get('state') == 'stopped' and not (root / 'native-observations.fifo').exists(),
        'ack_received': ack_matches and ack.get('handoff_complete') is True and event.get('delivery_state') == 'received',
        'passed_state_consistent': (node.get('result') == 'passed') == (bool(cases) and all(c.get('status') == 'passed' for c in cases)),
    }
    stages, errors, warnings, unknown, publications, intervals = [], [], [], [], [], []
    def instant(value):
        if not isinstance(value, str):
            raise ValueError('missing timestamp')
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None:
            raise ValueError('timestamp has no timezone')
        return result
    def stage(name, start, end, scope, top=None, details=None):
        try:
            a, b = instant(start), instant(end)
            if b < a:
                raise ValueError('negative interval')
        except (TypeError, ValueError):
            unknown.append({'stage': name, 'reason': '缺少有效起止时间', 'scope': scope})
            return
        item = {'stage': name, 'started_at': start, 'finished_at': end,
                'seconds': round((b - a).total_seconds(), 6), 'scope': scope}
        if details:
            for key in ('server_processing_timing', 'client_wait', 'case_id'):
                if key in details:
                    item[key] = details[key]
        stages.append(item)
        if top:
            intervals.append((a, b, top))
    def diagnostics(value, source):
        # Retain dynamic warnings at their original path; do not assume a fixed
        # success schema or expose unrelated context/account fields.
        if isinstance(value, dict):
            for key, child in value.items():
                path = source + '.' + key
                if key in {'warning', 'warnings'} and child:
                    warnings.append({'source': path, 'value': child})
                elif key in {'error', 'handoff_error', 'cleanup_error', 'close_error', 'recovery_error'} and child:
                    errors.append({'source': path, 'error': child})
                elif key in {'delivery_state', 'observed_delivery_state', 'operation_state'} and child in {'unknown', 'sending'}:
                    unknown.append({'source': path, 'reason': child})
                elif key == 'save_unconfirmed' and child is True:
                    unknown.append({'source': path, 'reason': '保存未确认'})
                elif isinstance(child, (dict, list)):
                    diagnostics(child, path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                diagnostics(child, source + '[' + str(index) + ']')
    for item in ledger.get('stages', []):
        stage(item['stage'], item.get('started_at'), item.get('finished_at'),
              'coordinator', item['stage'])
    environment = optional('browser-environment.json')
    if environment:
        if any(environment.get('identity', {}).get(k) != binding.get(k)
               for k in ('task_id', 'node_id', 'holder_id', 'executor_ref')):
            raise ValueError('浏览器环境计时不属于原执行者')
        stage('isolated_environment_create', environment.get('started_at'), environment.get('ready_at'),
              'browser_environment', '独立浏览器创建')
        stage('isolated_environment_close', environment.get('close_started_at'), environment.get('closed_at'),
              'browser_environment')
    cycles = []
    for path in sorted(root.glob('cycle-*.json')):
        cycle = read(path)
        cycles.append(cycle)
        diagnostics(cycle, path.name)
        label = {'prepare': '准备与接收器就绪', 'closeout': '交还、发布与通知', 'record': '结果保存',
                 'release': '交还与接续通知', 'review': '结果回查保存', 'complete': '报告补存与最终交付'}.get(cycle.get('action'))
        valid = []
        for item in cycle.get('stages', []):
            stage(item['stage'], item.get('started_at'), item.get('finished_at'), 'tool')
            try:
                a, b = instant(item.get('started_at')), instant(item.get('finished_at'))
                if b >= a:
                    valid.append((a, b))
            except (TypeError, ValueError):
                pass
        if label and valid:
            intervals.append((min(x[0] for x in valid), max(x[1] for x in valid), label))
        result = cycle.get('result') or {}
        for item in result.get('handoff_timing', []):
            stage(item['stage'], item.get('started_at'), item.get('finished_at'), 'handoff_detail', details=item)
        if result.get('publication'):
            published = result['publication']
            publications.append(published.get('publication', published))
    # This receipt is written before notification. A fast coordinator need not
    # wait for the worker's final cycle log merely to verify actual publication.
    closeout = optional('closeout-result.json')
    diagnostics(closeout, 'closeout-result.json')
    if closeout.get('publication'):
        publications.append(closeout['publication'])
    after_handoff = optional('handoff-publication-result.json')
    diagnostics(after_handoff, 'handoff-publication-result.json')
    if after_handoff.get('publication'):
        publications.append(after_handoff['publication'])
    # Report-only completion has its own receipt, persisted before coordinator
    # notification. Do not mistake the earlier release for the final publication.
    final = optional('publication-result.json')
    if final:
        identity = final.get('binding') or {}
        if any(identity.get(key) != binding.get(key) for key in ('holder_id', 'task_id', 'node_id', 'lease_id')):
            raise ValueError('最终发布回执不属于原执行绑定')
        values = identity.get('arguments') or {}
        if any(values.get(key) != binding.get(key) for key in ('project_id', 'execution_id', 'revision')):
            raise ValueError('最终发布回执与当前已保存修订不一致')
        diagnostics(final.get('result'), 'publication-result.json')
        if (final.get('result') or {}).get('publication'):
            publications.append(final['result']['publication'])
    for item in closeout.get('handoff_timing', []):
        stage(item['stage'], item.get('started_at'), item.get('finished_at'), 'handoff_detail',
              '交还、发布与通知' if not any(c.get('action') == 'closeout' for c in cycles) else None, details=item)
    native_paths = sorted(root.glob('native-call-timing*.json'))
    native_case_ids = set()
    for path in native_paths:
        native = read(path)
        stage('native_call', native.get('started_at'), native.get('finished_at'), 'native',
              '原生开页、完整检查、关页与保存', details=native)
        diagnostics(native, path.name)
        if native.get('case_id'):
            native_case_ids.add(native['case_id'])
    if not native_paths:
        unknown.append({'stage': 'native_call', 'reason': '缺少原生调用起止记录'})
    observations, observations_full = [], []
    for path in sorted(root.glob('observation-inbox-*.json')):
        observation = read(path)
        observations_full.append(observation)
        diagnostics(observation, path.name)
        timing = observation.get('timing') or {}
        observations.append({'case_id': observation.get('case_id'), 'status': observation.get('status'),
            'checks': len(observation.get('checks', [])),
            'passed_checks': sum(c.get('ok') is True for c in observation.get('checks', [])),
            'evidence_file': str(path)})
        stage('business', timing.get('started_at'), timing.get('last_assertion_at'), 'observation')
        stage('browser_close', timing.get('last_assertion_at'), timing.get('browser_closed_at'), 'observation')
    if native_case_ids:
        for case_id in sorted({o.get('case_id') for o in observations if o.get('case_id')} - native_case_ids):
            unknown.append({'stage': 'native_call', 'case_id': case_id, 'reason': '此用例缺少原生调用计时记录'})
    saved = optional('native-receiver-response.json')
    diagnostics(saved, 'native-receiver-response.json')
    timing = saved.get('timing') or {}
    stage('save', timing.get('save_started_at'), timing.get('save_finished_at'), 'observation')
    if timeline_file:
        for item in read(timeline_file):
            stage(item['stage'], item.get('started_at'), item.get('finished_at'), 'outer_tool')
    diagnostics(ack, 'ack')
    diagnostics(node, 'current_node')
    diagnostics(record, 'current_cases')
    for item in ack.get('handoff_timing', []):
        stage(item['stage'], item.get('started_at'), item.get('finished_at'), 'handoff_detail',
              '协调确认' if item['stage'] == 'coordinator_ack' and ack_matches else None, details=item)
    checks['report_published'] = bool(publications) and publications[-1].get('phase') == 'published'
    checks['save_confirmed'] = saved.get('saved') is True
    if not any(s.get('stage') in {'release_handoff', 'release_publish_handoff'}
               for c in cycles for s in c.get('stages', [])):
        unknown.append({'stage': 'closeout', 'reason': '完整交还调用日志尚未取得；已保存初始交还回执不等于全部发送回执完成'})
    start = None
    try:
        start = instant(ledger.get('started_at'))
    except (TypeError, ValueError):
        unknown.append({'stage': 'total', 'reason': '缺少本轮明确起点，总耗时未知'})
    case_statuses = {c['case_id']: c['status'] for c in cases}
    failed_cases = [key for key, status in case_statuses.items() if status != 'passed']
    failed_assertions = [{'case_id': o.get('case_id'), **c} for o in observations_full
                         for c in o.get('checks', []) if c.get('ok') is not True]
    remaining = [k for k, v in checks.items() if not v]
    def aggregate_timing(report_ready_at):
        finish = instant(report_ready_at)
        # Refresh only this audit's measured phase when the completed report
        # write is included in the final endpoint below.
        stages[:] = [s for s in stages if s['scope'] != 'audit']
        intervals[:] = [item for item in intervals if item[2] != '当前状态核验与报告整理']
        stage('audit_report', audit_started_at, report_ready_at, 'audit', '当前状态核验与报告整理')
        total, timeline = None, []
        if start is not None and start <= finish:
            total = round((finish - start).total_seconds(), 6)
            # Partition nested and parallel intervals. Every measured second
            # between the explicit start and report boundary appears once.
            boundaries = sorted({start, finish, *(max(start, min(finish, t)) for a, b, _ in intervals for t in (a, b))})
            for a, b in zip(boundaries, boundaries[1:]):
                if b <= a:
                    continue
                active = sorted({label for x, y, label in intervals if x < b and y > a})
                name = '、'.join(active) + ('（并行）' if len(active) > 1 else '') if active else '未归属间隔（含调用等待）'
                if timeline and timeline[-1]['stage'] == name:
                    timeline[-1]['finished_at'] = b.isoformat()
                    timeline[-1]['seconds'] = round((b - instant(timeline[-1]['started_at'])).total_seconds(), 6)
                else:
                    timeline.append({'stage': name, 'started_at': a.isoformat(), 'finished_at': b.isoformat(),
                                     'seconds': round((b - a).total_seconds(), 6), 'scope': 'whole_cycle',
                                     'attribution': 'measured' if active else 'unattributed'})
        elif start is not None and not any(item.get('reason') == '起点晚于报告时间，不能计算总耗时' for item in unknown):
            unknown.append({'stage': 'total', 'reason': '起点晚于报告时间，不能计算总耗时'})
        return total, timeline, round(sum(s['seconds'] for s in timeline if s['attribution'] == 'unattributed'), 6)
    report_ready_at = datetime.now(timezone.utc).isoformat()
    total, timeline, unassigned = aggregate_timing(report_ready_at)
    publication = publications[-1] if publications else None
    summary = {'started_at': ledger.get('started_at'), 'start_basis': ledger.get('start_basis', '未知'),
        'report_ready_at': report_ready_at, 'total_to_report_seconds': total,
        'case_count': len(cases), 'passed_cases': sum(s == 'passed' for s in case_statuses.values()),
        'check_count': sum(o['checks'] for o in observations), 'passed_checks': sum(o['passed_checks'] for o in observations),
        'case_statuses': case_statuses, 'failed_cases': failed_cases, 'failed_assertions': failed_assertions,
        'lifecycle_checks': checks, 'remaining': remaining, 'errors': errors, 'warnings': warnings,
        'unknown': unknown, 'unattributed_seconds': unassigned, 'timeline': timeline,
        'report_file': str(page_file), 'report_url': page_file.resolve().as_uri(),
        'data_file': str(output_file), 'publication': publication,
        'delivery_basis': '终点在报告正文首次写入完成后采样，随后只更新最终计时元数据；不包含聊天消息组织与发送。未归属间隔不等同于纯模型时间。'}
    result = {'task_id': binding['task_id'], 'node_id': binding['node_id'],
        'project_id': binding['project_id'], 'execution_id': binding['execution_id'],
        'node_result': node.get('result'), 'case_statuses': case_statuses,
        'checks': checks, 'observations': observations, 'stages': stages, 'errors': errors,
        'warnings': warnings, 'unknown': unknown, 'publication': publication, 'remaining': remaining,
        'summary': summary, 'timeline': timeline, 'report_ready_at': report_ready_at,
        'total_to_report_seconds': total, 'audit_seconds': round(time.monotonic() - started, 6),
        'timing_basis': '顶层时间轴覆盖明确起点到报告生成，重叠时间只计一次；细分与嵌套时间不可相加。缺失记录保持未知，不补零。'}
    def table(items):
        rows = ''.join('<tr>' + ''.join('<td>' + html.escape(str(x)) + '</td>' for x in
            (s['stage'], s['started_at'], s['finished_at'], s['seconds'])) + '</tr>' for s in items)
        return '<table><tr><th>阶段</th><th>开始（含时区）</th><th>结束</th><th>秒</th></tr>' + rows + '</table>'
    def details(value):
        return '<pre>' + html.escape(json.dumps(value, ensure_ascii=False, indent=2)) + '</pre>'
    def render_page():
        return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>原生完整链路交付核验</title>'
        '<style>body{font:16px system-ui;max-width:1300px;margin:40px auto;padding:20px;color:#172033}'
        'td,th{padding:10px;border-bottom:1px solid #ddd;text-align:left;vertical-align:top}table{width:100%;border-collapse:collapse}'
        'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f9;padding:16px}h2{margin-top:32px}</style>'
        '<h1>完整链路实际耗时与交付结果</h1><p>从 ' + html.escape(str(summary['started_at'] or '未知起点'))
        + ' 到 ' + html.escape(report_ready_at) + '，总耗时 <strong>' + (str(total) + ' 秒' if total is not None else '未知')
        + '</strong>。</p><p>' + html.escape(summary['start_basis']) + '；' + html.escape(summary['delivery_basis'])
        + '</p><p>独立用例 ' + str(summary['passed_cases']) + '/' + str(summary['case_count'])
        + ' 通过；实际检查 ' + str(summary['passed_checks']) + '/' + str(summary['check_count'])
        + ' 通过。生命周期核对通过不代替业务判定。</p><h2>完整顶层时间轴</h2><p>'
        + html.escape(result['timing_basis']) + '</p>' + table(timeline)
        + '<h2>失败、告警、未知与剩余问题</h2>' + details({k: summary[k] for k in
            ('failed_cases', 'failed_assertions', 'remaining', 'errors', 'warnings', 'unknown', 'unattributed_seconds')})
        + '<h2>当前结果与交还确认</h2>' + details({'case_statuses': case_statuses, 'lifecycle_checks': checks, 'publication': publication})
        + '<h2>原始阶段细分（不可累加到总耗时）</h2>' + table(stages)
        + '<h2>平台处理与客户端等待实测</h2>' + details([s for s in stages if
            'server_processing_timing' in s or 'client_wait' in s])
        + '<h2>独立观察证据</h2>' + details(observations) + '</html>')
    page_file.write_text(render_page(), encoding='utf-8')
    page_file.chmod(0o600)
    # Sample after the actual complete HTML exists. Only final timing metadata
    # is refreshed afterwards; this is not a claim of chat-message delivery.
    report_ready_at = datetime.now(timezone.utc).isoformat()
    total, timeline, unassigned = aggregate_timing(report_ready_at)
    summary.update(report_ready_at=report_ready_at, total_to_report_seconds=total,
                   timeline=timeline, unattributed_seconds=unassigned)
    result.update(report_ready_at=report_ready_at, total_to_report_seconds=total,
                  timeline=timeline, audit_seconds=round(time.monotonic() - started, 6))
    page_file.write_text(render_page(), encoding='utf-8')
    write_private_json(output_file, result)
    return {'report_file': str(page_file), 'data_file': str(output_file), 'checks': checks,
            'remaining': remaining, 'audit_seconds': result['audit_seconds'], 'summary': summary,
            'report_ready_at': report_ready_at, 'total_to_report_seconds': total}
