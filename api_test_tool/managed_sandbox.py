"""Docker isolation and an allowlisted TLS CONNECT relay, outside model control."""
from __future__ import annotations
import json
import os
from pathlib import Path
import select
import socket
import socketserver
import subprocess
import threading

from .codex_appserver import AppServer

class Relay(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            self.connection.settimeout(30)
            first=self.rfile.readline(4097).decode('ascii').strip().split()
            if len(first)!=3 or first[0]!='CONNECT':
                raise ValueError('CONNECT required')
            target=first[1].split(':')
            if len(target)!=2 or target[1]!='443' or target[0] not in self.server.allowed:
                raise ValueError('Unapproved inference endpoint')
            size=0
            while True:
                line=self.rfile.readline(4097);size+=len(line)
                if size>16384 or not line:
                    raise ValueError('Invalid proxy headers')
                if line in (b'\r\n',b'\n'):
                    break
            with socket.create_connection((target[0],443),timeout=20) as upstream:
                upstream.settimeout(180)
                self.connection.settimeout(180)
                self.connection.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
                while True:
                    ready,_,_=select.select([self.connection,upstream],[],[],60)
                    if not ready:
                        continue
                    for source in ready:
                        data=source.recv(65536)
                        if not data:return
                        (upstream if source is self.connection else self.connection).sendall(data)
        except Exception:
            # No raw headers, tokens, model messages or upstream errors in logs.
            try:self.connection.sendall(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n')
            except OSError:pass

class UnixServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads=True

class Sandbox:
    def __init__(self, root, image, auth_file, *, model=None):
        self.root=Path(root).resolve();self.image=image;self.auth_file=Path(auth_file).expanduser().resolve();self.model=model
        self.proxy=None

    def prepare(self):
        if not self.auth_file.is_file():
            raise RuntimeError('请用 --codex-auth 指定已登录 Codex 的 auth.json；不读取业务账号或其他聊天')
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        if os.uname().sysname!='Linux':
            raise RuntimeError('Docker 后端要求同机 Linux；macOS 请使用 --backend macos，不能降级为无隔离运行')
        info=json.loads(subprocess.check_output(['docker','info','--format','{{json .}}'],stderr=subprocess.DEVNULL))
        self.container_user='0:0' if any('rootless' in x for x in info.get('SecurityOptions',[])) else f'{os.getuid()}:{os.getgid()}'
        # No paid call. Verify the exact local image before accepting platform work.
        inspected=json.loads(subprocess.check_output(['docker','image','inspect',self.image],stderr=subprocess.DEVNULL))[0]
        self.image=inspected['Id']
        directory=self.root/'egress';directory.mkdir(mode=0o700,exist_ok=True)
        sock=directory/'proxy.sock'
        if sock.exists():sock.unlink()
        self.proxy=UnixServer(str(sock),Relay)
        self.proxy.allowed={'api.openai.com','chatgpt.com','auth.openai.com'}
        sock.chmod(0o600)
        threading.Thread(target=self.proxy.serve_forever,daemon=True).start()
        probe='import socket; s=socket.socket(); s.settimeout(1); result=s.connect_ex(("192.0.2.1",443)); assert result != 0; s.close(); u=socket.socket(socket.AF_UNIX); u.connect("/egress/proxy.sock"); u.sendall(b"CONNECT forbidden.invalid:443 HTTP/1.1\\r\\n\\r\\n"); assert b"403" in u.recv(1024); u.close()'
        subprocess.run(['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
            '--user',self.container_user,'--mount',f'type=bind,src={directory},dst=/egress,readonly','--entrypoint','python3',self.image,'-c',probe],
            check=True,timeout=30,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return {'network_isolation':'docker network=none + exact TLS inference relay',
                'credential_isolation':'only explicit shared model-auth file; browser and host token never mounted',
                'tool_gate':'server lease + Playwright request gate',
                'browser_context_isolation':'persistent context per node/account',
                'version':'managed-v2:'+self.image}

    def name(self, node_id):return 'api-test-codex-'+node_id

    def cwd(self, node_id):return '/work'

    def stop(self, node_id):
        name=self.name(node_id)
        proc=subprocess.run(['docker','inspect',name],capture_output=True,text=True)
        if proc.returncode:
            # Distinguish absent container from a lost Docker daemon.
            subprocess.run(['docker','info','--format','{{.ServerVersion}}'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            return
        item=json.loads(proc.stdout)[0]
        if item['Config'].get('Labels',{}).get('api-test-node')!=node_id:
            raise RuntimeError('执行容器归属不符')
        subprocess.run(['docker','rm','-f',name],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

    def open(self, node_id):
        self.stop(node_id)  # Fence any old process before resume; never two executors.
        state=self.root/node_id;state.mkdir(mode=0o700,exist_ok=True)
        # All module processes use the same explicitly selected model-auth file.
        # Copying OAuth refresh tokens per module would create stale refresh races.
        (state/'config.toml').write_text('web_search = "disabled"\ncli_auth_credentials_store = "file"\n')
        (state/'config.toml').chmod(0o600)
        command=['docker','run','--rm','-i','--name',self.name(node_id),'--label','api-test-node='+node_id,
                 '--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
                 '--pids-limit','256','--memory','2g','--cpus','2','--user',self.container_user,
                 '--tmpfs','/tmp:rw,noexec,nosuid,size=128m','--tmpfs','/work:rw,nosuid,size=64m',
                 '--mount',f'type=bind,src={state},dst=/state',
                 '--mount',f'type=bind,src={self.auth_file},dst=/state/auth.json',
                 '--mount',f'type=bind,src={self.root / "egress"},dst=/egress,readonly',self.image]
        return AppServer(command,cwd=self.root,env=os.environ.copy())

    def close(self):
        if self.proxy:self.proxy.shutdown();self.proxy.server_close()


def create_sandbox(root, image, auth_file, *, model=None, backend='auto', codex_bin=None):
    if backend=='auto':
        backend='macos' if os.uname().sysname=='Darwin' else 'docker'
    if backend=='macos':
        from .managed_macos import MacSandbox
        return MacSandbox(root, auth_file, model=model, codex_bin=codex_bin)
    return Sandbox(root, image, auth_file, model=model)
