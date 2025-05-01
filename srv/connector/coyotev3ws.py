import json, uuid, traceback, asyncio
from loguru import logger
import websockets
from websockets.legacy.protocol import WebSocketCommonProtocol

from srv import WS_CONNECTIONS, DEFAULT_WAVE #, WS_CONNECTIONS_ID_REVERSE, WS_BINDS

# 表示 DG-LAB WebSocket 协议消息的类
class DGWSMessage():
    # 预定义的标准心跳消息 JSON 字符串
    HEARTBEAT = json.dumps({'type': 'heartbeat', 'clientId': '', 'targetId': '', 'message': '200'})

    def __init__(self, type: str, clientId: str ="", targetId: str ="", message: str ="") -> None:
        """
        初始化 DGWSMessage 对象。

        Args:
            type (str): 消息类型 (如 'bind', 'msg', 'heartbeat', 'error')。
            clientId (str, optional): 发送方 ID (通常是 Master UUID 或设备 UUID)。 Defaults to "".
            targetId (str, optional): 接收方 ID (通常是 Master UUID 或设备 UUID)。 Defaults to "".
            message (str, optional): 消息内容。 Defaults to "".
        """
        self.type = type
        self.clientId = clientId
        self.targetId = targetId
        self.message = message
    
    def __str__(self) -> str:
        """
        将消息对象转换为符合 DG-LAB 协议的 JSON 字符串。
        """
        return json.dumps({
            'type': self.type,
            'clientId': self.clientId,
            'targetId': self.targetId,
            'message': str(self.message), # 确保 message 是字符串
        })
    async def send(self, conn):
        """
        通过指定的 WebSocket 连接发送此消息。

        Args:
            conn (DGConnection): 要发送消息的目标连接对象。

        Returns:
            Any: WebSocket 发送操作的返回值。
        """
        msg = self.__str__() # 获取 JSON 字符串
        logger.debug(f'ID {conn.uuid}, SENDING {msg}') # 记录发送日志
        # 调用连接对象的 WebSocket 连接发送消息
        ret = await conn.ws_conn.send(msg)
        return ret

