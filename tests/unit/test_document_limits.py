"""Document uploads must pass the transport, validation and storage limits together."""
import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from api_test_tool.document_limits import MAX_DOCUMENT_BYTES
from api_test_tool.web import create_app
from api_test_tool.web_security import check_document


def test_full_size_document_roundtrip(tmp_path):
    content = '# Upload boundary\n' + 'a' * (MAX_DOCUMENT_BYTES - len('# Upload boundary\n'))
    expected = hashlib.sha256(content.encode()).hexdigest()
    with TestClient(create_app(tmp_path, start_fixture=False, testing=True)) as c:
        boot = c.get('/api/bootstrap').json()
        assert boot['max_document_bytes'] == 50_000_000
        c.headers['x-csrf-token'] = boot['csrf']
        result = c.post('/api/projects', json={'filename': 'large.md', 'content': content})
        assert result.status_code == 200, result.text[:300]
        pid = result.json()['project']['id']
        response = c.get(f'/api/projects/{pid}/artifacts/document')
        assert response.status_code == 200
        assert len(response.content) == MAX_DOCUMENT_BYTES
        assert hashlib.sha256(response.content).hexdigest() == expected


def test_utf8_limit_and_no_saved_oversize_project(tmp_path):
    content = '中' * (MAX_DOCUMENT_BYTES // 3 + 1)
    with pytest.raises(ValueError, match='50 MB'):
        check_document(content, 'large.md')
    with TestClient(create_app(tmp_path, start_fixture=False, testing=True)) as c:
        c.headers['x-csrf-token'] = c.get('/api/bootstrap').json()['csrf']
        response = c.post('/api/projects', json={'filename':'large.md','content':content})
        assert response.status_code == 400
        assert '50 MB' in response.json()['detail']
        assert c.get('/api/bootstrap').json()['projects'] == []


def test_mcp_import_accepts_large_escaped_document(tmp_path):
    # Escaped JSON is larger than UTF-8 content; both exceed the old transport cap.
    content = '# 大文档\n' + '中文说明\n' * 120000
    with TestClient(create_app(tmp_path, start_fixture=False, testing=True)) as c:
        c.headers['x-csrf-token'] = c.get('/api/bootstrap').json()['csrf']
        code = c.post('/api/mcp/pair').json()['code']
        token = c.post('/api/mcp/redeem', json={'code':code}).json()['token']
        response = c.post('/api/mcp/call', content=json.dumps({'action':'import',
            'arguments':{'title':'Large MCP document','filename':'large.md','content':content}}, ensure_ascii=True),
            headers={'authorization':'Bearer '+token,'content-type':'application/json'})
        assert response.status_code == 200, response.text[:300]
        assert response.json()['project']['filename'] == 'large.md'
