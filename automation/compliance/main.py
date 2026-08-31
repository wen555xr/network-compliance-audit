#!/usr/bin/env python3
# 注释约定：每行 # 开头的文字是对下一行代码（或同一行代码）的解释。
# 这个文件是整个程序的「总指挥」：从命令行接收参数 → 采集 → 审计 → 出报告 → 告警。

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
from __future__ import annotations  # 兼容新旧 Python 版本的类型注解语法（保险丝）

import argparse   # 标准库：解析命令行参数（--source、-i 等）
import datetime   # 标准库：获取当前时间（给报告文件名加时间戳）
import pathlib    # 标准库：现代化文件路径处理（比 os.path 更简洁）
import sys        # 标准库：系统相关，这里用来向「错误流」打印信息

import yaml       # 第三方库：解析 YAML 配置文件（config.yaml / rules.yaml）

try:              # 先尝试「作为包」导入（python -m 方式运行时走这里）
    from . import collector, report_excel, report_html, wechat_alert  # 相对导入：导入同级模块
    from .auditor import build_report    # 从 auditor 模块导入「构建报告」函数
    from .parser import parse_config     # 从 parser 模块导入「解析配置」函数
    from .rules import load_rules        # 从 rules 模块导入「加载规则」函数
except ImportError:                      # 相对导入失败时（直接 py main.py 运行会失败）
    import collector, report_excel, report_html, wechat_alert  # 退回普通导入
    from auditor import build_report     # 普通导入同样导入这几个函数
    from parser import parse_config
    from rules import load_rules

BASE_DIR = pathlib.Path(__file__).resolve().parent    # __file__=本文件路径，取它所在目录 = compliance/
SAMPLES_DIR = BASE_DIR / "samples"                    # 离线样例目录（files 模式读取 .cfg 用）
DEFAULT_CONFIG = BASE_DIR / "config.example.yaml"     # 配置模板文件（带默认值）
USER_CONFIG = BASE_DIR / "config.yaml"                # 用户真实配置文件（可能不存在）

# 文件名 -> 设备角色（files 模式使用；与 inventory.yaml 保持一致）
ROLES = {"SW-Core": "核心层", "SW-Agg": "汇聚层", "SW-Acc1": "接入层", "SW-Acc2": "接入层"}


def load_config(path: pathlib.Path | None = None) -> dict:
    """加载配置：优先用户 config.yaml，否则用模板。"""
    p = pathlib.Path(path) if path else (USER_CONFIG if USER_CONFIG.exists() else DEFAULT_CONFIG)  # 决定用哪个配置文件（命令行 > 用户配置 > 模板）
    with open(p, "r", encoding="utf-8") as f:     # 打开配置文件：只读、UTF-8 编码（支持中文）
        return yaml.safe_load(f)                  # 把 YAML 文本解析成 Python 字典并返回


def collect_files() -> list[tuple[str, str, str, str]]:
    """files 模式：读取 samples/ 目录，返回 (名称, 管理IP, 角色, 文本)。"""
    results = []                                  # 初始化结果列表
    for f in sorted(SAMPLES_DIR.glob("*.cfg")):   # 遍历目录下所有 .cfg 文件，sorted 保证顺序固定
        text = f.read_text(encoding="utf-8")      # 把文件内容整个读成字符串
        name = f.stem                             # 取文件名去后缀，如 SW-Core.cfg -> SW-Core
        parsed = parse_config(text)               # 用解析引擎把文本结构化（目的是拿管理IP）
        host = parsed.mgmt_ip or name             # 解析到管理IP就用它，没有就用设备名兜底
        role = ROLES.get(name, "—")               # 从字典查角色，查不到用占位符 —
        results.append((name, host, role, text))  # 打包成四元组，追加进结果列表
    return results                                # 返回全部样例配置


