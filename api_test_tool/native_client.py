"""Build the real desktop-tool chain, without impersonating a desktop API.

The downloadable client embeds this helper and template. Generating a script
does not execute it; the caller runs it once in functions.exec where the native
message tool is actually available.
"""
import json


NATIVE_HANDOFF_CAPABILITY = 'native_handoff_exec_v1'
NATIVE_DIRECT_HANDOFF_CAPABILITY = 'native_direct_handoff_exec_v1'
NATIVE_COORDINATOR_WAIT_CAPABILITY = 'native_coordinator_wait_v1'


def bound_handoff_arguments(binding, arguments):
    """Reuse the last successful local binding, never infer exit or timestamps."""
    fields = ('holder_id', 'task_id', 'node_id', 'lease_id', 'project_id', 'execution_id')
    if (not isinstance(binding, dict) or any(not isinstance(binding.get(k), str) or not binding[k] for k in fields)
            or type(binding.get('revision')) is not int or binding['revision'] < 1):
        raise ValueError('收尾使用原生记录的完整 binding-file 和成功保存的 revision')
    result = dict(arguments)
    for key in ('holder_id', 'task_id', 'node_id', 'lease_id', 'account_id'):
        if key in binding:
            if key in result and result[key] != binding[key]:
                raise ValueError('收尾参数与原绑定不一致：' + key)
            result[key] = binding[key]
    for key in ('dispatch_id', 'executor_ref'):
        if binding.get(key) and not result.get(key):
            result[key] = binding[key]
    values = dict(result.get('arguments') or {})
    if values.get('final_report') is not None:
        if result.get('action') != 'finish' or values.get('browser_stopped') is not True:
            raise ValueError('合并收尾须先真实停止本任务浏览器，再提交 finish')
        final = dict(values['final_report'])
        for key in ('project_id', 'execution_id', 'revision'):
            if key in final and final[key] != binding[key]:
                raise ValueError('收尾报告与最后保存绑定不一致：' + key)
            final[key] = binding[key]
        values['final_report'] = final
    if values.get('publish_saved') is True:
        values['publication_binding'] = {key: binding[key] for key in ('project_id', 'execution_id', 'revision')}
    result['arguments'] = values
    return result


def handoff_arguments(arguments):
    """Opt the new executable entry into direct delivery; bare calls stay legacy."""
    if arguments.get('action') != 'finish':
        return arguments
    values = arguments.get('arguments') or {}
    if 'result' in values and not isinstance(values['result'], str):
        raise ValueError('arguments.result 使用 passed/failed/partial/blocked/not_run 字符串；统计保留在用例结果中，尚未发送收尾请求')
    return {**arguments, 'arguments': {**(arguments.get('arguments') or {}),
                                      'handoff_route': 'direct_successors'}}


def native_mcp_script(template, arguments):
    if arguments.get('action') not in {'finish', 'dispatch'} or (
            arguments.get('action') == 'dispatch' and not (arguments.get('arguments') or {}).get('handoff_ack')):
        raise ValueError('交接编排仅接受原 finish 或 dispatch 参数')
    return template + '\n' + 'const nativeArguments = ' + json.dumps(handoff_arguments(arguments), ensure_ascii=False) + ';\n' + native_mcp_transport() + r"""
text(await completeNativeHandoff(callNative, nativeArguments,
  tools.mcp__codex_app__send_message_to_thread));
"""


def native_mcp_transport():
    return r"""
const nativeTools = ALL_TOOLS.filter(item => item.name.endsWith("__direct_test_session"));
if (nativeTools.length !== 1) throw new Error("先发现当前测试台 direct_test_session 工具，再执行原编排；不能猜工具名称");
const callNative = async args => {
  const result = await tools[nativeTools[0].name](args);
  if (result?.isError) throw new Error("原平台调用失败；不发送或重发");
  if (result?.structuredContent) return result.structuredContent;
  for (const item of result?.content || []) {
    if (item.type === "text") {
      try { return JSON.parse(item.text); } catch (_) {}
    }
  }
  if (result && typeof result === "object" && !result.content) return result;
  throw new Error("平台回执格式未知；不发送或重发");
};
"""

def native_handoff_script(template, command, arguments, receipt_directory=None, initial_result=None):
    action = arguments.get('action')
    if action not in {'finish', 'dispatch'} or (
            action == 'dispatch' and not (arguments.get('arguments') or {}).get('handoff_ack')):
        raise ValueError('原生交接编排仅接受原 finish 或包含 handoff_ack 的原 dispatch')
    return template + '\n' + native_cli_transport(command, receipt_directory) + (
        'const nativeArguments = ' + json.dumps(handoff_arguments(arguments), ensure_ascii=False) + ';\n'
        'const initialResult = ' + json.dumps(initial_result, ensure_ascii=False) + ';\n'
        'text(await completeNativeHandoff(callNative, nativeArguments, '
        'tools.mcp__codex_app__send_message_to_thread, initialResult));\n')


