"""Jenkins-only native installer; preserve user service, data and resource budget."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from uuid import uuid4

HOME = Path('/home/user1')
APP = HOME / 'apps/api-test-workspace'
DATA = HOME / 'apps/api-test-data'
RELEASES = HOME / 'apps/api-test-releases'
UNIT = 'api-test-workspace.service'
DROPIN = HOME / '.config/systemd/user' / (UNIT + '.d') / '50-jenkins.conf'
DRAIN = Path('/tmp/api-test-deploy-drain')
MAINTENANCE = Path('/var/lib/api-test-release/maintenance')
PUBLIC = 'https://198.51.100.10'
DB_CONFIG = HOME / '.config/api-test-workspace/postgres.json'


def verify_storage(status, revision, *, active=False, migration_id=None):
    storage = status.get('storage', {})
    if (status.get('revision') != revision or storage.get('backend') != 'postgresql'
            or storage.get('schema') != 1 or storage.get('verified') is not True
            or not storage.get('migration_id') or storage.get('activation') not in {'ready', 'active'}
            or (migration_id is not None and storage['migration_id'] != migration_id)
            or (active and (storage['activation'] != 'active' or storage.get('revision') != revision))):
        raise RuntimeError('PostgreSQL release identity or readiness mismatch')


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def systemctl(*args):
    return run('systemctl', '--user', *args, stdout=subprocess.DEVNULL)


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + '.pending')
    pending.write_text(value)
    pending.chmod(0o600)
    os.replace(pending, path)


def health(public=False):
    url = (PUBLIC if public else 'http://127.0.0.1:18089') + '/healthz'
    with urllib.request.urlopen(url, timeout=10) as response:
        result = json.load(response)
    if result.get('status') != 'ok':
        raise RuntimeError('Unhealthy service')
    return result


def ready(expected, previous=False):
    for attempt in range(40):
        try:
            status = health()
            if (status.get('version') if previous else status.get('revision')) != expected:
                raise RuntimeError('Unexpected running version')
            return status
        except Exception:
            if attempt == 39:
                raise
            time.sleep(2)


def open_verified(revision):
    DRAIN.unlink(missing_ok=True)
    for _ in range(60):
        current = health()
        verify_storage(current, revision, active=True)
        if not current['deployment']['draining']:
            break
        time.sleep(1)
    else:
        raise RuntimeError('Activated service has not opened')
    verify_storage(health(True), revision, active=True)
    MAINTENANCE.unlink(missing_ok=True)
    with urllib.request.urlopen(PUBLIC + '/login', timeout=10) as response:
        if response.status != 200 or b'<html' not in response.read(65536).lower():
            raise RuntimeError('Public login startup check failed')
    return current


def migrate(python, source, env, *args):
    result = run(str(python), '-m', 'api_test_tool.storage_migrate', *args,
                 cwd=source, env=env, capture_output=True)
    return json.loads(result.stdout)


def link(target):
    pending = APP.with_name(APP.name + '.pending')
    pending.unlink(missing_ok=True)
    pending.symlink_to(target)
    os.replace(pending, APP)


def main(revision, digest):
    if not re.fullmatch('[a-f0-9]{40}', revision) or not re.fullmatch('[a-f0-9]{64}', digest):
        raise SystemExit('Invalid release identity')
    if os.getuid() != APP.stat().st_uid or os.getuid() == 0:
        raise SystemExit('Run as the existing application owner, not root')
    os.environ['XDG_RUNTIME_DIR'] = '/run/user/' + str(os.getuid())
    os.umask(0o077)
    candidate = RELEASES / revision
    receipt = candidate / 'release.json'

    def record(status, **values):
        atomic(receipt, json.dumps({'revision': revision, 'target': 'cloud-118',
                                   'status': status, **values}))

    with (RELEASES / 'publish.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        before = health()
        previous_postgres = before.get('storage', {}).get('backend') == 'postgresql'
        db_env = json.loads(DB_CONFIG.read_text())
        expected_keys = {'API_TEST_DB_HOST', 'API_TEST_DB_PORT', 'API_TEST_DB_NAME',
                         'API_TEST_DB_USER', 'API_TEST_DB_PASSWORD_FILE'}
        if set(db_env) != expected_keys or any(not re.fullmatch(r'[a-zA-Z0-9_./-]+', value) for value in db_env.values()):
            raise RuntimeError('Invalid native PostgreSQL configuration')
        if before.get('revision') == revision:
            verify_storage(before, revision)
            verify_storage(health(True), revision)
            current_env = {**os.environ, **db_env, 'PYTHONPATH': str(APP)}
            migrate(APP / '.venv/bin/python', APP, current_env, 'verify')
            migrate(APP / '.venv/bin/python', APP, current_env, 'activate', '--revision', revision)
            current = open_verified(revision)
            record('published', health=current, already_current=True)
            return
        if before['deployment']['active_jobs'] or before['deployment']['draining']:
            record('postponed', reason='Existing jobs or deployment remain active')
            return
        if shutil.disk_usage(RELEASES).free < 2 * 1024**3:
            raise RuntimeError('At least 2 GiB free disk required for staging and rollback')
        archive = candidate / 'runtime.tar.gz'
        with archive.open('rb') as handle:
            actual = hashlib.sha256()
            for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                actual.update(chunk)
        if actual.hexdigest() != digest:
            raise RuntimeError('Runtime transfer checksum mismatch')
        # Data filter rejects unsafe paths, devices and links outside staging.
        with tarfile.open(archive) as bundle:
            bundle.extractall(candidate, filter='data')
        source = candidate / 'source'
        venv = source / '.venv'
        python = venv / 'bin/python'
        if not python.exists():
            run(str(APP / '.venv/bin/python'), '-m', 'venv', str(venv))
        for name in ('requirements-web.lock', 'requirements-postgres.lock'):
            args = [str(python), '-m', 'pip', 'install', '--no-cache-dir', '--only-binary=:all:',
                    '--index-url', 'https://pypi.tuna.tsinghua.edu.cn/simple', '-r', str(candidate / name)]
            if name == 'requirements-postgres.lock':
                args += ['--require-hashes', '--no-deps']
            result = subprocess.run(args, text=True, capture_output=True)
            if result.returncode:
                raise RuntimeError('Runtime dependency installation failed: ' + result.stderr[-2500:])
        run(str(python), '-m', 'pip', 'check')
        # Web-only runtime: the retired browser runner is not installed/enabled.
        env = {**os.environ, **db_env,
               'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(source)}
        run(str(python), '-c', 'import api_test_tool.web', cwd=source, env=env)

        def database(*args):
            return migrate(python, source, env, *args)

        def idle():
            status = health()['deployment']
            probe_env = {**os.environ, 'API_TEST_DATA_DIR': str(DATA)}
            if status.get('activity_capability_version', 0) >= 1:
                probe_env['VERIQ_ACTIVITY_ADMISSION_V1'] = '1'
            if previous_postgres:
                probe_env.update(db_env)
            result = run(str(python), str(candidate / 'deployment_activity.py'),
                         env=probe_env, capture_output=True)
            counts = json.loads(result.stdout)
            return (not any(v for k, v in counts.items() if k not in {'dormant_reports', 'waiting', 'residuals'})
                    and not status['active_jobs'] and not status['active_writes'])

        if not idle():
            record('postponed', reason='Existing business activity; service unchanged')
            return
        previous = APP.resolve()
        old_dropin = DROPIN.read_text() if DROPIN.exists() else None
        backup = candidate / 'previous-data.tar.gz'
        stopped = switched = backed_up = False
        activation_attempted = False
        activated = False
        admission_opened = False
        recovered = True
        DRAIN.touch(exist_ok=False)
        try:
            MAINTENANCE.touch(exist_ok=False)
            try:
                urllib.request.urlopen(PUBLIC + '/login', timeout=10)
            except urllib.error.HTTPError as error:
                if error.code != 503 or error.headers.get('X-Veriq-Maintenance') != '1':
                    raise RuntimeError('Public maintenance gate is not configured') from error
            else:
                raise RuntimeError('Public maintenance gate did not block traffic')
            for _ in range(20):
                if idle() and health()['deployment']['draining']:
                    break
                time.sleep(1)
            else:
                record('postponed', reason='Admission did not drain; service retained')
                return
            size = sum(p.stat().st_size for p in DATA.rglob('*') if p.is_file())
            if shutil.disk_usage(DATA).free < 2 * size + 1024**3:
                raise RuntimeError('Insufficient space for backup plus a complete rollback copy')
            print('READY_FOR_SWITCH', flush=True)
            if sys.stdin.readline().strip() != revision:
                raise RuntimeError('Fresh main revision permission absent; live service retained')
            # Prevent systemd's default timeout from killing a late shutdown.
            atomic(DROPIN, '[Service]\nTimeoutStopSec=infinity\nSendSIGKILL=no\n' +
                   (old_dropin or ''))
            systemctl('daemon-reload')
            stopped = True
            recovered = False
            systemctl('stop', UNIT)
            with tarfile.open(backup, 'w:gz') as bundle:
                bundle.add(DATA, arcname=DATA.name)
            backed_up = True
            if shutil.disk_usage(DATA).free < size + 1024**3:
                raise RuntimeError('Rollback reserve was consumed; switch refused')
            migration_args = ['import-sqlite', '--source', str(DATA)]
            if before.get('version') == '0.13.0' and not (DATA / 'orchestration.sqlite3').exists():
                migration_args.append('--legacy-accounts-only')
            imported = database(*migration_args)
            activated = imported.get('activation') == 'active'
            database('verify')
            if not APP.is_symlink():
                previous = RELEASES / ('legacy-' + str(int(time.time())))
                APP.rename(previous)
            link(source)
            switched = True
            atomic(DROPIN, '[Service]\nTimeoutStopSec=infinity\nSendSIGKILL=no\n' +
                   f'Environment=API_TEST_REVISION={revision}\n' +
                   ''.join(f'Environment={key}={value}\n' for key, value in db_env.items()) +
                   'Environment=PYTHONDONTWRITEBYTECODE=1\n')
            systemctl('daemon-reload')
            systemctl('start', UNIT)
            current = ready(revision)
            public = health(True)
            verify_storage(current, revision, migration_id=imported['migration_id'])
            verify_storage(public, revision, migration_id=imported['migration_id'])
            activation_attempted = True
            database('activate', '--revision', revision)
            activated = True
            admission_opened = True
            current = open_verified(revision)
            atomic(RELEASES / 'current.json', json.dumps({'revision': revision,
                'previous': str(previous), 'backup': str(backup)}))
            record('published', health=current, previous=str(previous))
            recovered = True
            archive.unlink(missing_ok=True)
            print('Published cloud revision ' + revision, flush=True)
        except BaseException:
            if stopped and (admission_opened or (not previous_postgres and (activated or activation_attempted))):
                # Activation may have committed despite a lost response. Never
                # replace the new authority with the obsolete SQLite snapshot.
                record('failed', rollback='retained-postgresql', phase='activation-committed-or-unknown')
                print('PostgreSQL retained; legacy SQLite rollback prohibited.', flush=True)
                raise
            if stopped:
                systemctl('stop', UNIT)
                if switched:
                    link(previous)
                elif not APP.exists() and previous.exists():
                    link(previous)
                if backed_up and not previous_postgres:
                    failed_data = candidate / ('failed-start-data-' + uuid4().hex)
                    restore = candidate / ('restore-' + uuid4().hex)
                    restore.mkdir()
                    with tarfile.open(backup) as bundle:
                        bundle.extractall(restore, filter='data')
                    DATA.rename(failed_data)
                    (restore / DATA.name).rename(DATA)
                    restore.rmdir()
                if old_dropin is None:
                    DROPIN.unlink(missing_ok=True)
                else:
                    atomic(DROPIN, old_dropin)
                systemctl('daemon-reload')
                if previous_postgres:
                    database('activate', '--revision', before['revision'])
                systemctl('start', UNIT)
                ready(before['version'], previous=True)
                recovered = True
                print('Restored previous code, settings and data.', flush=True)
            raise
        finally:
            if recovered:
                DRAIN.unlink(missing_ok=True)
                MAINTENANCE.unlink(missing_ok=True)


if __name__ == '__main__':
    def interrupted(signum, _frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    main(*sys.argv[1:])
