"""Dedicated VERIQ PostgreSQL deployment primitives; never print credentials."""
import base64
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import subprocess


IMAGE = 'postgres:17-bookworm@sha256:858bb5e98eed02eb8cafbcdc007f9a65d1b613972028944a8ec2133ccaf80d27'
SERVICE = 'veriq-postgres'
NETWORK = 'api-test-web_storage'
VOLUME = 'api-test-web_postgres_data'


def extend_override(config, app):
    services = config.setdefault('services', {})
    web = services.setdefault('web', {})
    web.setdefault('environment', {}).update(API_TEST_DB_HOST=SERVICE, API_TEST_DB_PORT='5432',
        API_TEST_DB_NAME='veriq', API_TEST_DB_USER='veriq',
        API_TEST_DB_PASSWORD_FILE='/run/secrets/veriq_app_password')
    networks = web.get('networks', ['gomoku_backend'])
    if isinstance(networks, dict):
        networks.setdefault('veriq_storage', {})
    else:
        networks = list(dict.fromkeys([*networks, 'veriq_storage']))
    web['networks'] = networks
    existing = web.setdefault('secrets', [])
    if not any((value if isinstance(value, str) else value.get('source')) == 'veriq_app_password'
               for value in existing):
        existing.append('veriq_app_password')
    services[SERVICE] = {
        'image': IMAGE, 'restart': 'unless-stopped',
        'environment': {'POSTGRES_PASSWORD_FILE': '/run/secrets/veriq_admin_password',
                        'POSTGRES_DB': 'postgres', 'POSTGRES_USER': 'postgres'},
        'volumes': ['veriq_postgres_data:/var/lib/postgresql/data'],
        'networks': ['veriq_storage'],
        'secrets': ['veriq_admin_password'],
        'healthcheck': {'test': ['CMD', 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres', '-d', 'postgres'],
                        'interval': '5s', 'timeout': '3s', 'retries': 12, 'start_period': '10s'},
        'mem_limit': '2g', 'pids_limit': 256, 'stop_grace_period': '5m',
        'logging': {'driver': 'json-file', 'options': {'max-size': '10m', 'max-file': '3'}},
    }
    config.setdefault('networks', {})['veriq_storage'] = {'name': NETWORK, 'internal': True}
    config.setdefault('volumes', {})['veriq_postgres_data'] = {'name': VOLUME}
    for kind in ('admin', 'app'):
        config.setdefault('secrets', {})['veriq_' + kind + '_password'] = {
            'file': str(Path(app) / 'secrets' / ('postgres-' + kind + '.runtime'))}
    return config


def prepare_secrets(directory, runtime_image, *, existing_volume=False):
    directory = Path(directory)
    if directory.is_symlink():
        raise RuntimeError('Refusing symlinked database secret directory')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    paths = [directory / ('postgres-' + kind + '.password') for kind in ('admin', 'app')]
    if existing_volume and any(not path.is_file() for path in paths):
        raise RuntimeError('Existing PostgreSQL volume requires its original credentials')
    for path in paths:
        if path.is_symlink():
            raise RuntimeError('Refusing symlinked database credential')
        if not path.exists():
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w') as handle:
                handle.write(secrets.token_hex(32) + '\n')
                handle.flush()
                os.fsync(handle.fileno())
        path.chmod(0o600)
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    # File-source Compose secrets preserve host ownership, so create explicit
    # read-only projections for the two container UIDs. Source files stay 0600.
    postgres_uid = subprocess.run(['docker', 'run', '--rm', '--network', 'none',
        '--entrypoint', 'id', IMAGE, '-u', 'postgres'], check=True, text=True,
        capture_output=True).stdout.strip()
    if not postgres_uid.isdecimal():
        raise RuntimeError('PostgreSQL image user could not be verified')
    code = '''import os,re
from pathlib import Path
for kind,uid in [('admin',int(os.environ['POSTGRES_UID'])),('app',10001)]:
    source=Path('/secrets')/('postgres-'+kind+'.password')
    value=source.read_text().strip()
    if not re.fullmatch('[a-f0-9]{64}',value):
        raise RuntimeError('Invalid existing database credential format')
    target=source.with_suffix('.runtime')
    temporary=target.with_suffix('.pending')
    if target.is_symlink() or temporary.is_symlink():
        raise RuntimeError('Refusing symlinked credential projection')
    temporary.unlink(missing_ok=True)
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o400)
    with os.fdopen(fd,'w') as handle:
        os.fchmod(handle.fileno(),0o400)
        os.fchown(handle.fileno(),uid,uid)
        handle.write(value+'\\n')
        handle.flush();os.fsync(handle.fileno())
    os.replace(temporary,target)
directory=os.open('/secrets',os.O_RDONLY)
try: os.fsync(directory)
finally: os.close(directory)
'''
    result = subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--read-only',
        '--user', '0', '--cap-drop', 'ALL', '--cap-add', 'CHOWN', '--cap-add', 'DAC_OVERRIDE',
        '--security-opt', 'no-new-privileges:true', '--entrypoint', 'python',
        '--mount', 'type=bind,source=' + str(directory.resolve()) + ',target=/secrets',
        '-e', 'POSTGRES_UID=' + postgres_uid, runtime_image, '-c', code],
        text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError('Database credential projection failed; secret output suppressed')


