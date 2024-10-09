from . base_handler import BaseHandler
from ..connector.machine_tuya_cloud import TuYaConnection
import asyncio, time, math
from loguru import logger

class TuyaHandler(BaseHandler):
    def __init__(self, SETTINGS: dict, DEV_CONN: TuYaConnection) -> None:
        self.SETTINGS = SETTINGS
        self.DEV_CONN = DEV_CONN
        self.settings = SETTINGS['machine']['tuya']
        self.mode_config = self.settings['mode_config']

        self.mode = self.settings['mode']
        
        if self.mode == 'level':
            self._handler = self.handler_level
        else:
            raise ValueError(f"Not supported mode: {self.mode}")
        
        self.distance_update_time_window = 0.2
        self.distance_current_strength = 0

        self.to_clear_time    = 0
        self.is_cleared       = True
    
    def start_background_jobs(self):
        # logger.info(f"Channel: {self.channel}, background job started.")
        asyncio.ensure_future(self.clear_check())
        if self.mode == 'level':
            asyncio.ensure_future(self.distance_background_wave_feeder())


    async def clear_check(self):
        # logger.info(f'Channel {self.channel} started clear check.')
        sleep_time = 0.05
        while 1:
            await asyncio.sleep(sleep_time)
            current_time = time.time()
            # logger.debug(f"{str(self.is_cleared)}, {current_time}, {self.to_clear_time}")
            if not self.is_cleared and current_time > self.to_clear_time:
                self.is_cleared = True
                self.level_current = 1
                await self.DEV_CONN.set_level(1)
                logger.info(f'Machine set to level 1 cleared after timeout.')

    async def set_clear_after(self, val):
        self.is_cleared = False
        self.to_clear_time = time.time() + val

    async def handler_level(self, distance):
        await self.set_clear_after(5)
        strength = 0
        trigger_bottom = self.mode_config['trigger_range']['bottom']
        trigger_top = self.mode_config['trigger_range']['top']
        if distance > self.mode_config['trigger_range']['bottom']:
            strength = (
                    distance - trigger_bottom
                ) / (
                    trigger_top - trigger_bottom
                )
            strength = 1 if strength > 1 else strength
        self.distance_current_strength = strength

    async def distance_background_wave_feeder(self):
        tick_time_window = self.distance_update_time_window / 20
        next_tick_time   = 0
        last_level    = 0
        while 1:
            current_time = time.time()
            if current_time < next_tick_time:
                await asyncio.sleep(tick_time_window)
                continue
            next_tick_time = current_time + self.distance_update_time_window
            current_strength = self.distance_current_strength
            current_level = math.ceil(self.mode_config['level_max'] * current_strength)
            if last_level == current_level:
                continue
            logger.success(f'Machine Tuya, strength {current_strength:.3f}, Setting level {current_level}')
            last_level = current_level
            await self.DEV_CONN.set_level(current_level)
    