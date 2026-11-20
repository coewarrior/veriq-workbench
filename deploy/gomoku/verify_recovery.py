"""Run on the deployment host. Probes a temporary API container, never the live connection."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time

API = 'ai-api-gomoku-api-1'
DB = 'ai-api-gomoku-db-1'
NETWORK = 'ai-api-gomoku_backend'
IMAGE = 'ai-api-gomoku:33a90e4-env2'
NAME = 'gomoku-recovery-' + secrets.token_hex(5)
PREFIX = 'mvp_recovery_' + secrets.token_hex(8)
checks = []
owned = []
cookie = ''


def command(args, **kwargs):
    return subprocess.run(args, text=True, check=True, capture_output=True, **kwargs).stdout


def sql(statement):
    return command(['docker', 'exec', '-i', DB, 'sh', '-c',
                    'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot --batch --skip-column-names'],
                   input=statement + '\n').strip()


def request(label, method, path, payload=None, expected=200, reason=None, identity=None):
    global cookie
    args = ['docker', 'exec', '-i', NAME, 'curl', '-si', '--max-time', '20',
            '-X', method, 'http://127.0.0.1:8081' + path]
    if cookie:
        args += ['-H', 'Cookie: ' + cookie]
    if payload is not None:
        args += ['-H', 'Content-Type: application/json', '--data-binary', '@-']
    raw = command(args, input=json.dumps(payload) if payload is not None else '')
    headers, body = raw.replace('\r\n', '\n').split('\n\n', 1)
    status = int(headers.splitlines()[0].split()[1])
    for line in headers.splitlines():
        if line.lower().startswith('set-cookie:'):
            cookie = line.split(':', 1)[1].strip().split(';', 1)[0]
    data = json.loads(body)
    passed = status == expected and (reason is None or data.get('reason') == reason)
    if identity is not None:
        passed = passed and data.get('username') == identity
    checks.append({'name': label, 'status': status, 'passed': passed})
    assert passed, (label, status, data.get('reason'))
    return data


def interrupt_probe_connection():
    network = json.loads(command(['docker', 'inspect', NAME]))[0]['NetworkSettings']['Networks'][NETWORK]
    ip = network['IPAddress']
    # Match only this short-lived container; never kill the deployed API's connection.
    ids = sql("SELECT ID FROM information_schema.PROCESSLIST WHERE USER='gomoku_app' "
              "AND DB='gomoku_api_test' AND SUBSTRING_INDEX(HOST, ':', 1)='" + ip + "';").splitlines()
    assert len(ids) == 1 and ids[0].isdigit(), 'Expected exactly one probe DB connection'
    sql('KILL CONNECTION ' + ids[0] + ';')


def account(suffix):
    name = PREFIX + suffix
    owned.append(name)
    return {'username': name, 'password': secrets.token_hex(16)}


try:
    env = json.loads(command(['docker', 'inspect', API]))[0]['Config']['Env']
    with tempfile.NamedTemporaryFile(mode='w', prefix='gomoku-recovery-env-') as file:
        os.chmod(file.name, 0o600)
        file.write('\n'.join(value for value in env if value.startswith('GOMOKU_')) + '\n')
        file.flush()
        command(['docker', 'run', '-d', '--name', NAME, '--network', NETWORK,
                 '--env-file', file.name, '--read-only', '--tmpfs', '/tmp',
                 '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', IMAGE])
    for _ in range(20):
        try:
            command(['docker', 'exec', NAME, 'curl', '-fsS', '--max-time', '1',
                     'http://127.0.0.1:8081/login.html'])
            break
        except subprocess.CalledProcessError:
            time.sleep(0.25)
    creds = account('_first')
    request('注册新账号', 'POST', '/reg', creds, reason='用户注册成功！')
    request('正常登录', 'POST', '/login', creds, reason='用户登录成功！')
    assert cookie.startswith('SSID=')
    request('读取本人信息', 'GET', '/info', identity=creds['username'])
    interrupt_probe_connection()
    request('数据库连接失效后首次登录自动恢复', 'POST', '/login', creds, reason='用户登录成功！')
    request('恢复后信息与账号一致', 'GET', '/info', identity=creds['username'])
    interrupt_probe_connection()
    request('数据库连接失效后首次注册自动恢复', 'POST', '/reg', account('_second'), reason='用户注册成功！')
    request('真实重复账号仍返回业务错误', 'POST', '/reg', creds, expected=400, reason='用户名已被占用！')
    request('真实密码错误仍返回业务错误', 'POST', '/login', {**creds, 'password': 'wrong'},
            expected=400, reason='账号/密码错误!')
    command(['docker', 'network', 'disconnect', NETWORK, NAME])
    for method, path, payload in [('POST', '/login', creds), ('POST', '/reg', account('_offline')), ('GET', '/info', None)]:
        request('数据库不可达时' + path + '准确返回503', method, path, payload,
                expected=503, reason='数据库暂不可用，请稍后重试')
    command(['docker', 'network', 'connect', NETWORK, NAME])
    request('数据库恢复后无需重启即可登录', 'POST', '/login', creds, reason='用户登录成功！')
    request('数据库恢复后读取本人信息', 'GET', '/info', identity=creds['username'])
    request('数据库恢复后注册新账号', 'POST', '/reg', account('_third'), reason='用户注册成功！')
finally:
    subprocess.run(['docker', 'rm', '-f', NAME], capture_output=True)
    if owned:
        names = ','.join("'" + name + "'" for name in owned)
        sql('DELETE FROM gomoku_api_test.user WHERE username IN (' + names + ');')
        remaining = int(sql('SELECT COUNT(*) FROM gomoku_api_test.user WHERE username IN (' + names + ');'))
        checks.append({'name': '只清理本次验证创建的账号', 'remaining': remaining, 'passed': remaining == 0})
    Path('/tmp/gomoku-recovery-verification.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2))
    print(json.dumps(checks, ensure_ascii=False))
