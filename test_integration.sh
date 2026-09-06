#!/bin/bash
# Integration test: start main + mock device + send OSC, verify wave flow
set -e

source /usr/share/Modules/init/bash
module load python/3.11.6

cd /workspace/git/ehexyil/Shocking-VRChat

# Kill any existing instances
pkill -f "shocking_vrchat.py" 2>/dev/null || true
pkill -f "mock_device.py" 2>/dev/null || true
sleep 1

echo "=== Starting main program ==="
SHOCKING_SKIP_OPEN=1 python3 shocking_vrchat.py > /tmp/shocking_main.log 2>&1 &
MAIN_PID=$!
sleep 2

echo "=== Starting mock device ==="
python3 mock_device.py > /tmp/mock_device.log 2>&1 &
MOCK_PID=$!
sleep 3

echo "=== Checking status ==="
curl -s http://127.0.0.1:8800/api/v1/status | python3 -c "
import sys,json
d=json.load(sys.stdin)
n=len(d['devices'])
print(f'  Devices connected: {n}')
if n==0: print('  ERROR: mock device not connected!'); sys.exit(1)
"

echo "=== Sending OSC (continuous 2s) ==="
python3 -c "
from pythonosc.udp_client import SimpleUDPClient
import time, urllib.request, json

client = SimpleUDPClient('127.0.0.1', 9001)
for i in range(40):
    v = 0.3 + 0.5 * (i % 10) / 10.0
    client.send_message('/avatar/parameters/pcs/contact/enterPass', v)
    time.sleep(0.05)

# Check history immediately while still active
time.sleep(0.05)
resp = urllib.request.urlopen('http://127.0.0.1:8800/api/v1/wave_history')
data = json.loads(resp.read())
a = [x for x in data['A'] if x > 0]
b = [x for x in data['B'] if x > 0]
print(f'  A non-zero samples: {len(a)}')
print(f'  B non-zero samples: {len(b)}')
if a:
    print(f'  A values (first 10): {a[:10]}')
    print('  ✓ Wave history has data!')
else:
    print('  ✗ No wave data captured')
"

echo "=== Mock device received ==="
cat /tmp/mock_device.log | head -30

echo ""
echo "=== Cleanup ==="
kill $MOCK_PID $MAIN_PID 2>/dev/null
echo "Done."
