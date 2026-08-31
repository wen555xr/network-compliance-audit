#!/usr/bin/env python3
# 规则引擎：把 rules.yaml 里的 10 条规则加载成 Rule 对象，然后对设备配置文本执行正则检查。
# 核心设计：规则「数据驱动」——存在 YAML 里，增删规则只改 YAML，不用改代码。

"""规则引擎：加载 rules.yaml 并对配置文本执行正则合规检查。"""
from __future__ import annotations  # 兼容新旧 Python 版本的类型注解语法

import re                            # 标准库：正则表达式模块
from dataclasses import dataclass, field  # 数据类工具
from pathlib import Path             # 路径库

import yaml                          # 解析 rules.yaml

BASE_DIR = Path(__file__).resolve().parent  # 当前文件所在目录 = compliance/
DEFAULT_RULES = BASE_DIR / "rules.yaml"     # 默认规则文件路径

# 严重性排序权重（用于报告排序）
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}  # 高危排最前（0），中危(1)、低危(2)依次靠后


@dataclass                          # 数据类：自动生成构造函数
class Rule:
    """一条合规规则。"""

    id: str                                    # 规则编号，如 R01
    name: str                                  # 规则名称，如「SNMP 社区串安全」
    category: str                              # 类别：SNMP / AAA / 日志 / 访问控制等
    severity: str                              # 严重性：high / medium / low
    check_type: str  # regex_present | regex_absent  # 检查类型：要求出现=合规，或要求不出现=合规
    pattern: str                               # 正则表达式
    description: str = ""                      # 规则描述（默认空串）
    remediation: str = ""                      # 修复建议（默认空串）

    @classmethod                                # 类方法：不需要实例就能调用
    def from_dict(cls, data: dict) -> "Rule":   # 从字典（YAML 里的一条规则）创建 Rule 对象
        return cls(                             # cls(...) 等价于 Rule(...)，调用构造函数
            id=data["id"],                      # 取 id（用 [key] 必须存在，否则报 KeyError）
            name=data["name"],                  # 取 name
            category=data["category"],          # 取 category
            severity=data["severity"],          # 取 severity
            check_type=data["check_type"],      # 取 check_type
            pattern=data["pattern"],            # 取 pattern
            description=data.get("description", ""),  # 取 description（用 .get 可选，没有给默认空串）
            remediation=data.get("remediation", ""),  # 取 remediation（可选）
        )


@dataclass                          # 数据类
class RuleResult:
    """单条规则在单台设备上的执行结果。"""

    rule: Rule                                # 对应哪条规则
    passed: bool                              # True=合规，False=不合规
    evidence: list[str] = field(default_factory=list)  # 命中的证据行（正则匹配到的配置行，报告展示用）

    @property                                 # 属性装饰器：把方法伪装成变量，调用时不加括号
    def detail(self) -> str:
        return "合规" if self.passed else "不合规"  # 三目运算符：合规返回"合规"，否则返回"不合规"


def load_rules(path: Path | None = None) -> list[Rule]:
    """加载规则库 YAML，返回规则列表。"""
    rules_path = Path(path) if path else DEFAULT_RULES  # 传了路径用传的，否则用默认规则文件
    with open(rules_path, "r", encoding="utf-8") as f:  # 打开规则文件：只读、UTF-8
        data = yaml.safe_load(f)                        # 解析 YAML -> Python 数据
    return [Rule.from_dict(item) for item in data["rules"]]  # 列表推导式：遍历每条规则字典，转成 Rule 对象


def _matching_lines(pattern: str, text: str) -> list[str]:
    """返回所有命中的行（去首尾空白）。"""
    rx = re.compile(pattern, re.IGNORECASE)   # 预编译正则，IGNORECASE=忽略大小写（设备配置大小写都可能）
    return [ln.strip() for ln in text.splitlines() if rx.search(ln)]  # 遍历每行，包含匹配就留下（去空白）


def check_rule(rule: Rule, text: str) -> RuleResult:
    """对单条规则执行检查，返回 RuleResult。"""
    matches = _matching_lines(rule.pattern, text)  # 找出所有命中行作为证据
    if rule.check_type == "regex_present":         # 规则要求「必须出现」
        passed = bool(matches)                     # 有命中行就合规（bool(非空列表)=True）
    elif rule.check_type == "regex_absent":        # 规则要求「必须不出现」
        passed = not matches                       # 没有命中行才合规
    else:                                          # 其他未知类型
        raise ValueError(f"未知检查类型: {rule.check_type}")  # 主动抛异常，防止 YAML 写错类型静默出错
    return RuleResult(rule=rule, passed=passed, evidence=matches)  # 构造并返回结果对象


def check_all(rules: list[Rule], text: str) -> list[RuleResult]:
    """对一段配置执行全部规则。"""
    return [check_rule(rule, text) for rule in rules]  # 列表推导式：把每条规则依次执行，结果收集成列表
