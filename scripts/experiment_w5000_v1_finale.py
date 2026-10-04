#!/usr/bin/env python3
"""Small paired probe for Finale v0.1 and Unlimited Boost interaction."""

from __future__ import annotations

import argparse
import collections
import gzip
import json
import pickle
from pathlib import Path

import diagnose_w5000_v1_precore as diag
import experiment_w5000_v1_integrated_core_dp as integrated
import simulate_first_prestige_v1 as sim


DP_SCALE = 0.10
CORE_SCALE = 0.15
CHECKPOINTS = (4000, 4500, 4600, 4700, 4800, 4900, 5000)
PROFILES = {
    "A_finale_off_boost_off": (
        sim.FinaleConfig(enabled=False), sim.UnlimitedBoostConfig(enabled=False),
    ),
    "B_finale_on_boost_off": (
        sim.FinaleConfig(enabled=True), sim.UnlimitedBoostConfig(enabled=False),
    ),
    "C_finale_on_boost_on": (
        sim.FinaleConfig(enabled=True), sim.UnlimitedBoostConfig(enabled=True),
    ),
}


def fmt(value, digits=2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def augment_threshold(row: dict, wave: int) -> None:
    first_index = next(
        (index for index, run in enumerate(row["run_rows"]) if run["max_wave"] >= wave),
        None,
    )
    prefix = f"w{wave}"
    if first_index is None:
        row[f"{prefix}_to_w5000_runs"] = None
        row[f"hours_after_{prefix}"] = None
        return
    success_index = next(
        (index for index, run in enumerate(row["run_rows"]) if run["max_wave"] >= 5000),
        None,
    )
    row[f"{prefix}_to_w5000_runs"] = (
        None if success_index is None else success_index - first_index
    )
    first_run = row["run_rows"][first_index]
    reached_seconds = first_run[f"reach_w{wave}_seconds"] or 0.0
    seconds = first_run["game_seconds"] - reached_seconds
    seconds += sum(run["game_seconds"] for run in row["run_rows"][first_index + 1:])
    row[f"hours_after_{prefix}"] = seconds / 3600.0


def subgroup(rows: list[dict], acquired: bool) -> dict:
    selected = [row for row in rows if row["infinite_barrage_acquired"] is acquired]
    return {
        "samples": len(selected),
        "successes": sum(row["success"] for row in selected),
        "success_rate": (
            sum(row["success"] for row in selected) / len(selected) if selected else None
        ),
    }


def summarize(rows: list[dict]) -> dict:
    successes = [row for row in rows if row["success"]]
    reached_w4000 = [row for row in rows if "4000" in row["checkpoints"]]
    result = {
        "samples": len(rows),
        "checkpoints": {},
        "first_stop_wave": dict(sorted(collections.Counter(
            str(row["first_run_stop_wave"] or 5000) for row in rows
        ).items(), key=lambda item: int(item[0]))),
        "death_wave_4500_plus": dict(sorted(collections.Counter(
            str(run["failure_wave"])
            for row in rows for run in row["run_rows"]
            if run["failure_wave"] is not None and run["failure_wave"] >= 4500
        ).items(), key=lambda item: int(item[0]))),
        "runs_w4000_to_w5000": diag.dist([
            row["w4000_to_w5000_runs"] for row in successes
            if row["w4000_to_w5000_runs"] is not None
        ]),
        "runs_w4500_to_w5000": diag.dist([
            row["w4500_to_w5000_runs"] for row in successes
            if row["w4500_to_w5000_runs"] is not None
        ]),
        "hours_after_w4000": diag.dist([
            row["hours_after_w4000"] for row in successes
            if row["hours_after_w4000"] is not None
        ]),
        "hours_after_w4500": diag.dist([
            row["hours_after_w4500"] for row in successes
            if row["hours_after_w4500"] is not None
        ]),
        "w5000_margin": diag.dist([
            row["w5000_margin"] for row in successes if row["w5000_margin"] is not None
        ]),
        "boost_levels": {
            key: diag.dist([row["unlimited_boost_levels"][key] for row in reached_w4000])
            for key in sim.UNLIMITED_BOOST_NODES
        },
        "weapon_spent": diag.dist([
            row["unlimited_boost_weapon_spent"] for row in reached_w4000
        ]),
        "relic_spent": diag.dist([
            row["unlimited_boost_relic_spent"] for row in reached_w4000
        ]),
        "barrage_acquired": subgroup(rows, True),
        "barrage_not_acquired": subgroup(rows, False),
        "rows": rows,
    }
    for wave in CHECKPOINTS:
        states = [row["checkpoints"][str(wave)] for row in rows if str(wave) in row["checkpoints"]]
        result["checkpoints"][str(wave)] = {
            "reached": len(states), "reach_rate": len(states) / len(rows),
            "margin": diag.dist([float(item["margin_power"]) for item in states]),
            "finale_added_power": diag.dist([
                float(item.get("finale_added_power", 0.0)) for item in states
            ]),
            "boost_power": diag.dist([float(item.get("boost_power", 0.0)) for item in states]),
            "core_power": diag.dist([float(item.get("core_power", 0.0)) for item in states]),
            "late_dp_power": diag.dist([float(item.get("late_dp_power", 0.0)) for item in states]),
        }
    return result


def markdown(payload: dict) -> str:
    lines = [
        "# w5000_v1 Finale v0.1 probe", "",
        "Baseline: Boss Devourer base-heavy B, Infinite Barrage 37.5%, late DP 10%, Core flat 15%, W2500 guaranteed Legendary OFF.", "",
        "## Reach", "",
        "| Profile | W4000 | W4500 | W4600 | W4700 | W4800 | W4900 | W5000 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, item in payload["profiles"].items():
        lines.append(
            f"| {label} | " + " | ".join(
                f"{item['checkpoints'][str(w)]['reach_rate']:.0%}" for w in CHECKPOINTS
            ) + " |"
        )
    lines += [
        "", "## Runs and time", "",
        "| Profile | W4000→5000 Runs P25/P50/P75 | W4500→5000 Runs P25/P50/P75 | Hours after W4000 P50 | Hours after W4500 P50 | W5000 Margin P50 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, item in payload["profiles"].items():
        r4, r45 = item["runs_w4000_to_w5000"], item["runs_w4500_to_w5000"]
        lines.append(
            f"| {label} | {fmt(r4['p25'],1)}/{fmt(r4['p50'],1)}/{fmt(r4['p75'],1)}"
            f" | {fmt(r45['p25'],1)}/{fmt(r45['p50'],1)}/{fmt(r45['p75'],1)}"
            f" | {fmt(item['hours_after_w4000']['p50'],3)}"
            f" | {fmt(item['hours_after_w4500']['p50'],3)}"
            f" | {fmt(item['w5000_margin']['p50'])} |"
        )
    lines += ["", "## Checkpoint margin and contributions", "", "| Profile | W | Finale | Boost | Core | late DP | Margin P50 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for label, item in payload["profiles"].items():
        for wave in CHECKPOINTS:
            cp = item["checkpoints"][str(wave)]
            lines.append(
                f"| {label} | {wave} | {fmt(cp['finale_added_power']['p50'])}"
                f" | {fmt(cp['boost_power']['p50'])} | {fmt(cp['core_power']['p50'])}"
                f" | {fmt(cp['late_dp_power']['p50'])} | {fmt(cp['margin']['p50'])} |"
            )
    lines += ["", "## Stops and deaths", ""]
    for label, item in payload["profiles"].items():
        lines += [
            f"- {label} first stops: `{json.dumps(item['first_stop_wave'])}`",
            f"- {label} W4500+ deaths: `{json.dumps(item['death_wave_4500_plus'])}`",
        ]
    lines += ["", "## Boost purchases", "", "| Profile | Base | Weapon | AS | Crit Mult | All Damage | Boss Damage | Weapon Pt | Relic Dust |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for label, item in payload["profiles"].items():
        levels = item["boost_levels"]
        lines.append(
            f"| {label} | " + " | ".join(
                fmt(levels[key]["p50"], 0) for key in sim.UNLIMITED_BOOST_NODES
            ) + f" | {fmt(item['weapon_spent']['p50'],0)} | {fmt(item['relic_spent']['p50'],0)} |"
        )
    lines += ["", "## Infinite Barrage split", "", "| Profile | Group | N | W5000 |", "|---|---|---:|---:|"]
    for label, item in payload["profiles"].items():
        for key, name in (("barrage_acquired", "acquired"), ("barrage_not_acquired", "not acquired")):
            group = item[key]
            if group["samples"]:
                lines.append(f"| {label} | {name} | {group['samples']} | {group['success_rate']:.0%} |")
    lines += [
        "", "## Validation", "",
        f"- paired states: {payload['state_count']}",
        "- Finale is an additive enemy-Power config layer; the base enemy curve is unchanged.",
        f"- errors/nonfinite/overflow: {payload['error_count']}/{payload['nonfinite_count']}/{payload['overflow_count']}",
        "- No formal adoption or extra coefficient candidate.", "",
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
        default=Path("output/w5000_v1_finale_10_states"),
    )
    args = parser.parse_args()
    with gzip.open(args.states, "rb") as handle:
        captures = pickle.load(handle)
    if len(captures) != 10:
        raise ValueError(f"expected 10 W2500 states, found {len(captures)}")

    grouped = {label: [] for label in PROFILES}
    errors = []
    for label, (finale, boost) in PROFILES.items():
        for capture in captures.values():
            try:
                row = integrated.replay_one(
                    capture, label, DP_SCALE, CORE_SCALE,
                    unlimited_boost_config=boost,
                    finale_config=finale,
                    diagnostic_checkpoints=CHECKPOINTS,
                )
                augment_threshold(row, 4000)
                augment_threshold(row, 4500)
                grouped[label].append(row)
            except Exception as exc:
                errors.append({
                    "profile": label, "trial": capture["trial"],
                    "type": type(exc).__name__, "message": str(exc),
                })
    profiles = {label: summarize(rows) for label, rows in grouped.items()}
    nonfinite = sum(len(row["nonfinite"]) for rows in grouped.values() for row in rows)
    payload = {
        "state_count": len(captures), "trial_ids": sorted(captures),
        "profiles": profiles, "error_count": len(errors),
        "nonfinite_count": nonfinite,
        "overflow_count": sum(error["type"] == "OverflowError" for error in errors),
        "errors": errors, "formal_changed": False, "balance_adopted": False,
    }
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = output / "finale_report.md"
    summary = output / "finale_summary.json"
    report.write_text(markdown(payload), encoding="utf-8")
    summary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "report": str(report), "json": str(summary), "states": len(captures),
        "errors": len(errors), "nonfinite": nonfinite,
        "overflow": payload["overflow_count"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
