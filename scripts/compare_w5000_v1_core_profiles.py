#!/usr/bin/env python3
"""Small paired comparison of interchangeable W5000 v1 Core profiles."""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
from pathlib import Path
from typing import Any

import simulate_first_prestige_v1 as sim
import w5000_v1_profile as profile


CHECKPOINTS = profile.CORE_CHECKPOINTS
CORE_CONFIG_FIELDS = {
    "exponential_core_guaranteed_wave",
    "exponential_core_growth_stages",
}


def percentile(values: list[float], q: float) -> float | None:
    return None if not values else sim.percentile(values, q)


def distribution(values: list[float]) -> dict[str, float | None]:
    return {
        "min": min(values) if values else None,
        "p25": percentile(values, 0.25),
        "p50": percentile(values, 0.50),
        "p75": percentile(values, 0.75),
        "max": max(values) if values else None,
    }


def core_exponent_at(core_name: str, wave: int) -> float:
    config = profile.build_config(core_profile=core_name)
    run = sim.RunState(kills=wave)
    if profile.CORE_PROFILES[core_name].enabled and wave >= 2500:
        run.counts["exponential_core"] = 1
    return sim.exponential_core_exponent(run, config)


def summarize(core_name: str, rows: list[sim.TrialResult], config: sim.SimConfig) -> dict[str, Any]:
    checkpoints: dict[str, Any] = {}
    nonfinite: list[dict[str, Any]] = []
    for wave in CHECKPOINTS:
        reached = [row for row in rows if wave in row.first_reach_checkpoints]
        margins: list[float] = []
        exponents: list[float] = []
        for trial, row in enumerate(rows):
            if wave not in row.first_reach_checkpoints:
                continue
            final_power = sum(row.first_reach_checkpoints[wave])
            margin = final_power - sim.configured_enemy_power(wave, config)
            exponent = core_exponent_at(core_name, wave)
            if not math.isfinite(final_power) or not math.isfinite(margin) or not math.isfinite(exponent):
                nonfinite.append(
                    {"trial": trial, "wave": wave, "final_power": final_power,
                     "margin": margin, "core_exponent": exponent}
                )
            margins.append(margin)
            exponents.append(exponent)
        checkpoints[str(wave)] = {
            "reached": len(reached),
            "reach_rate": len(reached) / len(rows),
            "core_exponent": distribution(exponents),
            "player_minus_enemy_power": distribution(margins),
        }
    return {
        "success_rate": sum(row.success for row in rows) / len(rows),
        "deaths": distribution([float(row.deaths) for row in rows]),
        "runs": distribution([float(row.attempts) for row in rows]),
        "checkpoints": checkpoints,
        "nonfinite": nonfinite,
    }


def normalized_config(config: sim.SimConfig) -> dict[str, Any]:
    values = dataclasses.asdict(config)
    return {key: value for key, value in values.items() if key not in CORE_CONFIG_FIELDS}


def paired_invariants(
    results: dict[str, list[sim.TrialResult]], configs: dict[str, sim.SimConfig]
) -> dict[str, Any]:
    names = list(results)
    config_match = all(
        normalized_config(configs[name]) == normalized_config(configs[names[0]])
        for name in names[1:]
    )
    prefix_mismatches: list[dict[str, Any]] = []
    for trial in range(len(results[names[0]])):
        rows = [results[name][trial] for name in names]
        reached = [2500 in row.reach_seconds for row in rows]
        times = [row.reach_seconds.get(2500) for row in rows]
        if len(set(reached)) != 1 or (all(reached) and len(set(times)) != 1):
            prefix_mismatches.append({"trial": trial, "reached_w2500": reached, "reach_seconds": times})
    return {
        "same_seed_formula": "seed + 1_000_000 + trial_index for every Core profile",
        "non_core_config_match": config_match,
        "w2500_prefix_match": not prefix_mismatches,
        "prefix_mismatches": prefix_mismatches,
    }


def markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# w5000_v1 Exponential Core paired comparison",
        "",
        f"{payload['trials']} paired trials / Standard bot / seed {payload['seed']} / "
        f"max attempts {payload['max_attempts']}",
        "",
        "B/C/Dは同じ3段階式で、Cは各段階-0.05、Dは各段階+0.05。正式採用値ではない。",
        "",
        "| Core profile | W2500 | W3000 | W3500 | W4000 | W4500 | W5000 | Deaths P50 | Runs P50 | Nonfinite |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, result in payload["profiles"].items():
        rates = [result["checkpoints"][str(w)]["reach_rate"] for w in CHECKPOINTS]
        lines.append(
            f"| {name} | " + " | ".join(f"{value:.1%}" for value in rates)
            + f" | {result['deaths']['p50']:.1f} | {result['runs']['p50']:.1f} | {len(result['nonfinite'])} |"
        )
    lines += [
        "",
        "## Paired invariants",
        "",
        f"- Core以外のconfig一致: {payload['paired_invariants']['non_core_config_match']}",
        f"- W2500までの到達状態/時刻一致: {payload['paired_invariants']['w2500_prefix_match']}",
        f"- seed: `{payload['paired_invariants']['same_seed_formula']}`",
    ]
    for name, result in payload["profiles"].items():
        lines += ["", f"## {name}", "", "| W | Core exponent min/P25/P50/P75/max | Margin min/P25/P50/P75/max |", "|---:|---:|---:|"]
        for wave in CHECKPOINTS:
            item = result["checkpoints"][str(wave)]
            exponent = item["core_exponent"]
            margin = item["player_minus_enemy_power"]
            def fmt(values: dict[str, float | None]) -> str:
                return "/".join("—" if values[key] is None else f"{values[key]:.3f}" for key in ("min", "p25", "p50", "p75", "max"))
            lines.append(f"| {wave} | {fmt(exponent)} | {fmt(margin)} |")
    lines += ["", "本結果はCore比較基盤の10-pair診断であり、Core正式採用やゲームバランスの結論には使用しない。", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=10)
    parser.add_argument("--seed", type=int, default=sim.SEED)
    parser.add_argument("--max-attempts", type=int, default=140)
    parser.add_argument("--output-dir", type=Path, default=Path("output/w5000_v1_core_profiles_10"))
    args = parser.parse_args()
    if not 1 <= args.trials <= 10:
        parser.error("Core scaffold comparison is limited to 1-10 paired trials")

    configs = {
        name: profile.build_config(max_attempts=args.max_attempts, core_profile=name)
        for name in profile.CORE_PROFILES
    }
    results = {
        name: sim.simulate_standard(args.trials, config, args.seed, workers=1)
        for name, config in configs.items()
    }
    payload = {
        "profile": profile.PROFILE_NAME,
        "trials": args.trials,
        "seed": args.seed,
        "max_attempts": args.max_attempts,
        "core_profiles": {name: dataclasses.asdict(value) for name, value in profile.CORE_PROFILES.items()},
        "paired_invariants": paired_invariants(results, configs),
        "profiles": {name: summarize(name, rows, configs[name]) for name, rows in results.items()},
        "formal_modified": False,
        "core_adopted": False,
    }
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "w5000_v1_core_profiles.json"
    md_path = output_dir / "w5000_v1_core_profiles.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(markdown(payload), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "markdown": str(md_path),
                      "paired_invariants": payload["paired_invariants"],
                      "nonfinite": {name: len(value["nonfinite"]) for name, value in payload["profiles"].items()}},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
