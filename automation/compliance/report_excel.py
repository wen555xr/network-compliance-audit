#!/usr/bin/env python3
# Excel 报告生成器：用 openpyxl 库把审计结果写进 Excel，生成三个 Sheet（汇总 / 设备明细 / 不合规清单），
# 并做了样式美化（表头蓝底白字、合规绿、违规红、列宽自适应、冻结首行）。

"""生成 Excel 审计报告（openpyxl，三 Sheet：汇总 / 设备明细 / 不合规清单）。"""
from __future__ import annotations  # 兼容新旧 Python 版本的类型注解语法

from pathlib import Path            # 路径库（类型注解用）

from openpyxl import Workbook                        # 创建 Excel 工作簿（.xlsx 文件）
from openpyxl.styles import Alignment, Font, PatternFill  # 单元格样式：对齐 / 字体 / 背景填充
from openpyxl.utils import get_column_letter         # 把列号转字母（1->A, 2->B）

try:                                # 先尝试「作为包」导入
    from .auditor import AuditReport
except ImportError:                 # 直接运行脚本时退回普通导入
    from auditor import AuditReport

SEVERITY_LABEL = {"high": "高危", "medium": "中危", "low": "低危"}  # 严重性英文 -> 中文标签

HEADER_FILL = PatternFill("solid", fgColor="1a73e8")   # 表头背景：纯蓝色
HEADER_FONT = Font(color="FFFFFF", bold=True)          # 表头字体：白色、加粗
PASS_FILL = PatternFill("solid", fgColor="e6f4ea")     # 合规背景：浅绿
FAIL_FILL = PatternFill("solid", fgColor="fce8e6")     # 违规背景：浅红


def _write_header(ws, headers: list[str]) -> None:
    for col, title in enumerate(headers, start=1):  # 遍历表头，enumerate(start=1) 让列号从 1 开始（对应 Excel 第1列）
        cell = ws.cell(row=1, column=col, value=title)  # 在第 1 行、第 col 列写入标题
        cell.fill = HEADER_FILL                        # 上背景色
        cell.font = HEADER_FONT                        # 上字体
        cell.alignment = Alignment(horizontal="center", vertical="center")  # 文字水平垂直居中
    ws.freeze_panes = "A2"                             # 冻结首行：滚动时表头始终可见


def _autosize(ws) -> None:
    for col in ws.columns:                             # 遍历每一列（col 是一列的所有单元格）
        width = max((len(str(c.value)) if c.value else 0) for c in col) + 2  # 算这一列最长内容的长度，+2 留余量
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(width, 60)  # 设置列宽（上限 60）


def _sheet_summary(wb: Workbook, report: AuditReport) -> None:
    ws = wb.active                       # 取工作簿默认第一个工作表
    ws.title = "汇总"                    # 改表名为「汇总」
    _write_header(ws, ["设备", "角色", "管理IP", "通过数", "失败数", "合规率(%)", "状态", "违规规则"])  # 写表头
    for i, dev in enumerate(report.devices, start=2):  # 遍历设备，从第 2 行开始（第 1 行是表头）
        ws.cell(i, 1, dev.name)                                  # 列1：设备名
        ws.cell(i, 2, dev.role)                                  # 列2：角色
        ws.cell(i, 3, dev.mgmt_ip)                               # 列3：管理IP
        ws.cell(i, 4, dev.pass_count)                            # 列4：通过数
        ws.cell(i, 5, dev.fail_count)                            # 列5：失败数
        ws.cell(i, 6, dev.rate)                                  # 列6：合规率
        ws.cell(i, 7, "合规" if dev.is_compliant else "不合规")   # 列7：状态文字
        ws.cell(i, 8, ", ".join(r.rule.id for r in dev.failures))  # 列8：失败规则ID用逗号拼接
        status_cell = ws.cell(i, 7)                              # 拿到状态单元格
        status_cell.fill = PASS_FILL if dev.is_compliant else FAIL_FILL  # 合规绿、违规红
    total_row = len(report.devices) + 2    # 数据行下面空一行，算「总体」行行号
    ws.cell(total_row, 1, "总体").font = Font(bold=True)          # 第1列写「总体」并加粗
    ws.cell(total_row, 6, report.overall_rate).font = Font(bold=True)  # 第6列写总体合规率并加粗
    ws.cell(total_row, 7, f"阈值 {report.threshold}%，" + ("已触发告警" if report.alert_triggered else "未触发告警"))  # 第7列写阈值与告警状态
    _autosize(ws)                            # 自动调列宽


def _sheet_detail(wb: Workbook, report: AuditReport) -> None:
    ws = wb.create_sheet("设备明细")          # 新建工作表，命名「设备明细」
    _write_header(ws, ["设备", "规则ID", "规则名称", "类别", "严重性", "结果", "证据/说明", "修复建议"])  # 写表头
    row = 2                                   # 从第 2 行开始写数据
    for dev in report.devices:                # 遍历每台设备
        for res in dev.results:               # 遍历该设备的每条规则结果
            ws.cell(row, 1, dev.name)                                   # 设备名
            ws.cell(row, 2, res.rule.id)                                # 规则ID
            ws.cell(row, 3, res.rule.name)                              # 规则名
            ws.cell(row, 4, res.rule.category)                          # 类别
            ws.cell(row, 5, SEVERITY_LABEL.get(res.rule.severity, res.rule.severity))  # 严重性（转中文）
            ws.cell(row, 6, "合规" if res.passed else "不合规")          # 结果
            ws.cell(row, 7, "\n".join(res.evidence) if res.evidence else "（未命中合规项）")  # 证据行（多行用换行）
            ws.cell(row, 8, res.rule.remediation)                       # 修复建议
            result_cell = ws.cell(row, 6)                               # 结果单元格
            result_cell.fill = PASS_FILL if res.passed else FAIL_FILL   # 合规绿、违规红
            row += 1                           # 行号 +1，写下一行
    _autosize(ws)                              # 自动调列宽


def _sheet_noncompliant(wb: Workbook, report: AuditReport) -> None:
    ws = wb.create_sheet("不合规清单")         # 新建工作表，命名「不合规清单」
    _write_header(ws, ["设备", "规则ID", "规则名称", "严重性", "违规证据", "修复建议"])  # 写表头
    row = 2                                   # 从第 2 行开始
    for dev in report.noncompliant_devices:   # 只遍历不合规设备
        for res in dev.failures:              # 只遍历失败规则
            ws.cell(row, 1, dev.name)                                   # 设备名
            ws.cell(row, 2, res.rule.id)                                # 规则ID
            ws.cell(row, 3, res.rule.name)                              # 规则名
            ws.cell(row, 4, SEVERITY_LABEL.get(res.rule.severity, res.rule.severity))  # 严重性
            ws.cell(row, 5, "\n".join(res.evidence) if res.evidence else "（未命中合规项）")  # 违规证据
            ws.cell(row, 6, res.rule.remediation)                       # 修复建议
            row += 1                           # 行号 +1
    _autosize(ws)                              # 自动调列宽


def render(report: AuditReport, path: Path) -> None:
    """渲染并保存 Excel 报告。"""
    wb = Workbook()                            # 创建空工作簿
    _sheet_summary(wb, report)                 # 生成「汇总」Sheet
    _sheet_detail(wb, report)                  # 生成「设备明细」Sheet
    _sheet_noncompliant(wb, report)            # 生成「不合规清单」Sheet
    wb.save(path)                              # 保存到文件（main.py 传入的 xlsx 路径）
