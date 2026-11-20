"""Real loopback HTTP checks for bounded parallelism and isolated evidence."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from api_test_tool.execution import run_bundle
from api_test_tool.scheduling import JobPool, _configured_limit


@pytest.mark.parametrize(("name", "maximum", "configured"), [
    ("API_TEST_MAX_EXECUTIONS", 4, 1),
    ("API_TEST_CASE_WORKERS", 16, 4),
])
def test_deployment_concurrency_limits_are_bounded(monkeypatch, name, maximum, configured):
    monkeypatch.delenv(name, raising=False)
    assert _configured_limit(name, maximum) == maximum
    monkeypatch.setenv(name, str(configured))
    assert _configured_limit(name, maximum) == configured
    for invalid in ("0", str(maximum + 1), "not-a-number"):
        monkeypatch.setenv(name, invalid)
        with pytest.raises(ValueError, match=name):
            _configured_limit(name, maximum)


def case(identifier, *, independent=True):
    assertion = {"kind": "status", "expected": 200, "rule_id": "R"}
    item = {"id": identifier, "title": identifier, "state": "READY", "operation_id": "flow",
            "scenario": "normal", "rule_ids": ["R"],
            "variables": {"identity": {"kind": "unique", "prefix": identifier + "_"}},
            "steps": [{"id": "login", "request": {"method": "GET", "path": "/${identity}/login"},
                       "assertions": [assertion], "extract": [
                           {"name": "resource", "from": "json", "pointer": "/resource_id"},
                           {"name": "token", "from": "json", "pointer": "/token"}]},
                      {"id": "check", "request": {"method": "GET", "path": "/${resource}/check",
                                                   "headers": {"Authorization": "Bearer ${token}"}},
                       "assertions": [assertion]},
                      {"id": "after", "request": {"method": "GET", "path": "/${resource}/after"},
                       "assertions": [assertion]}],
            "cleanup_steps": [{"id": "cleanup", "request": {"method": "DELETE", "path": "/${resource}/cleanup"},
                               "assertions": [assertion]}]}
    if independent:
        item["execution_policy"] = {"mode": "independent", "reason": "每个场景独享登录 Cookie、Token 和资源，清理只作用于自己的资源。"}
    return item


def bundle(cases):
    return {"schema_version": "1.0", "title": "并发隔离检查", "cases": cases,
            "contract": {"sources": {"S": {"excerpt": "Loopback flow returns 200."}}},
            "rules": [{"id": "R", "state": "documented", "source_ids": ["S"]}]}


@pytest.fixture
def target():
    lock = threading.Lock()
    state = {"active": 0, "peak": 0, "gate": 0, "fail": "", "audit": [], "keys": []}
    reached, release = threading.Event(), threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def request(self):
            identity, stage = self.path.strip("/").split("/")
            key = "opaque-secret-" + identity
            with lock:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
                state["audit"].append((identity, stage))
                if state["gate"] and state["active"] >= state["gate"]:
                    reached.set()
            try:
                if state["gate"] and not release.wait(5):
                    raise RuntimeError("Parallel requests never reached the expected overlap")
                status = 200
                if stage == "login":
                    if self.headers.get("Cookie"):
                        status = 409  # Login must start with an empty cookie jar.
                    with lock:
                        state["keys"].append(key)
                elif self.headers.get("Cookie") != "sid=" + key:
                    status = 409
                if stage == "check" and self.headers.get("Authorization") != "Bearer " + key:
                    status = 409
                if state["fail"] and identity.startswith(state["fail"] + "_") and stage == "check":
                    status = 500
                body = json.dumps({"resource_id": identity, "token": key, "echo": key}).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                if stage == "login":
                    self.send_header("Set-Cookie", "sid=" + key + "; Path=/")
                self.end_headers()
            finally:
                with lock:
                    state["active"] -= 1
            self.wfile.write(body)

        do_GET = do_DELETE = request

    class Server(ThreadingHTTPServer):
        request_queue_size = 64

    server = Server(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    environment = {"name": "loopback", "base_url": origin, "allowed_origins": [origin], "case_workers": 4}
    try:
        yield environment, state, reached, release
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(5)


@pytest.mark.parametrize("workers", [4, 16])
def test_parallel_cases_keep_dependencies_cookies_cleanup_and_report_order(target, tmp_path, workers):
    environment, state, reached, release = target
    environment["case_workers"] = workers
    state["gate"] = workers
    case_count = workers * 3
    plan = bundle([case(f"C{i}") for i in range(case_count)])
    contexts = []

    def cleanup(value):
        assert state["active"] == 0
        assert sum(stage == "cleanup" for _, stage in state["audit"]) == case_count
        contexts.extend(value)
        return {"status": "PASS"}

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run_bundle, plan, environment, tmp_path, cleanup_callback=cleanup)
        try:
            assert reached.wait(5), f"{workers} independent requests should overlap"
            assert state["peak"] == workers
        finally:
            release.set()
        result = future.result(timeout=10)
    assert result["summary"]["PASS"] == case_count
    assert result["summary"]["complete"]
    assert result["requests_sent"] == case_count * 4 == len(state["audit"])
    assert state["peak"] <= workers
    assert [item["id"] for item in result["cases"]] == [item["id"] for item in plan["cases"]]
    assert [item["case_id"] for item in contexts] == [item["id"] for item in plan["cases"]]
    assert len({item["variables"]["identity"] for item in contexts}) == case_count
    for item in contexts:
        stages = [stage for identity, stage in state["audit"] if identity == item["variables"]["identity"]]
        assert stages == ["login", "check", "after", "cleanup"]
    serialized = (tmp_path / "result.json").read_text()
    assert all(key not in serialized for key in state["keys"])
    assert "<redacted>" in serialized


def test_serial_case_is_a_barrier_including_cleanup(target, tmp_path):
    environment, state, _, _ = target
    result = run_bundle(bundle([case("A"), case("B"), case("C", independent=False), case("D"), case("E")]), environment, tmp_path)
    assert result["summary"]["PASS"] == 5
    ordered = [(identity.split("_")[0], stage) for identity, stage in state["audit"]]
    assert max(ordered.index((name, "cleanup")) for name in ("A", "B")) < ordered.index(("C", "login"))
    assert ordered.index(("C", "cleanup")) < min(ordered.index((name, "login")) for name in ("D", "E"))


def test_parallel_failure_blocks_only_its_dependents_and_still_cleans(target, tmp_path):
    environment, state, _, _ = target
    state["fail"] = "bad"
    result = run_bundle(bundle([case("bad"), case("good")]), environment, tmp_path)
    bad, good = result["cases"]
    assert [step["status"] for step in bad["steps"]] == ["PASS", "FAIL", "BLOCKED"]
    assert bad["cleanup"]["status"] == "PASS"
    assert good["status"] == "PASS"
    assert not any(identity.startswith("bad_") and stage == "after" for identity, stage in state["audit"])


def test_request_budget_is_atomic_across_parallel_cases(target, tmp_path):
    environment, state, _, _ = target
    environment["max_requests"] = 5
    result = run_bundle(bundle([case(f"C{i}") for i in range(8)]), environment, tmp_path)
    assert result["requests_sent"] == len(state["audit"]) == 5
    assert result["summary"]["BLOCKED"]


def test_explicit_fail_fast_disables_case_parallelism(target, tmp_path):
    environment, state, _, _ = target
    environment["stop_on_5xx"] = True
    state["fail"] = "bad"
    result = run_bundle(bundle([case("bad"), case("good")]), environment, tmp_path)
    assert result["execution"]["case_workers"] == 1
    assert result["cases"][1]["status"] == "BLOCKED"
    assert not any(identity.startswith("good_") for identity, _ in state["audit"])


def test_job_queue_bounds_runs_and_busy_targets_do_not_starve_other_work():
    pool = JobPool()
    entered = {key: threading.Event() for key in ("A1", "A2", "B", "C", "D", "E", "document")}
    release = {key: threading.Event() for key in ("A1", "A2", "B", "C", "D", "E")}

    def work(name):
        entered[name].set()
        if name in release:
            assert release[name].wait(5)

    try:
        pool.submit(lambda: work("A1"), target="origin-a")
        assert entered["A1"].wait(5)
        pool.submit(lambda: work("A2"), target="origin-a")
        pool.submit(lambda: work("B"), target="origin-b")
        pool.submit(lambda: work("C"), target="origin-c")
        pool.submit(lambda: work("D"), target="origin-d")
        pool.submit(lambda: work("E"), target="origin-e")
        pool.submit(lambda: work("document"))
        assert all(entered[key].wait(5) for key in ("B", "C", "D", "document"))
        assert not entered["A2"].is_set() and not entered["E"].is_set()
        release["A1"].set()
        assert entered["A2"].wait(5)
        assert not entered["E"].is_set()
        release["B"].set()
        assert entered["E"].wait(5)
    finally:
        for event in release.values():
            event.set()
        pool.shutdown()


def test_shutdown_drains_waiting_jobs_and_failed_jobs_release_the_target():
    pool = JobPool()
    first, release, second = threading.Event(), threading.Event(), threading.Event()

    def fail():
        first.set()
        assert release.wait(5)
        raise RuntimeError("synthetic failure")

    pool.submit(fail, target="same")
    assert first.wait(5)
    pool.submit(second.set, target="same")
    with ThreadPoolExecutor(max_workers=1) as thread:
        finished = thread.submit(pool.shutdown)
        release.set()
        finished.result(timeout=5)
    assert second.is_set()
    with pytest.raises(RuntimeError, match="shutting down"):
        pool.submit(lambda: None)
