#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DG-LAB .pulse → hex op JSON converter.

Converts Dungeonlab+pulse export format to DG-LAB WebSocket protocol wave data.

Each output op is a 16-char hex string: 8 chars freq (4 bytes) + 8 chars strength (4 bytes).
Each op = 100ms playback (4 × 25ms sub-steps).

See doc/pulse_format.md for format specification.
"""

import json
import math
from dataclasses import dataclass
from typing import List, Tuple, Optional


PULSE_PREFIX = "Dungeonlab+pulse:"

# --- Frequency slider → interval (ms) lookup table ---
# Built according to the non-linear stepped mapping (84 positions, 0-83)
_FREQ_TABLE: List[int] = []

def _build_freq_table():
    """Build the slider → interval(ms) lookup table."""
    table = []
    # [10, 50) step=1: 40 positions
    for ms in range(10, 50):
        table.append(ms)
    # [50, 80) step=2: 15 positions
    ms = 50
    while ms < 80:
        table.append(ms)
        ms += 2
    # [80, 100) step=5: 4 positions
    ms = 80
    while ms < 100:
        table.append(ms)
        ms += 5
    # [100, 200) step=10: 10 positions
    ms = 100
    while ms < 200:
        table.append(ms)
        ms += 10
    # [200, 400] step=33,33,34 cycle: 7 positions
    ms = 200
    steps = [33, 33, 34]
    i = 0
    while ms <= 400:
        table.append(ms)
        if ms == 400:
            break
        ms += steps[i % 3]
        i += 1
    # (400, 600) step=50: 3 positions (450, 500, 550)
    ms = 450
    while ms < 600:
        table.append(ms)
        ms += 50
    # [600, 1000] step=100: 5 positions
    ms = 600
    while ms <= 1000:
        table.append(ms)
        ms += 100
    return table

_FREQ_TABLE = _build_freq_table()
assert len(_FREQ_TABLE) == 84, f"Expected 84 positions, got {len(_FREQ_TABLE)}"
assert _FREQ_TABLE[0] == 10
assert _FREQ_TABLE[83] == 1000


def slider_to_interval_ms(slider: int) -> int:
    """Convert frequency slider position (0-83) to pulse interval in ms."""
    slider = max(0, min(83, int(slider)))
    return _FREQ_TABLE[slider]


def slider_to_freq_byte(slider: int) -> int:
    """
    Convert frequency slider position (0-83) to the freq byte used in hex ops.

    The freq byte IS the pulse interval in milliseconds, clamped to [10, 240].
    Device protocol range: 0x0A (10ms, 100Hz) to 0xF0 (240ms, ~4Hz).
    Slider values above 75 (>240ms) are clamped to 240.
    """
    interval = slider_to_interval_ms(slider)
    return max(10, min(240, interval))


# --- Data classes ---

@dataclass
class PulseHeader:
    rest_ticks: int      # silence at end (ticks, each 100ms)
    speed: int           # playback speed multiplier (1, 2, 4)
    param3: Optional[int]  # unknown third parameter
    raw: str

@dataclass
class PulseSection:
    freq_low: int        # frequency slider low bound (0-83); used as fixed value in mode 1
    freq_high: int       # frequency slider high bound (0-83); ignored in mode 1
    duration: int        # minimum duration in ticks
    freq_mode: int       # 1=fixed, 2=linear, 3=cycle, 4=stepped
    enabled: bool        # whether this section is active
    points: List[Tuple[float, int]]  # (strength_percent, anchor_flag)
    raw: str


# --- Parser ---

def _parse_float(s: str) -> float:
    """Safely parse a float from potentially messy input."""
    try:
        return float(s)
    except ValueError:
        import re
        cleaned = re.sub(r"[^\d.\-]", "", s)
        return float(cleaned) if cleaned else 0.0


def parse_pulse(pulse_text: str) -> Tuple[Optional[PulseHeader], List[PulseSection]]:
    """Parse a .pulse file into header and sections."""
    pulse_text = pulse_text.strip()
    if pulse_text.startswith(PULSE_PREFIX):
        body = pulse_text[len(PULSE_PREFIX):]
    else:
        body = pulse_text

    # Parse optional header
    header = None
    if "=" in body:
        header_str, sections_str = body.split("=", 1)
        parts = [x.strip() for x in header_str.split(",") if x.strip()]
        rest_ticks = int(float(parts[0])) if len(parts) > 0 else 0
        speed = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
        param3 = int(float(parts[2])) if len(parts) > 2 else None
        header = PulseHeader(rest_ticks=rest_ticks, speed=speed, param3=param3, raw=header_str)
    else:
        sections_str = body

    # Parse sections
    sections: List[PulseSection] = []
    for raw in sections_str.split("+section+"):
        raw = raw.strip()
        if not raw:
            continue

        if "/" in raw:
            meta_str, points_str = raw.split("/", 1)
        else:
            meta_str, points_str = raw, ""

        # Parse meta
        meta = []
        for tok in meta_str.split(","):
            tok = tok.strip()
            if tok:
                try:
                    meta.append(int(float(tok)))
                except ValueError:
                    pass

        freq_low = meta[0] if len(meta) > 0 else 0
        freq_high = meta[1] if len(meta) > 1 else freq_low
        duration = meta[2] if len(meta) > 2 else 0
        freq_mode = meta[3] if len(meta) > 3 else 1
        enabled = bool(meta[4]) if len(meta) > 4 else True

        # Parse points
        points: List[Tuple[float, int]] = []
        if points_str.strip():
            for p in points_str.split(","):
                p = p.strip()
                if not p:
                    continue
                if "-" in p:
                    val_str, flag_str = p.rsplit("-", 1)
                    val = _parse_float(val_str)
                    try:
                        flag = int(float(flag_str))
                    except ValueError:
                        flag = 0
                else:
                    val = _parse_float(p)
                    flag = 0
                points.append((val, flag))

        sections.append(PulseSection(
            freq_low=freq_low,
            freq_high=freq_high,
            duration=duration,
            freq_mode=freq_mode,
            enabled=enabled,
            points=points,
            raw=raw,
        ))

    return header, sections


# --- Converter ---

def convert_to_ops(
    pulse_text: str,
    *,
    max_ops_per_msg: int = 86,
) -> Tuple[List[str], List[str], Optional[PulseHeader], List[PulseSection]]:
    """
    Convert .pulse text to hex ops.

    Returns:
        ops: list of 16-char hex strings (uppercase)
        wavestrs: list of JSON array strings (chunked for WS protocol)
        header: parsed header (or None)
        sections: parsed sections
    """
    header, sections = parse_pulse(pulse_text)

    # Speed determines how many 25ms slots each point occupies
    # speed=4: 1 point = 25ms = 1 slot; speed=2: 1 point = 50ms = 2 slots; speed=1: 1 point = 100ms = 4 slots
    speed = header.speed if header else 1
    slots_per_point = 4 // speed  # 4, 2, or 1

    ops: List[str] = []

    for sec in sections:
        # Skip disabled sections
        if not sec.enabled:
            continue

        # Skip sections with no points
        if not sec.points:
            continue

        n_points = len(sec.points)
        duration = max(0, sec.duration)

        # Calculate number of complete repetitions
        # Wave unit must play completely; repeat ceil(D/N) times, at least 1
        if duration <= 0 or n_points >= duration:
            repeats = 1
        else:
            repeats = math.ceil(duration / n_points)

        # Get strength values (each point = 1 tick, expanded to slots_per_point sub-steps)
        strengths = [max(0.0, min(100.0, v)) for v, _ in sec.points]

        # Calculate freq bytes for interpolation endpoints
        f_low = slider_to_freq_byte(sec.freq_low)
        f_high = slider_to_freq_byte(sec.freq_high)

        # Build the full sequence of slots (all repetitions, expanded by speed)
        # Each point expands to slots_per_point slots (25ms each)
        all_strengths: List[float] = []
        all_freqs: List[int] = []
        total_points = repeats * n_points  # logical points
        total_slots = total_points * slots_per_point  # actual 25ms slots

        for point_idx in range(total_points):
            unit_idx = point_idx % n_points      # position within current wave unit
            repeat_idx = point_idx // n_points   # which repetition we're in

            # Strength from point list
            strength = strengths[unit_idx]

            # Frequency depends on mode (calculated per logical point)
            if sec.freq_mode == 1:
                freq = f_low
            elif sec.freq_mode == 2:
                # 节内渐变: linear across entire section
                t = point_idx / (total_points - 1) if total_points > 1 else 0.0
                freq = int(round(f_low + (f_high - f_low) * t))
            elif sec.freq_mode == 3:
                # 元内渐变: linear within each wave unit
                t = unit_idx / (n_points - 1) if n_points > 1 else 0.0
                freq = int(round(f_low + (f_high - f_low) * t))
            elif sec.freq_mode == 4:
                # 元间渐变: fixed within unit, changes between units
                t = repeat_idx / (repeats - 1) if repeats > 1 else 0.0
                freq = int(round(f_low + (f_high - f_low) * t))
            else:
                freq = f_low

            # Expand this point to slots_per_point slots
            for _ in range(slots_per_point):
                all_strengths.append(strength)
                all_freqs.append(freq)

        # Pad to multiple of 4 (repeat last value)
        while len(all_strengths) % 4 != 0:
            all_strengths.append(all_strengths[-1])
            all_freqs.append(all_freqs[-1])

        # Pack every 4 points into 1 op
        for i in range(0, len(all_strengths), 4):
            freq_bytes = [max(10, min(240, int(round(all_freqs[i + j])))) for j in range(4)]
            strength_bytes = [max(0, min(100, int(round(all_strengths[i + j])))) for j in range(4)]
            freq_hex = "".join(f"{b:02X}" for b in freq_bytes)
            strength_hex = "".join(f"{b:02X}" for b in strength_bytes)
            ops.append(freq_hex + strength_hex)

    # Append rest silence: rest_ticks × slots_per_point slots of zero
    if header and header.rest_ticks > 0:
        rest_slots = header.rest_ticks * slots_per_point
        # Pad to multiple of 4
        rest_slots += (-rest_slots) % 4
        for _ in range(rest_slots // 4):
            ops.append("0000000000000000")

    # Build wavestrs (chunked JSON arrays for WS protocol)
    wavestrs: List[str] = []
    for i in range(0, len(ops), max_ops_per_msg):
        chunk = ops[i:i + max_ops_per_msg]
        wavestrs.append(json.dumps(chunk, separators=(",", ":")))

    return ops, wavestrs, header, sections


# --- CLI ---

def main():
    import argparse
    ap = argparse.ArgumentParser(
        description="Convert DG-LAB .pulse file to hex op JSON for WebSocket protocol."
    )
    ap.add_argument("pulse_file", help="Path to .pulse file")
    ap.add_argument("--out", default="", help="Output JSON path (default: <input>.wavestr.json)")
    ap.add_argument("--max-ops", type=int, default=86, help="Max ops per WS message chunk")
    args = ap.parse_args()

    with open(args.pulse_file, "r", encoding="utf-8", errors="replace") as f:
        txt = f.read().strip()

    ops, wavestrs, header, sections = convert_to_ops(txt, max_ops_per_msg=args.max_ops)
    enabled_sections = [s for s in sections if s.enabled]

    out_path = args.out or (args.pulse_file + ".wavestr.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "wavestrs": wavestrs,
            "num_ops": len(ops),
            "header": header.__dict__ if header else None,
        }, f, ensure_ascii=False, indent=2)

    print(f"Sections: {len(sections)} total, {len(enabled_sections)} enabled")
    print(f"Total ops: {len(ops)} ({len(ops) * 0.1:.1f}s)")
    print(f"WS message chunks: {len(wavestrs)}")
    print(f"Output: {out_path}")


if __name__ == "__main__":
    main()
