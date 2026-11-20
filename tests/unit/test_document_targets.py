import pytest
from api_test_tool.document_targets import document_targets, normalize_base_url


def test_servers_defaults_and_multiple_candidates():
    result = document_targets('''openapi: 3.0.3
servers:
- url: https://{host}/v1/
  description: 测试环境
  variables:
    host:
      default: api.example.com
- url: https://staging.example.com/v2
- url: /relative
- url: https://{unknown}/api
''', 'openapi.yaml')
    assert [c['url'] for c in result['candidates']] == ['https://api.example.com/v1', 'https://staging.example.com/v2']
    assert result['notes']


def test_markdown_only_uses_labelled_addresses():
    doc = '参考 https://docs.example.com\nAPI Key 申请：https://model.example.com\n**Base URL**: `https://api.example.com/v1`'
    assert document_targets(doc, 'doc.md')['candidates'][0]['url'] == 'https://api.example.com/v1'
    assert document_targets('文档 https://docs.example.com', 'doc.md')['candidates'] == []


@pytest.mark.parametrize('url', ['https://user:secret@example.com', 'https://api.example.com?token=secret', 'https://api.example.com/#x', '/v1', 'https://api.example.com/%2e%2e/admin', 'https://api.example.com:99999'])
def test_invalid_targets_are_not_accepted(url):
    with pytest.raises(ValueError):
        normalize_base_url(url)
