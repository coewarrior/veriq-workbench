"""Install the current runner as this user's macOS LaunchAgent, never as root."""
from __future__ import annotations

import os
from pathlib import Path
import plistlib
import subprocess
import sys


LABEL='com.api-test-workspace.managed-runner'


def service(action, root, *, auth_file=None, codex_bin=None, model=None):
    if sys.platform!='darwin':raise RuntimeError('service 命令仅用于 macOS 用户登录会话')
    domain=f'gui/{os.getuid()}'
    target=f'{domain}/{LABEL}'
    plist=Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'
    if action=='status':
        result=subprocess.run(['launchctl','print',target],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        print('服务已加载；连接状态请运行 api-test-runner status' if result.returncode==0 else '服务未加载')
        return
    if action=='stop':
        subprocess.run(['launchctl','bootout',target],check=True)
        print('已请求停止本机执行连接；执行进程退出后交还账号，任务进度保留。')
        return
    if action=='start':
        subprocess.run(['launchctl','bootstrap',domain,str(plist)],check=True)
        print('执行连接服务正在启动。');return
    if plist.exists():
        raise RuntimeError('已有执行连接服务；请先停止并保留原配置，不自动覆盖另一运行目录')
    if not (root/'connection.json').is_file():raise RuntimeError('请先 pair 完成平台配对')
    plist.parent.mkdir(parents=True,exist_ok=True)
    logs=root/'logs';logs.mkdir(mode=0o700,exist_ok=True)
    command=[sys.executable,'-m','api_test_tool.managed_runner','--root',str(root),'run','--headless','--backend','macos',
             '--codex-auth',str(Path(auth_file).expanduser().resolve())]
    if codex_bin:command.extend(['--codex-bin',str(Path(codex_bin).expanduser().resolve())])
    if model:command.extend(['--model',model])
    config={'Label':LABEL,'ProgramArguments':command,'WorkingDirectory':str(root),
            'RunAtLoad':True,'KeepAlive':{'SuccessfulExit':False},'ThrottleInterval':30,
            'ProcessType':'Interactive','Umask':0o077,
            'StandardOutPath':str(logs/'runner.log'),'StandardErrorPath':str(logs/'runner-error.log')}
    with open(plist,'xb',opener=lambda p,f:os.open(p,f,0o600)) as stream:plistlib.dump(config,stream)
    subprocess.run(['launchctl','bootstrap',domain,str(plist)],check=True)
    print('已安装并启动当前用户的执行连接服务；登录 Mac 后启动，退出登录后停止。')
