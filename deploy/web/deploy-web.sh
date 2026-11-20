#!/usr/bin/env bash
# Packages only the application and its explicit source-evidence dependencies.
# Never run with shell tracing: deployment deliberately keeps secrets off stdout.
set -euo pipefail

usage() {
  echo 'Usage: deploy-web.sh REPOSITORY [--package-only OUTPUT.tar.gz]' >&2
  exit 2
}
[[ $# == 1 || $# == 3 ]] || usage
if [[ $# == 3 && "$2" != '--package-only' ]]; then usage; fi
COMPONENT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPOSITORY="$(cd "$1" && pwd)"
WEB_PYTHON="${WEB_DEPLOY_PYTHON:-python3}"
STAGING="$(mktemp -d "${TMPDIR:-/tmp}/api-test-web-package.XXXXXXXX")"
trap 'rm -rf "$STAGING"' EXIT

"$WEB_PYTHON" - "$REPOSITORY" "$COMPONENT_DIR" "$STAGING" <<'PY'
import hashlib
import json
import shutil
import sys
from pathlib import Path

repo, components, staging = map(Path, sys.argv[1:])
required = ['pyproject.toml', 'README.md', 'api_test_tool/static/index.html',
            'api_test_tool/web.py', 'tests/fixtures/items_server.py',
            'examples/gomoku/evidence/assertions.md', 'examples/gomoku/rules.yaml',
            'examples/items/openapi.yaml', 'examples/gomoku/evidence/接口文档.md', 'examples/gomoku/evidence/info_cases.yaml']
missing = [name for name in required if not (repo / name).is_file()]
if missing:
    raise SystemExit('Application package is incomplete: ' + ', '.join(missing))
source = staging / 'source'
source.mkdir()
ignored = shutil.ignore_patterns('.git', '.venv', '__pycache__', '*.pyc',
    '.env', '.env.*', 'master.key', '*.pem', '*.key', 'node_modules',
    'reports', 'outputs', 'work', '.pytest_cache', '.DS_Store')
for name in ['api_test_tool', 'docs', 'examples', 'tests']:
    origin = repo / name
    if any(path.is_symlink() for path in origin.rglob('*')):
        raise SystemExit('Do not package symlinks inside application directories: ' + name)
    shutil.copytree(origin, source / name, ignore=ignored)
for name in ['pyproject.toml', 'README.md', 'README_MVP.md', 'README_WEB.md', 'README_MCP.md', 'pytest.ini', 'conftest.py', 'LICENSE']:
    if (repo / name).is_file():
        shutil.copy2(repo / name, source / name)
for name in ['Dockerfile', 'compose.yaml', '.dockerignore', 'requirements-web.lock', 'requirements-browser.lock', 'requirements-postgres.lock', 'install-browser.py', 'README_WEB.md']:
    shutil.copy2(components / name, staging / name)
manifest = {str(path.relative_to(staging)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(staging.rglob('*')) if path.is_file()}
(staging / 'manifest.sha256.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
PY

"$WEB_PYTHON" - "$STAGING" <<'PY'
import sys
import tarfile
from pathlib import Path
staging = Path(sys.argv[1])
with tarfile.open(staging / 'incoming.tar.gz', 'w:gz') as archive:
    for name in ['source', 'Dockerfile', 'compose.yaml', '.dockerignore', 'requirements-web.lock', 'requirements-browser.lock', 'requirements-postgres.lock', 'install-browser.py', 'README_WEB.md', 'manifest.sha256.json']:
        archive.add(staging / name, arcname=name)
PY
if [[ $# == 3 ]]; then
  cp "$STAGING/incoming.tar.gz" "$3"
  echo "Deployment package created: $3"
  exit 0
fi

IDENTITY="$HOME/.ssh/gpt_ed25519"
[[ -f "$IDENTITY" ]] || { echo 'Deployment SSH identity is unavailable.' >&2; exit 1; }
SSH=(ssh -i "$IDENTITY" -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=8)
SCP=(scp -i "$IDENTITY" -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=8)
TARGET='veriq@192.0.2.20'
"${SSH[@]}" "$TARGET" 'mkdir -p /home/veriq/apps/api-test-web && chmod 700 /home/veriq/apps/api-test-web'
"${SCP[@]}" "$STAGING/incoming.tar.gz" "$TARGET:/home/veriq/apps/api-test-web/incoming.tar.gz"

"${SSH[@]}" "$TARGET" bash -s <<'REMOTE'
set -euo pipefail
umask 077
cd /home/veriq/apps/api-test-web
docker network inspect ai-api-gomoku_backend --format '{{.Name}}' >/dev/null
tar -xzf incoming.tar.gz --no-same-owner
python3 - <<'PY'
import json
import os
import re
import secrets
import subprocess
import tempfile
from pathlib import Path

root = Path('/home/veriq/apps/api-test-web')
env_file = root / '.env'
if env_file.exists():
    settings = dict(line.split('=', 1) for line in env_file.read_text().splitlines()
                    if line and not line.startswith('#') and '=' in line)
    password = settings.get('GOMOKU_CLEANUP_PASSWORD', '')
    if not re.fullmatch(r'[a-f0-9]{64}', password):
        raise SystemExit('Existing cleanup credential is not owned by this deployment script; preserve it and deploy manually.')
    os.chmod(env_file, 0o600)
else:
    password = secrets.token_hex(32)
    settings = {'BIND_ADDRESS': '192.0.2.20', 'WEB_PORT': '18089',
                'GOMOKU_CLEANUP_PASSWORD': password}
    descriptor, temporary = tempfile.mkstemp(prefix='.env-pending-', dir=root)
    with os.fdopen(descriptor, 'w') as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(''.join(key + '=' + value + '\n' for key, value in settings.items()))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, env_file)

# The account is dedicated to this app and can access only its test table.
# SQL goes to stdin; neither passwords nor SQL are printed or stored in a file.
sql = ("CREATE USER IF NOT EXISTS 'gomoku_web_cleanup'@'%' IDENTIFIED BY '" + password + "';\n"
       "ALTER USER 'gomoku_web_cleanup'@'%' IDENTIFIED BY '" + password + "';\n"
       "REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'gomoku_web_cleanup'@'%';\n"
       "GRANT SELECT, DELETE ON `gomoku_api_test`.`user` TO 'gomoku_web_cleanup'@'%';\n")
command = ['docker', 'compose', '--env-file', '/home/veriq/apps/ai-api-gomoku/.env',
           '-f', '/home/veriq/apps/ai-api-gomoku/compose.yaml',
           '--project-directory', '/home/veriq/apps/ai-api-gomoku', 'exec', '-T', 'db',
           'sh', '-c', 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; exec mysql -uroot --batch --skip-column-names']
completed = subprocess.run(command, input=sql, text=True, capture_output=True, timeout=30)
if completed.returncode:
    raise SystemExit('Unable to configure the dedicated cleanup account. Inspect MySQL locally; no credentials were printed.')
print('Dedicated cleanup account configured with SELECT/DELETE on gomoku_api_test.user.')
PY
docker compose config --quiet
docker compose build --pull
docker compose up -d --wait --wait-timeout 120
docker compose ps
python3 - <<'PY'
import json
import urllib.request
with urllib.request.urlopen('http://192.0.2.20:18089/healthz', timeout=5) as response:
    health = json.load(response)
if health.get('status') != 'ok':
    raise SystemExit('Web application health verification failed.')
print('Ready: http://192.0.2.20:18089')
PY
REMOTE
