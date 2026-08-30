#!/usr/bin/env python3
"""规则引擎与解析引擎单元测试（标准库 unittest，无额外依赖）。

用法：
    py -3.12 test_audit.py
    py -3.12 -m unittest test_audit -v
"""
from __future__ import annotations

import unittest
from pathlib import Path

from auditor import audit_device, build_report
from parser import parse_config
from rules import load_rules

BASE_DIR = Path(__file__).resolve().parent
SAMPLES = BASE_DIR / "samples"

# 预期合规梯度与违规规则（与 docs/03 合规基线一致）
EXPECTED_RATE = {"SW-Core": 100.0, "SW-Agg": 70.0, "SW-Acc1": 60.0, "SW-Acc2": 30.0}
EXPECTED_FAILS = {
    "SW-Core": [],
    "SW-Agg": ["R08", "R09", "R10"],
    "SW-Acc1": ["R01", "R07", "R08", "R09"],
    "SW-Acc2": ["R01", "R03", "R04", "R05", "R06", "R07", "R08"],
}


class TestRules(unittest.TestCase):
    def test_rule_count(self):
        rules = load_rules()
        self.assertEqual(len(rules), 10)

    def test_rule_ids_unique(self):
        rules = load_rules()
        ids = [r.id for r in rules]
        self.assertEqual(len(ids), len(set(ids)))


class TestParser(unittest.TestCase):
    def test_sysname(self):
        text = (SAMPLES / "SW-Core.cfg").read_text(encoding="utf-8")
        self.assertEqual(parse_config(text).sysname, "SW-Core")

    def test_mgmt_ip_prefers_vlanif100(self):
        # SW-Core 有 Vlanif10/20/30/100，管理地址应取 Vlanif100 而非第一个
        text = (SAMPLES / "SW-Core.cfg").read_text(encoding="utf-8")
        self.assertEqual(parse_config(text).mgmt_ip, "192.168.100.1")

    def test_vlans(self):
        text = (SAMPLES / "SW-Core.cfg").read_text(encoding="utf-8")
        self.assertEqual(parse_config(text).vlans, ["10", "20", "30", "100"])


class TestAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = load_rules()

    def _device(self, name: str):
        text = (SAMPLES / f"{name}.cfg").read_text(encoding="utf-8")
        return audit_device(name, name, "接入层", text, self.rules)

    def test_compliance_gradient(self):
        for name, rate in EXPECTED_RATE.items():
            self.assertEqual(self._device(name).rate, rate, name)

    def test_failure_rules(self):
        for name, fails in EXPECTED_FAILS.items():
            got = [r.rule.id for r in self._device(name).failures]
            self.assertEqual(got, fails, name)

    def test_overall_rate_and_alert(self):
        devs = [
            (n, n, "接入层", (SAMPLES / f"{n}.cfg").read_text(encoding="utf-8"))
            for n in EXPECTED_RATE
        ]
        report = build_report(devs, self.rules, threshold=90.0)
        self.assertEqual(report.overall_rate, 65.0)
        self.assertTrue(report.alert_triggered)
        self.assertEqual(len(report.noncompliant_devices), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
