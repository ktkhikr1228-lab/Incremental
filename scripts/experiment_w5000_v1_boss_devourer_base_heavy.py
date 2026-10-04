#!/usr/bin/env python3
"""Compare fixed-base versus variable-growth Boss Devourer allocations."""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import json
import math
import statistics
from pathlib import Path
from typing import Any

import experiment_w5000_v1_boss_devourer_balance as common
import simulate_first_prestige_v1 as sim
import w5000_v1_profile as profile


CONDITIONS = {
    "A_current": {"growth": 1.00, "base_power": 0.0},
    "B_base_heavy_75": {"growth": 0.75, "base_power": 6.0},
    "C_base_heavy_50": {"growth": 0.50, "base_power": 12.0},
}


def make_configs(max_attempts: int) -> dict[str, sim.SimConfig]:
    base = dataclasses.replace(
        profile.build_config(
            max_attempts=max_attempts, core_profile="no_core", guaranteed_legendary=False,
        ),
        diagnostic_checkpoints=common.CHECKPOINTS,
        dp_v01=sim.DPV01Config(enabled=True),
    )
    return {
        name: dataclasses.replace(
            base,
            diagnostic_boss_devourer_growth_multiplier=item["growth"],
            diagnostic_boss_devourer_base_power=item["base_power"],
        )
        for name, item in CONDITIONS.items()
    }


def execute_task(args):
    name, config, trials, seed, card_only = args
    rows, errors = common.execute(name, config, trials, seed, card_only)
    return name, card_only, common.summarize(rows, errors, trials), errors


def contribution_summary(summary: dict[str, Any], config: sim.SimConfig) -> dict[str, Any]:
    rows = []
    for detail in summary["trial_details"]:
        # Per-run contribution details are added separately from the trial CSV;
        # checkpoint state summaries below are the comparable progression view.
        rows.append(detail)
    checkpoints = {}
    for wave in common.CHECKPOINTS:
        cp = summary["checkpoints"][str(wave)]
        units = cp["boss_devourer_units"]
        checkpoints[str(wave)] = {
            "base_power_if_owned": config.diagnostic_boss_devourer_base_power,
            "growth_units": units,
            "growth_power_at_units_p50": (
                units["p50"] * math.log10(1.15) if units["p50"] is not None else None
            ),
        }
    return checkpoints


