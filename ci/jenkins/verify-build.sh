#!/usr/bin/env bash
set -euo pipefail
revision=${1:?full commit required}
[[ "$revision" =~ ^[a-f0-9]{40}$ ]] || exit 2
[[ "$(git rev-parse HEAD)" == "$revision" ]] || exit 2
root=${API_TEST_CI_ROOT:?}
mode=${API_TEST_CHECK_MODE:-release}
[[ "$mode" == release || "$mode" == full ]] || { echo 'Check mode must be release or full.' >&2; exit 2; }
mkdir -p .ci-output
# Never reuse verification evidence or test reports from an earlier attempt.
rm -f .ci-output/verified-sha.txt .ci-output/image-id.txt .ci-output/unit.xml
printf '%s\n' "$mode" > .ci-output/check-mode.txt
test_container="api-test-ci-${revision:0:12}"
smoke_container="api-test-smoke-${revision:0:12}"
postgres_container="api-test-pg-${revision:0:12}"
smoke_network="api-test-smoke-net-${revision:0:12}"
postgres_secrets=''
cleanup() {
  docker rm -f "$test_container" "$smoke_container" "$postgres_container" >/dev/null 2>&1 || true
  docker network rm "$smoke_network" >/dev/null 2>&1 || true
  if [[ -n "$postgres_secrets" ]]; then rm -rf -- "$postgres_secrets"; fi
  docker buildx stop api-test-workspace >/dev/null 2>&1 || true
}
trap cleanup EXIT
trap 'exit 130' INT TERM

