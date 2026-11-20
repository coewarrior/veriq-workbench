"""Read-only status for desktop-owned execution; no desktop cancellation claims."""
from uuid import UUID


def browser_launch_policy(binding=None):
    """Launch instructions, not a claim that the server controls desktop tabs."""
    policy = {
        'browser': 'iab', 'options': {'visible': False},
        'foreground_fallback': False,
        'login_context_isolation': 'must_use_actual_browser_context',
        'guidance': (
            '新建原生测试页面默认使用 cua.createBrowserTab("iab", target_url, {visible:false})。'
            '隐藏页面不等于独立登录环境；只在选择或交接浏览器时核对对应账号和上下文，'
            '不新增逐动作检查。没有可用后台登录上下文时登记实际资源等待，'
            '不得删掉 visible:false 静默改用可见 Chrome、抢用其他任务登录态或切换 Runner。'
            '已有在途测试保留原现场，在正常资源交接时应用此安排。'
            '复用已确认页面、定位器和当前工具公开 API，将已知动作、本次业务完成等待、'
            '局部观察及逐项断言放在同次原生调用；正常步骤不逐动作追加全页 getAXState。'
            '等待同时识别真实中间步骤和失败状态，出现后按新状态继续，不盲等旧最终目标。'
            '导航后确认目标 URL 或内容已提交再刷新；某个未出现的加载文案已隐藏不证明完成。'
            '准备默认用 native-prepare 复用原设计和绑定，失败立即停止后续步骤；实际判定用 native-observe 或 native-record。'
            '有 CLI 时协调者派发前用 native-run-kit 生成固定生命周期包；执行者按返回的 first_action 先完成环境入口，再 prepare，ready 后直接打开真实入口。'
            '浏览器断言输出 case_id/status/checks(name,expected,observed,ok) 原值，交由固定入口生成结果，不另写长篇实际结果。'
            '同次 observation 可带 case_changes 和 asset_files 保存已知真实步骤、检查点及附件；复用回执动态缺口，不积到最后重写。'
            '读取当前完整状态须用工具文档的完整快照选项，不把增量快照中未出现的旧内容判为缺失。'
            '末条断言后的真实清理关页可在同次浏览器调用完成，再在同次编排保存、交还、发布和通知；仅明确结束且实际退出时才交还；保存未知保留现场及未确认状态。'
            '实际清理关页后立即用 native-closeout-script --browser-stopped --reason 真实依据，服务器先交还再汇总原记录；不临时拼总结。旧入口可将必要总结放入 finish.arguments.final_report，'
            '若关页后还需整理报告，缓存生命周期 release 先交还和通知后继，complete 只补原轮变化再发布；不重新领取账号。'
            '用原绑定和清单一次保存、交还、发布并通知后继，直接使用 publication 回执；'
            '每条判定后立即用原保存入口同步，成功后再开始下一条；'
            '不在受限原生工具中导入记录模块、读取凭据或另建浏览器代理。'
            '弹窗变为页内详情等结构变化后，按实际结构重新定位，不重复等待旧定位器。'
            '仅在定位超时、空快照或句柄异常时，按当前工具文档在同次调用读取原句柄 URL 和页面状态，'
            '保留已完成观察；确证 about:blank 且没有在途写入或未保存输入后，'
            '由 Codex 决定是否恢复明确的原只读入口并等待实际就绪，'
            '不把空快照单独当作空白页，不重放结果未知的写入，也不为恢复切换账号或浏览器。'
        ),
    }
    policy['direct_isolated'] = {
        'browser': 'chromium', 'browser_tool': 'node_repl',
        'assignment_field': 'direct_browser', 'helper': '/static/native-isolated-browser.mjs',
        'action_transport': 'direct_playwright', 'per_action_authorization': False,
        'guidance': '多账号隔离使用独立进程、私有 profile 和持久 Context，Codex 直接连接并操作；'
                    'native-run-kit 生成一次环境入口，准备、保存、交还仍复用原链路，不接旧 Runner。',
    }
    if not binding or binding.get('browser') == 'chromium':
        policy.update(browser='chromium', browser_tool='node_repl', options={'headless': True},
            guidance=('新任务默认执行 native-run-kit 返回的 environment_setup，自动发现执行主机的 Playwright/Chromium；'
                      '无需填写 direct_browser、主机名或模块路径，不回退共享 IAB。'
                      '环境创建成功后运行原 prepare；复用 nativeBrowserEnvironment 和真实 Playwright Page；'
                      '账号绑定只在首次取得页面时核对，后续动作直接执行。普通错误返回 Codex 判断，不关闭或交还；REPL 重置连接原浏览器。明确结束才关闭整个任务环境。'
                      + policy['guidance'][policy['guidance'].index('已有在途测试'):]))
    return policy


def is_native(task):
    return task.get('execution_route') == 'native_browser'


def desktop_stop_view(state, *, owner=None, task_id=None, node_ids=None):
    sessions = []
    tasks = [task for task in state['tasks'].values()
             if is_native(task) and (owner is None or task['owner'] == owner)
             and (task_id is None or task['id'] == task_id)
             and (node_ids is None or any(nid in node_ids for nid in task['node_ids']))]
    scheduling_stopped = bool(tasks)
    for task in tasks:
        for nid in task['node_ids']:
            node = state['nodes'][nid]
            if node.get('child_ids') or (node_ids is not None and nid not in node_ids):
                continue
            intent = node.get('control_intent', task['intent'])
            if intent == 'run' and node['state'] not in {'completed', 'blocked', 'stopped', 'paused'}:
                scheduling_stopped = False
            if intent not in {'stop', 'pause'}:
                continue
            receipt = node.get('executor_dispatch') or node.get('dispatch_offer') or {}
            lease = next((item for item in state['leases'].values() if item['node_id'] == nid), None)
            if not lease and not receipt.get('holder_id') and not receipt.get('executor_ref'):
                continue
            ref = receipt.get('executor_ref', '')
            thread_id = ref.removeprefix('thread:')
            try:
                thread_url = 'codex://threads/' + str(UUID(thread_id))
            except (ValueError, AttributeError, TypeError):
                thread_url = ''
            exited = bool(receipt.get('exit_acknowledged_at'))
            browser_stopped = (lease.get('browser_stopped') is True if lease else
                               bool(node.get('native_browser_stopped') or not node.get('attempts')))
            sessions.append({
                'node_id': nid, 'title': node['title'], 'executor_ref': ref,
                'thread_url': thread_url,
                'executor_exit_confirmed': exited,
                'browser_stopped': browser_stopped,
                'accounts_released': lease is None,
                'exit_confirmation_source': node.get('native_exit_evidence', {}).get('source'),
                'desktop_api_cancelled': False,
            })
    return {
        'platform_scheduling_stopped': scheduling_stopped,
        'manual_stop_required': any(not row['executor_exit_confirmed'] or
                                    not row['browser_stopped'] for row in sessions),
        'required_sessions': sessions,
        'method': 'desktop_manual_s1',
    }
