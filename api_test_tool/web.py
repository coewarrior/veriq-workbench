"""Four-stage browser workspace using the same frozen assets and execution engine as CLI."""
from __future__ import annotations
from . import ui_design_references

import asyncio
import base64
import binascii
import copy
import hashlib
import ipaddress
import importlib.util
import json
import os
import re
import secrets
import shutil
import threading
import tempfile
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit, quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import __version__
from .cleanup import build_cleanup
from .cli import read_asset
from .execution import Redactor, run_bundle, validate_bundle
from .generation import generate_bundle
from .demo import experience_bundle
from .model_planning import generate_plan
from .models import ModelConfig, PROVIDERS, AUTO_OUTPUT_TOKENS, generate_text, test_connection, validate_config
from .network_transport import pinned_session
from .parsers import add_source, parse_document
from .reporting import write_report
from .report_theme import prepare_online_report
from .case_reporting import render_case_report
from .web_cleanup import gomoku_mysql_cleanup
from .web_generation import approve_cases, auto_bundle, compile_model_bundle, model_prompts, refresh_approval_eligibility, preserve_reviews
from .web_security import check_document, check_public_endpoint, check_web_bundle
from .web_storage import Store
from .workspace_shell import prepare_workspace_page
from .document_targets import document_targets, normalize_base_url, url_origin
from .document_limits import MAX_DOCUMENT_BYTES, MAX_DOCUMENT_REQUEST_BYTES, DOCUMENT_LIMIT_LABEL
from .pingcode import install_pingcode, MAX_SCREENSHOT_REQUEST_BYTES
from .wecom import install_wecom
from .mcp_access import MCPAccess
from .mcp_progress import ACTIONS, record_progress, record_case_progress
from .accounts import install_accounts
from .task_reports import DEFAULT_GOAL, task_config, save_task_report
from .xlsx_results import MAX_XLSX_BYTES, parse_xlsx_results, result_findings
from .defect_title import AI_TITLE_GUIDANCE
from . import testing_policy
from . import ui_records, ui_closeout, ui_report_corrections, ui_retests, ui_attachments, ui_dependencies, requirement_design, test_checkpoints, test_capabilities
from . import report_collaboration, ui_rounds
from .interface_management import revision as contract_revision, change_operation, current_document_path
from .scheduling import JobPool, MAX_EXECUTIONS, CASE_WORKERS
from .case_import import WORKFLOWS, import_candidates, merge_bundles, append_generated, candidates_from_bundle, bundle_revision
from .load_testing import load_config, run_load, render_load_report
from .jmeter_engine import configuration as jmeter_config, capabilities as jmeter_capabilities, selected_cases as jmeter_cases, run_jmeter
from .network_transport import _origin as transport_origin, _resolve_once

REPO = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
TEMPLATES = {
    "gomoku": {"title": "五子棋接口", "file": REPO / "examples/gomoku/evidence/接口文档.md", "filename": "gomoku.md", "environment": "gomoku"},
    "items": {"title": "资源管理 API", "file": REPO / "examples/items/openapi.yaml", "filename": "items.yaml", "environment": "items"},
}
PUBLIC_REPORT_STATIC = {'/static/report-theme.css', '/static/shared-glass.css',
                        '/static/report-review.css', '/static/report-review.js',
                        '/static/report-retest.js', '/static/report-select.js', '/static/report-aggregate.js',
                        '/static/report-image-preview.css', '/static/report-image-preview.js'}
UI_EXECUTION_PERMISSIONS = {
    'safe': {
        'label': '安全测试权限',
        'description': '允许读取、浏览和使用不产生持久业务影响的测试操作；持久写入、外发和不可逆操作需要另行确认。',
    },
    'full': {
        'label': '完整功能测试权限',
        'description': '允许在目标系统和当前授权账号内使用合成数据执行创建、修改、删除、上传、下载、模型调用、重复提交、多标签和并发测试，并完成归属明确的测试数据收尾；付款、对外发送、正式发布、启动真实业务及操作既有共享数据仍需另行确认。',
    },
    'maximum': {
        'label': '最大权限',
        'description': '用户在测试开始前明确授权：可在目标系统和当前授权账号或租户内执行完成测试所需的全部操作，包括读取、创建、修改、删除、上传、下载、模型调用、重复或并发操作、对外发送、正式发布、付款、启动真实业务及不可逆操作，无需逐项再次询问。AI 仍须核对目标与对象，不能越出目标系统和当前账号或租户，不能操作与测试无关的数据；该授权不等于凭空获得缺失的账号、设备或系统能力。',
    },
}


UI_SCENE_RETENTION = {
    'none': '不保留测试现场',
    'defects': '仅保留缺陷现场',
    'test_data': '保留数据并恢复配置',
    'full': '保留完整测试现场',
}


def ui_scene_retention(value):
    value = 'none' if value in (None, '') else value
    if not isinstance(value, str) or value not in UI_SCENE_RETENTION:
        raise ValueError('测试现场保留范围仅支持 none/defects/test_data/full')
    return {'key': value, 'label': UI_SCENE_RETENTION[value]}


def ui_execution_permission(value, default='full'):
    value = default if value in (None, '') else value
    if not isinstance(value, str) or value not in UI_EXECUTION_PERMISSIONS:
        raise ValueError('执行权限范围仅支持 safe/full/maximum')
    return {'key': value, **UI_EXECUTION_PERMISSIONS[value]}


def _is_public_report_page(method: str, path: str) -> bool:
    if method not in {"GET", "HEAD"}:
        return False
    parts = path.split("/")
    if len(parts) != 7 or parts[1:3] != ["api", "projects"]:
        return False
    kind, filename = parts[4], parts[6]
    return (kind == "reports" and (filename in {"index.html", "cases.html", "cases.xlsx", "test-data.zip"} or filename.startswith('asset-'))
            or kind == "load-reports" and filename == "index.html")


def _summary(bundle):
    return {"total": len(bundle.get("cases", [])), **dict(Counter(c["state"] for c in bundle.get("cases", []))),
            "engine": bundle.get("generation", {}).get("engine", ""),
            "approval_eligible": sum(bool(c.get("web", {}).get("approval_eligible")) for c in bundle.get("cases", []))}


def _portable_sources(contract):
    for source in contract.get("sources", {}).values():
        if source.get("path"):
            source["path"] = "inputs/" + Path(source["path"]).name
    return contract


def _testing_skill():
    path = "skills/api-test-workspace/SKILL.md"
    return {"path": "/static/" + path, "name": "api-test-workspace", "content": (STATIC / path).read_text()}