# 管理单个 DG-LAB 设备 WebSocket 连接的类
class DGConnection():
    def __init__(self, ws_connection: WebSocketCommonProtocol, client_uuid=None, SETTINGS:dict=None) -> None:
        """
        初始化 DGConnection 对象。

        Args:
            ws_connection (WebSocketCommonProtocol): websockets 库的连接对象。
            client_uuid (str, optional): 此连接的客户端 UUID (通常是设备 UUID)。 如果为 None，则使用 ws_connection.id。
            SETTINGS (dict, optional): 全局配置字典。 Defaults to None。

        Raises:
            ValueError: 如果未提供 SETTINGS。
        """
        if SETTINGS is None:
            raise ValueError("DGConnection 初始化时必须提供 SETTINGS")
        self.ws_conn = ws_connection # WebSocket 连接实例
        if client_uuid is None:
            # 如果未指定 UUID，则使用 WebSocket 连接的 ID (可能是随机生成的)
            client_uuid = ws_connection.id
        self.uuid = str(client_uuid) # 连接 (设备) 的 UUID

        self.SETTINGS = SETTINGS # 全局配置
        self.master_uuid = SETTINGS['ws']['master_uuid'] # 控制端的 Master UUID

        # 从配置中读取该设备两个通道的强度限制
        limit_a = SETTINGS['dglab3']['channel_a']['strength_limit']
        limit_b = SETTINGS['dglab3']['channel_b']['strength_limit']

        # 存储设备状态
        self.strength = {'A': 0, 'B': 0} # 设备当前强度 (由 APP 同步或程序设置)
        self.strength_max = {'A': 0, 'B': 0} # 设备报告的最大可用强度 (由 APP 设置)
        self.strength_limit = {'A': limit_a, 'B': limit_b} # 程序配置的强度上限

        # 将此连接实例添加到全局连接集合中
        WS_CONNECTIONS.add(self)
        logger.info(f"添加新连接到全局集合: {self.uuid}, 当前总数: {len(WS_CONNECTIONS)}")
        # WS_CONNECTIONS_ID_REVERSE[self.uuid] = self # 反向查找字典 (已注释掉)
    
    def __str__(self):
        """
        返回连接对象的字符串表示，方便调试。
        """
        return f"<DGConnection (id:{self.uuid}, strength:{self.strength}, max:{self.strength_max})>"
    
    async def msg_handler(self, msg: DGWSMessage):
        """
        处理从 WebSocket 客户端 (DG-LAB APP) 收到的消息。

        Args:
            msg (DGWSMessage): 解析后的消息对象。
        """
        if msg.type == 'bind':
            # 处理绑定请求
            # APP 发送绑定请求，将 APP (clientId=Master UUID) 与此设备连接 (targetId=设备 UUID) 绑定
            # WS_BINDS[self] = WS_CONNECTIONS_ID_REVERSE[msg.targetId] # 绑定逻辑 (已注释掉)
            # 校验 targetId 是否与当前连接的 UUID 匹配
            assert msg.targetId == self.uuid, f"绑定请求的 targetId ({msg.targetId}) 与连接 UUID ({self.uuid}) 不匹配。"
            # 校验 clientId 是否为配置的 Master UUID
            assert msg.clientId == self.master_uuid, f"尝试绑定到未知的 Master UUID: {msg.clientId}。"
            # 发送绑定成功响应
            ret = DGWSMessage('bind', clientId=msg.clientId, targetId=msg.targetId, message='200')
            logger.success(f"设备 {self.uuid} 绑定成功。")
            await ret.send(self)
        elif msg.type == 'msg':
            # 处理普通消息
            if msg.message.startswith('strength-'):
                # 处理 APP 同步的强度信息
                # 格式: strength-强度A+强度B+最大强度A+最大强度B
                try:
                    # 解析强度值
                    s_a, s_b, max_a, max_b = map(int, msg.message[len('strength-'):].split('+'))
                    # 更新内部状态
                    self.strength['A'], self.strength['B'] = s_a, s_b
                    self.strength_max['A'], self.strength_max['B'] = max_a, max_b
                    logger.info(f"设备 {self.uuid} 同步强度: A={s_a}/{max_a}, B={s_b}/{max_b}")

                    # (关键逻辑) 检查 APP 设置的强度是否超过程序限制，如果超过，则强制设置回限制值
                    # 这实现了"逃生通道"功能：当用户在 APP 上将强度设置为 0 后，程序不再覆盖；
                    # 当用户在 APP 上将强度增加到大于 0 时，程序会再次强制应用上限。
                    for chann in ['A', 'B']:
                        # 获取该通道最终的强度上限 (程序限制和设备最大值中的较小者)
                        limit = self.get_upper_strength(chann)
                        # 如果 APP 当前设置的强度不为 0，且不等于最终上限
                        if (self.strength[chann] != 0 and self.strength[chann] != limit):
                            logger.warning(f"设备 {self.uuid} 通道 {chann} 的强度 ({self.strength[chann]}) 与上限 ({limit}) 不符，将强制设置为上限。")
                            # 强制将设备强度设置为计算出的上限值
                            await self.set_strength(chann, value=limit)
                except ValueError as e:
                    logger.error(f"解析设备 {self.uuid} 的强度消息失败: {msg.message}, 错误: {e}")
            elif msg.message.startswith('feedback-'):
                # 处理反馈消息 (例如执行结果)
                logger.success(f'收到设备 {self.uuid} 的反馈: {msg.message}')
            else:
                # 未知消息类型
                logger.error(f'收到设备 {self.uuid} 的未知消息: {msg.message}')
        elif msg.type == 'heartbeat':
            # 收到心跳消息
            logger.info(f'收到设备 {self.uuid} 的心跳响应。')
    
    def get_upper_strength(self, channel='A') -> int:
        """
        计算指定通道的最终强度上限。
        取设备报告的最大强度 (APP 设置) 和程序配置的强度限制中的较小值。

        Args:
            channel (str, optional): 通道 ('A' 或 'B')。 Defaults to 'A'.

        Returns:
            int: 该通道允许设置的最大强度值。
        """
        return min(self.strength_max[channel], self.strength_limit[channel])

    async def set_strength(self, channel='A', mode='2', value=0, force=False):
        """
        向设备发送设置强度的指令。

        Args:
            channel (str, optional): 通道 ('A' 或 'B')。 Defaults to 'A'.
            mode (str, optional): 设置模式 ('1': 减少, '2': 设置绝对值, '3': 增加)。 Defaults to '2'.
            value (int, optional): 强度值。 Defaults to 0。
            force (bool, optional): 是否忽略强度上限检查。 Defaults to False。
        """
        if not force:
            # 检查 value 是否在合理范围 (0-200, 实际可能取决于设备)
            if not (0 <= value <= 200): 
                logger.warning(f"尝试为设备 {self.uuid} 通道 {channel} 设置无效强度值: {value}，已忽略。")
                raise ValueError(f"强度值 {value} 超出范围 (0-200)")
                #return # 或者直接返回，不发送指令
            # 获取该通道的强度上限
            limit = self.get_upper_strength(channel)
            # 如果设置的值超过上限，并且是绝对值模式 ('2')
            if value > int(limit) and mode == '2':
                logger.warning(f'设备 {self.uuid} 通道 {channel} 设置强度 {value} 超过上限 {limit}, 将自动限制为 {limit}。')
                value = limit # 将值限制在上限内

        # 如果是设置绝对值模式，更新内部记录的当前强度
        # 注意：这可能与 APP 同步的 self.strength 产生竞争，取决于调用时机
        if mode == '2':
            self.strength[channel] = value

        # 构建设置强度的消息
        # 消息格式: strength-[通道号]+[模式]+[值]
        # 通道号: A -> 1, B -> 2
        logger.info(f"向设备 {self.uuid} 发送指令: 通道 {channel}, 模式 {mode}, 强度 {value}。")
        msg = DGWSMessage('msg', self.master_uuid, self.uuid, f"strength-{'1' if channel == 'A' else '2'}+{mode}+{value}")
        # 发送消息
        await msg.send(self)

    async def set_strength_0_to_1(self, channel='A', value=0):
        """
        根据 0 到 1 的归一化强度值设置设备强度。
        将归一化值乘以最终强度上限，然后调用 set_strength。

        Args:
            channel (str, optional): 通道 ('A' 或 'B')。 Defaults to 'A'.
            value (float, optional): 归一化的强度值 (0.0 到 1.0)。 Defaults to 0.
        """
        if not (0 <= value <= 1):
            raise ValueError(f"归一化强度值 {value} 超出范围 (0-1)")
        # 获取强度上限
        limit = self.get_upper_strength(channel)
        # 计算实际强度值
        strength = int(limit * value)
        # 调用 set_strength 设置绝对值
        await self.set_strength(channel=channel, mode='2', value=strength)

    async def send_wave(self, channel='A', wavestr=DEFAULT_WAVE):
        """
        向设备发送波形数据。

        Args:
            channel (str, optional): 目标通道 ('A' 或 'B')。 Defaults to 'A'.
            wavestr (str, optional): 波形 JSON 字符串。 Defaults to DEFAULT_WAVE。
        """
        # 消息格式: pulse-[通道]:[波形JSON]
        msg = DGWSMessage('msg', self.master_uuid, self.uuid, f"pulse-{channel}:{wavestr}")
        await msg.send(self)
    
    async def clear_wave(self, channel='A'):
        """
        向设备发送清除指定通道波形的指令。

        Args:
            channel (str, optional): 目标通道 ('A' 或 'B')。 Defaults to 'A'.
        """
        # 消息格式: clear-[通道号]
        channel_num = '1' if channel == 'A' else '2'
        msg = DGWSMessage('msg', self.master_uuid, self.uuid, f"clear-{channel_num}")
        await msg.send(self)
    
    async def send_err(self, type=''):
        """
        (未使用) 发送错误消息。
        """
        # 原始实现不完整
        # msg = DGWSMessage(type, )
        pass

    async def heartbeat(self):
        """
        后台任务：定期向设备发送心跳消息以保持连接。
        """
        while 1:
            # 每 60 秒发送一次心跳
            await asyncio.sleep(60)
            logger.info(f'向设备 {self.uuid} 发送心跳包。')
            # 直接发送预定义的 HEARTBEAT 消息
            try:
                 await self.ws_conn.send(DGWSMessage.HEARTBEAT)
            except websockets.exceptions.ConnectionClosed:
                 logger.warning(f"设备 {self.uuid} 的心跳任务检测到连接已关闭，将停止。")
                 break # 连接关闭，退出心跳循环
            except Exception as e:
                 logger.error(f"发送心跳到设备 {self.uuid} 时出错: {e}")
                 # 可以考虑在这里也退出循环或增加重试逻辑

    async def connection_init(self):
        """
        连接建立后的初始化操作。
        延迟 2 秒后，尝试将设备强度设置为 1 (force=True 忽略上限)。
        这有助于确保设备在连接后处于一个已知的非零状态，以便后续的强度控制生效。
        """
        await asyncio.sleep(2) # 等待一段时间，确保绑定等操作完成
        logger.info(f"初始化设备 {self.uuid} 连接，设置初始强度...")
        try:
             await self.set_strength('A', value=1, force=True)
             await self.set_strength('B', value=1, force=True)
        except Exception as e:
             logger.error(f"初始化设备 {self.uuid} 强度失败: {e}")

    async def serve(self):
        """
        处理单个 WebSocket 连接的主循环。
        - 发送初始绑定消息。
        - 启动心跳和初始化任务。
        - 循环接收、解析和处理来自客户端的消息。
        - 处理连接关闭和异常。
        """
        logger.info(f'新的 WebSocket 连接已建立: ID {self.uuid}。')
        # 发送初始绑定消息，告知客户端其 UUID (targetId)
        msg = DGWSMessage('bind', clientId=str(self.uuid), targetId='', message='targetId')
        await msg.send(self)
        # 启动连接初始化任务
        init_task = asyncio.create_task(self.connection_init())
        hb_task = None
        try:
            # 启动心跳任务
            hb_task = asyncio.ensure_future(self.heartbeat())
            # 循环处理接收到的消息
            async for message in self.ws_conn:
                logger.debug(f'WSID {self.uuid}, RECVMSG {message}.')
                try:
                    # 解析 JSON 消息
                    event = json.loads(message)
                    # 创建 DGWSMessage 对象
                    msg = DGWSMessage(**event)
                    # 调用消息处理器
                    await self.msg_handler(msg)
                except json.JSONDecodeError as e:
                    logger.error(f"解析来自设备 {self.uuid} 的 JSON 消息失败: {e}, 原始消息: {message}")
                except AssertionError as e:
                    logger.error(f"处理来自设备 {self.uuid} 的消息时断言失败: {e}")
                    # 可以考虑发送错误消息给客户端或关闭连接
                    # await DGWSMessage('error', message=str(e)).send(self)
                except Exception as e:
                    # 捕获 msg_handler 中的其他异常
                    logger.error(f"处理来自设备 {self.uuid} 的消息时发生错误: {traceback.format_exc()}")
                    # 尝试发送错误消息给客户端 (可能无效)
                    # DGWSMessage('error', message='500') # 这行代码没有发送
                    await DGWSMessage('error', clientId=self.master_uuid, targetId=self.uuid, message='500 Internal Server Error').send(self)

            # 等待 WebSocket 连接正常关闭
            await self.ws_conn.wait_closed()
            logger.info(f"设备 {self.uuid} 的 WebSocket 连接已正常关闭。")
        except websockets.exceptions.ConnectionClosedOK:
             logger.info(f"设备 {self.uuid} 的 WebSocket 连接已正常关闭 (OK)。")
        except websockets.exceptions.ConnectionClosedError as e:
             logger.warning(f"设备 {self.uuid} 的 WebSocket 连接异常关闭: Code={e.code}, Reason={e.reason}")
        except Exception as e:
             logger.error(f"处理设备 {self.uuid} 连接时发生未预料的错误: {traceback.format_exc()}")
        finally:
            # 连接关闭后的清理工作
            logger.warning(f'连接 {self.uuid} 已关闭，正在清理资源。')
            # 取消心跳任务
            if hb_task and not hb_task.done():
                hb_task.cancel()
            # 取消初始化任务 (如果还在运行)
            if init_task and not init_task.done():
                init_task.cancel()
            # 从全局连接集合中移除此连接
            if self in WS_CONNECTIONS:
                 WS_CONNECTIONS.remove(self)
                 logger.info(f"从全局集合中移除连接: {self.uuid}, 当前总数: {len(WS_CONNECTIONS)}")
            # WS_CONNECTIONS_ID_REVERSE.pop(self.uuid, None) # 清理反向查找字典

    # --- 类方法 --- (用于向所有连接广播)

    @classmethod
    async def broadcast_wave(cls, channel='A', wavestr=DEFAULT_WAVE):
        """
        向所有当前连接的 DGConnection 实例广播波形数据。

        Args:
            channel (str, optional): 目标通道 ('A' 或 'B')。 Defaults to 'A'.
            wavestr (str, optional): 波形 JSON 字符串。 Defaults to DEFAULT_WAVE。
        """
        logger.info(f"向 {len(WS_CONNECTIONS)} 个连接广播波形: 通道 {channel}, 波形 {wavestr[:50]}...")
        tasks = []
        for conn in WS_CONNECTIONS:
            # conn : cls # 类型提示 (在 Python 3.5+ 中不是必需的)
            tasks.append(conn.send_wave(channel=channel, wavestr=wavestr))
        # 并发执行所有发送任务
        if tasks:
             await asyncio.gather(*tasks, return_exceptions=True)

    @classmethod
    async def broadcast_clear_wave(cls, channel='A'):
        """
        向所有当前连接的 DGConnection 实例广播清除波形的指令。

        Args:
            channel (str, optional): 目标通道 ('A' 或 'B')。 Defaults to 'A'.
        """
        logger.info(f"向 {len(WS_CONNECTIONS)} 个连接广播清除波形指令: 通道 {channel}")
        tasks = []
        for conn in WS_CONNECTIONS:
            # conn : cls
            tasks.append(conn.clear_wave(channel=channel))
        if tasks:
             await asyncio.gather(*tasks, return_exceptions=True)

    @classmethod
    async def broadcast_strength_0_to_1(cls, channel='A', value=0):
        """
        向所有当前连接的 DGConnection 实例广播基于 0-1 归一化值的强度设置指令。

        Args:
            channel (str, optional): 目标通道 ('A' 或 'B')。 Defaults to 'A'.
            value (float, optional): 归一化的强度值 (0.0 到 1.0)。 Defaults to 0.
        """
        logger.info(f"向 {len(WS_CONNECTIONS)} 个连接广播归一化强度: 通道 {channel}, 值 {value:.3f}")
        tasks = []
        for conn in WS_CONNECTIONS:
            # conn : cls
            tasks.append(conn.set_strength_0_to_1(channel=channel, value=value))
        if tasks:
             await asyncio.gather(*tasks, return_exceptions=True)