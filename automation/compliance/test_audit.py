#!/usr/bin/env python3
# 单元测试文件：用 Python 标准库 unittest 对「规则引擎 + 解析引擎 + 审计逻辑」做自动化验证。
# 运行方式：py -3.12 test_audit.py

"""规则引擎与解析引擎单元测试（标准库 unittest，无额外依赖）。

用法：
    py -3.12 test_audit.py
    py -3.12 -m unittest test_audit -v
"""
from __future__ import annotations  # 兼容新旧 Python 版本的类型注解语法

import unittest                     # 标准库：单元测试框架
from pathlib import Path            # 路径库

from auditor import audit_device, build_report  # 导入审计函数（测试目标）
from parser import parse_config                 # 导入解析函数（测试目标）
from rules import load_rules                    # 导入规则加载函数（测试目标）

BASE_DIR = Path(__file__).resolve().parent  # 当前文件所在目录 = compliance/
SAMPLES = BASE_DIR / "samples"              # 样例配置目录

# 预期合规梯度与违规规则（与 docs/03 合规基线一致）
EXPECTED_RATE = {"SW-Core": 100.0, "SW-Agg": 70.0, "SW-Acc1": 60.0, "SW-Acc2": 30.0}  # 每台设备预期的合规率
EXPECTED_FAILS = {                        # 每台设备预期的失败规则ID列表
    "SW-Core": [],
    "SW-Agg": ["R08", "R09", "R10"],
    "SW-Acc1": ["R01", "R07", "R08", "R09"],
    "SW-Acc2": ["R01", "R03", "R04", "R05", "R06", "R07", "R08"],
}


class TestRules(unittest.TestCase):       # 测试规则加载：继承 unittest.TestCase（每个 test_ 开头的方法都会被运行）
    def test_rule_count(self):            # 测试用例1：规则数量
        rules = load_rules()              # 加载规则
        self.assertEqual(len(rules), 10)  # 断言：规则数必须等于 10（不符合则测试失败）

    def test_rule_ids_unique(self):       # 测试用例2：规则ID不重复
        rules = load_rules()              # 加载规则
        ids = [r.id for r in rules]       # 取出所有规则ID
        self.assertEqual(len(ids), len(set(ids)))  # 断言：ID列表长度 == 去重后长度（有重复则失败）


class TestParser(unittest.TestCase):      # 测试解析引擎
    def test_sysname(self):               # 测试用例：能解析出设备名
        text = (SAMPLES / "SW-Core.cfg").read_text(encoding="utf-8")  # 读 SW-Core 样例配置
        self.assertEqual(parse_config(text).sysname, "SW-Core")       # 断言解析出的设备名是 SW-Core

    def test_mgmt_ip_prefers_vlanif100(self):  # 测试用例：管理IP优先取 Vlanif100
        # SW-Core 有 Vlanif10/20/30/100，管理地址应取 Vlanif100 而非第一个
        text = (SAMPLES / "SW-Core.cfg").read_text(encoding="utf-8")   # 读样例
        self.assertEqual(parse_config(text).mgmt_ip, "192.168.100.1")  # 断言管理IP是 Vlanif100 的地址

    def test_vlans(self):                 # 测试用例：VLAN 解析
        text = (SAMPLES / "SW-Core.cfg").read_text(encoding="utf-8")   # 读样例
        self.assertEqual(parse_config(text).vlans, ["10", "20", "30", "100"])  # 断言VLAN列表符合预期


class TestAudit(unittest.TestCase):       # 测试审计逻辑
    @classmethod                          # 类方法：每个测试运行前只执行一次
    def setUpClass(cls):                  # 测试前的准备：加载规则
        cls.rules = load_rules()          # 把规则存到类上，供各测试方法用

    def _device(self, name: str):         # 辅助方法：审计指定设备并返回结果
        text = (SAMPLES / f"{name}.cfg").read_text(encoding="utf-8")  # 读对应样例
        return audit_device(name, name, "接入层", text, self.rules)   # 调用审计函数并返回

    def test_compliance_gradient(self):   # 测试用例：合规梯度符合预期
        for name, rate in EXPECTED_RATE.items():  # 遍历每台设备的预期合规率
            self.assertEqual(self._device(name).rate, rate, name)  # 断言实际合规率 == 预期（name 是失败时显示的信息）

    def test_failure_rules(self):         # 测试用例：失败规则列表符合预期
        for name, fails in EXPECTED_FAILS.items():  # 遍历每台设备的预期失败规则
            got = [r.rule.id for r in self._device(name).failures]  # 取实际失败规则ID列表
            self.assertEqual(got, fails, name)  # 断言实际 == 预期

    def test_overall_rate_and_alert(self):  # 测试用例：总体合规率与告警触发
        devs = [                          # 构造所有设备的 (名称, IP, 角色, 文本) 列表
            (n, n, "接入层", (SAMPLES / f"{n}.cfg").read_text(encoding="utf-8"))  # 元组解包，IP 用设备名占位
            for n in EXPECTED_RATE        # 遍历 4 台设备
        ]
        report = build_report(devs, self.rules, threshold=90.0)  # 构建整体报告，阈值 90
        self.assertEqual(report.overall_rate, 65.0)  # 断言总体合规率 = 65%（100/70/60/30 的平均形态）
        self.assertTrue(report.alert_triggered)      # 断言触发了告警（65 < 90）
        self.assertEqual(len(report.noncompliant_devices), 3)  # 断言不合规设备有 3 台


if __name__ == "__main__":                # 只有直接运行时才执行
    unittest.main(verbosity=2)            # 启动单元测试，verbosity=2 表示详细输出每个用例
