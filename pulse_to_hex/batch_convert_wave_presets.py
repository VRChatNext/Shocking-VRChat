#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
from pathlib import Path

from dglab_pulse_converter import convert_to_ops


def build_preset_name(pulse_file: Path) -> str:
    return pulse_file.stem


def convert_pulse_file(pulse_file: Path, output_dir: Path, max_ops: int) -> Path:
    with pulse_file.open("r", encoding="utf-8", errors="replace") as fr:
        pulse_text = fr.read().strip()

    ops, wavestrs, header, sections = convert_to_ops(pulse_text, max_ops_per_msg=max_ops)
    preset_name = build_preset_name(pulse_file)
    output_path = output_dir / f"{preset_name}.json"

    import math
    speed = header.speed if header else 1

    # Save section metadata for preview (so we don't need .pulse file at runtime)
    preview_sections = []
    for sec in sections:
        if not sec.enabled or not sec.points:
            continue
        n_points = len(sec.points)
        duration = max(0, sec.duration)
        repeats = max(1, math.ceil(duration / n_points)) if duration > 0 else 1
        preview_sections.append({
            'freq_low': sec.freq_low,
            'freq_high': sec.freq_high,
            'freq_mode': sec.freq_mode,
            'duration': duration,
            'n_points': n_points,
            'repeats': repeats,
            'points': [{'strength': round(max(0, min(100, v))), 'anchor': flag == 1} for v, flag in sec.points],
        })

    payload = {
        "name": preset_name,
        "source_file": pulse_file.name,
        "num_ops": len(ops),
        "header": (header.__dict__ if header else None),
        "preview_sections": preview_sections,
        "wavestrs": wavestrs,
    }
    with output_path.open("w", encoding="utf-8") as fw:
        json.dump(payload, fw, ensure_ascii=False, indent=2)
        fw.write("\n")
    return output_path


def main():
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent

    ap = argparse.ArgumentParser(description="Batch convert DG-LAB .pulse files into wave preset JSON files.")
    ap.add_argument("--input-dir", default=str(repo_root / "dg-lab"), help="Directory containing .pulse files.")
    ap.add_argument("--output-dir", default=str(repo_root / "wave_presets"), help="Directory for generated preset JSON files.")
    ap.add_argument("--max-ops", type=int, default=86, help="Max ops per websocket message chunk.")
    args = ap.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pulse_files = sorted(input_dir.glob("*.pulse"))
    if not pulse_files:
        raise SystemExit(f"No .pulse files found in {input_dir}")

    generated = []
    for pulse_file in pulse_files:
        generated.append(convert_pulse_file(pulse_file, output_dir, args.max_ops))

    print(f"Converted {len(generated)} preset(s) into {output_dir}")
    for output_path in generated:
        print(output_path.name.encode("unicode_escape").decode("ascii"))


if __name__ == "__main__":
    main()
