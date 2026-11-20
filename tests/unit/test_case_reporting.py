from api_test_tool.case_reporting import render_case_report


def _bundle():
    return {
        "title": "用户接口",
        "contract": {
            "operations": {"register": {"method": "post", "path": "/reg"}},
            "sources": {"S-1": {"path": "接口文档.md", "location": "注册", "excerpt": "注册成功返回 201"}},
        },
        "rules": [{"id": "R-1", "state": "documented", "source_ids": ["S-1"], "description": "合法用户注册成功"}],
        "cases": [{
            "id": "REG-001",
            "title": "<script>alert('x')</script>新用户注册",
            "operation_id": "register",
            "scenario": "normal",
            "state": "READY",
            "reason": "",
            "variables": {"username": {"kind": "unique", "prefix": "report_"}},
            "rule_ids": ["R-1"],
            "steps": [{
                "id": "register", "title": "提交注册请求", "operation_id": "register",
                "request": {"method": "POST", "path": "/reg", "json": {"username": "${username}"}},
                "assertions": [{"kind": "status", "expected": 201, "rule_id": "R-1"}],
                "extract": [],
            }],
            "cleanup_steps": [],
            "cleanup_policy": {"strategy": "none", "reason": "测试服务按会话自动回滚"},
        }],
    }


def test_case_report_matches_readable_design_report_structure_and_escapes_content():
    page = render_case_report({"id": "11111111-1111-4111-8111-111111111111", "title": "五子棋接口"}, _bundle())

    assert "1 条设计用例 · 1 个接口及关联链路 · 全部未执行" in page
    assert all(label in page for label in ("前置条件", "输入与请求步骤", "关键断言", "文档中的相关说明", "后置验证与清理", "执行状态"))
    assert all(control in page for control in ('id="search"', 'id="api-filter"', 'id="scenario-filter"', 'id="state-filter"'))
    assert "REG-001" in page and "POST /reg" in page
    assert "HTTP 状态码（期望=201）" in page
    assert "接口文档.md · 注册" in page
    assert "未执行 · 设计状态：可执行" in page
    assert "&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;" in page
    assert "<script>alert('x')</script>" not in page
    assert 'target="_blank"' not in page


def test_case_report_keeps_unavailable_reason_and_empty_steps_visible():
    bundle = _bundle()
    bundle["cases"][0].update(
        state="NEEDS_RULE", reason="文档未说明重复用户名响应", steps=[], cleanup_policy={"strategy": "none", "reason": "没有写操作"}
    )
    page = render_case_report({"id": "11111111-1111-4111-8111-111111111111", "title": "五子棋接口"}, bundle)

    assert "执行条件待完善或核对 1 条" in page
    assert "尚未配置请求步骤" in page
    assert "尚未配置断言" in page
    assert "文档未说明重复用户名响应" in page


def test_adjacent_and_overlapping_sources_display_once_with_one_source_toggle():
    bundle = _bundle()
    sources = bundle["contract"]["sources"]
    sources.clear()
    sources.update({
        "S-1": {"path": "inputs/document.md", "sha256": "abc", "location": "lines 16-17", "excerpt": "| 结果 | 注册成功 |\n| result | true |"},
        "S-2": {"path": "inputs/document.md", "sha256": "abc", "location": "lines 17-18", "excerpt": "| result | true |\n| 提示 | <script>用户注册成功</script> |"},
        "S-3": {"path": "inputs/document.md", "sha256": "abc", "location": "lines 21-21", "excerpt": "重复注册返回失败"},
    })
    bundle["rules"][0].update(description="OpenAPI 显式成功响应与 JSON Schema", source_ids=["S-2", "S-1", "S-3", "S-1"])
    page = render_case_report({"id": "p"}, bundle)
    assert page.count("result：true") == 1
    assert page.count("查看来源") == 1
    assert "第 16–18 行；第 21 行" in page
    assert "OpenAPI 显式成功响应与 JSON Schema" not in page
    assert "inputs/document.md" not in page
    assert "&lt;script&gt;用户注册成功&lt;/script&gt;" in page
    assert "重复注册返回失败" in page


def test_reasons_deduplicate_summary_details_and_equivalent_engine_message():
    bundle = _bundle()
    case = bundle["cases"][0]
    reasons = ["文档未明确本场景的成功 HTTP 状态码；不能猜测预期", "步骤 request 缺少有依据的预期；可验证业务字段、响应结构或 HTTP 状态", "Step request: business requests require assertions", "包含写操作，但尚未配置可验证的数据清理步骤", "参数 SSID 缺少登录信息"]
    case.update(state="NEEDS_RULE", reason="；".join(reasons), web={"blockers": reasons})
    page = render_case_report({"id": "p"}, bundle)
    assert page.count("步骤 request 尚未设置预期结果") == 1
    assert page.count("文档未说明成功时的 HTTP 状态码") == 1
    assert page.count("尚未设置写入数据后的清理和验证步骤") == 1
    assert page.count("参数 SSID 缺少登录信息") == 1
    assert "business requests require assertions" not in page


def test_complete_design_keeps_compiled_steps_in_closed_details():
    bundle = _bundle()
    bundle["cases"][0]["design"] = {"preconditions": "新用户名尚未注册", "expected": "注册成功", "basis": "注册接口成功响应说明"}
    page = render_case_report({"id": "p"}, bundle)
    assert "新用户名尚未注册" in page
    assert '<details class=source><summary>查看实际请求和检查项</summary>' in page
    assert "完整测试设计" in page


def test_document_markdown_is_readable_inside_closed_source_details():
    bundle = _bundle()
    bundle["rules"][0]["description"] = "OpenAPI 显式成功响应与 JSON Schema"
    bundle["contract"]["sources"]["S-1"]["excerpt"] = "| 正确响应 | **字段说明：**<br>成功时 `result=true` |"
    page = render_case_report({"id": "p"}, bundle)
    assert "参考接口文档中的请求与响应说明。" in page
    assert '正确响应：字段说明：\n成功时 result=true' in page
    assert '&lt;br&gt;' not in page
    assert '<details class="source"><summary>查看来源</summary>' in page