def _ui_testing_skill(project=None, role=''):
    root = STATIC / 'skills/web-exploratory-testing'
    from .testing_roles import resolve_role, role_skill
    selected = resolve_role(project or {}, role)
    return {'name': 'web-exploratory-testing', **role_skill(selected),
            **({
            'reproduction_guidance': ui_records.REPRODUCTION_GUIDANCE,
            'manual_action_guidance': ui_records.ui_action_context.GUIDANCE,
            'upload_fallback_guidance': ui_records.ui_uploads.GUIDANCE,
            'execution_strategy_guidance': ui_dependencies.EXECUTION_GUIDANCE,
            } if selected != 'coordinator' else {}),
            'files': [{'path': '/static/' + str(p.relative_to(STATIC)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                      for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts]}


def _ui_parallel_guidance(role=''):
    if role == 'coordinator':
        return '按平台随包协调参考登记原模块和真实会话，转发独立worker_packet并沿原协调入口等待；不领取业务账号。'
    # Keep the existing execution/resource rules without assigning workers the
    # coordinator's intervention duties.
    return ui_rounds.GUIDANCE.split('。', 1)[1]


def create_app(data_dir: Path | None = None, *, start_fixture: bool = True, testing: bool = False,
               trusted_model_origins=(), extra_test_origins=(), auth_enabled: bool | None = None,
               report_only: bool = False) -> FastAPI:
    store = Store(data_dir or Path(os.environ.get("API_TEST_DATA_DIR", "work/web-data")))
    jobs = {}
    load_stops = {}
    lock = threading.RLock()
    admission_lock = threading.RLock()
    jobs_lock = threading.RLock()
    health_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='workspace-health')
    pool = JobPool()
    fixture = None
    from .storage_gate import StorageGate
    storage_gate = StorageGate()
    configured_test_origins = tuple(x.strip().rstrip("/") for x in os.environ.get("API_TEST_ALLOWED_ORIGINS", "").split(",") if x.strip())
    for origin in configured_test_origins:
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.path or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("API_TEST_ALLOWED_ORIGINS 仅接受逗号分隔的 HTTP(S) origin")
        check_public_endpoint(origin, (origin,))
    environments = {
        "gomoku": {"id": "gomoku", "name": "五子棋 · 独立测试环境", "base_url": "http://192.0.2.20:18081"},
        "items": {"id": "items", "name": "资源 API · 可重置示例", "base_url": "http://127.0.0.1:18082"},
    }

    @asynccontextmanager
    async def lifespan(app):
        nonlocal fixture
        if start_fixture:
            spec = importlib.util.spec_from_file_location("web_items_fixture", REPO / "tests/fixtures/items_server.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            fixture = module.ItemsServer(port=int(os.environ.get("API_TEST_FIXTURE_PORT", "18082")))
            fixture.__enter__()
            environments["items"]["base_url"] = fixture.base_url
        def start_background():
            if not testing and not report_only:
                orchestration.start()
            if not report_only:
                app.state.defect_batches.start()
            if not testing and not report_only:
                project_reports.start()
        await storage_gate.start(start_background)
        yield
        await storage_gate.close()
        project_reports.close()
        app.state.defect_batches.close()
        orchestration.close()
        pool.shutdown()
        health_pool.shutdown(wait=True)
        if fixture:
            fixture.__exit__(None, None, None)

    app = FastAPI(title="测试工作台", version=__version__, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.store = store
    app.state.jobs = jobs
    drain_file = Path(os.environ.get("API_TEST_DRAIN_FILE", "/tmp/api-test-deploy-drain"))
    active_writes = 0
    project_writes = {}

    @app.middleware("http")
    async def deployment_gate(request: Request, call_next):
        nonlocal active_writes
        mutation = request.method not in {"GET", "HEAD", "OPTIONS"}
        parts = request.url.path.split("/")
        project_key = (getattr(request.state, "owner", None), parts[3]) if len(parts) > 3 and parts[1:3] == ["api", "projects"] else None
        if mutation:
            from .deployment import continuation
            payload = None
            # Drain can begin while the body arrives. Parse before the admission
            # decision so existing result/exit/ACK calls remain recognizable.
            if request.headers.get('content-type', '').startswith('application/json'):
                try:
                    payload = await request.json()
                except ValueError:
                    pass
            with admission_lock:
                if drain_file.exists() and not continuation(request.method, request.url.path, payload):
                    return JSONResponse({"detail": "测试台正在发布更新，暂缓新派发和资源领取；已有执行、结果保存和退出收尾继续保留。"}, 503,
                                        headers={"Retry-After": "30"})
                active_writes += 1
                if project_key:
                    project_writes[project_key] = project_writes.get(project_key, 0) + 1
        try:
            return await call_next(request)
        finally:
            if mutation:
                with admission_lock:
                    active_writes -= 1
                    if project_key:
                        project_writes[project_key] -= 1
                        if not project_writes[project_key]:
                            del project_writes[project_key]
    if auth_enabled is None:
        auth_enabled = not testing
    accounts = install_accounts(app, store, STATIC, auth_enabled)
    mcp_access = MCPAccess(store)
    install_pingcode(app, store, STATIC)
    install_wecom(app, store, STATIC)
    from . import orchestration_web
    orchestration = orchestration_web.install(app, store, STATIC)
    orchestration.admission_lock = admission_lock
    orchestration.draining = drain_file.exists
    from .project_reports import ProjectReports
    project_reports = ProjectReports(store, orchestration)
    project_report_tick = project_reports.tick

    def admitted_project_report_tick():
        # Keep the existing projection worker and durable cursor. A pending
        # projection is restartable intent; only an entered tick is active work.
        with orchestration.background_job('report_projection') as admitted:
            if admitted:
                return project_report_tick()

    project_reports.tick = admitted_project_report_tick
    store.project_reports = project_reports
    app.state.project_reports = project_reports

    @app.get('/api/account-projects/{account_id}/total-report')
    def account_total_report(request: Request, account_id: str):
        group = project_reports.group(request.state.owner, account_id)
        saved = project_reports.cached(request.state.owner, group)
        return {'report_url': f"/api/projects/{group['id']}/reports/total/index.html",
                'aggregate': saved['aggregate']}

    @app.middleware("http")
    async def session_and_limits(request: Request, call_next):
        if request.url.path.startswith(("/static/", "/landing-pages/")):
            if report_only and request.url.path not in PUBLIC_REPORT_STATIC:
                return JSONResponse({"detail": "公网端口仅提供只读测试报告"}, 404,
                                    headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            return response
        if request.url.path == "/healthz":
            return await call_next(request)
        if report_only and not _is_public_report_page(request.method, request.url.path):
            return JSONResponse({"detail": "公网端口仅提供只读测试报告"}, 404,
                                headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
        allowed_hosts = {"127.0.0.1", "localhost", "192.0.2.20", *os.environ.get("API_TEST_HOSTS", "").split(",")}
        if testing:
            allowed_hosts.add("testserver")
        numeric_report_host = False
        if report_only:
            try:
                ipaddress.ip_address(request.url.hostname or "")
                numeric_report_host = True
            except ValueError:
                pass
        if request.url.hostname not in allowed_hosts and not numeric_report_host:
            return JSONResponse({"detail": "访问地址未配置"}, 400)
        # Retired Runner transport must not authenticate against, write to, or
        # schedule the native account store, including stale external clients.
        if request.url.path in {"/api/managed-host/call", "/api/managed-host/redeem",
                                "/api/orchestration/hosts/pair"}:
            return JSONResponse({"detail": "旧执行机服务已停用，请使用原生 Codex 执行流程",
                                 "code": "legacy_runner_retired"}, 410,
                                headers={"Cache-Control": "no-store"})
        mcp_call = request.url.path == "/api/mcp/call"
        mcp_redeem = request.url.path == "/api/mcp/redeem"
        request.state.mcp = mcp_call
        request.state.mcp_scope = None
        if mcp_call:
            authorization = request.headers.get("authorization", "")
            try:
                authentication = await run_in_threadpool(mcp_access.authentication, authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else "")
                owner = authentication['owner']
                request.state.mcp_scope = authentication if 'project_ids' in authentication else None
            except PermissionError:
                return JSONResponse({"detail": "MCP 未连接或连接已撤销，请在网页重新连接 Codex"}, 401)
            session, token = {"id": owner, "csrf": ""}, None
        else:
            session, token = await run_in_threadpool(store.session, request.cookies.get("api_test_session"))
        request.state.browser_owner = session["id"]
        request.state.user = None if mcp_call else await run_in_threadpool(accounts.authenticate, request.cookies.get("api_test_auth"))
        request.state.owner = request.state.user["owner"] if request.state.user else session["id"]
        request.state.actor_owner = request.state.owner
        request.state.csrf = session["csrf"]
        request.state.public_report = _is_public_report_page(request.method, request.url.path)
        public = (request.url.path == "/login" or request.url.path.startswith("/api/auth/")
                  or mcp_redeem or request.state.public_report)
        if auth_enabled and not public and not mcp_call and not request.state.user:
            if request.url.path.startswith("/api/") and not request.url.path.endswith("/index.html"):
                response = JSONResponse({"detail": "请先登录", "login_required": True}, 401)
            else:
                response = RedirectResponse("/login?next=" + quote(request.url.path + ("?" + request.url.query if request.url.query else ""), safe=""), status_code=303)
            if token:
                response.set_cookie("api_test_session", token, httponly=True, samesite="strict", secure=request.url.scheme == "https", max_age=60 * 60 * 24 * 180)
            response.headers["Cache-Control"] = "no-store"
            return response
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            expected_origin = str(request.base_url).rstrip("/")
            if (origin and origin != expected_origin) or (not (mcp_call or mcp_redeem) and not secrets.compare_digest(request.headers.get("x-csrf-token", ""), session["csrf"])):
                return JSONResponse({"detail": "会话校验失效，请刷新页面后重试"}, 403)
            document_request = request.url.path in {"/api/projects", "/api/requirement-tests", "/api/mcp/call", "/api/document-targets"}
            xlsx_request = request.url.path == "/api/ui-tests/import-results"
            screenshot_request = "/pingcode/" in request.url.path
            body_limit = (MAX_DOCUMENT_REQUEST_BYTES if document_request else
                          MAX_XLSX_BYTES * 4 // 3 + 100_000 if xlsx_request else 1_500_000)
            if screenshot_request:
                body_limit = MAX_SCREENSHOT_REQUEST_BYTES
            if request.url.path.endswith('/retest-inputs'):
                body_limit = ui_retests.MAX_TOTAL_BYTES * 4 // 3 + 200_000
            if request.url.path == '/api/ui-tests' or re.fullmatch(r'/api/(?:ui-tests|projects)/[^/]+/(?:attachments|materials)', request.url.path):
                body_limit = ui_attachments.MAX_REQUEST_BYTES
            if mcp_call:
                body_limit = max(body_limit, 29_000_000)
            body = bytearray()
            async for chunk in request.stream():
                if len(body) + len(chunk) > body_limit:
                    message = f"请求过大，单份文档上限为 {DOCUMENT_LIMIT_LABEL}" if document_request else "请求内容过大"
                    return JSONResponse({"detail": message}, 413)
                body.extend(chunk)
            request._body = bytes(body)
            del body
        request.state.report_scope = None
        if request.state.user and not report_only and not mcp_call:
            try:
                context = await run_in_threadpool(report_collaboration.scope, store, request.url.path)
            except HTTPException as exc:
                return JSONResponse({'detail': exc.detail}, exc.status_code)
            except (ValueError, FileNotFoundError, PermissionError):
                return JSONResponse({'detail': '报告不存在'}, 404)
            if context:
                request.state.report_scope = context
                request.state.owner = context['owner']
        request.state.aggregate_context = None
        aggregate_id = request.headers.get('x-project-report', '')
        is_mutation = request.method not in {'GET', 'HEAD', 'OPTIONS'}
        stopping_batch = bool(re.fullmatch(r'/api/projects/[^/]+/reports/[^/]+/pingcode/batches/jobs/[^/]+/stop', request.url.path))
        parts = request.url.path.split('/')
        if is_mutation and not stopping_batch and len(parts) > 5 and parts[1:3] == ['api', 'projects'] and parts[4] == 'reports':
            try:
                holder = await run_in_threadpool(store.get_project, request.state.owner, parts[3])
                if holder.get('business_project'):
                    aggregate_id = parts[3]
            except (FileNotFoundError, PermissionError, ValueError):
                pass  # Existing route authorization supplies the response.
        if is_mutation and aggregate_id and not stopping_batch:
            try:
                aid = aggregate_id
                version = request.headers.get('x-project-revision', '')
                value = await run_in_threadpool(project_reports.validate, request.state.owner, aid, version)
                parts = request.url.path.split('/')
                if len(parts) < 6 or parts[1:3] != ['api', 'projects']:
                    raise HTTPException(400, '项目总报告操作来源无效')
                source_pid, source_rid = parts[3], parts[5]
                if source_pid != aid and not any(v['project_id'] == source_pid and v['report_id'] == source_rid
                    for v in value['inventory']['sources'].values()):
                    raise HTTPException(403, '操作对象不属于此项目总报告')
                aggregate_project = await run_in_threadpool(project_reports.get, request.state.owner, aid)
                request.state.aggregate_context = {'project_id': aid, 'revision': version,
                    'account_project_id': aggregate_project['aggregate_account_project_id'],
                    'membership_revision': value['inventory']['membership_revision']}
            except HTTPException as exc:
                return JSONResponse({'detail': exc.detail}, exc.status_code)
            except (ValueError, FileNotFoundError, PermissionError):
                return JSONResponse({'detail': '项目总报告来源不可用，请刷新'}, 409)
        response = await call_next(request)
        if (request.state.report_scope and request.method not in {'GET', 'HEAD', 'OPTIONS'}
                and 200 <= response.status_code < 300):
            await run_in_threadpool(report_collaboration.record, store, request.state.report_scope, request.state.user['username'])
        if token:
            response.set_cookie("api_test_session", token, httponly=True, samesite="strict",
                                secure=request.url.scheme == "https", max_age=60 * 60 * 24 * 180)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse({"detail": "提交内容格式错误，请检查输入字段"}, 422)

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        return JSONResponse({"detail": str(exc)[:800]}, 400)

    @app.exception_handler(FileNotFoundError)
    async def not_found(request, exc):
        return JSONResponse({"detail": "项目或文件不存在，或不属于当前账号"}, 404)

    @app.exception_handler(PermissionError)
    async def permission_error(request, exc):
        return JSONResponse({"detail": "当前会话不能访问该项目"}, 403)

    from .direct_execution import DirectExecutionDenied

    @app.exception_handler(DirectExecutionDenied)
    async def direct_permission_error(request, exc):
        return JSONResponse({'detail': str(exc)}, 403)

    from .cleanup_contract import CleanupScopeError, CleanupValidationError

    @app.exception_handler(CleanupValidationError)
    async def cleanup_validation_error(request, exc):
        return JSONResponse({'detail': str(exc)[:800], 'code': 'cleanup_invalid_events',
                             'errors': exc.errors}, 400)

    @app.exception_handler(CleanupScopeError)
    async def cleanup_scope_error(request, exc):
        return JSONResponse({'detail': str(exc), 'code': 'cleanup_scope_denied'}, 403)

    def ensure_idle(owner):
        with jobs_lock:
            if any(j["owner"] == owner and j["status"] in {"queued", "running"} for j in jobs.values()):
                raise HTTPException(409, "当前已有任务执行，请等待完成")

    def serialized(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            with lock:
                request = kwargs.get('request')
                if request and getattr(request.state, 'aggregate_context', None):
                    with store._lock:
                        return fn(*args, **kwargs)
                return fn(*args, **kwargs)
        return wrapped

    def public_job(job):
        return {key: value for key, value in job.items() if key != "owner"}

    def begin_job(owner, project_id, kind, work, *, execution_target=None):
        with lock, jobs_lock:
            if drain_file.exists():
                raise HTTPException(503, "测试台正在发布更新，请稍后重试")
            ensure_idle(owner)
            if sum(j["status"] in {"queued", "running"} for j in jobs.values()) >= 8:
                raise HTTPException(429, "服务器任务队列已满，请稍后重试")
            jid = str(uuid.uuid4())
            job = {"id": jid, "owner": owner, "project_id": project_id, "kind": kind, "status": "queued",
                   "message": "任务已排队", "created_at": time.time(), "logs": []}
            jobs[jid] = job

        def progress(message):
            with lock:
                with jobs_lock:
                    job.update(message=message)
                    job["logs"].append({"at": time.time(), "message": message})
                    job["logs"] = job["logs"][-200:]
                    saved_job = public_job(job)
                if project_id:
                    store.update_project(owner, project_id, {"last_job": saved_job})

        def worker():
            with lock, jobs_lock:
                job.update(status="running", started_at=time.time())
            try:
                result = work(progress)
                with lock, jobs_lock:
                    job.update(status="completed", result=result, message="任务完成")
            except Exception as exc:
                error = str(exc)[:800] if isinstance(exc, (ValueError, RuntimeError, HTTPException)) else "任务执行异常，请检查输入配置或服务器状态"
                saved_key = store.get_model(owner, include_secret=True).get("api_key", "")
                if saved_key:
                    error = error.replace(saved_key, "<redacted>")
                with lock, jobs_lock:
                    job.update(status="failed", error=error, message="任务未完成")
            finally:
                with lock:
                    with jobs_lock:
                        job["finished_at"] = time.time()
                        saved_job = public_job(job)
                    if project_id:
                        store.update_project(owner, project_id, {"last_job": saved_job})

        pool.submit(worker, target=execution_target)
        return public_job(job)

    def model_config(owner, profile_id=None):
        value = store.get_model(owner, include_secret=True, profile_id=profile_id)
        value.pop("has_key", None)
        config = ModelConfig(**value)
        validate_config(config)
        check_public_endpoint(config.base_url, trusted_model_origins if testing else ())
        return config

    def project_environment(project):
        chosen = project.get("task", {}).get("environment", "auto")
        return (project.get("template") or "custom") if chosen == "auto" else chosen

    def decorate_bundle(project, bundle):
        # Capabilities belong to the selected server, never to document identity.
        if project_environment(project) == "gomoku":
            bundle.setdefault("web", {})["trusted_cleanup"] = "gomoku"
        elif "web" in bundle:
            bundle["web"].pop("trusted_cleanup", None)
        return refresh_approval_eligibility(bundle)

    @app.get("/healthz")
    async def health():
        # Health must not queue behind long business routes in Starlette's shared
        # worker pool. Counts are still read now, never cached or assumed zero.
        return await asyncio.get_running_loop().run_in_executor(health_pool, health_snapshot)

    def health_snapshot():
        # Database/batch locks must never hold the request admission lock: the
        # async middleware also needs it to admit and finish existing requests.
        # Capture admission first. Once draining is observed no new background
        # worker can enter; a worker that commits during the DB read below stays
        # conservatively counted in this snapshot instead of falling in a gap.
        with admission_lock:
            writes = active_writes
            draining = drain_file.exists() or not storage_gate.active
            background = orchestration.background_activity()
            reports = orchestration.report_activity()
        from .database import storage_status
        storage = storage_status()
        managed_count = (orchestration.active_count() + app.state.defect_batches.active_count()
                         + sum(background.values()) + reports['count'])
        with jobs_lock:
            job_count = sum(j["status"] in {"queued", "running"} for j in jobs.values()) + managed_count
        return {"status": "ok", "version": __version__,
                "revision": os.environ.get("API_TEST_REVISION", ""),
                "storage": storage,
                "execution": {"max_parallel_runs": MAX_EXECUTIONS, "max_case_workers": CASE_WORKERS,
                              "same_target": "serial"},
                "deployment": {"draining": draining, "active_writes": writes, "active_jobs": job_count,
                               "activity_capability_version": 1,
                               "active_report_workers": reports['count'],
                               "report_worker_node_ids": reports['node_ids'],
                               "active_report_projection_workers": background.get('report_projection', 0),
                               "active_schedulers": background.get('scheduler', 0)}}

    def workspace_page(filename, assets, *, ui_workspace=False):
        # Content-based URLs also bypass assets already fresh in older browser
        # caches; cache headers alone cannot invalidate those existing entries.
        page = (STATIC / filename).read_text(encoding="utf-8")
        if filename == "index.html":
            page = prepare_workspace_page(page, ui=ui_workspace, version=__version__)
        for name in assets:
            digest = hashlib.sha256((STATIC / name).read_bytes()).hexdigest()[:16]
            page = page.replace(f'/static/{name}"', f'/static/{name}?v={digest}"')
        return HTMLResponse(page)

    @app.get("/")
    def home():
        return workspace_page("home.html", ("home.js", "home.css", "account-bar.js", "account-bar.css"))

    workspace_assets = ("app.js", "workspace-integrations.js", "workspace-integrations.css", "wecom.js", "pingcode.css", "ui-workflow.js", "requirements-workflow.js", "requirements-workflow.css", "ui-flow.css", "style.css", "workflow-tools.js", "workflow-tools.css", "manual-cases.js", "project-accounts.js")

    @app.get("/api-testing")
    def index():
        return workspace_page("index.html", workspace_assets)

    @app.get("/ui-testing")
    def ui_testing():
        return workspace_page("index.html", workspace_assets, ui_workspace=True)

    @app.get("/guide")
    def guide():
        return FileResponse(STATIC / "guide.html")

    @app.get("/api/bootstrap")
    def bootstrap(request: Request):
        owner = request.state.owner
        profiles = store.list_profiles(owner)
        projects = (ui_projects(owner) if request.query_params.get("test_kind") == "ui"
                    else store.list_projects(owner))
        for project in projects:
            if project.get("test_kind") == "ui":
                continue
            if "api_profile_id" not in project:
                store.update_project(owner, project["id"], {"api_profile_id": profiles["active_id"]})
            last = project.get("last_job", {})
            if last.get("status") in {"queued", "running"} and last.get("id") not in jobs:
                last.update(status="failed", message="服务重启中断了上次任务，请重新执行", error="服务重启中断了上次任务，请重新执行")
                store.update_project(owner, project["id"], {"last_job": last})
        # Only non-UI metadata can be changed above. The UI response can reuse
        # its current projection, including its shared legacy record cache.
        if request.query_params.get("test_kind") != "ui":
            projects = store.list_projects(owner)
        return {"version": __version__, "csrf": request.state.csrf, "providers": PROVIDERS, "auto_output_tokens": AUTO_OUTPUT_TOKENS,
                "apis": store.list_profiles(owner), "model": store.get_model(owner),
                "projects": [project for project in projects
                             if (project.get("test_kind") == "ui") == (request.query_params.get("test_kind") == "ui")],
                "default_task_goal": DEFAULT_GOAL, "jmeter": jmeter_capabilities(),
                "max_document_bytes": MAX_DOCUMENT_BYTES,
                "templates": [{"id": key, "title": value["title"], "filename": value["filename"]} for key, value in TEMPLATES.items()]}

    @app.get("/api/templates/{name}")
    def get_template(name: str):
        if name not in TEMPLATES:
            raise HTTPException(404, "示例不存在")
        template = TEMPLATES[name]
        return {"id": name, "title": template["title"], "filename": template["filename"], "content": template["file"].read_text()}

    @app.get("/api/apis")
    def api_profiles(request: Request):
        return store.list_profiles(request.state.owner)

    def write_profile(request, data, pid=None):
        owner = request.state.owner
        ensure_idle(owner)
        data = dict(data)
        name = data.pop("name", None)
        if not isinstance(name, str) or not name.strip() or len(name) > 80:
            raise ValueError("请填写1–80字的配置名称")
        current = store.get_model(owner, include_secret=True, profile_id=pid) if pid else {
            "provider": "custom", "protocol": "openai_chat", "base_url": "", "model": "", "api_key": "", "max_tokens": None, "timeout": 90}
        current.pop("has_key", None)
        if set(data) - set(current):
            raise ValueError("未知API配置字段")
        if current.get("api_key") and data.get("base_url", current["base_url"]).rstrip("/") != current["base_url"].rstrip("/") and not data.get("api_key"):
            raise ValueError("更换API地址时请重新填写对应Key")
        updated = {**current, **{k: v for k, v in data.items() if k != "api_key" or v}}
        validate_config(ModelConfig(**updated))
        store.save_model(owner, updated, profile_id=pid, name=name, create=pid is None)
        return store.list_profiles(owner)

    @app.post("/api/apis")
    def add_profile(request: Request, data: dict):
        return write_profile(request, data)

    @app.put("/api/apis/{pid}")
    def edit_profile(request: Request, pid: str, data: dict):
        return write_profile(request, data, pid)

    @app.delete("/api/apis/{pid}")
    def delete_profile(request: Request, pid: str):
        ensure_idle(request.state.owner)
        return store.delete_profile(request.state.owner, pid)

    @app.post("/api/apis/{pid}/select")
    def select_profile(request: Request, pid: str):
        ensure_idle(request.state.owner)
        return store.select_profile(request.state.owner, pid)

    @app.put("/api/model")
    def save_model(request: Request, data: dict):
        owner = request.state.owner
        ensure_idle(owner)
        current = store.get_model(owner, include_secret=True)
        current.pop("has_key", None)
        allowed = set(current)
        if set(data) - allowed:
            raise ValueError("模型配置包含未知字段")
        if data.get("base_url", current["base_url"]).rstrip("/") != current["base_url"].rstrip("/") and current.get("api_key") and not data.get("api_key"):
            raise ValueError("更换 API 地址时请重新填写该服务的 Key，避免将旧凭据发送给新地址")
        if data.get("api_key", "") == "":
            data = {k: v for k, v in data.items() if k != "api_key"}
        updated = {**current, **data}
        validate_config(ModelConfig(**updated))
        return store.save_model(owner, updated)

    @app.delete("/api/model")
    def clear_model(request: Request):
        ensure_idle(request.state.owner)
        store.clear_model(request.state.owner)
        return store.get_model(request.state.owner)

    @app.post("/api/model/test")
    def test_model(request: Request, profile_id: str | None = None):
        owner = request.state.owner
        config = model_config(owner, profile_id)
        def work(progress):
            progress("正在向所选模型发送一次短请求")
            result = test_connection(config, session_factory=lambda: pinned_session(config.base_url, tuple(trusted_model_origins if testing else ())), on_progress=progress)
            return {"connected": True, "model": result["model"], "protocol": result["protocol"],
                    "elapsed_ms": result["elapsed_ms"], "usage": result["usage"]}
        return begin_job(owner, None, "model_test", work)

    @app.post("/api/apis/{pid}/test")
    def test_profile(request: Request, pid: str):
        return test_model(request, pid)

    def extract_targets(data):
        filename, content = data.get("filename", "document.md"), data.get("content", "")
        if not isinstance(filename, str) or not isinstance(content, str):
            raise ValueError("文档名称和内容必须为文本")
        if len(content.encode("utf-8")) > MAX_DOCUMENT_BYTES:
            raise ValueError(f"单份文档上限为 {DOCUMENT_LIMIT_LABEL}")
        result = document_targets(content, filename)
        template = data.get("template")
        if isinstance(template, str) and template in TEMPLATES and content == TEMPLATES[template]["file"].read_text():
            result = {"candidates": [{"url": environments[template]["base_url"], "source": "示例配套测试服务", "description": environments[template]["name"]}], "notes": []}
        return result

    @app.post("/api/document-targets")
    def preview_targets(data: dict):
        return extract_targets(data)

    def ui_target(value):
        if not isinstance(value, str) or not value.strip() or len(value) > 4000 or any(ord(char) < 32 for char in value):
            raise ValueError("请填写有效的目标页面地址")
        target = value.strip()
        try:
            parsed = urlsplit(target)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError
            parsed.port
        except (ValueError, TypeError):
            raise ValueError("目标页面必须是完整的 HTTP(S) 地址") from None
        return target

    def ui_projects(owner, *, project_id=None):
        """Present legacy regression sessions as report rounds of their source session."""
        projects = store.list_projects(owner)
        by_id = {project['id']: dict(project) for project in projects}
        snapshot = orchestration.snapshot(owner) if any(p.get('test_kind') == 'ui' for p in projects) else None
        progress_projects = list(by_id.values())
        if project_id is not None:
            # A detail request needs only its actual record family. Keep all
            # metadata/snapshot inputs and the family's original order: a
            # sibling can populate a legacy record cache used by its parent.
            links = {pid: set() for pid in by_id}

            def link(left, right):
                if left in links and right in links:
                    links[left].add(right)
                    links[right].add(left)

            tasks = {t['id']: t['project_id'] for t in (snapshot or {}).get('tasks', [])}
            nodes = {n['id']: n for n in (snapshot or {}).get('nodes', [])}
            for node in nodes.values():
                link(tasks.get(node['task_id']), node.get('record_project_id'))
            for project in projects:
                for parent in (project.get('managed_parent_project_id'),
                               project.get('regression_source', {}).get('project_id'),
                               project.get('execution_round', {}).get('parent_project_id'),
                               project.get('execution_round', {}).get('source_project_id')):
                    link(project['id'], parent)
                node = nodes.get(project.get('managed_node_id'), {})
                link(project['id'], tasks.get(node.get('task_id')))
                link(project['id'], node.get('record_project_id'))
            related, pending = set(), [project_id]
            while pending:
                pid = pending.pop()
                if pid in related:
                    continue
                related.add(pid)
                pending.extend(links.get(pid, set()) - related)
            progress_projects = [p for p in progress_projects if p['id'] in related]
        progress_records = {}
        for project in progress_projects:
            if project.get('test_kind') == 'ui':
                project['mcp_progress'] = app.state.managed_workflow.progress(owner, project, snapshot=snapshot, projects=projects,
                                                                           record_cache=progress_records)
        # A parent visited later may load a legacy child's current record.
        # Reuse those reads so the child and parent do not depend on list order.
        for project in progress_projects:
            progress = project.get('mcp_progress') or {}
            if project.get('test_kind') == 'ui' and any(
                    not unit.get('case_counts_complete', True) and progress_records.get((
                        unit['project_id'], unit['execution_id'],
                        by_id.get(unit['project_id'], {}).get('ui_execution_revision')))
                    for unit in progress.get('modules', [])):
                project['mcp_progress'] = app.state.managed_workflow.progress(owner, project, snapshot=snapshot, projects=projects,
                                                                           record_cache=progress_records)
        from .progress_view import report_projects
        by_id, hidden = report_projects([by_id[p['id']] for p in projects])
        return sorted((project for pid, project in by_id.items()
                       if pid not in hidden and (project_id is None or pid == project_id)),
                      key=lambda project: project.get('updated_at', ''), reverse=True)

    def canonical_ui_project(owner, project_id):
        project = store.get_project(owner, project_id)
        seen = set()
        while project.get('regression_source', {}).get('project_id') and project['id'] not in seen:
            seen.add(project['id'])
            project = store.get_project(owner, project['regression_source']['project_id'])
        return project

    def latest_ui_report(owner, source):
        candidates = [source]
        candidates.extend(project for project in store.list_projects(owner)
                          if project.get('regression_source', {}).get('project_id') == source['id'] or project.get('managed_parent_project_id') == source['id'])
        entries = [(entry.get('created_at', ''), project, entry)
                   for project in candidates for entry in project.get('analysis_reports', [])]
        return max(entries, default=(None, source, None), key=lambda item: item[0])[1:]

    @app.get("/api/ui-tests")
    def ui_tests(request: Request):
        return {"projects": [project for project in ui_projects(request.state.owner)
                              if project.get("test_kind") == "ui"]}

    @app.post("/api/ui-tests")
    @serialized
    def create_ui_test(request: Request, data: dict):
        owner = request.state.owner
        ensure_idle(owner)
        account_project_id = data.get('account_project_id')
        if not account_project_id:
            raise ValueError('请选择测试所属项目；暂无项目时请先添加项目并填写产品登录地址')
        account_project = orchestration.account_projects.get(owner, account_project_id)
        if not data.get('target_url') and not account_project.get('login_url'):
            raise ValueError('所选项目尚未配置产品登录地址，请先在配置项目中补齐')
        target = ui_target(data.get('target_url') or account_project['login_url'])
        title = data.get("title", "")
        goal = data.get("goal", "")
        attachments = ui_attachments.prepare(data.get('attachments', []))
        if not isinstance(goal, str) or len(goal) > 30000:
            raise ValueError("测试目标必须是文本，最多 30000 字符")
        goal = goal.strip() or ('按上传的测试要求附件完成本轮测试。' if attachments else
                               '对目标页面开展完整的功能探索测试，验证业务流程、异常分支和关联结果，记录可复现缺陷与证据。')
        permission = ui_execution_permission(data.get('execution_permission'))
        scene_retention = ui_scene_retention(data.get('scene_retention'))
        document = ("# UI 测试任务\n\n"
                    f"- 目标页面：{target}\n"
                    f"- 测试目标：{goal.strip()}\n"
                    f"- 执行权限范围：{permission['label']}（{permission['key']}）\n"
                    f"- 授权说明：{permission['description']}\n\n"
                    "先探索目标页面，结合可选资料保存具体用例，再执行并记录真实步骤、结果、证据和缺陷。")
        project = store.create_project(owner, title, "ui-test.md", document,
                                       _before_create=getattr(request.state, 'workflow_before_create', None))
        store.save_asset(owner, project["id"], "contract", {
            "schema_version": "1.0", "title": title, "operations": {}, "sources": {}, "issues": []})
        project = store.update_project(owner, project["id"], {
            "test_kind": "ui", "ui_target_url": target,
            "ui_execution_permission": permission,
            "ui_scene_retention": scene_retention,
            "task": {"goal": goal.strip(), "environment": "auto", "base_url": ""},
            "contract_summary": {"operations": 0, "issues": 0}, "last_job": {}})
        if attachments:
            try:
                project = ui_attachments.save(store, owner, project['id'], attachments)
            except Exception:
                shutil.rmtree(store.project_dir(owner, project['id']))
                raise
        if account_project_id:
            orchestration.account_projects.bind(owner, project["id"], account_project_id)
        return {"project": project}

    @app.post('/api/requirement-tests')
    @serialized
    def create_requirement_test(request: Request, data: dict):
        owner = request.state.owner
        ensure_idle(owner)
        content, filename = data.get('content', ''), data.get('filename', 'requirements.md')
        if data.get('document_kind', 'auto') not in {'auto', 'api', 'requirements'}:
            raise ValueError('document_kind 仅支持 auto/api/requirements')
        if not isinstance(content, str) or not isinstance(filename, str) or not content.strip():
            raise ValueError('请提供需求原文和文件名')
        check_document(content, filename)
        if data.get('document_kind', 'auto') == 'api' or (data.get('document_kind', 'auto') == 'auto' and requirement_design.classify(content, filename) == 'api'):
            result = import_project(request, {**data, 'task': {'goal': data.get('goal') or '根据接口文档设计并执行测试'}})
            return {**result, 'document_kind': 'api', 'workspace_url': '/api-testing'}
        account_project_id = data.get('account_project_id')
        if not account_project_id:
            raise ValueError('请选择测试所属项目；暂无项目时请先添加项目并填写产品登录地址')
        account_project = orchestration.account_projects.get(owner, account_project_id)
        if not data.get('target_url') and not account_project.get('login_url'):
            raise ValueError('所选项目尚未配置产品登录地址，请先在配置项目中补齐')
        target = ui_target(data.get('target_url') or account_project['login_url'])
        goal = test_checkpoints.text(data.get('goal') or '结合需求文档探索目标页面，设计完整具体用例并执行测试。', 'goal', 30000, True)
        prepared = ui_attachments.prepare(data.get('attachments', []))
        project = store.create_project(owner, data.get('title') or Path(filename).stem, filename, content,
                                       _before_create=getattr(request.state, 'workflow_before_create', None))
        pid = project['id']
        store.save_asset(owner, pid, 'contract', {'schema_version': '1.0', 'title': project['title'],
                          'operations': {}, 'sources': {}, 'issues': []})
        design = requirement_design.initial(content)
        store.save_asset(owner, pid, 'requirement-design', design)
        project = store.update_project(owner, pid, {'test_kind': 'ui', 'document_kind': 'requirements',
            'ui_target_url': target, 'ui_execution_permission': ui_execution_permission(data.get('execution_permission')),
            'ui_scene_retention': ui_scene_retention(data.get('scene_retention')),
            'task': {'goal': goal, 'environment': 'auto', 'base_url': normalize_base_url(data['base_url']) if data.get('base_url') else ''},
            'contract_summary': {'operations': 0, 'issues': 0}, 'last_job': {}})
        if prepared:
            try:
                project = ui_attachments.save(store, owner, pid, prepared)
            except Exception:
                shutil.rmtree(store.project_dir(owner, pid))
                raise
        if account_project_id:
            orchestration.account_projects.bind(owner, pid, account_project_id)
        return {'project': project, 'document_kind': 'requirements', 'workspace_url': '/ui-testing', 'design': design}

    @app.get('/api/ui-tests/{project_id}/requirements')
    def requirement_inventory(request: Request, project_id: str):
        return requirement_design.view(store, request.state.owner, project_id)

    @app.put('/api/ui-tests/{project_id}/requirements')
    def save_requirement_inventory(request: Request, project_id: str, data: dict):
        return requirement_design.save(store, request.state.owner, project_id, data.get('revision'), data.get('requirements'), data.get('questions'))

    @app.post('/api/ui-tests/{project_id}/questions/{question_id}')
    def resolve_requirement_question(request: Request, project_id: str, question_id: str, data: dict):
        return requirement_design.resolve(store, request.state.owner, project_id, question_id, data.get('revision'), data.get('resolution'), data.get('basis'))

    @app.put('/api/ui-tests/{project_id}/materials')
    @serialized
    def bind_requirement_materials(request: Request, project_id: str, data: dict):
        owner = request.state.owner
        ensure_idle(owner)
        project = ui_records.ui_project(store, owner, project_id)
        return save_workflow_materials(owner, project, data)

    @app.post('/api/ui-tests/{project_id}/resume')
    def resume_requirement_test(request: Request, project_id: str, data: dict):
        app.state.managed_workflow.assert_idle(request.state.owner,project_id)
        ensure_idle(request.state.owner)
        return requirement_design.resume(store, request.state.owner, project_id, data.get('execution_id'), data.get('revision'),
            data.get('case_ids'), data.get('question_id', ''), data.get('reason', ''), data.get('mode', 'continue'))

    @app.get('/api/ui-tests/{project_id}/capabilities')
    def get_requirement_capabilities(request: Request, project_id: str):
        return test_capabilities.view(store, request.state.owner, project_id)

    @app.put('/api/ui-tests/{project_id}/capabilities')
    def save_requirement_capabilities(request: Request, project_id: str, data: dict):
        return test_capabilities.save(store, request.state.owner, project_id, data.get('revision'), data.get('items'))

    @app.get('/api/ui-tests/{project_id}/executions/{execution_id}/inventory')
    def requirement_case_inventory(request: Request, project_id: str, execution_id: str, offset: int = 0, limit: int = 200):
        from . import ui_asset_withdrawals
        if offset < 0 or not 1 <= limit <= 200:
            raise ValueError('用例分页无效')
        project = store.get_project(request.state.owner, project_id)
        record = ui_records.load(store, request.state.owner, project_id, execution_id)
        active = ui_records.active_cases(record['cases'])
        visible = ui_asset_withdrawals.record_view(store, request.state.owner, record)
        return {**visible, 'cases': active[offset:offset + limit], 'total': len(active),
                'superseded_cases': [c for c in record['cases'] if ui_records.is_superseded(c)],
                'blocking_summary': ui_dependencies.blocking_summary(record),
                'next_offset': offset + limit if offset + limit < len(active) else None,
                'execution_plan': ui_dependencies.plan(record, recovery=ui_dependencies.cached_recovery(project, record))}

    @app.post('/api/ui-tests/{project_id}/executions/{execution_id}/checkpoints/{case_id}/{checkpoint_id}')
    def save_requirement_checkpoint(request: Request, project_id: str, execution_id: str, case_id: str, checkpoint_id: str, data: dict):
        return test_checkpoints.record_result(store, request.state.owner, project_id, execution_id, data.get('revision'),
            case_id, checkpoint_id, data.get('result'))

    @app.post('/api/ui-tests/{project_id}/attachments')
    @app.post('/api/projects/{project_id}/attachments')
    @serialized
    def upload_ui_requirements(request: Request, project_id: str, data: dict):
        owner = request.state.owner
        ensure_idle(owner)
        project = store.get_project(owner, project_id)
        prepared = ui_attachments.prepare(data.get('attachments'), project.get('ui_requirement_attachments', []))
        if not data.get('attachments'):
            raise ValueError('请选择要上传的测试要求附件')
        return {'project': ui_attachments.save(store, owner, project_id, prepared)}

    @app.get('/api/ui-tests/{project_id}/attachments/{attachment_id}')
    @app.get('/api/projects/{project_id}/attachments/{attachment_id}')
    def download_ui_requirement(request: Request, project_id: str, attachment_id: str, preview: bool = False):
        item, path = ui_attachments.locate(store, request.state.owner, project_id, attachment_id)
        return FileResponse(path, filename=item['filename'], media_type=item['content_type'],
                            content_disposition_type='inline' if preview and item['kind'] == 'image' else 'attachment')

    @app.delete('/api/ui-tests/{project_id}/attachments/{attachment_id}')
    @app.delete('/api/projects/{project_id}/attachments/{attachment_id}')
    @serialized
    def delete_ui_requirement(request: Request, project_id: str, attachment_id: str):
        ensure_idle(request.state.owner)
        return {'project': ui_attachments.remove(store, request.state.owner, project_id, attachment_id)}

    @app.post("/api/ui-tests/{project_id}/regressions")
    @serialized
    def create_ui_regression(request: Request, project_id: str, data: dict):
        owner = request.state.owner
        ensure_idle(owner)
        source = canonical_ui_project(owner, project_id)
        if source.get("test_kind") != "ui":
            raise ValueError("请选择 UI 测试会话")
        scope = data.get('regression_scope', 'all')
        if scope is None or scope == '':
            scope = 'all'
        if not isinstance(scope, str) or scope not in {'all', 'failed'}:
            raise ValueError('回归范围仅支持整体回归或错误用例')
        target = ui_target(data.get("target_url") or source.get("ui_target_url", ""))
        default_goal = ('仅回归当前会话各用例最新结果为不通过的用例，复用原设计并重新记录实际结果。'
                        if scope == 'failed' else '整体回归当前会话的全部基线用例，复用原设计并重新记录实际结果。')
        goal = data.get('goal', default_goal)
        if not isinstance(goal, str) or not goal.strip() or len(goal) > 12000:
            raise ValueError("请填写回归目标，最多 12000 字符")
        permission = ui_execution_permission(
            data.get('execution_permission'),
            (source.get('ui_execution_permission') or {}).get('key', 'full'))
        scene_retention = ui_scene_retention(data.get('scene_retention'))
        report_project, latest_entry = latest_ui_report(owner, source)
        latest = latest_entry.get('id') if latest_entry else None
        saved = {}
        if latest:
            saved = store._read(store.project_dir(owner, report_project['id']) / 'analyses' / latest / 'report.json')
            if saved.get('ui_snapshot'):
                saved = ui_report_corrections.apply(saved, ui_report_corrections.load(store, owner, report_project['id'], latest))
        cases = saved.get('ui_snapshot', {}).get('cases') or saved.get('imported_results', {}).get('cases', [])
        case_sources = {}
        if latest:
            from . import ui_total_reports
            # Both scopes start from each case's latest session result, including
            # cases absent from the last partial stage. Filter failed cases only
            # after resolving corrections, legacy sessions and original sources.
            merged_cases = ui_total_reports.build(store, owner, source)['imported_results']['cases']
            if merged_cases:
                cases = merged_cases
                case_sources = {case['case_id']: {
                    'project_id': case['source_report']['project_id'],
                    'report_id': case['source_report']['id']} for case in cases}
        if not cases and source.get('ui_execution_id'):
            cases = ui_records.load(store, owner, source['id'], source['ui_execution_id'])['cases']
        baseline_path = store.project_dir(owner, source['id']) / 'inputs' / 'regression-baseline.json'
        if (source.get('regression_round') or {}).get('scope') in {'failed','selected'} and baseline_path.exists():
            # A focused report must not shrink the next overall regression.
            inventory = {case['case_id']: case for case in store._read(baseline_path).get('cases', [])}
            if case_sources:
                # Retain the session's first-seen order; older material only
                # supplies designs that have no published stage at all.
                inventory = {**{case['case_id']: case for case in cases},
                             **{cid: case for cid, case in inventory.items() if cid not in case_sources}}
            else:
                inventory.update({case['case_id']: case for case in cases})
            cases = list(inventory.values())
        all_cases = cases
        selected = data.get('case_ids')
        if selected is not None:
            if not isinstance(selected,list) or not selected or any(not isinstance(cid,str) for cid in selected) or len(set(selected)) != len(selected):
                raise ValueError('case_ids 必须是非空、无重复的原用例编号列表')
            if set(selected) - {c['case_id'] for c in cases}:
                raise ValueError('所选用例不在原会话基线中')
            cases = [c for c in cases if c['case_id'] in selected]
        if scope == 'failed':
            cases = [case for case in cases if case.get('status') == 'failed']
            if not cases:
                raise ValueError('没有已记录的不通过用例，请选择整体回归')
        scope_ids = [case['case_id'] for case in cases]
        if selected is not None:
            scope = 'selected'
        scope_label = '仅回归错误用例（不通过）' if scope == 'failed' else '整体回归（全部用例）'
        if scope == 'selected':
            scope_label = '所选原用例：' + ', '.join(scope_ids)
        defect_decisions = app.state.pingcode.lifecycle_for_report(owner, report_project['id'], latest) if latest else []
        decisions_by_draft = {item['draft_id']: item for item in defect_decisions}
        defect_lineage = [{
            'case_id': finding.get('case_id', ''), 'source_draft_id': f'finding-{index}',
            'title': finding.get('title', ''), 'lifecycle': decisions_by_draft.get(f'finding-{index}')
        } for index, finding in enumerate(saved.get('findings', [])) if finding.get('case_id')]
        if case_sources:
            defect_decisions, defect_lineage = [], []
            grouped_sources = {}
            for cid, origin in case_sources.items():
                grouped_sources.setdefault((origin['project_id'], origin['report_id']), set()).add(cid)
            for (origin_pid, origin_rid), ids in grouped_sources.items():
                origin_report = store._read(store.project_dir(owner, origin_pid) / 'analyses' / origin_rid / 'report.json')
                origin_report = ui_report_corrections.apply(origin_report, ui_report_corrections.load(
                    store, owner, origin_pid, origin_rid))
                decisions = app.state.pingcode.lifecycle_for_report(owner, origin_pid, origin_rid)
                by_draft = {item['draft_id']: item for item in decisions}
                for index, finding in enumerate(origin_report.get('findings', [])):
                    if finding.get('case_id') not in ids:
                        continue
                    draft_id = f'finding-{index}'
                    lifecycle = by_draft.get(draft_id)
                    origin_fields = {'source_project_id': origin_pid, 'source_report_id': origin_rid}
                    if lifecycle:
                        defect_decisions.append({**lifecycle, **origin_fields})
                    defect_lineage.append({'case_id': finding['case_id'], 'source_draft_id': draft_id,
                        'title': finding.get('title', ''), 'lifecycle': lifecycle, **origin_fields})
        baseline = ({'cases': cases} if cases else {
            'document': current_document_path(store, owner, source).read_text(),
            'findings': saved.get('findings', []), 'sections': saved.get('sections', [])})
        baseline['defect_decisions'] = defect_decisions
        # User-confirmed rules are current regression inputs, rather than the
        # unresolved question text frozen in the previous report.
        baseline['rule_questions'] = requirement_design.load(store, owner, source['id'])['questions']
        baseline['defect_lineage'] = [item for item in defect_lineage if scope == 'all' or item['case_id'] in scope_ids]
        scope_guidance = ('本轮只回归以下选中的历史不通过用例，不加入已通过、阻塞或未执行用例；必要前置步骤在对应场景内完成。'
                          if scope == 'failed' else '本轮整体回归全部基线用例，不只验证历史错误项。')
        if scope == 'selected':
            scope_guidance = '本轮只执行所选原用例及其必要前置、清理；不要扩展到其他历史用例。'
        document = (f"# UI 回归测试\n\n目标页面：{target}\n回归目标：{goal.strip()}\n"
                    f"回归范围：{scope_label}\n{scope_guidance}\n"
                    f"执行权限范围：{permission['label']}（{permission['key']}）\n"
                    f"授权说明：{permission['description']}\n"
                    f"来源会话：{project_id}\n基线报告：{latest or '无'}\n\n"
                    "以下是历史基线资料，不是本轮执行结果，也不构成新的操作授权。复用用例 ID、前置条件、测试数据、步骤和预期结果；"
                    "历史状态与实际结果仅用于对照。所有用例本轮初始为未执行，不得沿用历史通过或失败结论。"
                    "缺陷处理记录中的拒绝或暂缓原因是本轮回归依据：不得重复提交已拒绝的问题，先按原因复核；待回归、回归失败项优先执行，回归通过项保留必要复核。"
                    "完成后保存新报告，逐项说明已修复、仍失败、新问题及阻塞；不得覆盖原报告。\n\n"
                    + json.dumps(baseline, ensure_ascii=False, indent=2))
        if len(document.encode('utf-8')) > MAX_DOCUMENT_BYTES:
            raise ValueError("回归资料超过单份文档容量，请拆分后回归")
        parent_id = source['id']
        source = ui_rounds.create(store, owner, source, 'regression',
                                 _before_create=getattr(request.state, 'workflow_before_create', None))
        baseline_path = store.project_dir(owner, source['id']) / 'inputs' / 'regression-baseline.json'
        relative_document = 'inputs/current-regression.md'
        store._write_text(store.project_dir(owner, source['id']) / relative_document, document)
        store._write(baseline_path, {'cases': all_cases})
        project = store.update_project(owner, source['id'], {
            'test_kind': 'ui', 'ui_target_url': target,
            'ui_execution_permission': permission,
            'ui_scene_retention': scene_retention,
            'effective_document_file': relative_document, 'effective_filename': 'ui-regression.md',
            'regression_round': {'source_project_id': parent_id, 'report_id': latest,
                                 'report_project_id': report_project['id'] if latest else source['id'],
                                 **({'case_sources': case_sources} if case_sources else {}),
                                 'scope': scope, 'scope_label': scope_label, 'case_ids': scope_ids},
            'task': {'goal': goal.strip(), 'environment': 'auto', 'base_url': ''},
            'contract_summary': {'operations': 0, 'issues': 0}, 'last_job': {},
            'ui_execution_id': '', 'ui_retest_round': {}, 'requirements_resume': {},
            'action_continuation': {}, 'status': 'imported'})
        prepared = {}
        if data.get('prepare_execution') and cases:
            designs = ui_records.regression_design(cases)
            for offset in range(0,len(designs),200):
                prepared = ui_records.save_cases(store,owner,project['id'],designs[offset:offset+200],
                    prepared.get('execution_id',''),prepared.get('revision',0))
            project = store.get_project(owner,project['id'])
        visible = next(item for item in ui_projects(owner) if item['id'] == project['id'])
        return {'project': visible, 'regression_round': True,
                **({'prepared_execution': {'execution_id': prepared['execution_id'], 'revision':prepared['revision'],
                    'total':len(cases), 'cases':ui_records.regression_design(cases),
                    'result_template': ui_closeout.result_template(cases),
                    'defect_decisions':defect_decisions}} if prepared else {})}

    def workflow_status(owner, project):
        """Small, stable control-plane view; never returns documents or credentials."""
        from . import ui_finalization
        kind = 'ui' if project.get('test_kind') == 'ui' else 'api'
        execution = app.state.managed_workflow.summary(owner,project['id']) if kind == 'ui' else None
        task = project.get('task', {})
        report_candidates = [item for item in (project.get('last_analysis'), project.get('last_run')) if item]
        latest_report = max(report_candidates, key=lambda item: item.get('created_at', '')) if report_candidates else None
        required = []
        if not str(task.get('goal', '')).strip():
            required.append('goal')
        if kind == 'ui' and not (project.get('ui_target_url') or task.get('base_url')):
            required.append('target_url')
        execution_id = project.get('ui_execution_id') if kind == 'ui' else None
        cases = []
        if execution_id:
            try:
                cases = ui_records.load(store, owner, project['id'], execution_id).get('cases', [])
            except FileNotFoundError:
                execution_id = None
        run = project.get('last_run')
        ready_for_execution = not required and (kind == 'ui' or bool(task.get('base_url')))
        if kind == 'ui' and (project.get('regression_round') or project.get('action_continuation')) and not cases:
            next_action = 'get_test_context'
        elif project.get('last_analysis') and latest_report == project.get('last_analysis'):
            next_action = ('get_ui_test_cases' if kind == 'ui' and any(c.get('status') not in {'passed', 'failed'} for c in cases)
                           else 'get_test_report')
        elif kind == 'ui' and not cases:
            next_action = 'get_test_context'
        elif kind == 'ui':
            next_action = ('save_test_materials' if not ready_for_execution else
                           'publish_ui_test_report' if any(c.get('status') not in {'not_run', ''} for c in cases) else 'execute_saved_ui_cases')
        elif run:
            next_action = 'publish_task_report'
        elif task.get('base_url'):
            next_action = 'get_test_context'
        else:
            next_action = 'get_test_document'
        report_id = latest_report.get('id') if latest_report else ''
        decisions = app.state.pingcode.lifecycle_for_report(owner, project['id'], report_id) if report_id else []
        decision_counts = dict(Counter(item['triage_status'] for item in decisions))
        total = {}
        if kind == 'ui' and latest_report:
            from .ui_total_reports import canonical_project, entry as total_entry
            total = {'total_report': total_entry(canonical_project(store, owner, project))}
        return {
            **total,
            'finalization': ui_finalization.status(project) if kind == 'ui' else None,
            'project_id': project['id'], 'title': project['title'], 'test_kind': kind,
            'goal': task.get('goal', ''), 'target_url': project.get('ui_target_url', ''),
            'execution_permission': project.get('ui_execution_permission') if kind == 'ui' else None,
            'scene_retention': project.get('ui_scene_retention', ui_scene_retention(None)) if kind == 'ui' else None,
            'base_url': task.get('base_url', ''), 'ready_for_design': bool(str(task.get('goal', '')).strip()),
            'ready_for_execution': ready_for_execution,
            'required_inputs': required,
            'attachments': project.get('ui_requirement_attachments', []),
            'progress': execution['progress'] if execution else project.get('mcp_progress'), 'execution_id': execution_id,
            'case_counts': dict(Counter(c.get('status', 'not_run') for c in ui_records.active_cases(cases))) if cases else {},
            'latest_run': run, 'latest_report': latest_report,
            'defect_decisions': decision_counts, 'next_action': next_action,
            **({'managed_execution':execution} if execution else {}),
            **({'document_kind': project.get('document_kind', 'ui'),
                'checkpoint_plan': test_checkpoints.plan(ui_records.load(store, owner, project['id'], execution_id)) if execution_id else {}}
               if kind == 'ui' else {}),
        }

    def save_workflow_materials(owner, project, arguments):
        pid = project['id']
        prepared = ui_attachments.prepare(arguments.get('attachments', []), project.get('ui_requirement_attachments', []))
        task = dict(project.get('task', {}))
        for field in ('goal', 'requirements', 'business_rules', 'test_data'):
            value = arguments.get(field)
            if value is not None:
                task[field] = test_checkpoints.text(value, field, 30000)
        if arguments.get('base_url') is not None:
            task['base_url'] = normalize_base_url(arguments['base_url']) if arguments['base_url'] else ''
        updates = {'task': task}
        if arguments.get('target_url') is not None:
            if project.get('test_kind') != 'ui':
                raise ValueError('target_url 仅适用于 UI/需求会话')
            updates['ui_target_url'] = ui_target(arguments['target_url'])
        old_target = (project.get('ui_target_url', ''), project.get('task', {}).get('base_url', ''))
        new_target = (updates.get('ui_target_url', old_target[0]), task.get('base_url', ''))
        project = store.update_project(owner, pid, updates)
        if old_target != new_target and project.get('ui_execution_id'):
            record = ui_records.load(store, owner, pid, project['ui_execution_id'])
            for case in record['cases']:
                case['dependencies'] = ui_dependencies.normalize(case.get('dependencies', []), case, new_target[0])
                for point in case.get('checkpoints', []):
                    point['dependencies'] = ui_dependencies.normalize(point.get('dependencies', []), case, new_target[0])
                    point['correlation'] = {}
                requirement_design.reset_points(case)
            record['dependency_checks'] = {}
            test_checkpoints.write(store, owner, pid, record)
        if prepared:
            project = ui_attachments.save(store, owner, pid, prepared)
        return {'project': project, 'status': workflow_status(owner, project)}

    @app.get('/api/projects/{project_id}/reports/{run_id}/retest-inputs')
    def retest_inputs(request: Request, project_id: str, run_id: str):
        owner = request.state.owner
        saved = ui_retests.report(store, owner, store.get_project(owner, project_id), run_id)
        return ui_retests.view(store, owner, canonical_ui_project(owner, project_id), run_id, saved)

    @app.get('/api/projects/{project_id}/reports/{run_id}/collaboration')
    def report_collaboration_state(request: Request, project_id: str, run_id: str):
        if not request.state.user:
            raise HTTPException(401, '请先登录')
        owner = request.state.owner
        ui_retests.report(store, owner, store.get_project(owner, project_id), run_id)
        return report_collaboration.view(store, owner, store.get_project(owner, project_id))

    @app.post('/api/projects/{project_id}/reports/{run_id}/collaboration/pair')
    def report_collaboration_pair(request: Request, project_id: str, run_id: str):
        if not request.state.user:
            raise HTTPException(401, '请先登录')
        owner = request.state.owner
        ui_retests.report(store, owner, store.get_project(owner, project_id), run_id)
        source = canonical_ui_project(owner, project_id)
        return mcp_access.issue(owner, project_ids=list({project_id, source['id']}),
                                actor=request.state.user['username'])

    @app.get('/api/projects/{project_id}/reports/{run_id}/rule-questions')
    def report_rule_questions(request: Request, project_id: str, run_id: str):
        owner = request.state.owner
        saved = ui_retests.report(store, owner, store.get_project(owner, project_id), run_id)
        source = canonical_ui_project(owner, project_id)
        return requirement_design.report_questions(store, owner, source['id'], saved)

    @app.post('/api/projects/{project_id}/reports/{run_id}/rule-questions/{question_id}')
    @serialized
    def resolve_report_rule(request: Request, project_id: str, run_id: str, question_id: str, data: dict):
        owner = request.state.owner
        saved = ui_retests.report(store, owner, store.get_project(owner, project_id), run_id)
        source = canonical_ui_project(owner, project_id)
        current = requirement_design.report_questions(store, owner, source['id'], saved)
        if question_id not in {q['id'] for q in current['questions']}:
            raise ValueError('规则问题不属于本报告的用例')
        requirement_design.resolve_report_question(store, owner, source['id'], saved, question_id,
                                                  data.get('revision'), data.get('resolution'), data.get('basis'))
        return requirement_design.report_questions(store, owner, source['id'], saved)

    @app.put('/api/projects/{project_id}/reports/{run_id}/retest-inputs')
    def save_retest_inputs(request: Request, project_id: str, run_id: str, data: dict):
        owner = request.state.owner
        project = store.get_project(owner, project_id)
        saved = ui_retests.report(store, owner, project, run_id)
        return ui_retests.save(store, owner, canonical_ui_project(owner, project_id), run_id, saved, data)

    @app.post('/api/projects/{project_id}/reports/{run_id}/retests')
    @serialized
    def prepare_retest(request: Request, project_id: str, run_id: str, data: dict):
        owner = request.state.owner
        ensure_idle(owner)
        project = store.get_project(owner, project_id)
        saved = ui_retests.report(store, owner, project, run_id)
        source = canonical_ui_project(owner, project_id)
        task = ui_retests.prepare(store, owner, source, project, run_id, saved, data)
        return {'project_id': task['project_id'], 'task': task}

    @app.post("/api/projects/{project_id}/reports/{run_id}/ui-actions/{case_id}")
    @serialized
    def confirm_ui_report_action(request: Request, project_id: str, run_id: str, case_id: str, data: dict):
        """Save report decisions for batching; preserve the legacy continuation API.

        save_only leaves execution ownership untouched. Frozen reports stay immutable.
        """
        owner = request.state.owner
        if not data.get('save_only'):
            ensure_idle(owner)
        report_project = store.get_project(owner, project_id)
        source = canonical_ui_project(owner, project_id)
        saved = ui_retests.report(store, owner, report_project, run_id)
        if run_id == 'total':
            selected_case = next((item for item in saved['imported_results']['cases']
                                  if item['case_id'] == case_id), None)
            if not selected_case:
                raise ValueError('用例不属于本报告')
            origin = selected_case['source_report']
            report_project = store.get_project(owner, origin['project_id'])
            run_id = origin['id']
        source_case = next((item for item in saved.get('imported_results', {}).get('cases', [])
                            if item.get('case_id') == case_id), None)
        action = ui_records.required_action(source_case or {})
        previous_action = report_project.get('action_continuation', {})
        if not action and previous_action.get('report_id') == run_id and previous_action.get('case_id') == case_id:
            action = previous_action.get('resume_context', {}).get('action')
        if not source_case or not action:
            raise ValueError('该用例没有待用户确认的操作')
        if request.state.report_scope:
            if data.get('expected_action') != action:
                raise HTTPException(409, '待确认操作已变化，请刷新报告后核对再确认')
            if saved.get('report_type') == 'total':
                expected_origin = source_case.get('source_report', {})
                supplied = data.get('source_report') or {}
                if any(supplied.get(key) != expected_origin.get(key) for key in ('project_id', 'id')):
                    raise HTTPException(409, '此用例已有新的阶段结果，请刷新报告后确认')
        expected = 'authorized' if action['type'] == 'authorization' else 'completed'
        if data.get('decision') != expected:
            raise ValueError('确认状态无效')
        if saved.get('aggregate'):
            project_reports.validate(owner, saved['project_id'], request.headers.get('x-project-revision', ''))
            source_case = {**source_case, 'case_id': source_case['source_report']['case_id']}
            source = canonical_ui_project(owner, report_project['id'])
            original_saved = ui_retests.report(store, owner, report_project, run_id)
            current_case = next((c for c in original_saved.get('imported_results', {}).get('cases', [])
                                 if c['case_id'] == source_case['case_id']), None)
            if not current_case or ui_records.required_action(current_case) != action:
                raise HTTPException(409, '原用例待确认事项已变化，请刷新')
            if not data.get('save_only'):
                raise HTTPException(400, '请先保存确认，再在来源会话继续测试')
        if data.get('save_only'):
            return ui_retests.confirm_action(store, owner, source, run_id, source_case, action, expected,
                                            (request.state.user or {}).get('username', ''))
        # Continue the task that owns this report, including a regression child.
        source = report_project
        continuation = source.get('action_continuation', {})
        if (continuation.get('report_project_id') == report_project['id'] and continuation.get('report_id') == run_id
                and continuation.get('case_id') == case_id and continuation.get('decision') == expected
                and continuation.get('resume_context', {}).get('action', action) == action):
            visible = next(item for item in ui_projects(owner) if item['id'] == source['id'])
            return {'project': visible, 'workspace_url': '/ui-testing', 'decision': expected, 'reused': True}
        if (source.get('status') == 'imported' and continuation
                and source.get('effective_document_file') == 'inputs/current-action-continuation.md'):
            raise HTTPException(409, '已有待继续的确认任务，请先完成该任务后再确认另一条用例')
        if (source.get('mcp_progress') or {}).get('phase') in {'executing', 'reporting'}:
            raise HTTPException(409, '当前会话正在执行，请完成后再确认另一条用例')
        active_id = source.get('ui_execution_id')
        if active_id:
            active = ui_records.load(store, owner, source['id'], active_id)
            if not active.get('report_id'):
                raise HTTPException(409, '当前会话仍有未完成的执行，请完成后再确认另一条用例')
        decided_at = ui_records.now()
        source_snapshot = ui_retests.report(store, owner, report_project, run_id).get('ui_snapshot', {})
        decision_label = '已明确授权' if expected == 'authorized' else '已完成人工步骤'
        target = ui_target(source.get('ui_target_url', ''))
        baseline = {key: source_case.get(key, '') for key in ui_records.FIELDS if key not in {'status', 'actual', 'executed_at'}}
        baseline.update(status='not_run', actual='', executed_at='', action_type='', action_required='',
                        dependencies=source_case.get('dependencies', []))
        baseline['action_context'] = copy.deepcopy(action.get('context') or source_case.get('action_context', {}))
        for key in ('requirement_ids', 'question_ids', 'checkpoints'):
            baseline[key] = copy.deepcopy(source_case.get(key, []))
        for point in baseline['checkpoints']:
            if point.get('status') in {'passed', 'failed'}:
                point['inherited_from'] = {'execution_id': source_snapshot.get('id', ''),
                                          'report_id': run_id, 'note': '原现场前序观察，继续轮次未重复执行'}
            if point.get('id') == action.get('checkpoint_id'):
                point.update(status='not_run', actual='', evidence=[], action_required='')
        resume_context = {'action': action, 'source_report_id': run_id,
                          'source_execution_id': source_snapshot.get('id', '')}
        document = (f"# UI 测试继续任务\n\n目标页面：{target}\n来源会话：{project_id}\n"
                    f"来源报告：{run_id}\n用例：{case_id} · {source_case.get('scenario', '')}\n\n"
                    "## 已持久化的用户操作\n\n"
                    f"- 状态：{decision_label}\n- 要求：{action['prompt']}\n- 时间：{decided_at}\n\n"
                    "这是用户在报告中明确完成的操作状态，不得再以“未获得用户确认”标记阻塞。"
                    "执行前仍应核对当前对象、环境与影响范围；如对象已变更或风险超出原确认范围，记录新事实。"
                    "优先复用下方原浏览器标签和操作链接，核对原对象的人工操作成功状态后从暂停步骤继续；不要从首页重跑已完成步骤。"
                    "确认完成只表示用户已操作，不等于业务成功；扫码失效时先恢复原现场，不能重复创建订单或付款。"
                    "保留前序观察来源，无法恢复时说明具体缺口，不猜测页面。\n\n"
                    "## 原操作现场与暂停位置\n\n" + json.dumps(resume_context, ensure_ascii=False, indent=2) + "\n\n"
                    "本轮继续基线已保存，先用 get_ui_test_cases 读取，不重建用例或前序步骤。\n\n"
                    "## 本轮用例\n\n" + json.dumps({'cases': [baseline]}, ensure_ascii=False, indent=2))
        relative_document = 'inputs/current-action-continuation.md'
        store._write_text(store.project_dir(owner, source['id']) / relative_document, document)
        # Prepare a continuation, not a fresh execution of the completed prefix.
        snapshot = source_snapshot
        next_execution_id = snapshot.get('id') or str(uuid.uuid4())
        next_record = {**snapshot, 'id': next_execution_id, 'revision': snapshot.get('revision', 0) + 1,
                       'report_id': run_id,
                       'cases': [baseline if c['case_id'] == case_id else c for c in snapshot.get('cases', [baseline])],
                       'assets': list(snapshot.get('assets', [])),
                       'created_at': snapshot.get('created_at') or decided_at,
                       'coverage': snapshot.get('coverage', []),
                       'dependency_checks': snapshot.get('dependency_checks', {}),
                       'requirement_design': copy.deepcopy(snapshot.get('requirement_design', {})),
                       'scene_retention': source.get('ui_scene_retention'),
                       'continuation': resume_context}
        next_root = ui_records.root_for(store, owner, source['id'], next_execution_id)
        next_root.mkdir(parents=True, exist_ok=True)
        if snapshot.get('id'):
            old_root = ui_records.root_for(store, owner, report_project['id'], snapshot['id'])
            for asset in snapshot.get('assets', []):
                if old_root != next_root and (old_root / asset['id']).is_file():
                    shutil.copyfile(old_root / asset['id'], next_root / asset['id'])
        store._write(next_root / 'cases.json', next_record)
        project = store.update_project(owner, source['id'], {
            'test_kind': 'ui', 'ui_target_url': target,
            'effective_document_file': relative_document, 'effective_filename': 'ui-action-continuation.md',
            'action_continuation': {'report_project_id': report_project['id'], 'report_id': run_id,
                                    'case_id': case_id, 'decision': expected, 'decided_at': decided_at,
                                    'resume_context': resume_context,
                                    'actor': (request.state.user or {}).get('username', '')},
            'task': {'goal': f'继续执行已确认的用例 {case_id}，保存真实结果与证据。',
                     'environment': 'auto', 'base_url': ''},
            'contract_summary': {'operations': 0, 'issues': 0}, 'last_job': {},
            'ui_execution_id': next_execution_id, 'ui_retest_round': {}, 'status': 'imported'})
        ui_records.refresh_published(store, owner, source['id'], next_record)
        visible = next(item for item in ui_projects(owner) if item['id'] == project['id'])
        return {'project': visible, 'workspace_url': '/ui-testing', 'decision': expected}
    @app.post('/api/projects/{project_id}/reports/{run_id}/case-corrections/{case_id}')
    @serialized
    def correct_report_case(request: Request, project_id: str, run_id: str, case_id: str, data: dict):
        """Correct published case presentation without changing frozen execution evidence."""
        owner = request.state.owner
        project = store.get_project(owner, project_id)
        if run_id == 'total':
            saved = ui_retests.report(store, owner, project, run_id)
            case = next((c for c in saved['imported_results']['cases'] if c['case_id'] == case_id), None)
            if not case:
                raise HTTPException(404, '用例不存在')
            origin = case['source_report']
            supplied = data.get('source_report') or {}
            if any(supplied.get(key) != origin[key] for key in ('project_id', 'id')):
                raise HTTPException(409, '此用例已有新的阶段结果，请刷新总报告后修改')
            if project.get('business_project'):
                project_reports.validate(owner, project['id'], request.headers.get('x-project-revision', ''))
                if not origin.get('editable'):
                    raise HTTPException(400, '该来源不支持用例更正，请查看原执行证据')
            case_id = origin.get('case_id', case_id)
            project_id, run_id = origin['project_id'], origin['id']
            project = store.get_project(owner, project_id)
        ui_retests.report(store, owner, project, run_id)
        report = store._read(store.project_dir(owner, project_id) / 'analyses' / run_id / 'report.json')
        record = ui_report_corrections.save(store, owner, project_id, run_id, report,
                                            case_id, data.get('fields'), data.get('revision'),
                                            actor=(request.state.user or {}).get('username') or (request.state.mcp_scope or {}).get('actor', ''))
        effective = ui_report_corrections.apply(report, record)
        return {'revision': record['revision'], 'case': record['cases'][case_id],
                'summary': effective['summary']}

    @app.post('/api/projects/{project_id}/reports/{run_id}/title-corrections')
    @serialized
    def correct_defect_titles(request: Request, project_id: str, run_id: str, data: dict):
        for draft_id in data.get('draft_ids', []):
            app.state.defect_batches.assert_available(request, project_id, run_id, draft_id)
        owner = request.state.owner
        project = store.get_project(owner, project_id)
        if run_id == 'total':
            raise HTTPException(400, '请修改缺陷对应的来源阶段报告')
        ui_retests.report(store, owner, project, run_id)
        report = store._read(store.project_dir(owner, project_id) / 'analyses' / run_id / 'report.json')
        return ui_report_corrections.save_titles(store, owner, project_id, run_id, report,
            data.get('draft_ids'), data.get('attributes'), data.get('revision'),
            actor=(request.state.user or {}).get('username', ''))

    @app.post('/api/projects/{project_id}/reports/{run_id}/report-corrections')
    @serialized
    def correct_report_text(request: Request, project_id: str, run_id: str, data: dict):
        owner = request.state.owner
        project = store.get_project(owner, project_id)
        if run_id == 'total':
            raise HTTPException(400, '总报告总结由阶段结果自动汇总，请修改来源阶段报告')
        ui_retests.report(store, owner, project, run_id)
        report = store._read(store.project_dir(owner, project_id) / 'analyses' / run_id / 'report.json')
        record = ui_report_corrections.save_report(store, owner, project_id, run_id, report,
                                                   data.get('fields'), data.get('revision'),
                                                   actor=(request.state.user or {}).get('username') or (request.state.mcp_scope or {}).get('actor', ''))
        effective = ui_report_corrections.apply(report, record)
        return {'revision': record['revision'], 'report': record['report'],
                'title': effective['title'], 'summary': effective['summary']}

    @app.post("/api/ui-tests/import-results")
    def import_ui_results(request: Request, data: dict):
        owner = request.state.owner
        ensure_idle(owner)
        filename, encoded = data.get("filename", ""), data.get("content_base64", "")
        if (not isinstance(filename, str) or not filename.lower().endswith(".xlsx") or len(filename) > 255
                or any(character in filename for character in ("/", "\\", "\x00"))):
            raise ValueError("请选择有效的 .xlsx 文件")
        if not isinstance(encoded, str) or not encoded:
            raise ValueError("请选择非空的 XLSX 文件")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("XLSX 文件内容无效") from error
        environment = data.get("environment", "")
        client = data.get("client", "")
        parsed = parse_xlsx_results(content, environment=environment if isinstance(environment, str) else "",
                                    client=client if isinstance(client, str) else "")
        from .defect_title import attributes
        environment, client, _ = attributes(environment, client)
        title = data.get("title") or Path(filename).stem
        if not isinstance(title, str) or not title.strip() or len(title) > 200:
            raise ValueError("报告名称必须是 1–200 个字符")
        target = data.get("target_url", "")
        if target:
            target = ui_target(target)
        counts = parsed["counts"]
        quality = parsed["quality"]
        goal = f"查看从 {filename} 导入的 UI 测试结果，并审核失败用例后提交 PingCode。"
        document = ("# UI 测试结果导入\n\n"
                    f"- 来源文件：{filename}\n- 工作表：{parsed['sheet_name']}\n"
                    f"- 总用例：{counts['total']}\n- 通过：{counts['passed']}\n"
                    f"- 失败：{counts['failed']}\n- 阻塞：{counts['blocked']}\n")
        project = store.create_project(owner, title.strip(), "ui-xlsx-import.md", document)
        store.save_asset(owner, project["id"], "contract", {
            "schema_version": "1.0", "title": title.strip(), "operations": {}, "sources": {}, "issues": []})
        project = store.update_project(owner, project["id"], {
            "test_kind": "ui", "ui_target_url": target, "ui_import_filename": filename,
            "ui_report_context": {"environment": environment.strip(), "client": client.strip()},
            "task": {"goal": goal, "environment": "auto", "base_url": ""},
            "contract_summary": {"operations": 0, "issues": 0}, "last_job": {}})
        labels = {"passed": "通过", "failed": "失败", "blocked": "阻塞", "not_run": "未执行",
                  "skipped": "跳过", "other": "其他", "partial": "验证未完成",
                  "pending_rule": "待确认规则", "pending_action": "待用户确认"}
        summary = (f"已从“{parsed['sheet_name']}”工作表导入 {counts['total']} 条测试用例："
                   + "、".join(f"{labels[key]} {counts[key]} 条" for key in labels if counts.get(key)) + "。"
                   + ("失败用例已生成待审核的 PingCode 缺陷草稿；报告页面仅展示结果总结和这些草稿。" if counts['failed'] else
                      "本次没有失败用例，因此未生成缺陷草稿。"))
        findings = result_findings(parsed)
        if counts["failed"] > len(findings):
            summary += f" 当前报告最多生成 200 个缺陷草稿。"
        saved = save_task_report(store, owner, project, {
            "title": f"{title.strip()} · 测试结果",
            "summary": summary,
            "sections": [{"title": "导入说明", "content":
                          f"来源文件：{filename}\n工作表：{parsed['sheet_name']}\n表头行：第 {parsed['header_row']} 行"}],
            "findings": findings,
            "run_ids": [],
            "imported_results": {"filename": filename, **parsed},
        })
        refreshed = store.get_project(owner, project["id"])
        return {"project": refreshed, "report": saved["report"], "counts": counts, "quality": quality}

    @app.post("/api/projects")
    def import_project(request: Request, data: dict):
        owner = request.state.owner
        ensure_idle(owner)
        prepared = ui_attachments.prepare(data.get('attachments', []))
        filename, content = data.get("filename", "document.md"), data.get("content", "")
        if not isinstance(filename, str) or not isinstance(content, str):
            raise ValueError("文档名称和内容必须为文本")
        if not content.strip() or len(content.encode("utf-8")) > MAX_DOCUMENT_BYTES:
            raise ValueError(f"请提供非空文档，单份不超过 {DOCUMENT_LIMIT_LABEL}")
        targets = extract_targets(data)
        task_data = data.get("task", {})
        if not isinstance(task_data, dict):
            raise ValueError("任务配置必须为对象")
        task_data = dict(task_data)
        if "base_url" not in task_data and targets["candidates"]:
            task_data["base_url"] = targets["candidates"][0]["url"]
        task = task_config(task_data)
        template = data.get("template")
        if template not in TEMPLATES or content != TEMPLATES[template]["file"].read_text():
            template = None
        title = data.get("title") or Path(filename).stem
        extension = Path(filename).suffix.lower()
        if extension not in {".md", ".markdown", ".yaml", ".yml", ".json"}:
            raise ValueError("请选择 Markdown、JSON 或 YAML 文档")
        with tempfile.TemporaryDirectory(prefix="api-test-import-") as temporary:
            path = Path(temporary) / ("document" + extension)
            path.write_text(content, encoding="utf-8")
            try:
                check_document(content, filename)
                contract = _portable_sources(parse_document(path))
            except (ValueError, KeyError, TypeError, RecursionError) as exc:
                if data.get("allow_unparsed", getattr(request.state, "mcp", False)) is not True:
                    raise
                contract = {"schema_version": "1.0", "title": title, "operations": {}, "sources": {},
                    "issues": [{"code": "DOCUMENT_REVIEW_REQUIRED", "severity": "warning",
                                "message": "原文已保存，可交给 Codex 分析。自动解析提示：" + str(exc)[:500]}]}
                add_source(contract["sources"], path, "document", content, "document")
                _portable_sources(contract)
        project = store.create_project(owner, title, filename, content, template,
                                       _before_create=getattr(request.state, 'workflow_before_create', None))
        store.save_asset(owner, project["id"], "contract", contract)
        store.update_project(owner, project["id"], {"task": task, "document_targets": targets, "api_profile_id": store.list_profiles(owner)["active_id"], "contract_summary": {"operations": len(contract["operations"]), "issues": len(contract["issues"])}})
        if prepared:
            try:
                ui_attachments.save(store, owner, project['id'], prepared)
            except Exception:
                shutil.rmtree(store.project_dir(owner, project['id']))
                raise
        return {"project": store.get_project(owner, project["id"]), "contract": contract,
                "contract_revision": contract_revision(contract)}

    @app.get("/api/deleted-projects")
    def deleted_projects(request: Request):
        return {"projects": app.state.managed_workflow.controller.sessions.trash(request.state.owner)}

    @app.patch("/api/projects/{project_id}/title")
    @serialized
    def rename_project(request: Request, project_id: str, data: dict):
        title = data.get("title")
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > 120:
            raise ValueError("会话名称须为 1–120 个字符")
        project = store.update_project(request.state.owner, project_id, {"title": title.strip()})
        return {"project": project}

    @app.delete("/api/projects/{project_id}")
    @serialized
    def delete_project(request: Request, project_id: str):
        ensure_idle(request.state.owner)
        _, cleanup = app.state.managed_workflow.controller.sessions.recycle(request.state.owner, project_id)
        return {"deleted": True, "cleanup": cleanup, "projects": store.list_projects(request.state.owner)}

    @app.post("/api/deleted-projects/purge")
    @serialized
    def purge_deleted_projects(request: Request, data: dict):
        ensure_idle(request.state.owner)
        if data.get("confirm") is not True:
            raise ValueError("请确认彻底删除；会话中的文档、用例和报告将无法恢复")
        ids = data.get("project_ids")
        with admission_lock:
            if isinstance(ids, list) and any(project_writes.get((request.state.owner, pid), 0) for pid in ids if isinstance(pid, str)):
                raise HTTPException(409, "所选会话仍有保存或推送操作，请等待完成后重试")
        deleted = app.state.managed_workflow.controller.sessions.purge(request.state.owner, data.get("project_ids"))
        with jobs_lock:
            for jid, job in list(jobs.items()):
                if job["owner"] == request.state.owner and job.get("project_id") in deleted:
                    del jobs[jid]
        return {"deleted_ids": deleted, "projects": store.list_projects(request.state.owner, deleted=True)}

    @app.post("/api/projects/{project_id}/restore")
    @serialized
    def restore_project(request: Request, project_id: str):
        ensure_idle(request.state.owner)
        project, _ = app.state.managed_workflow.controller.sessions.recycle(request.state.owner, project_id, restore=True)
        return project

    @app.post("/api/projects/{project_id}/operations")
    @serialized
    def add_operation(request: Request, project_id: str, data: dict):
        return edit_operations(request, project_id, data)

    @app.delete("/api/projects/{project_id}/operations/{operation_id:path}")
    @serialized
    def delete_operation(request: Request, project_id: str, operation_id: str, data: dict):
        return edit_operations(request, project_id, data, operation_id)

    @app.patch("/api/projects/{project_id}/operations/{operation_id:path}")
    @serialized
    def update_operation(request: Request, project_id: str, operation_id: str, data: dict):
        return edit_operations(request, project_id, data, edit_id=operation_id)

    def edit_operations(request, pid, data, delete_id=None, edit_id=None):
        owner = request.state.owner
        ensure_idle(owner)
        project = store.get_project(owner, pid)
        contract = store.load_asset(owner, pid, "contract")
        if data.get("revision") != contract_revision(contract):
            raise HTTPException(409, "接口列表已更新，请刷新后重试")
        change_operation(store, owner, project, data.get("operation"), delete_id, edit_id)
        return project_details(request, pid)

    @app.get("/api/projects/{project_id}/progress")
    def project_progress_view(request: Request, project_id: str):
        from .progress_view import current_progress
        owner = request.state.owner
        project = store.get_project(owner, project_id)
        result = current_progress(app.state.managed_workflow, owner, project)
        result['connection'] = mcp_access.status(owner)
        return JSONResponse(result, headers={'Cache-Control': 'no-store'})

    @app.get("/api/projects/{project_id}")
    @serialized
    def project_details(request: Request, project_id: str):
        owner = request.state.owner
        project = store.get_project(owner, project_id)
        if project.get('test_kind') == 'ui':
            visible = next(iter(ui_projects(owner, project_id=project_id)), None)
            project = visible or {**project, 'mcp_progress': app.state.managed_workflow.progress(owner,project)}
            from .progress_view import details_version
            project['ui_details_version'] = details_version(store, owner, project_id)
        result = {"project": project, "contract": store.load_asset(owner, project_id, "contract")}
        result["contract_revision"] = contract_revision(result["contract"])
        try:
            result["bundle"] = decorate_bundle(project, store.load_asset(owner, project_id, "bundle"))
            result["bundle_revision"] = bundle_revision(result["bundle"])
        except FileNotFoundError:
            result["bundle"] = None
            result['bundle_revision'] = bundle_revision({})
        try: removed = store.load_asset(owner, project_id, 'deleted-cases').get('items', [])
        except FileNotFoundError: removed = []
        result['deleted_cases'] = [{'id': item['id'], 'title': item['case']['title'], 'deleted_at': item['deleted_at']} for item in removed]
        return result

    @app.put("/api/projects/{project_id}/task")
    @serialized
    def update_task(request: Request, project_id: str, data: dict):
        app.state.managed_workflow.assert_idle(request.state.owner,project_id)
        ensure_idle(request.state.owner)
        project = store.get_project(request.state.owner, project_id)
        updates = {"task": task_config({**project.get("task", {}), **data})}
        if project.get('test_kind') == 'ui' and 'scene_retention' in data:
            selected = ui_scene_retention(data['scene_retention'])
            execution_id = project.get('ui_execution_id')
            if execution_id:
                recorded = ui_records.load(store, request.state.owner, project_id, execution_id)
                if recorded.get('scene_retention', ui_scene_retention(None))['key'] != selected['key']:
                    raise ValueError('本轮已有执行记录，测试现场保留范围不能再更改；请在下一轮选择')
            updates['ui_scene_retention'] = selected
        updated = store.update_project(request.state.owner, project_id, updates)
        try:
            bundle = decorate_bundle(updated, store.load_asset(request.state.owner, project_id, "bundle"))
        except FileNotFoundError:
            pass
        else:
            store.save_asset(request.state.owner, project_id, "bundle", bundle)
            updated = store.update_project(request.state.owner, project_id, {"bundle_summary": _summary(bundle)})
        if data.get("restart_progress") is True:
            store.update_project(request.state.owner, project_id, {"mcp_progress": {}})
            record_progress(store, request.state.owner, project_id, "waiting", "任务已准备，等待 Codex 接手")
            updated = store.get_project(request.state.owner, project_id)
        return updated

    @app.put("/api/projects/{project_id}/api")
    def select_session_api(request: Request, project_id: str, data: dict):
        owner = request.state.owner
        ensure_idle(owner)
        store.get_project(owner, project_id)
        pid = data.get("api_profile_id")
        if not isinstance(pid, str) or pid not in {item["id"] for item in store.list_profiles(owner)["items"]}:
            raise HTTPException(404, "API 配置不存在")
        store.update_project(owner, project_id, {"api_profile_id": pid})
        return store.get_project(owner, project_id)

    @app.post("/api/projects/{project_id}/generate")
    @serialized
    def generate(request: Request, project_id: str, data: dict):
        owner = request.state.owner
        project = store.get_project(owner, project_id)
        if project.get('case_workflow') == 'own':
            raise ValueError('当前选择仅执行自己的用例，请导入用例或切换到 AI 生成方式')
        try:
            existing = store.load_asset(owner, project_id, 'bundle')
        except FileNotFoundError:
            existing = {}
        append = bool(existing.get('cases')) and (project.get('case_workflow') in {'import_ai', 'ai_import'} or
            any(c.get('web', {}).get('source') == 'user' for c in existing['cases']))
        prefix = 'ADD-' + uuid.uuid4().hex[:8] + '-'
        def combined(bundle):
            if append:return append_generated(existing, bundle, prefix, 'ai' if mode == 'model' else 'rules')
            for case in bundle['cases']:case.setdefault('web', {})['source'] = 'ai' if mode == 'model' else 'rules'
            return bundle
        mode = data.get("mode", "auto")
        if mode not in {"auto", "baseline", "model"}:
            raise ValueError("未知生成方式")
        if mode == "baseline" and (not project.get("template") or project.get("interfaces_modified")):
            raise ValueError("内置方案仅用于未修改的示例文档")
        config = model_config(owner, project.get("api_profile_id")) if mode == "model" else None
        supplement = data.get("supplement", "")
        if not isinstance(supplement, str) or len(supplement) > 12000:
            raise ValueError("补充规则最多 12000 字符")

        def work(progress):
            nonlocal existing, prefix
            contract = store.load_asset(owner, project_id, "contract")
            if not contract.get("operations"):
                raise ValueError("没有识别到接口，请使用 OpenAPI 3 或内置示例的 Markdown 表格格式重新导入")
            progress("正在整理文档中的接口和规则依据")
            if mode == "baseline":
                bundle = generate_bundle(contract, REPO / "examples" / project["template"] / "rules.yaml")
            elif mode == "auto":
                bundle = auto_bundle(contract)
            else:
                if supplement.strip():
                    path = store.project_dir(owner, project_id) / "inputs/supplement.md"
                    path.write_text(supplement)
                    add_source(contract["sources"], path, "document", supplement, "user_requirement")
                document = current_document_path(store, owner, project).read_text()
                fingerprint = hashlib.sha256(json.dumps({"contract": contract, "document": document,
                    "supplement": supplement, "model": config.model, "protocol": config.protocol,
                    "base_url": config.base_url, "max_tokens": config.max_tokens},
                    sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                try:
                    saved = store.load_asset(owner, project_id, "model-plan")
                except FileNotFoundError:
                    saved = {}
                state = saved.get("state") if saved.get("fingerprint") == fingerprint else None
                if state and state.get("complete"):
                    state = None
                if state:
                    existing = saved.get('base_bundle', existing)
                    prefix = saved.get('id_prefix', prefix)
                def checkpoint(state):
                    store.save_asset(owner, project_id, "model-plan", {"fingerprint": fingerprint, "state": state,
                        'base_bundle': existing, 'id_prefix': prefix})
                    if state["cases"]:
                        partial = compile_model_bundle(contract, json.dumps({"schema_version": "1.0", "cases": state["cases"]}, ensure_ascii=False))
                        partial = decorate_bundle(project, combined(partial))
                        partial["generation"].update(engine="model-staged-v1", partial=True,
                            design_count=len(state["cases"]), processed_count=len(state["compiled"]))
                        store.save_asset(owner, project_id, "bundle", partial)
                        store.update_project(owner, project_id, {"status": "generated", "bundle_summary": _summary(partial), "generation_mode": mode})
                def call_model(system, prompt):
                    return generate_text(config, system, prompt,
                        session_factory=lambda: pinned_session(config.base_url, tuple(trusted_model_origins if testing else ())), on_progress=progress)
                bundle = generate_plan(contract, document, supplement, call_model,
                    progress=progress, checkpoint=checkpoint, state=state,
                    execution_context={"environment": project_environment(project),
                        "cleanup": "五子棋环境已提供账号清理：variables.username={kind:'unique',prefix:'mvp_'}；注册请求 username 使用 ${username}。" if project_environment(project) == "gomoku" else "使用文档中的清理接口或准确说明无持久副作用"},
                    existing_cases=candidates_from_bundle(existing)['cases'] if append else None)
            bundle = combined(bundle)
            decorate_bundle(project, bundle)
            if mode == "model":
                bundle = refresh_approval_eligibility(bundle)
            _portable_sources(bundle.get("contract", {}))
            check_web_bundle(bundle)
            errors = validate_bundle(bundle)
            if errors:
                raise ValueError("用例静态校验失败：" + "; ".join(e["message"] for e in errors[:3]))
            store.save_asset(owner, project_id, 'contract', bundle['contract'])
            store.save_asset(owner, project_id, "bundle", bundle)
            store.save_asset(owner, project_id, 'mcp-candidates', candidates_from_bundle(bundle))
            summary = _summary(bundle)
            store.update_project(owner, project_id, {"status": "generated", "bundle_summary": summary, "generation_mode": mode})
            progress(f"已生成 {summary['total']} 条用例，{summary.get('READY', 0)} 条可执行")
            return {"summary": summary}
        return begin_job(owner, project_id, "generate", work)

    @app.post("/api/projects/{project_id}/approve")
    @serialized
    def approve(request: Request, project_id: str, data: dict):
        owner = request.state.owner
        ensure_idle(owner)
        project = store.get_project(owner, project_id)
        bundle = decorate_bundle(project, store.load_asset(owner, project_id, "bundle"))
        case_ids = data.get("case_ids", [])
        if not isinstance(case_ids, list) or not case_ids or any(not isinstance(x, str) for x in case_ids):
            raise ValueError("请先选择需要采纳预期的用例")
        note = "Codex 通过 MCP 核对并采纳了这些测试预期" if getattr(request.state, "mcp", False) else "使用者在网页核对并采纳了这些测试预期"
        bundle = approve_cases(bundle, case_ids, note, partial=True)
        check_web_bundle(bundle)
        errors = validate_bundle(bundle)
        if errors:
            raise ValueError("采纳后校验失败：" + errors[0]["message"])
        store.save_asset(owner, project_id, "bundle", bundle)
        store.update_project(owner, project_id, {"bundle_summary": _summary(bundle)})
        return {"bundle": bundle, "summary": _summary(bundle), **bundle["web"]["last_review"]}

    @app.put('/api/projects/{project_id}/case-workflow')
    @serialized
    def set_case_workflow(request: Request, project_id: str, data: dict):
        ensure_idle(request.state.owner)
        store.get_project(request.state.owner, project_id)
        if not isinstance(data.get('mode'), str) or data['mode'] not in WORKFLOWS:raise ValueError('未知用例准备方式')
        store.update_project(request.state.owner, project_id, {'case_workflow': data['mode']})
        return project_details(request, project_id)

    @app.get('/api/projects/{project_id}/editable-cases')
    def editable_cases(request: Request, project_id: str):
        project = store.get_project(request.state.owner, project_id)
        bundle = decorate_bundle(project, store.load_asset(request.state.owner, project_id, 'bundle'))
        return {**candidates_from_bundle(bundle), 'revision': bundle_revision(bundle)}

    @app.post('/api/projects/{project_id}/import-cases')
    @serialized
    def import_user_cases(request: Request, project_id: str, data: dict):
        owner = request.state.owner;ensure_idle(owner)
        project = store.get_project(owner, project_id)
        try:old = decorate_bundle(project, store.load_asset(owner, project_id, 'bundle'))
        except FileNotFoundError:old = {}
        if data.get('revision') != bundle_revision(old):
            raise HTTPException(409, '用例已变化，请刷新后重新导入或编辑')
        contract, incoming = import_candidates(store.load_asset(owner, project_id, 'contract'), data.get('filename', ''), data.get('content'))
        replace_id = data.get('replace_id')
        if replace_id is not None and (len(incoming['cases']) != 1 or incoming['cases'][0]['id'] != replace_id or replace_id not in {c['id'] for c in old.get('cases', [])}):
            raise ValueError('编辑只能替换指定的现有用例')
        bundle = refresh_approval_eligibility(decorate_bundle(project, merge_bundles(old, incoming, replace_id=replace_id)))
        check_web_bundle(bundle)
        errors = validate_bundle(bundle)
        if errors:raise ValueError('导入校验失败：' + errors[0]['message'])
        store.save_asset(owner, project_id, 'contract', bundle['contract'])
        store.save_asset(owner, project_id, 'bundle', bundle)
        store.save_asset(owner, project_id, 'mcp-candidates', candidates_from_bundle(bundle))
        store.update_project(owner, project_id, {'status': 'generated', 'bundle_summary': _summary(bundle),
            'generation_mode': project.get('generation_mode', 'mcp'), 'case_workflow': project.get('case_workflow', 'own')})
        return {**project_details(request, project_id), 'imported_count': len(incoming['cases'])}

    @app.post('/api/projects/{project_id}/cases/remove')
    @serialized
    def remove_case(request: Request, project_id: str, data: dict):
        owner = request.state.owner; ensure_idle(owner)
        project = store.get_project(owner, project_id)
        bundle = decorate_bundle(project, store.load_asset(owner, project_id, 'bundle'))
        if data.get('revision') != bundle_revision(bundle):
            raise HTTPException(409, '用例已变化，请刷新后重新删除')
        case = next((c for c in bundle['cases'] if c['id'] == data.get('case_id')), None)
        if case is None: raise HTTPException(404, '用例已不存在')
        try: archive = store.load_asset(owner, project_id, 'deleted-cases')
        except FileNotFoundError: archive = {'items': []}
        case_rules = [r for r in bundle['rules'] if r['id'] in case.get('rule_ids', [])]
        source_ids = {sid for rule in case_rules for sid in rule.get('source_ids', [])}
        operation_ids = {case['operation_id']} | {step.get('operation_id', case['operation_id']) for step in case.get('steps', []) + case.get('cleanup_steps', [])}
        context = {'operations': {oid: bundle['contract']['operations'][oid] for oid in operation_ids},
                   'sources': {sid: value for sid, value in bundle['contract']['sources'].items() if sid in source_ids}}
        archive['items'].append({'id': uuid.uuid4().hex, 'case': copy.deepcopy(case),
            'rules': copy.deepcopy(case_rules), 'contract': copy.deepcopy(context), 'deleted_at': time.time()})
        bundle['cases'] = [c for c in bundle['cases'] if c['id'] != case['id']]
        store.save_asset(owner, project_id, 'deleted-cases', archive)
        store.save_asset(owner, project_id, 'bundle', bundle)
        store.save_asset(owner, project_id, 'mcp-candidates', candidates_from_bundle(bundle))
        store.update_project(owner, project_id, {'bundle_summary': _summary(bundle)})
        return project_details(request, project_id)

    @app.post('/api/projects/{project_id}/cases/restore')
    @serialized
    def restore_case(request: Request, project_id: str, data: dict):
        owner = request.state.owner; ensure_idle(owner)
        project = store.get_project(owner, project_id)
        bundle = decorate_bundle(project, store.load_asset(owner, project_id, 'bundle'))
        if data.get('revision') != bundle_revision(bundle):
            raise HTTPException(409, '用例已变化，请刷新后重新恢复')
        archive = store.load_asset(owner, project_id, 'deleted-cases')
        item = next((v for v in archive['items'] if v['id'] == data.get('id')), None)
        if item is None: raise HTTPException(404, '已删除的用例不存在')
        case = item['case']
        if any(c['id'] == case['id'] for c in bundle['cases']):
            raise HTTPException(409, '已有相同编号的用例，不能覆盖恢复')
        operation_ids = {case['operation_id']} | {step.get('operation_id', case['operation_id']) for step in case.get('steps', []) + case.get('cleanup_steps', [])}
        if any(item['contract']['operations'].get(oid) != bundle['contract']['operations'].get(oid) for oid in operation_ids):
            raise HTTPException(409, '相关接口文档已变化，无法直接恢复旧用例，请按当前文档重新添加')
        rules = {r['id']: r for r in bundle['rules']}
        for rule in item['rules']:
            if rule['id'] not in case.get('rule_ids', []): continue
            if rule['id'] in rules and rules[rule['id']] != rule:
                raise HTTPException(409, '原用例的判断标准已变化，无法直接恢复')
            rules[rule['id']] = rule
        bundle['rules'] = list(rules.values())
        bundle['contract']['sources'] = {**item['contract']['sources'], **bundle['contract']['sources']}
        bundle['cases'].append(case)
        check_web_bundle(bundle)
        errors = validate_bundle(bundle)
        if errors: raise ValueError('恢复校验失败：' + errors[0]['message'])
        store.save_asset(owner, project_id, 'bundle', bundle)
        store.save_asset(owner, project_id, 'mcp-candidates', candidates_from_bundle(bundle))
        archive['items'] = [v for v in archive['items'] if v['id'] != item['id']]
        store.save_asset(owner, project_id, 'deleted-cases', archive)
        store.update_project(owner, project_id, {'bundle_summary': _summary(bundle)})
        return project_details(request, project_id)

    @app.post('/api/projects/{project_id}/load-test')
    @serialized
    def start_load_test(request: Request, project_id: str, data: dict):
        if any(j['kind'] == 'load' and j['status'] in {'queued', 'running'} for j in jobs.values()):
            raise HTTPException(409, '本机已有压测任务，请等待其结束；普通测试可继续使用')
        raw = data.get('load') or {}
        if not isinstance(raw, dict) or raw.get('engine') not in (None, 'builtin', 'jmeter'): raise ValueError('不支持的压测引擎')
        configuration = jmeter_config(raw) if raw.get('engine') == 'jmeter' else load_config(raw)
        if configuration.get('engine') == 'jmeter':
            if not jmeter_capabilities()['available']: raise ValueError('JMeter 执行引擎尚未安装')
            jmeter_cases(store.load_asset(request.state.owner, project_id, 'bundle'), data.get('case_ids') or [])
        if not isinstance(data.get('case_ids'), list) or not data['case_ids']:
            raise ValueError('请明确选择需要压测的用例')
        return execute(request, project_id, {**data, '_load': configuration})

    @app.post('/api/jobs/{job_id}/stop-load')
    def stop_load_test(request: Request, job_id: str):
        get_job(request, job_id)
        if job_id not in load_stops:raise ValueError('此任务不是压测任务')
        load_stops[job_id].set()
        return {'message': '已停止新增压测轮次；在途请求和清理结束后保存报告'}

    @app.post("/api/projects/{project_id}/run")
    @serialized
    def execute(request: Request, project_id: str, data: dict):
        # Only the dedicated endpoint may activate load mode; JSON clients cannot smuggle it through /run.
        if data.get('_load') is not None and not request.url.path.endswith('/load-test'):
            raise ValueError('请使用独立的可选压测入口')
        owner = request.state.owner
        project = store.get_project(owner, project_id)
        bundle = store.load_asset(owner, project_id, "bundle")
        check_web_bundle(bundle)
        errors = validate_bundle(bundle)
        global_errors = [e for e in errors if e["case_id"] == "*"]
        if global_errors:
            raise ValueError("静态校验失败：" + global_errors[0]["message"])
        case_ids = data.get("case_ids")
        if case_ids is not None:
            if not isinstance(case_ids, list) or not case_ids or any(not isinstance(cid, str) for cid in case_ids):
                raise ValueError("case_ids 必须为非空用例 ID 数组")
            if set(case_ids) - {c["id"] for c in bundle["cases"]}:
                raise ValueError("case_ids 包含不存在的用例")
        requested_environment = data.get("environment")
        experience = project.get('experience') and bundle.get('web', {}).get('experience')
        if experience:
            if requested_environment not in {None, "items"} or fixture is None:
                raise ValueError('完整流程演示仅可在专用示例服务中执行，请重新点击体验入口')
            selected = environments["items"]
            base_url = selected["base_url"]
            name = selected["name"]
        else:
            # New callers use the address saved with the document. Keep the
            # environment fallback only for old sessions/CLI payloads whose
            # task has no saved address; this preserves their reports and
            # cleanup behavior without making environment selection part of
            # the current workflow.
            base_url = normalize_base_url(data.get("base_url") or project.get("task", {}).get("base_url", ""))
            if base_url:
                name = "文档测试地址"
            else:
                legacy_environment = (requested_environment if requested_environment is not None
                                       else project_environment(project))
                if legacy_environment in environments:
                    selected = environments[legacy_environment]
                    base_url = selected["base_url"]
                    name = selected["name"]
                elif legacy_environment in {"auto", "custom"}:
                    name = "文档测试地址"
                else:
                    raise ValueError("未知测试环境")
        known = tuple(e["base_url"] for e in environments.values()) + configured_test_origins + tuple(extra_test_origins if testing else ())
        if not base_url:
            raise ValueError("尚未设置 Base URL，请回到导入文档补充测试地址；只检查文档不需要地址")
        base_url = normalize_base_url(base_url)
        check_public_endpoint(base_url, known)
        if bundle.get("web", {}).get("trusted_cleanup") == "gomoku" and base_url != environments["gomoku"]["base_url"]:
            raise ValueError("此方案依赖独立五子棋库的清理能力，不能切换到其他环境")
        environment = {"name": name, "base_url": base_url, "allowed_origins": [url_origin(base_url)],
                       "timeout": 5, "max_requests": None, "max_response_bytes": 1048576, "case_workers": CASE_WORKERS,
                       "stop_on_5xx": False, "stop_on_network_error": False, "stop_on_cleanup_failure": False}
        callback = None
        if bundle.get("web", {}).get("trusted_cleanup") == "gomoku":
            environment["stop_on_network_error"] = True
            if os.environ.get("GOMOKU_CLEANUP_MODE") == "mysql":
                callback = gomoku_mysql_cleanup(bundle)
            else:
                configuration = read_asset(REPO / "examples/gomoku/environment.yaml")
                callback = build_cleanup(bundle, configuration)
        rid = str(uuid.uuid4())
        run_dir = store.project_dir(owner, project_id) / "runs" / rid

        if data.get('_load') is not None:
            if experience:raise ValueError('可控故障演示不作为压测目标，请选择自己的测试会话')
            chosen = [c for c in bundle['cases'] if c['id'] in case_ids]
            if any(c.get('state') != 'READY' for c in chosen) or errors:
                raise ValueError('压测需选择已核对的可执行用例，并先解决静态校验错误')
            use_jmeter = data['_load'].get('engine') == 'jmeter'
            target_origin = transport_origin(base_url, base=True)
            addresses = _resolve_once(target_origin, url_origin(base_url) in known) if use_jmeter else ()
            stop = threading.Event()
            def load_work(progress):
                if use_jmeter:
                    result = run_jmeter(bundle, environment, run_dir, data['_load'], case_ids=case_ids, progress=progress, stop=stop, addresses=addresses)
                else:
                    result = run_load(bundle, environment, run_dir, data['_load'], case_ids=case_ids,
                        session_factory=lambda: pinned_session(base_url, known), cleanup_callback=callback,
                        progress=progress, stop=stop)
                entry = {'id': rid, 'kind': 'load', 'engine': result.get('engine','builtin'), 'engine_status': result.get('engine_status','completed'), 'created_at': result['started_at'], 'environment': result['environment'],
                    'requests_sent': result['requests_sent'], 'requests_per_second': result['requests_per_second'],
                    'error_rate': result['error_rate'], 'latency_ms': result['latency_ms'], 'stop_reason': result['stop_reason'],
                    'report_url': f'/api/projects/{project_id}/load-reports/{rid}/index.html'}
                current = store.get_project(owner, project_id)
                store.update_project(owner, project_id, {'last_load': entry, 'load_runs': ([entry] + current.get('load_runs', []))[:30]})
                app.state.wecom.auto_report(owner, project_id, rid, 'load-reports')
                return entry
            job = begin_job(owner, project_id, 'load', load_work, execution_target=url_origin(base_url))
            load_stops[job['id']] = stop
            return job

        def work(progress):
            progress("正在顺序执行；目标服务断连后停止后续请求并保留未执行用例" if environment["stop_on_network_error"] else f"正在执行用例：已确认独立的用例最多 {CASE_WORKERS} 条并发，依赖步骤顺序执行")
            if experience:
                progress('演示模式：独立服务将注入 3 种响应缺陷和连接中断；报告记录真实 HTTP 证据')
                with type(fixture)(fault='experience') as demo:
                    demo_env = {**environment, 'name': '【演示】专用资源服务 · 可控故障',
                                'base_url': demo.base_url, 'allowed_origins': [demo.base_url]}
                    result = run_bundle(bundle, demo_env, run_dir,
                                        case_ids=case_ids,
                                        session_factory=lambda: pinned_session(demo.base_url, (demo.base_url,)))
            else:
                result = run_bundle(bundle, environment, run_dir, cleanup_callback=callback,
                                    case_ids=case_ids,
                                    session_factory=lambda: pinned_session(base_url, known))
            write_report(result, read_asset(run_dir / "bundle.json"), run_dir / "index.html")
            current = store.get_project(owner, project_id)
            entry = {"id": rid, "run_id": result["run_id"], "summary": result["summary"], "experience": bool(experience),
                     "environment": result["environment"], "created_at": result["started_at"],
                     "requests_sent": result["requests_sent"], "cleanup": result["cleanup"],
                     "http_cleanup": dict(Counter(case.get("cleanup", {}).get("status", "NOT_CONFIGURED") for case in result.get("cases", []) if case.get("steps"))),
                     "report_url": f"/api/projects/{project_id}/reports/{rid}/index.html"}
            store.update_project(owner, project_id, {"status": "executed", "last_run": entry,
                "runs": ([entry] + current.get("runs", []))[:30]})
            counts = result['summary']
            app.state.wecom.auto_report(owner, project_id, rid, 'reports')
            progress(f"执行已结束：{counts['PASS']} 条通过、{counts['FAIL']} 条失败、{counts['BROKEN']} 条异常、{counts['BLOCKED']} 条受阻；证据与清理结果已保存")
            return entry
        return begin_job(owner, project_id, "run", work, execution_target=url_origin(base_url))

    @app.post("/api/demo")
    @serialized
    def start_demo(request: Request):
        """Only the built-in isolated resource fixture; no user-selected target or model."""
        ensure_idle(request.state.owner)
        if fixture is None:
            raise HTTPException(503, "示例服务未启用，请导入自己的文档或联系管理员")
        item = get_template("items")
        imported = import_project(request, {"title": "完整流程体验", "filename": item["filename"],
            "content": item["content"], "template": "items"})
        pid = imported["project"]["id"]
        bundle = experience_bundle(generate_bundle(imported["contract"], REPO / "examples/items/rules.yaml"))
        check_web_bundle(bundle)
        store.save_asset(request.state.owner, pid, "bundle", bundle)
        store.update_project(request.state.owner, pid, {"status": "generated", "generation_mode": "baseline", "experience": True, "bundle_summary": _summary(bundle)})
        job = execute(request, pid, {"environment": "items"})
        return {**project_details(request, pid), "job": job}

    @app.get("/api/jobs/{job_id}")
    def get_job(request: Request, job_id: str):
        with lock:
            job = jobs.get(job_id)
            if not job or job["owner"] != request.state.owner:
                raise HTTPException(404, "任务不存在或不属于当前会话")
            return copy.deepcopy(public_job(job))

    @app.get("/api/projects/{project_id}/artifacts/{name}")
    def download_asset(request: Request, project_id: str, name: str):
        owner = request.state.owner
        project = store.get_project(owner, project_id)
        if name in {"contract.json", "bundle.json"}:
            value = store.load_asset(owner, project_id, name[:-5])
            safe = Redactor().snapshot(value)
            return JSONResponse(safe, headers={"Content-Disposition": f'attachment; filename="{name}"'})
        if name == "document":
            return FileResponse(current_document_path(store, owner, project), filename=project.get("effective_filename", project["filename"]))
        if name == "original-document":
            return FileResponse(store.project_dir(owner, project_id) / project["document_file"], filename=project["filename"])
        if name == "environment.json":
            saved_base_url = project.get("task", {}).get("base_url", "")
            selected = {"name": "文档测试地址", "base_url": saved_base_url}
            if not saved_base_url:
                selected = environments.get(project_environment(project), selected)
            value = {"name": selected["name"], "base_url": selected["base_url"], "allowed_origins": [url_origin(selected["base_url"])] if selected["base_url"] else [],
                     "timeout": 5, "max_requests": None, "max_response_bytes": 1048576, "case_workers": CASE_WORKERS, "stop_on_5xx": False,
                     "stop_on_network_error": False, "stop_on_cleanup_failure": False}
            if project_environment(project) == "gomoku":
                value["stop_on_network_error"] = True
                value["cleanup"] = read_asset(REPO / "examples/gomoku/environment.yaml")["cleanup"]
            return JSONResponse(value, headers={"Content-Disposition": 'attachment; filename="environment.json"'})
        raise HTTPException(404, "文件不存在")

    @app.get('/api/ui-tests/{project_id}/executions/{execution_id}/{filename}')
    def ui_execution_file(request: Request, project_id: str, execution_id: str, filename: str):
        record = ui_records.load(store, request.state.owner, project_id, execution_id)
        from . import ui_asset_withdrawals
        if filename.startswith('asset-'):
            ui_asset_withdrawals.require_visible(store, request.state.owner, filename[6:])
        record = ui_asset_withdrawals.record_view(store, request.state.owner, record)
        saved = {'imported_results': ui_records.as_results(record), 'ui_snapshot': record}
        if filename == 'cases.html':
            return HTMLResponse(ui_records.cases_html(saved).replace('href="index.html"', 'href="/ui-testing"'))
        if filename == 'cases.xlsx':
            return Response(ui_records.export_xlsx(saved), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                            headers={'Content-Disposition': 'attachment; filename="test-cases.xlsx"'})
        if filename == 'test-data.zip':
            return Response(ui_records.export_test_data_zip(store, request.state.owner, project_id, saved),
                            media_type='application/zip',
                            headers={'Content-Disposition': 'attachment; filename="test-data.zip"'})
        asset = next((a for a in record['assets'] if filename == 'asset-' + a['id']), None)
        if not asset:
            raise HTTPException(404, '文件不存在')
        return FileResponse(ui_records.root_for(store, request.state.owner, project_id, execution_id) / asset['id'],
                            media_type=asset['content_type'], filename=asset['filename'],
                            headers={'Cache-Control': 'no-store'},
                            content_disposition_type='attachment' if asset['kind'] == 'fixture' else 'inline')

    @app.get("/api/projects/{project_id}/case-report")
    def case_report(request: Request, project_id: str):
        owner = request.state.owner
        project = store.get_project(owner, project_id)
        bundle = Redactor().snapshot(store.load_asset(owner, project_id, "bundle"))
        return HTMLResponse(render_case_report(project, bundle))

    def online_report(location, page=None, *, read_only=False, login_required=False, review=False,
                      action_base='', correction_base='', saved_report=None, project_total=None,
                      report_owner=None):
        # Add live integration controls without modifying frozen/offline artifacts.
        page = page if page is not None else location.read_text(encoding="utf-8")
        aggregate_digest = hashlib.sha256((STATIC / 'report-aggregate.js').read_bytes()).hexdigest()[:16]
        aggregate_script = f'<script src="/static/report-aggregate.js?v={aggregate_digest}" defer></script>'
        controls = '' if report_only else '<script src="/static/account-bar.js" defer></script><link rel="stylesheet" href="/static/pingcode.css"><script src="/static/pingcode-triage.js?v=0.10.1" defer></script><script src="/static/pingcode.js?v=0.10.1" defer></script>'
        controls = aggregate_script + controls
        access_mode = "read-only" if report_only else "login-required" if login_required else "read-only" if read_only else ""
        if not report_only:
            controls += '<script src="/static/wecom.js" defer></script>'
        access = f'<meta name="api-test-public-report" content="{access_mode}">' if access_mode else ''
        preview_assets = ('<link rel="stylesheet" href="/static/report-image-preview.css">'
                          '<script src="/static/report-image-preview.js" defer></script>')
        page = page.replace('</head>', access + '<link rel="stylesheet" href="/static/report-theme.css">'
                            + preview_assets + '</head>', 1)
        review_payload = None
        if review:
            # Frozen reports contain high-specificity dark control rules. Keep
            # evidence styling as a fallback, below the online report surface.
            page = re.sub(r'(<style\b[^>]*>)(.*?)(</style>)',
                          lambda match: match[1] + '@layer report-legacy {' + match[2] + '}' + match[3],
                          page, flags=re.S | re.I)
            page = page.replace('<link rel="stylesheet" href="/static/report-theme.css">',
                                '<style>@import url("/static/report-theme.css") layer(report-legacy);</style>')
            # Reuse saved, redacted results; public reports must not fetch private JSON.
            saved_path = location.with_name('report.json')
            saved = saved_report if saved_report is not None else store._read(saved_path) if saved_path.exists() else {}
            imported = saved.get('imported_results') or {}
            snapshot = saved.get('ui_snapshot', {})
            from .ui_experiments import report_timing
            timing = report_timing(saved)
            assets = [{key: asset.get(key, '') for key in
                       ('id', 'filename', 'kind', 'case_id', 'step', 'size', 'sha256', 'captured_at', 'url')}
                      for asset in snapshot.get('assets', [])]
            report_cases = ui_records.cases_with_actions(imported.get('cases', []))
            report_navigation = {}
            if saved.get('test_kind') == 'ui' and imported:
                report_navigation = {'reportType': saved.get('report_type', 'stage'),
                    'totalReport': {'report_url': f"/api/projects/{saved['project_id']}/reports/total/index.html"},
                    'stageReports': saved.get('stage_reports', [])}
            review_payload = {'imported': bool(imported), 'cases': report_cases, 'assets': assets,
                               'rejectedFindingIds': app.state.pingcode.rejected_report_findings(report_owner, saved)
                               if snapshot and report_owner else [],
                               **report_navigation, 'aggregate': saved.get('aggregate'), 'projectTotal': project_total,
                               'hasCoverage': bool(saved.get('ui_snapshot', {}).get('coverage')),
                               'sceneRetention': snapshot.get('scene_retention') if saved.get('report_type') != 'total' else None,
                               'sceneOutcome': snapshot.get('scene_outcome') if saved.get('report_type') != 'total' else None,
                               'uiExecution': bool(saved.get('ui_snapshot')), 'summary': saved.get('summary', ''),
                               'timing': timing,
                               'timingNotice': ('未完整记录执行起止时间，无法计算执行耗时'
                                                if snapshot and saved.get('report_type') != 'total' and not timing else ''),
                               **({'experiment': snapshot['experiment'], 'experimentPublishedAt': saved.get('updated_at') or saved.get('created_at', '')}
                                  if snapshot.get('experiment') and saved.get('report_type') != 'total' else {}),
                               'source': imported.get('filename', ''),
                               'actionBase': action_base if not (read_only or login_required or report_only) else '',
                               'retestBase': action_base.removesuffix('/ui-actions') if action_base and imported and saved.get('report_type') != 'total' and not (read_only or login_required or report_only) else '',
                               'ruleBase': action_base.removesuffix('/ui-actions') + '/rule-questions' if action_base and snapshot and not saved.get('aggregate') and not (read_only or login_required or report_only) else '',
                               'correctionBase': correction_base if not (read_only or login_required or report_only) else '',
                               'correctionRevision': saved.get('case_corrections', {}).get('revision', 0)}
            data = json.dumps(review_payload, ensure_ascii=False).replace('<', '\\u003c')
            if action_base and snapshot and not (read_only or login_required or report_only):
                controls += ('<meta name="report-collaboration-base" content="'
                             + action_base.removesuffix('/ui-actions') + '/collaboration">')
                digest = hashlib.sha256((STATIC / 'report-collaboration.js').read_bytes()).hexdigest()[:16]
                controls += f'<script src="/static/report-collaboration.js?v={digest}" defer></script>'
            controls += '<script type="application/json" id="report-review-data">' + data + '</script>'
            for name in ('report-review.css', 'report-select.js', 'report-review.js', 'report-rules.js', 'report-retest.js'):
                digest = hashlib.sha256((STATIC / name).read_bytes()).hexdigest()[:16]
                url = f'/static/{name}?v={digest}'
                controls += (f'<link rel="stylesheet" href="{url}">' if name.endswith('.css') else
                             f'<script src="{url}" defer></script>')
            for name in ('pingcode.js', 'pingcode-triage.js'):
                digest = hashlib.sha256((STATIC / name).read_bytes()).hexdigest()[:16]
                controls = controls.replace(name + '?v=0.10.1', name + '?v=' + digest)
        glass = ('<style>@import url("/static/shared-glass.css") layer(report-legacy);</style>' if review else
                 '<link rel="stylesheet" href="/static/shared-glass.css">')
        account_style = '' if report_only else '<link rel="stylesheet" href="/static/account-bar.css">'
        return HTMLResponse(prepare_online_report(
            page.replace('</body>', controls + glass + account_style + '</body>'), review_payload))

    def shared_report_project(request: Request, project_id: str):
        try:
            owner = request.state.owner
            project = store.get_project(owner, project_id)
        except (FileNotFoundError, PermissionError):
            if not request.state.public_report:
                raise
            owner = store.find_project_owner(project_id)
            project = store.get_project(owner, project_id)
        read_only = owner != request.state.owner or (auth_enabled and not request.state.user)
        return owner, project, read_only

    @app.get('/api/projects/{project_id}/jmeter-artifacts/{run_id}/{filename}')
    def jmeter_artifact(request: Request, project_id: str, run_id: str, filename: str):
        project = store.get_project(request.state.owner, project_id)
        if filename not in {'plan.zip', 'samples.jtl'} or run_id not in {r['id'] for r in project.get('load_runs', []) if r.get('engine') == 'jmeter'}:
            raise HTTPException(404, 'JMeter 文件不存在')
        path = store.project_dir(request.state.owner, project_id) / 'runs' / run_id / 'jmeter' / filename
        if not path.is_file(): raise HTTPException(404, '此任务未生成对应文件')
        return FileResponse(path, filename=filename, media_type='application/zip' if filename.endswith('.zip') else 'text/csv')

    @app.get('/api/projects/{project_id}/load-reports/{run_id}/{filename}')
    def load_report(request: Request, project_id: str, run_id: str, filename: str):
        owner, project, read_only = shared_report_project(request, project_id)
        if (run_id not in {r['id'] for r in project.get('load_runs', [])} and not store.has_saved_report(owner, project_id, run_id, kind='runs')) or filename not in {'index.html', 'result.json', 'bundle.json'}:
            raise HTTPException(404, '压测报告不存在')
        location = store.project_dir(owner, project_id) / 'runs' / run_id / filename
        saved = store._read(location.with_name('result.json'))
        if saved.get('kind') != 'load':
            raise HTTPException(404, '压测报告不存在')
        if filename == 'index.html':
            return online_report(location, render_load_report(saved), read_only=read_only,
                                 login_required=auth_enabled and not request.state.user)
        return FileResponse(location, media_type='application/json')

    @app.get("/api/projects/{project_id}/reports/{run_id}/{filename}")
    def report(request: Request, project_id: str, run_id: str, filename: str):
        owner, project, read_only = shared_report_project(request, project_id)
        from . import ui_asset_withdrawals
        if filename.startswith('asset-'):
            ui_asset_withdrawals.require_visible(store, owner, filename[6:])
        if run_id == 'total':
            from .ui_total_reports import build, export_test_data
            from .task_reports import render_task_report
            if filename not in {'index.html', 'report.json', 'cases.html', 'cases.xlsx', 'test-data.zip'}:
                raise HTTPException(404, '报告文件不存在')
            saved = build(store, owner, project)
            saved = ui_asset_withdrawals.report_view(store, owner, saved)
            if filename == 'report.json':
                return JSONResponse(saved, headers={'Cache-Control': 'no-store'})
            if filename == 'cases.xlsx':
                return Response(ui_records.export_xlsx(saved),
                    media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': 'attachment; filename="total-test-cases.xlsx"'})
            if filename == 'test-data.zip':
                return Response(export_test_data(store, owner, saved), media_type='application/zip',
                    headers={'Content-Disposition': 'attachment; filename="total-test-data.zip"'})
            if filename == 'cases.html':
                return HTMLResponse(ui_records.cases_html(saved), headers={'Cache-Control': 'no-store'})
            response = online_report(store.project_dir(owner, saved['project_id']) / 'total' / 'index.html',
                render_task_report(saved), read_only=read_only,
                login_required=auth_enabled and not request.state.user, review=True, saved_report=saved, report_owner=owner,
                action_base=f"/api/projects/{saved['project_id']}/reports/total/ui-actions",
                correction_base=f"/api/projects/{saved['project_id']}/reports/total/case-corrections")
            response.headers['Cache-Control'] = 'no-store'
            return response
        project_total = project_reports.session_link(owner, project_id)
        historical_report = store.has_saved_report(owner, project_id, run_id)
        if run_id in {r["id"] for r in project.get("analysis_reports", [])} or historical_report:
            saved = store._read(store.project_dir(owner, project_id) / 'analyses' / run_id / 'report.json')
            merged = saved.get('consolidated_into')
            if merged and filename in {'index.html', 'cases.html', 'cases.xlsx', 'test-data.zip'}:
                target_pid, target_rid = merged.get('project_id', ''), merged.get('report_id', '')
                if not all(re.fullmatch(r'[a-f0-9-]{36}', value) for value in (target_pid, target_rid)):
                    raise HTTPException(404, '合并报告不存在')
                target_project = store.get_project(owner, target_pid)
                from .ui_total_reports import canonical_project
                if canonical_project(store, owner, target_project)['id'] != canonical_project(store, owner, project)['id']:
                    raise HTTPException(404, '合并报告不属于当前会话')
                if (target_pid, target_rid) != (project_id, run_id):
                    return RedirectResponse(f'/api/projects/{target_pid}/reports/{target_rid}/{filename}', status_code=307)
            if saved.get('ui_snapshot'):
                saved = ui_report_corrections.apply(saved, ui_report_corrections.load(store, owner, project_id, run_id), store=store, owner=owner)
                saved = ui_asset_withdrawals.report_view(store, owner, saved)
            if filename in {'cases.html', 'cases.xlsx', 'test-data.zip'} and saved.get('imported_results'):
                if filename == 'cases.xlsx':
                    return Response(ui_records.export_xlsx(saved), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                    headers={'Content-Disposition': 'attachment; filename="test-cases.xlsx"'})
                if filename == 'test-data.zip':
                    return Response(ui_records.export_test_data_zip(store, owner, project_id, saved),
                                    media_type='application/zip',
                                    headers={'Content-Disposition': 'attachment; filename="test-data.zip"'})
                return HTMLResponse(ui_records.cases_html(saved))
            asset = next((a for a in saved.get('ui_snapshot', {}).get('assets', []) if filename == 'asset-' + a['id']), None)
            if asset:
                path = ui_records.root_for(store, owner, project_id, saved['ui_snapshot']['id']) / asset['id']
                return FileResponse(path, media_type=asset['content_type'], filename=asset['filename'],
                                    headers={'Cache-Control': 'no-store'},
                                    content_disposition_type='attachment' if asset['kind'] == 'fixture' else 'inline')
            if filename not in {"index.html", "report.json", "cases.html"}:
                raise HTTPException(404, "报告文件不存在")
            location = store.project_dir(owner, project_id) / "analyses" / run_id / filename
            if filename == "cases.html":
                if not location.exists():
                    raise HTTPException(404, "这份历史报告尚无用例设计快照")
                return online_report(location, read_only=read_only, project_total=project_total,
                                     login_required=auth_enabled and not request.state.user)
            if filename.endswith("html"):
                from .task_reports import render_saved_task_report
                if not saved.get("runs") and "sections" not in saved and not saved.get('case_corrections') and not saved.get('ui_snapshot'):
                    return online_report(location, read_only=read_only, project_total=project_total,
                                         login_required=auth_enabled and not request.state.user, review=True,
                                         action_base=f'/api/projects/{project_id}/reports/{run_id}/ui-actions',
                                         correction_base=f'/api/projects/{project_id}/reports/{run_id}/case-corrections',
                                         saved_report=saved, report_owner=owner)
                return online_report(location, render_saved_task_report(store, owner, project, saved),
                                     read_only=read_only, project_total=project_total,
                                     login_required=auth_enabled and not request.state.user, review=True,
                                     action_base=f'/api/projects/{project_id}/reports/{run_id}/ui-actions',
                                     correction_base=f'/api/projects/{project_id}/reports/{run_id}/case-corrections',
                                     saved_report=saved, report_owner=owner)
            return JSONResponse(saved, headers={'Cache-Control': 'no-store'}) if saved.get('ui_snapshot') or saved.get('case_corrections') or saved.get('regression_links') else FileResponse(location, media_type="application/json")
        if (filename not in {"index.html", "result.json", "bundle.json"}
                or run_id not in {run["id"] for run in project.get("runs", [])}
                and not store.has_saved_report(owner, project_id, run_id, kind='runs')):
            raise HTTPException(404, "报告不存在")
        location = store.project_dir(owner, project_id) / "runs" / run_id / filename
        return (online_report(location, read_only=read_only, project_total=project_total,
                              login_required=auth_enabled and not request.state.user, review=True)
                if filename.endswith("html") else FileResponse(location, media_type="application/json"))

    @app.get("/api/mcp/status")
    def mcp_status(request: Request):
        return mcp_access.status(request.state.owner)

    @app.post("/api/mcp/pair")
    def mcp_pair(request: Request):
        return mcp_access.issue(request.state.owner)

    @app.delete("/api/mcp/pair")
    def mcp_revoke(request: Request):
        return mcp_access.revoke(request.state.owner)

    @app.post("/api/mcp/redeem")
    def mcp_redeem_code(data: dict):
        result = mcp_access.redeem(data.get("code"))
        result["usage_guide"] = json.loads((STATIC / "workspace-usage.json").read_text())
        return result

    def mcp_revision(owner, pid):
        try:
            candidates = store.load_asset(owner, pid, "mcp-candidates")
        except FileNotFoundError:
            candidates = {"schema_version": "1.0", "cases": []}
        revision = hashlib.sha256(json.dumps({"candidates": candidates, "contract": store.load_asset(owner, pid, "contract")}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        return candidates, revision

    @app.post("/api/mcp/call")
    def mcp_call_tool(request: Request, data: dict):
        # Record only successful, authenticated calls. Browser refreshes never signal activity.
        if data.get('action') == 'direct_session':
            # This route has its own transactional lease/holder checks. Waiting
            # for an unrelated report's global lock delays every browser step.
            return dispatch_mcp_tool(request, data)
        if data.get('action') == 'run_test_capability':
            # Adapter I/O may take seconds; unrelated browser and MCP cases keep
            # progressing. The runner reserves and commits under the store lock.
            result = dispatch_mcp_tool(request, data)
            pid = data.get('arguments', {}).get('project_id')
            if pid:
                with lock:
                    latest = store.get_project(request.state.owner, pid)
                    execution_id = data.get('arguments', {}).get('execution_id')
                    if latest.get('ui_execution_id') == execution_id and not ui_records.load(
                            store, request.state.owner, pid, execution_id).get('report_id'):
                        record_progress(store, request.state.owner, pid, 'executing', '适配器执行记录已保存')
            return result
        with lock:
            action, arguments = data.get("action"), data.get("arguments", {})
            receipt_path=None
            if request.state.mcp_scope and action in {'start_workflow','start_regression'}:
                if action == 'start_workflow' or arguments.get('holder_id'):
                    raise HTTPException(403, '此连接只有报告协作权限；任务调度请使用工作空间连接')
                if not ui_rounds.related_access(store,request.state.owner,arguments.get('project_id'),request.state.mcp_scope['project_ids']):
                    raise HTTPException(403, '此连接仅可协作当前报告关联的测试会话')
            if action in {'start_workflow','start_regression'} and isinstance(arguments,dict) and arguments.get('request_id'):
                key=hashlib.sha256(((action+':' if action=='start_regression' else '')+str(arguments['request_id'])).encode()).hexdigest()
                fingerprint=hashlib.sha256(json.dumps(arguments,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                receipt_path=store._owner_dir(request.state.owner)/'workflow-requests'/(key+'.json')
                if receipt_path.exists():
                    old=store._read(receipt_path)
                    if old['hash']!=fingerprint:raise ValueError('同一 request_id 不能改变建任务参数')
                    if old.get('result'):return old['result']
                    raise HTTPException(409,'原创建请求尚未确认；请查询原会话列表核实，不重复创建任务')
                def before_create():
                    # Rejections before Store starts creating a session have no
                    # uncertain creation to guard. Once creation begins, retain
                    # pending even if a later binding/report/dispatch step fails.
                    store._mkdir(receipt_path.parent)
                    store._write(receipt_path, {'hash': fingerprint, 'state': 'pending'})
                request.state.workflow_before_create = before_create
            result = dispatch_mcp_tool(request, data)
            if receipt_path:
                if result.get('created') or result.get('regression_round'):store._write(receipt_path,{'hash':fingerprint,'state':'completed','result':result})
                else:receipt_path.unlink(missing_ok=True)
            action, arguments = data.get("action"), data.get("arguments", {})
            pid = arguments.get("project_id")
            if action in {'start_workflow', 'start_regression'}:
                pid = result.get('project_id')
            if action == "job":
                pid = result.get("project_id")
            phase = ACTIONS.get(action)
            if action in {'ui_asset', 'ui_assets'} and result.get('report_id'):
                # Restoring an input file does not start another test execution.
                phase = None
            if action == 'ui_cases' and any(c.get('status') not in {None, '', 'not_run', '未执行'} for c in arguments.get('cases', [])):
                phase = 'executing'
            if action == 'ui_cases' and arguments.get('experiment') is not None and not arguments.get('cases') and all(
                    arguments.get(key) is None for key in ('coverage', 'review_notes', 'scene_outcome')):
                # Optional measurements alone do not restart design/execution progress.
                phase = None
            # Document/context/job/report reads never change a task's activity.
            # Current scheduler, result and report facts are projected on reads.
            if action in {"task_report", "ui_publish", "finish_workflow", "submit"} and result.get('report'):
                phase = "completed"
                ui_completion = action == 'ui_publish' or (action == 'finish_workflow' and
                    store.get_project(request.state.owner, pid).get('test_kind') == 'ui')
                record_progress(store, request.state.owner, pid, phase,
                                'UI 报告已保存，用例、测试数据与步骤证据可在线查看。' if ui_completion else
                                f"报告已保存，关联 {result.get('report', {}).get('requests_sent', 0)} 次真实请求；请查看设计清单与未执行原因。")
                phase = None
            if pid and phase:
                if action == 'ui_cases':
                    record_case_progress(store, request.state.owner, pid, result)
                    app.state.managed_workflow.record_activity(request.state.owner,pid,result)
                else:
                    record_progress(store, request.state.owner, pid, phase)
            if request.state.mcp_scope and pid and action in {'ui_publish', 'finish_workflow',
                    'ui_cases', 'ui_correct', 'resolve_rule_question', 'resume_requirement_test'}:
                report_collaboration.record(store, {'owner': request.state.owner, 'project_id': pid,
                    'report_id': arguments.get('report_id', ''), 'operation': action},
                    request.state.mcp_scope.get('actor', ''))
            return result

    def dispatch_mcp_tool(request: Request, data: dict):
        # This finite dispatcher cannot call model APIs, change keys or execute code.
        owner = request.state.owner
        action = data.get("action")
        arguments = data.get("arguments", {})
        if not isinstance(arguments, dict):
            raise ValueError("arguments 必须是 JSON 对象")
        if action in {'start_workflow', 'save_materials', 'import'} and arguments.get('attachments') is None:
            arguments = {**arguments, 'attachments': []}
        scope = request.state.mcp_scope
        if action in {"direct_session", "managed_status", "managed_create", "managed_control", "managed_split", "managed_report", "managed_start", "managed_projects", "managed_bind_project"}:
            return orchestration_web.dispatch(orchestration, request, action, arguments)
        if scope:
            permitted = {'workspace', 'list_sessions', 'context', 'task', 'document', 'report', 'rules', 'progress',
                'ui_cases', 'ui_read', 'ui_design_reference', 'ui_asset', 'ui_assets', 'ui_asset_withdraw', 'ui_publish', 'ui_correct', 'save_materials', 'workflow_status',
                'finish_workflow', 'ui_retest_inputs', 'ui_retest_file', 'ui_dependency_check', 'test_attachment',
                'requirement_design', 'save_requirement_design', 'resolve_rule_question', 'resume_requirement_test',
                'record_checkpoint', 'test_capabilities', 'save_test_capabilities', 'run_test_capability',
                'test_experiment', 'ui_resources', 'start_regression'}
            if action not in permitted or (action not in {'workspace', 'list_sessions'}
                    and not ui_rounds.related_access(store, owner, arguments.get('project_id'), scope['project_ids'])):
                raise HTTPException(403, '此连接仅可协作当前报告关联的测试会话')
        if action == 'run_test_capability':
            pid = arguments.get('project_id', '')
            store.get_project(owner, pid)
            known = tuple(e['base_url'] for e in environments.values()) + configured_test_origins + tuple(extra_test_origins if testing else ())
            return test_capabilities.run(store, owner, pid, arguments.get('execution_id'), arguments.get('revision'),
                arguments.get('case_id'), arguments.get('checkpoint_id'), arguments.get('capability_key'), arguments.get('parameters'),
                arguments.get('invocation_id'), known, arguments.get('experiment', 'single'), arguments.get('scenario', ''),
                arguments.get('workers', 2), mutation_lock=lock)
        with lock:
            if action == "workspace":
                projects = ui_projects(owner)
                if scope:
                    projects = [p for p in projects if p['id'] in scope['project_ids']]
                return {"projects": projects, "templates": list(TEMPLATES),
                        "model_api_calls": False, "testing_skill": _testing_skill()}
            if action == 'list_sessions':
                kind, limit = arguments.get('test_kind', 'all'), arguments.get('limit', 20)
                if kind not in {'all', 'ui', 'api'} or type(limit) is not int or not 1 <= limit <= 50:
                    raise ValueError('test_kind 仅支持 all/ui/api，limit 需为 1–50')
                projects = store.list_projects(owner)
                if scope:
                    projects = [p for p in projects if p['id'] in scope['project_ids']]
                if kind != 'all':
                    projects = [p for p in projects if ('ui' if p.get('test_kind') == 'ui' else 'api') == kind]
                return {'sessions': [workflow_status(owner, p) for p in projects[:limit]],
                        'total': len(projects), 'limit': limit}
            if action == 'start_workflow':
                route = arguments.get('execution_route', 'native_browser')
                if route not in {'native_browser', 'local_browser', 'managed'}:
                    raise ValueError('execution_route 仅支持 native_browser/local_browser/managed')
                kind = arguments.get('test_kind', 'auto')
                goal = arguments.get('goal', '')
                if kind not in {'auto', 'ui', 'api', 'requirements'}:
                    raise ValueError('test_kind 仅支持 auto/ui/api/requirements')
                if not isinstance(goal, str) or not goal.strip() or len(goal) > 30000:
                    raise ValueError('测试目标必须是非空文本，最多 30000 字符')
                target = arguments.get('target_url', '')
                content = arguments.get('content', '')
                template = arguments.get('template')
                if kind == 'auto':
                    kind = requirement_design.classify(content, arguments.get('filename') or 'document.md') if content else 'ui' if target or arguments.get('account_project_id') else 'api' if template else 'auto'
                missing = []
                if kind == 'auto':
                    missing.append('test_kind 或 target_url/document')
                elif kind == 'api' and not (content or template):
                    missing.append('filename+content 或 template')
                elif kind == 'requirements' and not content:
                    missing.append('filename+content')
                if kind in {'ui', 'requirements'} and not target and arguments.get('account_project_id'):
                    target = orchestration.account_projects.get(owner, arguments['account_project_id']).get('login_url', '')
                    if not target:missing.append('project_login_url')
                if kind in {'ui','requirements'} and not arguments.get('account_project_id'):
                    missing.append('account_project_id')
                if missing:
                    return {'created': False, 'required_inputs': missing,
                            'account_projects': orchestration.account_projects.list(owner) if kind in {'ui','requirements'} else [],
                            'message': '请选择测试所属项目；暂无项目时请在项目管理中添加产品及统一登录地址。账号密码可不提供。' if 'account_project_id' in missing else '请补充执行必需信息。'}
                title = arguments.get('title', '')
                if not isinstance(title, str):
                    raise ValueError('title 必须是文本')
                title = title.strip() or goal.strip().splitlines()[0][:80]
                if kind == 'ui':
                    result = create_ui_test(request, {'title': title, 'target_url': target, 'goal': goal,
                                                     'account_project_id': arguments.get('account_project_id'),
                                                     'attachments': arguments.get('attachments', []),
                                                     'execution_permission': arguments.get('execution_permission'),
                                                     'scene_retention': arguments.get('scene_retention')})
                elif kind == 'requirements':
                    result = create_requirement_test(request, {**arguments, 'title': title,
                        'filename': arguments.get('filename') or 'requirements.md', 'document_kind': 'requirements'})
                else:
                    if template:
                        item = get_template(template)
                        filename, content = item['filename'], item['content']
                    else:
                        filename = arguments.get('filename') or 'document.md'
                    payload = {'title': title, 'filename': filename, 'content': content,
                               'attachments': arguments.get('attachments', []),
                               'template': template, 'allow_unparsed': True, 'task': {'goal': goal.strip()}}
                    result = import_project(request, payload)
                    if arguments.get('base_url') is not None:
                        update_task(request, result['project']['id'], {'goal': goal.strip(), 'base_url': arguments.get('base_url')})
                        result['project'] = store.get_project(owner, result['project']['id'])
                status = workflow_status(owner, result['project'])
                execution={}
                if result['project'].get('test_kind')=='ui':
                    execution=app.state.managed_workflow.start(owner,result['project']['id'],
                        {'request_id':'workflow:'+result['project']['id'],'execution_route':route,
                         **({'modules':arguments['modules']} if arguments.get('modules') is not None else {})})
                    result['project']=store.get_project(owner,result['project']['id'])
                    status['next_action']='get_managed_test' if execution.get('scheduled') else execution.get('next_action','start_session_test')
                return {'execution':execution,'created': True, 'project': result['project'], 'project_id': result['project']['id'],
                        'status': status, 'next_action': status['next_action']}
            if action == "import":
                template = arguments.get("template")
                if template:
                    item = get_template(template)
                    arguments = {**arguments, "filename": item["filename"], "content": item["content"]}
                return import_project(request, arguments)
            if action == "job":
                return get_job(request, arguments.get("job_id", ""))
            if action not in {"context", "task", "document", "task_report", "submit", "approve", "run", "report", "rules", "progress", "ui_cases", "ui_read", "ui_design_reference", "ui_asset", "ui_assets", "ui_asset_withdraw", "ui_publish", "ui_correct", "save_materials", "workflow_status", "start_regression", "defect_decisions", "finish_workflow", "ui_retest_inputs", "ui_retest_file", "ui_dependency_check", "test_attachment", "requirement_design", "save_requirement_design", "resolve_rule_question", "resume_requirement_test", "record_checkpoint", "test_capabilities", "save_test_capabilities", "run_test_capability", "test_experiment", "ui_resources"}:
                raise ValueError("未知 MCP 操作")
            pid = arguments.get("project_id", "")
            project = store.get_project(owner, pid)
            if action == 'ui_asset_withdraw':
                from .ui_asset_withdrawals import withdraw
                return withdraw(store, owner, pid, **{k: arguments.get(k, '') for k in
                    ('execution_id', 'asset_id', 'case_id', 'sha256', 'reason', 'request_id')},
                    actor=(scope or {}).get('actor') or owner)
            if action == 'ui_resources':
                return ui_rounds.coordinate(store, owner, pid, arguments.get('holder_id'),
                    arguments.get('operation'), arguments.get('resources'))
            if action == 'requirement_design':
                return requirement_design.view(store, owner, pid)
            if action == 'save_requirement_design':
                return requirement_design.save(store, owner, pid, arguments.get('revision'), arguments.get('requirements'), arguments.get('questions'))
            if action == 'resolve_rule_question':
                return requirement_design.resolve(store, owner, pid, arguments.get('question_id'), arguments.get('revision'), arguments.get('resolution'), arguments.get('basis'))
            if action == 'resume_requirement_test':
                return requirement_design.resume(store, owner, pid, arguments.get('execution_id'), arguments.get('revision'), arguments.get('case_ids'),
                    arguments.get('question_id', ''), arguments.get('reason', ''), arguments.get('mode', 'continue'))
            if action == 'record_checkpoint':
                return test_checkpoints.record_result(store, owner, pid, arguments.get('execution_id'), arguments.get('revision'),
                    arguments.get('case_id'), arguments.get('checkpoint_id'), arguments.get('result'))
            if action == 'test_capabilities':
                return test_capabilities.view(store, owner, pid)
            if action == 'save_test_capabilities':
                return test_capabilities.save(store, owner, pid, arguments.get('revision'), arguments.get('items'))
            if action == 'test_experiment':
                _, history = test_capabilities.experiments(store, owner, pid, arguments.get('execution_id'))
                return history['items'].get(arguments.get('invocation_id')) or {'status': 'not_found'}
            if action == 'test_attachment':
                return ui_attachments.read(store, owner, pid, arguments.get('attachment_id', ''),
                                           arguments.get('offset', 0), arguments.get('limit', ui_attachments.MAX_READ_BYTES))
            if action == 'ui_dependency_check':
                return ui_dependencies.record_check(store, owner, pid, arguments.get('execution_id', ''),
                    arguments.get('revision'), arguments.get('dependency_id'), arguments.get('status'),
                    arguments.get('observed'), arguments.get('method'))
            if action == 'ui_retest_inputs':
                return ui_retests.execution_inputs(store, owner, project, arguments.get('task_id', ''))
            if action == 'ui_retest_file':
                return ui_retests.file_content(store, owner, project, arguments.get('input_id', ''), arguments.get('file_id', ''), arguments.get('task_id', ''))
            if action == 'ui_correct':
                return correct_report_case(request, pid, arguments.get('report_id', ''),
                                           arguments.get('case_id', ''), arguments)
            if action == 'workflow_status':
                if arguments.get('finalization_only'):
                    from . import ui_finalization
                    current = project.get('ui_finish_request') or {}
                    if current.get('request_id') != arguments.get('request_id'):
                        return {'phase':'changed','pending':False,'message':'当前结束请求已更新，请读取当前任务状态。'}
                    return ui_finalization.status(project)
                return workflow_status(owner, project)
            if action == 'save_materials':
                return save_workflow_materials(owner, project, arguments)
            if action == 'start_regression':
                route = arguments.get('execution_route', 'native_browser')
                if route not in {'native_browser', 'local_browser', 'managed'}:
                    raise ValueError('execution_route 仅支持 native_browser/local_browser/managed')
                if project.get('test_kind') != 'ui':
                    raise ValueError('回归会话当前仅适用于 UI 测试')
                payload = {'prepare_execution': True}
                if arguments.get('case_ids') is not None:
                    payload['case_ids'] = arguments['case_ids']
                if arguments.get('holder_id') and not arguments.get('request_id'):
                    raise ValueError('直接开始回归请沿用稳定的 request_id，避免重复创建轮次')
                if arguments.get('target_url'):
                    payload['target_url'] = arguments['target_url']
                if arguments.get('goal'):
                    payload['goal'] = arguments['goal']
                if arguments.get('execution_permission'):
                    payload['execution_permission'] = arguments['execution_permission']
                if 'scene_retention' in arguments:
                    payload['scene_retention'] = arguments['scene_retention']
                result = create_ui_regression(request, pid, payload)
                # This explicit new round owns its route; the source task stays unchanged.
                result['project'] = store.update_project(owner, result['project']['id'], {'execution_route': route})
                if arguments.get('holder_id'):
                    result['execution'] = app.state.managed_workflow.start(owner,result['project']['id'],{
                        'request_id':arguments['request_id'], 'execution_route':route})
                status = workflow_status(owner, result['project'])
                return {**result, 'project_id': result['project']['id'], 'status': status,
                        'next_action': status['next_action']}
            if action == 'defect_decisions':
                candidates = [item for item in (project.get('last_analysis'), project.get('last_run')) if item]
                latest = max(candidates, key=lambda item: item.get('created_at', '')) if candidates else {}
                report_id = arguments.get('report_id') or latest.get('id')
                if not report_id:
                    return {'project_id': pid, 'report_id': None, 'decisions': [], 'counts': {}}
                valid = {r['id'] for r in project.get('analysis_reports', []) + project.get('runs', [])}
                if report_id not in valid:
                    raise FileNotFoundError('报告不存在')
                decisions = app.state.pingcode.lifecycle_for_report(owner, pid, report_id)
                return {'project_id': pid, 'report_id': report_id, 'decisions': decisions,
                        'counts': dict(Counter(item['triage_status'] for item in decisions))}
            if action == 'finish_workflow':
                title = arguments.get('title') or project['title'] + (' · UI 测试报告' if project.get('test_kind') == 'ui' else ' · 测试报告')
                summary = arguments.get('summary', '')
                if project.get('test_kind') == 'ui':
                    from . import ui_finalization
                    return ui_finalization.begin(app.state.managed_service, owner, project, arguments)
                ensure_idle(owner)
                return save_task_report(store, owner, project, {
                    'title': title, 'summary': summary,
                    'sections': arguments.get('sections') or [], 'findings': arguments.get('findings') or [],
                    'run_ids': arguments.get('run_ids') or [],
                })
            if action == 'ui_cases':
                return ui_records.save_cases(store, owner, pid, ui_retests.redact(store, owner, pid, arguments.get('cases')), arguments.get('execution_id', ''), arguments.get('revision', 0),
                                             arguments.get('coverage'), arguments.get('review_notes'), arguments.get('scene_outcome'), arguments.get('experiment'))
            if action == 'ui_design_reference':
                if scope and not ui_rounds.related_access(store, owner, arguments.get('source_project_id'), scope['project_ids']):
                    raise HTTPException(403, '此连接无权读取未分享会话的历史设计')
                from .ui_design_references import read
                return read(app.state.managed_workflow.controller, owner, project, arguments.get('source_project_id'),
                            arguments.get('offset', 0), arguments.get('limit', 100))
            if action == 'ui_read':
                execution_id = arguments.get('execution_id') or project.get('ui_execution_id')
                if not execution_id:
                    return {'execution_id': None, 'cases': [], 'assets': [], 'total': 0}
                record = ui_records.load(store, owner, pid, execution_id)
                from .ui_asset_withdrawals import record_view
                record = record_view(store, owner, record)
                offset, limit = arguments.get('offset', 0), arguments.get('limit', 100)
                if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 200:
                    raise ValueError('读取分页无效')
                active = ui_records.active_cases(record['cases'])
                cases = active[offset:offset + limit]
                return {**record, 'execution_id': record['id'], 'cases': cases, 'total': len(active), 'next_offset': offset + limit if offset + limit < len(active) else None,
                        'superseded_cases': [c for c in record['cases'] if ui_records.is_superseded(c)],
                        'blocking_summary': ui_dependencies.blocking_summary(record),
                        'assets': [a for a in record['assets'] if a['case_id'] in {c['case_id'] for c in cases}],
                        'coverage_check': ui_records.coverage_check(record),
                        'dependency_groups': ui_dependencies.groups(record['cases'], record.get('dependency_checks')),
                        'execution_plan': ui_dependencies.plan(record, recovery=ui_dependencies.cached_recovery(project, record))}
            if action == 'ui_asset':
                return ui_records.add_asset(store, owner, pid, **{k: arguments.get(k, '') for k in
                    ('execution_id', 'case_id', 'step', 'filename', 'content_type', 'content_base64', 'captured_at')}, kind=arguments.get('kind', 'screenshot'))
            if action == 'ui_assets':
                return ui_records.add_assets(store, owner, pid, arguments.get('execution_id', ''), arguments.get('assets'))
            if action == 'ui_publish':
                return ui_records.publish(store, owner, project, arguments.get('execution_id', ''), arguments.get('title', 'UI 测试结果'), arguments.get('summary', ''))
            if action == 'context' and project.get('test_kind') == 'ui':
                execution = app.state.managed_workflow.summary(owner,pid)
                return {'testing_policy': testing_policy.snapshot(), 'project': {**project, 'mcp_progress': execution['progress']}, 'testing_skill': _ui_testing_skill(project, arguments.get('role', '')), 'execution_id': project.get('ui_execution_id'), 'defect_title_guidance': AI_TITLE_GUIDANCE,
                        'requirement_design': requirement_design.view(store, owner, pid),
                        'execution': execution,
                        'test_capabilities': test_capabilities.view(store, owner, pid), 'requirements_guidance': requirement_design.GUIDANCE,
                        'attachments': project.get('ui_requirement_attachments', []), 'attachment_guidance': ui_attachments.GUIDANCE,
                        'design_references': [] if scope else ui_design_references.catalog(app.state.managed_workflow.controller, owner, project),
                        'design_reference_guidance': ui_design_references.GUIDANCE,
                        'execution_round': project.get('execution_round'), 'parallel_execution_guidance': _ui_parallel_guidance(arguments.get('role', '')),
                        'execution_permission': project.get('ui_execution_permission'),
                        'scene_retention': project.get('ui_scene_retention', ui_scene_retention(None)),
                        'workflow_guidance': ('按返回的协调角色参考处理模块范围、实际交接与汇总；worker_packet仅供转发给对应执行者。' if arguments.get('role') == 'coordinator' else ui_dependencies.CASE_EXECUTION_GUIDANCE + '读取 Skill 与覆盖设计参考。可先侦察页面认识功能；复用已有设计和准备；新任务保存本批必要具体设计并标明执行方式后直接测试，不等待无关准备或重复扩写计划。完整目标范围继续维护，仍有价值但依赖真实角色、设备、辅助技术、人工判断或额外授权的用例完整保留给人工，不缩成遗漏说明。执行中新发现的场景继续追加，不把基线锁死；不设条数配额，不让用户填表或审批计划。发布时如实说明实际执行与人工待执行范围。')}
            if action == "progress":
                phase = arguments.get("phase")
                if phase == "completed":
                    raise ValueError("完成状态由已保存的任务报告确认，请使用 publish_task_report")
                return record_progress(store, owner, pid, phase, arguments.get("message", ""))
            if action == "task":
                return update_task(request, pid, arguments)
            if action == "task_report":
                ensure_idle(owner)
                if project.get('test_kind') == 'ui':
                    if not project.get('ui_execution_id'):
                        raise ValueError('UI 任务请先保存具体用例，再发布本任务唯一的阶段报告')
                    return ui_records.publish(store, owner, project, project['ui_execution_id'],
                                              arguments.get('title', 'UI 测试报告'), arguments.get('summary', ''))
                return save_task_report(store, owner, project, arguments)
            if action == "document":
                content = current_document_path(store, owner, project).read_text()
                offset, limit = arguments.get("offset", 0), arguments.get("limit", 24000)
                if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 60000:
                    raise ValueError("offset 需为非负整数，limit 需为 1–60000")
                return {"testing_policy": testing_policy.snapshot(), "project_id": pid, "filename": project.get("effective_filename", project["filename"]), "task": project.get("task", {}),
                        "content": content[offset:offset + limit], "offset": offset, "total_chars": len(content),
                        "next_offset": offset + limit if offset + limit < len(content) else None,
                        "sha256": hashlib.sha256(content.encode()).hexdigest(),
                        'attachments': project.get('ui_requirement_attachments', []),
                        'attachment_guidance': ui_attachments.GUIDANCE,
                        **({'testing_skill': _ui_testing_skill(project, arguments.get('role', '')), 'execution_id': project.get('ui_execution_id'), 'defect_title_guidance': AI_TITLE_GUIDANCE,
                            'requirements_guidance': requirement_design.GUIDANCE,
                            'requirement_design': requirement_design.view(store, owner, pid),
                            'execution': app.state.managed_workflow.summary(owner,pid),
                            'execution_round': project.get('execution_round'), 'parallel_execution_guidance': _ui_parallel_guidance(arguments.get('role', '')),
                            'execution_permission': project.get('ui_execution_permission'),
                            'design_references': [] if scope else ui_design_references.catalog(app.state.managed_workflow.controller, owner, project),
                            'design_reference_guidance': ui_design_references.GUIDANCE,
                            'regression_round': project.get('regression_round'),
                            'retest_task': project.get('ui_retest_round') or None,
                            'scene_retention': project.get('ui_scene_retention', ui_scene_retention(None))} if project.get('test_kind') == 'ui' else {}),
                        "parse_issues": store.load_asset(owner, pid, "contract").get("issues", [])}
            if action == "context":
                contract = store.load_asset(owner, pid, "contract")
                chosen = arguments.get("operation_ids")
                if chosen:
                    if not isinstance(chosen, list) or any(oid not in contract["operations"] for oid in chosen):
                        raise ValueError("operation_ids 包含未知接口")
                    contract["operations"] = {oid: contract["operations"][oid] for oid in chosen}
                    source_ids = {sid for op in contract["operations"].values() for sid in op.get("source_ids", [])}
                    contract["sources"] = {sid: source for sid, source in contract["sources"].items() if sid in source_ids}
                # Instructions + contract contain the format and original evidence;
                # avoid duplicating the entire document on every tool call.
                try:
                    instructions, format_prompt = model_prompts(contract, "", codex=True)
                    example = json.loads(format_prompt)["required_output_example"]
                except ValueError as exc:
                    instructions, example = "声明式执行格式暂不可用：" + str(exc), None
                candidates, revision = mcp_revision(owner, pid)
                details = project_details(request, pid)
                offset, limit = arguments.get("offset", 0), arguments.get("limit", 50)
                if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 200:
                    raise ValueError("offset 需为非负整数，limit 需为 1–200；这是读取分页大小，不是用例总数限制")
                page = candidates["cases"][offset:offset + limit]
                page_ids = {c["id"] for c in page}
                return {"testing_policy": testing_policy.snapshot(), "project": project, "contract": contract, "candidate_instructions": instructions,
                        "attachments": project.get("ui_requirement_attachments", []), "attachment_guidance": ui_attachments.GUIDANCE,
                        "candidate_example": example,
                        "workflow_guidance": "按用户目标完成任务并输出报告。接口范围以当前 contract.operations 为准，不要重新加入已删除的接口。文档检查无需构造用例，使用 get_test_document 读取全文、publish_task_report 保存分析。需要设计或执行时，先完整保存具体用例（含暂不可执行项的 design），再按同一 ID 补充步骤、核对、采纳和执行。不要因清理、预期或工具表达缺口而删减设计；真实请求直接使用项目中保存的本次测试地址，逐条解决可修正的阻塞。地址为空时只做文档分析，不发送请求。最终报告只写结论、问题和未执行缺口；完整设计和逐条请求/断言分别查看独立用例页与执行报告，不重复展开。",
                        "report_submission": {"preferred_tool": "publish_task_report",
                            "compatible_tool": "submit_test_cases",
                            "compatible_cases": [{"record_type": "task_report", "title": "任务报告", "summary": "填写实际结论", "sections": [], "findings": [], "run_ids": []}],
                            "note": "若当前 Codex 连接尚未加载新工具，用 submit_test_cases 携带当前 revision 和上述单条报告记录即可直接发布报告，无需可执行用例。当前文档可通过 get_test_document 读取；原始文档仅供对照。"},
                        "base_url": project.get("task", {}).get("base_url", ""),
                        "target": {"base_url": project.get("task", {}).get("base_url", ""),
                                   "required_for_execution": bool(project.get("task", {}).get("base_url")),
                                   "document_only_allowed": True},
                        "execution_capabilities": {"case_workers": CASE_WORKERS,
                            "concurrency": "已核对独立性的用例可声明 execution_policy={mode:'independent',reason:'具体隔离依据'}；未声明的用例与同一用例内的步骤顺序执行。共享账号、资源、计数或时序的用例保留串行。",
                            "target": "真实请求只发送到项目中保存的本次测试地址；空地址仅允许文档分析。",
                            "cleanup": "按用例声明的清理步骤和当前服务端配置执行；清理证据会写入执行报告。",
                            # Kept as a compatibility field for old Codex
                            # sessions; current instructions do not expose
                            # or ask users to select this capability.
                            "gomoku_cleanup": "当前会话已保留专用清理能力，请按返回的用例和执行证据使用。" if project_environment(project) == "gomoku" else None},
                        "candidates": {**candidates, "cases": page}, "revision": revision,
                        "pagination": {"offset": offset, "limit": limit, "total": len(candidates["cases"]),
                                       "next_offset": offset + limit if offset + limit < len(candidates["cases"]) else None},
                        "testing_skill": _testing_skill(),
                        "case_status": [{"id": c["id"], "state": c["state"], "review": c.get("web", {}), "reason": c.get("reason", "")}
                                        for c in (details.get("bundle") or {}).get("cases", []) if c["id"] in page_ids]}
            if action == "rules":
                mode = arguments.get("mode", "auto")
                if mode not in {"auto", "baseline"}:
                    raise ValueError("MCP 仅允许本地规则生成；模型用例由 Codex 提交")
                return generate(request, pid, {"mode": mode})
            if action == "submit":
                ensure_idle(owner)
                previous, revision = mcp_revision(owner, pid)
                if arguments.get("revision") != revision:
                    raise HTTPException(409, "用例版本已变化，请重新读取 context 后提交")
                incoming = arguments.get("cases")
                if not isinstance(incoming, list) or not incoming:
                    raise ValueError("请提交非空 cases 数组")
                if len(incoming) == 1 and isinstance(incoming[0], dict) and incoming[0].get("record_type") == "task_report":
                    return save_task_report(store, owner, project, incoming[0])
                if project.get('case_workflow') == 'own':
                    raise ValueError('此会话选择执行自己的用例，请通过网页导入或编辑；切换到 AI 方式后可补充生成')
                if any(not isinstance(c, dict) or not isinstance(c.get("id"), str) for c in incoming):
                    raise ValueError("每条用例必须包含字符串 id")
                if len({c["id"] for c in incoming}) != len(incoming):
                    raise ValueError("提交的用例 id 不能重复")
                try:protected = {c['id'] for c in store.load_asset(owner, pid, 'bundle').get('cases', []) if c.get('web', {}).get('source') == 'user'}
                except FileNotFoundError:protected = set()
                prior = {c['id']: c for c in previous['cases']}
                if any(c['id'] in protected and c != prior.get(c['id']) for c in incoming):
                    raise ValueError('导入的用户用例作为基线保留；AI 补充请使用新 ID，需要编辑原用例时使用网页链路编辑入口')
                merged = {cid: c for cid, c in prior.items() if cid in protected} if arguments.get("replace") is True else prior
                merged.update({c["id"]: c for c in incoming})
                candidates = {"schema_version": "1.0", "cases": list(merged.values())}
                contract = store.load_asset(owner, pid, "contract")
                bundle = decorate_bundle(project, compile_model_bundle(contract, json.dumps(candidates, ensure_ascii=False, allow_nan=False)))
                bundle = refresh_approval_eligibility(bundle)
                try:
                    old_bundle = store.load_asset(owner, pid, "bundle")
                except FileNotFoundError:
                    old_bundle = {}
                unchanged_ids = {c["id"] for c in previous["cases"] if merged.get(c["id"]) == c}
                bundle = preserve_reviews(bundle, old_bundle, unchanged_ids)
                for case in bundle['cases']:case['web']['source'] = 'user' if case['id'] in protected else 'ai'
                bundle["generation"].update(origin="codex-mcp", model_api_calls=0)
                check_web_bundle(bundle)
                errors = validate_bundle(bundle)
                if errors:
                    raise ValueError("用例校验失败：" + errors[0]["message"])
                store.save_asset(owner, pid, "mcp-candidates", candidates)
                store.save_asset(owner, pid, "bundle", bundle)
                store.update_project(owner, pid, {"status": "generated", "bundle_summary": _summary(bundle), "generation_mode": "mcp", "last_job": {}})
                return {"summary": _summary(bundle), "revision": mcp_revision(owner, pid)[1],
                        "cases": [{"id": c["id"], "state": c["state"], "review": c.get("web", {}), "reason": c.get("reason", "")}
                                  for c in bundle["cases"] if c["id"] in {c["id"] for c in incoming}],
                        "note": "按 id 分批合并保存。未改动用例保留采纳状态；新增或修改项需核对采纳。缺少预期的项保留待确认，不妨碍其他用例执行。"}
            if action == "approve":
                ensure_idle(owner)
                result = approve(request, pid, {"case_ids": arguments.get("case_ids")})
                return {"summary": result["summary"], "accepted_case_ids": result["accepted_case_ids"], "skipped_cases": result["skipped_cases"]}
            if action == "run":
                ensure_idle(owner)
                return execute(request, pid, arguments)
            if action == "report":
                total = {}
                if project.get('test_kind') == 'ui' and project.get('last_analysis'):
                    from .ui_total_reports import canonical_project, entry as total_entry
                    total = {'total_report': total_entry(canonical_project(store, owner, project))}
                analysis = project.get("last_analysis")
                if analysis and (not project.get("last_run") or analysis["created_at"] >= project["last_run"]["created_at"]):
                    result = store._read(store.project_dir(owner, pid) / "analyses" / analysis["id"] / "report.json")
                    if result.get('ui_snapshot'):
                        result = ui_report_corrections.apply(result, ui_report_corrections.load(store, owner, pid, analysis['id']), store=store, owner=owner)
                        from .ui_asset_withdrawals import report_view
                        result = report_view(store, owner, result)
                    return {"project_id": pid, "report": analysis, "analysis": result, "cases": [], **total}
                run = project.get("last_run")
                if not run:
                    return {"project_id": pid, "report": None, "message": "尚未执行，没有报告"}
                result = store._read(store.project_dir(owner, pid) / "runs" / run["id"] / "result.json")
                return {"project_id": pid, "report": run,
                        "cases": [{"id": c.get("id"), "status": c.get("status"), "reason": c.get("reason"),
                                   **({"steps": c.get("steps", []), "cleanup": c.get("cleanup")} if arguments.get("include_evidence") else {})}
                                  for c in result.get("cases", [])]}

    app.mount("/landing-pages", StaticFiles(directory=STATIC / "sylva-background" / "landing-pages", check_dir=False), name="sylva-assets")
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    # Register last so this is outside authentication/session middleware, whose
    # ordinary GET paths can create session files. Existing deployment draining
    # still governs active releases; this stronger gate is only the first
    # PostgreSQL activation window.
    @app.middleware("http")
    async def storage_activation_gate(request: Request, call_next):
        readonly_asset = (request.method in {'GET', 'HEAD'} and
                          (request.url.path == '/healthz' or
                           request.url.path.startswith(('/static/', '/landing-pages/'))))
        if not storage_gate.active and not readonly_asset:
            return JSONResponse({'detail': '测试台正在核验数据库迁移，暂不接收请求。'}, 503,
                                headers={'Retry-After': '5'})
        return await call_next(request)
    return app


def serve(host="127.0.0.1", port=18089, data_dir=None):
    import uvicorn
    public_port = int(os.environ.get('API_TEST_PUBLIC_REPORT_PORT', '0'))
    public_server = public_thread = None
    if public_port:
        public_server = uvicorn.Server(uvicorn.Config(
            create_app(data_dir, start_fixture=False, report_only=True), host='0.0.0.0', port=public_port,
            access_log=False, proxy_headers=False))
        public_thread = threading.Thread(target=public_server.run, name='public-report-server', daemon=True)
        public_thread.start()
    try:
        uvicorn.run(create_app(data_dir), host=host, port=port, access_log=False, proxy_headers=False)
    finally:
        if public_server and public_thread:
            public_server.should_exit = True
            public_thread.join(timeout=10)
