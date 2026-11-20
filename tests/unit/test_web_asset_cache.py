"""A changed script must not reuse an older browser cache entry."""
import re
from fastapi.testclient import TestClient
from api_test_tool import web


def test_api_workspace_versions_assets_and_static_responses_disable_cache(tmp_path, monkeypatch):
    static=tmp_path/'static';static.mkdir()
    assets=('app.js','ui-workflow.js','requirements-workflow.js','requirements-workflow.css','ui-flow.css','style.css','workflow-tools.js','workflow-tools.css','manual-cases.js')
    (static/'index.html').write_text(''.join(f'<script src="/static/{name}"></script>' for name in assets))
    for name in assets:
        (static/name).write_text('/* old */')
    monkeypatch.setattr(web,'STATIC',static)
    with TestClient(web.create_app(tmp_path/'data',start_fixture=False,testing=True)) as client:
        first=client.get('/api-testing')
        assert first.headers['cache-control']=='no-store'
        old=re.search(r'/static/app.js\?v=[a-f0-9]{16}',first.text).group()
        css=re.search(r'/static/style.css\?v=[a-f0-9]{16}',first.text).group()
        for name in assets:
            url=re.search(r'/static/'+re.escape(name)+r'\?v=[a-f0-9]{16}',first.text).group()
            assert client.get(url).status_code==200
        for url in (old,css,'/static/app.js'):
            response=client.get(url)
            assert response.status_code==200
            assert response.headers['cache-control']=='no-store'
        (static/'app.js').write_text('/* new */')  # same size: still gets a new URL
        second=client.get('/api-testing')
        new=re.search(r'/static/app.js\?v=[a-f0-9]{16}',second.text).group()
        assert new!=old
        assert client.get(new).text=='/* new */'
        assert css in second.text
        (static/'manual-cases.js').write_text('/* new */')
        third=client.get('/api-testing')
        assert re.search(r'/static/manual-cases.js\?v=[a-f0-9]{16}',third.text).group()!=re.search(r'/static/manual-cases.js\?v=[a-f0-9]{16}',second.text).group()
        old_flow=re.search(r'/static/ui-flow.css\?v=[a-f0-9]{16}',third.text).group()
        (static/'ui-flow.css').write_text('/* new */')
        ui_page=client.get('/ui-testing')
        new_flow=re.search(r'/static/ui-flow.css\?v=[a-f0-9]{16}',ui_page.text).group()
        assert new_flow!=old_flow
        assert client.get(new_flow).text=='/* new */'


def test_brand_pages_and_branded_particle_scene_are_served_without_stale_cache(tmp_path):
    with TestClient(web.create_app(tmp_path, start_fixture=False, testing=True)) as client:
        for url in ('/', '/api-testing', '/ui-testing', '/login'):
            response = client.get(url)
            assert response.status_code == 200
            assert '探真' in response.text and 'VERIQ' in response.text
            assert response.headers['cache-control'] == 'no-store'
        scene = client.get('/static/spark-background/veriq-badge.html')
        assert scene.status_code == 200
        assert "const str = 'VERIQ'" in scene.text
        assert scene.headers['cache-control'] == 'no-store'
