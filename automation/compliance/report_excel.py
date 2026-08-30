#!/usr/bin/env python3
"""生成 Excel 审计报告（openpyxl，三 Sheet：汇总 / 设备明细 / 不合规清单）。"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

try:  # 作为包导入
    from .auditor import AuditReport
except ImportError:  # 直接以脚本方式运行
    from auditor import AuditReport

SEVERITY_LABEL = {"high": "高危", "medium": "中危", "low": "低危"}

HEADER_FILL = PatternFill("solid", fgColor="1a73e8")
HEADER_FONT = Font(color="FFFFFF", bold=True)
PASS_FILL = PatternFill("solid", fgColor="e6f4ea")
FAIL_FILL = PatternFill("solid", fgColor="fce8e6")


def _write_header(ws, headers: list[str]) -> None:
    for col, title in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=title)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.freeze_panes = "A2"


def _autosize(ws) -> None:
    for col in ws.columns:
        width = max((len(str(c.value)) if c.value else 0) for c in col) + 2
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(width, 60)


def _sheet_summary(wb: Workbook, report: AuditReport) -> None:
    ws = wb.active
    ws.title = "汇总"
    _write_header(ws, ["设备", "角色", "管理IP", "通过数", "失败数", "合规率(%)", "状态", "违规规则"])
    for i, dev in enumerate(report.devices, start=2):
        ws.cell(i, 1, dev.name)
        ws.cell(i, 2, dev.role)
        ws.cell(i, 3, dev.mgmt_ip)
        ws.cell(i, 4, dev.pass_count)
        ws.cell(i, 5, dev.fail_count)
        ws.cell(i, 6, dev.rate)
        ws.cell(i, 7, "合规" if dev.is_compliant else "不合规")
        ws.cell(i, 8, ", ".join(r.rule.id for r in dev.failures))
        # 状态着色
        status_cell = ws.cell(i, 7)
        status_cell.fill = PASS_FILL if dev.is_compliant else FAIL_FILL
    # 总体行
    total_row = len(report.devices) + 2
    ws.cell(total_row, 1, "总体").font = Font(bold=True)
    ws.cell(total_row, 6, report.overall_rate).font = Font(bold=True)
    ws.cell(total_row, 7, f"阈值 {report.threshold}%，" + ("已触发告警" if report.alert_triggered else "未触发告警"))
    _autosize(ws)


def _sheet_detail(wb: Workbook, report: AuditReport) -> None:
    ws = wb.create_sheet("设备明细")
    _write_header(ws, ["设备", "规则ID", "规则名称", "类别", "严重性", "结果", "证据/说明", "修复建议"])
    row = 2
    for dev in report.devices:
        for res in dev.results:
            ws.cell(row, 1, dev.name)
            ws.cell(row, 2, res.rule.id)
            ws.cell(row, 3, res.rule.name)
            ws.cell(row, 4, res.rule.category)
            ws.cell(row, 5, SEVERITY_LABEL.get(res.rule.severity, res.rule.severity))
            ws.cell(row, 6, "合规" if res.passed else "不合规")
            ws.cell(row, 7, "\n".join(res.evidence) if res.evidence else "（未命中合规项）")
            ws.cell(row, 8, res.rule.remediation)
            result_cell = ws.cell(row, 6)
            result_cell.fill = PASS_FILL if res.passed else FAIL_FILL
            row += 1
    _autosize(ws)


def _sheet_noncompliant(wb: Workbook, report: AuditReport) -> None:
    ws = wb.create_sheet("不合规清单")
    _write_header(ws, ["设备", "规则ID", "规则名称", "严重性", "违规证据", "修复建议"])
    row = 2
    for dev in report.noncompliant_devices:
        for res in dev.failures:
            ws.cell(row, 1, dev.name)
            ws.cell(row, 2, res.rule.id)
            ws.cell(row, 3, res.rule.name)
            ws.cell(row, 4, SEVERITY_LABEL.get(res.rule.severity, res.rule.severity))
            ws.cell(row, 5, "\n".join(res.evidence) if res.evidence else "（未命中合规项）")
            ws.cell(row, 6, res.rule.remediation)
            row += 1
    _autosize(ws)


def render(report: AuditReport, path: Path) -> None:
    """渲染并保存 Excel 报告。"""
    wb = Workbook()
    _sheet_summary(wb, report)
    _sheet_detail(wb, report)
    _sheet_noncompliant(wb, report)
    wb.save(path)
