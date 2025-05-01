import numpy as np
import collections
from .base_handler import BaseHandler
from loguru import logger
import time, asyncio, math, json

from ..connector.coyotev3ws import DGConnection

# 处理 DG-LAB Coyote 设备的 OSC 消息处理器
class ShockHandler(BaseHandler):
    def __init__(self, SETTINGS: dict, DG_CONN: DGConnection, channel_name: str) -> None:
        """
        初始化 ShockHandler。

        Args:
            SETTINGS (dict): 全局配置字典。
            DG_CONN (DGConnection): DG-LAB 连接类 (注意: 这里传入的是类本身, 因为使用了类方法广播)。
            channel_name (str): 此 Handler 实例负责的通道名称 ('A' 或 'B')。
        """
        self.SETTINGS = SETTINGS
        self.DG_CONN = DG_CONN # 存储 DGConnection 类
        self.channel = channel_name.upper() # 存储通道名 (大写)
        # 获取该通道的具体配置
        self.shock_settings = SETTINGS['dglab3'][f'channel_{channel_name.lower()}']
        # 获取该通道模式相关的配置
        self.mode_config = self.shock_settings['mode_config']

        # 获取当前配置的工作模式
        self.shock_mode = self.shock_settings['mode']

        # 根据配置的模式选择对应的处理函数
        if self.shock_mode == 'distance':
            self._handler = self.handler_distance
        elif self.shock_mode == 'shock':
            self._handler = self.handler_shock
        elif self.shock_mode == 'touch':
            self._handler = self.handler_touch
        else:
            # 如果配置了不支持的模式，则抛出错误
            raise ValueError(f"不支持的 Coyote 设备模式: {self.shock_mode}")
        
        self.bg_wave_update_time_window = 0.1
        self.bg_wave_current_strength = 0

        self.touch_dist_arr = collections.deque(maxlen=20)

        self.to_clear_time    = 0
        self.is_cleared       = True
    
    def start_background_jobs(self):
        """
        启动此 Handler 所需的后台异步任务。
        """
        logger.info(f"启动通道 {self.channel} 的后台任务 (模式: {self.shock_mode})。")
        # 启动超时清除波形任务
        asyncio.ensure_future(self.clear_check())
        # 注释掉: 持续发送固定波形的任务 (可能不需要)
        # if self.shock_mode == 'shock':
        #     asyncio.ensure_future(self.feed_wave())
        if self.shock_mode == 'distance':
            asyncio.ensure_future(self.distance_background_wave_feeder())
        elif self.shock_mode == 'touch':
            asyncio.ensure_future(self.touch_background_wave_feeder())

    def osc_handler(self, address, *args):
        """
        重写 BaseHandler 的 osc_handler 方法，添加调试日志。
        """
        # 添加针对此 Handler 的调试日志，显示通道和接收到的数据
        logger.debug(f"VRCOSC: 通道 {self.channel}: {address}: {args}")
        # 调用 BaseHandler 的参数清理方法
        val = self.param_sanitizer(args)
        # 异步执行具体的模式处理逻辑
        return asyncio.ensure_future(self._handler(val))

    async def clear_check(self):
        """
        后台任务：检查是否超时无 OSC 输入。
        如果超时，则广播清除该通道波形的命令。
        """
        logger.info(f'通道 {self.channel} 超时检查任务已启动。')
        sleep_time = 0.05 # 检查间隔
        while 1:
            await asyncio.sleep(sleep_time)
            current_time = time.time()
            # logger.debug(f"{str(self.is_cleared)}, {current_time}, {self.to_clear_time}")
            # 如果当前未清除且已超过设定的清除时间
            if not self.is_cleared and current_time > self.to_clear_time:
                self.is_cleared = True
                self.bg_wave_current_strength = 0 # 重置内部强度状态
                self.touch_dist_arr.clear() # 清空 touch 模式的数据队列
                # 广播清除波形指令到所有连接的设备
                await self.DG_CONN.broadcast_clear_wave(self.channel)
                logger.info(f'通道 {self.channel} 超时，已发送清除波形指令。')
    
    async def feed_wave(self):
        """
        (未使用/未完成) 后台任务：周期性地发送 shock 模式配置的固定波形。
        """
        raise NotImplementedError # 明确标记此方法未实现
        # logger.info(f'Channel {self.channel} started wave feeding.')
        # sleep_time = 1
        # while 1:
        #     await asyncio.sleep(sleep_time)
        #     await self.DG_CONN.broadcast_wave(channel=self.channel, wavestr=self.shock_settings['shock_wave'])

    async def set_clear_after(self, val):
        """
        设置一个未来的时间点，用于超时检查。
        每次接收到 OSC 消息时调用此方法，以推迟自动清除。

        Args:
            val (float): 延迟多少秒后清除 (从当前时间算起)。
        """
        self.is_cleared = False # 标记为未清除状态
        self.to_clear_time = time.time() + val # 计算清除时间点

    @staticmethod
    def generate_wave_100ms(freq: int, from_: float, to_: float) -> str:
        """
        静态方法，生成一个 100ms 的 Coyote V3 波形片段 JSON 字符串。
        该波形片段代表强度从 from_ (0-1) 线性变化到 to_ (0-1)。

        Args:
            freq (int): 波形频率参数 (通常对应配置中的 freq_ms)。
            from_ (float): 起始强度 (0.0 到 1.0)。
            to_ (float): 结束强度 (0.0 到 1.0)。

        Returns:
            str: 符合 Coyote V3 协议的波形 JSON 字符串，例如 '["0A0A0A0A324B647D"]'。
        """
        # 参数校验
        assert 0 <= from_ <= 1, "无效的起始强度值 (应在 0 到 1 之间)"
        assert 0 <= to_ <= 1, "无效的结束强度值 (应在 0 到 1 之间)"
        # 将 0-1 的浮点数强度转换为 0-100 的整数强度
        from_int = int(100 * from_)
        to_int = int(100 * to_)

        # 构建波形字符串
        # 前 4 个字节是频率参数 (十六进制)
        ret = ["{:02X}".format(freq)] * 4
        # 计算强度变化步长 (4 个步长)
        delta = (to_int - from_int) // 4
        # 生成后 4 个强度字节 (十六进制)，并确保值在 0-100 范围内
        ret += ["{:02X}".format(min(max(from_int + delta * i, 0), 100)) for i in range(1, 5, 1)]
        # 将列表合并成单个字符串
        wave_segment = ''.join(ret)
        # 封装成 JSON 数组格式 (Coyote 协议要求)
        # 使用 separators 去除空格，生成紧凑格式
        return json.dumps([wave_segment], separators=(',', ':'))
    
    def normalize_distance(self, distance: float) -> float:
        """
        根据配置中的 trigger_range (上下界) 将输入的距离值归一化到 0-1 范围。

        Args:
            distance (float): 原始 OSC 输入值。

        Returns:
            float: 归一化后的距离值 (0.0 到 1.0)。
        """
        out_distance = 0.0 # 默认为 0
        trigger_bottom = self.mode_config['trigger_range']['bottom']
        trigger_top = self.mode_config['trigger_range']['top']
        # 如果输入值大于触发下界
        if distance > trigger_bottom:
            # 计算上下界之间的差值
            range_diff = trigger_top - trigger_bottom
            # 防止除以零
            if range_diff > 0:
                # 在上下界之间进行线性插值
                out_distance = (distance - trigger_bottom) / range_diff
            else:
                # 如果上下界相等且输入值大于下界，则直接设为 1
                out_distance = 1.0
            # 限制归一化结果最大为 1.0
            out_distance = min(out_distance, 1.0)
        return out_distance

    async def handler_distance(self, distance: float):
        """
        Distance 模式的 OSC 消息处理逻辑。
        将归一化后的距离值存储起来，供后台任务使用。

        Args:
            distance (float): 经过 BaseHandler 清理后的 OSC 参数值 (0-1)。
        """
        # 收到消息，推迟 0.5 秒清除波形
        await self.set_clear_after(0.5)
        # 计算归一化距离并更新当前目标强度
        self.bg_wave_current_strength = self.normalize_distance(distance)

    async def distance_background_wave_feeder(self):
        """
        后台任务 (Distance 模式): 周期性地生成并广播波形，
        使得设备强度平滑地从上次的值过渡到当前计算出的目标强度。
        """
        logger.info(f"通道 {self.channel} Distance 模式后台波形更新任务已启动。")
        # 计算每次检查的间隔时间
        # tick_time_window = self.bg_wave_update_time_window / 20 # 原始实现，可能过小
        tick_time_window = self.bg_wave_update_time_window / 5 # 调整为更合理的间隔
        next_tick_time = 0
        last_strength = 0.0 # 记录上次发送波形时的结束强度
        while 1:
            current_time = time.time()
            # 如果未到下次更新时间，则休眠后继续
            if current_time < next_tick_time:
                await asyncio.sleep(tick_time_window)
                continue
            # 计算下次更新时间点
            next_tick_time = current_time + self.bg_wave_update_time_window

            # 获取当前计算出的目标强度
            current_strength = self.bg_wave_current_strength
            # 如果当前强度和上次强度都为 0，则无需发送波形
            if current_strength == 0 and last_strength == 0:
                continue

            # 生成从 last_strength 过渡到 current_strength 的 100ms 波形
            wave = self.generate_wave_100ms(
                self.mode_config['distance']['freq_ms'], # 使用配置的频率
                last_strength,
                current_strength
            )
            # 记录日志并广播波形
            logger.success(f'通道 {self.channel}, 强度 {last_strength:.3f} -> {current_strength:.3f}, 发送波形: {wave}')
            last_strength = current_strength # 更新上次强度
            await self.DG_CONN.broadcast_wave(self.channel, wavestr=wave)

    async def send_shock_wave(self, shock_time: float, shockwave: str):
        """
        异步任务：发送 shock 模式配置的固定波形，持续指定时间。

        Args:
            shock_time (float): 电击总持续时间（秒）。
            shockwave (str): 配置中定义的 shock 模式波形 JSON 字符串。
        """
        try:
            # 计算配置的波形 JSON 包含多少个 100ms 的片段
            # 如果 JSON 解析失败或格式不正确，则假定为 1 个片段 (100ms)
            wave_segments = json.loads(shockwave)
            if not isinstance(wave_segments, list):
                 raise json.JSONDecodeError("Wave format invalid", shockwave, 0)
            shockwave_duration = len(wave_segments) * 0.1 # 每个片段 100ms
            if shockwave_duration <= 0: shockwave_duration = 0.1 # 防止除零或负数
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"解析 shock 模式波形失败 ({e}), 将假定持续时间为 0.1 秒: {shockwave}")
            shockwave_duration = 0.1

        # 计算需要发送多少次配置的波形才能达到目标持续时间
        send_times = math.ceil(shock_time / shockwave_duration)
        logger.info(f"通道 {self.channel} 将发送 {send_times} 次 shock 波形 (每次持续 {shockwave_duration:.1f}s)。")

        # 循环发送波形
        for i in range(send_times):
            # 检查是否在此期间被新的 OSC 信号或超时取消了
            if self.is_cleared:
                logger.warning(f"通道 {self.channel} 的 shock 波形发送在第 {i+1} 次时被中断。")
                break
            await self.DG_CONN.broadcast_wave(self.channel, wavestr=shockwave)
            await asyncio.sleep(shockwave_duration) # 等待当前波形片段播放完毕
        logger.info(f"通道 {self.channel} 的 shock 波形发送完成。")

    async def handler_shock(self, distance: float):
        """
        Shock 模式的 OSC 消息处理逻辑。
        当输入值超过阈值且当前未处于电击状态时，触发一次固定时长的电击。

        Args:
            distance (float): 经过 BaseHandler 清理后的 OSC 参数值 (0-1)。
        """
        current_time = time.time()
        # 如果输入值大于触发下界，并且当前不处于延时清除状态 (即上一次 shock 已结束或从未开始)
        if distance > self.mode_config['trigger_range']['bottom'] and current_time > self.to_clear_time:
            # 获取配置的电击持续时间
            shock_duration = self.mode_config['shock']['duration']
            # 设置清除时间点，防止在本次电击期间被新的 OSC 消息重复触发
            await self.set_clear_after(shock_duration)
            logger.success(f'通道 {self.channel}: 触发电击，持续 {shock_duration} 秒。')
            # 创建一个后台任务来发送电击波形
            asyncio.create_task(self.send_shock_wave(shock_duration, self.mode_config['shock']['wave']))

    async def handler_touch(self, distance: float):
        """
        Touch 模式的 OSC 消息处理逻辑。
        记录归一化后的距离值和时间戳，供后台任务计算导数。

        Args:
            distance (float): 经过 BaseHandler 清理后的 OSC 参数值 (0-1)。
        """
        # 收到消息，推迟 0.5 秒清除波形
        await self.set_clear_after(0.5)
        # 归一化距离值
        out_distance = self.normalize_distance(distance)
        # 如果归一化后距离为 0，则忽略 (避免队列中充满 0)
        if out_distance == 0:
            return
        # 获取当前时间戳
        t = time.time()
        # 将 (时间戳, 归一化距离) 添加到队列末尾
        self.touch_dist_arr.append([t, out_distance])
    
    def compute_derivative(self) -> tuple[float, float, float, float]:
        """
        计算存储在 touch_dist_arr 中的距离时间序列的导数（速度、加速度、冲击力）。
        使用 NumPy 进行计算。

        Returns:
            tuple[float, float, float, float]: 包含 (距离, 速度, 加速度, 冲击力) 的元组。
                                               如果数据点不足，则返回 (0, 0, 0, 0)。
        """
        data = self.touch_dist_arr
        # 需要至少 4 个数据点才能计算三阶导数 (冲击力)
        if len(data) < 4:
            # logger.warning('计算加速度和冲击力至少需要 4 个样本点。')
            return 0.0, 0.0, 0.0, 0.0

        # 将队列数据转换为 NumPy 数组
        time_ = np.array([point[0] for point in data])
        distance = np.array([point[1] for point in data])

        # 可选：应用滑动平均滤波平滑距离数据，减少噪声影响
        window_size = 3
        if len(distance) >= window_size:
             distance = np.convolve(distance, np.ones(window_size) / window_size, mode='valid')
             # 滤波后时间戳数组需要截断以匹配长度
             time_ = time_[(window_size - 1):]

        # 如果滤波后数据点仍然不足，无法计算高阶导数
        if len(time_) < 4: return 0.0, 0.0, 0.0, 0.0

        # 使用 numpy.gradient 计算梯度 (导数)
        # 计算速度 (距离对时间的一阶导数)
        velocity = np.gradient(distance, time_)
        # 计算加速度 (速度对时间的导数，即距离的二阶导数)
        acceleration = np.gradient(velocity, time_)
        # 计算冲击力 (加速度对时间的导数，即距离的三阶导数)
        jerk = np.gradient(acceleration, time_)

        # logger.success(f"D:{distance[-1]:.3f} V:{velocity[-1]:.3f} A:{acceleration[-1]:.3f} J:{jerk[-1]:.3f}")
        # 返回最新的计算结果
        return distance[-1], velocity[-1], acceleration[-1], jerk[-1]

    async def touch_background_wave_feeder(self):
        """
        后台任务 (Touch 模式): 周期性地计算导数，并根据配置选择的导数
        生成并广播波形。
        """
        logger.info(f"通道 {self.channel} Touch 模式后台波形更新任务已启动。")
        # tick_time_window = self.bg_wave_update_time_window / 20 # 原始实现
        tick_time_window = self.bg_wave_update_time_window / 5 # 调整间隔
        next_tick_time = 0
        last_strength = 0.0
        while 1:
            current_time = time.time()
            if current_time < next_tick_time:
                await asyncio.sleep(tick_time_window)
                continue
            next_tick_time = current_time + self.bg_wave_update_time_window

            # 获取配置中要使用的导数阶数 (0:距离, 1:速度, 2:加速度, 3:冲击力)
            n_derivative = self.mode_config['touch']['n_derivative']
            # 计算所有导数
            derivatives = self.compute_derivative()
            # 根据配置选择要使用的导数值
            # 需要检查 n_derivative 是否在有效范围内 (0-3)
            if 0 <= n_derivative < len(derivatives):
                 current_derivative_value = derivatives[n_derivative]
            else:
                 logger.warning(f"通道 {self.channel} 配置的 n_derivative ({n_derivative}) 无效，将使用距离值。")
                 current_derivative_value = derivatives[0] # 回退到使用距离
                 n_derivative = 0 # 修正索引以便后续查找参数

            # 获取该导数对应的归一化参数 (上下界)
            # 需要检查 derivative_params 是否包含足够的配置项
            if n_derivative < len(self.mode_config['touch'].get('derivative_params', [])):
                derivative_params = self.mode_config['touch']['derivative_params'][n_derivative]
            else:
                logger.warning(f"通道 {self.channel} 缺少导数 {n_derivative} 的归一化参数，将使用默认值 {{'bottom': 0, 'top': 1}}。")
                derivative_params = {'bottom': 0.0, 'top': 1.0} # 提供默认值

            # 将导数值根据其配置的上下界归一化到 0-1
            # 注意：对于速度、加速度、冲击力，可能需要取绝对值？取决于期望的效果
            # 当前实现是直接使用原始值进行归一化
            trigger_bottom = derivative_params['bottom']
            trigger_top = derivative_params['top']
            range_diff = trigger_top - trigger_bottom
            current_strength = 0.0
            # 取绝对值可能更符合直觉，表示变化的剧烈程度，无论方向
            value_to_normalize = abs(current_derivative_value)
            if value_to_normalize > trigger_bottom:
                 if range_diff > 0:
                      current_strength = (value_to_normalize - trigger_bottom) / range_diff
                 else:
                      current_strength = 1.0
                 current_strength = min(current_strength, 1.0)

            # 更新内部强度状态
            self.bg_wave_current_strength = current_strength
            # 如果强度无变化且为 0，则跳过
            if current_strength == 0 and last_strength == 0:
                continue

            # 生成过渡波形
            wave = self.generate_wave_100ms(
                self.mode_config['touch']['freq_ms'], # 使用配置的频率
                last_strength,
                current_strength
            )
            logger.success(f'通道 {self.channel} (Touch D{n_derivative}), 强度 {last_strength:.3f} -> {current_strength:.3f}, 发送波形: {wave}')
            last_strength = current_strength
            # !! 注意: 原始代码中下面这行被注释掉了，意味着 Touch 模式实际上不会发送波形 !!
            # 如果需要启用 Touch 模式的实际输出，需要取消下面这行的注释:
            await self.DG_CONN.broadcast_wave(self.channel, wavestr=wave)

