#!/usr/bin/env python3
"""Paired Boss Devourer balance experiment for w5000_v1."""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import csv
import dataclasses
import json
import math
import random
import statistics
from pathlib import Path
from typing import Any

import diagnose_w5000_v1_precore as diag
import simulate_first_prestige_v1 as sim
import w5000_v1_profile as profile


CHECKPOINTS = (1250, 1500, 1750, 2000, 2250, 2500)
CONDITIONS = {
    "A_current_100": (1.00, ()),
    "B_growth_75": (0.75, ()),
    "C_growth_50": (0.50, ()),
    "D_growth_50_compensation": (0.50, ((1250, 4.0), (1500, 4.0), (1750, 4.0))),
}


def make_configs(max_attempts: int) -> dict[str, sim.SimConfig]:
    base = dataclasses.replace(
        profile.build_config(
            max_attempts=max_attempts, core_profile="no_core", guaranteed_legendary=False,
        ),
        diagnostic_checkpoints=CHECKPOINTS,
        dp_v01=sim.DPV01Config(enabled=True),
    )
    return {
        name: dataclasses.replace(
            base,
            diagnostic_boss_devourer_growth_multiplier=growth,
            diagnostic_fixed_wave_power_milestones=milestones,
        )
        for name, (growth, milestones) in CONDITIONS.items()
    }


def streams_for(seed: int, trial: int, card_only: bool) -> sim.RNGStreams:
    if not card_only:
        return sim.make_split_rng_streams(seed, trial)
    outer = sim.make_split_rng_streams(seed, 0)
    card = random.Random(sim.derived_rng_seed(seed, "balance-card-only", trial))
    return sim.RNGStreams(card, outer.weapon, outer.relic, outer.combat)


def execute(
    condition: str, config: sim.SimConfig, trials: int, seed: int, card_only: bool,
) -> tuple[list[tuple[int, sim.TrialResult]], list[dict[str, object]]]:
    completed: list[tuple[int, sim.TrialResult]] = []
    errors: list[dict[str, object]] = []
    for trial in range(trials):
        try:
            streams = streams_for(seed, trial, card_only)
            result = sim.run_trial(
                streams.combat, "balanced", config, True, rng_streams=streams
            )
            completed.append((trial, result))
        except Exception as exc:
            errors.append({
                "condition": condition, "trial": trial, "card_only": card_only,
                "type": type(exc).__name__, "message": str(exc),
            })
    return completed, errors


def execute_task(args: tuple[str, sim.SimConfig, int, int, bool]):
    name, config, trials, seed, card_only = args
    rows, errors = execute(name, config, trials, seed, card_only)
    return name, card_only, summarize(rows, errors, trials), errors


def recurrence(reaches: tuple[int, ...]) -> dict[str, float | int] | None:
    first = next((i for i, wave in enumerate(reaches) if wave >= 1500), None)
    if first is None:
        return None
    later = reaches[first + 1:]
    hits = sum(wave >= 1500 for wave in later)
    return {
        "later_runs": len(later), "later_reached_1500": hits,
        "rate": hits / len(later) if later else 0.0,
    }


