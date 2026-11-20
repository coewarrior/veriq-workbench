"""Readable, module-grouped UI case workbooks using literal OOXML cells."""
from collections import Counter
from io import BytesIO
import math
import re
import unicodedata
from xml.sax.saxutils import escape, quoteattr
from zipfile import ZipFile, ZIP_DEFLATED


NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
WIDTHS = {
    'case_id': 28, 'display_case_id': 28, 'scenario': 44, 'module': 20, 'priority': 12, 'executor': 16,
    'precondition': 42, 'test_data': 44, 'steps': 58, 'expected': 48, 'evidence': 58,
    'conclusion': 42, 'not_run_reason': 42, 'result': 18, 'ai_analysis': 44,
    'recommendation': 40, 'requirement_refs': 30, 'checkpoint_details': 62,
    'source_session': 30, 'scope_label': 26, 'source_url': 44,
}
STATUS_STYLES = {
    '通过': 3, 'passed': 3, '重试后通过': 3, 'retry_passed': 3,
    '不通过': 4, '失败': 4, 'failed': 4,
    '验证未完成': 5, '部分通过': 5, '部分验证': 5, 'partial': 5, '阻塞': 5, 'blocked': 5,
    '未执行': 6, 'not_run': 6, '跳过': 6, 'skipped': 6,
    '待用户确认': 7, 'pending_action': 7, '待确认规则': 7, 'pending_rule': 7,
}
PRIORITY_STYLES = {'P0': 4, 'P1': 5, 'P2': 3, 'P3': 6}
CELL_CHOICES = {
    'priority': ('P0', 'P1', 'P2', 'P3', '未设置'),
    'executor': ('AI', '人工', 'AI或人工'),
    'result': ('未执行', '通过', '不通过', '验证未完成', '阻塞', '待确认规则', '待用户确认', '跳过', '其他'),
}


def priority_label(value):
    text = str(value or '').strip()
    return text.upper() if text.upper() in PRIORITY_STYLES else text or '未设置'


def column_name(index):
    name = ''
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def cell_text(value):
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(value))


def row_height(row, widths):
    lines = 1
    for value, width in zip(row, widths):
        # Excel column widths approximate Latin glyphs; Chinese glyphs use two.
        wrapped = sum(max(1, math.ceil(sum(2 if unicodedata.east_asian_width(char) in 'WF' else 1
                                          for char in line.expandtabs(4)) / (width - 3)))
                      for line in cell_text(value).split('\n'))
        lines = max(lines, wrapped)
    # Excel's row-height limit affects display only; the full cell text remains.
    return min(409.5, max(36, lines * 16 + 12))


