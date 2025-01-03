import numpy as np
import collections
from .base_handler import BaseHandler
from loguru import logger
import time, asyncio, math, json

from ..connector.coyotev3ws import DGConnection


class ShockHandler(BaseHandler):
    def __init__(self, SETTINGS: dict, DG_CONN: DGConnection, channel_name: str) -> None:
        self.SETTINGS = SETTINGS
        self.DG_CONN = DG_CONN
        self.channel = channel_name.upper()
        self.shock_settings = SETTINGS['dglab3'][f'channel_{channel_name.lower()}']
        self.mode_config    = self.shock_settings['mode_config']

        self.shock_mode = self.shock_settings['mode']
        
        if self.shock_mode == 'distance':
            self._handler = self.handler_distance
        elif self.shock_mode == 'shock':
            self._handler = self.handler_shock
        elif self.shock_mode == 'touch':
            self._handler = self.handler_touch
        else:
            raise ValueError(f"Not supported mode: {self.shock_mode}")
        
        self.bg_wave_update_time_window = 0.1
        self.bg_wave_current_strength = 0

        self.touch_dist_arr = collections.deque(maxlen=20)

        self.to_clear_time    = 0
        self.is_cleared       = True
    
    def start_background_jobs(self):
        # logger.info(f"Channel: {self.channel}, background job started.")
        asyncio.ensure_future(self.clear_check())
        # if self.shock_mode == 'shock':
        #     asyncio.ensure_future(self.feed_wave())
        if self.shock_mode == 'distance':
            asyncio.ensure_future(self.distance_background_wave_feeder())
        elif self.shock_mode == 'touch':
            asyncio.ensure_future(self.touch_background_wave_feeder())

    def osc_handler(self, address, *args):
        logger.debug(f"VRCOSC: CHANN {self.channel}: {address}: {args}")
        val = self.param_sanitizer(args)
        return asyncio.ensure_future(self._handler(val))

    async def clear_check(self):
        # logger.info(f'Channel {self.channel} started clear check.')
        sleep_time = 0.05
        while 1:
            await asyncio.sleep(sleep_time)
            current_time = time.time()
            # logger.debug(f"{str(self.is_cleared)}, {current_time}, {self.to_clear_time}")
            if not self.is_cleared and current_time > self.to_clear_time:
                self.is_cleared = True
                self.bg_wave_current_strength = 0
                self.touch_dist_arr.clear()
                await self.DG_CONN.broadcast_clear_wave(self.channel)
                logger.info(f'Channel {self.channel}, wave cleared after timeout.')
    
    async def feed_wave(self):
        raise NotImplemented
        logger.info(f'Channel {self.channel} started wave feeding.')
        sleep_time = 1
        while 1:
            await asyncio.sleep(sleep_time)
            await self.DG_CONN.broadcast_wave(channel=self.channel, wavestr=self.shock_settings['shock_wave'])

    async def set_clear_after(self, val):
        self.is_cleared = False
        self.to_clear_time = time.time() + val

    @staticmethod
    def generate_wave_100ms(freq, from_, to_):
        assert 0 <= from_ <= 1, "Invalid wave generate."
        assert 0 <= to_   <= 1, "Invalid wave generate."
        from_ = int(100*from_)
        to_   = int(100*to_)
        ret = ["{:02X}".format(freq)]*4
        delta = (to_ - from_) // 4
        ret += ["{:02X}".format(min(max(from_ + delta*i, 0),100)) for i in range(1,5,1)]
        ret = ''.join(ret)
        return json.dumps([ret],separators=(',', ':'))
    
    def normalize_distance(self, distance):
        out_distance = 0
        trigger_bottom = self.mode_config['trigger_range']['bottom']
        trigger_top = self.mode_config['trigger_range']['top']
        if distance > self.mode_config['trigger_range']['bottom']:
            out_distance = (
                    distance - trigger_bottom
                ) / (
                    trigger_top - trigger_bottom
                )
            out_distance = 1 if out_distance > 1 else out_distance
        return out_distance

    async def handler_distance(self, distance):
        await self.set_clear_after(0.5)
        self.bg_wave_current_strength = self.normalize_distance(distance)

    async def distance_background_wave_feeder(self):
        tick_time_window = self.bg_wave_update_time_window / 20
        next_tick_time   = 0
        last_strength    = 0
        while 1:
            current_time = time.time()
            if current_time < next_tick_time:
                await asyncio.sleep(tick_time_window)
                continue
            next_tick_time = current_time + self.bg_wave_update_time_window
            current_strength = self.bg_wave_current_strength
            if current_strength == last_strength == 0:
                continue
            wave = self.generate_wave_100ms(
                self.mode_config['distance']['freq_ms'], 
                last_strength, 
                current_strength
            )
            logger.success(f'Channel {self.channel}, strength {last_strength:.3f} to {current_strength:.3f}, Sending {wave}')
            last_strength = current_strength
            await self.DG_CONN.broadcast_wave(self.channel, wavestr=wave)
    
    async def send_shock_wave(self, shock_time, shockwave: str):
        shockwave_duration = (shockwave.count(',')+1) * 0.1
        send_times = math.ceil(shock_time // shockwave_duration)
        for _ in range(send_times):
            await self.DG_CONN.broadcast_wave(self.channel, wavestr=self.mode_config['shock']['wave'])
            await asyncio.sleep(shockwave_duration)
    
    async def handler_shock(self, distance):
        current_time = time.time()
        if distance > self.mode_config['trigger_range']['bottom'] and current_time > self.to_clear_time:
            shock_duration = self.mode_config['shock']['duration']
            await self.set_clear_after(shock_duration)
            logger.success(f'Channel {self.channel}: Shocking for {shock_duration} s.')
            asyncio.create_task(self.send_shock_wave(shock_duration, self.mode_config['shock']['wave']))

    async def handler_touch(self, distance):
        await self.set_clear_after(0.5)
        out_distance = self.normalize_distance(distance)
        if out_distance == 0:
            return
        t = time.time()
        self.touch_dist_arr.append([t,out_distance])
    
    def compute_derivative(self):
        data = self.touch_dist_arr
        if len(data) < 4:
            # logger.warning('At least 4 samples are required to calculate acc and jerk.')
            return 0, 0, 0, 0

        time_ = np.array([point[0] for point in data])
        distance = np.array([point[1] for point in data])

        window_size = 3
        distance = np.convolve(distance, np.ones(window_size) / window_size, mode='valid')
        time_ = time_[:len(distance)]

        velocity = np.gradient(distance, time_)
        acceleration = np.gradient(velocity, time_)
        jerk = np.gradient(acceleration, time_)
        # logger.success(f"{distance[-1]:9.4f} {velocity[-1]:9.4f} {acceleration[-1]:9.4f} {jerk[-1]:9.4f}")
        return distance[-1], velocity[-1], acceleration[-1], jerk[-1]

    async def touch_background_wave_feeder(self):
        tick_time_window = self.bg_wave_update_time_window / 20
        next_tick_time   = 0
        last_strength    = 0
        while 1:
            current_time = time.time()
            if current_time < next_tick_time:
                await asyncio.sleep(tick_time_window)
                continue
            next_tick_time = current_time + self.bg_wave_update_time_window
            n_derivative = self.mode_config['touch']['n_derivative']
            current_strength = self.compute_derivative()[n_derivative]
            derivative_params = self.mode_config['touch']['derivative_params'][n_derivative]
            current_strength = max(min(derivative_params['bottom'],abs(current_strength)),derivative_params['top'])/(derivative_params['top']-derivative_params['bottom'])

            self.bg_wave_current_strength = current_strength
            if current_strength == last_strength == 0:
                continue
            wave = self.generate_wave_100ms(
                self.mode_config['touch']['freq_ms'], 
                last_strength, 
                current_strength
            )
            logger.success(f'Channel {self.channel}, strength {last_strength:.3f} to {current_strength:.3f}, Sending {wave}')
            last_strength = current_strength
            # await self.DG_CONN.broadcast_wave(self.channel, wavestr=wave)

