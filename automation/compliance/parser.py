#!/usr/bin/env python3
"""正则解析引擎。

把华为设备 `display current-configuration` 的原始文本，解析为结构化数据
（ParsedConfig），供规则引擎与报告使用。原始文本保留在 raw_text 中，
规则引擎直接在其上做正则匹配，结构化字段用于报告展示与设备信息提取。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ParsedConfig:
    """一段运行配置的结构化解析结果。"""

    raw_text: str = ""
    sysname: str = ""
    vlans: list[str] = field(default_factory=list)
    local_users: list[str] = field(default_factory=list)
    snmp_communities: list[str] = field(default_factory=list)
    interfaces: dict[str, list[str]] = field(default_factory=dict)
    info_center: list[str] = field(default_factory=list)
    acl_lines: list[str] = field(default_factory=list)
    vty_lines: list[str] = field(default_factory=list)
    mgmt_ips: list[str] = field(default_factory=list)
    mgmt_ip: str = ""  # 管理 VLAN(Vlanif100) 的地址


def _lines_starting_with(text: str, prefix: str) -> list[str]:
    """返回以 prefix 开头的行（去首尾空白）。"""
    return [ln.strip() for ln in text.splitlines() if ln.strip().startswith(prefix)]


def _extract_sysname(text: str) -> str:
    m = re.search(r"^sysname\s+(\S+)", text, re.MULTILINE)
    return m.group(1) if m else ""


def _extract_vlans(text: str) -> list[str]:
    m = re.search(r"^vlan batch\s+(.+)$", text, re.MULTILINE)
    return m.group(1).split() if m else []


def _extract_interfaces(text: str) -> dict[str, list[str]]:
    """把 interface 段解析为 {接口名: [配置行, ...]}。"""
    interfaces: dict[str, list[str]] = {}
    current = ""
    for raw in text.splitlines():
        line = raw.rstrip()
        if re.match(r"^interface\s+", line):
            current = line.split(None, 1)[1].strip()
            interfaces[current] = []
        elif current and line.startswith(" "):
            interfaces[current].append(line.strip())
        else:
            current = ""
    return interfaces


def _extract_mgmt_ips(interfaces: dict[str, list[str]]) -> list[str]:
    """提取所有 VLANIF 接口的 IP 地址。"""
    ips = []
    for name, lines in interfaces.items():
        if name.lower().startswith("vlanif"):
            for ln in lines:
                m = re.match(r"ip address\s+(\S+)\s+(\S+)", ln)
                if m:
                    ips.append(m.group(1))
    return ips


def _extract_mgmt_ip(interfaces: dict[str, list[str]]) -> str:
    """提取管理地址：优先管理 VLAN(Vlanif100)，否则取首个 VLANIF 地址。"""
    fallback = ""
    for name, lines in interfaces.items():
        if not name.lower().startswith("vlanif"):
            continue
        for ln in lines:
            m = re.match(r"ip address\s+(\S+)\s+(\S+)", ln)
            if m:
                if name.lower() == "vlanif100":
                    return m.group(1)
                if not fallback:
                    fallback = m.group(1)
    return fallback


def parse_config(text: str) -> ParsedConfig:
    """解析一段运行配置文本，返回结构化 ParsedConfig。"""
    text = text.strip()
    interfaces = _extract_interfaces(text)
    cfg = ParsedConfig(raw_text=text)
    cfg.sysname = _extract_sysname(text)
    cfg.vlans = _extract_vlans(text)
    cfg.local_users = _lines_starting_with(text, "local-user")
    cfg.snmp_communities = _lines_starting_with(text, "snmp-agent community")
    cfg.interfaces = interfaces
    cfg.info_center = _lines_starting_with(text, "info-center")
    cfg.acl_lines = _lines_starting_with(text, "acl") + _lines_starting_with(text, "rule")
    cfg.vty_lines = _lines_starting_with(text, "user-interface vty")
    cfg.mgmt_ips = _extract_mgmt_ips(interfaces)
    cfg.mgmt_ip = _extract_mgmt_ip(interfaces)
    return cfg
