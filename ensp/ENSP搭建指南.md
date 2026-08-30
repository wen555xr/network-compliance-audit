# eNSP 搭建指南（4 台 S5700 园区网络）

## 一、准备

- 已安装 eNSP V100R003C00SPC100；
- 已按 [06_部署与演示指南](../docs/06_部署与演示指南.md) 创建宿主机环回适配器（192.168.100.250/24）。

## 二、摆放设备

1. 打开 eNSP，从左侧「交换机」拖入 **4 台 S5700**，从「终端」拖入 **1 台 Cloud（云）**；
2. 重命名交换机为 `SW-Core`、`SW-Agg`、`SW-Acc1`、`SW-Acc2`。

## 三、连线

| 源设备/端口 | 目标设备/端口 | 说明 |
|---|---|---|
| SW-Core Gi0/0/1 | SW-Agg Gi0/0/1 | 核心↔汇聚 Trunk |
| SW-Agg Gi0/0/2 | SW-Acc1 Gi0/0/1 | 汇聚↔接入1 Trunk |
| SW-Agg Gi0/0/3 | SW-Acc2 Gi0/0/1 | 汇聚↔接入2 Trunk |
| SW-Core Gi0/0/24 | Cloud 端口1 | 管理通道（VLAN100） |

## 四、导入设备配置

1. 右键每台交换机 →「CLI」，进入命令行；
2. 进入系统视图（`system-view`）后，把 `ensp/configs/` 下对应设备的配置**逐段粘贴**执行；
3. 注意：
   - `rsa local-key-pair create` 为交互式命令，回车采用默认密钥长度即可；
   - 粘贴完成后执行 `return` 回到用户视图，再 `save` + `y` 保存配置。

## 五、配置 Cloud 桥接

1. 双击 Cloud 设备，打开配置；
2. 在「端口映射」中将一个端口绑定到宿主机环回适配器（Microsoft KM-TEST 环回适配器）；
3. 确保该端口已连到 SW-Core 的 Gi0/0/24。

## 六、验证连通性

宿主机命令行（Windows）：

```bash
ping 192.168.100.1     # SW-Core
ping 192.168.100.2     # SW-Agg
ping 192.168.100.11    # SW-Acc1
ping 192.168.100.12    # SW-Acc2
```

4 台设备均可达后，即可运行：

```bash
cd automation/compliance
py -3.12 main.py --source ensp -i inventory.yaml
```

## 七、SSH 登录口令说明

- 配置中 `local-user admin password irreversible-cipher <占位哈希>` 用于演示"不可逆加密"；
- 真实联调如需 SSH 登录，可先在设备上执行 `local-user admin password cipher <你的口令>`
  （display 会显示 `cipher`，规则 R03 会如实标记"可逆加密"不合规），并把 `inventory.yaml`
  中的 `password` 改为该口令；
- 生产环境建议用工具生成真实 `irreversible-cipher` 哈希，或通过 AAA 对接 RADIUS/TACACS+ 集中认证。
