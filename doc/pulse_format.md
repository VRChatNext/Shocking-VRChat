# DG-LAB .pulse 文件格式与设备协议

本文档基于对 DG-LAB 社区分享的 .pulse 波形文件的逆向分析及设备蓝牙协议 V3。

---

## 设备协议：Hex Op 格式

设备接收的波形数据为 16 位十六进制字符串（hex op），每个 op 包含 4 个脉冲：

```
FFFFFFFF SSSSSSSS
│││││││  ││││││││
│││││││  ││││││└┘─ 脉冲4 强度 (0x00-0x64 = 0-100%)
│││││││  ││││└┘─── 脉冲3 强度
│││││││  ││└┘───── 脉冲2 强度
│││││││  └┘─────── 脉冲1 强度
│││││└┘──────────── 脉冲4 频率字节
│││└┘────────────── 脉冲3 频率字节
│└┘──────────────── 脉冲2 频率字节
└┘───────────────── 脉冲1 频率字节
```

### 频率字节 = 脉冲间隔（毫秒）

**前 4 字节（8 位 hex）是频率，其数值直接等于脉冲间隔的毫秒数。**

- 有效范围：`0x0A` (10) ~ `0xF0` (240)
- 含义：两次脉冲之间的间隔时间
- **不是频率的倒数映射，不需要任何反向计算**

| freq_byte (十进制) | 间隔 | 实际频率 | 体感 |
|-------------------|------|---------|------|
| 10 (0x0A) | 10ms | 100 Hz | 最高频，柔和/震动感 |
| 30 (0x1E) | 30ms | 33 Hz | 中高频 |
| 50 (0x32) | 50ms | 20 Hz | 中频 |
| 100 (0x64) | 100ms | 10 Hz | 低频，明显脉冲感 |
| 200 (0xC8) | 200ms | 5 Hz | 很低频，每下明显 |
| 240 (0xF0) | 240ms | ~4 Hz | 设备最低频 |

### 强度字节

- 后 4 字节（8 位 hex）是强度
- 范围：`0x00` (0%) ~ `0x64` (100%)
- 实际输出强度 = 强度百分比 × 通道设定的强度上限

### 静默帧

当 freq_byte = 0 时，该脉冲静默（不输出）。强度字节应同时为 0：
```
0000000000000000    ← 4个脉冲全部静默，持续 100ms（4×25ms）
```

### 示例

```
F0F0F0F000050A0F
```
- 4 个脉冲频率都是 240（间隔 240ms ≈ 4Hz）
- 强度分别是 0%, 5%, 10%, 15%

```
0A0A0A0A64646464
```
- 4 个脉冲频率都是 10（间隔 10ms = 100Hz）
- 强度都是 100%

---

## 播放速度（Speed）与时间槽

### 基本概念

设备的最小时间单位是 **25ms 时间槽（slot）**。每个 op 固定包含 4 个 slot = 100ms。

Speed 决定 `.pulse` 文件中**每个 point（脉冲点）**占据多少个 slot：

| speed | 每 point 占 slot 数 | 每 point 实际时长 | 计算公式 |
|-------|-------------------|-----------------|---------|
| 4 | 1 slot | 25ms | 4 / speed = 1 |
| 2 | 2 slots | 50ms | 4 / speed = 2 |
| 1 | 4 slots (= 1 op) | 100ms | 4 / speed = 4 |

### 转换规则

`slots_per_point = 4 ÷ speed`

- **speed=4**（四倍速）：1 point → 1 slot (25ms)，4 points 填满 1 op
- **speed=2**（两倍速）：1 point → 2 slots (50ms)，2 points 填满 1 op
- **speed=1**（正常速）：1 point → 4 slots (100ms)，1 point 就是 1 op

### 实际影响

以一个有 20 个 point 的波形为例：

| speed | 总 slot 数 | 总 op 数 | 总时长 |
|-------|-----------|---------|-------|
| 4 | 20 | 5 ops | 0.5s |
| 2 | 40 | 10 ops | 1.0s |
| 1 | 80 | 20 ops | 2.0s |

### 展开方式

每个 point 的强度和频率值在展开时被**复制**到对应数量的 slot：

```
speed=4: point[0] → slot[0]
         point[1] → slot[1]
         point[2] → slot[2]
         point[3] → slot[3]  ← 这 4 slot 打包成 1 op

speed=1: point[0] → slot[0], slot[1], slot[2], slot[3]  ← 1 point 就是 1 op
```

### rest_ticks 与 speed

Header 中的 rest_ticks（静默 tick 数）同样受 speed 影响：

```
实际静默 slot 数 = rest_ticks × slots_per_point
实际静默时间 = rest_ticks × slots_per_point × 25ms
```

例如 `rest_ticks=99, speed=4`：
- 静默 slot = 99 × 1 = 99 slots
- 静默 op = ceil(99/4) = 25 ops
- 静默时间 = 99 × 25ms = 2.475s

---

## .pulse 文件结构

### 整体格式

```
Dungeonlab+pulse:[header=]section0+section+section1+section+section2+...
```

- 前缀固定 `Dungeonlab+pulse:`
- Header 可选，以 `=` 结尾
- 多个 Section 以 `+section+` 分隔
- APP 编辑器固定导出 10 个 Section 槽位

### Header

格式：`rest_ticks,speed,param3=`

| 字段 | 含义 | 取值 | 示例 |
|------|------|------|------|
| rest_ticks | 末尾静默 tick 数 | 0-99 | 99 |
| speed | 播放速度 | 1, 2, 4 | 4 |
| param3 | 未确认（可能是通道/平衡） | 1, 8, 16 | 8 |

