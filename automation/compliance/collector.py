#!/usr/bin/env python3
# 采集器：整个项目里唯一与真实设备交互的部分。
# 用 Netmiko 库 SSH/Telnet 登录设备，执行 display current-configuration，把设备配置原文拿回来。

"""采集器：用 Netmiko 批量 SSH 登录，采集每台设备的运行配置。

返回 (设备名, 主机, 角色, 运行配置文本) 列表，供审计器消费。
"""
from __future__ import annotations  # 兼容新旧 Python 版本的类型注解语法

import pathlib  # 标准库：路径处理
import sys      # 标准库：向错误流打印信息

import yaml     # 第三方库：解析 YAML 设备清单
from netmiko import ConnectHandler  # 第三方库核心：netmiko 的「连接设备」函数


def load_devices(inventory_path: pathlib.Path) -> list[dict]:
    """读取设备清单（YAML）。"""
    with open(inventory_path, "r", encoding="utf-8") as f:  # 打开清单文件：只读、UTF-8
        data = yaml.safe_load(f)                            # 解析 YAML -> Python 数据
    return data["devices"]                                  # 取 devices 键，即设备列表（每台是一个字典）


def collect_device(device: dict) -> tuple[str, str, str, str]:
    """连接单台设备，采集 display current-configuration。"""
    params = dict(device)                       # 复制一份字典，避免修改原始清单
    name = params.pop("name")                   # 弹出并取走设备名（pop 会从字典里删除该键）
    role = params.pop("role", "")               # 弹出角色，没有就用空字符串
    host = params.get("host")                   # 取 IP 地址（只取值、不删除），等会打印用
    print(f"[{name}] 连接 {host}:{params.get('port', 22)} ...")  # 打印连接信息，端口默认 22
    with ConnectHandler(**params) as conn:      # **params 把字典展开成参数传给 ConnectHandler 并连接；with 保证用完自动断开
        running = conn.send_command("display current-configuration")  # 发送命令并等设备把配置全部返回
    print(f"[{name}] 采集完成，共 {len(running)} 字符")  # 打印采到的字符数，len() 求字符串长度
    return name, host, role, running            # 打包成四元组返回（名称、IP、角色、配置文本）


def collect_all(inventory_path: pathlib.Path) -> list[tuple[str, str, str, str]]:
    """批量采集清单内全部设备，单台失败不中断整体。"""
    devices = load_devices(inventory_path)      # 先读清单，拿到所有设备
    results: list[tuple[str, str, str, str]] = []  # 初始化结果列表（冒号后是类型注解，仅提示）
    ok, fail = 0, 0                             # 一行同时初始化两个计数器：成功数、失败数
    for dev in devices:                         # 遍历每台设备
        try:                                    # 尝试采集这台设备
            results.append(collect_device(dev)) # 成功：把结果加进列表
            ok += 1                             # 成功数 +1
        except Exception as exc:                # 任何异常（网络不通/密码错/协议不兼容）都进这里
            print(f"[{dev.get('name', dev.get('host'))}] 采集失败: {exc}", file=sys.stderr)  # 打印失败原因到错误流
            fail += 1                           # 失败数 +1，程序继续跑下一台（不中断整体）
    print(f"\n采集汇总: 成功 {ok} 台, 失败 {fail} 台")  # 打印最终汇总
    return results                              # 返回所有成功采集到的配置
