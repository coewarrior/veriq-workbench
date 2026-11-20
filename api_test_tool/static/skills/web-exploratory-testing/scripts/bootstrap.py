#!/usr/bin/env python3
"""Internal setup: capability reuse first; isolated, locked fallback, no global installs."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parent
CACHE = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.cache') / 'api-test-ui'
# A fallback only. Existing versions that pass the probe are never upgraded.
FALLBACK = '1.58.2'


@contextmanager
def installation_lock(cache):
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (cache / 'install.lock').open('a+b') as lock:
        if os.name == 'nt':
            import msvcrt
            lock.seek(0); lock.write(b'0'); lock.flush(); lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        yield


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=kwargs.pop('timeout', 45), **kwargs)


def candidates(node, cache):
    result = []
    configured = os.environ.get('UI_TEST_PLAYWRIGHT_MODULE')
    if configured:
        result.append(configured)
    for name in ('playwright', 'playwright-core'):
        found = run([node, '-p', 'require.resolve(' + json.dumps(name) + ')'])
        if found.returncode == 0:
            result.append(found.stdout.strip())
    roots = [cache / 'packages', Path.home() / '.npm/_npx']
    roots.extend([Path(node).resolve().parent.parent / 'lib/node_modules'])
    for root in roots:
        for pattern in ('*/node_modules/playwright/package.json', '*/node_modules/playwright-core/package.json',
                        'playwright/package.json', 'playwright-core/package.json', '@playwright/cli/node_modules/playwright/package.json'):
            for package in sorted(root.glob(pattern)):
                result.append(str(package.parent))
    return list(dict.fromkeys(result))


def probe(node, module, channel='', video=False):
    try:
        result = run([node, HERE / 'probe.cjs', module, channel, 'video' if video else ''], timeout=40)
        if result.returncode == 0:
            return {'node': str(node), 'module': str(module), 'channel': channel, 'browser': json.loads(result.stdout)['browser'], 'video': video}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return None


def find_working(node, cache):
    for module in candidates(node, cache):
        for channel in ('', 'chrome', 'msedge'):
            found = probe(node, module, channel)
            if found:
                return found
    return None


def download(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        if not response.url.startswith('https://nodejs.org/dist/'):
            raise RuntimeError('Unexpected runtime download origin')
        return response.read()


def portable_node(cache):
    system = {'Darwin': 'darwin', 'Linux': 'linux', 'Windows': 'win'}.get(platform.system())
    arch = {'aarch64': 'arm64', 'arm64': 'arm64', 'AMD64': 'x64', 'x86_64': 'x64'}.get(platform.machine())
    if not system or not arch:
        raise RuntimeError('此系统没有自动准备的 Node 发行包；请复用已有浏览器工具')
    cached = list((cache / 'node').glob('node-*/' + ('node.exe' if system == 'win' else 'bin/node')))
    for node in cached:
        if run([node, '--version']).returncode == 0:
            return node
    base = 'https://nodejs.org/dist/latest-v22.x/'
    sums = download(base + 'SHASUMS256.txt').decode().splitlines()
    suffix = '-' + system + '-' + arch + ('.zip' if system == 'win' else '.tar.gz')
    checksum, filename = next(line.split() for line in sums if line.endswith(suffix))
    content = download(base + filename)
    if hashlib.sha256(content).hexdigest() != checksum:
        raise RuntimeError('Node 包校验失败，未安装')
    destination = cache / 'node'
    destination.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache, prefix='node-download-') as temp:
        archive = Path(temp) / filename
        archive.write_bytes(content)
        out = Path(temp) / 'unpacked'
        out.mkdir()
        if filename.endswith('.zip'):
            with zipfile.ZipFile(archive) as z:
                for member in z.namelist():
                    if not (out / member).resolve().is_relative_to(out.resolve()):
                        raise RuntimeError('Unsafe runtime archive')
                z.extractall(out)
        else:
            with tarfile.open(archive) as t:
                for member in t.getmembers():
                    if member.issym() or member.islnk():
                        # Runtime/npm use JS targets directly; no archive symlinks needed.
                        continue
                    if not (out / member.name).resolve().is_relative_to(out.resolve()):
                        raise RuntimeError('Unsafe runtime archive')
                    t.extract(member, out)
        folder = next(out.iterdir())
        folder.rename(destination / folder.name)
    return destination / folder.name / ('node.exe' if system == 'win' else 'bin/node')


def prepare(cache=CACHE, install=True):
    cache = cache.resolve()
    node = shutil.which('node')
    if node:
        found = find_working(node, cache)
        if found:
            return {**found, 'reused': True}
    if not install:
        raise RuntimeError('未找到通过能力检查的浏览器运行环境；尚未下载')
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    # OS-released advisory lock prevents duplicate installation, including after a crash.
    with installation_lock(cache):
        node = node or portable_node(cache)
        found = find_working(node, cache)
        if found:
            return {**found, 'reused': True}
        # First try installing just the browser belonging to an existing package.
        modules = candidates(node, cache)
        for module in modules:
            root = Path(module) if Path(module).is_dir() else Path(module).parent
            if (root / 'cli.js').exists():
                outcome = run([node, root / 'cli.js', 'install', 'chromium'], timeout=600)
                if outcome.returncode == 0 and (found := probe(node, module)):
                    return {**found, 'reused': True}
        npm = Path(node).resolve().parent.parent / 'lib/node_modules/npm/bin/npm-cli.js'
        if os.name == 'nt':
            npm = Path(node).resolve().parent / 'node_modules/npm/bin/npm-cli.js'
        if not npm.exists():
            node = portable_node(cache)
            npm = Path(node).parent / 'node_modules/npm/bin/npm-cli.js' if os.name == 'nt' else Path(node).parent.parent / 'lib/node_modules/npm/bin/npm-cli.js'
        # Only the isolated fallback requires a supported Node. Existing working
        # combinations returned above, regardless of their version numbers.
        version = run([node, '-p', 'process.versions.node.split(".")[0]'])
        if version.returncode or not version.stdout.strip().isdigit() or int(version.stdout.strip()) < 20:
            node = portable_node(cache)
            npm = Path(node).parent / 'node_modules/npm/bin/npm-cli.js' if os.name == 'nt' else Path(node).parent.parent / 'lib/node_modules/npm/bin/npm-cli.js'
        package = cache / 'packages' / ('fallback-' + FALLBACK)
        package.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, 'PATH': str(Path(node).parent) + os.pathsep + os.environ.get('PATH', ''), 'PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD': '1'}
        result = run([node, npm, 'install', '--prefix', package, '--ignore-scripts', '--no-audit', '--no-fund', 'playwright@' + FALLBACK], timeout=600, env=env)
        if result.returncode:
            raise RuntimeError('浏览器依赖准备失败；请检查 npm 网络访问。未更改现有项目依赖')
        module = package / 'node_modules/playwright'
        for channel in ('', 'chrome', 'msedge'):
            found = probe(node, module, channel)
            if found:
                return {**found, 'reused': False}
        result = run([node, module / 'cli.js', 'install', 'chromium'], timeout=600, env=env)
        found = probe(node, module)
        if not found:
            raise RuntimeError('浏览器仍不能启动，可能缺少系统库或受权限限制；不自动执行 sudo，请 Codex 记录阻塞')
        return {**found, 'reused': False}


def ensure_video(runtime, install=True, cache=CACHE):
    args = [runtime['node'], runtime['module'], runtime['channel']]
    if found := probe(*args, video=True):
        return {**runtime, **found}
    if not install:
        raise RuntimeError('已有截图能力，录屏尚不可用；未下载')
    module = Path(runtime['module'])
    root = module if module.is_dir() else module.parent
    with installation_lock(cache):
        if found := probe(*args, video=True):
            return {**runtime, **found}
        run([runtime['node'], root / 'cli.js', 'install', 'ffmpeg'], timeout=180)
        if found := probe(*args, video=True):
            return {**runtime, **found}
    raise RuntimeError('截图可用，但录屏依赖未就绪；不要声称已经录屏，改用实时截图并说明瞬态证据缺口')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--cache', type=Path, default=CACHE)
    parser.add_argument('--video', action='store_true', help='Also verify recording; download only missing ffmpeg if needed')
    args = parser.parse_args()
    try:
        runtime = prepare(args.cache, not args.check_only)
        if args.video:
            runtime = ensure_video(runtime, not args.check_only, args.cache)
        print(json.dumps(runtime, ensure_ascii=False))
    except Exception as error:
        raise SystemExit(str(error))
