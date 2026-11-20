"""Prepare the current workspace frame before asynchronous session loading."""
import re
from html import escape
from pathlib import Path

_LOADING_CSS = (Path(__file__).parent / 'static' / 'workspace-loading.css').read_text(encoding='utf-8')


def prepare_workspace_page(page: str, *, ui: bool, version: str) -> str:
    """Only decorate the response; the saved session and final UI stay unchanged."""
    # This guard must not depend on a second network request to hide the old form.
    page = page.replace('<link rel="stylesheet" href="/static/workspace-loading.css">',
                        '<style>' + _LOADING_CSS + '</style>', 1)
    body_class = 'ui-workspace workspace-loading' if ui else 'workspace-loading'
    page = page.replace('<body>', f'<body class="{body_class}">', 1)
    page = re.sub(r'(<span class="version">).*?(</span>)',
                  lambda m: m[1] + 'v' + escape(version) + m[2], page, count=1)
    page = re.sub(r'(<footer class="page-footer"><span>).*?(</span>)',
                  lambda m: m[1] + '探真 VERIQ · 内网版 ' + escape(version) + m[2], page, count=1)
    page = page.replace('id="current-title">新建测试会话', 'id="current-title">正在加载测试会话', 1)
    page = page.replace('id="model-label">接入你的模型', 'id="model-label">正在读取连接状态', 1)
    page = re.sub(r'(<h1 id="stage-title">).*?(</h1>)',
                  lambda m: m[1] + ('需求与页面测试' if ui else 'API 测试') + m[2], page, count=1)
    page = re.sub(r'(<p id="stage-description">).*?(</p>)',
                  lambda m: m[1] + '正在加载测试会话与进度。' + m[2], page, count=1)
    page = page.replace('id="stage-count">STEP 01 / 04', 'id="stage-count">', 1)
    page = page.replace('<p class="sidebar-hint">导入第一份文档，开始测试。</p>',
                        '<p class="sidebar-hint">正在加载历史会话…</p>', 1)
    if ui:
        page = page.replace('<title>API 测试 · 探真 VERIQ</title>', '<title>需求与页面测试 · 探真 VERIQ</title>', 1)
        page = page.replace('<small>VERIQ · API 测试</small>', '<small>VERIQ · 需求与页面测试</small>', 1)
        page = page.replace('>API TEST WORKSPACE</p>', '>UI TEST WORKSPACE</p>', 1)
        # Keep the hidden original step for existing navigation/setup callers.
        stepper = ('<nav class="stepper" aria-label="测试流程">'
                   '<button data-stage="1" disabled><b>1</b><span>提交资料<small>目标与文档</small></span></button><i></i>'
                   '<button data-stage="2" disabled><b>2</b><span>开始测试<small>进度与待办</small></span></button><i hidden></i>'
                   '<button data-stage="3" hidden disabled><b>3</b><span>执行测试</span></button><i></i>'
                   '<button data-stage="4" disabled><b>3</b><span>查看结果<small>结论与证据</small></span></button></nav>')
        page = re.sub(r'<nav class="stepper".*?</nav>', lambda _: stepper, page, count=1, flags=re.S)
    loading = ('<section id="workspace-loading" class="panel" role="status" aria-live="polite">'
               '<p id="workspace-loading-message">正在加载测试会话…</p>'
               '<p class="hint">若加载失败，可刷新页面重试。</p>'
               '<noscript><p>请启用 JavaScript 后刷新页面。</p></noscript></section>')
    return page.replace('<div id="session-progress">', loading + '<div id="session-progress">', 1)
