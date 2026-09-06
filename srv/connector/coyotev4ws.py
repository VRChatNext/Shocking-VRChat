"""
DG-LAB V4 WebSocket Protocol Connector.

V4 protocol uses a relay model:
- Controller (us) connects without ?tid → gets clientId
- Controlled (DG-LAB APP) connects with ?tid=<our clientId> → paired automatically
- Messages use RPC format: {t: 'req', reqId, m, data} / {t: 'resp', reqId, result/error}
- Events from APP: {t: 'ev', ev: '<event_type>', ...}
- Server frames: {type: 'message', clientId, data} for relay

In our self-hosted relay mode, WE are the relay server AND the controller.
The DG-LAB APP connects to us directly as a controlled client.
"""
import json
import asyncio
import time
import uuid
import os
from loguru import logger

from srv import WS_CONNECTIONS

# V4 Action Types
ACTION_APPEND_PULSE_DATA = 0
ACTION_ADD_INTENSITY = 3
ACTION_SET_TEMP_INTENSITY = 4
ACTION_SET_MUTE = 5
ACTION_SET_INTENSITY = 7

# V4 Channels
V4_CHANNEL_A = 0
V4_CHANNEL_B = 1

# Heartbeat interval
V4_HEARTBEAT_INTERVAL = 30.0


