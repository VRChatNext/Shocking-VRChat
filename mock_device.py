"""
Mock DG-LAB device client for testing on Linux without a real device.

Simulates the DG-LAB APP connecting to the Shocking-VRChat WebSocket server.
Prints all received commands (strength changes, wave data) to console.

Usage:
    python3 mock_device.py [ws_url]

    If ws_url is not given, reads it from the settings file automatically.

Example:
    python3 mock_device.py
    python3 mock_device.py ws://127.0.0.1:28846/6da2fd3b-a6e5-4af4-afc1-96bfd2e9e95c
"""

import asyncio
import json
import sys
import uuid
import yaml
import os

try:
    import websockets
except ImportError:
    print("需要安装 websockets: pip install websockets")
    sys.exit(1)

# ANSI colors
C_RESET = "\033[0m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_CYAN = "\033[36m"
C_RED = "\033[31m"
C_DIM = "\033[2m"


def decode_wave_ops(wavestr: str) -> str:
    """Decode wave hex ops to human-readable summary."""
    try:
        ops = json.loads(wavestr)
        if not ops:
            return "(empty)"
        strengths = []
        for op in ops[:5]:  # show first 5
            # each op is 16 hex chars: 8 freq + 8 strength
            s_bytes = [int(op[i:i+2], 16) for i in range(8, 16, 2)]
            strengths.append(f"{sum(s_bytes)//4}%")
        suffix = f" ...+{len(ops)-5} more" if len(ops) > 5 else ""
        return f"[{', '.join(strengths)}{suffix}] ({len(ops)} ops)"
    except Exception:
        return wavestr[:60]


async def mock_device(ws_url: str, strength_max: int = 100):
    """Connect to WS server as a mock DG-LAB device."""
    device_id = str(uuid.uuid4())
    print(f"{C_GREEN}[mock] Connecting to {ws_url}{C_RESET}")
    print(f"{C_GREEN}[mock] Device ID: {device_id}{C_RESET}")
    print(f"{C_GREEN}[mock] Strength max: {strength_max}{C_RESET}")
    print(f"{C_DIM}{'─' * 60}{C_RESET}")

    # Extract master_uuid from URL path
    master_uuid = ws_url.rstrip('/').split('/')[-1]

    strength = {'A': 0, 'B': 0}
    strength_max_val = {'A': strength_max, 'B': strength_max}

    async with websockets.connect(ws_url) as ws:
        print(f"{C_GREEN}[mock] Connected! Waiting for bind request...{C_RESET}")

        # Server sends bind request first
        raw = await ws.recv()
        event = json.loads(raw)
        print(f"{C_CYAN}[recv] {event['type']}: {event['message']}{C_RESET}")

        if event['type'] == 'bind':
            # Respond with bind confirmation
            target_id = event['clientId']  # server's connection id
            bind_resp = json.dumps({
                'type': 'bind',
                'clientId': master_uuid,
                'targetId': target_id,
                'message': '200'
            })
            await ws.send(bind_resp)
            print(f"{C_GREEN}[mock] Bind confirmed.{C_RESET}")

            # Send initial strength report
            # format: strength-A_current+B_current+A_max+B_max
            strength_msg = json.dumps({
                'type': 'msg',
                'clientId': master_uuid,
                'targetId': target_id,
                'message': f"strength-{strength['A']}+{strength['B']}+{strength_max_val['A']}+{strength_max_val['B']}"
            })
            await ws.send(strength_msg)
            print(f"{C_GREEN}[mock] Sent initial strength: A={strength['A']}/{strength_max_val['A']} B={strength['B']}/{strength_max_val['B']}{C_RESET}")

        print(f"{C_DIM}{'─' * 60}{C_RESET}")
        print(f"{C_GREEN}[mock] Ready. Listening for commands...{C_RESET}")
        print(f"{C_DIM}(Press Ctrl+C to disconnect){C_RESET}\n")

        # Listen for messages
        async for raw in ws:
            try:
                event = json.loads(raw)
                msg_type = event.get('type', '')
                message = event.get('message', '')

                if msg_type == 'heartbeat':
                    # Respond to heartbeat
                    await ws.send(json.dumps({
                        'type': 'heartbeat',
                        'clientId': '',
                        'targetId': '',
                        'message': '200'
                    }))
                    print(f"{C_DIM}[heartbeat]{C_RESET}")

                elif msg_type == 'msg':
                    if message.startswith('strength-'):
                        # strength-{channel}+{mode}+{value}
                        parts = message[len('strength-'):].split('+')
                        ch = 'A' if parts[0] == '1' else 'B'
                        mode = parts[1]  # 0=sub, 1=add, 2=set
                        value = int(parts[2])
                        mode_name = {0: 'sub', 1: 'add', 2: 'set'}.get(int(mode), mode)

                        if int(mode) == 2:
                            strength[ch] = value
                        elif int(mode) == 1:
                            strength[ch] = min(strength[ch] + value, strength_max_val[ch])
                        elif int(mode) == 0:
                            strength[ch] = max(strength[ch] - value, 0)

                        print(f"{C_YELLOW}[strength] Ch {ch} {mode_name}={value} → now {strength[ch]}/{strength_max_val[ch]}{C_RESET}")

                        # Report back current strength
                        strength_report = json.dumps({
                            'type': 'msg',
                            'clientId': master_uuid,
                            'targetId': event.get('clientId', ''),
                            'message': f"strength-{strength['A']}+{strength['B']}+{strength_max_val['A']}+{strength_max_val['B']}"
                        })
                        await ws.send(strength_report)

                    elif message.startswith('pulse-'):
                        # pulse-{channel}:{wavedata}
                        ch = message[6]  # 'A' or 'B'
                        wavestr = message[8:]  # skip "pulse-X:"
                        summary = decode_wave_ops(wavestr)
                        print(f"{C_CYAN}[wave] Ch {ch} {summary}{C_RESET}")

                    elif message.startswith('clear-'):
                        ch_num = message[6]
                        ch = 'A' if ch_num == '1' else 'B'
                        print(f"{C_RED}[clear] Ch {ch}{C_RESET}")

                    else:
                        print(f"{C_DIM}[msg] {message}{C_RESET}")
                else:
                    print(f"{C_DIM}[{msg_type}] {message}{C_RESET}")

            except Exception as e:
                print(f"{C_RED}[error] {e}{C_RESET}")


def get_ws_url_from_config() -> str:
    """Read WS URL from settings files."""
    config_file = 'settings-advanced-v0.2.yaml'
    if not os.path.exists(config_file):
        # Try to find any settings-advanced file
        for f in os.listdir('.'):
            if f.startswith('settings-advanced-') and f.endswith('.yaml'):
                config_file = f
                break

    if not os.path.exists(config_file):
        print(f"{C_RED}找不到配置文件，请指定 ws_url 参数或先运行一次主程序生成配置{C_RESET}")
        sys.exit(1)

    with open(config_file, 'r', encoding='utf-8') as f:
        settings = yaml.safe_load(f)

    host = '127.0.0.1'
    port = settings['ws']['listen_port']
    master_uuid = settings['ws']['master_uuid']
    return f"ws://{host}:{port}/{master_uuid}"


def main():
    if len(sys.argv) > 1:
        ws_url = sys.argv[1]
    else:
        ws_url = get_ws_url_from_config()

    strength_max = 100
    if len(sys.argv) > 2:
        strength_max = int(sys.argv[2])

    print(f"""
╔══════════════════════════════════════════════╗
║   DG-LAB Mock Device (Linux Test Client)    ║
╚══════════════════════════════════════════════╝
""")

    try:
        asyncio.run(mock_device(ws_url, strength_max))
    except KeyboardInterrupt:
        print(f"\n{C_GREEN}[mock] Disconnected.{C_RESET}")
    except Exception as e:
        print(f"{C_RED}[error] {e}{C_RESET}")
        sys.exit(1)


if __name__ == '__main__':
    main()
