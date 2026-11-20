"""Optional bounded virtual-user runs using the existing reviewed case engine."""
from __future__ import annotations

import json
import math
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from .execution import Redactor, run_bundle
from .load_report import render_load_report


def load_config(data):
    if not isinstance(data, dict) or data.get('enabled') is not True:
        raise ValueError('压测默认关闭，请主动开启后再执行')
    result = {}
    for key, default, low, high in [('virtual_users', 5, 1, 20), ('duration_seconds', 30, 1, 300),
                                   ('think_time_ms', 200, 0, 60000), ('max_rounds', 1000, 1, 10000)]:
        value = data.get(key, default)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f'{key} 须为 {low}～{high} 的整数')
        result[key] = value
    return result


def run_load(bundle, environment, output_dir, config, *, case_ids, session_factory, cleanup_callback=None,
             progress=lambda _: None, stop=None):
    stop = stop or threading.Event()
    chosen = [c for c in bundle['cases'] if c['id'] in case_ids]
    if not chosen or len(chosen) != len(set(case_ids)) or any(c.get('state') != 'READY' for c in chosen):
        raise ValueError('压测只能选择已核对且可执行的用例')
    cost = sum(len(c.get('steps', [])) + len(c.get('cleanup_steps', [])) for c in chosen)
    if not 0 < cost <= 50000:
        raise ValueError('选中链路的请求数量超出本机单次压测容量')
    budget = min(config['max_rounds'], 50000 // cost)
    output_dir.mkdir(parents=True, exist_ok=True)
    env = {**environment, 'case_workers': 1, 'stop_on_network_error': True, 'stop_on_cleanup_failure': True}
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic();deadline = started + config['duration_seconds']
    guard = threading.Lock();stats = {'rounds_started': 0, 'rounds_finished': 0, 'rounds_passed': 0,
        'requests_sent': 0, 'requests_failed': 0, 'cleanup_failures': 0, 'status_codes': {}, 'stop_reason': ''}
    latencies, samples, series = [], [], {}

    def observe_request(sample):
        # Collect at each request completion, not when its entire chain finishes.
        # Only measurements enter this callback; no headers, URLs or credentials.
        with guard:
            second = max(0, int(sample['completed_at'] - started))
            point = series.setdefault(second, {'second': second, 'requests': 0, 'failed': 0, '_latencies': []})
            point['requests'] += 1
            point['failed'] += int(sample['failed'])
            stats['requests_failed'] += int(sample['failed'])
            code = str(sample['status_code'] or 'NETWORK_ERROR')
            stats['status_codes'][code] = stats['status_codes'].get(code, 0) + 1
            latency = sample['elapsed_ms']
            if isinstance(latency, (int, float)) and math.isfinite(latency):
                latencies.append(latency)
                point['_latencies'].append(latency)

    def worker():
        while not stop.is_set():
            with guard:
                if time.monotonic() >= deadline or stats['rounds_started'] >= budget:
                    return
                stats['rounds_started'] += 1
            with tempfile.TemporaryDirectory(prefix='api-load-') as tmp:
                result = run_bundle(bundle, env, Path(tmp), case_ids=case_ids,
                                    session_factory=session_factory, cleanup_callback=cleanup_callback,
                                    request_observer=observe_request)
            with guard:
                stats['rounds_finished'] += 1;stats['requests_sent'] += result['requests_sent']
                passed = result['summary']['complete'] and result['summary']['PASS'] == len(chosen)
                if passed:stats['rounds_passed'] += 1
                cleanup_failed = result['cleanup'].get('status') == 'FAIL' or any(c.get('cleanup', {}).get('status') == 'FAIL' for c in result['cases'])
                stats['cleanup_failures'] += int(cleanup_failed)
                if not passed and len(samples) < 5:samples.append(result)
                if cleanup_failed or result['summary']['BROKEN']:
                    stats['stop_reason'] = '发生清理失败或连接异常，停止新增轮次；在途链路完成清理'
                    stop.set()
                progress(f"压测中：{stats['rounds_finished']} 轮，{stats['requests_sent']} 次请求，{stats['requests_failed']} 次未通过；{config['virtual_users']} 个虚拟用户")
            stop.wait(min(config['think_time_ms'] / 1000, max(0, deadline - time.monotonic())))
    with ThreadPoolExecutor(max_workers=config['virtual_users'], thread_name_prefix='api-load') as pool:
        futures = [pool.submit(worker) for _ in range(config['virtual_users'])]
        try:
            for future in futures:future.result()
        except Exception:
            stop.set()
            raise
    elapsed = time.monotonic() - started
    if not stats['stop_reason']:
        stats['stop_reason'] = '用户停止' if stop.is_set() else '达到轮次数或本机请求预算上限' if stats['rounds_started'] >= budget else '达到设定时长'
    ordered = sorted(latencies)
    def percentile(p):return ordered[max(0, math.ceil(p * len(ordered)) - 1)] if ordered else None
    for point in series.values():
        values = sorted(point.pop('_latencies'))
        point['latency_ms'] = {name: values[max(0, math.ceil(p * len(values)) - 1)] if values else None
                               for name, p in [('p50', .5), ('p95', .95), ('p99', .99)]}
        point['latency_ms']['count'] = len(values)
    result = {'kind': 'load', 'started_at': started_at, 'finished_at': datetime.now(timezone.utc).isoformat(),
        'environment': {k: environment[k] for k in ('name', 'base_url')}, 'config': config, 'case_ids': case_ids,
        **stats, 'elapsed_seconds': round(elapsed, 3), 'requests_per_second': round(stats['requests_sent'] / elapsed, 3),
        'error_rate': stats['requests_failed'] / stats['requests_sent'] if stats['requests_sent'] else 0,
        'latency_ms': {'count': len(ordered), 'p50': percentile(.5), 'p95': percentile(.95), 'p99': percentile(.99),
                       'max': max(ordered) if ordered else None}, 'series': sorted(series.values(), key=lambda p:p['second']),
        'series_basis': 'request_completed', 'failure_samples': samples,
        'measurement': '复用已核对用例；请求包括前置、业务与HTTP清理。RPS为总请求/实际任务耗时，非指定发压速率；响应耗时分位数只含收到响应的请求。到时停止新轮次，在途链路与清理结束后出报告。失败包括断言失败和连接异常。该单机结果不是服务极限容量。'}
    redactor = Redactor()
    result = redactor.snapshot(result)
    (output_dir/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    (output_dir/'bundle.json').write_text(json.dumps(redactor.snapshot(bundle), ensure_ascii=False, indent=2))
    (output_dir/'index.html').write_text(render_load_report(result))
    return result