def main() -> int:
    parser = argparse.ArgumentParser(description="网络设备配置合规性自动审计系统")  # 创建命令行参数解析器
    parser.add_argument("--source", choices=["files", "mock", "ensp"], default="files",  # 数据源参数：三选一，默认 files
                        help="数据源：files=本地样例（默认）/ mock=伪SSH服务器 / ensp=真实设备")
    parser.add_argument("-i", "--inventory", default=None, help="设备清单 YAML（mock/ensp 模式）")   # 清单文件参数
    parser.add_argument("--config", default=None, help="配置文件（默认 config.yaml 或模板）")         # 配置文件参数
    parser.add_argument("--rules", default=None, help="规则库 YAML（默认 rules.yaml）")               # 规则库参数
    parser.add_argument("--output-dir", default=None, help="报告输出目录（默认配置中的 report_dir）") # 输出目录参数
    parser.add_argument("--threshold", type=float, default=None, help="覆盖配置中的合规率阈值")       # 阈值参数，type=float 转成小数
    args = parser.parse_args()                     # 真正读取命令行，结果存入 args 对象

    cfg = load_config(args.config)                 # 读取配置文件（阈值、webhook 等）
    threshold = args.threshold if args.threshold is not None else cfg.get("threshold", 90)  # 阈值：命令行优先，否则用配置，再默认 90
    webhook = cfg.get("wechat_webhook", "")        # 取企业微信 webhook 地址，没配就是空字符串
    out_dir = pathlib.Path(args.output_dir) if args.output_dir else BASE_DIR / cfg.get("report_dir", "reports")  # 报告输出目录
    out_dir.mkdir(parents=True, exist_ok=True)     # 创建输出目录：parents 建整条路径，exist_ok 已存在不报错

    # 1) 采集数据
    print(f"[审计] 数据源 = {args.source}")         # 在控制台打印当前数据源，方便观察进度
    if args.source == "files":                      # 离线模式
        device_configs = collect_files()            # 从本地样例目录读取
    else:                                           # mock / ensp 模式
        inv = args.inventory or (BASE_DIR / ("inventory.mock.yaml" if args.source == "mock" else "inventory.yaml"))  # 按模式自动选设备清单
        device_configs = collector.collect_all(pathlib.Path(inv))  # 调用采集器：批量登录设备拿配置
    if not device_configs:                          # 如果一台设备都没采到
        print("[审计] 未采集到任何设备配置，退出。", file=sys.stderr)  # 打印错误（stderr=错误流）
        return 2                                    # 返回退出码 2，表示「数据异常」

    # 2) 加载规则并审计
    rules = load_rules(pathlib.Path(args.rules) if args.rules else None)  # 加载 10 条合规规则，得到规则对象列表
    report = build_report(device_configs, rules, threshold)  # 逐设备逐规则审计，得到 AuditReport 报告对象

    # 3) 生成报告
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")  # 当前时间格式化成 20260831_013509 这种文件名后缀
    html_path = out_dir / f"report_{timestamp}.html"   # HTML 报告的完整路径
    xlsx_path = out_dir / f"report_{timestamp}.xlsx"   # Excel 报告的完整路径
    html_path.write_text(report_html.render(report), encoding="utf-8")  # 把报告渲染成 HTML 字符串并写入文件
    report_excel.render(report, xlsx_path)             # 渲染并保存 Excel 文件
    print(f"[审计] HTML 报告 -> {html_path}")          # 打印 HTML 报告位置
    print(f"[审计] Excel 报告 -> {xlsx_path}")         # 打印 Excel 报告位置

    # 4) 阈值判断 → 告警
    print(f"\n[审计] 总体合规率 {report.overall_rate}%（阈值 {threshold}%）")  # 打印总体合规率，\n 是换行
    if report.alert_triggered:                         # 如果总体合规率 < 阈值（触发条件）
        wechat_alert.send(report, webhook)             # 推送企业微信告警（没配 webhook 就打印内容）
    else:                                              # 否则（合规率达标）
        print("[审计] 合规率达标，未触发告警。")        # 打印未触发提示

    # 5) 控制台摘要
    print("\n设备合规率汇总：")                         # 打印汇总标题
    for dev in report.devices:                         # 遍历每台设备的审计结果
        fails = ", ".join(r.rule.id for r in dev.failures) or "—"  # 取所有失败规则ID，用逗号拼接；没有失败就显示 —
        print(f"  {dev.name:8s} {dev.rate:5.1f}%  失败规则: {fails}")  # 打印设备名、合规率（1位小数）、失败规则
    return 0                                           # 正常结束，退出码 0 = 成功


if __name__ == "__main__":    # 只有「直接运行本文件」时 __name__ 才等于 "__main__"，被 import 时不执行
    sys.exit(main())          # 执行主函数，并把返回的退出码交给操作系统
