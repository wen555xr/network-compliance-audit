# 网络设备配置合规性自动审计系统

> 角色：网络自动化运维 / 配置合规审计　|　场景：企业园区网络
> 工具：Huawei eNSP · Python Netmiko · 正则解析引擎 · openpyxl · 企业微信机器人

本项目基于华为 eNSP 模拟平台，搭建一个「**核心 — 汇聚 — 接入**」三层企业园区网络作为审计目标，
使用 Python Netmiko 批量 SSH 登录采集每台交换机的运行配置，经正则解析引擎逐项审计
（SNMP 安全 / AAA 认证 / 高危服务端口 / 日志管理 / 访问控制等 10 项规则），
输出 **HTML + Excel** 双格式审计报告，并在**总体合规率低于阈值**时自动触发**企业微信机器人告警**。

## 交付内容总览

| 阶段 | 交付物 | 位置 |
|---|---|---|
| 需求分析 | 项目背景与需求 | [docs/01_项目背景与需求.md](docs/01_项目背景与需求.md) |
| 组网规划 | 三层拓扑、VLAN/IP、管理通道设计 | [docs/02_网络拓扑与IP规划.md](docs/02_网络拓扑与IP规划.md) |
| 仿真搭建 | eNSP 搭建指南 + 4 台设备配置 + 拓扑图 | [ensp/](ensp/) |
| 合规基线 | 设备配置与合规基线手册 | [docs/03_设备配置与合规基线手册.md](docs/03_设备配置与合规基线手册.md) |
| 规则库 | 10 项合规规则说明 | [docs/04_合规规则库说明.md](docs/04_合规规则库说明.md) |
| 系统设计 | 审计系统架构与数据流 | [docs/05_自动化审计系统设计.md](docs/05_自动化审计系统设计.md) |
| 部署演示 | 依赖安装、联调与演示步骤 | [docs/06_部署与演示指南.md](docs/06_部署与演示指南.md) |

## 目录结构

```
网络设备配置合规审计系统/
├── README.md                 # 本文件
├── docs/                     # 6 篇项目文档
├── ensp/                     # eNSP 仿真（拓扑图 + 4 台设备配置 + 搭建指南）
├── automation/compliance/    # 审计系统核心包
│   ├── main.py               # 编排入口（采集→解析→审计→报告→告警）
│   ├── collector.py          # Netmiko 批量 SSH 采集
│   ├── parser.py             # 正则解析引擎
│   ├── rules.yaml            # 10 项合规规则（数据驱动）
│   ├── rules.py              # 规则加载 + 规则引擎
│   ├── auditor.py            # 逐设备逐规则比对与评分
│   ├── report_html.py        # HTML 报告
│   ├── report_excel.py       # Excel 报告（openpyxl）
│   ├── wechat_alert.py       # 企业微信机器人告警
│   ├── config.example.yaml   # 阈值/告警配置模板
│   ├── inventory.yaml        # 真实 eNSP 设备清单（SSH）
│   ├── inventory.mock.yaml   # 本机 mock 服务器清单
│   ├── samples/              # 4 台设备 display 输出（离线验证）
│   └── mock/mock_device.py   # 伪华为 SSH 服务器
└── sample_output/            # 演示用示例报告（HTML + Excel）
```

## 网络拓扑（4 台 S5700）

```
                 [ 宿主机环回适配器 192.168.100.250 ]
                            │ 桥接
                        [ Cloud 云 ]
                            │ Gi0/0/24 (VLAN100)
                      [ SW-Core 核心层 ]        Vlanif100 = 192.168.100.1
                            │ Gi0/0/1 Trunk (10/20/30/100)
                      [ SW-Agg 汇聚层 ]         Vlanif100 = 192.168.100.2
                 ┌──────────┴──────────┐
        Gi0/0/2 Trunk(10/100)   Gi0/0/3 Trunk(20/30/100)
      [ SW-Acc1 接入层 ]        [ SW-Acc2 接入层 ]
      Vlanif100=192.168.100.11  Vlanif100=192.168.100.12
      Gi0/0/2~5 接入 VLAN10/20  Gi0/0/2~4 接入 VLAN20/30
```

