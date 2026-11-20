import copy
import json
import re
import subprocess
from html import unescape

import pytest

from api_test_tool.defect_drafts import DRAFT_SCRIPT, case_defect_draft
from api_test_tool.reporting import write_report
from api_test_tool.task_reports import render_task_report


@pytest.fixture
def evidence():
    case = {"id": "CREATE-001", "title": "创建资源后查询名称", "status": "FAIL", "steps": [
        {"id": "create", "status": "PASS", "request": {"method": "POST", "url": "http://localhost:18082/items",
            "headers": {"Authorization": "Bearer test-secret-1234"}, "body": {"name": "测试资源"}},
            "response": {"status": 201, "body": {"id": 7}}, "assertions": []},
        {"id": "get", "status": "FAIL", "request": {"method": "GET", "url": "http://localhost:18082/items/7", "headers": {}, "body": None},
            "response": {"status": 200, "body": {"name": "错误名称", "token": "private-token-5678"}, "elapsed_ms": 12},
            "assertions": [{"kind": "json_equal", "passed": False, "expected": "测试资源", "actual": "错误名称", "rule_id": "NAME"}]},
        {"id": "later", "status": "BLOCKED", "request": {}, "response": {}, "assertions": [], "error": "前置步骤未通过"}],
        "cleanup": {"status": "PASS", "steps": []}}
    bundle = {"contract": {"sources": {"doc": {"path": "openapi.yaml", "location": "GET /items/{id}", "excerpt": "返回创建时的资源名称。"}}},
        "rules": [{"id": "NAME", "description": "查询名称与创建名称一致", "source_ids": ["doc"]}],
        "cases": [{"id": case["id"], "steps": [{"id": "create", "title": "创建资源", "extract": [{"name": "item_id", "from": "json", "pointer": "/id"}]},
            {"id": "get", "title": "查询资源", "assertions": [{"kind": "json_equal", "pointer": "/name"}]}]}]}
    result = {"run_id": "run-001", "started_at": "2026-09-10T12:00:00+08:00", "environment": {"name": "本地测试", "base_url": "http://localhost:18082"},
        "cases": [case], "summary": {"total": 1, "FAIL": 1, "complete": True}}
    return result, bundle, case


def test_draft_preserves_reproduction_order_differences_and_sources(evidence):
    result, bundle, case = evidence
    original = copy.deepcopy(evidence)
    heading, text = case_defect_draft(result, bundle, case)
    assert heading == "接口缺陷描述"
    assert "GET /items/7" in text and "【测试环境】" in text
    assert text.index("1. 创建资源") < text.index("2. 查询资源") < text.index("3. later")
    assert "后续步骤使用的响应变量" in text and "item_id" in text
    assert "未发送请求；前置步骤未通过" in text
    assert '响应字段值 /name："测试资源"' in text and '响应字段值 /name："错误名称"' in text
    for internal in ("openapi.yaml", "【预期依据】", "【关联证据】", "run-001", "CREATE-001", "result.json", "bundle.json", "附件："):
        assert internal not in text
    assert "test-secret-1234" not in text and "private-token-5678" not in text
    assert "<redacted>" in text
    headers = re.search(r'请求头：(\{.*?\})', text, re.S)[1]
    assert json.loads(headers)["Authorization"] == "<redacted>"
    assert evidence == original


@pytest.mark.parametrize("status", ["PASS", "BLOCKED", "QUARANTINED", "UNSUPPORTED"])
def test_non_failures_have_no_defect_button(evidence, tmp_path, status):
    result, bundle, case = evidence
    case.update(status=status, steps=[])
    assert case_defect_draft(result, bundle, case) is None
    output = write_report(result, bundle, tmp_path / "index.html").read_text()
    assert 'class="copy-defect"' not in output


def test_timeout_and_cleanup_failure_are_not_labelled_functional_defects(evidence):
    result, bundle, case = evidence
    case.update(status="BROKEN", steps=[{"id": "get", "status": "BROKEN", "error": "Read timed out", "response": {}, "request": {"method": "GET", "url": "http://localhost/items/7"}}])
    heading, text = case_defect_draft(result, bundle, case)
    assert heading == "执行异常描述" and "Read timed out" in text
    assert "尚不能据此认定接口功能缺陷" in text and "未取得有效响应记录" in text
    case.update(status="PASS", steps=[], cleanup={"status": "FAIL", "steps": [{"id": "delete", "status": "FAIL", "response": {"status": 500}}]})
    heading, text = case_defect_draft(result, bundle, case)
    assert heading == "清理异常描述" and "[清理] delete" in text
    assert "不能据此判定业务断言失败" in text and "500" in text


def test_missing_evidence_does_not_invent_request_or_expected_result(evidence):
    result, bundle, case = evidence
    case.update(steps=[], reason="仅记录失败状态")
    _, text = case_defect_draft(result, bundle, case)
    assert "未记录请求步骤" in text and "缺少具体预期" in text
    assert "仅记录失败状态" in text


def test_draft_html_escapes_payload_and_keeps_copy_button_visible(evidence, tmp_path):
    result, bundle, case = evidence
    payload = '</textarea><script>alert("injection")</script>'
    case["title"] = payload
    output = write_report(result, bundle, tmp_path / "index.html").read_text()
    assert payload not in output
    assert payload in unescape(re.search(r'<textarea[^>]*>(.*?)</textarea>', output, re.S)[1])
    assert '</details><div class="defect-draft">' in output
    assert 'data-draft="defect-0"' in output and 'id="defect-0"' in output


