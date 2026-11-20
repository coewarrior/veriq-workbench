"""Read completed UI test-case results from an XLSX workbook without macros."""
from __future__ import annotations

import posixpath
import re
import zipfile
from io import BytesIO
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET
from .defect_title import attributes, normalize_title


MAX_XLSX_BYTES = 10 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 40 * 1024 * 1024
MAX_ROWS = 10000
_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"

_ALIASES = {
    "ai_analysis": ("ai解读", "aianalysis"),
    "cause_analysis": ("原因分析", "causeanalysis"),
    "recommendation": ("建议优化", "优化建议", "recommendation"),
    "case_id": ("用例id", "用例编号", "用例序号", "序号", "编号", "caseid", "id"),
    "environment": ("环境", "测试环境", "部署环境", "environment", "env"),
    "test_environment": ("运行环境", "设备环境", "浏览器设备", "系统浏览器", "testenvironment"),
    "client": ("端", "测试端", "客户端", "终端", "端类型", "client"),
    "module": ("模块", "功能模块", "功能", "功能/模块", "功能/模块名称"),
    "priority": ("优先级", "priority"),
    "executor": ("执行方式", "执行人", "执行主体", "executor"),
    "not_run_reason": ("本轮未执行原因", "未执行原因", "跳过原因", "notrunreason"),
    "category": ("类别", "类型", "用例类型"),
    "layer": ("层级", "测试层级"),
    "scenario": ("场景", "测试场景", "用例名称", "用例标题", "标题"),
    "precondition": ("前置条件", "前提条件"),
    "test_data": ("测试数据", "用例数据", "输入数据", "数据准备", "完整测试输入", "测试输入", "完整输入"),
    "steps": ("步骤", "测试步骤", "操作步骤", "逐步操作", "执行步骤"),
    "expected": ("预期结果关键断言", "预期结果/关键断言", "预期结果", "关键断言"),
    "code_basis": ("代码依据", "依据"),
    "criterion": ("判定口径", "验收口径"),
    "result": ("执行结果", "测试结果", "结果", "状态"),
    "conclusion": ("测试结论", "结论", "conclusion"),
    "evidence": ("实际证据", "实际结果", "执行证据", "证据", "实际结果与缺陷", "实际结果及缺陷",
                 "实际结果和缺陷", "问题描述", "缺陷描述"),
    "defect_id": ("缺陷编号", "缺陷id", "bug编号", "bugid"),
}


def _normalized(value: str) -> str:
    return re.sub(r"[\s_\-—:：/\\（）()【】\[\]]+", "", str(value or "")).lower()


def _column_index(reference: str) -> int:
    letters = re.match(r"[A-Za-z]+", reference or "")
    if not letters:
        return 0
    value = 0
    for char in letters.group().upper():
        value = value * 26 + ord(char) - 64
    return value - 1


def _strings(root: ET.Element) -> list[str]:
    return ["".join(node.text or "" for node in item.iter(_NS + "t"))
            for item in root.findall(_NS + "si")]


def _cell_value(cell: ET.Element, shared: list[str]) -> str:
    kind = cell.get("t", "")
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(_NS + "t")).strip()
    value = cell.findtext(_NS + "v", default="")
    if kind == "s" and value.isdigit():
        index = int(value)
        return shared[index].strip() if index < len(shared) else ""
    if kind == "b":
        return "是" if value == "1" else "否"
    return str(value).strip()


def _worksheet_rows(root: ET.Element, shared: list[str]) -> list[list[str]]:
    result = []
    for row in root.findall(".//" + _NS + "sheetData/" + _NS + "row"):
        values: list[str] = []
        for cell in row.findall(_NS + "c"):
            index = _column_index(cell.get("r", ""))
            if index >= 200:
                continue
            if len(values) <= index:
                values.extend([""] * (index + 1 - len(values)))
            values[index] = _cell_value(cell, shared)
        result.append(values)
        if len(result) > MAX_ROWS + 50:
            raise ValueError(f"工作表行数过多，最多支持 {MAX_ROWS} 条测试用例")
    return result


