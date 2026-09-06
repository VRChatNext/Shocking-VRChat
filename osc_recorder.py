"""
OSC Recorder - 录制 VRChat OSC 数据

监听指定端口，将所有收到的 OSC 消息按时间顺序记录到 JSON 文件。
每条消息记录相对于录制开始的精确时间偏移（毫秒），保证回放时时序完全一致。

使用方式：
    python osc_recorder.py                    # 默认监听 9001 端口
    python osc_recorder.py -p 9021            # 自定义端口
    python osc_recorder.py -o my_recording    # 自定义输出文件名前缀
    python osc_recorder.py -d 60             # 录制60秒后自动停止

按 Ctrl+C 停止录制并保存。
"""

import argparse
import json
import time
import sys
from datetime import datetime
from pythonosc.osc_server import BlockingOSCUDPServer
from pythonosc.dispatcher import Dispatcher


class OSCRecorder:
    def __init__(self):
        self.messages = []
        self.start_time = None
        self.message_count = 0

    def handler(self, address, *args):
        now = time.perf_counter()
        if self.start_time is None:
            self.start_time = now

        elapsed_ms = (now - self.start_time) * 1000.0

        # 记录消息：时间偏移、地址、参数（保留类型信息）
        entry = {
            't': round(elapsed_ms, 3),
            'addr': address,
            'args': list(args),
        }
        self.messages.append(entry)
        self.message_count += 1

        # 实时打印
        args_str = ', '.join(f'{a}' for a in args)
        print(f"\r  [{elapsed_ms/1000:.1f}s] #{self.message_count} {address} = {args_str}    ", end='', flush=True)

    def save(self, filepath):
        duration_ms = 0
        if self.messages:
            duration_ms = self.messages[-1]['t']

        data = {
            'version': 1,
            'recorded_at': datetime.now().isoformat(),
            'duration_ms': round(duration_ms, 3),
            'message_count': len(self.messages),
            'messages': self.messages,
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, separators=(',', ':'))

        print(f"\n\n已保存: {filepath}")
        print(f"  消息数: {len(self.messages)}")
        print(f"  时长: {duration_ms/1000:.2f}s")
        size_kb = len(json.dumps(data, ensure_ascii=False, separators=(',', ':'))) / 1024
        print(f"  文件大小: {size_kb:.1f} KB")


def main():
    parser = argparse.ArgumentParser(description='OSC Recorder - 录制 VRChat OSC 数据')
    parser.add_argument('-p', '--port', type=int, default=9001, help='OSC 监听端口 (默认 9001)')
    parser.add_argument('-H', '--host', type=str, default='127.0.0.1', help='OSC 监听地址 (默认 127.0.0.1)')
    parser.add_argument('-o', '--output', type=str, default=None, help='输出文件名前缀 (默认按时间命名)')
    parser.add_argument('-d', '--duration', type=float, default=0, help='录制时长(秒), 0=手动停止')
    args = parser.parse_args()

    recorder = OSCRecorder()

    dispatcher = Dispatcher()
    dispatcher.set_default_handler(recorder.handler)

    filename = args.output or f"osc_recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if not filename.endswith('.json'):
        filename += '.json'

    print(f"OSC Recorder")
    print(f"  监听: {args.host}:{args.port}")
    print(f"  输出: {filename}")
    if args.duration > 0:
        print(f"  时长: {args.duration}s")
    print(f"  按 Ctrl+C 停止录制\n")
    print("等待 OSC 数据...")

    server = BlockingOSCUDPServer((args.host, args.port), dispatcher)

    try:
        if args.duration > 0:
            import threading
            def timeout():
                time.sleep(args.duration)
                print("\n\n录制时间到，正在保存...")
                server.shutdown()
            t = threading.Thread(target=timeout, daemon=True)
            t.start()

        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\n录制中断，正在保存...")
    finally:
        server.server_close()

    if recorder.messages:
        recorder.save(filename)
    else:
        print("\n未录制到任何消息。")


if __name__ == '__main__':
    main()
