#!/usr/bin/env python3
"""Repair Rare-card count aggregates from already saved trial checkpoint counts."""

import json
import math
from pathlib import Path

import simulate_new_w5000_common_uncommon as base
import simulate_new_w5000_common_uncommon_rare as report


output_dir = Path("output/new_w5000_common_uncommon_rare_30")
json_path = output_dir / "new_w5000_common_uncommon_rare.json"
payload = json.loads(json_path.read_text(encoding="utf-8"))

for wave in report.CHECKPOINTS:
    values = []
    execution_contributions = []
    for trial in payload["trials"]:
        state = trial["checkpoint"].get(str(wave))
        if state is None:
            continue
        rare_count = sum(state["counts"].get(key, 0) for key in report.RARE_KEYS)
        state["rare_cards"] = rare_count
        values.append(float(rare_count))
        execution_mult = 1.0 + 1.50 * state["counts"].get("execution", 0)
        execution_power = -math.log10(0.70 + 0.30 / execution_mult)
        old_execution_power = state["card_power_contribution"].get("execution", 0.0)
        state["card_power_contribution"]["execution"] = execution_power
        state["full_window_damage_power"] += execution_power - old_execution_power
        execution_contributions.append(execution_power)
    payload["summary"]["checkpoint"][str(wave)]["rare_cards"] = {
        "p25": base.percentile(values, 0.25),
        "p50": base.percentile(values, 0.50),
        "p75": base.percentile(values, 0.75),
    }
    payload["summary"]["checkpoint"][str(wave)]["rare_damage_power_contribution"]["execution"] = (
        sum(execution_contributions) / len(execution_contributions)
        if execution_contributions else 0.0
    )
    full_window_values = [
        float(trial["checkpoint"][str(wave)]["full_window_damage_power"])
        for trial in payload["trials"]
        if str(wave) in trial["checkpoint"]
    ]
    payload["summary"]["checkpoint"][str(wave)]["full_window_damage_power"] = {
        "p25": base.percentile(full_window_values, 0.25),
        "p50": base.percentile(full_window_values, 0.50),
        "p75": base.percentile(full_window_values, 0.75),
    }

payload["summary"]["rare"]["execution"]["damage_power_contribution"] = {
    str(wave): payload["summary"]["checkpoint"][str(wave)]["rare_damage_power_contribution"]["execution"]
    for wave in (500, 1000, 2500)
}

json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
report.write_csv(output_dir / "new_w5000_common_uncommon_rare_checkpoints.csv", payload)
report.write_markdown(output_dir / "new_w5000_common_uncommon_rare.md", payload)
