"""Native macOS executor: Seatbelt surrounds the entire App Server process.

The browser, platform bearer, ownership journal and policy files remain outside
the sandbox. Only the pinned Codex and Code Mode helper may execute; their
owned process group is stopped together. Only dynamic broker tools are used.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import socketserver
import subprocess
import threading
from uuid import uuid4

from .codex_appserver import AppServer, ThreadNotFound
from .managed_sandbox import Relay


CONFIG = '''web_search = "disabled"
cli_auth_credentials_store = "file"
[features]
shell_tool = false
unified_exec = false
shell_snapshot = false
# Dynamic tools may be routed through Code Mode by the selected model.
# Keep its host enabled inside the same Seatbelt boundary.
code_mode_host = true
apps = false
computer_use = false
in_app_browser = false
multi_agent = false
'''


def private_json(path, value):
    temporary=path.with_suffix('.new')
    with open(temporary,'w',opener=lambda p,f:os.open(p,f,0o600)) as stream:
        json.dump(value,stream);stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)


class TCPRelay(socketserver.ThreadingTCPServer):
    daemon_threads=True


class MacSandbox:
    def __init__(self, root, auth_file, *, model=None, codex_bin=None):
        self.root=Path(root).resolve()
        self.auth_file=Path(auth_file).expanduser().resolve()
        self.model=model;self.codex_bin=codex_bin;self.proxy=None
        self.process_lock=threading.RLock()

    def _node(self, node_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',node_id):
            raise ValueError('执行节点标识无效')
        return self.root/'nodes'/node_id

    def cwd(self, node_id):return str(self._node(node_id)/'work')

    def _environment(self, node_id):
        state=self._node(node_id)
        proxy=f'http://127.0.0.1:{self.proxy.server_address[1]}'
        # Never inherit global API keys, user MCP configuration, proxy credentials
        # or the parent's CODEX_HOME. Model auth is the one selected file only.
        return {'HOME':str(state),'CFFIXED_USER_HOME':str(state),
                '__CFPREFERENCES_AVOID_DAEMON':'1','CODEX_HOME':str(state),
                'TMPDIR':str(state/'tmp'),'PATH':'/usr/bin:/bin:/usr/sbin:/sbin',
                # Public CA bundle avoids granting access to SecurityServer or
                # the user's Keychain. TLS verification remains enabled.
                'LANG':'en_US.UTF-8','SSL_CERT_FILE':'/private/etc/ssl/cert.pem',
                'HTTPS_PROXY':proxy,'HTTP_PROXY':proxy,
                'ALL_PROXY':proxy,'NO_PROXY':''}

    def _profile(self, node_id):
        state=self._node(node_id);q=lambda p:json.dumps(str(p),ensure_ascii=False)
        port=self.proxy.server_address[1]
        executables=[self.binary,self.tool_host]
        if node_id.startswith('startup-'):
            executables.extend(Path(p) for p in ('/bin/cat','/bin/sh','/bin/bash','/usr/bin/curl'))
        exec_rules=' '.join(f'(literal {q(p)})' for p in executables)
        # Darwin loader exceptions are deliberately separate from user data.
        # No cfprefsd, Keychain, Apple Events, WindowServer, arbitrary local
        # sockets or process-info of another process is allowed.
        return f'''(version 1)
(deny default)
(allow process-fork)
(allow process-exec {exec_rules})
(allow signal (target self))
(allow sysctl-read)
(allow file-read-metadata)
(allow file-read* file-map-executable
  (subpath "/System/Library") (subpath "/usr/lib")
  (subpath "/System/Volumes/Preboot/Cryptexes/OS")
  (subpath "/usr/bin") (subpath "/bin")
  (subpath "/private/etc/ssl") (literal {q(self.binary)}) (literal {q(self.tool_host)}))
(allow file-read* (literal "/") (literal "/dev/random") (literal "/dev/urandom"))
(allow file-read* file-write* (literal "/dev/null") (subpath {q(state)}))
(deny file-write* (literal {q(state/'config.toml')}))
(allow file-read* file-write-data (literal {q(self.auth_file)}))
(allow system-mac-syscall (mac-policy-name "vnguard"))
(allow system-mac-syscall (require-all (mac-policy-name "Sandbox") (mac-syscall-number 67)))
(allow mach-lookup (global-name "com.apple.system.opendirectoryd.libinfo")
                   (global-name "com.apple.system.notification_center"))
(allow ipc-posix-shm-read* (ipc-posix-name "apple.shm.notification_center"))
(allow network-outbound (remote tcp "localhost:{port}"))
'''

    def _configure(self, node_id):
        state=self._node(node_id);state.mkdir(mode=0o700,exist_ok=True)
        for name in ('tmp','work'):(state/name).mkdir(mode=0o700,exist_ok=True)
        config=state/'config.toml'
        if config.is_symlink():raise RuntimeError('隔离配置不能是符号链接')
        config.write_text(CONFIG);config.chmod(0o600)
        auth=state/'auth.json'
        if auth.is_symlink():
            if auth.resolve()!=self.auth_file:raise RuntimeError('模型认证文件绑定已改变')
        elif auth.exists():
            raise RuntimeError('节点存在独立认证副本，不能替换或复制刷新令牌')
        else:auth.symlink_to(self.auth_file)
        policy=self.root/'policies'/f'{node_id}.sb'
        policy.write_text(self._profile(node_id));policy.chmod(0o600)
        return policy

    def _command(self, node_id, command):
        return ['/usr/bin/sandbox-exec','-f',str(self.root/'policies'/f'{node_id}.sb'),*command]

    def _probe(self, node_id, command):
        return subprocess.run(self._command(node_id,command),cwd=self.cwd(node_id),
            env=self._environment(node_id),stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,timeout=10)

    def prepare(self):
        if os.uname().sysname!='Darwin' or not Path('/usr/bin/sandbox-exec').is_file():
            raise RuntimeError('此后端需要 macOS Seatbelt；不会降级为无隔离运行')
        if not self.auth_file.is_file():
            raise RuntimeError('请先登录 Codex，并用 --codex-auth 指定 auth.json')
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.root.chmod(0o700)
        for name in ('nodes','policies','processes'):
            (self.root/name).mkdir(mode=0o700,exist_ok=True)
        selected=self.codex_bin or next((p for p in (
            '/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex',
            '/Applications/Codex.app/Contents/Resources/codex',shutil.which('codex')) if p and Path(p).is_file()),None)
        if not selected:raise RuntimeError('未找到 Codex；请用 --codex-bin 指定本机原生 Codex 二进制')
        source=Path(selected).expanduser().resolve()
        with source.open('rb') as stream:
            if stream.read(4) not in (b'\xcf\xfa\xed\xfe',b'\xce\xfa\xed\xfe',b'\xca\xfe\xba\xbe',b'\xca\xfe\xba\xbf'):
                raise RuntimeError('--codex-bin 必须是 macOS 原生可执行文件，不能是 shell/npm 启动脚本')
            stream.seek(0);fingerprint=hashlib.file_digest(stream,'sha256').hexdigest()
        # Keep Apple's installed signed executable in place. Copying a nested
        # app executable outside its signed bundle can be killed by macOS.
        # Pin its digest for this runner lifetime, rejecting an app update until
        # the runner restarts and revalidates the new version.
        self.binary=source;self.fingerprint=fingerprint
        candidates=[source.parent/'codex-code-mode-host',source.parents[3]/'bin/codex-code-mode-host']
        self.tool_host=next((p.resolve() for p in candidates if p.is_file()),None)
        if self.tool_host is None:raise RuntimeError('缺少配套 Code Mode 宿主，无法执行动态工具')
        with self.tool_host.open('rb') as stream:
            self.tool_host_fingerprint=hashlib.file_digest(stream,'sha256').hexdigest()
        self.proxy=TCPRelay(('127.0.0.1',0),Relay)
        self.proxy.allowed={'api.openai.com','chatgpt.com','auth.openai.com'}
        threading.Thread(target=self.proxy.serve_forever,daemon=True,name='managed-inference-relay').start()
        node_id='startup-'+uuid4().hex
        sentinel=self.root/('private-'+uuid4().hex)
        try:
            self._configure(node_id)
            state=self._node(node_id)
            sentinel.write_text('private');sentinel.chmod(0o600)
            # A positive read establishes that the probe executable really ran.
            if self._probe(node_id,['/bin/cat',str(state/'config.toml')]).returncode!=0:
                raise RuntimeError('macOS 隔离进程未能启动')
            if self._probe(node_id,['/bin/cat',str(sentinel)]).returncode==0:
                raise RuntimeError('macOS 私有文件隔离自检失败')
            if self._probe(node_id,['/bin/sh','-c','/bin/sleep 0.1 & wait $!']).returncode==0:
                raise RuntimeError('macOS 未授权子进程隔离自检失败')
            helper=self._probe(node_id,['/bin/sh','-c','"$1" --help & wait $!','probe',str(self.tool_host)])
            if helper.returncode!=0 or b'codex-code-mode-host' not in helper.stdout:
                raise RuntimeError('Code Mode 辅助进程未能在隔离内启动')
            with socket.socket() as blocked:
                blocked.bind(('127.0.0.1',0));blocked.listen(1)
                url=f'http://127.0.0.1:{blocked.getsockname()[1]}/'
                result=self._probe(node_id,['/usr/bin/curl','--noproxy','*','--connect-timeout','2','--max-time','3','--fail',url])
                blocked.settimeout(.1)
                try:
                    connection,_=blocked.accept();connection.close()
                    raise RuntimeError('macOS 直接网络隔离自检失败')
                except socket.timeout:pass
                if result.returncode==0:raise RuntimeError('macOS 网络隔离自检失败')
            # This verifies a reachable relay rejects non-model destinations.
            result=self._probe(node_id,['/usr/bin/curl','--max-time','3','--fail','--write-out','%{http_connect}','https://forbidden.invalid/'])
            if result.returncode not in (22,56) or result.stdout!=b'403':
                raise RuntimeError('macOS 推理出口自检失败')
            server=self.open(node_id)
            try:
                server.check_auth()
                thread_id=server.start_thread(cwd=self.cwd(node_id),model=self.model,tools=[{
                    'name':'startup_probe','description':'Startup protocol probe; no model turn.',
                    'inputSchema':{'type':'object','properties':{}}}])
            finally:
                server.close();self.stop(node_id)
            server=self.open(node_id)
            try:
                try:
                    server.resume_thread(thread_id)
                except ThreadNotFound:
                    # Codex can defer persistence until its first turn. This
                    # probe never requested a turn, so an empty replacement is
                    # safe. Production requires the persisted runner journal too.
                    server.start_thread(cwd=self.cwd(node_id),model=self.model,tools=[])
            finally:
                server.close();self.stop(node_id)
        except BaseException:
            self.close();raise
        finally:
            sentinel.unlink(missing_ok=True)
            shutil.rmtree(self._node(node_id),ignore_errors=True)
            (self.root/'policies'/f'{node_id}.sb').unlink(missing_ok=True)
        return {'network_isolation':'macOS Seatbelt: exact loopback inference relay only',
                'credential_isolation':'explicit model-auth file only; private browser and platform token denied',
                'tool_gate':'server lease + Playwright request gate; pinned executables + owned process group',
                'browser_context_isolation':'independent context per lease/account',
                'version':'managed-macos-v1:'+fingerprint}

    def open(self, node_id):
        import psutil
        with self.process_lock:
            self.stop(node_id)
            with self.binary.open('rb') as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest()!=self.fingerprint:
                    raise RuntimeError('Codex 已更新；请重启执行连接，重新核验后续接')
            with self.tool_host.open('rb') as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest()!=self.tool_host_fingerprint:
                    raise RuntimeError('Code Mode 宿主已更新；请重启执行连接重新核验')
            binary_stat=self.binary.stat()
            self._configure(node_id)
            def remember(process):
                private_json(self.root/'processes'/f'{node_id}.json',{
                    'pid':process.pid,'created':psutil.Process(process.pid).create_time(),
                    'node_id':node_id,'binary':str(self.binary),'pgid':os.getpgid(process.pid)})
                after=self.binary.stat()
                if (after.st_ino,after.st_size,after.st_mtime_ns)!=(binary_stat.st_ino,binary_stat.st_size,binary_stat.st_mtime_ns):
                    raise RuntimeError('Codex 在启动过程中更新，请重启执行连接')
            return AppServer(self._command(node_id,[str(self.binary),'app-server']),
                cwd=self.cwd(node_id),env=self._environment(node_id),on_spawn=remember,start_new_session=True)

    def stop(self, node_id):
        import psutil
        self._node(node_id)
        with self.process_lock:
            path=self.root/'processes'/f'{node_id}.json'
            if not path.exists():return
            record=json.loads(path.read_text())
            if record['node_id']!=node_id:raise RuntimeError('执行进程归属不符')
            try:
                leader=psutil.Process(record['pid'])
                if leader.create_time()!=record['created']:
                    path.unlink();return  # PID was reused, never touch its group.
            except psutil.NoSuchProcess:leader=None
            if record.get('pgid')==record['pid']:
                members=[]
                for candidate in psutil.process_iter(['pid','create_time']):
                    try:
                        if (os.getpgid(candidate.pid)==record['pgid'] and
                                os.getsid(candidate.pid)==record['pgid'] and
                                candidate.create_time()>=record['created']):
                            members.append(candidate)
                    except (ProcessLookupError,PermissionError,psutil.NoSuchProcess):pass
                if members:
                    try:os.killpg(record['pgid'],signal.SIGTERM)
                    except ProcessLookupError:pass
                    _,alive=psutil.wait_procs(members,timeout=5)
                    for process in alive:
                        try:process.kill()
                        except psutil.NoSuchProcess:pass
                    _,alive=psutil.wait_procs(alive,timeout=5)
                    if alive:raise RuntimeError('受控执行进程组尚未退出，不能释放现场')
            elif leader is not None:
                # Pre-process-group journals remain readable during upgrades.
                leader.terminate()
                try:leader.wait(timeout=5)
                except psutil.TimeoutExpired:
                    leader.kill();leader.wait(timeout=5)
            path.unlink()

    def close(self):
        try:
            for path in (self.root/'processes').glob('*.json'):self.stop(path.stem)
        finally:
            if self.proxy:
                self.proxy.shutdown();self.proxy.server_close();self.proxy=None
