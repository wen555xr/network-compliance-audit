#!/usr/bin/env python3
"""伪华为 SSH 服务器：回放 samples/ 下的设备配置，供 Netmiko 离线联调。

无需 eNSP，即可端到端验证「Netmiko SSH 采集 → 解析 → 审计」完整链路。

用法:
    py -3.12 mock/mock_device.py
另开终端:
    py -3.12 main.py --source mock -i inventory.mock.yaml
"""
from __future__ import annotations

import pathlib
import socket
import threading

import paramiko

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent  # compliance/
SAMPLES = BASE_DIR / "samples"

# 统一 mock 登录凭据（审计对象是设备配置，而非 SSH 登录凭据本身）
MOCK_USERNAME = "admin"
MOCK_PASSWORD = "Admin@123"

# (设备名, 监听端口)
DEVICES = [
    ("SW-Core", 10001),
    ("SW-Agg", 10002),
    ("SW-Acc1", 10003),
    ("SW-Acc2", 10004),
]

HOST_KEY = paramiko.RSAKey.generate(2048)


class HuaweiMockServer(paramiko.ServerInterface):
    """极简 SSH 服务端：认证通过后回放对应设备的配置。"""

    def __init__(self, hostname: str, config_text: str):
        self.hostname = hostname
        self.config_text = config_text

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_auth_password(self, username, password):
        if username == MOCK_USERNAME and password == MOCK_PASSWORD:
            return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def check_channel_shell_request(self, channel):
        return True

    def check_channel_pty_request(self, channel, term, width, height, pixelwidth, pixelheight, modes):
        return True


def serve_device(hostname: str, port: int) -> None:
    config_text = (SAMPLES / f"{hostname}.cfg").read_text(encoding="utf-8")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    sock.listen(5)
    print(f"[mock] {hostname} 监听 127.0.0.1:{port} (账号 {MOCK_USERNAME}/{MOCK_PASSWORD})")

    while True:
        client, _ = sock.accept()
        threading.Thread(target=_handle, args=(client, hostname, config_text), daemon=True).start()


def _handle(client, hostname: str, config_text: str) -> None:
    transport = paramiko.Transport(client)
    transport.add_server_key(HOST_KEY)
    transport.start_server(server=HuaweiMockServer(hostname, config_text))
    channel = transport.accept(30)  # 等待 shell 通道建立
    if channel is None:
        transport.close()
        return

    channel.send(f"<{hostname}>")  # 登录后提示符
    buf = ""
    try:
        while True:
            data = channel.recv(65535)
            if not data:
                break
            buf += data.decode("utf-8", errors="ignore")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.strip()
                # 回显命令（真实终端行为，供 Netmiko cmd_verify 匹配）
                if line:
                    channel.send("\r\n" + line)
                if "display current-configuration" in line:
                    channel.send("\r\n" + config_text)
                # 每条命令后回提示符（含空行，供 find_prompt 检测 ">"）
                channel.send("\r\n" + f"<{hostname}>")
    except Exception:
        pass
    finally:
        transport.close()


def main() -> None:
    threads = [threading.Thread(target=serve_device, args=(name, port), daemon=True) for name, port in DEVICES]
    for t in threads:
        t.start()
    print("[mock] 伪华为 SSH 服务器已启动，Ctrl+C 退出。")
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\n[mock] 已退出。")


if __name__ == "__main__":
    main()
