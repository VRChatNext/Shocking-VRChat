import json, uuid, traceback, asyncio
from loguru import logger
import websockets
from websockets.legacy.protocol import WebSocketCommonProtocol

from srv import WS_CONNECTIONS, DEFAULT_WAVE #, WS_CONNECTIONS_ID_REVERSE, WS_BINDS

class DGWSMessage():
    HEARTBEAT = json.dumps({'type': 'heartbeat', 'clientId': '', 'targetId': '', 'message': '200'})
    def __init__(self, type, clientId="", targetId="", message="") -> None:
        self.type = type
        self.clientId = clientId
        self.targetId = targetId
        self.message = message
    
    def __str__(self) -> str:
        return json.dumps({
            'type': self.type,
            'clientId': self.clientId,
            'targetId': self.targetId,
            'message': str(self.message),
        })
    async def send(self, conn):
        msg = self.__str__()
        logger.debug(f'ID {conn.uuid}, SENDING {msg}')
        ret = await conn.ws_conn.send(msg)
        return ret

class DGConnection():
    def __init__(self, ws_connection: WebSocketCommonProtocol, client_uuid=None, SETTINGS:dict=None) -> None:
        if SETTINGS is None:
            raise ValueError("DGConnection SETTINGS not provided.")
        self.ws_conn = ws_connection
        if client_uuid is None:
            client_uuid = ws_connection.id
        self.uuid = str(client_uuid)

        self.SETTINGS = SETTINGS
        self.master_uuid = SETTINGS['ws']['master_uuid']

        limit_a = SETTINGS['dglab3']['channel_a']['strength_limit']
        limit_b = SETTINGS['dglab3']['channel_b']['strength_limit']

        self.strength       = {'A':0, 'B':0}
        self.strength_max   = {'A':0, 'B':0}
        self.strength_limit = {'A':limit_a, 'B':limit_b}

        WS_CONNECTIONS.add(self)
        # WS_CONNECTIONS_ID_REVERSE[self.uuid] = self
    
    def __str__(self):
        return f"<DGConnection (id:{self.uuid}, {self.strength}, max {self.strength_max})>"
    
    async def msg_handler(self, msg: DGWSMessage):
        if msg.type == 'bind':
            # APP send bind request
            # WS_BINDS[self] = WS_CONNECTIONS_ID_REVERSE[msg.targetId] 
            assert msg.targetId == self.uuid, "UUID mismatch."
            assert msg.clientId == self.master_uuid, "Binding to unknown uuid."
            ret = DGWSMessage('bind', clientId=msg.clientId, targetId=msg.targetId, message='200')
            await ret.send(self)
        elif msg.type == 'msg':
            # 跟随强度变化
            if msg.message.startswith('strength-'):
                self.strength['A'], self.strength['B'], self.strength_max['A'], self.strength_max['B'] = map(int, msg.message[len('strength-'):].split('+'))
                for chann in ['A', 'B']:
                    limit = self.get_upper_strength(chann)
                    if (self.strength[chann] != 0 and self.strength[chann] != limit):
                        await self.set_strength(chann, value=limit)
            elif msg.message.startswith('feedback-'):
                logger.success(f'ID {self.uuid}, {msg.message}')
            else:
                logger.error(f'ID {self.uuid}, unknown msg {msg.message}')
        elif msg.type == 'heartbeat':
            logger.info(f'ID {self.uuid}, RECV HB')
    
    def get_upper_strength(self, channel='A'):
        return min(self.strength_max[channel], self.strength_limit[channel])

    async def set_strength(self, channel='A', mode='2', value=0, force=False):
        if not force:
            if value < 0 or value > 200:
                raise ValueError()
            limit = self.get_upper_strength(channel)
            if value > int(limit) and mode == '2':
                logger.warning(f'ID {self.uuid}, set_strength, {value} is over the limit {limit}, setting to {limit}.')
                value = limit
        if mode == '2':
            self.strength[channel] = value
        logger.info(f"Channel {channel}, set strength, mode {mode}, value {value}.")
        msg = DGWSMessage('msg', self.master_uuid, self.uuid, f"strength-{'1' if channel == 'A' else '2'}+{mode}+{value}")
        await msg.send(self)

    async def set_strength_0_to_1(self, channel='A', value=0):
        if value < 0 or value > 1:
            raise ValueError()
        limit = self.get_upper_strength(channel)
        strength = int(limit * value)
        await self.set_strength(channel=channel, mode='2', value=strength)

    async def send_wave(self, channel='A', wavestr=DEFAULT_WAVE):
        msg = DGWSMessage('msg', self.master_uuid, self.uuid, f"pulse-{channel}:{wavestr}")
        await msg.send(self)
    
    async def clear_wave(self, channel='A'):
        channel = '1' if channel == 'A' else '2'
        msg = DGWSMessage('msg', self.master_uuid, self.uuid, f"clear-{channel}")
        await msg.send(self)
    
    async def send_err(self, type=''):
        msg = DGWSMessage(type, )
    
    async def heartbeat(self):
        while 1:
            await asyncio.sleep(60)
            logger.info(f'ID {self.uuid}, Sending HB.')
            await self.ws_conn.send(DGWSMessage.HEARTBEAT)
    
    async def connection_init(self):
        await asyncio.sleep(2)
        await self.set_strength('A', value=1, force=True)
        await self.set_strength('B', value=1, force=True)

    async def serve(self):
        logger.info(f'New WS conn, id {self.uuid}.')
        msg = DGWSMessage('bind', clientId=str(self.uuid), targetId='', message='targetId')
        await msg.send(self)
        asyncio.create_task(self.connection_init())
        try:
            hb = asyncio.ensure_future(self.heartbeat())
            async for message in self.ws_conn:
                logger.debug(f'WSID {self.uuid}, RECVMSG {message}.')
                event = json.loads(message)
                msg = DGWSMessage(**event)
                try:
                    await self.msg_handler(msg)
                except Exception as e:
                    logger.error(traceback.format_exc())
                    DGWSMessage('error',message='500')
            await self.ws_conn.wait_closed()
        finally:
            logger.warning(f'ID {self.uuid} CLOSED.')
            hb.cancel()
            WS_CONNECTIONS.remove(self)

    @classmethod
    async def broadcast_wave(cls, channel='A', wavestr=DEFAULT_WAVE):
        for conn in WS_CONNECTIONS:
            conn : cls
            await conn.send_wave(channel=channel, wavestr=wavestr)

    @classmethod
    async def broadcast_clear_wave(cls, channel='A'):
        for conn in WS_CONNECTIONS:
            conn : cls
            await conn.clear_wave(channel=channel)
    
    @classmethod
    async def broadcast_strength_0_to_1(cls, channel='A', value=0):
        for conn in WS_CONNECTIONS:
            conn : cls
            await conn.set_strength_0_to_1(channel=channel, value=value)