- 管理 VLAN：**VLAN 100**（192.168.100.0/24），全部交换机管理 IP 通过 **VLANIF 虚拟接口**配置
- 业务 VLAN：VLAN10 办公 / VLAN20 研发 / VLAN30 访客与监控
- 宿主机经 Cloud 桥接进 VLAN100，可达 4 台设备的 Vlanif100，作为 Netmiko 的 SSH 连接目标

## 核心能力

- **批量自动化采集**：Netmiko 多设备 SSH 登录，`display current-configuration` 一键采集
- **正则解析引擎**：把运行配置结构化为 `ParsedConfig`（sysname/VLAN/接口/AAA/SNMP/日志/ACL）
- **数据驱动规则库**：10 项合规规则存于 `rules.yaml`，增删规则不改引擎
- **双格式报告**：自包含 HTML（合规矩阵 + 修复建议）+ Excel（汇总/明细/不合规清单三 Sheet）
- **阈值联动告警**：总体合规率低于阈值时，企业微信机器人自动推送 Markdown 告警

## 快速开始

### 1. 纯离线一键验证（无需 eNSP / SSH）

```bash
cd automation/compliance
py -3.12 -m pip install -r requirements.txt
py -3.12 main.py --source files
```

脚本读取 `samples/` 下的样例配置，产出 `reports/report_*.html` 与 `reports/report_*.xlsx`，
并在控制台打印 4 台设备合规率（预期 100% / 70% / 60% / 30%，总体 65% < 阈值 90% 触发告警）。

### 2. mock 模式（验证 Netmiko SSH 采集链路）

```bash
# 终端 A：启动伪华为 SSH 服务器
py -3.12 mock/mock_device.py

# 终端 B：通过 SSH 采集并审计
py -3.12 main.py --source mock -i inventory.mock.yaml
```

### 3. eNSP 真实联调（需图形界面 + 环回适配器）

按 [ensp/ENSP搭建指南.md](ensp/ENSP搭建指南.md) 搭拓扑、导入配置、配置 Cloud 桥接，
再执行：

```bash
py -3.12 main.py --source ensp -i inventory.yaml
```

> 提示：SW-Acc2 故意未启用 SSH（只开 Telnet），清单已将其设为 `huawei_telnet`/端口 23 采集。
> 若要手动 SSH 登录设备，eNSP 老版本 VRP 只支持旧算法，Windows 自带 ssh 需加 legacy 参数：
> `ssh -o KexAlgorithms=+diffie-hellman-group1-sha1 -o HostKeyAlgorithms=+ssh-rsa -o Ciphers=+aes128-cbc,3des-cbc admin@192.168.100.1`

## 真机联调实测结果（eNSP）

按搭建指南在 eNSP 部署 4 台 S5700 后，实测 `--source ensp` 采集审计结果如下：

| 设备 | 角色 | 管理 IP | 采集方式 | 合规率 | 违规规则 |
|---|---|---|---|---|---|
| SW-Core | 核心层 | 192.168.100.1 | SSH | 80.0% | R03, R09 |
| SW-Agg | 汇聚层 | 192.168.100.2 | SSH | 60.0% | R03, R08, R09, R10 |
| SW-Acc1 | 接入层 | 192.168.100.11 | SSH | 70.0% | R03, R08, R09 |
| SW-Acc2 | 接入层 | 192.168.100.12 | Telnet | 40.0% | R01, R03, R04, R05, R08, R09 |

- 总体合规率 **62.5%**（阈值 90%）→ 触发企业微信告警
- 4 台设备全部采集成功：**3 台 SSH + 1 台 Telnet**（SW-Acc2 故意未启用 SSH、只开 Telnet 明文，其本身即为违规项）
- 真实结果与离线样例略有差异，源于 VRP 不打印默认命令（如 `info-center timestamp log date`、`telnet server enable`），审计按「显式配置」从严判定

## 环境依赖

| 依赖 | 说明 |
|---|---|
| Python 3.12 | `py -3.12` |
| Netmiko / Paramiko / PyYAML | SSH 采集与设备清单 |
| openpyxl | Excel 报告 |
| requests | 企业微信告警推送 |
| Huawei eNSP | 网络仿真（仅 `--source ensp` 需要） |

安装：`py -3.12 -m pip install -r automation/compliance/requirements.txt`