def test_document_findings_have_copyable_description_without_fabricated_http():
    report = {"id": "review-1", "title": "文档检查", "goal": "仅检查文档", "created_at": "2026-09-10", "summary": "发现一处不一致",
        "document": {"filename": "openapi.yaml", "sha256": "abc"}, "runs": [], "requests_sent": 0, "sections": [],
        "findings": [{"title": "必填字段与示例不一致", "severity": "待确认", "detail": "声明必填 name，响应示例未提供。",
            "evidence": "GET /items/{id} 的 required 和 example", "recommendation": "核对实现后统一文档。"}]}
    html = render_task_report(report)
    assert "复制问题描述" in html
    draft = unescape(re.search(r'<textarea[^>]*>(.*?)</textarea>', html, re.S)[1])
    assert "required 和 example" in draft and "核对实现后统一文档" in draft
    assert "未记录的接口请求、响应及复现次数不作推定" in draft
    assert "HTTP 200" not in draft
    assert "review-1" not in draft and "SHA-256" not in draft and "【关联证据】" not in draft


def test_nested_password_data_is_redacted_before_json_serialization(evidence):
    result, bundle, case = evidence
    bundle['cases'][0]['variables'] = {'password': {'kind': 'unique', 'prefix': 'mvp_'}}
    case['steps'][0]['request']['body'] = {'username': 'mvp_example', 'password': {'nested': 'private-secret'}}
    _, text = case_defect_draft(result, bundle, case)
    assert '"kind": "unique"' not in text
    assert 'password：每次使用新生成的测试值' in text
    assert 'private-secret' not in text
    body = re.search(r'请求体：(\{.*?\})', text, re.S)[1]
    assert json.loads(body) == {'username': 'mvp_example', 'password': '<redacted>'}


@pytest.mark.parametrize("secure,modern_ok,legacy_ok,expected", [
    (True, True, False, "modern"), (False, False, True, "legacy"),
    (True, False, True, "legacy"), (False, False, False, "manual")])
def test_clipboard_secure_http_file_and_manual_fallback(secure, modern_ok, legacy_ok, expected):
    # Run the actual embedded report script, including edited-text copying and failure feedback.
    harness = r'''
const vm=require('node:vm'),assert=require('node:assert/strict');
const options=JSON.parse(process.argv[1]),script=process.argv[2];
let handler,mode,removed=false,timeoutCallback,timeoutDelay,timerSequence=0,clearCount=0; const status={},details={open:false};
const field={value:'编辑后的中文缺陷\n"参数"',closest:()=>details,focus(){},select(){mode='manual'}};
const button={dataset:{draft:'defect-0'},parentElement:{querySelector:()=>status},addEventListener:(name,fn)=>handler=fn,focus(){}};
const helper={style:{},setAttribute(){},focus(){},select(){},remove(){removed=true}};
const document={querySelectorAll:()=>[button],getElementById:()=>field,createElement:()=>helper,body:{appendChild(){}},execCommand:()=>{mode='legacy';return options.legacy_ok}};
const navigator={clipboard:{writeText:async text=>{assert.equal(text,field.value);if(!options.modern_ok)throw Error('denied');mode='modern'}}};
const setTimeout=(callback,delay)=>{timeoutCallback=callback;timeoutDelay=delay;return ++timerSequence};
const clearTimeout=()=>{clearCount++;timeoutCallback=undefined;timeoutDelay=undefined};
vm.runInNewContext(script,{document,navigator,window:{isSecureContext:options.secure},setTimeout,clearTimeout});
(async()=>{await handler();assert.equal(mode,options.expected);assert.equal(button.disabled,false);
if(mode==='manual'){assert.equal(details.open,true);assert.match(status.textContent,/已选中文字/);assert.equal(timeoutCallback,undefined)}
else{assert.match(status.textContent,/已复制/);assert.equal(timeoutDelay,2000);
const firstCallback=timeoutCallback;await handler();assert.equal(clearCount,1);assert.notEqual(timeoutCallback,firstCallback);
timeoutCallback();assert.equal(status.textContent,'')}
if(mode!=='modern'){assert.equal(helper.value,field.value);assert.equal(removed,true)}})().catch(e=>{console.error(e);process.exitCode=1});
'''
    options = dict(secure=secure, modern_ok=modern_ok, legacy_ok=legacy_ok, expected=expected)
    result = subprocess.run(["node", "-e", harness, json.dumps(options), DRAFT_SCRIPT], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('demo', [False, True])
def test_issue_title_is_single_and_endpoint_is_in_body(evidence, demo):
    result, bundle, case = evidence
    case['title'] = '【演示】查询返回了错误的资源归属' if demo else '查询返回了错误的资源归属'
    bundle['web'] = {'experience': demo}
    _, text = case_defect_draft(result, bundle, case)
    assert text.splitlines()[0] == '【标题】' + case['title']
    assert '接口：GET /items/7' in text
    assert '问题类型：接口断言未通过' in text


def test_sibling_failures_are_not_included_in_a_case_draft(evidence):
    result, bundle, case = evidence
    sibling = copy.deepcopy(case)
    sibling.update(id='OTHER', title='另一个独立缺陷')
    sibling['steps'][1]['response']['body'] = {'other': '另一个缺陷的响应'}
    result['cases'].append(sibling)
    _, text = case_defect_draft(result, bundle, case)
    assert '另一个独立缺陷' not in text
    assert '另一个缺陷的响应' not in text
    assert '错误名称' in text