def _sheet_paths(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {item.get("Id"): item.get("Target", "") for item in rels.findall(_PKG_REL_NS + "Relationship")}
    sheets = []
    for item in workbook.findall(".//" + _NS + "sheet"):
        target = targets.get(item.get(_REL_NS + "id"), "")
        if not target:
            continue
        path = posixpath.normpath(target.lstrip("/") if target.startswith("/") else posixpath.join("xl", target))
        if not path.startswith("xl/") or ".." in PurePosixPath(path).parts:
            raise ValueError("XLSX 工作表路径无效")
        sheets.append((item.get("name", "未命名工作表"), path))
    return sheets


def _header_map(rows: list[list[str]]) -> tuple[int, dict[str, int]] | None:
    aliases = {alias: field for field, values in _ALIASES.items() for alias in values}
    for row_index, row in enumerate(rows[:40]):
        mapped = {}
        for index, value in enumerate(row):
            field = aliases.get(_normalized(value))
            if field and field not in mapped:
                mapped[field] = index
        if "result" in mapped and ("case_id" in mapped or "scenario" in mapped):
            return row_index, mapped
    return None


def _status(value: str) -> str:
    normalized = _normalized(value)
    if normalized in {"通过", "pass", "passed", "成功", "ok"}:
        return "passed"
    if normalized in {"失败", "fail", "failed", "不通过", "ng"}:
        return "failed"
    if normalized in {"验证未完成", "部分通过", "partial"}:
        return "partial"
    if normalized in {"待确认规则", "pendingrule"}:
        return "pending_rule"
    if normalized in {"待用户确认", "pendingaction"}:
        return "pending_action"
    if normalized in {"阻塞", "blocked", "block"}:
        return "blocked"
    if normalized in {"跳过", "skipped", "skip"}:
        return "skipped"
    if normalized in {"未执行", "待执行", "notrun", "pending", "todo", ""}:
        return "not_run"
    return "other"


def _needs_detail(value: str, *, minimum: int, generic: set[str]) -> bool:
    normalized = _normalized(value)
    return bool(normalized) and (len(normalized) < minimum or normalized in generic)


def parse_xlsx_results(content: bytes, *, environment: str = "", client: str = "") -> dict:
    if not isinstance(content, bytes) or not content:
        raise ValueError("请选择非空的 XLSX 文件")
    if len(content) > MAX_XLSX_BYTES:
        raise ValueError("XLSX 文件不能超过 10 MB")
    try:
        archive = zipfile.ZipFile(BytesIO(content))
    except zipfile.BadZipFile as error:
        raise ValueError("文件不是有效的 XLSX 工作簿") from error
    with archive:
        names = set(archive.namelist())
        if "xl/workbook.xml" not in names or "xl/_rels/workbook.xml.rels" not in names:
            raise ValueError("文件不是有效的 XLSX 工作簿")
        if len(names) > 500 or sum(item.file_size for item in archive.infolist()) > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("XLSX 解压后的内容过大")
        shared = _strings(ET.fromstring(archive.read("xl/sharedStrings.xml"))) if "xl/sharedStrings.xml" in names else []
        candidates = []
        for sheet_name, path in _sheet_paths(archive):
            if path not in names:
                continue
            try:
                rows = _worksheet_rows(ET.fromstring(archive.read(path)), shared)
            except ET.ParseError as error:
                raise ValueError(f"工作表“{sheet_name}”内容损坏") from error
            header = _header_map(rows)
            if header:
                candidates.append((sheet_name, rows, header))
        if not candidates:
            raise ValueError("没有找到包含“执行结果”及“用例ID/场景”列的工作表")
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        module_export = any(item.get("name") == "_VERIQ_ModuleExport" and item.text == "1"
                            for item in workbook.findall(_NS + "definedNames/" + _NS + "definedName"))
        selected = candidates if module_export else [next(
            (item for item in candidates if _normalized(item[0]) in {"测试用例", "用例", "测试结果"}), candidates[0])]
        sheet_name = f"测试用例（{len(selected)} 个模块）" if module_export else selected[0][0]
        header_index = selected[0][2][0]
        cases = []
        for source_sheet, rows, (sheet_header, columns) in selected:
            for source_row, values in enumerate(rows[sheet_header + 1:], sheet_header + 2):
                case = {field: (values[index].strip() if index < len(values) else "") for field, index in columns.items()}
                case["environment"], case["client"], case["module"] = attributes(
                    environment or case.get("environment", ""), client or case.get("client", ""), case.get("module", ""))
                if not any(case.get(key) for key in ("case_id", "scenario", "result")):
                    continue
                case["source_row"] = source_row
                if module_export:
                    case["source_sheet"] = source_sheet
                if module_export and case.get("priority") == "未设置":
                    case["priority"] = ""
                case["status"] = _status(case.get("result", ""))
                case["test_data_issue"] = ("missing" if not case.get("test_data", "").strip() else
                                           "brief" if _needs_detail(case.get("test_data", ""), minimum=6,
                                                                    generic={"无", "同上", "正常数据", "有效数据", "测试数据"}) else "")
                case["steps_issue"] = ("missing" if not case.get("steps", "").strip() else
                                       "brief" if _needs_detail(case.get("steps", ""), minimum=12,
                                                                generic={"执行测试", "检查结果", "触发同步", "同步", "操作"}) else "")
                cases.append(case)
                if len(cases) > MAX_ROWS:
                    raise ValueError(f"测试用例过多，最多支持 {MAX_ROWS} 条")
        if not cases:
            raise ValueError("工作表中没有可导入的测试用例")
    counts = dict.fromkeys(("passed", "failed", "blocked", "not_run", "skipped", "other"), 0)
    for case in cases:
        counts[case["status"]] = counts.get(case["status"], 0) + 1
    quality = {
        "missing_test_data": sum(case["test_data_issue"] == "missing" for case in cases),
        "brief_test_data": sum(case["test_data_issue"] == "brief" for case in cases),
        "missing_steps": sum(case["steps_issue"] == "missing" for case in cases),
        "brief_steps": sum(case["steps_issue"] == "brief" for case in cases),
    }
    return {"sheet_name": sheet_name, "header_row": header_index + 1, "cases": cases,
            "counts": {"total": len(cases), **counts}, "quality": quality}


def result_findings(parsed: dict, maximum: int = 200) -> list[dict]:
    findings = []
    for case in parsed["cases"]:
        if case["status"] != "failed":
            continue
        case_id = case.get("case_id") or f'第 {case["source_row"]} 行'
        scenario = case.get("scenario") or "未命名测试场景"
        precondition = case.get("precondition") or "无"
        test_data = case.get("test_data") or "未填写"
        steps = case.get("steps") or "未填写"
        expected = case.get("expected") or "未填写"
        source = f'XLSX 工作表“{case["source_sheet"]}”' if case.get("source_sheet") else 'XLSX'
        actual = case.get("evidence") or f'{source} 第 {case["source_row"]} 行记录执行结果为“{case.get("result") or "未填写"}”。'
        environment = case.get("environment") or "未标注环境"
        client = case.get("client") or "未标注端"
        module = case.get("module") or "未标注模块"
        findings.append({
            "title": normalize_title(scenario, environment, client, module),
            "case_id": case_id,
            "test_environment": case.get("test_environment", ""),
            "environment": environment,
            "client": client,
            "module": module,
            "detail": f"前置条件：{precondition}\n测试数据：{test_data}\n测试步骤：{steps}\n预期结果：{expected}",
            "evidence": actual,
            **{key: case.get(key, "") for key in ("ai_analysis", "cause_analysis", "recommendation")},
            "severity": "严重" if _normalized(case.get("priority")) in {"p0", "最高", "紧急"} else "一般",
            "priority": case.get("priority") or "普通",
            "precondition": precondition,
            "test_data": test_data,
            "steps": steps,
            "expected": expected,
            "rule_basis": case.get("rule_basis") or case.get("code_basis", ""),
            "actual": actual,
        })
        if len(findings) >= maximum:
            break
    return findings
