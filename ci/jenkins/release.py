"""Serialize app-only releases; preserve data/env and roll back unhealthy images."""
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

from postgres_runtime import IMAGE as POSTGRES_IMAGE, NETWORK as POSTGRES_NETWORK
from postgres_runtime import SERVICE as POSTGRES_SERVICE, VOLUME as POSTGRES_VOLUME
from postgres_runtime import extend_override, prepare_secrets, provision_role

APP = Path('/home/veriq/apps/api-test-web')
STATE = Path('/home/veriq/jenkins-api-test/releases')
DRAIN = '/tmp/api-test-deploy-drain'
PUBLIC_REPORT_CONTAINER_PORT = 18090
PUBLIC_REPORT_HOST_PORT = 8888


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def output(*args):
    return run(*args, capture_output=True).stdout.strip()


def compose(*args, **kwargs):
    return run('docker', 'compose', '--project-directory', str(APP), '-f', str(APP / 'compose.yaml'),
               '-f', str(APP / 'compose.jenkins.json'), *args, **kwargs)


def atomic(path, data):
    temp = path.with_suffix(path.suffix + '.pending')
    with temp.open('w') as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def health():
    # Old releases serve health through the busy request pool and SQLite. Allow
    # bounded recovery without treating a timeout as an empty/healthy service.
    for attempt, timeout in enumerate((10, 20, 30)):
        try:
            with urllib.request.urlopen('http://192.0.2.20:18089/healthz', timeout=timeout) as response:
                result = json.load(response)
            if result.get('status') != 'ok':
                raise RuntimeError('Health endpoint did not report ok')
            return result
        except urllib.error.HTTPError as error:
            if error.code not in {502, 503, 504} or attempt == 2:
                raise
        except (TimeoutError, urllib.error.URLError, ConnectionError):
            if attempt == 2:
                raise
        print('Health endpoint temporarily unavailable; retrying read-only check.', flush=True)
        time.sleep(1)


def public_report_health():
    with urllib.request.urlopen(f'http://127.0.0.1:{PUBLIC_REPORT_HOST_PORT}/healthz', timeout=3) as response:
        status = json.load(response)
    try:
        urllib.request.urlopen(f'http://127.0.0.1:{PUBLIC_REPORT_HOST_PORT}/api/bootstrap', timeout=3)
    except urllib.error.HTTPError as error:
        storage = status.get('storage', {})
        gated = storage.get('backend') == 'postgresql' and status.get('deployment', {}).get('draining')
        allowed = {404, 503} if storage.get('activation') == 'ready' or gated else {404}
        if error.code not in allowed:
            raise
    else:
        raise RuntimeError('Public report port exposed a platform API')
    return status


def activity(container, status=None):
    # The candidate's read-only probe works before the old image is replaced.
    probe = Path(__file__).resolve().parents[2] / 'api_test_tool/deployment_activity.py'
    status = health()['deployment'] if status is None else status
    capable = status.get('activity_capability_version', 0) >= 1
    args = ['docker', 'exec', '-i']
    if capable:
        args += ['-e', 'VERIQ_ACTIVITY_ADMISSION_V1=1', '-e', 'VERIQ_ACTIVITY_DETAILS=1']
    result = run(*args, container, 'python', '-', input=probe.read_text(), capture_output=True)
    value = json.loads(result.stdout)
    if capable:
        # Release receipts expose useful reasons, not user goals or chat identity.
        return {'summary': value['summary'], 'blockers': [{key: row.get(key) for key in
            ('category', 'task_id', 'node_id', 'code', 'reason', 'next_action')} for row in value['blockers']]}
    return value


def blocking_activity(counts):
    # Only the proven idle native report drafts are informational. Unknown
    # counters continue to block; real jobs/writes/drain checks remain below.
    summary = counts.get('summary', counts)
    return bool(counts.get('blockers')) or any(value for key, value in summary.items()
        if key not in {'dormant_reports', 'waiting', 'residuals'})


def executing_jobs(status):
    # Existing business jobs postpone release. Entered background work drains
    # after admission closes, without killing writers or mistaking an idle tick
    # for a running business test.
    return max(0, status.get('active_jobs', 0) - sum(status.get(key, 0) for key in
        ('active_report_workers', 'active_report_projection_workers', 'active_schedulers')))


def postponed(revision, reason, counts=None):
    atomic(Path('.ci-output/release.json'), json.dumps({
        'revision': revision, 'status': 'postponed', 'reason': reason, 'activity': counts}))
    print('Release postponed; current tests and service retained: ' + reason)


