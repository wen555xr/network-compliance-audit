#!/usr/bin/env python3
"""企业微信机器人告警：总体合规率低于阈值时推送 Markdown 告警。"""
from __future__ import annotations

import requests

try:  # 作为包导入
    from .auditor import AuditReport
except ImportError:  # 直接以脚本方式运行
    from auditor import AuditReport


def build_markdown(report: AuditReport) -> str:
    """构造企业微信 Markdown 告警内容。"""
    lines = [
        "## 网络设备配置合规告警",
        f"> 总体合规率 <font color=\"warning\">{report.overall_rate}%</font>（阈值 {report.threshold}%）",
        f"> 审计设备 {len(report.devices)} 台，不合规 {len(report.noncompliant_devices)} 台",
        "",
        "**不合规设备：**",
    ]
    for dev in report.noncompliant_devices:
        lines.append(f"- **{dev.name}**（{dev.role} · {dev.mgmt_ip}）：合规率 "
                     f"<font color=\"warning\">{dev.rate}%</font>，违规 {dev.fail_count} 项")
    if report.top_violations():
        lines.append("")
        lines.append("**Top 违规规则：**")
        for rule_id, count in report.top_violations(5):
            rule = next(r for r in report.rules if r.id == rule_id)
            lines.append(f"- {rule_id} {rule.name}：{count} 台违规")
    lines.append("")
    lines.append(f"生成时间：{report.generated_at}")
    return "\n".join(lines)


def send(report: AuditReport, webhook: str) -> bool:
    """发送告警。webhook 为空时仅打印到控制台（dry-run）。"""
    markdown = build_markdown(report)
    if not webhook:
        print("\n[告警] 未配置企业微信 webhook，告警内容（dry-run）：")
        print(markdown)
        return False
    payload = {"msgtype": "markdown", "markdown": {"content": markdown}}
    resp = requests.post(webhook, json=payload, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    ok = data.get("errcode") == 0
    print(f"[告警] 企业微信推送{'成功' if ok else '失败'}: errcode={data.get('errcode')}, errmsg={data.get('errmsg')}")
    return ok
