---
name: linux-dev-run
description: 在 Linux 开发环境中启动 Shocking-VRChat 服务器用于临时查看和调试。包括环境准备、启动、测试、关闭的完整流程。
---

# Linux 开发环境启动指南

## 环境准备

```bash
# 加载 Python 3.11
source /usr/share/Modules/init/bash && module load python/3.11.6

# 加载 Node.js 20（如果需要重新构建前端）
source /usr/share/Modules/init/bash && module load nodejs/20.19.5
```

## 项目路径

```
/workspace/git/ehexyil/Shocking-VRChat
```

## 启动服务器

```bash
cd /workspace/git/ehexyil/Shocking-VRChat

# 后台启动（不自动打开浏览器）
SHOCKING_SKIP_OPEN=1 python3 shocking_vrchat.py > /tmp/svrc.log 2>&1 &

# 等待启动完成（约5-6秒）
sleep 6

# 检查是否启动成功
grep -E "Started|Listen" /tmp/svrc.log
```

成功启动后应看到：
```
[init] Config loaded. WS needs external access - allow firewall prompt if shown.
OSC Listening: 127.0.0.1:9001
WS Listening: 127.0.0.1:28846
[engine] Started.
```

## 访问地址

- **Web 管理界面**: http://127.0.0.1:8800
- **WebSocket (设备)**: ws://127.0.0.1:28846
- **OSC 监听**: 127.0.0.1:9001

## 查看日志

```bash
# 实时查看
tail -f /tmp/svrc.log

# 查看错误
grep -i "error\|ERROR" /tmp/svrc.log

# 查看最近N行
tail -20 /tmp/svrc.log
```

## 测试 API

```bash
# 状态
curl -s http://127.0.0.1:8800/api/v1/status | python3 -m json.tool

# 配置
curl -s http://127.0.0.1:8800/api/v1/config | python3 -m json.tool

# 波形预设列表
curl -s http://127.0.0.1:8800/api/v1/wave_presets | python3 -m json.tool

# 强度设置
curl -s http://127.0.0.1:8800/api/v1/strength_limit | python3 -m json.tool

# 模式配置
curl -s http://127.0.0.1:8800/api/v1/mode_config/a/distance | python3 -m json.tool

# 日志
curl -s http://127.0.0.1:8800/api/v1/logs | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{len(d[\"logs\"])} entries')"

# 检查更新
curl -s http://127.0.0.1:8800/api/v1/update/check | python3 -m json.tool
```

## 模拟 OSC 输入

```bash
python3 -c "
from pythonosc.udp_client import SimpleUDPClient
client = SimpleUDPClient('127.0.0.1', 9001)

# 发送 float (距离模式)
client.send_message('/avatar/parameters/pcs/contact/enterPass', 0.5)

# 发送 bool (电击触发)
client.send_message('/avatar/parameters/Shock/trigger', True)
"
```

## 重新构建前端

```bash
cd /workspace/git/ehexyil/Shocking-VRChat/frontend

# 类型检查
node node_modules/.bin/vue-tsc --noEmit

# 构建（产物输出到 ../static/）
node node_modules/.bin/vite build
```

## 验证 Python 编译

```bash
cd /workspace/git/ehexyil/Shocking-VRChat
python3 -c "import py_compile; py_compile.compile('shocking_vrchat.py', doraise=True)" && echo "OK"
```

## 关闭服务器

```bash
pkill -f shocking_vrchat
```

或通过 API：
```bash
curl -s -X POST http://127.0.0.1:8800/api/v1/shutdown
```

## 常见问题

### 端口被占用

```bash
# 查看占用端口的进程
lsof -i :8800
lsof -i :9001

# 强制杀掉
pkill -f shocking_vrchat; sleep 2
```

### 首次运行（无配置文件）

首次运行会生成默认配置文件并启动设置向导（/setup 页面）。用 `SHOCKING_SKIP_OPEN=1` 时需要手动打开 http://127.0.0.1:8800/setup。

### 修改后快速重启

```bash
pkill -f shocking_vrchat; sleep 1
cd /workspace/git/ehexyil/Shocking-VRChat && SHOCKING_SKIP_OPEN=1 python3 shocking_vrchat.py > /tmp/svrc.log 2>&1 &
sleep 5 && grep "Started" /tmp/svrc.log
```

### Python 依赖问题

```bash
pip install -r requirements.txt
```

注意：`pystray` 和 `Pillow` 在 Linux 无头环境下可能无法使用托盘功能，但不影响服务器运行（会自动跳过）。
