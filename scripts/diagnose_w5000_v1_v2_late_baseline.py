#!/usr/bin/env python3
"""Paired late-game baseline diagnosis with Infinite Barrage v2 fixed ratio."""

from __future__ import annotations

import argparse
import collections
import gzip
import json
import pickle
from pathlib import Path

import diagnose_w5000_v1_precore as diag
import experiment_w5000_v1_integrated_core_dp as integrated
import experiment_w5000_v1_unlimited_boost_v02 as boost_v02
import simulate_first_prestige_v1 as sim


DP_SCALE = 0.10
CORE_SCALE = 0.15
CHECKPOINTS = (4000, 4250, 4500, 4600, 4700, 4800, 4900, 5000)
PROFILES = {
    "A_finale_off_boost_off": (
        sim.FinaleConfig(enabled=False), sim.UnlimitedBoostConfig(enabled=False),
    ),
    "B_finale_on_boost_off": (
        sim.FinaleConfig(enabled=True), sim.UnlimitedBoostConfig(enabled=False),
    ),
    "C_finale_off_boost_v02": (
        sim.FinaleConfig(enabled=False), boost_v02.v02_config(),
    ),
    "D_finale_on_boost_v02": (
        sim.FinaleConfig(enabled=True), boost_v02.v02_config(),
    ),
}


