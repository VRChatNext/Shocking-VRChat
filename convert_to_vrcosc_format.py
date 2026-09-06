#!/usr/bin/env python3
"""Convert wave_presets/*.json to DG-LAB-VRCOSC pulse_data.py format."""
import json, glob, os, re

output_names = []
output_data = {}

for path in sorted(glob.glob("wave_presets/pulse-*.json")):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Extract readable name from filename: "pulse-搓搓揉揉-9058076" -> "搓搓揉揉"
    name = data["name"]
    match = re.match(r"pulse-(.+?)-\d+", name)
    display_name = match.group(1) if match else name

    # Parse all hex ops from wavestrs
    ops = []
    for wavestr in data["wavestrs"]:
        hex_list = json.loads(wavestr)
        for h in hex_list:
            b = bytes.fromhex(h)
            freq = tuple(b[:4])
            strength = tuple(b[4:])
            ops.append((freq, strength))

    output_names.append(display_name)
    output_data[display_name] = ops

# Write output
with open("pulse_data_converted.py", "w", encoding="utf-8") as f:
    f.write("PULSE_NAME = [\n")
    for n in output_names:
        f.write(f"    '{n}',\n")
    f.write("]\n\nPULSE_DATA = {\n")
    for n in output_names:
        f.write(f"    '{n}': [\n")
        for freq, strength in output_data[n]:
            f.write(f"        ({freq}, {strength}),\n")
        f.write("    ],\n")
    f.write("}\n")

print(f"Converted {len(output_names)} presets -> pulse_data_converted.py")
