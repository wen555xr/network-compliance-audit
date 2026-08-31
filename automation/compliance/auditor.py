#!/usr/bin/env python3
# 审计器：把设备配置和规则库「组合起来」——每台设备 × 每条规则，算出每台设备的合规率，
# 再汇总出总体合规率、不合规设备清单、Top 违规规则。是「计算结果」的地方。

"""审计器：逐设备 × 逐规则比对，计算合规率并汇总。"""
from __future__ import annotations  # 兼容新旧 Python 版本的类型注解语法

import datetime                     # 标准库：获取报告生成时间
from dataclasses import dataclass, field  # 数据类工具

try:                                # 先尝试「作为包」导入
    from .parser import ParsedConfig, parse_config   # 相对导入：解析引擎
    from .rules import Rule, RuleResult, SEVERITY_ORDER, check_all  # 相对导入：规则引擎
except ImportError:                 # 直接 py main.py 运行时退回普通导入
    from parser import ParsedConfig, parse_config
    from rules import Rule, RuleResult, SEVERITY_ORDER, check_all


@dataclass                          # 数据类
class DeviceResult:
    """单台设备的审计结果。"""

    name: str                                     # 设备名（来自清单）
    host: str                                     # IP 地址
    role: str                                     # 角色（核心/汇聚/接入）
    parsed: ParsedConfig                          # 该设备的解析结果对象
    results: list[RuleResult]                     # 该设备所有规则的执行结果列表

    @property                                     # 属性：设备名
    def sysname(self) -> str:
        return self.parsed.sysname or self.name   # 优先用配置解析出的设备名，没有就用清单里的名字

    @property                                     # 属性：管理 IP
    def mgmt_ip(self) -> str:
        return self.parsed.mgmt_ip or self.host   # 优先用解析出的管理 IP，没有就用 host 兜底

    @property                                     # 属性：通过规则数
    def pass_count(self) -> int:
        return sum(1 for r in self.results if r.passed)  # 生成器表达式：合规的结果数 1 个加 1，最后求和

    @property                                     # 属性：失败规则数
    def fail_count(self) -> int:
        return len(self.results) - self.pass_count  # 总规则数减去通过数

    @property                                     # 属性：合规率
    def rate(self) -> float:
        if not self.results:                      # 如果一条规则都没有
            return 0.0                            # 合规率记 0
        return round(self.pass_count / len(self.results) * 100, 1)  # 通过/总数×100，round 保留 1 位小数

    @property                                     # 属性：失败规则列表（按严重性排序）
    def failures(self) -> list[RuleResult]:
        return sorted(                            # sorted 排序
            (r for r in self.results if not r.passed),  # 先生成器筛出所有没通过的规则
            key=lambda r: SEVERITY_ORDER.get(r.rule.severity, 9),  # key 指定排序依据：按严重性权重（查不到用 9 排最后）
        )

    @property                                     # 属性：是否合规
    def is_compliant(self) -> bool:
        return self.fail_count == 0               # 一条失败都没有才算合规（all-or-nothing）


@dataclass                          # 数据类
class AuditReport:
    """整体审计报告数据模型。"""

    generated_at: str                 # 报告生成时间字符串
    devices: list[DeviceResult]       # 所有设备的审计结果列表
    rules: list[Rule]                 # 全部规则
    threshold: float                  # 告警阈值

    @property                         # 属性：总检查次数
    def total_checks(self) -> int:
        return len(self.rules) * len(self.devices)  # 规则数 × 设备数（如 10×4=40 次检查）

    @property                         # 属性：总通过数
    def total_pass(self) -> int:
        return sum(d.pass_count for d in self.devices)  # 每台设备通过数相加，sum 求和

    @property                         # 属性：总体合规率
    def overall_rate(self) -> float:
        if not self.total_checks:     # 总检查数为 0（没有设备或没有规则）
            return 0.0                # 返回 0
        return round(self.total_pass / self.total_checks * 100, 1)  # 总通过/总检查×100，保留 1 位小数

    @property                         # 属性：不合规设备列表
    def noncompliant_devices(self) -> list[DeviceResult]:
        return [d for d in self.devices if not d.is_compliant]  # 列表推导式：筛出 is_compliant 为假的设备

    @property                         # 属性：合规设备列表
    def compliant_devices(self) -> list[DeviceResult]:
        return [d for d in self.devices if d.is_compliant]  # 列表推导式：筛出合规的设备

    @property                         # 属性：是否触发告警
    def alert_triggered(self) -> bool:
        return self.overall_rate < self.threshold  # 总体合规率低于阈值即触发，这就是告警逻辑的核心

    def top_violations(self, limit: int = 5) -> list[tuple[str, int]]:
        """统计最常被违反的规则（规则ID -> 违规设备数）。"""
        counter: dict[str, int] = {}   # 空字典，用来计数（规则ID -> 违规次数）
        for dev in self.devices:       # 遍历每台设备
            for r in dev.failures:     # 遍历它的每条失败规则
                counter[r.rule.id] = counter.get(r.rule.id, 0) + 1  # 经典计数模式：取当前值（没有给0）+1 存回
        ranked = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))  # 排序：按次数从大到小（负号取反），次数相同按 ID 字母序
        return ranked[:limit]          # 切片取前 limit 个（默认前 5）


def audit_device(name: str, host: str, role: str, text: str, rules: list[Rule]) -> DeviceResult:
    """对单台设备执行全部规则审计。"""
    parsed = parse_config(text)        # 先把配置文本解析成 ParsedConfig
    results = check_all(rules, parsed.raw_text)  # 用全部规则去匹配原始文本，得到所有检查结果
    return DeviceResult(name=name, host=host, role=role, parsed=parsed, results=results)  # 打包成 DeviceResult 返回


def build_report(
    device_configs: list[tuple[str, str, str, str]],
    rules: list[Rule],
    threshold: float,
) -> AuditReport:
    """按 (name, host, role, text) 列表构建整体审计报告。"""
    devices = [audit_device(name, host, role, text, rules) for name, host, role, text in device_configs]  # 列表推导式：每台设备审计一遍，元组解包成4个变量
    return AuditReport(                             # 构造整体报告对象
        generated_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # 当前时间，格式如 2026-08-31 01:35:09
        devices=devices,                            # 设备审计结果
        rules=rules,                                # 规则列表
        threshold=threshold,                        # 阈值
    )