def native_cli_transport(command, receipt_directory=None):
    # command is an argv array from this running client, never a server-supplied
    # shell command. Quote every argument independently before invoking the CLI.
    import tempfile
    control_directory = str(receipt_directory) if receipt_directory else tempfile.mkdtemp(prefix='native-control-')
    template = globals().get('NATIVE_CONTROL_TEMPLATE')
    if template is None:
        from pathlib import Path
        template = (Path(__file__).parent / 'static/native-control-read.js').read_text()
    return template + '\n' + r'''
const nativeCommand = ''' + json.dumps(command, ensure_ascii=False) + r''';
const receiptDirectory = ''' + json.dumps(str(receipt_directory) if receipt_directory else None) + r''';
const controlDirectory = ''' + json.dumps(control_directory) + r''';
let controlSequence = 0;
const shellQuote = value => "'" + String(value).replace(/'/g, "'\\''") + "'";
const callNative = async args => {
  const phase = args.arguments?.handoff_delivery?.state;
  const receiptFile = receiptDirectory && receiptDirectory + '/' +
    (phase ? 'delivery-' + phase : args.record_action === 'publish' ? 'handoff-publication-result' : args.action === 'dispatch' ? 'ack-server-result' : 'closeout-result') + '.json';
  const controlFile = controlDirectory + '/control-' + Date.now() + '-' + (++controlSequence) + '.json';
  const command = [...nativeCommand, "--args", JSON.stringify(args), '--control-result-file', controlFile,
    ...(receiptFile ? ['--receipt-file', receiptFile] : [])].map(shellQuote).join(" ");
  let execution = await tools.exec_command({cmd: command, max_output_tokens: 12000, yield_time_ms: 10000});
  let output = execution.output;
  while (execution.session_id && execution.exit_code == null) {
    execution = await tools.write_stdin({session_id: execution.session_id, chars: "",
      max_output_tokens: 12000, yield_time_ms: 1000});
    output += execution.output;
  }
  if (execution.exit_code !== 0) {
    throw new Error("原平台调用未取得确定回执；保留原事件，不自动重发");
  }
  return await nativeReadControl(tools, nativeCommand.slice(0, -2), controlFile);
};
'''


def native_coordinator_script(template, handoff_template, arguments, *, command=None):
    from uuid import UUID
    config = dict(arguments)
    for key in ('holder_id', 'coordinator_ref'):
        if not isinstance(config.get(key), str) or not config[key]:
            raise ValueError('协调等待需原 holder_id 与真实 coordinator_ref')
    UUID(config['coordinator_ref'].removeprefix('thread:'))
    ids = config.get('task_ids')
    if not isinstance(ids, list) or not ids or any(not isinstance(tid, str) or not tid for tid in ids):
        raise ValueError('协调等待需本轮原 task_ids')
    config['task_ids'] = list(dict.fromkeys(ids))
    # Reuse the established startup observation basis, not an eligibility or
    # recovery deadline. The outer window bounds only this tool invocation.
    for key in ('observation_seconds', 'window_seconds'):
        if key not in config:
            continue
        value = config[key]
        if type(value) not in (int, float) or not 0 < value < float('inf'):
            raise ValueError(key + ' 必须是有限正数，仅用于本次观察')
    for target in config.get('targets', []):
        if not isinstance(target, dict) or not isinstance(target.get('threadId'), str):
            raise ValueError('targets 使用公开 wait_threads 的真实 threadId/hostId')
    transport = native_cli_transport(command) if command else native_mcp_transport()
    return handoff_template + '\n' + template + '\n' + transport + (
        'const coordinatorConfig = ' + json.dumps(config, ensure_ascii=False) + ';\n'
        'text(await waitNativeCoordinator(callNative, tools.mcp__codex_app__wait_threads, '
        'tools.mcp__codex_app__send_message_to_thread, coordinatorConfig));\n')


def native_client_status(result):
    if (result.get('mode') == 'native_browser' or result.get('handoff')
            or result.get('continuation')):
        result = {**result, 'execution_client': {
            **result.get('execution_client', {}),
            'native_handoff': NATIVE_HANDOFF_CAPABILITY,
            'native_direct_handoff': NATIVE_DIRECT_HANDOFF_CAPABILITY,
            'native_handoff_automatic': False,
            'handoff_executor': 'functions.exec',
            'handoff_command': 'native-handoff-script',
            'handoff_guidance': (
                '原生收尾或消费交接使用 native-handoff-script --args-file 原参数文件，'
                '把返回的 script 原样作为 functions.exec 代码执行一次。'
                '新版finish在同次工具执行直接通知有资源的原后继，无需先唤醒协调者；'
                '只在原组结束或异常需协调时通知协调者。旧事件保持原路线，旧v1能力不代表支持直达。'
                '同次工具执行完成平台调用、发送占用、真实桌面消息与回执；'
                '脚本生成、本地文件和CLI单独finish都不是送达。未知发送不重发。'),
        }}
    return result
