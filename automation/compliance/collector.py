#!/usr/bin/env python3
"""采集器：用 Netmiko 批量 SSH 登录，采集每台设备的运行配置。

返回 (设备名, 主机, 角色, 运行配置文本) 列表，供审计器消费。
"""
from __future__ import annotations

import pathlib
import sys

import yaml
from netmiko import ConnectHandler


def load_devices(inventory_path: pathlib.Path) -> list[dict]:
    """读取设备清单（YAML）。"""
    with open(inventory_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["devices"]


def collect_device(device: dict) -> tuple[str, str, str, str]:
    """连接单台设备，采集 display current-configuration。"""
    params = dict(device)  # 拷贝，避免修改原清单
    name = params.pop("name")
    role = params.pop("role", "")
    host = params.get("host")
    print(f"[{name}] 连接 {host}:{params.get('port', 22)} ...")
    with ConnectHandler(**params) as conn:
        running = conn.send_command("display current-configuration")
    print(f"[{name}] 采集完成，共 {len(running)} 字符")
    return name, host, role, running


def collect_all(inventory_path: pathlib.Path) -> list[tuple[str, str, str, str]]:
    """批量采集清单内全部设备，单台失败不中断整体。"""
    devices = load_devices(inventory_path)
    results: list[tuple[str, str, str, str]] = []
    ok, fail = 0, 0
    for dev in devices:
        try:
            results.append(collect_device(dev))
            ok += 1
        except Exception as exc:  # noqa: BLE001 单台失败不影响其余设备
            print(f"[{dev.get('name', dev.get('host'))}] 采集失败: {exc}", file=sys.stderr)
            fail += 1
    print(f"\n采集汇总: 成功 {ok} 台, 失败 {fail} 台")
    return results
