#!/usr/bin/env python3
"""Connectivity and small-sample behavior probe for Unlimited Boost v0.1."""

from __future__ import annotations

import argparse
import gzip
import json
import pickle
import statistics
from pathlib import Path

import diagnose_w5000_v1_precore as diag
import experiment_w5000_v1_integrated_core_dp as integrated
import simulate_first_prestige_v1 as sim


DP_SCALE = 0.10
CORE_SCALE = 0.15
PROFILES = {
    "A_boost_off": sim.UnlimitedBoostConfig(enabled=False),
    "B_boost_on": sim.UnlimitedBoostConfig(enabled=True),
}
CHECKPOINTS = (4000, 4250, 4500, 4750, 5000)


def fmt(value, digits=2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def augment(row: dict) -> None:
    first_w4000 = next(
        (index for index, run in enumerate(row["run_rows"]) if run["max_wave"] >= 4000),
        None,
    )
    row["first_w4000_run_index"] = None if first_w4000 is None else first_w4000 + 1
    if first_w4000 is None:
        row["additional_runs_w4000_to_w5000"] = None
        row["game_hours_after_w4000"] = None
        return
    success_index = next(
        (index for index, run in enumerate(row["run_rows"]) if run["max_wave"] >= 5000),
        None,
    )
    row["additional_runs_w4000_to_w5000"] = (
        None if success_index is None else success_index - first_w4000
    )
    first_run = row["run_rows"][first_w4000]
    elapsed = first_run["reach_w4000_seconds"]
    after_seconds = first_run["game_seconds"] - (elapsed or 0.0)
    after_seconds += sum(
        run["game_seconds"] for run in row["run_rows"][first_w4000 + 1:]
    )
    row["game_hours_after_w4000"] = after_seconds / 3600.0


def summarize(label: str, rows: list[dict]) -> dict:
    base = integrated.summarize_rows(rows)
    reached_w4000 = [row for row in rows if "4000" in row["checkpoints"]]
    successes = [row for row in rows if row["success"]]
    base["w4000_reached"] = len(reached_w4000)
    base["runs_w4000_to_w5000"] = diag.dist([
        row["additional_runs_w4000_to_w5000"]
        for row in successes if row["additional_runs_w4000_to_w5000"] is not None
    ])
    base["hours_after_w4000"] = diag.dist([
        row["game_hours_after_w4000"]
        for row in successes if row["game_hours_after_w4000"] is not None
    ])
    base["w4000_group_boost_levels"] = {
        key: diag.dist([row["unlimited_boost_levels"][key] for row in reached_w4000])
        for key in sim.UNLIMITED_BOOST_NODES
    }
    base["w4000_group_weapon_spent"] = diag.dist([
        row["unlimited_boost_weapon_spent"] for row in reached_w4000
    ])
    base["w4000_group_relic_spent"] = diag.dist([
        row["unlimited_boost_relic_spent"] for row in reached_w4000
    ])
    for acquired, key in ((True, "barrage_acquired"), (False, "barrage_not_acquired")):
        selected = [row for row in rows if row["infinite_barrage_acquired"] is acquired]
        base[key] = integrated.summarize_rows(selected, include_rows=False)
    return base


def markdown(payload: dict) -> str:
    lines = [
        "# w5000_v1 Unlimited Boost v0.1 probe", "",
        "Diagnostic baseline: Boss Devourer base-heavy B, Infinite Barrage 37.5%, late DP 10%, Core flat 15%, W2500 guaranteed Legendary OFF.", "",
        "## Progression", "",
        "| Profile | W4000 N | W4250 | W4500 | W4750 | W5000 | Runs W4000→5000 P25/P50/P75 | Hours after W4000 P50 | Success Margin P50 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, item in payload["profiles"].items():
        runs = item["runs_w4000_to_w5000"]
        lines.append(
            f"| {label} | {item['w4000_reached']} | "
            + " | ".join(f"{item['checkpoints'][str(w)]['reach_rate']:.0%}" for w in CHECKPOINTS[1:])
            + f" | {fmt(runs['p25'],1)}/{fmt(runs['p50'],1)}/{fmt(runs['p75'],1)}"
            f" | {fmt(item['hours_after_w4000']['p50'],3)}"
            f" | {fmt(item['w5000_margin']['p50'])} |"
        )
    lines += [
        "", "## Purchased levels and materials (W4000-reaching trials)", "",
        "| Profile | Base ATK | Weapon ATK | AS | Crit Mult | All Damage | Boss Damage | Weapon Pt used P50 | Relic Dust used P50 | Boost Power P50 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, item in payload["profiles"].items():
        levels = item["w4000_group_boost_levels"]
        lines.append(
            f"| {label} | "
            + " | ".join(fmt(levels[key]["p50"], 0) for key in sim.UNLIMITED_BOOST_NODES)
            + f" | {fmt(item['w4000_group_weapon_spent']['p50'],0)}"
            f" | {fmt(item['w4000_group_relic_spent']['p50'],0)}"
            f" | {fmt(item['boost_power']['p50'])} |"
        )
    lines += ["", "## Checkpoint contribution P50", "", "| Profile | W | Boost | Core | late DP | Margin |", "|---|---:|---:|---:|---:|---:|"]
    for label, item in payload["profiles"].items():
        for wave in CHECKPOINTS:
            cp = item["checkpoints"][str(wave)]
            lines.append(
                f"| {label} | {wave} | {fmt(cp['boost_power']['p50'])}"
                f" | {fmt(cp['core_power']['p50'])} | {fmt(cp['late_dp_power']['p50'])}"
                f" | {fmt(cp['margin']['p50'])} |"
            )
    lines += ["", "## Infinite Barrage interaction", "", "| Profile | Group | N | W5000 |", "|---|---|---:|---:|"]
    for label, item in payload["profiles"].items():
        for key, name in (("barrage_acquired", "acquired"), ("barrage_not_acquired", "not acquired")):
            group = item[key]
            if group["samples"]:
                lines.append(f"| {label} | {name} | {group['samples']} | {group['success_rate']:.0%} |")
    lines += [
        "", "## Experimental values", "",
        "- Costs: Weapon nodes 80/70/90 Pt; Relic nodes 35/50/40 Dust; ×1.70 per node level.",
        "- Effects: Base/Weapon/AS +5% per effective level; Crit Mult +0.10; All Damage +5%; Boss Damage +10%.",
        "- Softcap: after Lv5, each level contributes 50% effect. Purchase policy balances the lowest node levels per affordable currency.",
        "", "## Validation", "",
        f"- paired states: {payload['state_count']}",
        f"- errors/nonfinite/overflow: {payload['error_count']}/{payload['nonfinite_count']}/{payload['overflow_count']}",
        "- Finale is not implemented. No formal adoption or large-trial run.", "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--states", type=Path,
        default=Path("output/w5000_v1_micro_core_10_states_final/w2500_checkpoint_states.pkl.gz"),
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("output/w5000_v1_unlimited_boost_10_states"),
    )
    args = parser.parse_args()
    with gzip.open(args.states, "rb") as handle:
        captures = pickle.load(handle)
    if len(captures) != 10:
        raise ValueError(f"expected 10 W2500 states, found {len(captures)}")

    grouped = {label: [] for label in PROFILES}
    errors = []
    for label, boost_config in PROFILES.items():
        for capture in captures.values():
            try:
                row = integrated.replay_one(
                    capture, label, DP_SCALE, CORE_SCALE,
                    unlimited_boost_config=boost_config,
                )
                augment(row)
                grouped[label].append(row)
            except Exception as exc:
                errors.append({
                    "profile": label, "trial": capture["trial"],
                    "type": type(exc).__name__, "message": str(exc),
                })
    profiles = {label: summarize(label, rows) for label, rows in grouped.items()}
    nonfinite = sum(len(row["nonfinite"]) for rows in grouped.values() for row in rows)
    payload = {
        "state_count": len(captures), "trial_ids": sorted(captures),
        "profiles": profiles, "boost_configs": {
            label: vars(config) for label, config in PROFILES.items()
        },
        "error_count": len(errors), "nonfinite_count": nonfinite,
        "overflow_count": sum(error["type"] == "OverflowError" for error in errors),
        "errors": errors, "formal_changed": False, "balance_adopted": False,
        "finale_implemented": False,
    }
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = output / "unlimited_boost_report.md"
    summary = output / "unlimited_boost_summary.json"
    report.write_text(markdown(payload), encoding="utf-8")
    summary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "report": str(report), "json": str(summary), "states": len(captures),
        "errors": len(errors), "nonfinite": nonfinite,
        "overflow": payload["overflow_count"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
