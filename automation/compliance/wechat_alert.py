#!/usr/bin/env python3
# 企业微信机器人告警：总体合规率低于阈值时，把告警内容按企业微信 Markdown 格式拼好，
# POST 到群机器人 webhook 地址推送到群里；没配 webhook 就打印到控制台（dry-run 模式）。

"""企业微信机器人告警：总体合规率低于阈值时推送 Markdown 告警。"""
from __future__ import annotations  # 兼容新旧 Python 版本的类型注解语法

import requests                     # 第三方库：HTTP 请求，用来 POST 到 webhook

try:                                # 先尝试「作为包」导入
    from .auditor import AuditReport
except ImportError:                 # 直接运行脚本时退回普通导入
    from auditor import AuditReport


def build_markdown(report: AuditReport) -> str:
    """构造企业微信 Markdown 告警内容。"""
    lines = [                        # 用一个字符串列表一行一行攒内容，最后再拼接（好维护）
        "## 网络设备配置合规告警",    # Markdown 二级标题
        f"> 总体合规率 <font color=\"warning\">{report.overall_rate}%</font>（阈值 {report.threshold}%）",  # 引用块 + 彩色文字（企业微信特有标签），\" 是转义的双引号
        f"> 审计设备 {len(report.devices)} 台，不合规 {len(report.noncompliant_devices)} 台",  # 设备总数与不合规数
        "",                          # 空行（Markdown 段落分隔）
        "**不合规设备：**",          # 加粗标题
    ]
    for dev in report.noncompliant_devices:  # 遍历不合规设备
        lines.append(f"- **{dev.name}**（{dev.role} · {dev.mgmt_ip}）：合规率 "  # 列表项：设备名加粗 + 角色 + IP
                     f"<font color=\"warning\">{dev.rate}%</font>，违规 {dev.fail_count} 项")  # 合规率 + 违规项数
    if report.top_violations():      # 如果存在违规规则（有数据才加这段）
        lines.append("")             # 空行
        lines.append("**Top 违规规则：**")  # 加粗标题
        for rule_id, count in report.top_violations(5):  # 遍历前 5 条最常违规的规则
            rule = next(r for r in report.rules if r.id == rule_id)  # 通过规则ID找回规则对象（拿名称）
            lines.append(f"- {rule_id} {rule.name}：{count} 台违规")  # 列表项：规则ID+名称+违规台数
    lines.append("")                 # 空行
    lines.append(f"生成时间：{report.generated_at}")  # 结尾加生成时间
    return "\n".join(lines)          # 用换行把所有行拼成一个字符串返回


def send(report: AuditReport, webhook: str) -> bool:
    """发送告警。webhook 为空时仅打印到控制台（dry-run）。"""
    markdown = build_markdown(report)  # 先构造告警文本
    if not webhook:                  # 如果 webhook 是空的（没配置）
        print("\n[告警] 未配置企业微信 webhook，告警内容（dry-run）：")  # 提示进入 dry-run 模式
        print(markdown)              # 把告警内容打印到控制台
        return False                 # 返回 False（未真正发送）
    payload = {"msgtype": "markdown", "markdown": {"content": markdown}}  # 企业微信规定的 JSON 报文结构
    resp = requests.post(webhook, json=payload, timeout=10)  # POST 发送：json= 自动把字典转 JSON，timeout=10 秒超时
    resp.raise_for_status()          # 检查 HTTP 状态码，非 2xx 直接抛异常（让错误暴露）
    data = resp.json()               # 解析响应 JSON
    ok = data.get("errcode") == 0    # errcode 0 表示成功，非 0 表示失败
    print(f"[告警] 企业微信推送{'成功' if ok else '失败'}: errcode={data.get('errcode')}, errmsg={data.get('errmsg')}")  # 打印推送结果
    return ok                        # 返回是否成功