def summarize(
    completed: list[tuple[int, sim.TrialResult]], errors: list[dict[str, object]], trials: int,
) -> dict[str, Any]:
    details = []
    recurrences = []
    dev_groups: dict[str, list[float]] = collections.defaultdict(list)
    all_units: list[float] = []
    nonfinite = []
    for trial, row in completed:
        reaches = row.run_reaches
        highest = max(reaches) if reaches else 0
        final = reaches[-1] if reaches else 0
        recent = statistics.median(reaches[-10:]) if reaches else 0.0
        rec = recurrence(reaches)
        if rec is not None:
            recurrences.append(rec)
        details.append({
            "trial": trial, "highest_wave": highest, "final_death_wave": final,
            "deaths": row.deaths, "best_minus_recent10_p50": highest - recent,
            "run_reaches": list(reaches),
        })
        for state in row.run_end_states:
            owned = bool(dict(state["cards"]).get("boss_devourer", 0))
            dev_groups["owned" if owned else "not_owned"].append(float(state["reached_wave"]))
            all_units.append(float(state.get("boss_devourer_units", 0)))
        for wave, state in row.first_reach_checkpoint_states.items():
            for key, value in state.items():
                if isinstance(value, float) and not math.isfinite(value):
                    nonfinite.append({"trial": trial, "wave": wave, "field": key, "value": value})
    later_runs = sum(int(item["later_runs"]) for item in recurrences)
    later_hits = sum(int(item["later_reached_1500"]) for item in recurrences)
    checkpoints = {}
    for wave in CHECKPOINTS:
        states = [
            row.first_reach_checkpoint_states[wave]
            for _, row in completed if wave in row.reach_seconds
        ]
        checkpoints[str(wave)] = {
            "reached": len(states), "reach_rate": len(states) / trials,
            "margin": diag.dist([float(state["margin_power"]) for state in states]),
            "boss_devourer_units": diag.dist([
                float(state["boss_devourer_units"]) for state in states
            ]),
        }
    highest_values = [float(item["highest_wave"]) for item in details]
    return {
        "completed": len(completed),
        "highest_wave_mean": statistics.fmean(highest_values) if highest_values else None,
        "highest_wave": diag.dist(highest_values),
        "highest_wave_variance": statistics.pvariance(highest_values) if len(highest_values) > 1 else 0.0,
        "final_death_wave": diag.dist([float(item["final_death_wave"]) for item in details]),
        "deaths": diag.dist([float(item["deaths"]) for item in details]),
        "best_minus_recent10_p50": diag.dist([
            float(item["best_minus_recent10_p50"]) for item in details
        ]),
        "w1500_rearrival": {
            "eligible_trials": len(recurrences), "later_runs": later_runs,
            "later_reached_1500": later_hits,
            "rate": later_hits / later_runs if later_runs else None,
        },
        "boss_devourer_run_wave": {
            key: {"runs": len(values), **diag.dist(values)} for key, values in dev_groups.items()
        },
        "boss_devourer_growth_units": diag.dist(all_units),
        "checkpoints": checkpoints,
        "trial_details": details,
        "errors": errors, "nonfinite": nonfinite,
    }


