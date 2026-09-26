#!/usr/bin/env python3
"""Repair Epic aggregates from the already saved 30-trial checkpoints."""

import json
from pathlib import Path

import simulate_new_w5000_common_uncommon as base
import simulate_new_w5000_common_uncommon_rare_epic as report


output_dir = Path("output/new_w5000_common_uncommon_rare_epic_30")
json_path = output_dir / "new_w5000_common_uncommon_rare_epic.json"
payload = json.loads(json_path.read_text(encoding="utf-8"))
trials = payload["trials"]
observed_wave = "750"
observed = [trial for trial in trials if observed_wave in trial["checkpoint"]]

for wave, checkpoint in payload["summary"]["checkpoint"].items():
    if checkpoint["reach_count"] == 0:
        checkpoint["epic_ownership_rate"] = {key: None for key in report.EPIC_KEYS}
        checkpoint["epic_power_contribution"] = {key: None for key in report.EPIC_KEYS}

for key in report.EPIC_KEYS:
    owned = [trial for trial in observed if trial["checkpoint"][observed_wave]["counts"].get(key, 0)]
    unowned = [trial for trial in observed if not trial["checkpoint"][observed_wave]["counts"].get(key, 0)]
    waves = [
        float(trial["checkpoint"][observed_wave]["epic_acquisition_waves"][key])
        for trial in owned
        if key in trial["checkpoint"][observed_wave]["epic_acquisition_waves"]
    ]
    item = payload["summary"]["epic"][key]
    item.pop("acquisition_rate_first_w500_run", None)
    item["observed_through_wave"] = 750
    item["acquisition_rate"] = len(owned) / len(observed) if observed else 0.0
    item["acquisition_wave_p50"] = base.percentile(waves, 0.50)
    item["ownership_rate"] = {
        wave: payload["summary"]["checkpoint"][wave]["epic_ownership_rate"][key]
        for wave in ("500", "1000", "1500", "2500")
    }
    item["damage_power_contribution"] = {
        wave: payload["summary"]["checkpoint"][wave]["epic_power_contribution"][key]
        for wave in ("500", "1000", "1500", "2500")
    }
    item["best_wave_owned_p50"] = base.percentile([float(x["best_failed_wave"]) for x in owned], 0.50)
    item["best_wave_unowned_p50"] = base.percentile([float(x["best_failed_wave"]) for x in unowned], 0.50)

states = [trial["checkpoint"][observed_wave] for trial in observed]
combo_pairs = {
    "follow_up_strike_plus_echo": ("follow_up_strike", "follow_up_echo"),
    "re_action_plus_chain": ("re_action", "chain_action"),
    "supplemental_plus_resonant": ("supplemental_damage", "resonant_damage"),
    "supplemental_plus_echoing": ("supplemental_damage", "echoing_damage"),
    "time_collapse_plus_last_stand": ("time_collapse", "last_stand"),
}
payload["summary"]["observed_combinations_w750"] = {
    name: sum(bool(state["counts"].get(a, 0) and state["counts"].get(b, 0)) for state in states)
    for name, (a, b) in combo_pairs.items()
}

json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
report.write_csv(output_dir / "new_w5000_common_uncommon_rare_epic_checkpoints.csv", payload)
report.write_markdown(output_dir / "new_w5000_common_uncommon_rare_epic.md", payload)
