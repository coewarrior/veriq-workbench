import copy
from api_test_tool.load_report import render_load_report


def result():
    return {'config':{'virtual_users':20},'environment':{'base_url':'http://example.test/<script>alert(1)</script>'},
            'started_at':'2026-09-14', 'requests_sent':4,'requests_per_second':1.6,'error_rate':.25,
            'elapsed_seconds':2.5,'rounds_finished':1,'rounds_passed':0,'cleanup_failures':0,
            'stop_reason':'达到设定时长','measurement':'测试数据','status_codes':{'200':3,'NETWORK_ERROR':1},
            'latency_ms':{'count':3,'p50':10,'p95':90,'p99':90,'max':90},
            'series_basis':'request_completed',
            'series':[{'second':0,'requests':3,'failed':1,'latency_ms':{'p50':10,'p95':90,'p99':90}},
                      {'second':2,'requests':1,'failed':0,'latency_ms':{'p50':20,'p95':20,'p99':20}}]}


def test_charts_escape_values_keep_gaps_and_show_partial_bucket_rate():
    data=result();before=copy.deepcopy(data);page=render_load_report(data)
    assert data==before
    assert '<script>alert' not in page and '&lt;script&gt;' in page
    assert 'RPS · 2s：2 req/s' in page  # one request / final 0.5 sec
    assert 'RPS · 1s：0 req/s' in page
    assert 'P50 · 1s' not in page  # idle bucket is not zero latency
    assert '未通过比例 · 1s' not in page
    assert '未通过比例 · 0s：33.33 %' in page
    assert 'role="img"' in page and '查看逐秒数据' in page


def test_old_report_does_not_invent_latency_or_request_timestamps():
    data=result();data.pop('series_basis')
    for point in data['series']:point.pop('latency_ms')
    page=render_load_report(data)
    assert '历史请求完成量' in page and '历史数据按整轮链路完成时点汇总' in page
    assert '未保存逐秒耗时，无法还原趋势' in page
    assert 'P50 ·' not in page and '整体响应时间分布' in page


def test_empty_run_has_no_fake_response_statistics():
    data=result();data.update(series=[],status_codes={},requests_sent=0,error_rate=0)
    data['latency_ms']={'count':0,'p50':None,'p95':None,'p99':None,'max':None}
    page=render_load_report(data)
    assert '没有对应采样数据' in page and '没有请求记录' in page
    assert 'None' not in page
