#!/usr/bin/env python3
"""审计器：逐设备 × 逐规则比对，计算合规率并汇总。"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field

try:  # 作为包导入
    from .parser import ParsedConfig, parse_config
    from .rules import Rule, RuleResult, SEVERITY_ORDER, check_all
except ImportError:  # 直接以脚本方式运行时（py -3.12 main.py）
    from parser import ParsedConfig, parse_config
    from rules import Rule, RuleResult, SEVERITY_ORDER, check_all


@dataclass
class DeviceResult:
    """单台设备的审计结果。"""

    name: str
    host: str
    role: str
    parsed: ParsedConfig
    results: list[RuleResult]

    @property
    def sysname(self) -> str:
        return self.parsed.sysname or self.name

    @property
    def mgmt_ip(self) -> str:
        return self.parsed.mgmt_ip or self.host

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def fail_count(self) -> int:
        return len(self.results) - self.pass_count

    @property
    def rate(self) -> float:
        if not self.results:
            return 0.0
        return round(self.pass_count / len(self.results) * 100, 1)

    @property
    def failures(self) -> list[RuleResult]:
        return sorted(
            (r for r in self.results if not r.passed),
            key=lambda r: SEVERITY_ORDER.get(r.rule.severity, 9),
        )

    @property
    def is_compliant(self) -> bool:
        return self.fail_count == 0


@dataclass
class AuditReport:
    """整体审计报告数据模型。"""

    generated_at: str
    devices: list[DeviceResult]
    rules: list[Rule]
    threshold: float

    @property
    def total_checks(self) -> int:
        return len(self.rules) * len(self.devices)

    @property
    def total_pass(self) -> int:
        return sum(d.pass_count for d in self.devices)

    @property
    def overall_rate(self) -> float:
        if not self.total_checks:
            return 0.0
        return round(self.total_pass / self.total_checks * 100, 1)

    @property
    def noncompliant_devices(self) -> list[DeviceResult]:
        return [d for d in self.devices if not d.is_compliant]

    @property
    def compliant_devices(self) -> list[DeviceResult]:
        return [d for d in self.devices if d.is_compliant]

    @property
    def alert_triggered(self) -> bool:
        return self.overall_rate < self.threshold

    def top_violations(self, limit: int = 5) -> list[tuple[str, int]]:
        """统计最常被违反的规则（规则ID -> 违规设备数）。"""
        counter: dict[str, int] = {}
        for dev in self.devices:
            for r in dev.failures:
                counter[r.rule.id] = counter.get(r.rule.id, 0) + 1
        ranked = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
        return ranked[:limit]


def audit_device(name: str, host: str, role: str, text: str, rules: list[Rule]) -> DeviceResult:
    """对单台设备执行全部规则审计。"""
    parsed = parse_config(text)
    results = check_all(rules, parsed.raw_text)
    return DeviceResult(name=name, host=host, role=role, parsed=parsed, results=results)


def build_report(
    device_configs: list[tuple[str, str, str, str]],
    rules: list[Rule],
    threshold: float,
) -> AuditReport:
    """按 (name, host, role, text) 列表构建整体审计报告。"""
    devices = [audit_device(name, host, role, text, rules) for name, host, role, text in device_configs]
    return AuditReport(
        generated_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        devices=devices,
        rules=rules,
        threshold=threshold,
    )
