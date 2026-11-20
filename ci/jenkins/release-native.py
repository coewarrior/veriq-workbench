"""Publish the verified runtime to the existing user1 cloud service via SSH."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile

TARGET = 'user1@198.51.100.10'
REMOTE = '/home/user1/apps/api-test-releases'


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def output(*args):
    return run(*args, capture_output=True).stdout.strip()


def main(revision):
    if not re.fullmatch('[a-f0-9]{40}', revision):
        raise SystemExit('Full revision required')
    root = Path('.ci-output')
    receipt = root / 'release.json'
    receipt.unlink(missing_ok=True)
    if (root / 'verified-sha.txt').read_text().strip() != revision:
        raise SystemExit('Successful verification required')
    tag = 'api-test-web:git-' + revision
    image = (root / 'image-id.txt').read_text().strip()
    if output('docker', 'image', 'inspect', tag, '--format', '{{.Id}}') != image:
        raise SystemExit('Verified image changed')
    if output('git', 'ls-remote', 'origin', 'refs/heads/main').split()[0] != revision:
        raise SystemExit('A newer main exists; stale cloud release refused')
    secrets = Path(os.environ['API_TEST_CI_ROOT']) / 'secrets'
    options = ['-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=yes',
               '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=8',
               '-o', 'UserKnownHostsFile=' + str(secrets / 'cloud-known-hosts'),
               '-i', str(secrets / 'cloud-deploy')]
    destination = REMOTE + '/' + revision
    run('ssh', *options, TARGET, 'mkdir -p ' + destination)
    # The retired platform browser runner is not enabled on this lightweight
    # installation. Send web runtime files, not Docker/browser/build tooling.
    package = root / 'native-runtime.tar.gz'
    with tarfile.open(package, 'w:gz') as archive:
        archive.add(root / 'image/source', arcname='source')
        archive.add('deploy/web/requirements-web.lock', arcname='requirements-web.lock')
        archive.add('deploy/web/requirements-postgres.lock', arcname='requirements-postgres.lock')
        archive.add('api_test_tool/deployment_activity.py', arcname='deployment_activity.py')
    digest = hashlib.sha256()
    with package.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    run('scp', *options, str(package), TARGET + ':' + destination + '/runtime.tar.gz')
    run('scp', *options, 'ci/jenkins/native-install.py', TARGET + ':' + destination + '/install.py')
    # Re-check after transfer, before any remote mutation of the live service.
    if output('git', 'ls-remote', 'origin', 'refs/heads/main').split()[0] != revision:
        raise SystemExit('A newer main arrived during transfer; cloud switch refused')
    command = f'/home/user1/apps/api-test-workspace/.venv/bin/python -u {destination}/install.py {revision} {digest.hexdigest()}'
    with subprocess.Popen(['ssh', *options, TARGET, command], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, text=True) as remote:
        for line in remote.stdout:
            if line.strip() == 'READY_FOR_SWITCH':
                # The remote holds its publish lock and has finished staging
                # and draining. Authorize this exact revision immediately before stop.
                current = output('git', 'ls-remote', 'origin', 'refs/heads/main').split()[0]
                remote.stdin.write((revision if current == revision else 'STALE') + '\n')
                remote.stdin.flush()
            else:
                print(line, end='', flush=True)
        remote.stdin.close()
        if remote.wait() != 0:
            raise RuntimeError('Cloud publication failed; inspect the native release output')
    run('scp', *options, TARGET + ':' + destination + '/release.json', str(receipt))
    result = json.loads(receipt.read_text())
    if result.get('revision') != revision or result.get('target') != 'cloud-118':
        raise SystemExit('Invalid cloud release receipt')


if __name__ == '__main__':
    main(sys.argv[1])
