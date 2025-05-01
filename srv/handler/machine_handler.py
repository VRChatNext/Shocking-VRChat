from . base_handler import BaseHandler
from ..connector.machine_tuya_cloud import TuYaConnection
import asyncio, time, math
from loguru import logger

# 处理设备 (Tuya) 的 OSC 消息处理器
class TuyaHandler(BaseHandler):
    def __init__(self, SETTINGS: dict, DEV_CONN: TuYaConnection) -> None:
        """
        初始化 TuyaHandler。

        Args:
            SETTINGS (dict): 全局配置字典。
            DEV_CONN (TuYaConnection): tuya设备连接实例。
        """
        self.SETTINGS = SETTINGS
        self.DEV_CONN = DEV_CONN
        # 获取 machine.tuya 部分的配置
        self.settings = SETTINGS['machine']['tuya']
        # 获取模式相关的配置
        self.mode_config = self.settings['mode_config']

        # 获取当前配置的工作模式
        self.mode = self.settings['mode']

        # 根据模式选择具体的处理函数
        if self.mode == 'level':
            self._handler = self.handler_level # 将 BaseHandler 的 _handler 指向 level 处理函数
        else:
            # 如果配置了不支持的模式，则抛出错误
            raise ValueError(f"不支持的设备模式: {self.mode}")
        
        # Level 模式下，用于后台任务更新设备状态的时间窗口 (秒)
        self.distance_update_time_window = 0.2 # 注意: 变量名可能有点误导，实际用于 level 模式
        # Level 模式下，当前计算出的目标强度 (0-1)
        self.distance_current_strength = 0

        # 用于超时自动清除状态的时间戳
        self.to_clear_time = 0
        # 标记当前是否处于已清除状态 (即无 OSC 输入一段时间后)
        self.is_cleared = True
    
    def start_background_jobs(self):
        """
        启动此 Handler 所需的后台异步任务。
        通常在主程序初始化时调用。
        """
        # logger.info(f"Channel: {self.channel}, background job started.") # channel 属性可能不存在
        logger.info(f"启动tuya设备 ({self.DEV_CONN.device_ids}) 的后台任务 (模式: {self.mode})。")
        # 启动超时检查任务
        asyncio.ensure_future(self.clear_check())
        # 如果是 level 模式，启动后台更新设备档位的任务
        if self.mode == 'level':
            asyncio.ensure_future(self.distance_background_wave_feeder())

    async def clear_check(self):
        """
        后台任务：检查是否超时无 OSC 输入。
        如果超时，则将设备档位重置为 1。
        """
        # logger.info(f'Channel {self.channel} started clear check.')
        logger.info(f"tuya设备 ({self.DEV_CONN.device_ids}) 超时检查任务已启动。")
        sleep_time = 0.05 # 检查间隔
        while 1:
            await asyncio.sleep(sleep_time)
            current_time = time.time()
            # logger.debug(f"{str(self.is_cleared)}, {current_time}, {self.to_clear_time}")
            # 如果当前未清除且已超过设定的清除时间
            if not self.is_cleared and current_time > self.to_clear_time:
                self.is_cleared = True
                self.level_current = 1 # 重置内部状态 (level_current 似乎未在其他地方使用)
                await self.DEV_CONN.set_level(1) # 将设备档位设置为 1
                logger.info(f'tuya设备 ({self.DEV_CONN.device_ids}) 超时，已自动将档位设置为 1。')

    async def set_clear_after(self, val):
        """
        设置一个未来的时间点，用于超时检查。
        每次接收到 OSC 消息时调用此方法，以推迟自动清除。

        Args:
            val (float): 延迟多少秒后清除 (从当前时间算起)。
        """
        self.is_cleared = False # 标记为未清除状态
        self.to_clear_time = time.time() + val # 计算清除时间点

    async def handler_level(self, distance):
        """
        Level 模式的 OSC 消息处理逻辑。
        将输入的距离值 (0-1) 转换为目标强度。

        Args:
            distance (float): 经过 BaseHandler 清理后的 OSC 参数值 (0-1)。
        """
        # 收到消息，推迟 5 秒清除
        await self.set_clear_after(5)
        strength = 0 # 默认为 0 强度
        # 获取配置的触发阈值
        trigger_bottom = self.mode_config['trigger_range']['bottom']
        trigger_top = self.mode_config['trigger_range']['top']
        # 如果输入值大于触发下界
        if distance > trigger_bottom:
            # 在上下界之间进行线性插值计算强度
            # 防止除以零
            if trigger_top - trigger_bottom > 0:
                strength = (
                        distance - trigger_bottom
                    ) / (
                        trigger_top - trigger_bottom
                    )
            else:
                # 如果上下界相等且大于下界，则直接设为 1
                strength = 1
            # 限制强度最大为 1
            strength = min(strength, 1.0)

        # 更新当前的目标强度，供后台任务使用
        self.distance_current_strength = strength

    async def distance_background_wave_feeder(self):
        """
        后台任务 (Level 模式): 周期性地根据计算出的强度更新设备档位。
        """
        logger.info(f"tuya设备 ({self.DEV_CONN.device_ids}) Level 模式后台档位更新任务已启动。")
        # 计算每次检查的间隔时间
        # 注意: 这个 tick_time_window 似乎过小 (0.2 / 20 = 0.01s)，可能导致过于频繁的检查和潜在的 API 调用
        # 建议直接使用 self.distance_update_time_window 或一个更合理的值
        tick_time_window = self.distance_update_time_window # 使用原始窗口时间作为间隔
        next_tick_time = 0
        last_level = 0 # 记录上次设置的档位，避免重复发送相同指令
        while 1:
            current_time = time.time()
            # 如果未到下次更新时间，则短暂休眠后继续循环
            if current_time < next_tick_time:
                await asyncio.sleep(tick_time_window / 5) # 稍微减少休眠时间以提高响应性
                continue
            # 计算下次更新时间点
            next_tick_time = current_time + self.distance_update_time_window

            # 获取当前计算出的强度
            current_strength = self.distance_current_strength
            # 根据强度和配置中的最大档位计算目标档位 (向上取整)
            # !! 注意: 配置中需要有 'level_max' 字段
            level_max = self.mode_config.get('level_max', 1) # 从配置读取最大档位，默认为 1
            if level_max <= 0: level_max = 1 # 防止配置错误
            # 如果强度为 0，目标档位为 0 (但 TuyaConnection 会处理为 1)
            current_level = math.ceil(level_max * current_strength) if current_strength > 0 else 0

            # 如果计算出的目标档位与上次设置的相同，则无需操作
            if last_level == current_level:
                continue

            # 记录日志并发送设置档位的指令
            logger.success(f'tuya设备 ({self.DEV_CONN.device_ids}), 强度 {current_strength:.3f}, 设置档位 {current_level}')
            last_level = current_level # 更新上次设置的档位
            await self.DEV_CONN.set_level(current_level) # 调用连接对象的方法设置设备档位
    