def fmt(value: float | None, digits: int = 1) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# w5000_v1 Boss Devourer base-heavy experiment", "",
        f"paired {payload['trials']} trials / seed {payload['seed']} / DP v0.1 BC / Coreなし / W2500 guaranteed Legendary OFF", "",
        "B: growth 75% + 所持中固定+6 Power。C: growth 50% + 所持中固定+12 Power。外部Wave補償なし。", "",
        "| Condition | Highest mean | Highest P25/P50/P75 | W1500再到達率 | Best−recent10 P50 | Card-only variance | W2500 | W5000 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in CONDITIONS:
        item = payload["paired"][name]
        card = payload["card_only"][name]
        high = item["highest_wave"]
        recurrence = item["w1500_rearrival"]["rate"]
        lines.append(
            f"| {name} | {fmt(item['highest_wave_mean'])} | "
            f"{fmt(high['p25'])}/{fmt(high['p50'])}/{fmt(high['p75'])} | "
            f"{fmt(recurrence * 100 if recurrence is not None else None)}% | "
            f"{fmt(item['best_minus_recent10_p50']['p50'])} | {card['highest_wave_variance']:.1f} | "
            f"{item['checkpoints']['2500']['reach_rate']:.1%} | {item['success_rate']:.1%} |"
        )
    lines += [
        "", "## Checkpoint reach / margin P50", "",
        "| Condition | W1250 | W1500 | W1750 | W2000 | W2250 | W2500 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name in CONDITIONS:
        item = payload["paired"][name]
        cells = []
        for wave in common.CHECKPOINTS:
            cp = item["checkpoints"][str(wave)]
            cells.append(f"{cp['reach_rate']:.1%} ({fmt(cp['margin']['p50'],2)})")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines += [
        "", "## Boss Devourer contribution", "",
        "固定寄与は所持時のみ。Growth Powerはcheckpoint到達者のgrowth units P50を`log10(1.15)`で換算。", "",
        "| Condition | First acquire Wave P50 | Fixed Power | Growth Power W1250/W1500/W1750 P50 |",
        "|---|---:|---:|---:|",
    ]
    for name in CONDITIONS:
        item = payload["paired"][name]
        contrib = payload["contribution"][name]
        first = item["boss_devourer_first_wave"]
        values = [contrib[str(w)]["growth_power_at_units_p50"] for w in (1250, 1500, 1750)]
        lines.append(
            f"| {name} | {fmt(first['p50'])} | {CONDITIONS[name]['base_power']:.1f} | "
            + "/".join(fmt(value, 2) for value in values) + " |"
        )
    base_var = payload["card_only"]["A_current"]["highest_wave_variance"]
    lines += [
        "", "## Card RNG variance", "",
        "Weapon/Relic/Combat RNG固定、Card RNGのみ30通り。", "",
        "| Condition | Variance | current比 |", "|---|---:|---:|",
    ]
    for name in CONDITIONS:
        value = payload["card_only"][name]["highest_wave_variance"]
        reduction = (base_var - value) / base_var if base_var else 0.0
        lines.append(f"| {name} | {value:.1f} | {reduction:.1%} reduction |")
    lines += [
        "", "## Validation", "",
        f"errors/nonfinite: {payload['error_count']}/{payload['nonfinite_count']}",
        f"non-intervention config一致: {payload['paired_invariants']['only_intervention_diff']}",
        "", "正式仕様・formal値は未変更。候補の自動採用なし。", "",
    ]
    return "\n".join(lines)


def enrich_summary(
    summary: dict[str, Any], completed_rows: list[tuple[int, sim.TrialResult]] | None = None,
) -> None:
    details = summary["trial_details"]
    summary["success_rate"] = sum(item["highest_wave"] >= 5000 for item in details) / len(details) if details else 0.0
    first_waves = []
    # Acquisition Wave is present on every saved run-end state in the source
    # result, but common.summarize intentionally condenses it. It is collected
    # by execute_with_first_wave below.
    summary.setdefault("boss_devourer_first_wave", {"p25": None, "p50": None, "p75": None})


def execute_with_first_wave(
    condition: str, config: sim.SimConfig, trials: int, seed: int, card_only: bool,
):
    rows, errors = common.execute(condition, config, trials, seed, card_only)
    summary = common.summarize(rows, errors, trials)
    first = [
        float(state["boss_devourer_first_wave"])
        for _, result in rows for state in result.run_end_states
        if state.get("boss_devourer_first_wave") is not None
    ]
    summary["boss_devourer_first_wave"] = common.diag.dist(first)
    enrich_summary(summary)
    return condition, card_only, summary, errors


def execute_full_task(args):
    return execute_with_first_wave(*args)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--seed", type=int, default=sim.SEED)
    parser.add_argument("--max-attempts", type=int, default=140)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("output/w5000_v1_boss_devourer_base_heavy_30"),
    )
    args = parser.parse_args()
    if not 1 <= args.trials <= 30:
        parser.error("experiment is limited to 1..30 paired trials")
    configs = make_configs(args.max_attempts)
    tasks = [
        (name, config, args.trials, args.seed, card_only)
        for name, config in configs.items() for card_only in (False, True)
    ]
    paired, card_only, errors = {}, {}, []
    with concurrent.futures.ProcessPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for name, is_card_only, summary, task_errors in pool.map(execute_full_task, tasks):
            (card_only if is_card_only else paired)[name] = summary
            errors.extend(task_errors)
    normalized = []
    for config in configs.values():
        values = dataclasses.asdict(config)
        values.pop("diagnostic_boss_devourer_growth_multiplier")
        values.pop("diagnostic_boss_devourer_base_power")
        normalized.append(values)
    payload = {
        "trials": args.trials, "seed": args.seed, "max_attempts": args.max_attempts,
        "conditions": CONDITIONS, "paired": paired, "card_only": card_only,
        "contribution": {
            name: contribution_summary(paired[name], configs[name]) for name in CONDITIONS
        },
        "paired_invariants": {
            "only_intervention_diff": all(item == normalized[0] for item in normalized[1:])
        },
        "error_count": len(errors),
        "nonfinite_count": sum(
            len(group[name]["nonfinite"])
            for group in (paired, card_only) for name in CONDITIONS
        ),
        "formal_changed": False, "automatic_adoption": False,
    }
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "boss_devourer_base_heavy_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "boss_devourer_base_heavy_report.md").write_text(
        markdown(payload), encoding="utf-8"
    )
    print(json.dumps({
        "report": str(output / "boss_devourer_base_heavy_report.md"),
        "json": str(output / "boss_devourer_base_heavy_summary.json"),
        "errors": payload["error_count"], "nonfinite": payload["nonfinite_count"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
