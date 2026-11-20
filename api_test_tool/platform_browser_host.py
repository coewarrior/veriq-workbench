"""Platform-owned browser execution, with a private adapter for each workspace owner.

No desktop credentials, model process, shared user bearer, or new business task.
All actions still enter ManagedService with their original owner and lease checks.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import threading
import time
from uuid import uuid4

from .managed_runner import Runner, save
from .orchestration_storage import read_sections


class BrowserOnlyBackend:
    def prepare(self):
        from . import __version__
        return {
            'network_isolation': 'No local model process; remote Codex uses only authenticated lease-bound browser tools',
            'credential_isolation': 'Private owner directory; no local model process or desktop model credentials',
            'tool_gate': 'ManagedService owner + holder + lease + operation gate',
            'browser_context_isolation': 'Separate persistent browser contexts per owner/node/account',
            'version': 'platform-browser:' + __version__,
        }

    def stop(self, node_id):
        # This backend never starts a model. Runner fences the actual browsers.
        return None

    def close(self):
        return None

    def open(self, node_id):
        raise RuntimeError('平台浏览器连接不运行后台模型')


class OwnerAPI:
    """In-process trusted adapter, never exposed as a browser/MCP tool."""
    def __init__(self, service, owner, host_id):
        self.service = service
        self.auth = {'owner': owner, 'host_id': host_id}

    def call(self, action, /, **args):
        if action == 'register':
            args['evidence'].update(platform_browser=1, auxiliary_channels=0)
            args['model_slots'] = 0
        result = self.service.host_call(self.auth, action, args)
        if action == 'register':
            with self.service.controller.transaction() as (_, state):
                state['runners'][self.auth['host_id']]['platform_managed'] = True
        return result


class PlatformRunner(Runner):
    def __init__(self, supervisor, owner):
        root = supervisor.root / owner
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        host_id = hashlib.sha256(('platform-browser:' + supervisor.machine_id + ':' + owner).encode()).hexdigest()[:32]
        # All owner adapters report the same physical machine. The scheduler
        # counts its leases globally, while access remains owner-scoped.
        save(root / 'machine.json', {'id': supervisor.machine_id})
        self.supervisor = supervisor
        super().__init__(root, OwnerAPI(supervisor.service, owner, host_id), BrowserOnlyBackend(),
                         headed=False, max_browsers=0, max_models=0)

    def capacity(self):
        return self.supervisor.capacity(), 0

    async def execute(self, event, recovery_id=None):
        raise RuntimeError('平台浏览器只接受当前 Codex 会话的直接执行租约')


def available_memory():
    """Use the container allowance, not the physical host's apparent free RAM."""
    import psutil
    free = psutil.virtual_memory().available
    pairs = [('/sys/fs/cgroup/memory.max', '/sys/fs/cgroup/memory.current'),
             ('/sys/fs/cgroup/memory/memory.limit_in_bytes', '/sys/fs/cgroup/memory/memory.usage_in_bytes')]
    for maximum, current in pairs:
        try:
            limit = Path(maximum).read_text().strip()
            if limit != 'max':
                free = min(free, max(0, int(limit) - int(Path(current).read_text())))
        except (FileNotFoundError, ValueError):
            continue
    return free


class PlatformBrowserHost:
    def __init__(self, service):
        self.service = service
        self.root = service.store.root / 'platform-browser-host'
        self.stop_event = threading.Event()
        self.runners = {}
        self.jobs = {}
        self.thread = None
        self.lock = None
        self.last_error = ''
        self.machine_id = ''
        self.browser_memory = 768 * 1024**2

    def start(self):
        import fcntl
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = open(self.root / 'leader.lock', 'a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close(); self.lock = None
            return
        identity = self.root / 'machine.json'
        if not identity.exists():
            save(identity, {'id': uuid4().hex})
        self.machine_id = json.loads(identity.read_text())['id']
        self.thread = threading.Thread(target=lambda: asyncio.run(self.run()),
                                       name='platform-browser-host', daemon=True)
        self.thread.start()

    def owners(self):
        with self.service.controller.connect() as db:
            db.execute('BEGIN')
            state = read_sections(db, ('accounts', 'tasks'), include_baseline=False)
        # Registration is readiness, never authorization to resume a stopped task.
        owners = {a['owner'] for a in state['accounts'].values()}
        owners.update(t['owner'] for t in state['tasks'].values() if t.get('execution_route') == 'local_browser')
        result = []
        for owner in owners:
            try:
                self.service.store._owner_dir(owner)
            except (PermissionError, FileNotFoundError, ValueError):
                continue
            result.append(owner)
        return result

    def capacity(self):
        import psutil
        count = sum(len(r.browser.contexts) + len(r.browser.probe_contexts) for r in self.runners.values())
        rss = 0
        for process in psutil.Process().children(recursive=True):
            try:
                if any(name in process.name().lower() for name in ('chrom', 'headless')):
                    rss += process.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        if count and rss:
            self.browser_memory = max(self.browser_memory, rss // count)
        # Existing allocations stay counted; reserve web-process headroom from
        # the same container budget. No fixed module/browser count is imposed.
        free = max(0, available_memory() - psutil.Process().memory_info().rss)
        budget = count + int(free // self.browser_memory)
        if psutil.cpu_percent() > 95:
            budget = count
        return min(1024, max(0, budget))

    async def run(self):
        retry_at = {}
        try:
            while not self.stop_event.is_set():
                try:
                    for owner in await asyncio.to_thread(self.owners):
                        job = self.jobs.get(owner)
                        if job is not None and not job.done():
                            continue
                        if job is not None:
                            try:
                                job.result()
                            except Exception as exc:
                                self.last_error = type(exc).__name__
                            self.jobs.pop(owner, None)
                            self.runners.pop(owner, None)
                            retry_at[owner] = time.monotonic() + 30
                        if time.monotonic() < retry_at.get(owner, 0):
                            continue
                        runner = PlatformRunner(self, owner)
                        self.runners[owner] = runner
                        self.jobs[owner] = asyncio.create_task(runner.run())
                    save(self.root / 'status.json', {'updated': time.time(), 'owners': len(self.runners),
                         'ready': sum(r.status == 'connected' for r in self.runners.values()),
                         'error': self.last_error})
                except Exception as exc:
                    self.last_error = type(exc).__name__
                await asyncio.sleep(3)
        finally:
            for runner in self.runners.values():
                runner.stopping = True
            await asyncio.gather(*self.jobs.values(), return_exceptions=True)

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join()
        if self.lock:
            self.lock.close(); self.lock = None
