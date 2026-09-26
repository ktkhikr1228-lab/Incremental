#!/usr/bin/env python3
"""One-run paired probe of Standard-bot score versus exact immediate Power."""
from __future__ import annotations

import copy
import csv
import json
import math
from pathlib import Path
import statistics

import simulate_new_w5000_legendary_v01 as lg
import simulate_new_w5000_common_uncommon_rare_epic as epic
import simulate_new_w5000_dp_v01 as dp
weapon = lg.weapon


TARGETS = {
    "power_up", "rapid_fire", "critical_eye", "critical_power",
    "balanced_training", "critical_training", "multi_hit",
    "follow_up_strike", "re_action", "execution", "multi_crit",
    "time_collapse", "critical_overload", "recursive_follow_up",
    "endless_action", "critical_singularity", "weapon_mitosis",
    "supplemental_inversion",
}


def main() -> None:
    out = Path("output/standard_score_scale_calibration")
    out.mkdir(parents=True, exist_ok=True)
    # This is one deterministic Standard run, not a Monte Carlo comparison.
    lg.monte_carlo_condition("score_scale_probe", True, 1, 20260828, 220, True)
    states = lg.CAPTURE_STATES.get(0, {})
    rows: list[dict] = []
    build_summary: dict[str, dict] = {}
    for wave in (500, 600, 750):
        snapshot = states.get(wave)
        if snapshot is None:
            continue
        run = copy.deepcopy(snapshot["run"])
        permanent = copy.deepcopy(snapshot["permanent"])
        permanent._weapon_current_run = run
        config = dp.ACTIVE_CONFIG
        boss = wave % 10 == 0
        before = dp.candidate_snapshot(run, permanent, boss, config).log_dps
        build_summary[str(wave)] = {
            "sample_trial": 0,
            "card_count": run.card_count,
            "counts": dict(run.counts),
            "crit_rate": float(dp.candidate_snapshot(run, permanent, boss, config).crit_chance),
            "crit_multiplier": float(dp.candidate_snapshot(run, permanent, boss, config).crit_multiplier),
            "follow_up_rate": float(dp.candidate_snapshot(run, permanent, boss, config).follow_rate),
            "weapon_rarity": getattr(weapon.equipped(run), "rarity", None),
            "power_before": float(before),
        }
        card_pool = {item.key: item for item in tuple(epic.ALL_CARDS) + tuple(lg.LEGENDARY_CARDS)}
        for item in card_pool.values():
            if item.key not in TARGETS:
                continue
            if item.unique and run.counts.get(item.key, 0):
                continue
            standard_score = lg.LEGENDARY_SCORE_ORIGINAL("balanced", item, run, permanent, wave + 1, config)
            dedicated_score = lg.legendary_card_score("balanced", item, run, permanent, wave + 1, config)
            test_run, test_permanent = copy.deepcopy(run), copy.deepcopy(permanent)
            test_permanent._weapon_current_run = test_run
            previous_trial, previous_permanent = lg.ACTIVE_TRIAL, lg.ACTIVE_PERMANENT
            lg.ACTIVE_TRIAL = -1
            lg.ACTIVE_PERMANENT = test_permanent
            try:
                lg.acquire_card(test_run, item)
            finally:
                lg.ACTIVE_TRIAL, lg.ACTIVE_PERMANENT = previous_trial, previous_permanent
            after = dp.candidate_snapshot(test_run, test_permanent, boss, config).log_dps
            delta = float(after - before)
            score = dedicated_score if item.rarity == "L" else standard_score
            rows.append({
                "wave": wave, "card_id": item.key, "rarity": item.rarity,
                "standard_score": float(standard_score),
                "legendary_dedicated_score": float(dedicated_score) if item.rarity == "L" else None,
                "score_used_for_scale": float(score),
                "power_before": float(before), "power_after": float(after),
                "immediate_power_delta": delta,
                "score_per_power_delta": float(score / delta) if abs(delta) > 1e-12 else None,
                "tags": list(item.tags),
                "available_in_representative_state": True,
            })

    bands = [(0.005, 0.015, "+0.01"), (0.015, 0.03, "+0.02"),
             (0.04, 0.06, "+0.05"), (0.08, 0.12, "+0.10"), (0.20, math.inf, "+0.20以上")]
    band_summary = []
    common_rows = [r for r in rows if r["rarity"] != "L" and r["immediate_power_delta"] > 0]
    for low, high, label in bands:
        selected = [r for r in common_rows if low <= r["immediate_power_delta"] < high]
        scores = [r["standard_score"] for r in selected]
        band_summary.append({
            "power_delta_band": label, "sample_count": len(selected),
            "score_median": statistics.median(scores) if scores else None,
            "score_min": min(scores) if scores else None,
            "score_max": max(scores) if scores else None,
            "samples": [{"wave": r["wave"], "card_id": r["card_id"],
                         "power_delta": r["immediate_power_delta"], "score": r["standard_score"]}
                        for r in selected],
        })
    for target_delta in (0.01, 0.02, 0.05, 0.10):
        nearest = min(common_rows, key=lambda r: abs(r["immediate_power_delta"] - target_delta), default=None)
        if nearest is not None:
            band_summary.append({
                "power_delta_target": target_delta,
                "closest_card": {"wave": nearest["wave"], "card_id": nearest["card_id"],
                                 "actual_delta": nearest["immediate_power_delta"],
                                 "standard_score": nearest["standard_score"]},
            })
    payload = {
        "settings": {"source": "one deterministic Standard run", "seed": 20260828,
                     "DP": "BC", "weapon": "C_drop_affix", "relic": False,
                     "refinement": False, "trials": 1, "no_balance_changes": True},
        "representative_builds": build_summary,
        "card_rows": rows,
        "power_delta_bands": band_summary,
    }
    (out / "standard_score_scale_calibration.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with (out / "standard_score_scale_calibration.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["wave", "card_id", "rarity", "standard_score",
            "legendary_dedicated_score", "score_used_for_scale", "power_before", "power_after",
            "immediate_power_delta", "score_per_power_delta", "tags", "available_in_representative_state"])
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "tags": ",".join(row["tags"])})
    print(json.dumps({"rows": len(rows), "captured_waves": sorted(map(int, build_summary)),
                      "files": [str(out / "standard_score_scale_calibration.csv"),
                                str(out / "standard_score_scale_calibration.json")]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