def runtime_override(image, revision, previous=None):
    # Compose on the host is preserved; override its old CPU quota explicitly.
    config = json.loads(previous) if previous is not None else {'services': {'web': {}}}
    service = config['services']['web']
    service.update(image=image, cpus=0, mem_limit='8g', pids_limit=12288)
    service.setdefault('environment', {})['API_TEST_REVISION'] = revision
    service['environment']['API_TEST_PUBLIC_REPORT_PORT'] = str(PUBLIC_REPORT_CONTAINER_PORT)
    service['ports'] = [{'target': PUBLIC_REPORT_CONTAINER_PORT, 'published': str(PUBLIC_REPORT_HOST_PORT),
                         'host_ip': '0.0.0.0', 'protocol': 'tcp'}]
    return extend_override(config, APP)


def database_command(image, *args, data_mount=None, capture_output=False):
    # This short-lived full-history migration/verification process needs a
    # separate budget from the 2 GiB database service. The normal web limit is
    # also 8 GiB; no runtime worker or unrelated service limits are changed.
    command = ['docker', 'run', '--rm', '--network', POSTGRES_NETWORK, '--read-only',
               '--memory', '8g', '--pids-limit', '128', '--cap-drop', 'ALL',
               '--security-opt', 'no-new-privileges:true', '--tmpfs', '/tmp:rw,nosuid,size=128m',
               '--mount', 'type=bind,source=' + str(APP / 'secrets/postgres-app.runtime') +
               ',target=/run/secrets/veriq_app_password,readonly',
               '-e', 'API_TEST_DB_HOST=' + POSTGRES_SERVICE,
               '-e', 'API_TEST_DB_NAME=veriq', '-e', 'API_TEST_DB_USER=veriq',
               '-e', 'API_TEST_DB_PASSWORD_FILE=/run/secrets/veriq_app_password']
    if data_mount is not None:
        command.extend(['--mount', data_mount])
    return run(*command, image, 'python', *args, capture_output=capture_output)


def database_status(image):
    result = database_command(image, '-c',
        'import json; from api_test_tool.database import storage_status; print(json.dumps(storage_status()))',
        capture_output=True)
    return json.loads(result.stdout)


def source_mount(container):
    mounts = json.loads(output('docker', 'inspect', container, '--format', '{{json .Mounts}}'))
    mount = next((value for value in mounts if value.get('Destination') == '/data'), None)
    if not mount or mount.get('Type') not in {'volume', 'bind'}:
        raise RuntimeError('Existing application data mount could not be identified')
    source = mount['Name'] if mount['Type'] == 'volume' else mount['Source']
    if ',' in source:
        raise RuntimeError('Unsupported application data mount name')
    return 'type=' + mount['Type'] + ',source=' + source + ',target=/data,readonly'


