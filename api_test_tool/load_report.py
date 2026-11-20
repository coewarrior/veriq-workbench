"""Self-contained, accessible charts rendered only from saved load measurements."""
import html
import math
from .report_theme import REPORT_THEME_CSS


def esc(value):
    return html.escape(str(value), quote=True)


def number(value):
    return f'{value:,.2f}'.rstrip('0').rstrip('.') if isinstance(value, (float, int)) else '—'


def chart(title, points, lines, unit, note):
    """SVG paths preserve missing samples as gaps; titles expose exact values."""
    colors = ['#7eb6ff', '#63dec8', '#e9b573']
    measured = [v for p in points for _, key in lines if isinstance((v := p.get(key)), (float, int)) and math.isfinite(v)]
    if not measured:
        return f'<section class="chart"><h2>{esc(title)}</h2><p class="empty">没有对应采样数据</p><p class="hint">{esc(note)}</p></section>'
    xmax = max(1, max(p['second'] for p in points))
    ymax = max(1, max(measured))
    if unit == '%': ymax = 100
    x = lambda s: 58 + 620 * s / xmax
    y = lambda v: 214 - 176 * v / ymax
    svg = []
    for i in range(5):
        value = ymax * i / 4
        svg.append(f'<path class="gridline" d="M58 {y(value):.2f} H678"/><text x="48" y="{y(value)+4:.2f}" text-anchor="end">{number(value)}</text>')
    for i in range(5):
        value = xmax * i / 4
        svg.append(f'<text x="{x(value):.2f}" y="241" text-anchor="middle">{number(value)}s</text>')
    legend = []
    for idx, (label, key) in enumerate(lines):
        color = colors[idx % len(colors)]
        path, pen = [], False
        for p in points:
            value = p.get(key)
            if not isinstance(value, (float, int)) or not math.isfinite(value):
                pen = False
                continue
            path.append(f'{"L" if pen else "M"}{x(p["second"]):.2f},{y(value):.2f}')
            pen = True
            svg.append(f'<circle cx="{x(p["second"]):.2f}" cy="{y(value):.2f}" r="3" fill="{color}"><title>{esc(label)} · {p["second"]}s：{number(value)} {esc(unit)}</title></circle>')
        svg.append(f'<path d="{" ".join(path)}" fill="none" stroke="{color}" stroke-width="2.5"/>')
        legend.append(f'<span><i style="background:{color}"></i>{esc(label)}</span>')
    return f'<section class="chart"><h2>{esc(title)}</h2><div class="legend">{"".join(legend)}</div><svg viewBox="0 0 710 260" role="img" aria-label="{esc(title)}，单位 {esc(unit)}"><title>{esc(title)}</title>{"".join(svg)}</svg><p class="hint">{esc(note)}</p></section>'


