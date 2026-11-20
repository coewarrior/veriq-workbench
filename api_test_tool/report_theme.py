"""Embed the shared report palette so downloaded reports remain self-contained."""
from html import escape, unescape
from pathlib import Path
import re

REPORT_THEME_CSS = (Path(__file__).parent / 'static' / 'report-theme.css').read_text(encoding='utf-8')

# Inline the glass layer as well, keeping exported reports usable offline.
REPORT_THEME_CSS += '\n' + (Path(__file__).parent / 'static' / 'shared-glass.css').read_text(encoding='utf-8')

# Preserve button feedback in offline reports too.
REPORT_THEME_CSS += '\n' + (Path(__file__).parent / 'static' / 'controls.css').read_text(encoding='utf-8')

_STATIC = Path(__file__).parent / 'static'
_FIRST_PAINT_CSS = (_STATIC / 'report-first-paint.css').read_text(encoding='utf-8')
_FIRST_PAINT_JS = (_STATIC / 'report-first-paint.js').read_text(encoding='utf-8')


def prepare_online_report(page: str, review_data: dict | None = None) -> str:
    """Prepare only the served HTML; frozen reports and their data stay intact."""
    body = re.search(r'<body\b[^>]*>', page, re.I)
    head_end = re.search(r'</head\s*>', page, re.I)
    if not body or not head_end:
        return page

    # Styles appended alongside live controls must block the first body paint.
    styles = []

    def move_style(match):
        styles.append(match[0])
        return ''

    content = re.sub(r'<link\b(?=[^>]*\brel=["\']stylesheet["\'])[^>]*>'
                     r'|<style\b[^>]*>\s*@import\b[^<]*</style\s*>',
                     move_style, page[body.end():], flags=re.I)
    page = page[:body.end()] + content
    page = page[:head_end.start()] + ''.join(styles) + page[head_end.start():]
    if review_data is None or 'id="rr-first-paint"' in page:
        return page

    title_match = re.search(r'<title\b[^>]*>(.*?)</title\s*>', page, re.S | re.I)
    title = unescape(title_match[1]) if title_match else '测试报告'
    header = re.search(r'<header\b[^>]*>.*?</header\s*>', page, re.S | re.I)
    back_match = re.search(r'href=["\'](/(?:ui|api)-testing)["\']', header[0] if header else '')
    back = back_match[1] if back_match else '/api-testing'
    report_type = '总报告' if review_data.get('reportType') == 'total' else '阶段报告' if review_data.get('totalReport') else '测试报告'
    source = ('汇总同项目各会话，审核结果保存到原始记录' if review_data.get('aggregate') else
              '用例与数据保存在本会话' if review_data.get('uiExecution') else
              '来源文件：' + str(review_data['source']) if review_data.get('source') else
              'UI 测试报告' if back == '/ui-testing' else 'API 测试报告')
    first_paint = (
        '<div id="rr-first-paint" class="rr-shell" aria-busy="true">'
        f'<div class="rr-top"><a class="rr-back" href="{back}">← 返回测试台</a>'
        f'<span class="rr-separator">/</span><span>{report_type}</span></div>'
        '<div class="rr-heading"><div><p class="rr-eyebrow">TEST REPORT</p>'
        f'<h1>{escape(title)}</h1><p class="rr-source">{escape(source)}</p></div></div>'
        '<p id="rr-first-paint-status" role="status">正在载入报告内容；也可展开下方报告正文。</p>'
        '<noscript><p>浏览器未启用 JavaScript，可展开下方报告正文查看结果与证据。</p></noscript>'
        '<div class="rr-review rr-first-paint-panels" aria-hidden="true">'
        '<div class="rr-inbox"><div class="rr-inbox-tools">'
        + ('缺陷与回归' if review_data.get('uiExecution') else '缺陷审核')
        + '</div></div><div class="rr-review-side"><div class="rr-editor-heading">缺陷详情</div></div></div></div>'
        '<details id="rr-first-paint-fallback"><summary>展开报告正文</summary>'
        '<p>以下为本次报告正文。交互视图载入后将自动显示。</p></details>'
    )

    def prepare_body(match):
        tag = match[0]
        if re.search(r'\bid=["\']', tag, re.I):
            tag = re.sub(r'\bid=(["\']).*?\1', 'id="report-review-page"', tag, count=1, flags=re.I)
        else:
            tag = tag[:-1] + ' id="report-review-page">'
        if re.search(r'\bclass=["\']', tag, re.I):
            tag = re.sub(r'\bclass=(["\'])(.*?)\1', lambda value: f'class={value[1]}{value[2]} rr-pending{value[1]}', tag, count=1, flags=re.I)
        else:
            tag = tag[:-1] + ' class="rr-pending">'
        return tag + first_paint

    page = re.sub(r'<body\b[^>]*>', prepare_body, page, count=1, flags=re.I)
    # Inline the tiny guard so its failure still leaves a native disclosure.
    guard = '<style>' + _FIRST_PAINT_CSS + '</style><script>' + _FIRST_PAINT_JS + '</script>'
    head = re.search(r'<head\b[^>]*>', page, re.I)
    if not head:
        return page
    charset = re.search(r'<meta\b[^>]*\bcharset=[^>]*>', page[head.end():head_end.start()], re.I)
    offset = head.end() + charset.end() if charset else head.end()
    return page[:offset] + guard + page[offset:]
