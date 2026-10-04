#!/usr/bin/env python3
"""Paired Core scale bracket with late DP fixed at diagnostic 10%."""

from __future__ import annotations

import argparse
import gzip
import json
import pickle
from pathlib import Path

import experiment_w5000_v1_integrated_core_dp as integrated


DP_SCALE = 0.10
CORE_PROFILES = {
    "A_core_off": 0.00,
    "B_core_10": 0.10,
    "C_core_15": 0.15,
    "D_core_20": 0.20,
}
DISPLAY_CHECKPOINTS = (2750, 3000, 3500, 4000, 4500, 5000)


def fmt(value, digits=2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def subgroup(rows: list[dict], acquired: bool) -> dict:
    return integrated.summarize_rows(
        [row for row in rows if row["infinite_barrage_acquired"] is acquired],
        include_rows=False,
    )


def markdown(payload: dict) -> str:
    lines = [
        "# w5000_v1 Core re-bracket (late DP 10%)", "",
        "Diagnostic only. Boss Devourer base-heavy B, Infinite Barrage 37.5%, late DP 10%, W2500 guaranteed Legendary OFF.", "",
        "## First run", "",
        "| Profile | Max Wave P25/P50/P75 | W2750 | W3000 | W3500 | W4000 | W4500 | W5000 | Same-run W5000 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, item in payload["profiles"].items():
        best = item["first_run_max_wave"]
        lines.append(
            f"| {label} | {fmt(best['p25'],0)}/{fmt(best['p50'],0)}/{fmt(best['p75'],0)} | "
            + " | ".join(
                f"{item['first_run_checkpoints'][str(w)]['reach_rate']:.0%}"
                for w in DISPLAY_CHECKPOINTS
            )
            + f" | {item['first_run_w5000_rate']:.0%} |"
        )
    lines += ["", "### First-run Core exponent / direct Power", ""]
    for label, item in payload["profiles"].items():
        lines += [
            f"#### {label}", "",
            "| W | Core exponent P50 | Core direct ΔPower P50 | Margin P50 |",
            "|---:|---:|---:|---:|",
        ]
        for wave in DISPLAY_CHECKPOINTS:
            cp = item["first_run_checkpoints"][str(wave)]
            lines.append(
                f"| {wave} | {fmt(cp['core_exponent']['p50'],3)}"
                f" | {fmt(cp['core_power']['p50'])} | {fmt(cp['margin']['p50'])} |"
            )
        lines.append("")

    lines += [
        "### Configured exponent progression", "",
        "This table shows the configured exponent even when no first run reached that checkpoint.", "",
        "| Profile | W2750 | W3000 | W3500 | W4000 | W4500 | W5000 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label, item in payload["profiles"].items():
        lines.append(
            f"| {label} | " + " | ".join(
                fmt(item["configured_core_exponent"][str(w)], 3)
                for w in DISPLAY_CHECKPOINTS
            ) + " |"
        )

    lines += [
        "## Long run", "",
        "| Profile | W2750 | W3000 | W3500 | W4000 | W4500 | W5000 | Add Runs P25/P50/P75 | Hours P50 | Best P25/P50/P75 | Terminal Margin P50 | Success Margin P50 | Best-recent10 P50 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, item in payload["profiles"].items():
        runs = item["additional_runs_to_w5000"]
        best = item["best_wave"]
        lines.append(
            f"| {label} | "
            + " | ".join(
                f"{item['checkpoints'][str(w)]['reach_rate']:.0%}"
                for w in DISPLAY_CHECKPOINTS
            )
            + f" | {fmt(runs['p25'],1)}/{fmt(runs['p50'],1)}/{fmt(runs['p75'],1)}"
            f" | {fmt(item['game_hours_to_w5000']['p50'],3)}"
            f" | {fmt(best['p25'],0)}/{fmt(best['p50'],0)}/{fmt(best['p75'],0)}"
            f" | {fmt(item['terminal_margin']['p50'])} | {fmt(item['w5000_margin']['p50'])}"
            f" | {fmt(item['best_minus_recent10_median']['p50'],0)} |"
        )

    lines += [
        "", "## Infinite Barrage interaction", "",
        "| Profile | Group | N | W5000 | Best Wave P50 | Success Margin P50 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for label, item in payload["profiles"].items():
        for key, name in (("barrage_acquired", "acquired"), ("barrage_not_acquired", "not acquired")):
            group = item[key]
            if not group["samples"]:
                continue
            lines.append(
                f"| {label} | {name} | {group['samples']} | {group['success_rate']:.0%}"
                f" | {fmt(group['best_wave']['p50'],0)} | {fmt(group['w5000_margin']['p50'])} |"
            )
    lines += [
        "", "## Validation", "",
        f"- Paired W2500 states: {payload['state_count']}",
        "- Same saved state/RNG per trial; only Core weak-increment scale differs.",
        "- late DP is fixed at 10% in all profiles.",
        f"- errors/nonfinite/overflow: {payload['error_count']}/{payload['nonfinite_count']}/{payload['overflow_count']}",
        "- No formal adoption, extra coefficient, or trial expansion.", "",
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
        default=Path("output/w5000_v1_core_rebracket_10_states"),
    )
    args = parser.parse_args()
    with gzip.open(args.states, "rb") as handle:
        captures = pickle.load(handle)
    if len(captures) != 10:
        raise ValueError(f"expected 10 W2500 states, found {len(captures)}")

    grouped = {label: [] for label in CORE_PROFILES}
    errors = []
    for label, core_scale in CORE_PROFILES.items():
        for capture in captures.values():
            try:
                grouped[label].append(
                    integrated.replay_one(capture, label, DP_SCALE, core_scale)
                )
            except Exception as exc:
                errors.append({
                    "profile": label,
                    "trial": capture["trial"],
                    "type": type(exc).__name__,
                    "message": str(exc),
                })

    profiles = {}
    first_capture = next(iter(captures.values()))
    for label, rows in grouped.items():
        summary = integrated.summarize_rows(rows)
        summary["barrage_acquired"] = subgroup(rows, True)
        summary["barrage_not_acquired"] = subgroup(rows, False)
        config = integrated.make_config(
            first_capture, DP_SCALE, CORE_PROFILES[label]
        )
        summary["configured_core_exponent"] = {
            str(wave): integrated.core.exponent_at(
                config, wave, bool(CORE_PROFILES[label])
            )
            for wave in DISPLAY_CHECKPOINTS
        }
        profiles[label] = summary
    nonfinite = sum(len(row["nonfinite"]) for rows in grouped.values() for row in rows)
    payload = {
        "state_count": len(captures),
        "trial_ids": sorted(captures),
        "late_dp_scale": DP_SCALE,
        "core_profiles": CORE_PROFILES,
        "infinite_barrage_strength": integrated.BARRAGE_STRENGTH,
        "profiles": profiles,
        "error_count": len(errors),
        "nonfinite_count": nonfinite,
        "overflow_count": sum(error["type"] == "OverflowError" for error in errors),
        "errors": errors,
        "formal_changed": False,
        "balance_adopted": False,
    }
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = output / "core_rebracket_report.md"
    summary = output / "core_rebracket_summary.json"
    report.write_text(markdown(payload), encoding="utf-8")
    summary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "report": str(report), "json": str(summary), "states": len(captures),
        "errors": len(errors), "nonfinite": nonfinite,
        "overflow": payload["overflow_count"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
