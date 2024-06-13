# Shocking VRChat

一个小工具，通过接受 VRChat Avatar 的 OSC 消息，使用 Websocket 协议联动郊狼 DG-LAB 3.0 ，达到游戏中Avatar被别人/自己触摸，就会被郊狼电的效果。

> [!CAUTION]
> 您必须阅读并同意 [安全须知](doc/dglab/安全须知.md) ([Safety Precautions](doc/dglab/SafetyPrecautions.md) in English) 后才可以使用本工具！

## 使用方式

1. 前往 [本项目Release](https://github.com/VRChatNext/Shocking-VRChat/releases) 下载最新版本的 Shocking-VRChat 工具
2. 首次运行 exe 程序，将会在当前目录生成设置文件并退出。
3. 在配置文件 `settings-v*.*.yaml` 中填入 `avatar_params` 与工作模式（shock/distance）。
4. （可选）按需修改进阶配置文件 `settings-advanced-v*.*.yaml` 内容，参数含义请查看进阶配置文件参考。
4. 重新运行本程序，请确认是否弹出了 Windows 防火墙安全警告，如弹出请选择允许，以接受郊狼 APP 被控连接。
5. 启动 DG-LAB 3.0 APP，使用 Socket 控制功能扫描弹出窗口的二维码。
6. 享受 VRChat！

## 模型参数配置

- 程序内部流转处理的参数为 0 ~ 1 之间的 float
- 支持输入的参数类型为 float、int、bool
    - float，int ：小于 0 会被视为 0，大于 1 会被视为 1
    - bool ：True 为 1，False 为 0
- 其他参数类型会报错

## 工作模式解释

### distance 距离模式

- 根据与触发区域中心的距离控制波形强度
- 越接近中心，强度越强
- 距离模式下 trigger_range 的含义
    - 当接收到的 OSC 数据大于 bottom 时，开始线性变化波形强度，上界为 top
    - 当数据达到或超过 top 参数后，以最大强度输出
    - 建议 bottom 设置为 0 或较小数字
    - 建议 top 设置为 1.0 以获得最大动态范围

### shock 电击模式

- 触发后电击固定时长（默认：2秒）
- 如果一直被触碰，会电击到触摸离开后的固定时长
- 电击模式下 trigger_range 的含义
    - 当接收到的 OSC 数据大于 bottom 时，触发电击
    - top 参数在 shock 模式被忽略


## 基础配置文件参考

配置文件格式 `yaml`， 当前配置文件版本: `v0.2` 。

```yaml
dglab3:
  channel_a:
    avatar_params:  
    # 此处填写 OSC 监听参数组，可以使用通配符 * 匹配任意字符串，注意保留正确缩进与前缀的 “- ” 
    # 可参考 https://python-osc.readthedocs.io/en/latest/dispatcher.html#mapping 
    - /avatar/parameters/pcs/contact/enterPass
    - /avatar/parameters/Shock/wildcard/*
    mode: distance # 工作模式，此处为距离模式
    strength_limit: 100 # 强度限制，程序将取该强度与主机设置的强度中最大的一个
  channel_b:
    avatar_params:
    - /avatar/parameters/lms-penis-proximityA*
    - /avatar/parameters/ShockB2/some/param
    mode: shock # 工作模式，此处为电击模式
    strength_limit: 100
version: v0.2
```

## 常见参数

> 本部分请协助补充描述与解释。

- float
  - /avatar/parameters/pcs/contact/enterPass
    - 最常用，位于pcs触发入口处，可自动切换跟随被触发的位置
  - /avatar/parameters/pcs/contact/proximityA
  - /avatar/parameters/pcs/contact/proximityB
  - /avatar/parameters/pcs/contact/slide
  - /avatar/parameters/pcs/smash-intensity
  - /avatar/parameters/pcs/sps/pussy
    - 如果需要仅通过指定位置触发，可尝试 pcs/sps 下的参数，不会跟随auto mode位置变化
  - /avatar/parameters/pcs/sps/ass
  - /avatar/parameters/pcs/sps/boobs
  - /avatar/parameters/pcs/sps/mouth
  - /avatar/parameters/pcs/sps/penis*
  - /avatar/parameters/lms-penis-proximityA*
    - 通过 LMS 触发可以使用的参数
- bool
  - /avatar/parameters/pcs/smash-intense
  - /avatar/parameters/pcs/contact/in
  - /avatar/parameters/pcs/contact/out
  - /avatar/parameters/pcs/contact/hit
  - /avatar/parameters/lms-stroke-in
  - /avatar/parameters/lms-stroke-out*
  - /avatar/parameters/lms-stroke-smash

## 进阶配置文件参考

```yaml
SERVER_IP: null # 为 null 时程序将尝试自动获取本机 IP，如果获取错误，请将null修改为正确的 IP 地址（手机可以访问到电脑的 IP ，通常为有线网络或 WiFi ）
dglab3:
  channel_a: # 通道 A 配置
    mode_config:   # 工作模式配置
      distance:
      # 该项目下的参数仅对 distance 距离模式生效
        freq_ms: 10 
        # 生成波形的频率（间隔毫秒），推荐 10 
        # 详细请参考 DG-LAB-OPENSOURCE 蓝牙协议V3 的波形部分
      shock:
      # 该项目下的参数仅对 shock 电击模式生效
        duration: 2
        # 触发后的电击时长
        wave: '["0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464"]'
        # 电击波形
      trigger_range:
      # 触发阈值设置，对所有模式生效，范围 0 ~ 1
        bottom: 0.0 # OSC 回报参数触发下界（低于视为 0%）
        top: 0.8    # OSC 回报参数触发上界（超过视为 100%）
  channel_b: # 通道 B 配置，参数设置与 A 通道相同
    mode_config:
      distance:
        freq_ms: 10
      shock:
        duration: 2
        wave: '["0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464","0A0A0A0A64646464"]'
      trigger_range:
        bottom: 0.1
        top: 0.8
general: # 通用配置
  auto_open_qr_web_page: true # 程序启动时自动开启扫码 Web 页面
  local_ip_detect:  # 探测本地 IP 时使用的服务器地址
    host: 223.5.5.5 # 默认为 AliDNS 如果在中国大陆以外使用，请适当修改
    port: 80
log_level: INFO # 日志等级，诊断问题时可以改为 DEBUG
osc: # OSC 服务配置
  listen_host: 127.0.0.1 # 如果 VRChat 在其他主机运行，请改为 0.0.0.0，并给 VRChat 正确配置 osc 启动命令行参数。
  listen_port: 9001
version: v0.2 # 配置文件版本
web_server: # Web 服务器配置
  listen_host: 127.0.0.1 # 如果需要从其他主机打开网页扫码，请改为 0.0.0.0
  listen_port: 8800
ws: # Websocket 服务配置
  listen_host: 0.0.0.0
  listen_port: 28846
  master_uuid: 6da2fd3b-a6e5-4af4-afc1-96bfd2e9e95c # 首次启动自动随机生成

```

## FAQ

### 是否有逃生通道

- 有，可以按一下郊狼的任意一侧肩键按钮，此时 A B 通道强度会被设置为 0。
- 当程序检测到通道强度被用户主动设置为 0 后，将不再自动跟随强度上限。
- 还原需要手动在手机上点击 "+" 键，将通道强度 +1 ，即恢复自动跟随。

### 应该如何设置上限

- 建议通过郊狼 APP 内的被控设置进行调整，程序将跟随。
- `settings-v*.*.yaml` 基础配置文件内的 `strength_limit` 也会限制强度上限，如果超过默认值 100，需要调整该参数。
- 为保证强度自动跟随自动运行，请确认郊狼APP内 菜单-被控设置 中，两个通道的强度上限初始值（最小值）大于等于 1。

### 想用一个参数同时触发两个通道

- 请将需要使用的参数，例如 `/avatar/parameters/pcs/contact/enterPass` 同时复制进基础配置文件 `settings-v*.*.yaml` 内 `channel_a` 和 `channel_b` 的 `avatar_params` 列表内，请注意缩进与行首的 `-` 。

### 控制台内有波形输出，但是没有强度或强度显著变小

- 试试看按一下按钮将郊狼强度设置为 0 之后，再手动点击屏幕 +1 恢复正常模式。

### 程序看起来收不到 OSC 数据

1. **如果你有面捕**，请检查 Steam 中 VRChat 的启动命令行参数，是否有类似 `--osc=9000:127.0.0.1:9001` 的配置，如有，请修改进阶配置文件，`osc` `listen_port` 的值为最后一个冒号后的值，如 9001。
2. Action Menu 中选择 Options > OSC > Reset Config 重置 OSC 配置
3. 如果之前是正常使用的，但忽然收不到，重启电脑可以解决问题，似乎是 VRChat 的 Bug。

### 为什么强度一直是最大可用值

- 程序运行后会自动跟随郊狼APP内设置的上限并与基础配置文件内 `strength_limit` 取一最小值设置为最大强度。
- 程序使用波形信号控制强度，即便您看到的强度达到了上限，但实际被触发的强度是由触发实体（例如他人的手）距离触发区域（例如 enterPass）中心点的距离决定，线性提升。
- 如需修改判定上下界请用 `trigger_range` 配置。

### APP 扫码无法连接/连接超时

1. 请确认手机和电脑在同一个网络内，例如手机不可以使用流量。
2. 请检查二维码网页上显示的IP地址，例如 ws://192.168.1.2:28846/ ，该IP是否为你的网卡IP。
3. 如果IP错误，请在进阶配置文件中 `SERVER_IP:` 填写正确的 IP 地址后重启程序再试。
4. 请确认 Windows 防火墙是否允许本程序访问网络（接受传入连接）。

### 程序版本更新后配置文件如何继承？

- 程序版本与配置文件版本分离，如果仅仅是程序版本更新，配置文件无需改动即可继承使用。
- 如果配置文件版本发生更新，原配置不会被覆盖，请观察新配置文件的变更位置，将需要保留的参数填入新配置文件。

### OSC 能收到其他参数但收不到模型的参数

- 如果你的模型是刚刚修改过的，有可能是 VRChat 的 OSC 配置文件没有更新，请尝试在 Action Menu 中选择 Options > OSC > Reset Config 重置 OSC 配置。

## Credits

感谢 [DG-LAB-OPENSOURCE](https://github.com/DG-LAB-OPENSOURCE/DG-LAB-OPENSOURCE) ，赞美 DG-LAB 的开源精神！

-----

## 安全须知

**为了您能健康地享受产品带来的乐趣，请在使用前确保已阅读并理解本安全须知的全部内容。**  
**错误使用本产品可能对您或者他人造成伤害，由此产生的责任将由您自行承担。**

感谢您选择DG-LAB系列产品，用户的安全始终是我们的第一要务。  
本产品为情趣用品，请保证在**安全，清醒，自愿**的情况下使用。并将其放置于未成年人接触不到的地方。

本安全须知大约需要**2分钟**阅读。

### **下列人群严禁使用本产品：**

1. **佩戴心脏起搏器，或体内有电子/金属植入物的人群**（可能影响起搏器或植入物的正常功能）
2. **癫痫，哮喘、心脏病、血栓及其他心脑血管疾病患者**（感官刺激可能诱发或加重症状）
3. **皮肤敏感，皮炎及其他皮肤疾病患者**（可能使皮肤疾病症状加重）
4. **有出血倾向性疾病的患者**(电刺激会使局部毛细血管扩张从而可能诱发出血)
5. 未成年人、孕妇、知觉异常及无表达意识能力的人群
6. 肢体运动障碍及其他**无法及时操作产品**的人群（可能在感到不适时无法及时停止输出）
7. 其他正在接受治疗或身体不适的人群。

### **下列部位严禁使用本产品：**

1. 严禁将电极置于胸部；**绝对禁止将两电极分别置于心脏投影区前后、左右**或任何可能使电流流经心脏的位置；
2. 严禁将电极置于**头部、面部，眼部、口腔、颈部**及颈动脉窦附近；
3. 严禁将电极置于**皮肤破损或水肿处，关节扭伤挫伤处，肌肉拉伤处，炎症/感染病灶处，或未完全愈合的伤口**附近。

### **其他注意事项：**

1. **严禁在同一部位连续使用30分钟以上，**长时间使用可能导致局部红肿或知觉减弱等其他损伤。
2. 严禁在输出状态下移动电极，**在移动电极或更换电极时，必须先停止输出，**避免接触面积变化导致刺痛或灼伤。
3. 严禁在驾驶或操作机器等危险情况下使用，**以避免受脉冲影响而失去控制。**
4. 严禁将电极导线插入产品主机导线插孔之外的地方（如电源插座等）。
5. 严禁在具有易燃易爆物质的场合使用。
6. **请勿同时使用多台产品。**
7. 请勿私自拆卸或修理产品主机，可能会引起故障或意料外的输出。
8. 请勿在浴室等潮湿环境使用。
9. 在使用过程中，**请勿使两电极互相接触短路，**可能导致感受减弱，接触部位刺痛或灼伤，或损坏设备。
10. 电极使用时必须与皮肤充分紧密接触，如果电极与皮肤的接触面积过小，可能导致刺痛或灼伤。如果电极与皮肤的接触面积过大，则可能导致电感微弱。
11. 产品内含锂电池，禁止拆解，装机，挤压或投入火中。若产品出现**故障或异常发热**，请勿继续使用。

### **重要使用提示：**

1. 由于不同部位对于电流耐受程度存在差异，且一些材质的电极可能使少部分用户出现过敏现象。**当您在一个部位首次使用本产品时，或使用一款新的电极时，请先试用10分钟**之后等待一段时间，确认使用部位无异常后方可继续使用。
2. 受人体生理特性的影响，身体对于脉冲刺激的感受会逐渐变弱，因此，在使用过程中可能需要逐渐增加强度来保持相对稳定的体感强度。  
这有可能导致**在同一部位过长时间使用本产品后，真实刺激强度已经逐渐超过可承受的范围但是却没有被感觉到，**从而造成损伤。  
虽然本产品的最高输出严格低于安全标准的限制（r.m.s < 50ma，500Ω），但长时间使用仍然有可能造成损伤。因此，请在使用过程中**严格遵守连续使用时长的限制**。在同一部位连续使用**30分钟**后请休息一段时间，让感受灵敏度恢复到正常水平。
3. 连续不断的高频刺激会使使用部位快速适应，建议使用**频率不断变化且间歇休息**的波形，从而获得更好的使用体验。以每小段波形刺激时间1-10秒，休息1-10秒为宜。