无 Header 时默认：`rest_ticks=0, speed=1`

### Section

格式：`meta/point_list`

#### Meta

5 个逗号分隔整数：`freq_low,freq_high,duration,freq_mode,enabled`

| 字段 | 含义 | 取值 |
|------|------|------|
| freq_low | 频率滑块低值 | 0-83 |
| freq_high | 频率滑块高值（模式1忽略） | 0-83 |
| duration | 最小 tick 数 | 0-99+ |
| freq_mode | 频率变化模式 | 1-4 |
| enabled | 是否启用 | 0/1 |

#### Point List

格式：`value-flag,value-flag,...`

- `value`：强度 0-100（百分比）
- `flag`：1=锚点（手动），0=自动插值点

每个 point 对应一个逻辑脉冲。实际时长由 speed 决定（见上文）。

---

## 频率滑块映射表

.pulse 中的 `freq_low`/`freq_high` 是 0-83 的滑块档位。转换时需要映射到 freq_byte（毫秒）：

| 滑块范围 | 间隔范围 | 步进 | 档位数 |
|---------|---------|------|--------|
| 0-39 | 10-49ms | 1ms | 40 |
| 40-54 | 50-78ms | 2ms | 15 |
| 55-58 | 80-95ms | 5ms | 4 |
| 59-68 | 100-190ms | 10ms | 10 |
| 69-75 | 200-400ms | ~33ms (33,33,34循环) | 7 |
| 76-78 | 450-550ms | 50ms | 3 |
| 79-83 | 600-1000ms | 100ms | 5 |

**注意**：设备 freq_byte 上限 240ms，滑块 76+ 的值（>240ms）在写入 op 时被截断为 240。

关键参考值：

| 滑块 | 间隔(ms) | freq_byte | 体感 |
|------|---------|-----------|------|
| 0 | 10 | 0x0A | 最高频，震动感 |
| 20 | 30 | 0x1E | 中高频 |
| 40 | 50 | 0x32 | 中频 |
| 59 | 100 | 0x64 | 低频，脉冲感 |
| 69 | 200 | 0xC8 | 很低频 |
| 75 | 400 | 0xF0 (截断) | 极低频（超出设备范围） |

---

## 频率模式（freq_mode）

频率按**每个 point（逻辑脉冲）**分配，不是按 op。同一个 op 内的 4 个 slot 可以有不同频率。

| 值 | 名称 | 描述 |
|----|------|------|
| 1 | 固定 | 整个 Section 使用 freq_low 的对应 freq_byte |
| 2 | 节内渐变 | 从 freq_low 到 freq_high 线性，跨 Section 所有 point（含循环） |
| 3 | 元内渐变 | 每个波形单元（N points）内部从 freq_low 到 freq_high 线性 |
| 4 | 元间渐变 | 单元内频率固定，但从第1个单元到最后一个单元线性变化 |

freq_low 和 freq_high 先通过滑块映射表转换为 freq_byte，然后在各模式下线性插值。

---

## Duration 与循环

设 Point List 有 N 个点，duration 为 D：

- 波形单元必须**完整播放**（不能中途截断）
- 实际循环次数 = `ceil(D / N)`（至少 1）
- 当 N ≥ D 时，仍完整播放 1 遍

| 场景 | N | D | 循环 | 实际 point 总数 |
|------|---|---|------|--------------|
| 弹球 Sec 1 | 8 | 68 | 9 | 72 |
| 夹子用 Sec 0 | 17 | 49 | 3 | 51 |
| 摸摸拍拍 Sec 1 | 8 | 11 | 2 | 16 |
| 特别疼 Sec 0 | 4 | 8 | 2 | 8 |

实际播放总时长 = 总 point 数 × slots_per_point × 25ms

---

## 转换流程总结

```
.pulse 文件
    ↓ parse
[Header] + [Section 0..N]
    ↓ 对每个 enabled Section
读取 Point List → N 个 (strength, flag)
计算循环: repeats = ceil(duration / N)
展开: total_points = repeats × N
    ↓ 按 speed 展开到 slot
每个 point → slots_per_point 个 slot
total_slots = total_points × slots_per_point
    ↓ 频率分配（按 freq_mode）
每个 point 计算一个 freq_byte，复制到其所有 slot
    ↓ 打包
每 4 个 slot → 1 个 hex op (freq_hex + strength_hex)
    ↓ 追加静默
rest_slots = rest_ticks × slots_per_point (补齐到4的倍数)
追加全零 op
    ↓ 分片
每 86 个 op → 1 条 WebSocket 消息 (JSON 数组)
```

---

## 完整示例

文件：`pulse-弹球-9121280.pulse`，Header: `99,4,8=`

- rest_ticks=99, speed=4, param3=8
- slots_per_point = 4/4 = 1（每 point = 1 slot = 25ms）

Section 1: `25,60,68,1,1/...8个点...`
- freq_low=25 → 35ms, 固定模式
- 8 个 point, duration=68
- 循环 = ceil(68/8) = 9 次
- 总 point = 72, 总 slot = 72
- 总 op = 72/4 = 18 ops
- 时长 = 72 × 25ms = 1.8s

末尾静默：99 × 1 = 99 slots → 25 ops → 2.475s

---

## 参考

- 设备协议：[DG-LAB-OPENSOURCE](https://github.com/DG-LAB-OPENSOURCE/DG-LAB-OPENSOURCE) 蓝牙协议 V3
- 波形数据来源：DG-LAB 社区公开分享
- 转换器实现：`pulse_to_hex/dglab_pulse_converter.py`