# The systemd agent cgroup limits npm and its child processes to 2 CPU / 4 GiB.
(cd frontend/background && npm ci --ignore-scripts --no-audit --no-fund && npm run build)
(cd frontend/spark-background && npm ci --ignore-scripts --no-audit --no-fund && npm run build)
(cd frontend/login-background && npm ci --ignore-scripts --no-audit --no-fund && npm run build)
(cd frontend/home-water && npm ci --ignore-scripts --no-audit --no-fund && npm run build)
(cd frontend/home-induction && npm ci --ignore-scripts --no-audit --no-fund && npm run build)
if [[ "$mode" == full ]]; then
  node --test tests/js/*.test.cjs tests/unit/test_web_ui_state.mjs
else
  echo 'Release mode: full JS/Python regression and verification image are omitted.'
fi
bash deploy/web/deploy-web.sh "$PWD" --package-only "$PWD/.ci-output/source.tar.gz"
mkdir -p .ci-output/image
tar -xzf .ci-output/source.tar.gz -C .ci-output/image
python3 - <<'PY'
from pathlib import Path
import os
import shutil
p = Path('.ci-output/image/Dockerfile')
s = p.read_text()
base = next(line for line in s.splitlines() if line.startswith('FROM python:3.13-slim'))
s = s.replace(base, base + ' AS runtime', 1)
if os.environ.get('API_TEST_CHECK_MODE', 'release') == 'full':
    shutil.copy2('ci/jenkins/requirements-verification.lock', '.ci-output/image/')
    s += '''\nFROM runtime AS verification
USER 0
RUN apt-get update && apt-get install -y --no-install-recommends nodejs && rm -rf /var/lib/apt/lists/*
COPY requirements-verification.lock /tmp/requirements-verification.lock
RUN pip install --no-cache-dir --no-deps -r /tmp/requirements-verification.lock && pip check
USER 10001:10001
'''
p.write_text(s)
PY
docker buildx build --builder api-test-workspace --load \
  --target runtime \
  --label "org.opencontainers.image.revision=$revision" \
  --tag "api-test-web:git-$revision" .ci-output/image

# The runtime now requires PostgreSQL. This build-only internal network has no
# published database port, no business network and no outbound connectivity.
postgres_image="$(python3 ci/jenkins/postgres_runtime.py image)"
docker pull "$postgres_image"
postgres_secrets="$(mktemp -d "${TMPDIR:-/tmp}/api-test-ci-pg.XXXXXXXX")"
python3 ci/jenkins/postgres_runtime.py secrets "$postgres_secrets" "api-test-web:git-$revision"
docker network create --internal "$smoke_network" >/dev/null
docker run -d --name "$postgres_container" --network "$smoke_network" \
  --cpus 1 --memory 512m --pids-limit 128 --read-only \
  --tmpfs /var/lib/postgresql/data:rw,nosuid,size=512m \
  --tmpfs /var/run/postgresql:rw,nosuid,size=16m --tmpfs /tmp:rw,nosuid,size=16m \
  --mount "type=bind,source=$postgres_secrets/postgres-admin.runtime,target=/run/secrets/veriq_admin_password,readonly" \
  -e POSTGRES_PASSWORD_FILE=/run/secrets/veriq_admin_password "$postgres_image" >/dev/null
postgres_ready=false
for attempt in {1..60}; do
  if docker exec "$postgres_container" pg_isready -h 127.0.0.1 -U postgres -d postgres >/dev/null 2>&1; then
    postgres_ready=true
    break
  fi
  sleep 1
done
[[ "$postgres_ready" == true ]] || { echo 'Isolated PostgreSQL startup failed.' >&2; exit 1; }
python3 ci/jenkins/postgres_runtime.py role "$postgres_container" "$postgres_secrets/postgres-app.password"
storage_command() {
  docker run --rm --network "$smoke_network" --read-only --cpus 1 --memory 512m --pids-limit 64 \
    --tmpfs /tmp:rw,nosuid,size=64m --tmpfs /data:rw,nosuid,size=64m,uid=10001,gid=10001 \
    --cap-drop ALL --security-opt no-new-privileges:true \
    --mount "type=bind,source=$postgres_secrets/postgres-app.runtime,target=/run/secrets/veriq_app_password,readonly" \
    -e "API_TEST_DB_HOST=$postgres_container" -e API_TEST_DB_NAME=veriq -e API_TEST_DB_USER=veriq \
    -e API_TEST_DB_PASSWORD_FILE=/run/secrets/veriq_app_password \
    "api-test-web:git-$revision" python -m api_test_tool.storage_migrate "$@"
}
if [[ "$mode" == full ]]; then
docker buildx build --builder api-test-workspace --load --target verification \
  --tag "api-test-verify:git-$revision" .ci-output/image

# The full suite reaches only this build's internal PostgreSQL service.
# CREATEDB is scoped to the disposable instance for per-test database isolation.
docker exec --user postgres "$postgres_container" psql -X -U postgres -d postgres \
  --quiet -v ON_ERROR_STOP=1 -c 'ALTER ROLE veriq CREATEDB' >/dev/null
chmod -R a+rX ci
mkdir -p .ci-output/test-results
chmod 777 .ci-output/test-results
test_status=0
docker run --name "$test_container" --network "$smoke_network" --cpus 2 --memory 4g --pids-limit 256 \
  --read-only --tmpfs /tmp:rw,nosuid,size=512m --tmpfs /data:rw,nosuid,size=256m,uid=10001,gid=10001 \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --mount "type=bind,source=$PWD/ci,target=/app/ci,readonly" \
  --mount "type=bind,source=$postgres_secrets/postgres-app.runtime,target=/run/secrets/veriq_app_password,readonly" \
  -e "API_TEST_DB_HOST=$postgres_container" -e API_TEST_DB_NAME=veriq -e API_TEST_DB_USER=veriq \
  -e API_TEST_DB_PASSWORD_FILE=/run/secrets/veriq_app_password \
  --mount "type=bind,source=$PWD/.ci-output/test-results,target=/test-results" \
  "api-test-verify:git-$revision" \
  python -m pytest tests/unit -q -p no:cacheprovider --junitxml=/test-results/unit.xml || test_status=$?
docker exec --user postgres "$postgres_container" psql -X -U postgres -d postgres \
  --quiet -v ON_ERROR_STOP=1 -c 'ALTER ROLE veriq NOCREATEDB' >/dev/null
cp .ci-output/test-results/unit.xml .ci-output/unit.xml
[[ "$test_status" == 0 ]] || exit "$test_status"
python3 - <<'PY'
import xml.etree.ElementTree as ET
root = ET.parse('.ci-output/unit.xml').getroot()
skipped = [case.get('name') for case in root.iter('testcase') if case.find('skipped') is not None]
if skipped:
    raise SystemExit('Release checks must not silently skip tests: ' + ', '.join(skipped))
PY
fi


storage_command import-sqlite --allow-empty
storage_command verify
storage_command activate --revision "$revision"
docker run -d --name "$smoke_container" --network "$smoke_network" --cpus 1 --memory 1g --pids-limit 128 \
  --read-only --tmpfs /tmp:rw,nosuid,size=256m --tmpfs /data:rw,nosuid,size=256m,uid=10001,gid=10001 \
  --cap-drop ALL --security-opt no-new-privileges:true -e "API_TEST_REVISION=$revision" \
  --mount "type=bind,source=$postgres_secrets/postgres-app.runtime,target=/run/secrets/veriq_app_password,readonly" \
  -e "API_TEST_DB_HOST=$postgres_container" -e API_TEST_DB_NAME=veriq -e API_TEST_DB_USER=veriq \
  -e API_TEST_DB_PASSWORD_FILE=/run/secrets/veriq_app_password \
  "api-test-web:git-$revision" >/dev/null
python3 ci/jenkins/smoke.py "$smoke_container" "$revision"
docker exec "$smoke_container" python -c "import json,urllib.request; s=json.load(urllib.request.urlopen('http://127.0.0.1:18089/healthz',timeout=3))['storage']; assert s['backend']=='postgresql' and s['schema']==1 and s['activation']=='active' and s['verified'] is True"
docker image inspect "api-test-web:git-$revision" --format '{{.Id}}' > .ci-output/image-id.txt
printf '%s\n' "$revision" > .ci-output/verified-sha.txt