def styles_xml():
    colors = ['25364B', 'FFFFFF', '334E68', '166534', 'B91C1C', '92400E', '64748B', '6B21A8']
    fonts = ''.join('<font>' + ('<b/>' if index else '') +
                    f'<sz val="11"/><color rgb="FF{color}"/><name val="Microsoft YaHei"/><family val="2"/><charset val="134"/></font>'
                    for index, color in enumerate(colors))
    fills = '<fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
    fill_colors = ('203B54', 'F4F7FB', 'EAF7EE', 'FDECEC', 'FFF4DD', 'F1F5F9', 'F3E8FF')
    fills += ''.join(f'<fill><patternFill patternType="solid"><fgColor rgb="FF{color}"/><bgColor indexed="64"/></patternFill></fill>'
                     for color in fill_colors)
    formats = [(0, 0), (0, 3), (1, 2), (3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (2, 0), (2, 3)]
    xfs = ''.join(f'<xf numFmtId="0" fontId="{font}" fillId="{fill}" borderId="1" xfId="0" '
                  'applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
                  f'<alignment horizontal="{"center" if 3 <= index <= 7 else "left"}" '
                  f'vertical="{"center" if index == 2 else "top"}" wrapText="1" indent="{0 if 3 <= index <= 7 else 1}"/></xf>'
                  for index, (font, fill) in enumerate(formats))
    dxfs = ''.join(f'<dxf><font><b/><color rgb="FF{colors[font]}"/></font>'
                   f'<fill><patternFill patternType="solid"><fgColor rgb="FF{fill_colors[fill - 2]}"/>'
                   '<bgColor indexed="64"/></patternFill></fill></dxf>' for font, fill in formats[3:8])
    return (f'<styleSheet xmlns="{NS}"><fonts count="8">{fonts}</fonts><fills count="9">{fills}</fills>'
            '<borders count="2"><border/><border><left/><right/><top/><bottom style="thin"><color rgb="FFDCE4ED"/></bottom><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            f'<cellXfs count="10">{xfs}</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            f'<dxfs count="5">{dxfs}</dxfs></styleSheet>')


def _cell(ref, value, style):
    if isinstance(value, bool):
        body = f't="b"><v>{int(value)}</v>'
    elif isinstance(value, (int, float)) and (not isinstance(value, float) or math.isfinite(value)):
        body = f't="n"><v>{value}</v>'
    else:
        body = f't="inlineStr"><is><t xml:space="preserve">{escape(cell_text(value))}</t></is>'
    return f'<c r="{ref}" s="{style}" {body}</c>'


def _sheet_name(module, used):
    base = re.sub(r'[\[\]:*?/\\]', '_', cell_text(module)).strip().strip("'") or '未分类'
    name, number = base[:31].strip("'"), 1
    while name.casefold() in used:
        number += 1
        suffix = f' ({number})'
        name = base[:31 - len(suffix)].rstrip("'") + suffix
    used.add(name.casefold())
    return name


def _cell_options(fields, row_count):
    validations, conditional = [], []
    rule_priority = 0
    for index, (key, label) in enumerate(fields, 1):
        if key not in CELL_CHOICES:
            continue
        column = column_name(index)
        cell_range = f'{column}6:{column}{max(6, row_count + 5)}'
        options = escape('"' + ','.join(CELL_CHOICES[key]) + '"')
        # Excel/WPS hide the arrow when showDropDown is true. Keep free-text compatibility.
        validations.append(f'<dataValidation type="list" allowBlank="1" showDropDown="0" '
                           f'showErrorMessage="0" showInputMessage="1" promptTitle={quoteattr(label)} '
                           f'prompt="点击单元格右侧箭头选择，也可直接填写或清空。" sqref="{cell_range}">'
                           f'<formula1>{options}</formula1></dataValidation>')
        styles = PRIORITY_STYLES if key == 'priority' else STATUS_STYLES if key == 'result' else {}
        rules = []
        for value, style in styles.items():
            rule_priority += 1
            formula = escape('"' + value + '"')
            rules.append(f'<cfRule type="cellIs" dxfId="{style - 3}" priority="{rule_priority}" '
                         f'operator="equal"><formula>{formula}</formula></cfRule>')
        if rules:
            conditional.append(f'<conditionalFormatting sqref="{cell_range}">{"".join(rules)}</conditionalFormatting>')
    return ''.join(conditional) + (f'<dataValidations count="{len(validations)}">{"".join(validations)}</dataValidations>'
                                    if validations else '')


def _worksheet(fields, records, module):
    widths = [WIDTHS.get(key, 40) for key, _ in fields]
    priority_index = next((i for i, (key, _) in enumerate(fields) if key == 'priority'), None)
    counts = Counter(priority_label(row[priority_index]) for row in records) if priority_index is not None else Counter()
    summary = ['用例总数', len(records)]
    for priority in PRIORITY_STYLES:
        summary += [priority, counts[priority]]
    summary_cells = []
    for index, value in enumerate(summary, 1):
        ref = f'{column_name(index)}2'
        if priority_index is not None and index >= 4 and index % 2 == 0:
            column = column_name(priority_index + 1)
            formula = f'COUNTIFS({column}6:{column}{max(6, len(records) + 5)},"{summary[index - 2]}")'
            summary_cells.append(f'<c r="{ref}" t="n" s="0"><f>{escape(formula)}</f><v>{value}</v></c>')
        else:
            summary_cells.append(_cell(ref, value, 8 if index % 2 else 0))
    rows = [
        '<row r="1" ht="34" customHeight="1">' + _cell('A1', module + ' · 测试用例', 2) + '</row>',
        '<row r="2" ht="32" customHeight="1">' +
        ''.join(summary_cells) + '</row>',
        '<row r="3" ht="26" customHeight="1">' + _cell('A3', 'P0 核心关键 · P1 高 · P2 中 · P3 低；未设置及其他原值保留在明细。', 0) + '</row>',
        '<row r="4" ht="10" customHeight="1"/>',
    ]
    for ri, row in enumerate([[label for _, label in fields], *records], 5):
        cells = []
        for ci, ((key, _), value) in enumerate(zip(fields, row), 1):
            style = 2 if ri == 5 else ri % 2
            if ri > 5:
                if ci == 1:
                    style += 8
                elif key == 'result':
                    style = 6
                elif key == 'priority':
                    value = priority_label(value)
                    style = 6
            cells.append(_cell(f'{column_name(ci)}{ri}', value, style))
        height = 34 if ri == 5 else row_height(row, widths)
        rows.append(f'<row r="{ri}" ht="{height}" customHeight="1">' + ''.join(cells) + '</row>')
    end = f'{column_name(len(fields))}{len(records) + 5}'
    cols = ''.join(f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
                   for index, width in enumerate(widths, 1))
    sheet = (f'<worksheet xmlns="{NS}"><dimension ref="A1:{end}"/><sheetViews><sheetView workbookViewId="0" showGridLines="0" zoomScale="90">'
             '<pane xSplit="3" ySplit="5" topLeftCell="D6" activePane="bottomRight" state="frozen"/>'
             '<selection pane="bottomRight" activeCell="D6" sqref="D6"/></sheetView></sheetViews>'
             f'<sheetFormatPr defaultRowHeight="36"/><cols>{cols}</cols><sheetData>{"".join(rows)}</sheetData>'
             f'<autoFilter ref="A5:{end}"/><mergeCells count="2"><mergeCell ref="A1:J1"/><mergeCell ref="A3:J3"/></mergeCells>'
             + _cell_options(fields, len(records)) +
             '<printOptions horizontalCentered="0"/>'
             '<pageMargins left="0.35" right="0.35" top="0.45" bottom="0.45" header="0.2" footer="0.2"/>'
             '<pageSetup paperSize="8" orientation="landscape" scale="85" pageOrder="overThenDown"/>'
             '<headerFooter><oddFooter>&amp;L测试用例&amp;R第 &amp;P 页 / 共 &amp;N 页</oddFooter></headerFooter></worksheet>')
    return sheet


def workbook(fields, values):
    """Split by the original module, preserving row order and literal values."""
    module_index = next((i for i, (key, _) in enumerate(fields) if key == 'module'), None)
    groups = {}
    for row in values[1:]:
        module = str(row[module_index] or '').strip() if module_index is not None else ''
        groups.setdefault(module, []).append(row)
    if not groups:
        groups[''] = []
    used, sheets, definitions, relationships, overrides, contents = set(), [], [], [], [], []
    for index, (module, records) in enumerate(groups.items(), 1):
        label = module or '未分类'
        name = _sheet_name(label, used)
        sheets.append(f'<sheet name={quoteattr(name)} sheetId="{index}" r:id="rId{index}"/>')
        reference = escape("'" + name.replace("'", "''") + "'")
        area_end = '$' + column_name(len(fields)) + '$' + str(len(records) + 5)
        definitions.append(f'<definedName name="_xlnm.Print_Titles" localSheetId="{index - 1}">{reference}!$5:$5,{reference}!$A:$C</definedName>')
        definitions.append(f'<definedName name="_xlnm.Print_Area" localSheetId="{index - 1}">{reference}!$A$1:{area_end}</definedName>')
        relationships.append(f'<Relationship Id="rId{index}" Type="{REL}/worksheet" Target="worksheets/sheet{index}.xml"/>')
        overrides.append(f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
        contents.append(_worksheet(fields, records, label))
    definitions.append('<definedName name="_VERIQ_ModuleExport" hidden="1">1</definedName>')
    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' + ''.join(overrides) + '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>')
        archive.writestr('_rels/.rels', f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{REL}/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr('xl/workbook.xml', f'<workbook xmlns="{NS}" xmlns:r="{REL}"><sheets>{"".join(sheets)}</sheets><definedNames>{"".join(definitions)}</definedNames><calcPr calcId="0" calcMode="auto" fullCalcOnLoad="1"/></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{"".join(relationships)}<Relationship Id="rId{len(contents) + 1}" Type="{REL}/styles" Target="styles.xml"/></Relationships>')
        archive.writestr('xl/styles.xml', styles_xml())
        for index, content in enumerate(contents, 1):
            archive.writestr(f'xl/worksheets/sheet{index}.xml', content)
    return output.getvalue()