def render_load_report(result):
    latency = result['latency_ms']
    current = result.get('series_basis') == 'request_completed'
    basis = '按每个请求完成时点汇总；每个点代表该秒内完成的请求。' if current else '历史数据按整轮链路完成时点汇总，不代表请求实际发生时点。'
    raw = {p['second']: p for p in result.get('series', [])}
    # Zero-fill idle seconds for throughput; no response is not a zero-ms response.
    end = max(max(raw, default=0), math.ceil(result['elapsed_seconds']) - 1)
    points = []
    for second in range(end + 1):
        p = raw.get(second, {})
        count, failed = p.get('requests', 0), p.get('failed', 0)
        window = max(.001, min(1, result['elapsed_seconds'] - second))
        points.append({'second': second, 'requests': count, 'failed': failed,
                       'rps': count / window if current else count, 'threads': p.get('active_threads'),
                       'error_rate': 100 * failed / count if count else None,
                       **{key: p.get('latency_ms', {}).get(key) for key in ('p50', 'p95', 'p99')}})
    charts = chart('吞吐量趋势' if current else '历史请求完成量', points,
                   [('RPS' if current else '请求数 / 秒桶', 'rps')], 'req/s',
                   basis + ('最后不足一秒的桶按实际时长折算 RPS。' if current else ''))
    charts += chart('响应时间趋势', points, [('P50', 'p50'), ('P95', 'p95'), ('P99', 'p99')], 'ms',
                    '分位数按该秒收到响应的请求计算；无响应的秒留空。' if current else '这份历史报告未保存逐秒耗时，无法还原趋势；下方保留整体分位数。')
    charts += chart('未通过比例趋势', points, [('未通过比例', 'error_rate')], '%', basis + '包含断言失败及连接异常；没有请求的秒留空。')
    if result.get('engine') == 'jmeter':
        charts += chart('实际活跃线程', points, [('活跃 JMeter 线程', 'threads')], '个', '取每秒请求采样记录中的活跃线程最大值；没有采样的秒留空，不等同于同时在途请求数。')
    distribution = [('P50', latency.get('p50')), ('P95', latency.get('p95')), ('P99', latency.get('p99')), ('最大值', latency.get('max'))]
    bars = ''.join(f'<div class="bar-row"><span>{esc(k)}</span><div class="bar-track"><div class="bar" style="width:{(v or 0)/max(1,latency.get("max") or 1)*100:.2f}%"></div></div><strong>{number(v)} ms</strong></div>' for k,v in distribution)
    charts += f'<section class="chart"><h2>整体响应时间分布</h2>{bars}<p class="hint">基于 {latency.get("count",0)} 次有响应的请求；P95 表示其中 95% 的响应耗时不超过此值。</p></section>'
    total = max(1, sum(result['status_codes'].values()))
    codes = ''.join(f'<div class="bar-row"><span>{esc(k)}</span><div class="bar-track"><div class="bar" style="width:{v/total*100:.2f}%"></div></div><strong>{v} · {v/total:.1%}</strong></div>' for k,v in sorted(result['status_codes'].items())) or '<p>没有请求记录</p>'
    metrics = [('虚拟用户', result['config']['virtual_users']), ('请求总数', result['requests_sent']),
               ('平均 RPS', result['requests_per_second']), ('未通过比例', f'{result["error_rate"]:.2%}'),
               ('P95 / ms', latency['p95']), ('实际耗时 / 秒', result['elapsed_seconds'])]
    rows = ''.join(f'<tr><td>{p["second"]}–{p["second"]+1}</td><td>{p["requests"]}</td><td>{p["failed"]}</td><td>{number(p["p50"])}</td><td>{number(p["p95"])}</td><td>{number(p["p99"])}</td></tr>' for p in points)
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>压测统计报告</title><style>
body{{font:15px/1.7 system-ui;background:#111827;color:#e5e7eb}}main{{max-width:1400px;margin:24px auto;padding:24px}}h1{{margin:8px 0}}h2{{font-size:19px;margin:0 0 18px}}.metrics{{display:flex;gap:28px;flex-wrap:wrap}}section{{padding:24px;border:1px solid #465069;border-radius:16px;margin:18px 0}}b{{display:block;font-size:28px}}a{{color:#b4cbff}}.charts{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}}.chart{{margin:0;min-width:0}}.chart svg{{width:100%;display:block}}svg text{{fill:#aab9ce;font-size:12px}}.gridline{{stroke:#465069;stroke-opacity:.5}}.legend{{display:flex;gap:20px;font-size:13px}}.legend i{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:7px}}.hint{{font-size:13px;color:#aab9ce}}.empty{{min-height:160px;display:grid;place-items:center;color:#aab9ce}}.bar-row{{display:flex;gap:15px;align-items:center;margin:22px 0;font-size:13px}}.bar-row>span{{min-width:100px}}.bar-row strong{{min-width:105px;text-align:right}}.bar-track{{flex:1;background:#ffffff0c;border-radius:5px;overflow:hidden}}.bar{{height:13px;background:#7eb6ff;border-radius:5px}}table{{width:100%;border-collapse:collapse}}td,th{{padding:8px;text-align:left;border-bottom:1px solid #465069}}.table-wrap{{overflow:auto}}summary{{cursor:pointer}}@media(max-width:850px){{.charts{{grid-template-columns:1fr}}main{{padding:14px}}section{{padding:18px}}}}{REPORT_THEME_CSS}
</style></head><body><main><a href="/api-testing#load">← 返回压测</a><h1>压测统计报告</h1><p>{"执行引擎：Apache JMeter 5.6.3" if result.get("engine")=="jmeter" else "执行引擎：内置链路回放"} · {"引擎异常 / 部分结果" if result.get("engine_status")=="failed" else "已完成采样"}</p><p>{esc(result['environment']['base_url'])} · {esc(result['started_at'])}</p>
<section class="metrics">{''.join(f'<div>{esc(label)}<b>{esc(number(value) if isinstance(value,(int,float)) else (value if value is not None else "—"))}</b></div>' for label,value in metrics)}</section>
<p class="hint">图表来自本次已保存的测量数据，悬停数据点可查看数值。{esc(basis)}</p><div class="charts">{charts}</div>
<section><h2>HTTP 状态码分布</h2>{codes}<p class="hint">HTTP 状态码不等同于断言结果：预期的 4xx 可以通过，200 也可能因业务断言失败而未通过。</p></section>
<section><h2>结束原因与测量口径</h2><p>{esc(result['stop_reason'])}</p><p>{esc(result['measurement'])}</p><p>完成轮次 {result['rounds_finished']}；通过轮次 {result['rounds_passed']}；清理失败 {result['cleanup_failures']}。</p><a href="result.json">完整结果与失败样本 JSON</a> · <a href="bundle.json">用例快照</a></section>
<section><details><summary>查看逐秒数据</summary><div class="table-wrap"><table><thead><tr><th>距开始 / 秒</th><th>请求数</th><th>未通过</th><th>P50 / ms</th><th>P95 / ms</th><th>P99 / ms</th></tr></thead><tbody>{rows}</tbody></table></div></details></section></main></body></html>'''
