import collections
from .base_handler import BaseHandler
from loguru import logger
import time, asyncio, math, json

from ..connector.coyotev3ws import DGConnection
from ..wave_preset import WavePresetLibrary
from ..command_queue import CommandQueue, CommandPriority


class ShockHandler(BaseHandler):
    _wave_library = WavePresetLibrary()
    _command_queue: CommandQueue = None  # Shared across all handlers
    osc_activity_observer = None  # Callback for OSC activity tracking
    _curve_getter = None  # Callback: (channel) -> points list

    @classmethod
    def set_command_queue(cls, queue: CommandQueue):
        cls._command_queue = queue

    def __init__(self, SETTINGS: dict, DG_CONN: DGConnection, channel_name: str, handler_mode: str = None) -> None:
        self.SETTINGS = SETTINGS
        self.DG_CONN = DG_CONN
        self.channel = channel_name.upper()
        self.shock_settings = SETTINGS['dglab3'][f'channel_{channel_name.lower()}']
        self.mode_config    = self.shock_settings['mode_config']

        self.shock_mode = handler_mode or self.shock_settings['mode']
        
        if self.shock_mode == 'distance':
            self._handler = self.handler_distance
        elif self.shock_mode == 'shock':
            self._handler = self.handler_shock
        elif self.shock_mode == 'touch':
            self._handler = self.handler_touch
        elif self.shock_mode == 'combo':
            self._handler = self.handler_combo
        elif self.shock_mode == 'boost':
            self._handler = self.handler_boost
        else:
            raise ValueError(f"Not supported mode: {self.shock_mode}")
        
        self.bg_wave_update_time_window = 0.1
        self.bg_wave_current_strength = 0

        self.touch_dist_arr = collections.deque(maxlen=20)
        self.dynamic_wave_index = 0
        self.active_dynamic_preset = None
        self.dynamic_wave_heads = {
            'distance': 0.0,
            'touch': 0.0,
            'shock': 0.0,
        }
        self.active_mode_presets = {}
        self.shock_started_at = 0
        self.shock_last_strength = 0

        self.to_clear_time    = 0
        self.is_cleared       = True

        # Combo mode state
        self.combo_touch_start = 0      # when current continuous touch began
        self.combo_in_touch_mode = False  # currently dispatching to touch logic
        self.combo_shock_fired = False    # already fired shock for this touch

        # Boost mode state
        self.boost_active = False         # currently boosted
    
    def start_background_jobs(self):
        logger.info(f'[handler] Channel {self.channel} background job started')
        asyncio.ensure_future(self.clear_check())
        if self.shock_mode == 'distance':
            asyncio.ensure_future(self.distance_background_wave_feeder())
        elif self.shock_mode == 'shock':
            asyncio.ensure_future(self.shock_background_wave_feeder())
        elif self.shock_mode == 'touch':
            asyncio.ensure_future(self.touch_background_wave_feeder())
        elif self.shock_mode == 'combo':
            asyncio.ensure_future(self.combo_background_wave_feeder())

    def refresh_settings(self):
        self.shock_settings = self.SETTINGS['dglab3'][f'channel_{self.channel.lower()}']
        self.mode_config = self.shock_settings['mode_config']

    def osc_handler(self, address, *args):
        val = self.param_sanitizer(args)
        context = {
            'address': address,
            'raw_args': list(args),
            'sanitized_value': val,
            'mode': self.shock_mode,
            'channel': self.channel,
        }
        if ShockHandler.osc_activity_observer:
            try:
                ShockHandler.osc_activity_observer(address, val, self.channel, self.shock_mode)
            except Exception:
                pass
        if self._command_queue:
            asyncio.ensure_future(self._enqueue_osc(val, context))
        else:
            asyncio.ensure_future(self._handler(val, context=context))
        return None

    async def _enqueue_osc(self, val, context):
        accepted = await self._command_queue.put(
            CommandPriority.OSC_INTERACTION,
            self.channel,
            'osc_trigger',
            value={'val': val, 'context': context, 'handler': self._handler},
            source_id=f"{self.channel}_{self.shock_mode}_{context.get('address', '')}",
        )
        if not accepted:
            logger.debug(f"[handler] Queue dropped (cooldown): {self.channel} {self.shock_mode} {context.get('address')}")

    @staticmethod
    def summarize_wave(wavestr):
        try:
            ops = json.loads(wavestr)
            if not ops:
                return 'ops=0'
            return f"ops={len(ops)} first={ops[0]} last={ops[-1]}"
        except Exception:
            return f"wavestr={str(wavestr)[:48]}"

    @staticmethod
    def scale_wavestr(wavestr, strength_scale):
        try:
            ops = json.loads(wavestr)
            scaled_ops = [WavePresetLibrary.scale_op(op, strength_scale) for op in ops]
            return json.dumps(scaled_ops, separators=(",", ":"))
        except Exception:
            return wavestr

    def log_trigger(self, context, *, value, normalized=None, extra=''):
        param = context.get('address') if context else '-'
        raw = context.get('raw_args') if context else [value]
        msg = (
            f"[handler] [trigger] channel={self.channel} mode={self.shock_mode} "
            f"param={param} raw={raw} value={value:.3f}"
        )
        if normalized is not None:
            msg += f" normalized={normalized:.3f}"
        if extra:
            msg += f" {extra}"
        logger.debug(msg)

    def log_output(self, *, source, strength=None, wave=None, extra=''):
        msg = f"[handler] [output] channel={self.channel} mode={self.shock_mode} source={source}"
        if strength is not None:
            msg += f" strength={strength:.3f}"
        if wave is not None:
            msg += f" {self.summarize_wave(wave)}"
        if extra:
            msg += f" {extra}"
        logger.debug(msg)

    async def clear_check(self):
        logger.debug(f'[handler] Channel {self.channel} clear check started')
        sleep_time = 0.05
        while 1:
            await asyncio.sleep(sleep_time)
            current_time = time.time()
            # logger.debug(f"{str(self.is_cleared)}, {current_time}, {self.to_clear_time}")
            if not self.is_cleared and current_time > self.to_clear_time:
                self.is_cleared = True
                self.bg_wave_current_strength = 0
                self.touch_dist_arr.clear()
                self.dynamic_wave_index = 0
                self.active_dynamic_preset = None
                self.dynamic_wave_heads = {key: 0 for key in self.dynamic_wave_heads}
                self.active_mode_presets = {}
                self.shock_started_at = 0
                self.shock_last_strength = 0
                self.combo_touch_start = 0
                self.combo_in_touch_mode = False
                self.combo_shock_fired = False
                await self.DG_CONN.broadcast_clear_wave(self.channel)
                logger.debug(f"[handler] Channel {self.channel} cleared after timeout")
    
    async def feed_wave(self):
        raise NotImplemented
        logger.debug(f'[handler] Channel {self.channel} wave feeder started')
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

    @staticmethod
    def generate_wave_100ms_improved(freq, from_, to_, *, steps=4, curve="smoothstep"):
        """
        Generate a 100ms DG wave (4x25ms sub-steps by default).
        Returns wavestr: JSON string like ["0A0A0A0A14191E23"]

        freq: int (0-255, but DG commonly 10..240)
        from_, to_: float in [0,1]
        steps: number of sub-steps in 100ms (DG commonly 4)
        curve: "linear" | "smoothstep" | "ease_in_out_sine"
        """
        if not (0 <= from_ <= 1) or not (0 <= to_ <= 1):
            raise ValueError("from_ and to_ must be in [0,1]")
        if steps <= 0:
            raise ValueError("steps must be > 0")

        # clamp freq to byte
        freq = int(freq)
        freq = max(0, min(255, freq))

        from_i = int(round(from_ * 100))
        to_i   = int(round(to_   * 100))

        def apply_curve(t: float) -> float:
            t = max(0.0, min(1.0, t))
            if curve == "linear":
                return t
            if curve == "smoothstep":
                # 3t^2 - 2t^3
                return t * t * (3.0 - 2.0 * t)
            if curve == "ease_in_out_sine":
                # 0.5 - 0.5*cos(pi*t)
                return 0.5 - 0.5 * math.cos(math.pi * t)
            raise ValueError(f"unknown curve: {curve}")

        # Build strengths for each 25ms slice: i=1..steps
        strengths = []
        for i in range(1, steps + 1):
            t = apply_curve(i / steps)
            v = from_ + (to_ - from_) * t
            si = int(round(v * 100))
            si = max(0, min(100, si))
            strengths.append(si)

        # Guarantee last sample hits to_i exactly (avoid accumulated rounding error)
        strengths[-1] = max(0, min(100, to_i))

        # Pack: 4 freq bytes + 4 strength bytes (if steps!=4, we still pack exactly `steps` strength bytes)
        # DG 的 100ms 帧通常要求 4 个 strength 字节；如果你要保持协议一致，建议 steps=4。
        freq_hex = f"{freq:02X}" * 4
        strength_hex = "".join(f"{s:02X}" for s in strengths)

        # If steps != 4, the hex length won't be 16 (8 bytes). Keep steps=4 for DG 100ms op.
        if steps != 4:
            raise ValueError("DG 100ms op expects 4 strength bytes; please keep steps=4.")

        ret = freq_hex + strength_hex
        return json.dumps([ret], separators=(",", ":"))
    
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

    def apply_strength_curve(self, value, param_path=None):
        """Apply custom param-to-strength curve mapping."""
        getter = ShockHandler._curve_getter
        if not getter:
            return value
        points = getter(param_path or self.channel)
        if not points:
            return value
        # Linear interpolation through control points
        if value <= 0:
            return 0.0
        if value >= 1.0:
            return min(1.0, points[-1].get('y', 1.0) if points else 1.0)
        for i in range(len(points) - 1):
            px, py = points[i].get('x', 0), points[i].get('y', 0)
            nx, ny = points[i + 1].get('x', 0), points[i + 1].get('y', 0)
            if value >= px and value <= nx:
                dx = nx - px
                if dx <= 0:
                    return py
                t = (value - px) / dx
                return py + t * (ny - py)
        return points[-1].get('y', value) if points else value

    @staticmethod
    def normalize_between(value, bottom, top):
        if top <= bottom:
            logger.warning(f'[handler] Invalid normalize range: bottom={bottom}, top={top}')
            return 0
        clamped = min(max(value, bottom), top)
        return (clamped - bottom) / (top - bottom)

    def get_mode_conf(self, mode_name):
        return self.mode_config.get(mode_name, {})

    def get_shock_duration(self):
        return max(0.1, float(self.get_mode_conf('shock').get('duration', 2)))

    def get_dynamic_window_size(self, mode_name):
        mode_conf = self.get_mode_conf(mode_name)
        window_size = int(mode_conf.get('wave_window_ops', 4))
        return max(1, min(32, window_size))

    def get_dynamic_sample_step(self, mode_name):
        mode_conf = self.get_mode_conf(mode_name)
        sample_step = float(mode_conf.get('wave_sample_step', 1.0))
        return max(0.25, min(8.0, sample_step))

    def get_dynamic_window_advance(self, mode_name):
        mode_conf = self.get_mode_conf(mode_name)
        default_advance = 4.0 * self.get_dynamic_sample_step(mode_name)
        advance = float(mode_conf.get('wave_advance_samples', default_advance))
        return max(0.25, min(32.0, advance))

    def get_dynamic_envelope_curve(self, mode_name):
        mode_conf = self.get_mode_conf(mode_name)
        return mode_conf.get('wave_envelope_curve', 'smoothstep')

    def get_texture_floor(self, mode_name):
        return max(0.0, min(1.0, float(self.get_mode_conf(mode_name).get('texture_floor', 0.0))))

    def build_dynamic_wave(self, mode_name, from_strength, to_strength, *, preset_name=None, wave_scale=None):
        mode_conf = self.get_mode_conf(mode_name)
        preset_name = preset_name if preset_name is not None else mode_conf.get('wave_preset')
        wave_scale = mode_conf.get('wave_scale', 1.0) if wave_scale is None else wave_scale
        wave_scale = max(0.0, min(1.0, wave_scale))
        if preset_name and mode_name in ['distance', 'touch']:
            if preset_name != self.active_mode_presets.get(mode_name):
                self.dynamic_wave_heads[mode_name] = 0
                self.active_mode_presets[mode_name] = preset_name
            start_position = self.dynamic_wave_heads[mode_name]
            window_size = self.get_dynamic_window_size(mode_name)
            preset_wave = self._wave_library.build_resampled_window(
                preset_name,
                start_position,
                window_size,
                wave_scale=wave_scale,
                texture_floor=self.get_texture_floor(mode_name),
                sample_step=self.get_dynamic_sample_step(mode_name),
            )
            if preset_wave:
                self.dynamic_wave_heads[mode_name] = start_position + self.get_dynamic_window_advance(mode_name)
                self.active_dynamic_preset = preset_name
                return preset_wave
        if preset_name and mode_name == 'shock':
            if preset_name != self.active_mode_presets.get(mode_name):
                self.active_mode_presets[mode_name] = preset_name
            self.active_dynamic_preset = preset_name
            scaled_strength = to_strength * wave_scale
            preset_wave = self._wave_library.build_scaled_window(
                preset_name,
                int(self.dynamic_wave_heads[mode_name]),
                self.get_dynamic_window_size(mode_name),
                scaled_strength,
            )
            if preset_wave:
                self.dynamic_wave_heads[mode_name] += 1
                return preset_wave
        self.active_mode_presets.pop(mode_name, None)
        self.active_dynamic_preset = None
        if mode_name == 'shock':
            return self.scale_wavestr(
                self.get_mode_conf('shock')['wave'],
                to_strength * wave_scale,
            )
        return self.generate_wave_100ms_improved(
            mode_conf['freq_ms'],
            from_strength,
            to_strength,
        )

    def resolve_touch_profile(self, current_strength):
        touch_conf = self.get_mode_conf('touch')
        selected_profile = None
        for profile in touch_conf.get('preset_bands', []):
            try:
                threshold = float(profile.get('threshold', 0))
            except (TypeError, ValueError):
                logger.warning(f'[handler] Channel {self.channel} invalid touch preset threshold: {profile}')
                continue
            if current_strength >= threshold:
                if selected_profile is None or threshold >= selected_profile['threshold']:
                    selected_profile = {
                        'threshold': threshold,
                        'wave_preset': profile.get('wave_preset'),
                        'wave_scale': profile.get('wave_scale'),
                    }
        if selected_profile is None:
            return touch_conf.get('wave_preset'), touch_conf.get('wave_scale', 1.0)
        wave_preset = selected_profile.get('wave_preset') or touch_conf.get('wave_preset')
        wave_scale = selected_profile.get('wave_scale')
        if wave_scale is None:
            wave_scale = touch_conf.get('wave_scale', 1.0)
        return wave_preset, wave_scale

    async def handler_distance(self, distance, context=None):
        await self.set_clear_after(0.5)
        normalized = self.normalize_distance(distance)
        param_path = context.get('address') if context else None
        normalized = self.apply_strength_curve(normalized, param_path)
        self.bg_wave_current_strength = normalized
        self.log_trigger(context, value=distance, normalized=normalized)

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
            wave = self.build_dynamic_wave('distance', last_strength, current_strength)
            self.log_output(
                source='distance',
                strength=current_strength,
                wave=wave,
                extra=(
                    f"from={last_strength:.3f} to={current_strength:.3f} "
                    f"preset={self.active_dynamic_preset or '-'} "
                    f"texture_floor={self.get_texture_floor('distance'):.2f}"
                ),
            )
            last_strength = current_strength
            await self.DG_CONN.broadcast_wave(self.channel, wavestr=wave)
    
    def get_shock_wavestrs(self):
        shock_conf = self.get_mode_conf('shock')
        preset_name = shock_conf.get('wave_preset')
        wave_scale = max(0.0, min(1.0, shock_conf.get('wave_scale', 1.0)))
        preset_wavestrs = self._wave_library.build_scaled_wavestrs(preset_name, wave_scale)
        if preset_wavestrs:
            return preset_wavestrs
        return [shock_conf['wave']]

    def get_shock_strength(self, current_time):
        if self.shock_started_at <= 0:
            return 0
        duration = self.get_shock_duration()
        elapsed = current_time - self.shock_started_at
        if elapsed <= 0:
            return 1
        return max(0.0, 1.0 - (elapsed / duration))

    async def shock_background_wave_feeder(self):
        tick_time_window = self.bg_wave_update_time_window / 20
        next_tick_time = 0
        while 1:
            current_time = time.time()
            if current_time < next_tick_time:
                await asyncio.sleep(tick_time_window)
                continue
            next_tick_time = current_time + self.bg_wave_update_time_window
            if self.is_cleared:
                self.shock_last_strength = 0
                continue
            current_strength = self.get_shock_strength(current_time)
            if current_strength <= 0:
                self.shock_last_strength = 0
                continue
            wave = self.build_dynamic_wave(
                'shock',
                self.shock_last_strength,
                current_strength,
                preset_name=self.get_mode_conf('shock').get('wave_preset'),
                wave_scale=self.get_mode_conf('shock').get('wave_scale', 1.0),
            )
            self.log_output(
                source='shock',
                strength=current_strength,
                wave=wave,
                extra=(
                    f"from={self.shock_last_strength:.3f} to={current_strength:.3f} "
                    f"duration={self.get_shock_duration():.2f}s preset={self.get_mode_conf('shock').get('wave_preset') or '-'}"
                ),
            )
            self.shock_last_strength = current_strength
            await self.DG_CONN.broadcast_wave(self.channel, wavestr=wave)
    
    async def handler_shock(self, distance, context=None):
        current_time = time.time()
        if distance > self.mode_config['trigger_range']['bottom']:
            shock_duration = self.get_shock_duration()
            await self.set_clear_after(shock_duration)
            self.shock_started_at = current_time
            self.shock_last_strength = 0
            preset_names = self.get_mode_conf('shock').get('wave_preset') or '-'
            self.log_trigger(
                context,
                value=distance,
                extra=f"duration={shock_duration:.2f}s preset={preset_names} action=reset-to-peak",
            )

    async def handler_touch(self, distance, context=None):
        await self.set_clear_after(0.5)
        out_distance = self.normalize_distance(distance)
        self.log_trigger(context, value=distance, normalized=out_distance)
        if out_distance == 0:
            return
        t = time.time()
        self.touch_dist_arr.append([t,out_distance])
    
    def compute_derivative(self):
        data = self.touch_dist_arr
        if len(data) < 4:
            return 0, 0, 0, 0

        time_ = [point[0] for point in data]
        distance = [point[1] for point in data]

        # Moving average (window=3, valid mode)
        window_size = 3
        smoothed = []
        for i in range(len(distance) - window_size + 1):
            smoothed.append(sum(distance[i:i+window_size]) / window_size)
        distance = smoothed
        time_ = time_[:len(distance)]

        # Gradient (central differences, matching np.gradient behavior)
        def _gradient(values, times):
            n = len(values)
            if n < 2:
                return [0.0] * n
            grad = [0.0] * n
            # Forward difference for first element
            dt = times[1] - times[0]
            grad[0] = (values[1] - values[0]) / dt if dt != 0 else 0.0
            # Central differences for interior
            for i in range(1, n - 1):
                dt = times[i+1] - times[i-1]
                grad[i] = (values[i+1] - values[i-1]) / dt if dt != 0 else 0.0
            # Backward difference for last element
            dt = times[-1] - times[-2]
            grad[-1] = (values[-1] - values[-2]) / dt if dt != 0 else 0.0
            return grad

        velocity = _gradient(distance, time_)
        acceleration = _gradient(velocity, time_)
        jerk = _gradient(acceleration, time_)
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
            derivative_values = self.compute_derivative()
            if n_derivative < 0 or n_derivative >= len(derivative_values):
                logger.warning(f'[handler] Channel {self.channel} invalid n_derivative {n_derivative}, fallback to 1')
                n_derivative = 1
            current_strength = derivative_values[n_derivative]
            derivative_params = self.mode_config['touch']['derivative_params'][n_derivative]
            current_strength = self.normalize_between(
                abs(current_strength),
                derivative_params['bottom'],
                derivative_params['top'],
            )

            self.bg_wave_current_strength = current_strength
            if current_strength == last_strength == 0:
                continue
            touch_preset, touch_scale = self.resolve_touch_profile(current_strength)
            wave = self.build_dynamic_wave(
                'touch',
                last_strength,
                current_strength,
                preset_name=touch_preset,
                wave_scale=touch_scale,
            )
            derivative_name = ['distance', 'velocity', 'acceleration', 'jerk'][n_derivative]
            self.log_output(
                source='touch',
                strength=current_strength,
                wave=wave,
                extra=(
                    f"from={last_strength:.3f} to={current_strength:.3f} "
                    f"derivative={derivative_name} "
                    f"preset={touch_preset or '-'} scale={touch_scale:.2f} "
                    f"texture_floor={self.get_texture_floor('touch'):.2f}"
                ),
            )
            last_strength = current_strength
            await self.DG_CONN.broadcast_wave(self.channel, wavestr=wave)


    def get_combo_conf(self):
        return self.mode_config.get('combo', {})

    async def handler_combo(self, distance, context=None):
        """Combo mode: dispatch to shock (short) or touch (sustained)."""
        combo_conf = self.get_combo_conf()
        threshold = float(combo_conf.get('switch_duration', 0.3))
        trigger_bottom = self.mode_config['trigger_range']['bottom']
        current_time = time.time()

        if distance > trigger_bottom:
            # Touch is active
            if self.combo_touch_start == 0:
                # New touch begins
                self.combo_touch_start = current_time
                self.combo_in_touch_mode = False
                self.combo_shock_fired = False

            touch_duration = current_time - self.combo_touch_start

            if touch_duration >= threshold and not self.combo_in_touch_mode:
                # Switch to touch mode
                self.combo_in_touch_mode = True
                self.touch_dist_arr.clear()
                logger.debug(f"[handler] [combo] channel={self.channel} switched to touch after {touch_duration:.2f}s")

            if self.combo_in_touch_mode:
                # Sustained: feed to touch logic
                await self.handler_touch(distance, context=context)
            else:
                # Still in burst window, accumulate for potential shock
                # Keep extending clear timer
                shock_duration = self.get_shock_duration()
                await self.set_clear_after(max(threshold + 0.2, shock_duration))
        else:
            # Touch released
            if self.combo_touch_start > 0:
                touch_duration = current_time - self.combo_touch_start
                if touch_duration < threshold and not self.combo_shock_fired:
                    # Short touch → fire shock
                    self.combo_shock_fired = True
                    await self.handler_shock(distance=trigger_bottom + 0.01, context=context)
                    logger.debug(f"[handler] [combo] channel={self.channel} fired shock (duration={touch_duration:.2f}s)")
                self.combo_touch_start = 0
                self.combo_in_touch_mode = False

    async def combo_background_wave_feeder(self):
        """Combo feeder: runs both shock and touch feeders, output based on current combo state."""
        tick_time_window = self.bg_wave_update_time_window / 20
        next_tick_time = 0
        last_touch_strength = 0
        while 1:
            current_time = time.time()
            if current_time < next_tick_time:
                await asyncio.sleep(tick_time_window)
                continue
            next_tick_time = current_time + self.bg_wave_update_time_window

            if self.is_cleared:
                self.shock_last_strength = 0
                last_touch_strength = 0
                continue

            if self.combo_in_touch_mode:
                # Touch wave output
                n_derivative = self.mode_config['touch']['n_derivative']
                derivative_values = self.compute_derivative()
                if n_derivative < 0 or n_derivative >= len(derivative_values):
                    n_derivative = 1
                current_strength = derivative_values[n_derivative]
                derivative_params = self.mode_config['touch']['derivative_params'][n_derivative]
                current_strength = self.normalize_between(
                    abs(current_strength),
                    derivative_params['bottom'],
                    derivative_params['top'],
                )
                self.bg_wave_current_strength = current_strength
                if current_strength == last_touch_strength == 0:
                    continue
                touch_preset, touch_scale = self.resolve_touch_profile(current_strength)
                wave = self.build_dynamic_wave(
                    'touch', last_touch_strength, current_strength,
                    preset_name=touch_preset, wave_scale=touch_scale,
                )
                self.log_output(source='combo/touch', strength=current_strength, wave=wave)
                last_touch_strength = current_strength
                await self.DG_CONN.broadcast_wave(self.channel, wavestr=wave)
            else:
                # Shock wave output (if shock was triggered)
                last_touch_strength = 0
                current_strength = self.get_shock_strength(current_time)
                if current_strength <= 0:
                    self.shock_last_strength = 0
                    continue
                wave = self.build_dynamic_wave(
                    'shock', self.shock_last_strength, current_strength,
                    preset_name=self.get_mode_conf('shock').get('wave_preset'),
                    wave_scale=self.get_mode_conf('shock').get('wave_scale', 1.0),
                )
                self.log_output(source='combo/shock', strength=current_strength, wave=wave)
                self.shock_last_strength = current_strength
                await self.DG_CONN.broadcast_wave(self.channel, wavestr=wave)

    async def handler_boost(self, distance, context=None):
        """Boost mode: param > threshold → strength +N, param back to 0 → strength -N."""
        trigger_bottom = self.mode_config['trigger_range']['bottom']
        boost_conf = self.get_mode_conf('boost')
        boost_value = int(boost_conf.get('value', 30))

        if distance > trigger_bottom:
            if not self.boost_active:
                self.boost_active = True
                await self.DG_CONN.broadcast_strength_adjust(self.channel, mode='1', value=boost_value)
                self.log_trigger(context, value=distance, extra=f"boost +{boost_value}")
        else:
            if self.boost_active:
                self.boost_active = False
                await self.DG_CONN.broadcast_strength_adjust(self.channel, mode='0', value=boost_value)
                self.log_trigger(context, value=distance, extra=f"boost -{boost_value} (reverted)")
