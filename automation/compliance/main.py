#!/usr/bin/env python3
"""编排入口：采集 → 解析 → 审计 → 报告 → 告警。

运行模式（--source）：
  files —— 读取 samples/ 目录下的样例配置（纯离线，无需 eNSP / SSH）
  mock  —— 连接本机伪 SSH 服务器（先运行 mock/mock_device.py）
  ensp  —— 连接真实 eNSP 设备（需 eNSP 拓扑 + Cloud 桥接 + 环回适配器）

用法示例：
  py -3.12 main.py --source files
  py -3.12 main.py --source mock -i inventory.mock.yaml
  py -3.12 main.py --source ensp -i inventory.yaml
"""
from __future__ import annotations

import argparse
import datetime
import pathlib
import sys

import yaml

try:  # 作为包导入
    from . import collector, report_excel, report_html, wechat_alert
    from .auditor import build_report
    from .parser import parse_config
    from .rules import load_rules
except ImportError:  # 直接以脚本方式运行
    import collector, report_excel, report_html, wechat_alert
    from auditor import build_report
    from parser import parse_config
    from rules import load_rules

BASE_DIR = pathlib.Path(__file__).resolve().parent
SAMPLES_DIR = BASE_DIR / "samples"
DEFAULT_CONFIG = BASE_DIR / "config.example.yaml"
USER_CONFIG = BASE_DIR / "config.yaml"

# 文件名 -> 设备角色（files 模式使用；与 inventory.yaml 保持一致）
ROLES = {"SW-Core": "核心层", "SW-Agg": "汇聚层", "SW-Acc1": "接入层", "SW-Acc2": "接入层"}


def load_config(path: pathlib.Path | None = None) -> dict:
    """加载配置：优先用户 config.yaml，否则用模板。"""
    p = pathlib.Path(path) if path else (USER_CONFIG if USER_CONFIG.exists() else DEFAULT_CONFIG)
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def collect_files() -> list[tuple[str, str, str, str]]:
    """files 模式：读取 samples/ 目录，返回 (名称, 管理IP, 角色, 文本)。"""
    results = []
    for f in sorted(SAMPLES_DIR.glob("*.cfg")):
        text = f.read_text(encoding="utf-8")
        name = f.stem
        parsed = parse_config(text)
        host = parsed.mgmt_ip or name
        role = ROLES.get(name, "—")
        results.append((name, host, role, text))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="网络设备配置合规性自动审计系统")
    parser.add_argument("--source", choices=["files", "mock", "ensp"], default="files",
                        help="数据源：files=本地样例（默认）/ mock=伪SSH服务器 / ensp=真实设备")
    parser.add_argument("-i", "--inventory", default=None, help="设备清单 YAML（mock/ensp 模式）")
    parser.add_argument("--config", default=None, help="配置文件（默认 config.yaml 或模板）")
    parser.add_argument("--rules", default=None, help="规则库 YAML（默认 rules.yaml）")
    parser.add_argument("--output-dir", default=None, help="报告输出目录（默认配置中的 report_dir）")
    parser.add_argument("--threshold", type=float, default=None, help="覆盖配置中的合规率阈值")
    args = parser.parse_args()

    cfg = load_config(args.config)
    threshold = args.threshold if args.threshold is not None else cfg.get("threshold", 90)
    webhook = cfg.get("wechat_webhook", "")
    out_dir = pathlib.Path(args.output_dir) if args.output_dir else BASE_DIR / cfg.get("report_dir", "reports")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) 采集数据
    print(f"[审计] 数据源 = {args.source}")
    if args.source == "files":
        device_configs = collect_files()
    else:
        inv = args.inventory or (BASE_DIR / ("inventory.mock.yaml" if args.source == "mock" else "inventory.yaml"))
        device_configs = collector.collect_all(pathlib.Path(inv))
    if not device_configs:
        print("[审计] 未采集到任何设备配置，退出。", file=sys.stderr)
        return 2

    # 2) 加载规则并审计
    rules = load_rules(pathlib.Path(args.rules) if args.rules else None)
    report = build_report(device_configs, rules, threshold)

    # 3) 生成报告
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    html_path = out_dir / f"report_{timestamp}.html"
    xlsx_path = out_dir / f"report_{timestamp}.xlsx"
    html_path.write_text(report_html.render(report), encoding="utf-8")
    report_excel.render(report, xlsx_path)
    print(f"[审计] HTML 报告 -> {html_path}")
    print(f"[审计] Excel 报告 -> {xlsx_path}")

    # 4) 阈值判断 → 告警
    print(f"\n[审计] 总体合规率 {report.overall_rate}%（阈值 {threshold}%）")
    if report.alert_triggered:
        wechat_alert.send(report, webhook)
    else:
        print("[审计] 合规率达标，未触发告警。")

    # 5) 控制台摘要
    print("\n设备合规率汇总：")
    for dev in report.devices:
        fails = ", ".join(r.rule.id for r in dev.failures) or "—"
        print(f"  {dev.name:8s} {dev.rate:5.1f}%  失败规则: {fails}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
