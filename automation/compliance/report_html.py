#!/usr/bin/env python3
# HTML 报告渲染器：把 AuditReport 渲染成一份「自包含」的 HTML 报告（样式全部内嵌，单文件即可查看）。
# 全部用 Python 字符串拼接动态生成 HTML，不依赖任何前端框架。

"""生成自包含 HTML 审计报告（内联 CSS，无外部依赖）。"""
from __future__ import annotations  # 兼容新旧 Python 版本的类型注解语法

import html                          # HTML 转义模块：把特殊字符（< > &）转成安全形式，防止破坏页面/注入

try:                                # 先尝试「作为包」导入
    from .auditor import AuditReport
except ImportError:                 # 直接运行脚本时退回普通导入
    from auditor import AuditReport

SEVERITY_LABEL = {"high": "高危", "medium": "中危", "low": "低危"}  # 严重性 -> 中文
SEVERITY_COLOR = {"high": "#d93025", "medium": "#e37400", "low": "#5f6368"}  # 严重性 -> 颜色（红/橙/灰）


def _esc(value: object) -> str:
    return html.escape(str(value))   # 安全转义辅助函数：任意值转字符串并转义，拼接用户数据前都过一遍


def _status_badge(rate: float) -> str:
    if rate >= 100:                  # 100%：合规
        return '<span style="background:#e6f4ea;color:#137333;padding:2px 10px;border-radius:12px;font-weight:600">合规</span>'  # 返回绿色「合规」徽章 HTML
    if rate >= 80:                   # 80%~99%：基本合规
        return '<span style="background:#fef7e0;color:#b06000;padding:2px 10px;border-radius:12px;font-weight:600">基本合规</span>'  # 返回橙色「基本合规」徽章
    return '<span style="background:#fce8e6;color:#c5221f;padding:2px 10px;border-radius:12px;font-weight:600">不合规</span>'  # 否则返回红色「不合规」徽章


def _rate_color(rate: float) -> str:
    if rate >= 90:                   # 合规率 ≥90：绿色
        return "#137333"
    if rate >= 70:                   # ≥70：橙色
        return "#b06000"
    return "#c5221f"                 # 其他：红色


