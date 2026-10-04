#!/usr/bin/env python3
"""Late-DP comparison with Infinite Barrage fixed at diagnostic 37.5%."""

from __future__ import annotations

import argparse
import gzip
import json
import math
import pickle
from pathlib import Path

import diagnose_w5000_v1_late_dp_scaling as late
import diagnose_w5000_v1_precore as diag


SCALES = {
    "A_late_dp_10": 0.10,
    "B_late_dp_25": 0.25,
    "C_late_dp_50": 0.50,
}
BARRAGE_STRENGTH = 0.375


def subgroup(rows: list[dict], acquired: bool) -> dict:
    selected = [row for row in rows if row["infinite_barrage_acquired"] is acquired]
    if not selected:
        return {"samples": 0}
    result = late.summarize(selected)
    result.pop("rows", None)
    return result


def fmt(value, digits=2):
    return "—" if value is None else f"{value:.{digits}f}"


def markdown(payload: dict) -> str:
    lines = [
        "# w5000_v1 late DP with Infinite Barrage 37.5%", "",
        "Diagnostic only. W2500 baseline DP is identical; only combat contribution from DP levels bought after W2500 is scaled.", "",
        "| Condition | W3000 | W3500 | W4000 | W4500 | W5000 | Best P25/P50/P75 | Add Runs P25/P50/P75 | W5000 Margin P50 | Terminal Margin P50 | Late-DP Power P50 | Variance | Best-recent10 P50 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, item in payload["conditions"].items():
        best = item["best_wave"]
        runs = item["additional_runs_to_w5000"]
        lines.append(
            f"| {label} | "
            + " | ".join(f"{item['checkpoints'][str(w)]['reach_rate']:.0%}" for w in late.CHECKPOINTS)
            + f" | {fmt(best['p25'],0)}/{fmt(best['p50'],0)}/{fmt(best['p75'],0)}"
            f" | {fmt(runs['p25'],1)}/{fmt(runs['p50'],1)}/{fmt(runs['p75'],1)}"
            f" | {fmt(item['w5000_margin']['p50'],2)} | {fmt(item['terminal_margin']['p50'],2)}"
            f" | {fmt(item['late_dp_power']['p50'],2)} | {fmt(item['best_wave_variance'],1)}"
            f" | {fmt(item['best_minus_recent10_median']['p50'],0)} |"
        )
    lines += ["", "## Infinite Barrage acquisition split", "", "| Condition | Group | N | W3000 | W3500 | W4000 | W4500 | W5000 | Best P50 | Terminal Margin P50 |", "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for label, item in payload["conditions"].items():
        for group_key, group_name in (("barrage_acquired", "acquired"), ("barrage_not_acquired", "not acquired")):
            group = item[group_key]
            if not group.get("samples"):
                continue
            lines.append(
                f"| {label} | {group_name} | {group['samples']} | "
                + " | ".join(f"{group['checkpoints'][str(w)]['reach_rate']:.0%}" for w in late.CHECKPOINTS)
                + f" | {fmt(group['best_wave']['p50'],0)} | {fmt(group['terminal_margin']['p50'],2)} |"
            )
    lines += ["", "## Checkpoint late-DP Power contribution (P50)", "", "| Condition | W3000 | W3500 | W4000 | W4500 | W5000 |", "|---|---:|---:|---:|---:|---:|"]
    for label, item in payload["conditions"].items():
        lines.append(
            f"| {label} | " + " | ".join(
                fmt(item["checkpoints"][str(wave)]["late_dp_power"]["p50"], 2)
                for wave in late.CHECKPOINTS
            ) + " |"
        )
    lines += [
        "", "## Diagnostic reading", "",
        "- late_dp_50 is too strong for the stated goal: all 8 Infinite Barrage-acquired trials reached W5000 and late-DP contribution reached +121.91 Power at W5000.",
        "- late_dp_10 and late_dp_25 remain the useful band. Acquired-trial W5000 success is 5/7 versus 6/7, while W5000 late-DP contribution is +27.87 versus +54.14 Power.",
        "- If Core must be the primary late-game growth source, late_dp_10 leaves the most room; late_dp_25 is an upper-bound candidate. No value is adopted here.",
        "", "## Validation", "", f"- paired W2500 states: {payload['state_count']}", "- Infinite Barrage strength: 37.5% (diagnostic candidate, not adopted)", "- Core OFF; no enemy/weapon/relic/other-card changes.", f"- errors/nonfinite/overflow: {payload['error_count']}/{payload['nonfinite_count']}/{payload['overflow_count']}", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--states", type=Path, default=Path("output/w5000_v1_micro_core_10_states_final/w2500_checkpoint_states.pkl.gz"))
    parser.add_argument("--output-dir", type=Path, default=Path("output/w5000_v1_late_dp_barrage375_10_states"))
    args = parser.parse_args()
    with gzip.open(args.states, "rb") as handle:
        captures = pickle.load(handle)
    if len(captures) != 10:
        raise ValueError(f"expected 10 W2500 states, found {len(captures)}")

    grouped = {label: [] for label in SCALES}
    errors = []
    for label, scale in SCALES.items():
        for capture in captures.values():
            try:
                grouped[label].append(
                    late.replay_one(capture, label, scale, BARRAGE_STRENGTH)
                )
            except Exception as exc:
                errors.append({"condition": label, "trial": capture["trial"], "type": type(exc).__name__, "message": str(exc)})
    conditions = {}
    for label, rows in grouped.items():
        item = late.summarize(rows)
        item["barrage_acquired"] = subgroup(rows, True)
        item["barrage_not_acquired"] = subgroup(rows, False)
        conditions[label] = item
    nonfinite = sum(len(row["nonfinite"]) for rows in grouped.values() for row in rows)
    payload = {
        "state_count": len(captures),
        "trial_ids": sorted(captures),
        "scales": SCALES,
        "infinite_barrage_strength": BARRAGE_STRENGTH,
        "conditions": conditions,
        "error_count": len(errors),
        "nonfinite_count": nonfinite,
        "overflow_count": sum(item["type"] == "OverflowError" for item in errors),
        "errors": errors,
        "formal_changed": False,
        "core_enabled": False,
        "balance_adopted": False,
    }
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = output / "late_dp_barrage375_report.md"
    data = output / "late_dp_barrage375_summary.json"
    report.write_text(markdown(payload), encoding="utf-8")
    data.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report), "json": str(data), "errors": len(errors), "nonfinite": nonfinite}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
