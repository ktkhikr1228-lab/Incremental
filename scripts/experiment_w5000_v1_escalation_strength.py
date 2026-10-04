#!/usr/bin/env python3
"""Matched Escalation growth-strength experiment for the new W5000 candidate."""

from __future__ import annotations

import argparse
import collections
import csv
import dataclasses
import json
import math
import statistics
from pathlib import Path

import diagnose_w5000_v1_midgame_card_effects as source
import diagnose_w5000_v1_precore as diag
import simulate_first_prestige_v1 as sim


CHECKPOINTS = source.CHECKPOINTS
CONDITIONS = {
    "A_current_100": 1.00,
    "B_growth_65": 0.65,
    "C_growth_50": 0.50,
}


def distribution(values):
    finite = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return diag.dist(finite) if finite else {
        "count": 0, "p25": None, "p50": None, "p75": None, "min": None, "max": None,
    }


def snapshot_rows(config, captures, success_ids):
    rows = []
    for capture in captures.values():
        wave = capture["wave"]
        if wave not in CHECKPOINTS:
            continue
        run, permanent = capture["run"], capture["permanent"]
        for condition, scale in CONDITIONS.items():
            active = dataclasses.replace(config, diagnostic_escalation_growth_scale=scale)
            snap = sim.compute_snapshot(run, permanent, wave % 10 == 0, active)
            off = dataclasses.replace(active, diagnostic_suppressed_card_keys=frozenset({"escalation"}))
            off_snap = sim.compute_snapshot(run, permanent, wave % 10 == 0, off)
            enemy = sim.configured_enemy_power(wave, active)
            limit = 15.0 if wave % 10 == 0 else 10.0
            kill_time = sim.time_to_kill(enemy, limit, snap)
            rows.append({
                "trial": capture["trial"], "attempt": capture["attempt"], "wave": wave,
                "group": "success10" if capture["trial"] in success_ids else "failure20",
                "condition": condition, "scale": scale, "player_power": snap.log_dps,
                "enemy_power": enemy, "margin": snap.log_dps - enemy,
                "killable": kill_time is not None, "kill_time": kill_time,
                "escalation_stack": float(run.counts.get("escalation", 0)),
                "escalation_power": snap.log_dps - off_snap.log_dps,
            })
    return rows


def trial_outcomes(rows, results):
    lookup = collections.defaultdict(dict)
    for row in rows:
        lookup[(row["trial"], row["attempt"], row["condition"])][row["wave"]] = row
    output = []
    for trial, result in results.items():
        for condition in CONDITIONS:
            highs, growth, margins_1500 = [], [], []
            reached = {wave: False for wave in CHECKPOINTS}
            for attempt, actual_high in enumerate(result.run_reaches, start=1):
                states = lookup.get((trial, attempt, condition), {})
                high = int(actual_high)
                if 1250 in states:
                    reached[1250] = True
                    for wave in CHECKPOINTS[1:]:
                        state = states.get(wave)
                        if state is None:
                            continue
                        if not state["killable"]:
                            high = min(high, wave - 1)
                            break
                        reached[wave] = True
                    if 1500 in states and states[1500]["killable"]:
                        growth.append(states[1500]["player_power"] - states[1250]["player_power"])
                        margins_1500.append(states[1500]["margin"])
                highs.append(high)
            first_1500 = next((index for index, high in enumerate(highs) if high >= 1500), None)
            later = highs[first_1500 + 1:] if first_1500 is not None else []
            reattainment = (
                sum(high >= 1500 for high in later) / len(later) if later else None
            )
            recent = highs[-10:]
            output.append({
                "trial": trial, "group": "success10" if result.success else "failure20",
                "condition": condition, "highest_wave": max(highs) if highs else 0,
                "reached": reached,
                "growth_1250_1500": statistics.median(growth) if growth else None,
                "margin_1500": statistics.median(margins_1500) if margins_1500 else None,
                "reattainment_1500": reattainment,
                "best_minus_recent10": (
                    max(highs) - statistics.median(recent) if recent else None
                ),
            })
    return output


def first_w1500_stack(rows):
    current = [row for row in rows if row["condition"] == "A_current_100" and row["wave"] == 1500]
    by_trial = {}
    for row in sorted(current, key=lambda item: (item["trial"], item["attempt"])):
        if row["killable"] and row["trial"] not in by_trial:
            by_trial[row["trial"]] = row["escalation_stack"]
    return by_trial


def stack_band(stack):
    if stack <= 1:
        return "low_0_1"
    if stack < 3:
        return "mid_2"
    return "high_3_plus"


