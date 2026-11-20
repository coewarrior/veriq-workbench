"""Release safety checks without Docker, network or user data."""
import importlib.util
import itertools
import json
import urllib.error
from pathlib import Path
from types import SimpleNamespace
import pytest


@pytest.fixture
def release(tmp_path, monkeypatch):
    path = Path(__file__).parents[2] / 'ci/jenkins/release.py'
    if not path.exists():
        # Runtime package intentionally excludes the CI control scripts.
        pytest.skip('release control-plane tests run from the repository')
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location('ci_release', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.chdir(tmp_path)
    (tmp_path / '.ci-output').mkdir()
    module.APP = tmp_path / 'app'
    module.APP.mkdir()
    module.STATE = tmp_path / 'releases'
    monkeypatch.setattr(module, 'activity', lambda container: {'rounds': 0, 'channels': 0,
        'finalizations': 0, 'acknowledgements': 0})
    # Keep these release-control cases isolated from Docker and PostgreSQL;
    # their existing unhealthy-candidate scenarios stop before activation.
    monkeypatch.setattr(module, 'source_mount', lambda container: 'type=volume,source=legacy,target=/data,readonly')
    monkeypatch.setattr(module, 'prepare_database', lambda image: None)
    monkeypatch.setattr(module, 'database_command', lambda *args, **kwargs: SimpleNamespace(stdout=''))
    monkeypatch.setattr(module, 'database_status', lambda image: {'backend': 'postgresql',
        'schema': 1, 'migration_id': 'migration', 'activation': 'ready', 'revision': '', 'verified': True})
    return module


def test_stale_release_does_not_touch_running_service(release, monkeypatch):
    revision = 'a' * 40
    Path('.ci-output/verified-sha.txt').write_text(revision)
    calls = []
    monkeypatch.setattr(release, 'output', lambda *args: ('b' * 40) + '\trefs/heads/main')
    monkeypatch.setattr(release, 'run', lambda *args, **kwargs: calls.append(args))
    release.main(revision)
    assert calls == []
    assert not (release.APP / 'compose.jenkins.json').exists()


def test_unhealthy_candidate_restores_previous_image(release, monkeypatch):
    revision = 'a' * 40
    Path('.ci-output/verified-sha.txt').write_text(revision)
    Path('.ci-output/image-id.txt').write_text('sha256:' + 'd' * 64)
    def output(*args):
        if args[0] == 'git': return revision + '\trefs/heads/main'
        if args[1] == 'inspect': return 'sha256:previous'
        if args[1] == 'image': return 'sha256:' + 'd' * 64
        return 'web-container'
    monkeypatch.setattr(release, 'output', output)
    calls = []
    def run(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout='web-container')
    monkeypatch.setattr(release, 'run', run)
    monkeypatch.setattr(release.subprocess, 'run', lambda *args, **kwargs: None)
    health = {'status': 'ok', 'revision': 'c' * 40,
              'deployment': {'draining': True, 'active_jobs': 0, 'active_writes': 0}}
    reads = itertools.count()
    monkeypatch.setattr(release, 'health', lambda: {**health,
        'deployment': {**health['deployment'], 'draining': next(reads) > 0}})
    with pytest.raises(RuntimeError, match='health verification'):
        release.main(revision)
    assert ('docker', 'stop', '--timeout=-1', 'web-container') in calls
    assert any('--force-recreate' in args for args in calls)
    assert json.loads((release.APP / 'compose.jenkins.json').read_text())['services']['web']['image'] == 'sha256:previous'
    assert not (release.STATE / 'current.json').exists()


def test_release_applies_runtime_limits_and_rollback_restores_previous_overrides(release, monkeypatch):
    revision = 'a' * 40
    image = 'sha256:' + 'd' * 64
    Path('.ci-output/verified-sha.txt').write_text(revision)
    Path('.ci-output/image-id.txt').write_text(image)
    old = {'services': {'web': {'image': 'old-tag', 'cpus': 0.5, 'mem_limit': '1g',
                               'environment': {'API_TEST_REVISION': 'c' * 40, 'KEEP_SETTING': 'yes'}}}}
    (release.APP / 'compose.jenkins.json').write_text(json.dumps(old))

    def output(*args):
        if args[0] == 'git': return revision + '\trefs/heads/main'
        if args[1] == 'inspect': return 'sha256:previous'
        if args[1] == 'image': return image
        return 'web-container'

    monkeypatch.setattr(release, 'output', output)
    monkeypatch.setattr(release, 'run', lambda *args, **kwargs: None)
    monkeypatch.setattr(release.subprocess, 'run', lambda *args, **kwargs: None)
    reads = itertools.count()
    monkeypatch.setattr(release, 'health', lambda: {'status': 'ok', 'revision': 'c' * 40,
        'deployment': {'draining': next(reads) > 0, 'active_jobs': 0, 'active_writes': 0}})
    snapshots = []
    def compose(*args, **kwargs):
        if args[0] == 'ps':
            return SimpleNamespace(stdout='web-container')
        snapshots.append(json.loads((release.APP / 'compose.jenkins.json').read_text())['services']['web'])
        return SimpleNamespace(stdout='')
    monkeypatch.setattr(release, 'compose', compose)
    with pytest.raises(RuntimeError, match='health verification'):
        release.main(revision)
    candidate, restored = snapshots
    assert candidate['cpus'] == 0 and candidate['mem_limit'] == '8g' and candidate['pids_limit'] == 12288
    assert candidate['environment']['API_TEST_PUBLIC_REPORT_PORT'] == '18090'
    assert candidate['ports'] == [{'target': 18090, 'published': '8888',
                                  'host_ip': '0.0.0.0', 'protocol': 'tcp'}]
    assert candidate['environment']['KEEP_SETTING'] == 'yes'
    assert restored['image'] == 'sha256:previous'
    assert restored['cpus'] == 0.5 and restored['mem_limit'] == '1g'
    assert restored['environment']['KEEP_SETTING'] == 'yes'
    assert json.loads((release.APP / 'compose.jenkins.json').read_text()) == old


def test_public_report_health_rejects_exposed_platform_api(release, monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def read(self): return b'{"status":"ok"}'

    monkeypatch.setattr(release.urllib.request, 'urlopen', lambda url, timeout: Response())
    with pytest.raises(RuntimeError, match='exposed a platform API'):
        release.public_report_health()

    def restricted(url, timeout):
        if url.endswith('/api/bootstrap'):
            raise urllib.error.HTTPError(url, 404, 'not found', {}, None)
        return Response()
    monkeypatch.setattr(release.urllib.request, 'urlopen', restricted)
    assert release.public_report_health() == {'status': 'ok'}


def test_health_recovers_slow_old_service_without_replacing_response(release, monkeypatch):
    timeouts = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def read(self): return b'{"status":"ok","deployment":{"active_jobs":4}}'
    def request(url, timeout):
        timeouts.append(timeout)
        if len(timeouts) < 3:
            raise TimeoutError('busy')
        return Response()
    monkeypatch.setattr(release.urllib.request, 'urlopen', request)
    monkeypatch.setattr(release.time, 'sleep', lambda seconds: None)
    assert release.health()['deployment']['active_jobs'] == 4
    assert timeouts == [10, 20, 30]


def test_health_retry_is_bounded_and_never_returns_false_idle(release, monkeypatch):
    calls = []
    def request(url, timeout):
        calls.append(timeout)
        raise TimeoutError('busy')
    monkeypatch.setattr(release.urllib.request, 'urlopen', request)
    monkeypatch.setattr(release.time, 'sleep', lambda seconds: None)
    with pytest.raises(TimeoutError):
        release.health()
    assert calls == [10, 20, 30]


@pytest.mark.parametrize('busy', [True, False])
def test_preflight_unavailable_or_busy_preserves_running_service(release, monkeypatch, busy):
    revision, image = 'a' * 40, 'sha256:' + 'd' * 64
    Path('.ci-output/verified-sha.txt').write_text(revision)
    Path('.ci-output/image-id.txt').write_text(image)
    def output(*args):
        if args[0] == 'git': return revision + '\trefs/heads/main'
        if args[1] == 'inspect': return 'sha256:previous'
        if args[1] == 'image': return image
        return 'web-container'
    def health():
        assert not busy, 'Known active work must defer before querying busy health'
        raise TimeoutError('busy')
    monkeypatch.setattr(release, 'output', output)
    monkeypatch.setattr(release, 'health', health)
    monkeypatch.setattr(release, 'activity', lambda cid: {'channels': int(busy)})
    calls = []
    monkeypatch.setattr(release, 'run', lambda *args, **kwargs: calls.append(args))
    release.main(revision)
    result = json.loads(Path('.ci-output/release.json').read_text())
    assert result['status'] == 'postponed'
    assert calls == []  # No drain flag, stop, restart or live-file change.
    assert not (release.APP / 'compose.jenkins.json').exists()
    assert not (release.STATE / 'current.json').exists()
