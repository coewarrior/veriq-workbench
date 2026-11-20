"""Targeted offline checks for literal analysis-section URL rendering."""
from copy import deepcopy
from html.parser import HTMLParser
import json

import pytest

from api_test_tool.task_reports import _section_content_html, render_saved_task_report


class Content(HTMLParser):
    def __init__(self, markup):
        super().__init__(convert_charrefs=True)
        self.text = ''
        self.links = []
        self.tags = []
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == 'a':
            self.links.append(dict(attrs))

    def handle_data(self, text):
        self.text += text


def test_section_links_preserve_internal_urls_query_fragments_and_literal_text():
    urls = ['http://192.0.2.20:18089/api/projects/p/reports/r/index.html',
            'https://git.example.test/team/project/-/merge_requests/263?view=diff&file=a%20b#L12',
            'HTTP://[::1]:18089/report', 'https://example.test/中文']
    text = '报告：' + urls[0] + '\n\nMR：' + urls[1] + '\n' + '\n'.join(urls[2:])
    parsed = Content(_section_content_html(text))
    assert parsed.text == text
    assert [link['href'] for link in parsed.links] == urls
    assert all(link['target'] == '_blank' and link['rel'] == 'noopener noreferrer' for link in parsed.links)


@pytest.mark.parametrize(('text', 'expected'), [
    ('见（https://example.test/a）。下一行\nhttp://example.test/b，完成。',
     ['https://example.test/a', 'http://example.test/b']),
    ('[参考](https://example.test/wiki/Topic_(one)). 保留 **原文字**',
     ['https://example.test/wiki/Topic_(one)']),
    ('https://example.test/x?a=[one]); https://example.test/two!',
     ['https://example.test/x?a=[one]', 'https://example.test/two']),
])
def test_punctuation_and_markdown_remain_literal(text, expected):
    parsed = Content(_section_content_html(text))
    assert parsed.text == text
    assert [link['href'] for link in parsed.links] == expected
    assert set(parsed.tags) <= {'a'}


@pytest.mark.parametrize('text', [
    'javascript:alert(1) data:text/html,evil file:///tmp/evidence /relative/path //example.test/x',
    'javascript:https://example.test/x',
    'https://user:secret@example.test/x', 'https://@example.test/x',
    'https://user@example.test/x', 'https://user%3Asecret@example.test/x',
    'http://', 'http:///path', 'https://[invalid/x',
    'https://example.test:invalid/x', 'https://example.test:65536/x',
    'https://example.test:0/x', 'https://example.test\\@evil.test/x',
    'https://example.test/a\x00b', 'https://example.test/a\x7fb',
    'https://host%00.test/x',
])
def test_unsupported_malformed_or_credential_urls_stay_plain_text(text):
    parsed = Content(_section_content_html(text))
    assert parsed.text == text
    assert parsed.links == []


def test_html_and_attribute_payloads_never_become_markup():
    text = '<script>alert(1)</script> <img src=x onerror="boom"> & "quote"\nhttps://example.test/?a=1&b=2" onclick="boom'
    parsed = Content(_section_content_html(text))
    assert parsed.text == text
    assert parsed.tags == ['a']
    assert parsed.links == [{'href': 'https://example.test/?a=1&b=2',
                             'target': '_blank', 'rel': 'noopener noreferrer'}]


def test_saved_report_render_only_links_section_content_and_preserves_snapshot(tmp_path):
    url = 'https://example.test/evidence'
    report = {'title': url, 'summary': url, 'goal': url, 'sections': [{'title': url, 'content': url + '\n未执行'}],
              'findings': [], 'runs': [], 'requests_sent': 0, 'created_at': '2026-10-11T00:00:00+00:00',
              'document': {'filename': 'api.md', 'sha256': 'a' * 64},
              'untouched_results': [{'status': 'not_run', 'actual': ''}]}
    original = deepcopy(report)
    path = tmp_path / 'report.json'
    frozen = json.dumps(report, ensure_ascii=False).encode()
    path.write_bytes(frozen)
    class NoStorageAccess:
        def __getattr__(self, name):
            raise AssertionError('Rendering must not access storage: ' + name)
    page = render_saved_task_report(NoStorageAccess(), 'owner', {}, report)
    parsed = Content(page)
    assert len([link for link in parsed.links if link['href'] == url]) == 1
    assert report == original
    assert path.read_bytes() == frozen
    assert '<h2>' + url + '</h2>' in page
    assert '<div class="prose">' + url + '</div>' in page
