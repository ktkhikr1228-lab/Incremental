#!/usr/bin/env python3
"""Paired flat-versus-tapered Core shape comparison."""

from __future__ import annotations

import argparse
import gzip
import json
import pickle
from pathlib import Path

import experiment_w5000_v1_integrated_core_dp as integrated


DP_SCALE = 0.10
PROFILES = {
    "A_flat_10": {"flat": 0.10, "stages": None},
    "B_flat_15": {"flat": 0.15, "stages": None},
    "C_tapered_15_12_5_10": {"flat": 0.0, "stages": (0.15, 0.125, 0.10)},
}
CHECKPOINTS = (3000, 3500, 4000, 4500, 5000)


def fmt(value, digits=2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def subgroup(rows: list[dict], acquired: bool) -> dict:
    return integrated.summarize_rows(
        [row for row in rows if row["infinite_barrage_acquired"] is acquired],
        include_rows=False,
    )


def markdown(payload: dict) -> str:
    lines = [
        "# w5000_v1 Core shape comparison", "",
        "Diagnostic only. Boss Devourer base-heavy B, Infinite Barrage 37.5%, late DP 10%, W2500 guaranteed Legendary OFF.", "",
        "| Profile | First-run Max P25/P50/P75 | First-run W5000 | W3000 | W3500 | W4000 | W4500 | W5000 | Add Runs P25/P50/P75 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, item in payload["profiles"].items():
        first = item["first_run_max_wave"]
        runs = item["additional_runs_to_w5000"]
        lines.append(
            f"| {label} | {fmt(first['p25'],0)}/{fmt(first['p50'],0)}/{fmt(first['p75'],0)}"
            f" | {item['first_run_w5000_rate']:.0%} | "
            + " | ".join(f"{item['checkpoints'][str(w)]['reach_rate']:.0%}" for w in CHECKPOINTS)
            + f" | {fmt(runs['p25'],1)}/{fmt(runs['p50'],1)}/{fmt(runs['p75'],1)} |"
        )
    lines += [
        "", "## Core progression and checkpoint state", "",
        "| Profile | W | Exponent | First-run Core ΔPower P50 | Long-run Core ΔPower P50 | First-run Margin P50 | Long-run Margin P50 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label, item in payload["profiles"].items():
        for wave in CHECKPOINTS:
            first = item["first_run_checkpoints"][str(wave)]
            long = item["checkpoints"][str(wave)]
            lines.append(
                f"| {label} | {wave} | {fmt(item['configured_core_exponent'][str(wave)],3)}"
                f" | {fmt(first['core_power']['p50'])} | {fmt(long['core_power']['p50'])}"
                f" | {fmt(first['margin']['p50'])} | {fmt(long['margin']['p50'])} |"
            )
    lines += [
        "", "## Long-run detail", "",
        "| Profile | Best P25/P50/P75 | Hours P50 | Terminal Margin P50 | Success Margin P50 | Best-recent10 P50 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, item in payload["profiles"].items():
        best = item["best_wave"]
        lines.append(
            f"| {label} | {fmt(best['p25'],0)}/{fmt(best['p50'],0)}/{fmt(best['p75'],0)}"
            f" | {fmt(item['game_hours_to_w5000']['p50'],3)}"
            f" | {fmt(item['terminal_margin']['p50'])} | {fmt(item['w5000_margin']['p50'])}"
            f" | {fmt(item['best_minus_recent10_median']['p50'],0)} |"
        )
    lines += [
        "", "## Infinite Barrage interaction", "",
        "| Profile | Group | N | W5000 | Best P50 |",
        "|---|---|---:|---:|---:|",
    ]
    for label, item in payload["profiles"].items():
        for key, name in (("barrage_acquired", "acquired"), ("barrage_not_acquired", "not acquired")):
            group = item[key]
            if group["samples"]:
                lines.append(
                    f"| {label} | {name} | {group['samples']} | {group['success_rate']:.0%}"
                    f" | {fmt(group['best_wave']['p50'],0)} |"
                )
    lines += [
        "", "## Validation", "",
        f"- Paired W2500 states: {payload['state_count']}",
        "- Existing weak increments and Big Boss timing are unchanged; only their stage scale differs.",
        f"- errors/nonfinite/overflow: {payload['error_count']}/{payload['nonfinite_count']}/{payload['overflow_count']}",
        "- No formal adoption or additional coefficient profile.", "",
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
        default=Path("output/w5000_v1_core_shape_10_states"),
    )
    args = parser.parse_args()
    with gzip.open(args.states, "rb") as handle:
        captures = pickle.load(handle)
    if len(captures) != 10:
        raise ValueError(f"expected 10 W2500 states, found {len(captures)}")

    grouped = {label: [] for label in PROFILES}
    errors = []
    for label, definition in PROFILES.items():
        for capture in captures.values():
            try:
                grouped[label].append(integrated.replay_one(
                    capture,
                    label,
                    DP_SCALE,
                    definition["flat"],
                    definition["stages"],
                ))
            except Exception as exc:
                errors.append({
                    "profile": label, "trial": capture["trial"],
                    "type": type(exc).__name__, "message": str(exc),
                })

    first_capture = next(iter(captures.values()))
    profiles = {}
    for label, rows in grouped.items():
        definition = PROFILES[label]
        item = integrated.summarize_rows(rows)
        item["barrage_acquired"] = subgroup(rows, True)
        item["barrage_not_acquired"] = subgroup(rows, False)
        config = integrated.make_config(
            first_capture, DP_SCALE, definition["flat"], definition["stages"]
        )
        item["configured_core_exponent"] = {
            str(wave): integrated.core.exponent_at(config, wave, True)
            for wave in CHECKPOINTS
        }
        profiles[label] = item

    nonfinite = sum(len(row["nonfinite"]) for rows in grouped.values() for row in rows)
    payload = {
        "state_count": len(captures), "trial_ids": sorted(captures),
        "profiles_definition": PROFILES, "late_dp_scale": DP_SCALE,
        "infinite_barrage_strength": integrated.BARRAGE_STRENGTH,
        "profiles": profiles, "error_count": len(errors),
        "nonfinite_count": nonfinite,
        "overflow_count": sum(error["type"] == "OverflowError" for error in errors),
        "errors": errors, "formal_changed": False, "balance_adopted": False,
    }
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = output / "core_shape_report.md"
    summary = output / "core_shape_summary.json"
    report.write_text(markdown(payload), encoding="utf-8")
    summary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "report": str(report), "json": str(summary), "states": len(captures),
        "errors": len(errors), "nonfinite": nonfinite,
        "overflow": payload["overflow_count"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