def summarize(rows, trials):
    result = {}
    stack_by_trial = first_w1500_stack(rows)
    for condition in CONDITIONS:
        selected = [item for item in trials if item["condition"] == condition]
        result[condition] = {
            "scale": CONDITIONS[condition],
            "reach_rate": {
                str(wave): sum(item["reached"][wave] for item in selected) / len(selected)
                for wave in CHECKPOINTS
            },
            "growth_1250_1500": distribution(item["growth_1250_1500"] for item in selected),
            "margin_w1500": distribution(item["margin_1500"] for item in selected),
            "highest_wave": distribution(item["highest_wave"] for item in selected),
            "w1500_reattainment": distribution(item["reattainment_1500"] for item in selected),
            "best_minus_recent10": distribution(item["best_minus_recent10"] for item in selected),
            "stack_bands": {},
        }
        for band in ("low_0_1", "mid_2", "high_3_plus"):
            ids = {trial for trial, stack in stack_by_trial.items() if stack_band(stack) == band}
            band_trials = [item for item in selected if item["trial"] in ids]
            band_rows = [
                row for row in rows
                if row["condition"] == condition and row["wave"] == 1500 and row["trial"] in ids
            ]
            result[condition]["stack_bands"][band] = {
                "trials": len(band_trials),
                "stack": distribution(stack_by_trial[trial] for trial in ids),
                "escalation_power_w1500": distribution(row["escalation_power"] for row in band_rows),
                "highest_wave": distribution(item["highest_wave"] for item in band_trials),
                "reach_w2500": (
                    sum(item["reached"][2500] for item in band_trials) / len(band_trials)
                    if band_trials else None
                ),
            }
    return result


def fmt(value, digits=2):
    return "—" if value is None else f"{value:.{digits}f}"


def trip(item):
    return f"{fmt(item['p25'])}/{fmt(item['p50'])}/{fmt(item['p75'])}"


def markdown(payload):
    lines = [
        "# Escalation growth-strength matched experiment", "",
        f"{payload['trials']} trials / seed {payload['seed']} / checkpoint-state replay", "",
        "取得Wave・stack・カード履歴・RNGは共通。EscalationのWave依存成長部分だけを100%/65%/50%へ変更した。到達率は保存済み250Wave checkpoint grid上の診断値。", "",
        "| Condition | W1250 | W1500 | W1750 | W2000 | W2250 | W2500 | W1250→1500 Power P25/P50/P75 | W1500 Margin P25/P50/P75 | Highest P25/P50/P75 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for condition, item in payload["summary"].items():
        reach = item["reach_rate"]
        lines.append(
            f"| {condition} | {reach['1250']:.0%} | {reach['1500']:.0%} | {reach['1750']:.0%} | "
            f"{reach['2000']:.0%} | {reach['2250']:.0%} | {reach['2500']:.0%} | "
            f"{trip(item['growth_1250_1500'])} | {trip(item['margin_w1500'])} | {trip(item['highest_wave'])} |"
        )
    lines += ["", "## Run reproducibility", "", "| Condition | W1500再到達率 P25/P50/P75 | Best - recent10 median P25/P50/P75 |", "|---|---:|---:|"]
    for condition, item in payload["summary"].items():
        lines.append(f"| {condition} | {trip(item['w1500_reattainment'])} | {trip(item['best_minus_recent10'])} |")
    lines += ["", "## Escalation stack bands at first reachable W1500", "", "Low=0-1、Mid=2、High=3枚以上（100%条件の最初のW1500状態で固定分類）。", "", "| Condition | Band | Trials | Stack P50 | Escalation Power at W1500 P50 | Highest P50 | W2500 |", "|---|---|---:|---:|---:|---:|---:|"]
    for condition, item in payload["summary"].items():
        for band, band_item in item["stack_bands"].items():
            rate = band_item["reach_w2500"]
            lines.append(
                f"| {condition} | {band} | {band_item['trials']} | {fmt(band_item['stack']['p50'])} | "
                f"{fmt(band_item['escalation_power_w1500']['p50'])} | {fmt(band_item['highest_wave']['p50'], 0)} | "
                f"{'—' if rate is None else f'{rate:.0%}'} |"
            )
    lines += ["", "## Safety", "", f"- errors: {len(payload['errors'])}", f"- nonfinite rows: {payload['nonfinite_rows']}", "- Formal/default Escalation remains 100%; this experiment does not adopt a value."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20260828)
    parser.add_argument("--output-dir", default="output/w5000_v1_escalation_strength_30_final")
    args = parser.parse_args()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    config, captures, results, success_ids, errors = source.collect(args.trials, args.seed)
    rows = snapshot_rows(config, captures, success_ids)
    trial_rows = trial_outcomes(rows, results)
    nonfinite = sum(
        not all(math.isfinite(float(row[key])) for key in ("player_power", "enemy_power", "margin", "escalation_power"))
        for row in rows
    )
    payload = {
        "seed": args.seed, "trials": args.trials,
        "baseline_success_count": len(success_ids), "conditions": CONDITIONS,
        "summary": summarize(rows, trial_rows), "errors": errors,
        "nonfinite_rows": nonfinite,
    }
    (out / "escalation_strength.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "escalation_strength.md").write_text(markdown(payload), encoding="utf-8")
    with (out / "escalation_strength_trials.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "trial", "group", "condition", "highest_wave", "growth_1250_1500",
            "margin_1500", "reattainment_1500", "best_minus_recent10",
        ] + [f"reach_{wave}" for wave in CHECKPOINTS])
        writer.writeheader()
        for item in trial_rows:
            writer.writerow({
                **{key: item[key] for key in writer.fieldnames if not key.startswith("reach_")},
                **{f"reach_{wave}": item["reached"][wave] for wave in CHECKPOINTS},
            })
    print(markdown(payload))


if __name__ == "__main__":
    main()