def prepare_database(image):
    exists = subprocess.run(['docker', 'volume', 'inspect', POSTGRES_VOLUME],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if subprocess.run(['docker', 'image', 'inspect', POSTGRES_IMAGE],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        run('docker', 'pull', POSTGRES_IMAGE)
    prepare_secrets(APP / 'secrets', image, existing_volume=exists)
    compose('up', '-d', '--no-deps', '--no-build', '--wait', '--wait-timeout', '120', POSTGRES_SERVICE)
    container = compose('ps', '-q', POSTGRES_SERVICE, capture_output=True).stdout.strip()
    if not container:
        raise RuntimeError('Dedicated PostgreSQL container did not start')
    provision_role(container, APP / 'secrets/postgres-app.password')


def verify_candidate(current, revision, *, active=False, migration_id=None):
    storage = current.get('storage', {})
    if (current.get('revision') != revision or current.get('status') != 'ok'
            or storage.get('backend') != 'postgresql' or storage.get('schema') != 1
            or storage.get('verified') is not True
            or not isinstance(storage.get('migration_id'), str) or not storage['migration_id']
            or (migration_id is not None and storage['migration_id'] != migration_id)
            or storage.get('activation') not in {'ready', 'active'}):
        raise RuntimeError('Published revision or PostgreSQL storage did not pass health verification')
    if active and (storage.get('activation') != 'active' or storage.get('revision') != revision
                   or current.get('deployment', {}).get('draining')):
        raise RuntimeError('PostgreSQL activation has not opened the verified application')


def record_published(revision, target, old_image, current, counts):
    atomic(STATE / 'current.json', json.dumps({'revision': revision, 'image': target,
        'previous_image': old_image, 'storage': current['storage']}))
    atomic(Path('.ci-output/release.json'), json.dumps({'revision': revision, 'status': 'published',
        'health': current, 'activity_before_switch': counts}))


def wait_activation(revision):
    deadline = time.monotonic() + 120
    while True:
        current = health()
        public = public_report_health()
        if (current.get('storage', {}).get('activation') == 'active'
                and not current.get('deployment', {}).get('draining')
                and not public.get('deployment', {}).get('draining')):
            verify_candidate(current, revision, active=True)
            verify_candidate(public, revision, active=True)
            return current
        if time.monotonic() >= deadline:
            raise RuntimeError('Candidate did not open after durable PostgreSQL activation')
        time.sleep(1)


def main(revision):
    if not re.fullmatch('[a-f0-9]{40}', revision):
        raise SystemExit('Full commit SHA required')
    if Path('.ci-output/verified-sha.txt').read_text().strip() != revision:
        raise SystemExit('No successful verification for this revision')
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / 'publish.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        remote = output('git', 'ls-remote', 'origin', 'refs/heads/main').split()[0]
        if remote != revision:
            print('A newer main commit exists; skipping stale release.')
            return
        cid = output('docker', 'compose', '--project-directory', str(APP), 'ps', '-q', 'web')
        if not cid:
            raise SystemExit('Expected existing web service is missing; refusing first-time bootstrap')
        old_image = output('docker', 'inspect', cid, '--format', '{{.Image}}')
        tag = 'api-test-web:git-' + revision
        target = Path('.ci-output/image-id.txt').read_text().strip()
        if not re.fullmatch('sha256:[a-f0-9]{64}', target) or target != output('docker', 'image', 'inspect', tag, '--format', '{{.Id}}'):
            raise SystemExit('Candidate image changed after verification; refusing release')
        override = APP / 'compose.jenkins.json'
        old_override = override.read_text() if override.exists() else None
        candidate_override = runtime_override(target, revision, old_override)
        if old_image == target:
            # Recover an interrupted activation/receipt without stopping a
            # deployed image or treating its newly admitted work as a release.
            current = health()
            verify_candidate(current, revision)
            verify_candidate(public_report_health(), revision)
            storage = current['storage']
            if storage['activation'] != 'active' or storage.get('revision') != revision:
                database_command(target, '-m', 'api_test_tool.storage_migrate', 'verify')
                database_command(target, '-m', 'api_test_tool.storage_migrate', 'activate', '--revision', revision)
            current = wait_activation(revision)
            counts = activity(cid)
            record_published(revision, target, old_image, current, counts)
            print('Verified deployed PostgreSQL revision; release receipt recovered.')
            return
        counts = None
        try:
            previous = health()
        except (TimeoutError, urllib.error.URLError, ConnectionError) as error:
            # No drain flag or service mutation has occurred. Record the reason
            # for retry instead of losing the release outcome to a traceback.
            postponed(revision, 'Preflight health unavailable after bounded retries: ' + type(error).__name__, counts)
            return
        status = previous.get('deployment', {})
        counts = activity(cid, status)
        if status.get('draining') or executing_jobs(status) or blocking_activity(counts):
            postponed(revision, 'Existing rounds, execution channels or settlement work remain', counts)
            return
        atomic(STATE / (revision + '.previous.json'), json.dumps({'image': old_image, 'health': previous}))
        source = source_mount(cid)
        previous_postgres = previous.get('storage', {}).get('backend') == 'postgresql'
        current_record = STATE / 'current.json'
        previous_record = json.loads(current_record.read_text()) if current_record.exists() else {}
        journal = STATE / (revision + '.cutover.json')
        def phase(name):
            atomic(journal, json.dumps({'revision': revision, 'phase': name,
                'previous_backend': 'postgresql' if previous_postgres else 'sqlite',
                'previous_image': old_image, 'image': target}))
        stopped = False
        activation_attempted = False
        activated = False
        clear_drain = True
        try:
            phase('draining')
            run('docker', 'exec', cid, 'touch', DRAIN)
            if 'deployment' in previous:
                deadline = time.monotonic() + 600
                while True:
                    status = health()['deployment']
                    counts = activity(cid, status)
                    if executing_jobs(status) or blocking_activity(counts):
                        postponed(revision, 'Existing work appeared before switching; admission reopened', counts)
                        return
                    if status['draining'] and not status['active_jobs'] and not status['active_writes']:
                        break
                    if time.monotonic() > deadline:
                        raise RuntimeError('Users still have active jobs; release postponed, existing service retained')
                    time.sleep(3)
            else:
                print('First CI migration: graceful shutdown waits for all existing jobs without a kill timeout.')
            # Infinite grace prevents Docker's default forced termination of long jobs.
            run('docker', 'stop', '--timeout=-1', cid)
            stopped = True
            clear_drain = False
            phase('previous-stopped')
            atomic(override, json.dumps(candidate_override))
            prepare_database(target)
            database_command(target, '-m', 'api_test_tool.storage_migrate', 'import-sqlite', data_mount=source)
            database_command(target, '-m', 'api_test_tool.storage_migrate', 'verify')
            imported = database_status(target)
            activated = imported.get('activation') == 'active'
            phase('import-verified')
            compose('up', '-d', '--no-deps', '--no-build', '--wait', '--wait-timeout', '120', 'web')
            current = health()
            verify_candidate(current, revision, migration_id=imported['migration_id'])
            public = public_report_health()
            verify_candidate(public, revision, migration_id=imported['migration_id'])
            phase('candidate-verified')
            activation_attempted = True
            phase('activating')
            database_command(target, '-m', 'api_test_tool.storage_migrate', 'activate', '--revision', revision)
            activated = True
            phase('activated')
            current = wait_activation(revision)
            record_published(revision, target, old_image, current, counts)
            phase('published')
            print('Published verified commit ' + revision)
        except BaseException as error:
            if stopped and not previous_postgres and (activated or activation_attempted):
                # Activation can commit even when the CLI loses its response.
                # Never restart an obsolete SQLite authority on uncertainty.
                try:
                    current = health()
                    verify_candidate(current, revision, active=True)
                    verify_candidate(public_report_health(), revision, active=True)
                    record_published(revision, target, old_image, current, counts)
                    phase('published')
                except Exception:
                    atomic(Path('.ci-output/release.json'), json.dumps({'revision': revision,
                        'status': 'failed', 'phase': 'activation-committed-or-unknown',
                        'rollback': 'retained-postgresql', 'reason': type(error).__name__}))
                    print('PostgreSQL authority retained; legacy SQLite rollback is prohibited.')
                    raise error
                if isinstance(error, (SystemExit, KeyboardInterrupt)):
                    raise
                print('Activated PostgreSQL revision verified; release receipt recovered.')
                return
            if stopped:
                candidate = compose('ps', '-q', 'web', capture_output=True).stdout.strip()
                if candidate:
                    if previous_postgres:
                        # A PG-compatible rollback still must not interrupt work
                        # admitted by an already-active candidate. Unknown counts
                        # retain that service instead of bypassing the old gate.
                        run('docker', 'exec', candidate, 'touch', DRAIN)
                        clear_drain = True
                        rollback_counts = activity(candidate)
                        rollback_status = health().get('deployment', {})
                        if (rollback_status.get('draining') is not True
                                or blocking_activity(rollback_counts) or rollback_status.get('active_jobs')
                                or rollback_status.get('active_writes')):
                            atomic(Path('.ci-output/release.json'), json.dumps({'revision': revision,
                                'status': 'failed', 'phase': 'rollback-postponed',
                                'rollback': 'retained-postgresql', 'activity': rollback_counts}))
                            raise RuntimeError('Candidate admitted work; PostgreSQL service retained for safe recovery') from error
                    run('docker', 'stop', '--timeout=-1', candidate)
                    clear_drain = False
                # Force a recreate on rollback; its tmpfs must not retain the drain flag.
                rollback = json.loads(old_override) if old_override is not None else {'services': {'web': {}}}
                old_web = rollback['services']['web']
                old_web['image'] = old_image
                old_web.setdefault('environment', {})['API_TEST_REVISION'] = previous.get('revision', '')
                atomic(override, json.dumps(rollback))
                compose('up', '-d', '--no-deps', '--no-build', '--force-recreate', '--wait', '--wait-timeout', '120', 'web')
                if old_override is not None:
                    atomic(override, old_override)
                clear_drain = True
                if previous_postgres:
                    old_revision = previous['revision']
                    database_command(old_image, '-m', 'api_test_tool.storage_migrate',
                                     'activate', '--revision', old_revision)
                    restored = wait_activation(old_revision)
                    restored_record = (previous_record.copy()
                        if previous_record.get('revision') == old_revision
                        and previous_record.get('image') == old_image else {})
                    restored_record.update(revision=old_revision, image=old_image, storage=restored['storage'])
                    atomic(current_record, json.dumps(restored_record))
                    atomic(Path('.ci-output/release.json'), json.dumps({'revision': revision,
                        'status': 'failed', 'phase': 'rolled-back',
                        'rollback': {'revision': old_revision, 'image': old_image}, 'health': restored}))
                phase('rolled-back')
                print('Restored previous compatible image; persistent data unchanged.')
            raise
        finally:
            if clear_drain:
                active = output('docker', 'compose', '--project-directory', str(APP), 'ps', '-q', 'web')
                if active:
                    subprocess.run(['docker', 'exec', active, 'rm', '-f', DRAIN], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == '__main__':
    def interrupted(signum, _frame):
        # Jenkins launches children with SIGINT ignored. Explicit handlers ensure
        # its cancellation still runs the drain cleanup/rollback in finally.
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    main(sys.argv[1])