def render(report: AuditReport) -> str:
    """渲染完整 HTML 报告字符串。"""
    # KPI 卡片
    kpi_cards = "".join(             # 用 join 把 6 张 KPI 卡片无缝拼成一个长字符串
        [
            _kpi("审计设备数", len(report.devices)),             # 卡片1：审计设备数
            _kpi("合规设备", len(report.compliant_devices), "#137333"),  # 卡片2：合规设备（绿色）
            _kpi("不合规设备", len(report.noncompliant_devices), "#c5221f"),  # 卡片3：不合规设备（红色）
            _kpi("总体合规率", f"{report.overall_rate}%", _rate_color(report.overall_rate)),  # 卡片4：总体合规率（按值着色）
            _kpi("告警阈值", f"{report.threshold}%"),            # 卡片5：告警阈值
            _kpi(                                               # 卡片6：告警状态
                "告警状态",
                "已触发" if report.alert_triggered else "未触发",  # 三目运算符决定显示文字
                "#c5221f" if report.alert_triggered else "#137333",  # 触发红色、未触发绿色
            ),
        ]
    )

    matrix = _compliance_matrix(report)   # 生成「设备×规则」合规矩阵表 HTML
    details = _violation_details(report)  # 生成「不合规设备清单与改进建议」HTML
    top = _top_violations(report)         # 生成「Top 违规规则」表 HTML

    # 以下 return 的是一个 f-string 巨型 HTML 模板。
    # 注意：这是字符串字面量，里面不能写 # 注释；{matrix} 等花括号处会被替换成上面拼好的内容。
    # 模板里的 {{ }} 双花括号是转义写法，f-string 遇到它们会输出单个 { 字符（即真正的 CSS 花括号）。
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>网络设备配置合规审计报告</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: "Segoe UI", "Microsoft YaHei", system-ui, sans-serif; background: #f5f6f8; color: #202124; padding: 24px; }}
  .container {{ max-width: 1080px; margin: 0 auto; }}
  header {{ background: linear-gradient(135deg, #1a73e8, #0d47a1); color: #fff; padding: 28px 32px; border-radius: 12px; margin-bottom: 20px; }}
  header h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 6px; }}
  header .sub {{ font-size: 13px; opacity: .85; }}
  header .overall {{ font-size: 40px; font-weight: 800; margin-top: 12px; }}
  .kpi-row {{ display: flex; flex-wrap: wrap; gap: 14px; margin-bottom: 20px; }}
  .kpi {{ flex: 1 1 150px; background: #fff; border-radius: 10px; padding: 16px 18px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
  .kpi .label {{ font-size: 12px; color: #5f6368; }}
  .kpi .value {{ font-size: 26px; font-weight: 700; margin-top: 4px; }}
  .card {{ background: #fff; border-radius: 10px; padding: 22px 24px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
  .card h2 {{ font-size: 16px; font-weight: 700; margin-bottom: 14px; border-left: 4px solid #1a73e8; padding-left: 10px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ padding: 9px 10px; text-align: left; border-bottom: 1px solid #eef0f3; }}
  th {{ background: #fafbfc; color: #5f6368; font-weight: 600; }}
  .pass {{ color: #137333; font-weight: 700; }}
  .fail {{ color: #c5221f; font-weight: 700; }}
  .cell-p {{ color: #137333; font-weight: 700; }}
  .cell-f {{ color: #c5221f; font-weight: 700; }}
  .violation {{ border-left: 4px solid #e0e0e0; padding: 12px 14px; margin-bottom: 12px; background: #fafbfc; border-radius: 6px; }}
  .violation.high {{ border-left-color: #d93025; }}
  .violation.medium {{ border-left-color: #e37400; }}
  .violation .sev {{ font-size: 11px; color: #fff; padding: 1px 8px; border-radius: 10px; margin-left: 8px; }}
  .evidence {{ font-family: Consolas, monospace; font-size: 12px; background: #f1f3f4; padding: 6px 10px; border-radius: 4px; margin-top: 6px; color: #3c4043; white-space: pre-wrap; }}
  .remediation {{ color: #137333; font-size: 13px; margin-top: 6px; }}
  .muted {{ color: #5f6368; }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>网络设备配置合规性自动审计报告</h1>
    <div class="sub">生成时间：{_esc(report.generated_at)}　·　审计规则：{len(report.rules)} 项　·　审计对象：华为 S5700 园区网络（eNSP）</div>
    <div class="overall" style="color:{_rate_color(report.overall_rate)}">{report.overall_rate}%</div>
    <div class="sub">总体合规率（阈值 {report.threshold}%）</div>
  </header>

  <div class="kpi-row">{kpi_cards}</div>

  <div class="card">
    <h2>设备合规率总览</h2>
    {matrix}
  </div>

  <div class="card">
    <h2>不合规设备清单与改进建议</h2>
    {details}
  </div>

  <div class="card">
    <h2>Top 违规规则</h2>
    {top}
  </div>

  <p class="muted" style="text-align:center;font-size:12px;margin-top:8px">本报告由「网络设备配置合规性自动审计系统」自动生成（Python + Netmiko + 正则解析引擎）</p>
</div>
</body>
</html>"""


def _kpi(label: str, value: object, color: str = "#202124") -> str:
    return (                          # 返回一张 KPI 卡片的 HTML；相邻两个字符串自动拼接（Python 特性）
        f'<div class="kpi"><div class="label">{_esc(label)}</div>'       # 上半部分：标签
        f'<div class="value" style="color:{color}">{_esc(value)}</div></div>'  # 下半部分：数值（带颜色），数值也过转义
    )


def _compliance_matrix(report: AuditReport) -> str:
    """设备 × 规则 合规矩阵表。"""
    header = "".join(                 # 生成表头：每列是一条规则
        f'<th title="{_esc(r.name)}">{_esc(r.id)}</th>' for r in report.rules  # title=悬停提示规则全名，单元格显示规则ID
    )
    rows = []                         # 准备装每一行的 HTML
    for dev in report.devices:        # 遍历每台设备（生成一行）
        cells = []                    # 准备装这行的规则单元格
        by_rule = {r.rule.id: r for r in dev.results}  # 字典推导式：按规则ID建索引，方便按ID快速取结果
        for rule in report.rules:     # 按规则顺序遍历（保证列顺序一致）
            res = by_rule[rule.id]    # 取这条规则在这台设备上的结果
            if res.passed:            # 合规
                cells.append(f'<td class="cell-p" title="{_esc(rule.name)}">✓</td>')  # 绿色 ✓ 单元格
            else:                     # 不合规
                cells.append(f'<td class="cell-f" title="{_esc(rule.name)}">✗</td>')  # 红色 ✗ 单元格
        rows.append(                  # 拼出完整一行
            f"<tr><td><b>{_esc(dev.name)}</b></td>"          # 设备名（加粗）
            f'<td class="muted">{_esc(dev.role)}</td>'       # 角色
            f'<td class="muted">{_esc(dev.mgmt_ip)}</td>'    # 管理IP
            f'<td>{dev.pass_count}/{len(report.rules)}</td>' # 通过数/总规则数
            f'<td style="color:{_rate_color(dev.rate)};font-weight:700">{dev.rate}%</td>'  # 合规率（按值着色）
            f"<td>{_status_badge(dev.rate)}</td>"            # 状态徽章
            + "".join(cells)          # 拼接所有规则单元格
            + "</tr>"                 # 行结束标签
        )
    return (                          # 拼成完整表格
        '<table><thead><tr><th>设备</th><th>角色</th><th>管理IP</th><th>通过</th><th>合规率</th><th>状态</th>'  # 固定表头列
        + header                      # 追加规则列表头
        + "</tr></thead><tbody>"      # 表头结束、表体开始
        + "".join(rows)               # 拼接所有数据行
        + "</tbody></table>"          # 表格结束
    )


def _violation_details(report: AuditReport) -> str:
    """不合规设备逐条明细 + 修复建议。"""
    if not report.noncompliant_devices:  # 没有不合规设备
        return '<p class="pass">全部设备均合规，无不合规项 🎉</p>'  # 返回庆祝提示
    blocks = []                        # 准备装每个设备块
    for dev in report.noncompliant_devices:  # 遍历不合规设备
        items = []                     # 准备装该设备每条违规
        for res in dev.failures:       # 遍历失败规则（已按严重性排好序）
            sev = res.rule.severity    # 取严重性
            items.append(              # 拼一个违规项卡片
                f'<div class="violation {sev}">'                                  # 违规块（类名带严重性，用于左边色条）
                f'<b>{_esc(res.rule.id)} {_esc(res.rule.name)}</b>'               # 规则ID+名称（加粗）
                f'<span class="sev" style="background:{SEVERITY_COLOR[sev]}">{SEVERITY_LABEL[sev]}</span>'  # 严重性徽章
                f'<div class="muted" style="margin-top:4px">{_esc(res.rule.description)}</div>'  # 规则描述
                + (                                                     # 证据区（三目运算符选择）
                    f'<div class="evidence">{"\n".join(_esc(e) for e in res.evidence)}</div>'  # 有证据：逐行转义拼接
                    if res.evidence                                    # 有证据时
                    else '<div class="evidence">（未在配置中命中合规项）</div>'  # 没证据时给占位提示
                )
                + f'<div class="remediation">✅ 改进建议：{_esc(res.rule.remediation)}</div>'  # 修复建议
                + "</div>"                                             # 违规块结束
            )
        blocks.append(                # 把该设备所有违规包成一个块
            f'<div style="margin-bottom:18px"><h3 style="font-size:15px;margin-bottom:10px">'  # 块开始 + 标题开始
            f'{_esc(dev.name)} <span class="muted">（{_esc(dev.role)} · {_esc(dev.mgmt_ip)} · 合规率 '  # 标题：设备名/角色/IP
            f'<span style="color:{_rate_color(dev.rate)}">{dev.rate}%</span>）</span></h3>'  # 标题里的合规率（着色）
            + "".join(items)          # 拼该设备所有违规项
            + "</div>"                # 块结束
        )
    return "".join(blocks)            # 所有设备块拼接返回


def _top_violations(report: AuditReport) -> str:
    """Top 违规规则统计表。"""
    if not report.top_violations():   # 没有违规规则
        return '<p class="pass">无违规规则。</p>'  # 返回提示
    rows = []                         # 准备装行
    for rule_id, count in report.top_violations():  # 遍历 (规则ID, 违规设备数)
        rule = next(r for r in report.rules if r.id == rule_id)  # next(生成器) 从规则列表里找出 ID 匹配的那条规则对象
        rows.append(                  # 拼一行
            f"<tr><td><b>{_esc(rule.id)}</b></td><td>{_esc(rule.name)}</td>"        # 规则ID（加粗）+ 规则名
            f'<td class="muted">{_esc(rule.category)}</td>'                          # 类别
            f'<td><span style="color:{SEVERITY_COLOR[rule.severity]};font-weight:600">{SEVERITY_LABEL[rule.severity]}</span></td>'  # 严重性（着色）
            f'<td class="fail">{count} 台</td></tr>'                                 # 违规台数
        )
    return (                          # 拼成完整表格
        "<table><thead><tr><th>规则</th><th>名称</th><th>类别</th><th>严重性</th><th>违规设备数</th></tr></thead><tbody>"
        + "".join(rows)               # 拼接所有行
        + "</tbody></table>"          # 表格结束
    )