class DGV4Connection:
    """Represents a single DG-LAB APP connected via V4 protocol."""

    wave_observer = None
    clear_observer = None
    _suppress_clear = False

    def __init__(self, ws_connection, client_id: str, SETTINGS: dict):
        if SETTINGS is None:
            raise ValueError("DGV4Connection SETTINGS not provided.")
        self.ws_conn = ws_connection
        self.client_id = client_id
        self.uuid = client_id  # Compatibility with V3 interface
        self.SETTINGS = SETTINGS
        self._req_counter = 0
        self._closed = False

        limit_a = SETTINGS['dglab3']['channel_a']['strength_limit']
        limit_b = SETTINGS['dglab3']['channel_b']['strength_limit']
        overlimit_a = SETTINGS['dglab3']['channel_a'].get('overlimit_max', 20)
        overlimit_b = SETTINGS['dglab3']['channel_b'].get('overlimit_max', 20)

        self.strength = {'A': 0, 'B': 0}
        self.strength_max = {'A': 200, 'B': 200}
        self.strength_limit = {'A': limit_a, 'B': limit_b}
        self.overlimit_max = {'A': overlimit_a, 'B': overlimit_b}
        self.overlimit_active = {'A': False, 'B': False}

        # Device slots discovered from APP
        self.devices = []  # [{slotId, name, type, props, slotState}]
        self.default_slot = None  # First discovered slot ID

        WS_CONNECTIONS.add(self)

    def __str__(self):
        return f"<DGV4Connection (id:{self.client_id}, {self.strength}, max {self.strength_max})>"

    def _next_req_id(self) -> str:
        self._req_counter += 1
        return f"req-{self._req_counter}"

    def _channel_to_v4(self, channel: str) -> int:
        """Convert 'A'/'B' to V4 channel number."""
        return V4_CHANNEL_A if channel == 'A' else V4_CHANNEL_B

    def get_upper_strength(self, channel='A'):
        limit = self.strength_limit[channel]
        if self.overlimit_active[channel]:
            limit = max(limit, self.overlimit_max[channel])
        return min(self.strength_max[channel], limit)

    async def _send_json(self, data: dict):
        """Send JSON message to the APP."""
        if self._closed:
            return
        try:
            msg = json.dumps(data, separators=(',', ':'))
            logger.debug(f'[v4] Device {self.client_id} sending: {msg}')
            await self.ws_conn.send_text(msg)
        except Exception as e:
            logger.warning(f'[v4] Device {self.client_id} send error: {e}')

    async def _send_rpc(self, method: str, data: dict = None) -> str:
        """Send an RPC request to the APP via relay frame. Returns reqId."""
        req_id = self._next_req_id()
        rpc_payload = {
            't': 'req',
            'reqId': req_id,
            'm': method,
        }
        if data is not None:
            rpc_payload['data'] = data
        # Wrap in server message frame (we are the relay, sending to APP)
        frame = {
            'type': 'message',
            'data': rpc_payload,
        }
        await self._send_json(frame)
        return req_id

    async def set_strength(self, channel='A', mode='2', value=0, force=False):
        """Set strength. mode: 0=sub, 1=add, 2=set."""
        if not force:
            if value < 0 or value > 200:
                raise ValueError(f"Invalid strength value: {value}")
            limit = self.get_upper_strength(channel)
            if value > int(limit) and mode == '2':
                logger.warning(f'[v4] Device {self.client_id} set_strength: {value} over limit {limit}, clamping')
                value = limit

        slot_id = self.default_slot or 'slot-a'
        v4_channel = self._channel_to_v4(channel)

        if mode == '2':
            # Set absolute — V4 only supports SetIntensity to 0, use AddIntensity for other values
            if value == 0:
                await self._send_rpc('device.op', {
                    's': slot_id,
                    't': ACTION_SET_INTENSITY,
                    'c': v4_channel,
                    'p': 1,
                    'v': 0,
                })
            else:
                # Use SetTempIntensity with long duration as a workaround for absolute set
                # Or better: use AddIntensity relative to current
                current = self.strength[channel]
                delta = value - current
                if delta != 0:
                    await self._send_rpc('device.op', {
                        's': slot_id,
                        't': ACTION_ADD_INTENSITY,
                        'c': v4_channel,
                        'p': 1,
                        'v': delta,
                    })
            self.strength[channel] = value
        elif mode == '1':
            # Add
            await self._send_rpc('device.op', {
                's': slot_id,
                't': ACTION_ADD_INTENSITY,
                'c': v4_channel,
                'p': 1,
                'v': value,
            })
            self.strength[channel] = min(200, self.strength[channel] + value)
        elif mode == '0':
            # Sub
            await self._send_rpc('device.op', {
                's': slot_id,
                't': ACTION_ADD_INTENSITY,
                'c': v4_channel,
                'p': 1,
                'v': -value,
            })
            self.strength[channel] = max(0, self.strength[channel] - value)

        logger.debug(f'[v4] Set strength: ch={channel} mode={mode} val={value}')

    async def set_strength_0_to_1(self, channel='A', value=0):
        if value < 0 or value > 1:
            raise ValueError()
        limit = self.get_upper_strength(channel)
        strength = int(limit * value)
        await self.set_strength(channel=channel, mode='2', value=strength)

    async def send_wave(self, channel='A', wavestr=None):
        """Send wave data to device. wavestr is JSON array of hex op strings."""
        if wavestr is None:
            return
        slot_id = self.default_slot or 'slot-a'
        v4_channel = self._channel_to_v4(channel)

        try:
            ops = json.loads(wavestr)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f'[v4] Invalid wavestr for device {self.client_id}')
            return

        # V4 uses AppendPulseData with hex strings directly
        # Duration = num_ops * 100ms (each op = 4 pulses × 25ms)
        duration_ms = len(ops) * 100

        await self._send_rpc('device.op', {
            's': slot_id,
            't': ACTION_APPEND_PULSE_DATA,
            'c': v4_channel,
            'p': 1,
            'd': duration_ms,
            'v': ops,
        })

    async def clear_wave(self, channel='A'):
        """Clear wave output for a channel."""
        slot_id = self.default_slot or 'slot-a'
        v4_channel = self._channel_to_v4(channel)

        await self._send_rpc('device.op.clear', {
            's': slot_id,
            'c': v4_channel,
        })

    async def _handle_message(self, data: dict):
        """Handle incoming message from APP (inside relay frame)."""
        msg_type = data.get('t')

        if msg_type == 'ev':
            await self._handle_event(data)
        elif msg_type == 'resp':
            self._handle_response(data)
        elif msg_type == 'req':
            # APP sending request to us (unusual, but handle ping)
            method = data.get('m', '')
            if method == 'ping':
                await self._send_json({
                    'type': 'message',
                    'data': {'t': 'resp', 'reqId': data.get('reqId', ''), 'result': {}}
                })
        else:
            logger.debug(f'[v4] Device {self.client_id} unknown message type: {msg_type}')

    async def _handle_event(self, data: dict):
        """Handle events from APP."""
        event_type = data.get('ev', '')

        if event_type == 'devices.snapshot':
            # Full device list from APP
            self.devices = data.get('devices', [])
            if self.devices:
                self.default_slot = self.devices[0].get('slotId', 'slot-a')
                # Extract strength info
                for dev in self.devices:
                    props = dev.get('props', {})
                    slot_state = dev.get('slotState', {})
                    self.strength['A'] = props.get('intensityA', 0)
                    self.strength['B'] = props.get('intensityB', 0)
                    ch_a = slot_state.get('channelA', {})
                    ch_b = slot_state.get('channelB', {})
                    self.strength_max['A'] = ch_a.get('intensityMax', 200)
                    self.strength_max['B'] = ch_b.get('intensityMax', 200)
                    break  # Use first device
                logger.info(f'[v4] Device {self.client_id} snapshot: {len(self.devices)} devices, '
                           f'slot={self.default_slot} str={self.strength} max={self.strength_max}')
                # Apply strength limits
                for ch in ['A', 'B']:
                    limit = self.get_upper_strength(ch)
                    if self.strength[ch] != 0 and self.strength[ch] != limit:
                        await self.set_strength(ch, value=limit)
            else:
                logger.info(f'[v4] Device {self.client_id} snapshot: no devices')

        elif event_type == 'devices.patch':
            added = data.get('added', [])
            removed = data.get('removed', [])
            for dev in added:
                self.devices.append(dev)
                logger.info(f'[v4] Device {self.client_id} added slot: {dev.get("slotId")}')
            for slot_id in removed:
                self.devices = [d for d in self.devices if d.get('slotId') != slot_id]
                logger.info(f'[v4] Device {self.client_id} removed slot: {slot_id}')
            if self.devices and not self.default_slot:
                self.default_slot = self.devices[0].get('slotId', 'slot-a')

        elif event_type == 'slots.patch':
            # Strength / state updates
            slots = data.get('slots', [])
            for slot_data in slots:
                props = slot_data.get('props', {})
                if 'intensityA' in props:
                    self.strength['A'] = props['intensityA']
                if 'intensityB' in props:
                    self.strength['B'] = props['intensityB']
                slot_state = slot_data.get('slotState', {})
                if 'channelA' in slot_state:
                    imax = slot_state['channelA'].get('intensityMax')
                    if imax is not None:
                        self.strength_max['A'] = imax
                if 'channelB' in slot_state:
                    imax = slot_state['channelB'].get('intensityMax')
                    if imax is not None:
                        self.strength_max['B'] = imax
            # Auto-follow strength limit
            for ch in ['A', 'B']:
                limit = self.get_upper_strength(ch)
                if self.strength[ch] != 0 and self.strength[ch] != limit:
                    await self.set_strength(ch, value=limit)

        elif event_type == 'custom.action':
            action = data.get('action', -1)
            logger.info(f'[v4] Device {self.client_id} custom action: {action}')

        else:
            logger.debug(f'[v4] Device {self.client_id} unknown event: {event_type}')

    def _handle_response(self, data: dict):
        """Handle RPC responses. Currently we fire-and-forget, so just log."""
        req_id = data.get('reqId', '')
        if 'error' in data:
            logger.warning(f'[v4] Device {self.client_id} RPC error: reqId={req_id} error={data["error"]}')
        else:
            result = data.get('result', {})
            logger.debug(f'[v4] Device {self.client_id} RPC response: reqId={req_id} result={result}')

    async def connection_init(self):
        """Initialize after connection is established."""
        await asyncio.sleep(1)
        # Request device list
        await self._send_rpc('devices.get')

    async def close(self):
        """Close the connection."""
        self._closed = True
        WS_CONNECTIONS.discard(self)

    @classmethod
    async def broadcast_wave(cls, channel='A', wavestr=None):
        """Broadcast wave to all V4 connections."""
        if cls.wave_observer is not None:
            try:
                cls.wave_observer(channel, wavestr)
            except Exception:
                logger.exception('[v4] wave_observer failed')
        for conn in list(WS_CONNECTIONS):
            if isinstance(conn, cls):
                await conn.send_wave(channel=channel, wavestr=wavestr)

    @classmethod
    async def broadcast_clear_wave(cls, channel='A'):
        """Broadcast clear to all V4 connections."""
        if cls._suppress_clear:
            return
        if cls.clear_observer is not None:
            try:
                cls.clear_observer(channel)
            except Exception:
                logger.exception('[v4] clear_observer failed')
        for conn in list(WS_CONNECTIONS):
            if isinstance(conn, cls):
                await conn.clear_wave(channel=channel)

    @classmethod
    def refresh_limits_from_settings(cls, settings: dict):
        """Refresh strength limits from settings for all V4 connections."""
        limit_a = settings['dglab3']['channel_a']['strength_limit']
        limit_b = settings['dglab3']['channel_b']['strength_limit']
        overlimit_a = settings['dglab3']['channel_a'].get('overlimit_max', 20)
        overlimit_b = settings['dglab3']['channel_b'].get('overlimit_max', 20)
        for conn in list(WS_CONNECTIONS):
            if isinstance(conn, cls):
                conn.strength_limit['A'] = limit_a
                conn.strength_limit['B'] = limit_b
                conn.overlimit_max['A'] = overlimit_a
                conn.overlimit_max['B'] = overlimit_b


