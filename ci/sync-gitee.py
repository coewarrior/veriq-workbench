"""Fast-forward the dedicated Gitee repository to a verified published release."""
import argparse
import json
from pathlib import Path
import re
import subprocess


JENKINS = 'http://192.0.2.20:18140/job/api-test-workspace/job/deploy-main'
HEALTH = 'http://192.0.2.20:18089/healthz'
GITEE = 'git@gitee.com:Code_Warrior/api-test-workspace.git'
SOURCE = 'http://192.0.2.34/example/api-test-workspace.git'
BRANCH = 'refs/heads/main'
ROOT = Path(__file__).resolve().parents[1]


def command(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def read_json(url, netrc=None):
    args = ['curl', '--fail', '--silent', '--show-error', '--connect-timeout', '10', '--max-time', '30']
    if netrc:
        args += ['--netrc-file', str(netrc)]
    return json.loads(command(*args, url))


def remote_head():
    rows = command('git', 'ls-remote', '--heads', GITEE, BRANCH).splitlines()
    if len(rows) > 1:
        raise ValueError('Unexpected Gitee branch response')
    if not rows:
        return None
    revision, ref = rows[0].split()
    if ref != BRANCH or not re.fullmatch(r'[a-f0-9]{40}', revision):
        raise ValueError('Invalid Gitee branch response')
    return revision


def sync(build, netrc):
    job = f'{JENKINS}/{build}'
    metadata = read_json(job + '/api/json', netrc)
    parameters = [p for a in metadata.get('actions', []) for p in a.get('parameters', [])]
    if (metadata.get('building') is not False or metadata.get('result') != 'SUCCESS'
            or not any(p.get('name') == 'DEPLOY' and p.get('value') is True for p in parameters)):
        raise ValueError('Jenkins has not completed a successful DEPLOY=true release')
    release = read_json(job + '/artifact/.ci-output/release.json', netrc)
    revision = release.get('revision', '')
    if release.get('status') != 'published' or not re.fullmatch(r'[a-f0-9]{40}', revision):
        raise ValueError('Missing published receipt; postponed/verification builds cannot sync')
    target = release.get('target', 'intranet')
    health_urls = {'intranet': HEALTH, 'cloud-118': 'https://198.51.100.10/healthz'}
    if target not in health_urls:
        raise ValueError('Unknown published target')
    selected = next((p.get('value') for p in parameters if p.get('name') == 'DEPLOY_TARGET'), 'intranet')
    if selected != target:
        raise ValueError('Published target does not match build parameters')
    health = read_json(health_urls[target])
    if (health.get('status') != 'ok' or health.get('revision') != revision
            or (release.get('health') or {}).get('revision') != revision
            or health.get('version') != (release.get('health') or {}).get('version')):
        raise ValueError('The live version does not match this published release')
    command('git', 'fetch', '--no-tags', SOURCE, 'refs/heads/main')
    command('git', 'merge-base', '--is-ancestor', revision, 'FETCH_HEAD')
    previous = remote_head()
    if previous != revision:
        if previous:
            command('git', 'fetch', '--no-tags', GITEE, BRANCH)
            command('git', 'merge-base', '--is-ancestor', previous, revision)
        command('git', 'push', GITEE, revision + ':' + BRANCH)
    if remote_head() != revision:
        raise ValueError('Gitee did not retain the expected published commit')
    return {'status': 'synced', 'repository': 'https://gitee.com/Code_Warrior/api-test-workspace',
            'branch': 'main', 'revision': revision, 'version': health['version'], 'jenkins_build': build}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', required=True, type=int, help='Successful deploy-main build number')
    parser.add_argument('--netrc', type=Path, default=Path.home() / '.config/jenkins/credentials')
    args = parser.parse_args()
    if args.build <= 0:
        parser.error('--build must be positive')
    print(json.dumps(sync(args.build, args.netrc), ensure_ascii=False))