def fmt(value: float | None, digits: int = 1) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# w5000_v1 Boss Devourer balance experiment", "",
        f"paired {payload['trials']} trials / seed {payload['seed']} / DP v0.1 BC / Coreなし / W2500 guaranteed Legendary OFF", "",
        "D compensation: W1250/W1500/W1750 clear後に各+4 Power（累積+4/+8/+12）。診断専用。", "",
        "| Condition | Highest mean | Highest P25/P50/P75 | Final death P25/P50/P75 | W1500再到達率 | Best−recent10 P50 | Card-only variance | W2500 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in CONDITIONS:
        item = payload["paired"][name]
        card = payload["card_only"][name]
        high = item["highest_wave"]
        rate = item["w1500_rearrival"]["rate"]
        lines.append(
            f"| {name} | {fmt(item['highest_wave_mean'])} | "
            f"{fmt(high['p25'])}/{fmt(high['p50'])}/{fmt(high['p75'])} | "
            f"{fmt(item['final_death_wave']['p25'])}/{fmt(item['final_death_wave']['p50'])}/{fmt(item['final_death_wave']['p75'])} | "
            f"{fmt(rate * 100 if rate is not None else None)}% | "
            f"{fmt(item['best_minus_recent10_p50']['p50'])} | {card['highest_wave_variance']:.1f} | "
            f"{item['checkpoints']['2500']['reach_rate']:.1%} |"
        )
    lines += [
        "", "## Checkpoint reach / margin P50", "",
        "| Condition | W1250 | W1500 | W1750 | W2000 | W2250 | W2500 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name in CONDITIONS:
        item = payload["paired"][name]
        cells = []
        for wave in CHECKPOINTS:
            cp = item["checkpoints"][str(wave)]
            cells.append(f"{cp['reach_rate']:.1%} ({fmt(cp['margin']['p50'],2)})")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines += [
        "", "## Boss Devourer", "",
        "| Condition | W1250/W1500/W1750 units P50 | Owned run Wave P50 | Not-owned run Wave P50 |",
        "|---|---:|---:|---:|",
    ]
    for name in CONDITIONS:
        item = payload["paired"][name]
        groups = item["boss_devourer_run_wave"]
        lines.append(
            f"| {name} | {fmt(item['checkpoints']['1250']['boss_devourer_units']['p50'])}/"
            f"{fmt(item['checkpoints']['1500']['boss_devourer_units']['p50'])}/"
            f"{fmt(item['checkpoints']['1750']['boss_devourer_units']['p50'])} | "
            f"{fmt(groups.get('owned', {}).get('p50'))} | {fmt(groups.get('not_owned', {}).get('p50'))} |"
        )
    base_var = payload["card_only"]["A_current_100"]["highest_wave_variance"]
    lines += [
        "", "## Card RNG variance", "",
        "Weapon/Relic/Combat RNGを固定し、Card RNGだけを30通り変更したHighest Wave分散。", "",
        "| Condition | Variance | current比 |", "|---|---:|---:|",
    ]
    for name in CONDITIONS:
        value = payload["card_only"][name]["highest_wave_variance"]
        reduction = (base_var - value) / base_var if base_var else 0.0
        lines.append(f"| {name} | {value:.1f} | {reduction:.1%} reduction |")
    lines += [
        "", "## Validation", "",
        f"errors/nonfinite: {payload['error_count']}/{payload['nonfinite_count']}",
        f"paired config differs only intervention: {payload['paired_invariants']['only_intervention_diff']}",
        "", "正式仕様・formal値は未変更。候補の自動採用なし。", "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--seed", type=int, default=sim.SEED)
    parser.add_argument("--max-attempts", type=int, default=140)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("output/w5000_v1_boss_devourer_balance_30"),
    )
    args = parser.parse_args()
    if not 1 <= args.trials <= 30:
        parser.error("experiment is limited to 1..30 paired trials")
    configs = make_configs(args.max_attempts)
    paired, card_only = {}, {}
    all_errors = []
    tasks = [
        (name, config, args.trials, args.seed, card_only_mode)
        for name, config in configs.items() for card_only_mode in (False, True)
    ]
    with concurrent.futures.ProcessPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for name, card_only_mode, summary, errors in pool.map(execute_task, tasks):
            (card_only if card_only_mode else paired)[name] = summary
            all_errors.extend(errors)
    normalized = []
    for config in configs.values():
        values = dataclasses.asdict(config)
        values.pop("diagnostic_boss_devourer_growth_multiplier")
        values.pop("diagnostic_fixed_wave_power_milestones")
        normalized.append(values)
    payload = {
        "trials": args.trials, "seed": args.seed, "max_attempts": args.max_attempts,
        "conditions": {
            name: {"growth": CONDITIONS[name][0], "milestones": CONDITIONS[name][1]}
            for name in CONDITIONS
        },
        "paired": paired, "card_only": card_only,
        "paired_invariants": {
            "only_intervention_diff": all(item == normalized[0] for item in normalized[1:])
        },
        "error_count": len(all_errors),
        "nonfinite_count": sum(
            len(group[name]["nonfinite"])
            for group in (paired, card_only) for name in CONDITIONS
        ),
        "formal_changed": False, "automatic_adoption": False,
    }
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "boss_devourer_balance_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "boss_devourer_balance_report.md").write_text(
        markdown(payload), encoding="utf-8"
    )
    fields = (
        "cohort", "condition", "trial", "highest_wave", "final_death_wave",
        "deaths", "best_minus_recent10_p50",
    )
    with (output / "boss_devourer_balance_trials.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for cohort, group in (("paired", paired), ("card_only", card_only)):
            for name in CONDITIONS:
                for row in group[name]["trial_details"]:
                    writer.writerow({key: {"cohort": cohort, "condition": name, **row}[key] for key in fields})
    print(json.dumps({
        "report": str(output / "boss_devourer_balance_report.md"),
        "json": str(output / "boss_devourer_balance_summary.json"),
        "errors": payload["error_count"], "nonfinite": payload["nonfinite_count"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