class DGV4RelayServer:
    """
    V4 Relay Server implemented as a FastAPI WebSocket endpoint.

    Acts as both the relay server and the controller.
    DG-LAB APP connects to us with ?tid=<controller_id>.
    We generate a stable controller_id and present it in the QR code.
    """

    def __init__(self, settings: dict):
        self.settings = settings
        self.controller_id = self._generate_controller_id()
        self.clients: dict[str, DGV4Connection] = {}  # client_id -> connection
        self._heartbeat_task = None

    def _generate_controller_id(self) -> str:
        """Generate a short hex client ID for the controller (us)."""
        return uuid.uuid4().hex[:8]

    def regenerate_controller_id(self):
        """Regenerate controller ID (e.g., on settings change)."""
        self.controller_id = self._generate_controller_id()

    def get_qr_content(self, server_ip: str, port: int) -> str:
        """Generate V4 QR code content for DG-LAB APP to scan."""
        import urllib.parse
        ws_url = f'ws://{server_ip}:{port}/ws/dglab-v4?tid={self.controller_id}'
        return f'https://dungeon-lab.cn/s/?v=1&action=socket&url={urllib.parse.quote(ws_url, safe="")}'

    async def handle_websocket(self, websocket, tid: str = None):
        """
        Handle a new WebSocket connection.

        If tid matches our controller_id, this is a controlled APP client.
        Otherwise reject.
        """
        from fastapi import WebSocket as FastAPIWebSocket

        # Generate client ID for this connection
        client_id = uuid.uuid4().hex[:8]

        if tid is None:
            # No tid = someone trying to connect as controller (not supported in our model)
            # We ARE the controller; send hello and close
            await websocket.send_text(json.dumps({
                'type': 'hello',
                'clientId': client_id,
            }))
            await websocket.send_text(json.dumps({
                'type': 'error',
                'code': 'not_supported',
                'message': 'This server only accepts controlled clients with ?tid parameter',
            }))
            await websocket.close(4001, 'controller_not_supported')
            return

        if tid != self.controller_id:
            # Wrong controller ID
            await websocket.send_text(json.dumps({
                'type': 'hello',
                'clientId': client_id,
            }))
            await websocket.send_text(json.dumps({
                'type': 'error',
                'code': 'controller_not_found',
            }))
            await websocket.close(4001, 'controller_not_found')
            logger.warning(f'[v4] Rejected client {client_id}: tid={tid} does not match {self.controller_id}')
            return

        # Valid controlled client connecting to us
        await websocket.send_text(json.dumps({
            'type': 'hello',
            'clientId': client_id,
        }))
        await websocket.send_text(json.dumps({
            'type': 'controller_attached',
            'clientId': self.controller_id,
        }))

        # Create connection object
        conn = DGV4Connection(websocket, client_id, self.settings)
        self.clients[client_id] = conn

        logger.success(f'[v4] APP connected: {client_id} (slot target: {tid})')

        # Start initialization
        asyncio.create_task(conn.connection_init())

        try:
            while True:
                raw = await websocket.receive_text()
                logger.debug(f'[v4] Device {client_id} recv: {raw}')

                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning(f'[v4] Device {client_id} invalid JSON')
                    continue

                msg_type = msg.get('type')

                if msg_type == 'ping':
                    await websocket.send_text(json.dumps({'type': 'pong', 'ts': int(time.time() * 1000)}))
                elif msg_type == 'pong':
                    pass  # Response to our ping
                elif msg_type == 'message':
                    # APP sending us data via relay frame
                    data = msg.get('data')
                    if data:
                        await conn._handle_message(data)
                elif msg_type == 'heartbeat':
                    pass
                else:
                    logger.debug(f'[v4] Device {client_id} unknown frame type: {msg_type}')

        except Exception as e:
            # WebSocket disconnected or error
            logger.warning(f'[v4] APP disconnected: {client_id} ({type(e).__name__})')
        finally:
            await conn.close()
            self.clients.pop(client_id, None)
            logger.info(f'[v4] Cleaned up: {client_id}, remaining: {len(self.clients)}')

    async def broadcast_heartbeat(self):
        """Send heartbeat to all connected clients."""
        payload = json.dumps({'type': 'heartbeat'})
        for client_id, conn in list(self.clients.items()):
            if conn._closed:
                continue
            try:
                await conn.ws_conn.send_text(payload)
            except Exception:
                pass

    async def heartbeat_loop(self, stop_event: asyncio.Event):
        """Background heartbeat loop."""
        while not stop_event.is_set():
            try:
                await asyncio.sleep(V4_HEARTBEAT_INTERVAL)
            except asyncio.CancelledError:
                return
            await self.broadcast_heartbeat()
