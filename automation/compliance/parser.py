#!/usr/bin/env python3
# 正则解析引擎：把设备返回的 display current-configuration「纯文本」解析成结构化数据（ParsedConfig）。
# 规则引擎和报告模块都靠这份结构化数据工作。

"""正则解析引擎。

把华为设备 `display current-configuration` 的原始文本，解析为结构化数据
（ParsedConfig），供规则引擎与报告使用。原始文本保留在 raw_text 中，
规则引擎直接在其上做正则匹配，结构化字段用于报告展示与设备信息提取。
"""
from __future__ import annotations  # 兼容新旧 Python 版本的类型注解语法

import re                           # 标准库：正则表达式模块，本文件的核心
from dataclasses import dataclass, field  # 数据类工具：自动生成 __init__ 等样板代码


@dataclass                          # 声明这是一个「数据类」
class ParsedConfig:
    """一段运行配置的结构化解析结果。"""

    raw_text: str = ""                                    # 原始配置文本（原样保留，规则引擎直接匹配）
    sysname: str = ""                                     # 设备名（如 SW-Core）
    vlans: list[str] = field(default_factory=list)        # VLAN 列表（如 ["10","20","30","100"]）
    local_users: list[str] = field(default_factory=list)  # AAA 本地用户配置行
    snmp_communities: list[str] = field(default_factory=list)  # SNMP 社区串配置行
    interfaces: dict[str, list[str]] = field(default_factory=dict)  # 接口配置 {接口名: [配置行]}
    info_center: list[str] = field(default_factory=list)  # 日志中心(info-center)配置行
    acl_lines: list[str] = field(default_factory=list)    # ACL 规则行
    vty_lines: list[str] = field(default_factory=list)    # 虚拟终端(user-interface vty)配置行
    mgmt_ips: list[str] = field(default_factory=list)     # 所有 VLANIF 接口的 IP 列表
    mgmt_ip: str = ""  # 管理 VLAN(Vlanif100) 的地址


def _lines_starting_with(text: str, prefix: str) -> list[str]:
    """返回以 prefix 开头的行（去首尾空白）。"""
    return [ln.strip() for ln in text.splitlines() if ln.strip().startswith(prefix)]  # 遍历每行，保留以指定前缀开头的行，并去掉首尾空白


def _extract_sysname(text: str) -> str:
    m = re.search(r"^sysname\s+(\S+)", text, re.MULTILINE)  # 正则找 sysname 后面的设备名；^=行首，\s+=空白，\S+=非空白，()=捕获组，MULTILINE=每行都当行首
    return m.group(1) if m else ""    # 匹配到就返回捕获组(设备名)，没匹配到返回空串


def _extract_vlans(text: str) -> list[str]:
    m = re.search(r"^vlan batch\s+(.+)$", text, re.MULTILINE)  # 正则匹配 vlan batch 行，捕获后面所有内容（.+）
    return m.group(1).split() if m else []  # 捕获的内容按空白拆成列表（"10 20 30" -> ["10","20","30"]），没匹配到给空列表


def _extract_interfaces(text: str) -> dict[str, list[str]]:
    """把 interface 段解析为 {接口名: [配置行, ...]}。"""
    interfaces: dict[str, list[str]] = {}   # 空字典，准备存结果
    current = ""                            # 记录「当前正在处理哪个接口」，空=不在任何接口段里
    for raw in text.splitlines():           # 逐行遍历配置
        line = raw.rstrip()                 # 去掉行尾空白（保留行首空格，用于判断缩进层级）
        if re.match(r"^interface\s+", line):        # 如果这行以 "interface " 开头（新接口段开始）
            current = line.split(None, 1)[1].strip()  # 取接口名（如 Vlanif100），作为当前接口
            interfaces[current] = []        # 给这个接口初始化一个空列表
        elif current and line.startswith(" "):      # 如果正在某个接口里，且这行以空格开头（是它的缩进子配置）
            interfaces[current].append(line.strip())  # 把该行去空白后追加到当前接口的配置列表
        else:                               # 否则（既不是新接口，也不是接口子配置）
            current = ""                    # 清空当前接口标记，表示离开了接口段
    return interfaces                       # 返回 {接口名: [配置行]} 字典


def _extract_mgmt_ips(interfaces: dict[str, list[str]]) -> list[str]:
    """提取所有 VLANIF 接口的 IP 地址。"""
    ips = []                                # 空列表准备存 IP
    for name, lines in interfaces.items():  # 遍历每个接口（name=接口名，lines=它的配置行）
        if name.lower().startswith("vlanif"):  # 接口名转小写后判断是否以 vlanif 开头（大小写不敏感）
            for ln in lines:                # 遍历该接口的每一行配置
                m = re.match(r"ip address\s+(\S+)\s+(\S+)", ln)  # 匹配 IP 地址行，捕获 IP 和掩码
                if m:                       # 匹配成功
                    ips.append(m.group(1))  # 取第 1 个捕获组（IP 地址）加入列表
    return ips                              # 返回所有 VLANIF 的 IP


def _extract_mgmt_ip(interfaces: dict[str, list[str]]) -> str:
    """提取管理地址：优先管理 VLAN(Vlanif100)，否则取首个 VLANIF 地址。"""
    fallback = ""                           # 备用变量：存「非管理VLAN」的第一个 IP
    for name, lines in interfaces.items():  # 遍历每个接口
        if not name.lower().startswith("vlanif"):  # 不是 VLANIF 接口就跳过
            continue                        # continue = 跳过本次循环，继续下一个
        for ln in lines:                    # 遍历该接口的配置行
            m = re.match(r"ip address\s+(\S+)\s+(\S+)", ln)  # 匹配 IP 地址行
            if m:                           # 匹配成功
                if name.lower() == "vlanif100":  # 如果正好是管理 VLAN
                    return m.group(1)       # 直接返回它的 IP（这就是管理 IP）
                if not fallback:            # 否则，如果备用还没填过
                    fallback = m.group(1)   # 把这个 IP 存为备用
    return fallback                         # 循环完都没遇到 vlanif100，返回第一个 VLANIF IP 兜底


def parse_config(text: str) -> ParsedConfig:
    """解析一段运行配置文本，返回结构化 ParsedConfig。"""
    text = text.strip()                     # 去掉整段文本首尾的空白
    interfaces = _extract_interfaces(text)  # 先解析接口块（后面多个字段都要用到）
    cfg = ParsedConfig(raw_text=text)       # 创建数据类对象，把原始文本存入 raw_text
    cfg.sysname = _extract_sysname(text)          # 提取设备名
    cfg.vlans = _extract_vlans(text)              # 提取 VLAN 列表
    cfg.local_users = _lines_starting_with(text, "local-user")           # 提取所有 local-user 开头的行
    cfg.snmp_communities = _lines_starting_with(text, "snmp-agent community")  # 提取 SNMP 社区串行
    cfg.interfaces = interfaces                    # 存入接口字典
    cfg.info_center = _lines_starting_with(text, "info-center")          # 提取日志中心配置行
    cfg.acl_lines = _lines_starting_with(text, "acl") + _lines_starting_with(text, "rule")  # 提取 ACL 行和 rule 行（+ 拼接两个列表）
    cfg.vty_lines = _lines_starting_with(text, "user-interface vty")     # 提取 vty 配置行
    cfg.mgmt_ips = _extract_mgmt_ips(interfaces)   # 提取所有 VLANIF IP
    cfg.mgmt_ip = _extract_mgmt_ip(interfaces)     # 提取管理 IP
    return cfg                                # 返回填好的 ParsedConfig 对象
