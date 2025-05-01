# 用于向 Shocking-VRChat 发送 OSC 消息进行测试的脚本
from pythonosc.udp_client import SimpleUDPClient
import time, random

# Shocking-VRChat 默认监听的 IP 和端口
ip = "127.0.0.1"
port = 9001

# 创建 OSC 客户端
client = SimpleUDPClient(ip, port)

# --- 测试消息示例 (注释掉的部分) ---

# 发送单个 float 值到指定地址
# client.send_message("/avatar/parameters/Shock/Area1", 0.02)
# input() # 等待用户输入，方便观察效果

# 发送包含单个 float 的列表 (pythonosc 的常见用法)
# client.send_message("/avatar/parameters/ShockA1/a", [0.07,])
# time.sleep(0.02)
# client.send_message("/avatar/parameters/ShockA1/b", [0.2,])
# time.sleep(0.2)
# client.send_message("/avatar/parameters/ShockA1/b", [0.3,])
# time.sleep(0.2)
# client.send_message("/avatar/parameters/ShockA1/b", [0.4,])
# time.sleep(0.2)
# client.send_message("/avatar/parameters/ShockA1/b", [0.5,])
# time.sleep(0.2)
# client.send_message("/avatar/parameters/ShockA1/b", [0.8,])
# time.sleep(0.2)
# client.send_message("/avatar/parameters/ShockA1/b", [0.9,])
# time.sleep(0.2)
# client.send_message("/avatar/parameters/ShockA1/b", [0.6,])
# time.sleep(0.2)

# --- 当前使用的测试逻辑 ---

# 向 "/avatar/parameters/ShockB2/some/param" 地址发送 30 次随机 float 值 (0.0 到 1.0)
# 每次发送后暂停 0.05 秒
# 这可以用来测试配置了通配符 (* 或 ?) 的监听地址
for _ in range(30):
    client.send_message("/avatar/parameters/ShockB2/some/param", [random.random(),])
    time.sleep(0.05)

# 向 "/avatar/parameters/pcs/sps/pussy" 地址发送 200 次随机 float 值
# 每次发送后暂停 0.05 秒
# 这可以用来测试处理大量快速变化数据的能力，例如模拟距离变化
for _ in range(200):
    client.send_message("/avatar/parameters/pcs/sps/pussy", [random.random(),])
    time.sleep(0.05)

# 再次向 "/avatar/parameters/ShockB2/some/param" 发送 3 次随机 float 值
# 每次发送后暂停 0.05 秒
for _ in range(3):
    client.send_message("/avatar/parameters/ShockB2/some/param", [random.random(),])
    time.sleep(0.05)