#!/usr/bin/env python3
"""规则引擎：加载 rules.yaml 并对配置文本执行正则合规检查。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_RULES = BASE_DIR / "rules.yaml"

# 严重性排序权重（用于报告排序）
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class Rule:
    """一条合规规则。"""

    id: str
    name: str
    category: str
    severity: str
    check_type: str  # regex_present | regex_absent
    pattern: str
    description: str = ""
    remediation: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "Rule":
        return cls(
            id=data["id"],
            name=data["name"],
            category=data["category"],
            severity=data["severity"],
            check_type=data["check_type"],
            pattern=data["pattern"],
            description=data.get("description", ""),
            remediation=data.get("remediation", ""),
        )


@dataclass
class RuleResult:
    """单条规则在单台设备上的执行结果。"""

    rule: Rule
    passed: bool
    evidence: list[str] = field(default_factory=list)

    @property
    def detail(self) -> str:
        return "合规" if self.passed else "不合规"


def load_rules(path: Path | None = None) -> list[Rule]:
    """加载规则库 YAML，返回规则列表。"""
    rules_path = Path(path) if path else DEFAULT_RULES
    with open(rules_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return [Rule.from_dict(item) for item in data["rules"]]


def _matching_lines(pattern: str, text: str) -> list[str]:
    """返回所有命中的行（去首尾空白）。"""
    rx = re.compile(pattern, re.IGNORECASE)
    return [ln.strip() for ln in text.splitlines() if rx.search(ln)]


def check_rule(rule: Rule, text: str) -> RuleResult:
    """对单条规则执行检查，返回 RuleResult。"""
    matches = _matching_lines(rule.pattern, text)
    if rule.check_type == "regex_present":
        passed = bool(matches)
    elif rule.check_type == "regex_absent":
        passed = not matches
    else:
        raise ValueError(f"未知检查类型: {rule.check_type}")
    return RuleResult(rule=rule, passed=passed, evidence=matches)


def check_all(rules: list[Rule], text: str) -> list[RuleResult]:
    """对一段配置执行全部规则。"""
    return [check_rule(rule, text) for rule in rules]
