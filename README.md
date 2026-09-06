# Shocking VRChat

[English version](README_en.md)

一个小工具，通过接受 VRChat Avatar 的 OSC 消息，使用 WebSocket 协议联动郊狼 DG-LAB 3.0，达到游戏中 Avatar 被别人/自己触摸就会被郊狼电的效果。

我们的 VRChat 群组：[ShockingVRC https://vrc.group/SHOCK.2911](https://vrc.group/SHOCK.2911)

> [!CAUTION]
> 您必须阅读并同意 [安全须知](doc/dglab/安全须知.md) ([Safety Precautions](doc/dglab/SafetyPrecautions.md) in English) 后才可以使用本工具！

## 功能概览

- 🎮 **多种工作模式**：距离、电击、触摸、Combo 组合
- 📈 **自定义强度曲线**：可视化编辑 OSC 参数到输出强度的映射
- 🧪 **波形预设系统**：导入/预览 DG-LAB 社区波形，实时波形测试
- 🔄 **实时 WebSocket 推送**：波形可视化、设备状态实时同步
- ⚙️ **Web 管理界面**：所有配置通过浏览器完成，无需手动编辑文件
- 🔁 **热重载**：修改配置后自动生效，设备连接不断开
- 📦 **自动更新**：一键检测并下载 GitHub 最新版本

## 快速开始

1. 前往 [Releases](https://github.com/VRChatNext/Shocking-VRChat/releases) 下载最新版本
2. 解压并运行 `shocking_vrchat.exe`，浏览器将自动打开管理页面
3. 在管理页面的「参数管理」中添加 OSC 参数（或使用初始设置向导）
4. 在「强度设置」中调整强度上限（初始默认值很低，请逐步提高）
5. 启动 DG-LAB 3.0 APP，使用「Socket 控制」功能扫描页面上的二维码
6. 确认 Windows 防火墙弹窗中选择「允许」
7. 进入 VRChat，享受！

## 工作模式

### 📏 距离模式 (distance)

- 根据与触发区域中心的距离**线性控制**波形强度
- 越接近中心，强度越强
- 支持自定义强度曲线（非线性映射）
- 支持波形预设纹理

### ⚡ 电击模式 (shock)

- 触发后电击固定时长（默认 2 秒）
- 持续触碰时延续到触碰离开后的固定时长
- 支持自定义电击波形

### 🤚 触摸模式 (touch)

- 根据触摸动作的**变化率**控制波形强度
- 支持多阶导数：速度（1阶）、加速度（2阶）、急动度（3阶）
- 适合持续抚摸场景

### 🔀 Combo 模式

- 短触发 → 电击（一激灵）
- 持续触摸 → 触摸模式（柔和）
- 可配置切换时长

## Web 管理界面

程序启动后自动打开 `http://127.0.0.1:8800`，所有功能均可在网页中操作：

| 页面 | 功能 |
|------|------|
| Dashboard | 实时波形、设备状态、OSC 事件监控 |
| 参数管理 | 添加/编辑 OSC 参数、分配工作模式 |
| 强度设置 | 调节强度上限（自动保存、±1 微调） |
| 模式 > 电击 | 电击时长、波形预设、触发阈值 |
| 模式 > 距离 | 波形参数、触发阈值、强度曲线编辑 |
| 模式 > 触摸 | 导数阶数、波形参数 |
| 模式 > Combo | 组合逻辑配置 |
| 波形测试 | A/B 通道实时波形测试 |
| 设置 | 端口配置、配置导入/导出、软件更新 |

## 配置文件

程序使用两个 YAML 配置文件（首次运行自动生成）：

- `settings-v0.2.yaml` — 基础配置（参数、模式、强度上限）
- `settings-advanced-v0.2.yaml` — 进阶配置（端口、日志、mode_config）

> 推荐通过 Web 界面管理配置，无需手动编辑文件。配置修改后自动热重载。

### 基础配置示例

```yaml
dglab3:
  channel_a:
    avatar_params:
    - /avatar/parameters/pcs/contact/enterPass
    - /avatar/parameters/Shock/*
    mode: distance
    strength_limit: 100
  channel_b:
    avatar_params:
    - /avatar/parameters/lms-penis-proximityA*
    mode: shock
    strength_limit: 100
version: v0.2
```

### 进阶配置示例

```yaml
SERVER_IP: null  # null = 自动检测，或手动填写 IP
dglab3:
  channel_a:
    mode_config:
      distance:
        freq_ms: 10
        wave_preset: null       # 波形预设名称
        wave_scale: 1.0         # 波形强度系数
        texture_floor: 0.0      # 底噪（0=允许静默）
      shock:
        duration: 2
        wave_preset: null
        wave_scale: 1.0
      touch:
        wave_preset: null
        wave_scale: 1.0
        n_derivative: 1         # 导数阶数
      combo:
        enabled: false
        shock_threshold: 0.9
        shock_hold_ms: 200
      trigger_range:
        bottom: 0.0
        top: 0.8
  channel_b:
    mode_config:
      # 与 channel_a 结构相同
log_level: INFO
osc:
  listen_host: 127.0.0.1
  listen_port: 9001
web_server:
  listen_host: 127.0.0.1
  listen_port: 8800
ws:
  listen_host: 0.0.0.0
  listen_port: 28846
  master_uuid: (自动生成)
version: v0.2
```

## 常见 OSC 参数

- **PCS (Poiyomi Contact System)**
  - `/avatar/parameters/pcs/contact/enterPass` — 最常用，触发入口
  - `/avatar/parameters/pcs/sps/pussy|ass|boobs|mouth` — 指定部位
  - `/avatar/parameters/pcs/smash-intensity` — 碰撞强度
- **LMS**
  - `/avatar/parameters/lms-penis-proximityA*` — LMS 1.2
  - `/avatar/parameters/lms/contact/proximity` — LMS 1.3
- 支持通配符 `*`，如 `/avatar/parameters/Shock/*`
- 支持 float (0-1)、int、bool 类型

## 自动更新

程序内置自动更新功能：

1. 打开设置页面，自动检查 GitHub Releases 最新版本
2. 如有更新，点击「下载并更新」
3. 程序自动下载、替换文件并重启

配置文件和波形预设不会被覆盖。

## Build

CI 使用 GitHub Actions 自动构建（push `v*` tag 触发），产出两个版本：

| 产物 | 说明 |
|------|------|
| `shocking_vrchat_windows_x64.zip` | PyInstaller 目录版（推荐） |
| `shocking_vrchat_windows_x64_onefile.zip` | Nuitka 单文件版 |

本地构建：

```cmd
pip install -r requirements.txt pyinstaller
pyinstaller --clean -y shocking_vrchat.spec
```

产物在 `dist/shocking_vrchat/` 目录。

文件结构（全部外部，不编译进 exe）：
```
shocking_vrchat.exe
wave_presets/*.json      ← 波形预设
dg-lab/*.pulse           ← 原始 pulse 源文件
settings-v0.2.yaml       ← 基础配置（运行时生成）
settings-advanced-v0.2.yaml ← 进阶配置
```

## FAQ

### 是否有逃生通道

有。按一下郊狼的任意一侧肩键按钮，A/B 通道强度会被设置为 0。程序检测到后将不再自动跟随强度上限。还原需要在手机上点击 "+" 键 +1 即可恢复。

### APP 扫码无法连接

1. 确认手机和电脑在同一网络（手机不能用流量）
2. 检查二维码页面显示的 IP 是否正确
3. IP 错误时在进阶配置 `SERVER_IP` 手动填写
4. 确认 Windows 防火墙允许本程序

### OSC 端口冲突（面捕软件）

使用 [osc-repeater](https://github.com/CyCoreSystems/osc-repeater) 分发 OSC 数据到多个程序。详细步骤见 [Wiki](https://github.com/VRChatNext/Shocking-VRChat/wiki) 或进阶配置文件中的说明。

### 收不到 OSC 数据

1. VRChat Action Menu > Options > OSC > Reset Config
2. 检查 VRChat 启动参数中的 OSC 端口是否匹配
3. 重启电脑（VRChat 已知 Bug）
4. 退出已知冲突程序（如酷狗音乐占用 UDP 9000）

### 强度工作原理

```
实际输出 = min(程序强度设置, 郊狼APP被控上限) × 波形纹理(0-100%)
```

程序通过波形信号控制实际体感，即便通道强度显示为上限值，实际触发强度由 OSC 距离值决定。

## 波形文件声明

本仓库 `dg-lab/` 和 `wave_presets/` 目录中的波形预设文件仅供学习与技术研究使用。数据来源于 DG-LAB 社区公开分享，本项目不主张所有权。如有侵权请通过 Issue 联系，将第一时间删除。

## Credits

- [DG-LAB-OPENSOURCE](https://github.com/DG-LAB-OPENSOURCE/DG-LAB-OPENSOURCE) — 赞美 DG-LAB 的开源精神！
- 常见参数部分感谢：ichiAkagi

---

## 安全须知

**为了您能健康地享受产品带来的乐趣，请在使用前确保已阅读并理解本安全须知的全部内容。**
**错误使用本产品可能对您或者他人造成伤害，由此产生的责任将由您自行承担。**

本产品为情趣用品，请保证在**安全、清醒、自愿**的情况下使用，并将其放置于未成年人接触不到的地方。

### 严禁使用人群

1. 佩戴心脏起搏器，或体内有电子/金属植入物
2. 癫痫、哮喘、心脏病、血栓及其他心脑血管疾病患者
3. 皮肤敏感、皮炎及其他皮肤疾病患者
4. 有出血倾向性疾病的患者
5. 未成年人、孕妇、知觉异常及无表达意识能力的人群
6. 无法及时操作产品的人群

### 严禁使用部位

1. 胸部、心脏投影区前后左右
2. 头部、面部、眼部、口腔、颈部及颈动脉窦附近
3. 皮肤破损、水肿、扭伤、拉伤、炎症/感染病灶处

### 重要提示

- **同一部位连续使用不超过 30 分钟**
- 移动/更换电极前必须先停止输出
- 严禁在驾驶或操作机器时使用
- 建议使用频率变化且间歇休息的波形
