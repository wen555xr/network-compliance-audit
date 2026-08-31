#!/usr/bin/env python3
# 伪华为 SSH 服务器：用 paramiko 起一个「假的」SSH 服务器，模拟华为设备的命令行交互。
# Netmiko 来连它时，它按命令回显 + 回配置文本。这样不开 eNSP 也能端到端测试「SSH采集→解析→审计」链路。
# 这是项目的「测试替身」设计，面试问「怎么测试的」就讲它。

"""伪华为 SSH 服务器：回放 samples/ 下的设备配置，供 Netmiko 离线联调。

无需 eNSP，即可端到端验证「Netmiko SSH 采集 → 解析 → 审计」完整链路。

用法:
    py -3.12 mock/mock_device.py
另开终端:
    py -3.12 main.py --source mock -i inventory.mock.yaml
"""
from __future__ import annotations  # 兼容新旧 Python 版本的类型注解语法

import pathlib                      # 路径库
import socket                       # 底层网络套接字（建 TCP 服务）
import threading                    # 多线程（每来一个连接开一个线程处理）

import paramiko                     # SSH 协议库（这里当服务端用；netmiko 底层也是它，但当客户端）

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent  # 本文件在 compliance/mock/，向上两级 = compliance/
SAMPLES = BASE_DIR / "samples"      # 样例配置目录

# 统一 mock 登录凭据（审计对象是设备配置，而非 SSH 登录凭据本身）
MOCK_USERNAME = "admin"             # mock 统一用户名
MOCK_PASSWORD = "Admin@123"         # mock 统一密码

# (设备名, 监听端口)
DEVICES = [                         # 设备列表：每台设备名 + 一个监听端口（模拟 4 台独立设备）
    ("SW-Core", 10001),
    ("SW-Agg", 10002),
    ("SW-Acc1", 10003),
    ("SW-Acc2", 10004),
]

HOST_KEY = paramiko.RSAKey.generate(2048)  # 生成 2048 位 RSA 密钥，作为 SSH 服务器主机密钥（证明服务器身份）


class HuaweiMockServer(paramiko.ServerInterface):
    """极简 SSH 服务端：认证通过后回放对应设备的配置。"""

    def __init__(self, hostname: str, config_text: str):
        self.hostname = hostname      # 存设备名
        self.config_text = config_text  # 存要回放的配置文本

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED  # 通道类型是 session 就放行，其他类型拒绝

    def check_auth_password(self, username, password):
        if username == MOCK_USERNAME and password == MOCK_PASSWORD:  # 用户名密码都匹配
            return paramiko.AUTH_SUCCESSFUL   # 认证成功
        return paramiko.AUTH_FAILED           # 否则认证失败

    def check_channel_shell_request(self, channel):
        return True                   # 允许客户端请求 shell（命令行）

    def check_channel_pty_request(self, channel, term, width, height, pixelwidth, pixelheight, modes):
        return True                   # 允许客户端请求虚拟终端（pty），网络设备交互必须有它


def serve_device(hostname: str, port: int) -> None:
    config_text = (SAMPLES / f"{hostname}.cfg").read_text(encoding="utf-8")  # 读该设备对应的样例配置
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # 创建 TCP 套接字（AF_INET=IPv4，SOCK_STREAM=TCP）
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # 设置端口可重用，防止服务器重启时端口被占用
    sock.bind(("0.0.0.0", port))      # 绑定端口，0.0.0.0 = 监听所有网卡
    sock.listen(5)                    # 开始监听，最多排队 5 个连接
    print(f"[mock] {hostname} 监听 127.0.0.1:{port} (账号 {MOCK_USERNAME}/{MOCK_PASSWORD})")  # 打印启动信息

    while True:                       # 无限循环：服务器永不退出，一直等新连接
        client, _ = sock.accept()     # accept 阻塞等待，有客户端连上时返回连接 socket（地址用不到，用 _ 忽略）
        threading.Thread(target=_handle, args=(client, hostname, config_text), daemon=True).start()  # 开线程处理这个连接，主循环立刻回去等下一个


def _handle(client, hostname: str, config_text: str) -> None:
    transport = paramiko.Transport(client)   # 把 TCP socket 包装成 paramiko 的传输层对象
    transport.add_server_key(HOST_KEY)       # 告诉传输层用这把主机密钥
    transport.start_server(server=HuaweiMockServer(hostname, config_text))  # 启动服务端，paramiko 会调用上面类的回调方法完成握手认证
    channel = transport.accept(30)           # 等待客户端建立通道，超时 30 秒
    if channel is None:                      # 30 秒内没等到通道
        transport.close()                    # 关闭连接
        return                               # 退出函数

    channel.send(f"<{hostname}>")            # 发送登录提示符 <SW-Core>，Netmiko 靠它识别设备就绪
    buf = ""                                 # 缓冲区：网络数据可能分块到达，先攒着
    try:
        while True:                          # 主循环：一直处理客户端命令
            data = channel.recv(65535)       # 收数据，最多 65535 字节；recv 阻塞，没数据就一直等
            if not data:                     # 收到空数据 = 客户端断开
                break                        # 退出循环
            buf += data.decode("utf-8", errors="ignore")  # 字节解码成字符串，errors=ignore 忽略乱码字节不崩溃
            while "\n" in buf:               # 缓冲区里只要有换行，就按行处理（命令可能分多次到达）
                line, buf = buf.split("\n", 1)  # 按第一个换行切开：左边是完整一行命令，右边留回缓冲区
                line = line.strip()          # 去掉首尾空白
                # 回显命令（真实终端行为，供 Netmiko cmd_verify 匹配）
                if line:                     # 非空命令
                    channel.send("\r\n" + line)  # 回显命令（\r\n=回车换行）。不回显 Netmiko 会超时，这是踩过的坑
                if "display current-configuration" in line:  # 如果命令是要显示运行配置
                    channel.send("\r\n" + config_text)      # 把整段样例配置发回去（这就是采集结果）
                # 每条命令后回提示符（含空行，供 find_prompt 检测 ">"）
                channel.send("\r\n" + f"<{hostname}>")      # 回提示符 <SW-Core>，Netmiko 靠 ">" 识别命令执行完
    except Exception:                      # 任何异常（如客户端突然断开）
        pass                               # 都忽略，保持服务器健壮
    finally:
        transport.close()                  # 无论正常还是异常，最后都关闭传输层释放资源


def main() -> None:
    threads = [threading.Thread(target=serve_device, args=(name, port), daemon=True) for name, port in DEVICES]  # 列表推导式：为每台设备创建一个线程
    for t in threads:                      # 遍历线程列表
        t.start()                          # 逐个启动（4 个服务器同时跑）
    print("[mock] 伪华为 SSH 服务器已启动，Ctrl+C 退出。")  # 提示用户如何退出
    try:
        for t in threads:                  # 遍历线程
            t.join()                       # 等待线程结束，主线程在这里阻塞，让服务器一直运行
    except KeyboardInterrupt:              # 用户按 Ctrl+C
        print("\n[mock] 已退出。")         # 打印退出信息（而不是报错）


if __name__ == "__main__":    # 只有直接运行时才启动服务器
    main()                    # 调用主函数
