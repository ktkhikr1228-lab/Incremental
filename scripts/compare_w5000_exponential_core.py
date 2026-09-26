#!/usr/bin/env python3
"""Staged 50-trial comparison of W5000 Exponential Core candidates.

This imports the first-prestige simulator without modifying formal files.
Each completed condition is immediately persisted to JSON and CSV.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import importlib
import json
import math
import os
import random
import sys
from pathlib import Path
from typing import Any


CHECKPOINTS = (2500, 3000, 3500, 4000, 4500, 5000)
CONDITIONS: tuple[tuple[str, float | None], ...] = (
    ("A_no_core", None),
    ("B_core_1.015", 1.015),
    ("C_core_1.020", 1.020),
    ("D_core_1.025", 1.025),
    ("E_core_1.030", 1.030),
)


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return float(ordered[low])
    return float(ordered[low] + (ordered[high] - ordered[low]) * (position - low))


def make_config(sim: Any, exponent: float | None, max_attempts: int) -> Any:
    disabled = {"final_equation"}
    if exponent is None:
        disabled.add("exponential_core")
    return sim.SimConfig(
        max_attempts=max_attempts,
        reward_skip_enabled=True,
        defense=sim.DefenseConfig(enabled=False),
        target_wave=5000,
        enemy_curve_scale=1.0,
        card_upgrade_cap=1,
        relic_selection_enabled=False,
        exponential_core_multiplier=1.0 if exponent is None else exponent,
        exponential_core_unlock_wave=2500,
        disabled_card_keys=frozenset(disabled),
    )


def worker_batch(
    exponent: float | None,
    guaranteed_core: bool,
    start: int,
    count: int,
    seed: int,
    max_attempts: int,
) -> list[dict[str, Any]]:
    import simulate_first_prestige_v1 as sim

    sim = importlib.reload(sim)
    sim.REACH_WAVES = CHECKPOINTS
    sim.VARIANT_REACH_WAVES = CHECKPOINTS
    if guaranteed_core and exponent is not None:
        original_guaranteed_choices = sim.process_guaranteed_choices

        def process_guaranteed_choices_with_core(
            rng: random.Random,
            profile: str,
            run: Any,
            permanent: Any,
            next_wave: int,
            config: Any,
        ) -> None:
            original_guaranteed_choices(
                rng, profile, run, permanent, next_wave, config
            )
            if run.kills == 2500 and not sim.n(run.counts, "exponential_core"):
                sim.acquire_card(run, sim.CARD_BY_KEY["exponential_core"])

        sim.process_guaranteed_choices = process_guaranteed_choices_with_core
    config = make_config(sim, exponent, max_attempts)
    rows: list[dict[str, Any]] = []
    for trial_index in range(start, start + count):
        rng = random.Random(seed + 1_000_000 + trial_index)
        result = sim.run_trial(rng, "balanced", config, allow_overdrive=True)
        first_post_2500_failure: int | None = None
        for reached in result.run_reaches:
            if 2500 <= reached < 5000:
                first_post_2500_failure = int(reached)
                break
        rows.append(
            {
                "trial": trial_index,
                "success": result.success,
                "play_hours": (
                    result.total_combat_seconds + result.total_interaction_seconds
                )
                / 3600.0,
                "deaths": result.deaths,
                "reach_hours": {
                    int(wave): seconds / 3600.0
                    for wave, seconds in result.reach_seconds.items()
                    if wave in CHECKPOINTS
                },
                "first_post_2500_failure": first_post_2500_failure,
                "final_has_core": bool(result.final_counts.get("exponential_core", 0)),
            }
        )
    return rows


def run_condition(
    exponent: float | None,
    guaranteed_core: bool,
    trials: int,
    seed: int,
    max_attempts: int,
    workers: int,
) -> list[dict[str, Any]]:
    chunk = max(1, math.ceil(trials / workers))
    jobs = [
        (
            exponent,
            guaranteed_core,
            start,
            min(chunk, trials - start),
            seed,
            max_attempts,
        )
        for start in range(0, trials, chunk)
    ]
    rows: list[dict[str, Any]] = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(worker_batch, *job) for job in jobs]
        for future in concurrent.futures.as_completed(futures):
            rows.extend(future.result())
    rows.sort(key=lambda row: row["trial"])
    return rows


def summarize(label: str, exponent: float | None, rows: list[dict[str, Any]]) -> dict[str, Any]:
    successes = [row for row in rows if row["success"]]

    reach_rates = {
        str(wave): sum(wave in row["reach_hours"] for row in rows) / len(rows)
        for wave in CHECKPOINTS
    }

    def elapsed_between(start_wave: int, end_wave: int) -> list[float]:
        return [
            row["reach_hours"][end_wave] - row["reach_hours"][start_wave]
            for row in rows
            if start_wave in row["reach_hours"] and end_wave in row["reach_hours"]
        ]

    failures = [
        int(row["first_post_2500_failure"])
        for row in rows
        if row["first_post_2500_failure"] is not None
    ]
    bins = {f"{start}-{start + 99}": 0 for start in range(2500, 5000, 100)}
    for wave in failures:
        start = min(4900, max(2500, (wave // 100) * 100))
        bins[f"{start}-{start + 99}"] += 1

    success_times = [float(row["play_hours"]) for row in successes]
    return {
        "condition": label,
        "exponential_core_exponent": exponent,
        "trials": len(rows),
        "reach_rate": reach_rates,
        "success_rate": len(successes) / len(rows),
        "prestige_time_p50": percentile(success_times, 0.50),
        "w2500_to_w3000_p50": percentile(elapsed_between(2500, 3000), 0.50),
        "w2500_to_w5000_p50": percentile(elapsed_between(2500, 5000), 0.50),
        "deaths_p50": percentile([float(row["deaths"]) for row in rows], 0.50),
        "final_run_core_rate": sum(row["final_has_core"] for row in rows) / len(rows),
        "first_post_w2500_failure": {
            "count": len(failures),
            "p25": percentile([float(value) for value in failures], 0.25),
            "p50": percentile([float(value) for value in failures], 0.50),
            "p75": percentile([float(value) for value in failures], 0.75),
            "bins_100_waves": bins,
        },
    }


def write_csv(path: Path, results: dict[str, dict[str, Any]]) -> None:
    fields = [
        "condition",
        "exponential_core_exponent",
        "trials",
        "reach_w2500_rate",
        "reach_w3000_rate",
        "reach_w3500_rate",
        "reach_w4000_rate",
        "reach_w4500_rate",
        "success_rate",
        "prestige_time_p50",
        "w2500_to_w3000_p50",
        "w2500_to_w5000_p50",
        "deaths_p50",
        "final_run_core_rate",
        "first_post_w2500_failure_count",
        "first_post_w2500_failure_p25",
        "first_post_w2500_failure_p50",
        "first_post_w2500_failure_p75",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for label, _ in CONDITIONS:
            if label not in results:
                continue
            result = results[label]
            failure = result["first_post_w2500_failure"]
            writer.writerow(
                {
                    "condition": label,
                    "exponential_core_exponent": result["exponential_core_exponent"],
                    "trials": result["trials"],
                    "reach_w2500_rate": result["reach_rate"]["2500"],
                    "reach_w3000_rate": result["reach_rate"]["3000"],
                    "reach_w3500_rate": result["reach_rate"]["3500"],
                    "reach_w4000_rate": result["reach_rate"]["4000"],
                    "reach_w4500_rate": result["reach_rate"]["4500"],
                    "success_rate": result["success_rate"],
                    "prestige_time_p50": result["prestige_time_p50"],
                    "w2500_to_w3000_p50": result["w2500_to_w3000_p50"],
                    "w2500_to_w5000_p50": result["w2500_to_w5000_p50"],
                    "deaths_p50": result["deaths_p50"],
                    "final_run_core_rate": result["final_run_core_rate"],
                    "first_post_w2500_failure_count": failure["count"],
                    "first_post_w2500_failure_p25": failure["p25"],
                    "first_post_w2500_failure_p50": failure["p50"],
                    "first_post_w2500_failure_p75": failure["p75"],
                }
            )


def save_progress(
    output_dir: Path,
    trials: int,
    seed: int,
    max_attempts: int,
    guaranteed_core: bool,
    results: dict[str, dict[str, Any]],
) -> None:
    payload = {
        "conditions": {
            "trials_per_condition": trials,
            "seed": seed,
            "max_attempts": max_attempts,
            "bot": "Standard/balanced",
            "target_wave": 5000,
            "enemy_curve": "formal through W2500; 3x compressed to formal W10000 at W5000",
            "defense": False,
            "final_equation": False,
            "card_refinement_cap": 1,
            "relic_selection_enabled": False,
            "reward_skip_enabled": True,
            "weapon_system": "existing D old Weapon Power",
            "exponential_core_semantics": (
                "B-E receive Exponential Core for free immediately after clearing W2500"
                if guaranteed_core
                else "unlocked in Legendary pool at W2500; not guaranteed"
            ),
        },
        "completed_conditions": [label for label, _ in CONDITIONS if label in results],
        "results": results,
    }
    (output_dir / "w5000_exponential_core_50_progress.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_csv(output_dir / "w5000_exponential_core_50_progress.csv", results)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260828)
    parser.add_argument("--max-attempts", type=int, default=220)
    parser.add_argument("--guaranteed-core", action="store_true")
    parser.add_argument("--workers", type=int, default=max(1, min(6, os.cpu_count() or 1)))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/w5000_exponential_core_50"),
    )
    args = parser.parse_args()
    if args.trials <= 0 or args.max_attempts <= 0 or args.workers <= 0:
        parser.error("trials, max-attempts, and workers must be positive")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict[str, Any]] = {}
    save_progress(
        output_dir,
        args.trials,
        args.seed,
        args.max_attempts,
        args.guaranteed_core,
        results,
    )

    for label, exponent in CONDITIONS:
        print(f"{label}: {args.trials} trials", flush=True)
        rows = run_condition(
            exponent,
            args.guaranteed_core,
            args.trials,
            args.seed,
            args.max_attempts,
            args.workers,
        )
        results[label] = summarize(label, exponent, rows)
        save_progress(
            output_dir,
            args.trials,
            args.seed,
            args.max_attempts,
            args.guaranteed_core,
            results,
        )
        result = results[label]
        print(
            f"  success={result['success_rate']:.1%} "
            f"p50={result['prestige_time_p50']}",
            flush=True,
        )

    print(f"json={output_dir / 'w5000_exponential_core_50_progress.json'}", flush=True)
    print(f"csv={output_dir / 'w5000_exponential_core_50_progress.csv'}", flush=True)


if __name__ == "__main__":
    main()
