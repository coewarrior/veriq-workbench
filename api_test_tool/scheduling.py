"""Small in-process queue: bounded workers, one execution per target origin."""
from concurrent.futures import ThreadPoolExecutor
import os
import threading


def _configured_limit(name, maximum):
    raw = os.environ.get(name, str(maximum))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer between 1 and {maximum}") from exc
    if not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer between 1 and {maximum}")
    return value


MAX_EXECUTIONS = _configured_limit("API_TEST_MAX_EXECUTIONS", 4)
CASE_WORKERS = _configured_limit("API_TEST_CASE_WORKERS", 16)


def execution_policy_problem(policy):
    if not isinstance(policy, dict) or set(policy) - {"mode", "reason"}:
        return "execution_policy only accepts mode and reason"
    if not isinstance(policy.get("mode"), str) or policy["mode"] not in {"serial", "independent"}:
        return "execution_policy.mode must be serial or independent"
    reason = policy.get("reason", "")
    if not isinstance(reason, str) or len(reason) > 2000:
        return "execution_policy.reason must be text of at most 2000 characters"
    if policy["mode"] == "independent" and not reason.strip():
        return "Independent cases require an explanation of data/session isolation"
    return ""


class JobPool:
    def __init__(self, workers=MAX_EXECUTIONS + 1, executions=MAX_EXECUTIONS):
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="api-test")
        self._workers = workers
        self._executions = executions
        self._condition = threading.Condition()
        self._pending = []
        self._active = 0
        self._targets = set()
        self._closing = False

    def submit(self, work, *, target=None):
        with self._condition:
            if self._closing:
                raise RuntimeError("Task queue is shutting down")
            self._pending.append((work, target))
            self._dispatch()

    def _dispatch(self):
        # A busy target must not consume a worker and stall unrelated work.
        while self._active < self._workers:
            index = next((i for i, (_, target) in enumerate(self._pending)
                          if target is None or target not in self._targets
                          and len(self._targets) < self._executions), None)
            if index is None:
                return
            work, target = self._pending.pop(index)
            self._active += 1
            if target is not None:
                self._targets.add(target)
            self._pool.submit(self._run, work, target)

    def _run(self, work, target):
        try:
            work()
        finally:
            with self._condition:
                self._active -= 1
                if target is not None:
                    self._targets.remove(target)
                self._dispatch()
                self._condition.notify_all()

    def shutdown(self):
        with self._condition:
            self._closing = True
            # Keep the executor open until admitted jobs waiting on a target
            # have also completed, including their cleanup and report writes.
            while self._pending or self._active:
                self._condition.wait()
        self._pool.shutdown(wait=True)
