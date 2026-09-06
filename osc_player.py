"""
OSC Player - 回放录制的 OSC 数据

读取 osc_recorder.py 录制的 JSON 文件，按原始时间间隔精确发送 OSC 消息，
使接收端的行为与录制时完全一致。

使用方式：
    python osc_player.py recording.json                  # 回放到默认 9001 端口
    python osc_player.py recording.json -p 9001          # 指定目标端口
    python osc_player.py recording.json --speed 2.0      # 2倍速回放
    python osc_player.py recording.json --loop           # 循环回放
    python osc_player.py recording.json --loop 3         # 循环3次

按 Ctrl+C 停止回放。
"""

import argparse
import json
import time
import sys

from pythonosc.udp_client import SimpleUDPClient


def load_recording(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if data.get('version', 0) < 1:
        print("警告: 录制文件版本未知，尝试继续...")

    messages = data.get('messages', [])
    duration_ms = data.get('duration_ms', 0)
    print(f"  文件: {filepath}")
    print(f"  消息数: {len(messages)}")
    print(f"  时长: {duration_ms/1000:.2f}s")
    print(f"  录制时间: {data.get('recorded_at', '未知')}")
    return messages, duration_ms


def resolve_arg_type(arg):
    """确保参数类型正确传递（JSON反序列化后int/float/bool/str保持原样）"""
    # json.load 已经保留了 int, float, bool, str, None
    # python-osc 会根据 Python 类型自动映射到 OSC 类型
    return arg


def playback(messages, client, speed=1.0):
    """按原始时序回放消息"""
    if not messages:
        print("  无消息可回放")
        return

    total = len(messages)
    start_time = time.perf_counter()

    for i, msg in enumerate(messages):
        target_time_ms = msg['t'] / speed
        target_time_s = target_time_ms / 1000.0

        # 精确等待到目标时间
        while True:
            elapsed = time.perf_counter() - start_time
            remaining = target_time_s - elapsed
            if remaining <= 0:
                break
            if remaining > 0.005:
                # 粗等待：sleep 大部分时间
                time.sleep(remaining * 0.8)
            else:
                # 精等待：busy-wait 最后几毫秒
                pass

        # 发送 OSC 消息
        addr = msg['addr']
        args = [resolve_arg_type(a) for a in msg.get('args', [])]

        try:
            client.send_message(addr, args)
        except Exception as e:
            print(f"\n  发送失败: {addr} {args} -> {e}")
            continue

        # 进度显示
        progress = (i + 1) / total * 100
        elapsed_s = time.perf_counter() - start_time
        args_str = ', '.join(f'{a}' for a in args)
        print(f"\r  [{elapsed_s:.1f}s] {progress:.0f}% #{i+1}/{total} {addr} = {args_str}    ", end='', flush=True)

    elapsed_total = time.perf_counter() - start_time
    print(f"\n  回放完成，实际耗时: {elapsed_total:.3f}s")


def main():
    parser = argparse.ArgumentParser(description='OSC Player - 回放录制的 OSC 数据')
    parser.add_argument('file', help='录制文件路径 (.json)')
    parser.add_argument('-p', '--port', type=int, default=9001, help='目标 OSC 端口 (默认 9001)')
    parser.add_argument('-H', '--host', type=str, default='127.0.0.1', help='目标地址 (默认 127.0.0.1)')
    parser.add_argument('--speed', type=float, default=1.0, help='回放速度倍率 (默认 1.0)')
    parser.add_argument('--loop', nargs='?', const=-1, type=int, default=1, help='循环次数 (-1=无限, 默认=1)')
    args = parser.parse_args()

    print(f"OSC Player")
    messages, duration_ms = load_recording(args.file)

    if not messages:
        print("文件中无消息，退出。")
        return

    client = SimpleUDPClient(args.host, args.port)
    print(f"  目标: {args.host}:{args.port}")
    print(f"  速度: {args.speed}x")
    if args.loop == -1:
        print(f"  循环: 无限")
    elif args.loop > 1:
        print(f"  循环: {args.loop} 次")
    print(f"  按 Ctrl+C 停止\n")

    loop_count = 0
    try:
        while True:
            loop_count += 1
            if args.loop > 0:
                print(f"--- 第 {loop_count}/{args.loop} 次回放 ---")
            else:
                print(f"--- 第 {loop_count} 次回放 ---")

            playback(messages, client, speed=args.speed)

            if args.loop > 0 and loop_count >= args.loop:
                break

            # 循环间隔等一小段
            print("  间隔 0.5s...")
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n\n回放已停止。")


if __name__ == '__main__':
    main()