def fmt(value, digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def augment(row: dict) -> None:
    first_w4000 = next(
        (index for index, run in enumerate(row["run_rows"]) if run["max_wave"] >= 4000),
        None,
    )
    success_run = next(
        (index for index, run in enumerate(row["run_rows"]) if run["max_wave"] >= 5000),
        None,
    )
    row["w4000_to_w5000_runs"] = (
        None
        if first_w4000 is None or success_run is None
        else success_run - first_w4000
    )
    acquisition = next(
        (
            (run["run_index"], run["infinite_barrage_first_wave"])
            for run in row["run_rows"]
            if run["infinite_barrage_first_wave"] is not None
        ),
        None,
    )
    row["first_barrage_acquisition"] = acquisition


def subgroup(rows: list[dict], acquired: bool) -> dict:
    selected = [row for row in rows if row["infinite_barrage_acquired"] is acquired]
    return {
        "samples": len(selected),
        "successes": sum(row["success"] for row in selected),
        "success_rate": (
            sum(row["success"] for row in selected) / len(selected) if selected else None
        ),
    }


def death_band(wave: int) -> str:
    low = (wave // 250) * 250
    return f"{low}-{low + 249}"


def summarize(rows: list[dict]) -> dict:
    successes = [row for row in rows if row["success"]]
    death_waves = [
        int(run["failure_wave"])
        for row in rows
        for run in row["run_rows"]
        if run["failure_wave"] is not None
    ]
    result = {
        "samples": len(rows),
        "successes": len(successes),
        "checkpoints": {},
        "death_wave_exact": dict(sorted(collections.Counter(
            str(wave) for wave in death_waves
        ).items(), key=lambda item: int(item[0]))),
        "death_wave_bands": dict(sorted(collections.Counter(
            death_band(wave) for wave in death_waves
        ).items(), key=lambda item: int(item[0].split("-")[0]))),
        "w4000_to_w5000_runs": diag.dist([
            row["w4000_to_w5000_runs"]
            for row in successes if row["w4000_to_w5000_runs"] is not None
        ]),
        "w5000_margin": diag.dist([
            row["w5000_margin"] for row in successes if row["w5000_margin"] is not None
        ]),
        "barrage_acquired": subgroup(rows, True),
        "barrage_not_acquired": subgroup(rows, False),
        "rows": rows,
    }
    for wave in CHECKPOINTS:
        states = [
            row["checkpoints"][str(wave)]
            for row in rows if str(wave) in row["checkpoints"]
        ]
        result["checkpoints"][str(wave)] = {
            "reached": len(states),
            "reach_rate": len(states) / len(rows),
            "margin": diag.dist([float(state["margin_power"]) for state in states]),
            "core_power": diag.dist([
                float(state.get("core_power", 0.0)) for state in states
            ]),
            "late_dp_power": diag.dist([
                float(state.get("late_dp_power", 0.0)) for state in states
            ]),
            "boost_power": diag.dist([
                float(state.get("boost_power", 0.0)) for state in states
            ]),
            "barrage_power": diag.dist([
                float(state.get("barrage_power", 0.0)) for state in states
            ]),
            "finale_added_power": diag.dist([
                float(state.get("finale_added_power", 0.0)) for state in states
            ]),
        }
    return result


def markdown(payload: dict) -> str:
    lines = [
        "# w5000_v1 v2 Barrage late baseline diagnosis",
        "",
        "Infinite Barrage v2 fixed ratio; Core flat15%, late DP10%, Boss Devourer base-heavy B, W2500 guaranteed Legendary OFF.",
        "",
        "## Reach",
        "",
        "| Profile | W4000 | W4250 | W4500 | W4600 | W4700 | W4800 | W4900 | W5000 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, item in payload["profiles"].items():
        lines.append(
            f"| {label} | " + " | ".join(
                f"{item['checkpoints'][str(wave)]['reach_rate']:.0%}"
                for wave in CHECKPOINTS
            ) + " |"
        )
    lines += [
        "",
        "## W4000 to W5000 and Barrage split",
        "",
        "| Profile | Runs P25/P50/P75 | W5000 Margin P50 | Barrage acquired | Barrage not acquired |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, item in payload["profiles"].items():
        runs = item["w4000_to_w5000_runs"]
        acquired = item["barrage_acquired"]
        not_acquired = item["barrage_not_acquired"]
        lines.append(
            f"| {label} | {fmt(runs['p25'],1)}/{fmt(runs['p50'],1)}/{fmt(runs['p75'],1)}"
            f" | {fmt(item['w5000_margin']['p50'])}"
            f" | {acquired['successes']}/{acquired['samples']}"
            f" | {not_acquired['successes']}/{not_acquired['samples']} |"
        )
    lines += [
        "",
        "## Checkpoint margins and direct contributions",
        "",
        "| Profile | W | Margin P25/P50/P75 | Core P50 | late DP P50 | Boost P50 | Barrage P50 | Finale enemy Power |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, item in payload["profiles"].items():
        for wave in CHECKPOINTS:
            cp = item["checkpoints"][str(wave)]
            margin = cp["margin"]
            lines.append(
                f"| {label} | {wave}"
                f" | {fmt(margin['p25'])}/{fmt(margin['p50'])}/{fmt(margin['p75'])}"
                f" | {fmt(cp['core_power']['p50'])}"
                f" | {fmt(cp['late_dp_power']['p50'])}"
                f" | {fmt(cp['boost_power']['p50'])}"
                f" | {fmt(cp['barrage_power']['p50'],3)}"
                f" | {fmt(cp['finale_added_power']['p50'])} |"
            )
    lines += ["", "## Death Wave distribution (250-Wave bands)", ""]
    for label, item in payload["profiles"].items():
        lines.append(f"- {label}: `{json.dumps(item['death_wave_bands'])}`")
    lines += [
        "",
        "## Validation",
        "",
        f"- paired W2500 states: {payload['state_count']}",
        f"- first Barrage acquisition signatures identical: {payload['first_acquisition_signatures_identical']}",
        "- The W2500 start states/RNG are paired; post-effect trajectory and later acquisition signatures may diverge causally.",
        f"- errors/nonfinite/overflow: {payload['error_count']}/{payload['nonfinite_count']}/{payload['overflow_count']}",
        "- Barrage/Finale/Core/DP/Boost values were not changed.",
        "- No formal adoption.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--states",
        type=Path,
        default=Path("output/w5000_v1_micro_core_10_states_final/w2500_checkpoint_states.pkl.gz"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/w5000_v1_v2_late_baseline_10_states"),
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
                    capture,
                    label,
                    DP_SCALE,
                    CORE_SCALE,
                    unlimited_boost_config=boost,
                    finale_config=finale,
                    diagnostic_checkpoints=CHECKPOINTS,
                    barrage_mode="v2_fixed_ratio",
                )
                augment(row)
                grouped[label].append(row)
            except Exception as exc:
                errors.append({
                    "profile": label,
                    "trial": capture["trial"],
                    "type": type(exc).__name__,
                    "message": str(exc),
                })

    profiles = {label: summarize(rows) for label, rows in grouped.items()}
    signatures = {
        label: {row["trial"]: row["first_barrage_acquisition"] for row in rows}
        for label, rows in grouped.items()
    }
    reference = signatures["A_finale_off_boost_off"]
    mismatches = [
        {
            "profile": label,
            "trial": trial,
            "expected": reference[trial],
            "actual": signature,
        }
        for label, values in signatures.items()
        for trial, signature in values.items()
        if signature != reference[trial]
    ]
    nonfinite = sum(len(row["nonfinite"]) for rows in grouped.values() for row in rows)
    payload = {
        "state_count": len(captures),
        "trial_ids": sorted(captures),
        "profiles": profiles,
        "first_acquisition_signatures_identical": not mismatches,
        "first_acquisition_signature_mismatches": mismatches,
        "error_count": len(errors),
        "nonfinite_count": nonfinite,
        "overflow_count": sum(item["type"] == "OverflowError" for item in errors),
        "errors": errors,
        "formal_changed": False,
        "balance_adopted": False,
    }
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "v2_late_baseline_summary.json"
    report_path = output / "v2_late_baseline_report.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(markdown(payload), encoding="utf-8")
    print(json.dumps({
        "report": str(report_path),
        "json": str(json_path),
        "states": len(captures),
        "errors": len(errors),
        "nonfinite": nonfinite,
        "overflow": payload["overflow_count"],
        "first_acquisition_signatures_identical": not mismatches,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