def scram_verifier(password_file):
    # Match PostgreSQL 17 scram_build_secret (src/common/scram-common.c).
    # Generated passwords are ASCII hex, so SASLprep cannot change them.
    password = Path(password_file).read_text().strip()
    if not re.fullmatch('[a-f0-9]{64}', password):
        raise RuntimeError('Invalid existing database credential format')
    salt = secrets.token_bytes(16)
    iterations = 4096
    salted = hashlib.pbkdf2_hmac('sha256', password.encode('ascii'), salt, iterations)
    client_key = hmac.digest(salted, b'Client Key', 'sha256')
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.digest(salted, b'Server Key', 'sha256')
    encode = lambda value: base64.b64encode(value).decode('ascii')
    return f'SCRAM-SHA-256${iterations}:{encode(salt)}${encode(stored_key)}:{encode(server_key)}'


def provision_role(container, password_file):
    # The app owns only its dedicated database and has no cluster privileges.
    # Only a SCRAM verifier enters SQL, via stdin (never argv or environment).
    # Plaintext remains in the private host file and cannot reach statement or
    # error-statement logs, including when role creation itself fails.
    verifier = scram_verifier(password_file)
    script = r'''SET log_statement = 'none';
SET log_duration = off;
SET log_min_duration_statement = -1;
SET log_min_duration_sample = -1;
SET log_transaction_sample_rate = 0;
SET log_min_error_statement = 'panic';
SELECT format('CREATE ROLE veriq LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD %L', '__VERIFIER__')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='veriq') \gexec
ALTER ROLE veriq NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
SELECT 'CREATE DATABASE veriq OWNER veriq'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname='veriq') \gexec
REVOKE ALL ON DATABASE veriq FROM PUBLIC;
GRANT CONNECT ON DATABASE veriq TO veriq;
'''.replace('__VERIFIER__', verifier)
    result = subprocess.run(['docker', 'exec', '--user', 'postgres', '-i', container,
                            'psql', '-X', '-U', 'postgres', '-d', 'postgres', '--quiet', '-v', 'ON_ERROR_STOP=1'],
                            input=script, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError('Dedicated PostgreSQL role initialization failed; secret output suppressed')


if __name__ == '__main__':
    import sys
    if sys.argv[1:] == ['image']:
        print(IMAGE)
    elif len(sys.argv) == 4 and sys.argv[1] == 'secrets':
        prepare_secrets(sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 4 and sys.argv[1] == 'role':
        provision_role(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit('Expected image, secrets DIRECTORY RUNTIME_IMAGE, or role CONTAINER PASSWORD_FILE')
