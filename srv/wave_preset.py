import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger



def get_runtime_base_dir() -> Path:
    """Get the directory where the main script/exe lives (for external data files)."""
    if getattr(sys, "frozen", False):
        # PyInstaller/Nuitka: exe directory (where wave_presets/ lives alongside)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_bundled_base_dir() -> Path:
    """Get the bundled resources dir (for static/templates that ARE packed inside)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


PRESET_DIR = get_runtime_base_dir() / "wave_presets"


def _coerce_ops(raw_wave_data) -> List[str]:
    if raw_wave_data is None:
        return []
    if isinstance(raw_wave_data, str):
        parsed = json.loads(raw_wave_data)
    else:
        parsed = raw_wave_data
    if not isinstance(parsed, list):
        raise ValueError("Wave data must be a JSON array.")
    ops = []
    for op in parsed:
        if not isinstance(op, str) or len(op) != 16:
            raise ValueError(f"Invalid wave op: {op}")
        ops.append(op.upper())
    return ops


def _ops_to_wavestrs(ops: List[str], chunk_size: int = 86) -> List[str]:
    if not ops:
        return []
    return [
        json.dumps(ops[idx:idx + chunk_size], separators=(",", ":"))
        for idx in range(0, len(ops), chunk_size)
    ]


def _decode_ops_to_samples(ops: List[str]) -> Dict[str, List[float]]:
    freq_samples: List[float] = []
    strength_samples: List[float] = []
    for op in ops:
        for idx in range(0, 8, 2):
            freq_samples.append(int(op[idx:idx + 2], 16))
        for idx in range(8, 16, 2):
            strength_samples.append(int(op[idx:idx + 2], 16) / 100.0)
    if not strength_samples:
        texture_samples = []
    else:
        max_strength = max(strength_samples)
        if max_strength <= 0:
            texture_samples = [0.0 for _ in strength_samples]
        else:
            texture_samples = [sample / max_strength for sample in strength_samples]
    return {
        "freq_samples": freq_samples,
        "strength_samples": strength_samples,
        "texture_samples": texture_samples,
    }


class WavePresetLibrary:
    _instance: Optional['WavePresetLibrary'] = None

    def __new__(cls, preset_dir: Optional[Path] = None):
        if cls._instance is None:
            obj = super().__new__(cls)
            obj.preset_dir = Path(preset_dir) if preset_dir is not None else PRESET_DIR
            obj.presets = {}
            obj.reload()
            cls._instance = obj
        return cls._instance

    def __init__(self, preset_dir: Optional[Path] = None) -> None:
        # __new__ handles initialization; avoid re-init on subsequent calls
        pass

    def reload(self):
        self.presets = {}
        if not self.preset_dir.exists():
            logger.warning(f"[preset] Directory not found: {self.preset_dir}")
            return
        for preset_file in sorted(self.preset_dir.glob("*.json")):
            try:
                with preset_file.open("r", encoding="utf-8") as fr:
                    raw = json.load(fr)
                name = raw.get("name") or preset_file.stem
                ops = []
                if "ops" in raw:
                    ops = _coerce_ops(raw["ops"])
                elif "wavestrs" in raw:
                    for wavestr in raw["wavestrs"]:
                        ops.extend(_coerce_ops(wavestr))
                else:
                    raise ValueError("Preset must contain `ops` or `wavestrs`.")
                self.presets[name] = {
                    "ops": ops,
                    "wavestrs": _ops_to_wavestrs(ops),
                    "header": raw.get("header"),
                    "preview_sections": raw.get("preview_sections"),
                    **_decode_ops_to_samples(ops),
                }
                logger.info(f"[preset] Loaded: {name} ({len(ops)} ops)")
            except Exception as exc:
                logger.error(f"[preset] Failed to load {preset_file.name}: {exc}")

    def get(self, name: Optional[str]):
        if not name:
            return None
        preset = self.presets.get(name)
        if preset is None:
            logger.warning(f"[preset] Not found: {name}")
        return preset

    def get_raw(self, name: Optional[str]):
        """Get preset data including preview_sections and header metadata."""
        return self.get(name)

    @staticmethod
    def scale_op(op: str, strength_scale: float) -> str:
        strength_scale = max(0.0, min(1.0, float(strength_scale)))
        freq_hex = op[:8]
        strength_bytes = [
            max(0, min(100, round(int(op[idx:idx + 2], 16) * strength_scale)))
            for idx in range(8, 16, 2)
        ]
        return freq_hex + "".join(f"{value:02X}" for value in strength_bytes)

    @staticmethod
    def _apply_curve(t: float, curve: str) -> float:
        t = max(0.0, min(1.0, t))
        if curve == "linear":
            return t
        if curve == "smoothstep":
            return t * t * (3.0 - 2.0 * t)
        if curve == "ease_in_out_sine":
            return 0.5 - 0.5 * math.cos(math.pi * t)
        raise ValueError(f"unknown curve: {curve}")

    @staticmethod
    def _sample_looped(sequence: List[float], position: float) -> float:
        if not sequence:
            return 0.0
        if len(sequence) == 1:
            return sequence[0]
        length = len(sequence)
        pos = position % length
        left = int(math.floor(pos))
        right = (left + 1) % length
        frac = pos - left
        return sequence[left] * (1.0 - frac) + sequence[right] * frac

    def build_scaled_single_op(self, name: Optional[str], index: int, strength_scale: float) -> Optional[str]:
        preset = self.get(name)
        if not preset or not preset["ops"]:
            return None
        op = preset["ops"][index % len(preset["ops"])]
        return json.dumps([self.scale_op(op, strength_scale)], separators=(",", ":"))

    def build_scaled_window(self, name: Optional[str], start_index: int, window_size: int, strength_scale: float) -> Optional[str]:
        preset = self.get(name)
        if not preset or not preset["ops"]:
            return None
        if window_size <= 0:
            return None
        ops = preset["ops"]
        window_ops = [
            self.scale_op(ops[(start_index + offset) % len(ops)], strength_scale)
            for offset in range(window_size)
        ]
        return json.dumps(window_ops, separators=(",", ":"))

    def build_resampled_window(
        self,
        name: Optional[str],
        start_position: float,
        window_ops: int,
        *,
        wave_scale: float = 1.0,
        texture_floor: float = 0.35,
        sample_step: float = 1.0,
    ) -> Optional[str]:
        preset = self.get(name)
        if not preset:
            return None
        freq_samples = preset["freq_samples"]
        texture_samples = preset["texture_samples"]
        if not freq_samples or not texture_samples or window_ops <= 0:
            return None

        total_samples = window_ops * 4
        wave_scale = max(0.0, min(1.0, float(wave_scale)))
        texture_floor = max(0.0, min(1.0, float(texture_floor)))

        sampled_freqs: List[int] = []
        sampled_strengths: List[int] = []
        for sample_idx in range(total_samples):
            position = start_position + sample_idx * sample_step
            texture_strength = self._sample_looped(texture_samples, position)
            sampled_freq = self._sample_looped(freq_samples, position)
            # freq=0 and strength=0 means explicit silence — don't apply texture_floor
            if sampled_freq < 0.5 and texture_strength <= 0:
                sampled_freqs.append(0)
                sampled_strengths.append(0)
            else:
                lifted_texture = texture_floor + texture_strength * (1.0 - texture_floor)
                final_strength = lifted_texture * wave_scale
                sampled_freqs.append(max(0, min(255, int(round(sampled_freq)))))
                sampled_strengths.append(max(0, min(100, int(round(final_strength * 100)))))

        ops: List[str] = []
        for idx in range(0, total_samples, 4):
            freq_hex = "".join(f"{value:02X}" for value in sampled_freqs[idx:idx + 4])
            strength_hex = "".join(f"{value:02X}" for value in sampled_strengths[idx:idx + 4])
            ops.append(freq_hex + strength_hex)
        return json.dumps(ops, separators=(",", ":"))

    def build_scaled_wavestrs(self, name: Optional[str], strength_scale: float) -> List[str]:
        preset = self.get(name)
        if not preset or not preset["ops"]:
            return []
        scaled_ops = [self.scale_op(op, strength_scale) for op in preset["ops"]]
        return _ops_to_wavestrs(scaled_ops)
