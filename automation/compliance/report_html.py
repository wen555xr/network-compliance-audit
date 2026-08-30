#!/usr/bin/env python3
"""生成自包含 HTML 审计报告（内联 CSS，无外部依赖）。"""
from __future__ import annotations

import html

try:  # 作为包导入
    from .auditor import AuditReport
except ImportError:  # 直接以脚本方式运行
    from auditor import AuditReport

SEVERITY_LABEL = {"high": "高危", "medium": "中危", "low": "低危"}
SEVERITY_COLOR = {"high": "#d93025", "medium": "#e37400", "low": "#5f6368"}


def _esc(value: object) -> str:
    return html.escape(str(value))


def _status_badge(rate: float) -> str:
    if rate >= 100:
        return '<span style="background:#e6f4ea;color:#137333;padding:2px 10px;border-radius:12px;font-weight:600">合规</span>'
    if rate >= 80:
        return '<span style="background:#fef7e0;color:#b06000;padding:2px 10px;border-radius:12px;font-weight:600">基本合规</span>'
    return '<span style="background:#fce8e6;color:#c5221f;padding:2px 10px;border-radius:12px;font-weight:600">不合规</span>'


def _rate_color(rate: float) -> str:
    if rate >= 90:
        return "#137333"
    if rate >= 70:
        return "#b06000"
    return "#c5221f"


def render(report: AuditReport) -> str:
    """渲染完整 HTML 报告字符串。"""
    # KPI 卡片
    kpi_cards = "".join(
        [
            _kpi("审计设备数", len(report.devices)),
            _kpi("合规设备", len(report.compliant_devices), "#137333"),
            _kpi("不合规设备", len(report.noncompliant_devices), "#c5221f"),
            _kpi("总体合规率", f"{report.overall_rate}%", _rate_color(report.overall_rate)),
            _kpi("告警阈值", f"{report.threshold}%"),
            _kpi(
                "告警状态",
                "已触发" if report.alert_triggered else "未触发",
                "#c5221f" if report.alert_triggered else "#137333",
            ),
        ]
    )

    matrix = _compliance_matrix(report)
    details = _violation_details(report)
    top = _top_violations(report)

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
    return (
        f'<div class="kpi"><div class="label">{_esc(label)}</div>'
        f'<div class="value" style="color:{color}">{_esc(value)}</div></div>'
    )


def _compliance_matrix(report: AuditReport) -> str:
    """设备 × 规则 合规矩阵表。"""
    header = "".join(
        f'<th title="{_esc(r.name)}">{_esc(r.id)}</th>' for r in report.rules
    )
    rows = []
    for dev in report.devices:
        cells = []
        by_rule = {r.rule.id: r for r in dev.results}
        for rule in report.rules:
            res = by_rule[rule.id]
            if res.passed:
                cells.append(f'<td class="cell-p" title="{_esc(rule.name)}">✓</td>')
            else:
                cells.append(f'<td class="cell-f" title="{_esc(rule.name)}">✗</td>')
        rows.append(
            f"<tr><td><b>{_esc(dev.name)}</b></td>"
            f'<td class="muted">{_esc(dev.role)}</td>'
            f'<td class="muted">{_esc(dev.mgmt_ip)}</td>'
            f'<td>{dev.pass_count}/{len(report.rules)}</td>'
            f'<td style="color:{_rate_color(dev.rate)};font-weight:700">{dev.rate}%</td>'
            f"<td>{_status_badge(dev.rate)}</td>"
            + "".join(cells)
            + "</tr>"
        )
    return (
        '<table><thead><tr><th>设备</th><th>角色</th><th>管理IP</th><th>通过</th><th>合规率</th><th>状态</th>'
        + header
        + "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _violation_details(report: AuditReport) -> str:
    """不合规设备逐条明细 + 修复建议。"""
    if not report.noncompliant_devices:
        return '<p class="pass">全部设备均合规，无不合规项 🎉</p>'
    blocks = []
    for dev in report.noncompliant_devices:
        items = []
        for res in dev.failures:
            sev = res.rule.severity
            items.append(
                f'<div class="violation {sev}">'
                f'<b>{_esc(res.rule.id)} {_esc(res.rule.name)}</b>'
                f'<span class="sev" style="background:{SEVERITY_COLOR[sev]}">{SEVERITY_LABEL[sev]}</span>'
                f'<div class="muted" style="margin-top:4px">{_esc(res.rule.description)}</div>'
                + (
                    f'<div class="evidence">{"\n".join(_esc(e) for e in res.evidence)}</div>'
                    if res.evidence
                    else '<div class="evidence">（未在配置中命中合规项）</div>'
                )
                + f'<div class="remediation">✅ 改进建议：{_esc(res.rule.remediation)}</div>'
                + "</div>"
            )
        blocks.append(
            f'<div style="margin-bottom:18px"><h3 style="font-size:15px;margin-bottom:10px">'
            f'{_esc(dev.name)} <span class="muted">（{_esc(dev.role)} · {_esc(dev.mgmt_ip)} · 合规率 '
            f'<span style="color:{_rate_color(dev.rate)}">{dev.rate}%</span>）</span></h3>'
            + "".join(items)
            + "</div>"
        )
    return "".join(blocks)


def _top_violations(report: AuditReport) -> str:
    """Top 违规规则统计表。"""
    if not report.top_violations():
        return '<p class="pass">无违规规则。</p>'
    rows = []
    for rule_id, count in report.top_violations():
        rule = next(r for r in report.rules if r.id == rule_id)
        rows.append(
            f"<tr><td><b>{_esc(rule.id)}</b></td><td>{_esc(rule.name)}</td>"
            f'<td class="muted">{_esc(rule.category)}</td>'
            f'<td><span style="color:{SEVERITY_COLOR[rule.severity]};font-weight:600">{SEVERITY_LABEL[rule.severity]}</span></td>'
            f'<td class="fail">{count} 台</td></tr>'
        )
    return (
        "<table><thead><tr><th>规则</th><th>名称</th><th>类别</th><th>严重性</th><th>违规设备数</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )
