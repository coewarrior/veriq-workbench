"""Owner control plane and separately authenticated execution-host protocol."""
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from .orchestration import Controller, Conflict


def install(app, store, static):
    controller = Controller(store)
    app.state.orchestration = controller
    from .managed_service import ManagedService
    managed = ManagedService(controller, static)
    app.state.managed_service = managed
    from .managed_workflow import ManagedWorkflow
    workflow=ManagedWorkflow(managed)
    app.state.managed_workflow=workflow

    @app.get('/orchestration')
    def page():
        return RedirectResponse('/ui-testing', status_code=303)

    @app.get('/api/account-projects')
    def account_projects(request: Request):
        return {'projects': controller.account_projects.list(request.state.owner)}

    @app.post('/api/account-projects')
    def create_account_project(request: Request, data: dict):
        return controller.account_projects.create(request.state.owner, data)

    @app.get('/api/account-projects/{aid}')
    def account_project(request: Request, aid: str):
        return controller.account_projects.get(request.state.owner, aid)

    @app.patch('/api/account-projects/{aid}')
    def rename_account_project(request: Request, aid: str, data: dict):
        return controller.account_projects.rename(request.state.owner, aid, data)

    @app.delete('/api/account-projects/{aid}')
    def delete_account_project(request: Request, aid: str):
        return controller.account_projects.delete(request.state.owner, aid)

    @app.delete('/api/account-projects/{aid}/accounts/{account_id}')
    def remove_project_account(request: Request, aid: str, account_id: str):
        return controller.account_projects.remove_account(request.state.owner, aid, account_id)

    @app.post('/api/account-projects/{aid}/configure')
    def configure_account_project(request: Request, aid: str, data: dict):
        return controller.account_projects.configure(request.state.owner, aid, data)

    @app.get('/api/projects/{pid}/account-project')
    def session_account_project(request: Request, pid: str):
        return {'project': controller.account_projects.binding(request.state.owner, pid)}

    @app.post('/api/projects/{pid}/account-project')
    def bind_account_project(request: Request, pid: str, data: dict):
        return controller.account_projects.bind(request.state.owner, pid, data.get('account_project_id'))

    @app.get('/api/projects/{pid}/managed')
    def workflow_status(request: Request, pid: str):
        return workflow.status(request.state.owner,pid)

    @app.post('/api/projects/{pid}/managed/start')
    def workflow_start(request: Request, pid: str, data: dict):
        return workflow.start(request.state.owner,pid,data)

    @app.post('/api/projects/{pid}/managed/configure')
    def workflow_configure(request: Request, pid: str, data: dict):
        return workflow.configure(request.state.owner,pid,data)

    @app.post('/api/orchestration/console')
    def console_open(request: Request, data: dict):
        return managed.console.open(request.state.owner,data)

    @app.post('/api/orchestration/console/{sid}/command')
    def console_command(request: Request, sid: str, data: dict):
        return managed.console.submit(request.state.owner,sid,data)

    @app.get('/api/orchestration/console/{sid}/command/{cid}')
    def console_result(request: Request, sid: str, cid: str):
        return managed.console.result(request.state.owner,sid,cid)

    @app.post('/api/orchestration/console/{sid}/close')
    def console_close(request: Request, sid: str):
        return managed.console.close(request.state.owner,sid)

    @app.post('/api/orchestration/hosts/{host_id}/revoke')
    def revoke(request: Request, host_id: str):
        return managed.revoke(request.state.owner, host_id)

    @app.patch('/api/orchestration/accounts/{account_id}')
    def edit_account(request: Request, account_id: str, data: dict):
        return managed.change_account(request.state.owner, account_id, data)

    @app.delete('/api/orchestration/accounts/{account_id}')
    def delete_account(request: Request, account_id: str, data: dict):
        return managed.change_account(request.state.owner, account_id, data, delete=True)

    @app.post('/api/orchestration/accounts/{account_id}/login')
    def login(request: Request, account_id: str, data: dict):
        return managed.configure_account(request.state.owner,account_id,data)

    @app.post('/api/orchestration/policies')
    def policy(request: Request, data: dict):
        return managed.save_policy(request.state.owner,data)

    @app.post('/api/orchestration/policies/{policy_id}/revoke')
    def revoke_policy(request: Request, policy_id: str):
        controller.revoke_policy(request.state.owner,policy_id)
        return {'revoked':True}

    @app.post('/api/orchestration/leases/{lease_id}/human-mode')
    def human_mode(request: Request, lease_id: str):
        return managed.human_mode(request.state.owner,lease_id)

    @app.post('/api/orchestration/leases/{lease_id}/resolve')
    def resolve(request: Request, lease_id: str, data: dict):
        return managed.resolve(request.state.owner,lease_id,data)

    @app.get('/api/orchestration/tasks/{task_id}/report')
    def report(request: Request, task_id: str):
        return managed.report(request.state.owner,task_id)

    @app.get('/api/orchestration/bootstrap')
    def bootstrap(request: Request):
        projects=store.list_projects(request.state.owner)
        return dict(csrf=request.state.csrf, projects=[{
            'id':p['id'], 'title':p.get('title',p.get('filename',p['id'])),
            'test_kind':p.get('test_kind','api')
        } for p in projects if not p.get('managed_node_id')])

    @app.get('/api/orchestration')
    def status(request: Request, task_id: str = '', activity: bool = False):
        result = controller.snapshot(request.state.owner, task_id or None)
        if activity:
            if not task_id:
                raise HTTPException(400, '请选择原测试轮次查看待处理事项')
            from .native_coordination import view
            result['activity'] = view(controller, request.state.owner, task_id)['activity']
        return result

    @app.post('/api/orchestration/accounts')
    def account(request: Request, data: dict):
        return controller.add_account(request.state.owner, data)

    @app.post('/api/orchestration/tasks')
    def create(request: Request, data: dict):
        return controller.create_task(request.state.owner, data)

    @app.post('/api/orchestration/tasks/{task_id}/control')
    def control(request: Request, task_id: str, data: dict):
        if data.get('action') == 'confirm_native_exit':
            from .native_execution import NativeExecution
            return NativeExecution(managed.direct).confirm_exit(request.state.owner,task_id,data)
        return controller.control(request.state.owner, task_id, data)

    @app.post('/api/orchestration/nodes/{node_id}/split')
    def split(request: Request, node_id: str, data: dict):
        return controller.split(request.state.owner, node_id, data)

    @app.exception_handler(Conflict)
    async def conflict(request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail':str(exc)}, 409)

    return controller


def dispatch(controller, request, action, arguments):
    # A report-scoped collaborator cannot turn report access into account access.
    if request.state.mcp_scope:
        raise HTTPException(403, '此连接只有报告协作权限；任务调度请使用工作空间连接')
    owner=request.state.owner
    if action=='direct_session':
        return request.app.state.managed_service.direct.call(owner,arguments)
    if action=='managed_projects':
        return {'projects':controller.account_projects.list(owner)}
    if action=='managed_bind_project':
        return controller.account_projects.bind(owner,arguments.get('project_id'),arguments.get('account_project_id'))
    if action=='managed_start':
        return request.app.state.managed_workflow.start(owner,arguments.get('project_id'),
            {'execution_route':'native_browser',**arguments})
    if action=='managed_report':
        return request.app.state.managed_service.report(owner,arguments.get('task_id'))
    if action=='managed_status':
        return controller.snapshot(owner, arguments.get('task_id'))
    if action=='managed_create':
        return controller.create_task(owner, {**arguments,'independent_module_records':True,
            'session_workflow':controller.project(owner,arguments.get('project_id')).get('test_kind')=='ui'})
    if action=='managed_control':
        if arguments.get('action') == 'confirm_native_exit':
            from .native_execution import NativeExecution
            return NativeExecution(request.app.state.managed_service.direct).confirm_exit(
                owner,arguments.get('task_id'),arguments)
        return controller.control(owner, arguments.get('task_id'), arguments)
    if action=='managed_split':
        return controller.split(owner, arguments.get('node_id'), arguments)
    raise ValueError('未知调度操作')
