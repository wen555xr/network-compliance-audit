"""网络设备配置合规性自动审计系统核心包。

模块职责：
- parser:   正则解析引擎，把 display current-configuration 文本结构化
- rules:    合规规则库加载 + 规则引擎（解释 rules.yaml）
- auditor:  逐设备逐规则比对 + 评分 + 汇总
- collector: Netmiko 批量 SSH 采集运行配置
- report_html / report_excel / wechat_alert: 报告与告警
- main:     编排入口
"""
