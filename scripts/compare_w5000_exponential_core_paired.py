#!/usr/bin/env python3
"""Paired W2500-state replay for Exponential Core candidates.

The W1-W2500 prefix is generated once per seed and persisted.  Every Core
candidate then resumes from the same RunState, PermanentState and RNG state.
Formal spec/config files are not modified.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import copy
import csv
import importlib
import json
import math
import os
import pickle
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
        disabled_card_keys=frozenset({"exponential_core", "final_equation"}),
    )


class CapturedW2500(BaseException):
    def __init__(self, run: Any, permanent: Any, rng_state: object, snapshot: Any):
        self.run = copy.deepcopy(run)
        self.permanent = copy.deepcopy(permanent)
        self.rng_state = rng_state
        self.snapshot = snapshot


def capture_state(sim: Any, trial: int, seed: int, max_attempts: int) -> dict[str, Any] | None:
    config = make_config(sim, None, max_attempts)
    rng = random.Random(seed + 1_000_000 + trial)
    permanent = sim.PermanentState(
        automation_enabled=config.automation_enabled,
        rare_card_automation_enabled=config.future_qol_enabled,
        one_tap_workshop_enabled=config.future_qol_enabled,
    )
    original_compute = sim.compute_snapshot

    def capture_compute(run: Any, current_permanent: Any, boss: bool, current_config: Any) -> Any:
        snapshot = original_compute(run, current_permanent, boss, current_config)
        if run.kills == 2500:
            raise CapturedW2500(run, current_permanent, rng.getstate(), snapshot)
        return snapshot

    sim.compute_snapshot = capture_compute
    try:
        for attempt in range(1, max_attempts + 1):
            try:
                result = sim.run_once(rng, "balanced", permanent, config, True)
            except CapturedW2500 as captured:
                return {
                    "trial": trial,
                    "seed": seed + 1_000_000 + trial,
                    "attempt": attempt,
                    "run": captured.run,
                    "permanent": captured.permanent,
                    "rng_state": captured.rng_state,
                    "base_snapshot": captured.snapshot,
                }
            sim.store_memory_candidates(result, permanent)
            gained = result.reached // 5
            sim.allocate_and_spend_dp(permanent, "balanced", gained, config)
            sim.purchase_game_speed(permanent, config)
            sim.convert_surplus_material(permanent, config)
            sim.forge_relics(rng, permanent, config)
    finally:
        sim.compute_snapshot = original_compute
    return None


def replay_condition(sim: Any, captured: dict[str, Any], exponent: float | None) -> dict[str, Any]:
    # Continuation is deliberately a single paired run; max_attempts is not
    # consulted by run_once(), but one documents that intent in the config.
    config = make_config(sim, exponent, 1)
    run = copy.deepcopy(captured["run"])
    permanent = copy.deepcopy(captured["permanent"])
    rng = random.Random()
    rng.setstate(captured["rng_state"])
    if exponent is not None:
        # Add only the formula switch.  Do not add card count, tags, growth
        # units, interaction time, or consume RNG through acquire_card().
        run.counts["exponential_core"] = 1
    else:
        run.counts.pop("exponential_core", None)

    original_compute = sim.compute_snapshot
    observed: dict[int, dict[str, float]] = {}

    def observe_compute(run_state: Any, permanent_state: Any, boss: bool, current_config: Any) -> Any:
        snapshot = original_compute(run_state, permanent_state, boss, current_config)
        wave = int(run_state.kills)
        if wave in CHECKPOINTS and wave not in observed:
            observed[wave] = {
                "base_atk_power": float(snapshot.base_attack_power),
                "final_damage_power": float(snapshot.log_dps),
            }
        return snapshot

    base_before = original_compute(captured["run"], captured["permanent"], True, make_config(sim, None, 1))
    base_after = original_compute(run, permanent, True, config)
    observed[2500] = {
        "base_atk_power": float(base_after.base_attack_power),
        "final_damage_power": float(base_after.log_dps),
    }
    combat_before = float(run.combat_seconds)
    interaction_before = float(permanent.interaction_seconds)
    sim.compute_snapshot = observe_compute
    try:
        result = sim.run_once(
            rng,
            "balanced",
            permanent,
            config,
            True,
            target_wave=5000,
            initial_run=run,
            start_wave=2501,
        )
    finally:
        sim.compute_snapshot = original_compute

    reach_hours: dict[int, float] = {2500: 0.0}
    for wave, (combat_elapsed, interaction_elapsed) in result.reach_elapsed.items():
        if wave >= 3000:
            reach_hours[int(wave)] = (
                float(combat_elapsed) - combat_before + float(interaction_elapsed)
            ) / 3600.0
    success = result.reached >= 5000
    delta_power = float(base_after.base_attack_power - base_before.base_attack_power)
    multiplier = 10.0**delta_power if delta_power < 308.0 else math.inf
    return {
        "success": success,
        "reached_wave": int(result.reached),
        "failure_wave": None if success else int(result.failure_wave or result.reached + 1),
        "post_w2500_deaths": 0 if success else 1,
        "reach_hours": reach_hours,
        "checkpoint_power": observed,
        "w2500_base_atk_power_without_core": float(base_before.base_attack_power),
        "w2500_base_atk_power_with_core": float(base_after.base_attack_power),
        "w2500_core_power_gain": delta_power,
        "w2500_core_multiplier": multiplier,
        "interaction_hours": (float(permanent.interaction_seconds) - interaction_before) / 3600.0,
    }


def worker(trial: int, seed: int, max_attempts: int, state_dir: str) -> dict[str, Any]:
    import simulate_first_prestige_v1 as sim

    sim = importlib.reload(sim)
    sim.CHECKPOINTS = CHECKPOINTS
    sim.REACH_WAVES = CHECKPOINTS
    sim.VARIANT_REACH_WAVES = CHECKPOINTS
    captured = capture_state(sim, trial, seed, max_attempts)
    if captured is None:
        return {"trial": trial, "captured": False}

    state_path = Path(state_dir) / f"trial_{trial:03d}_w2500.pkl"
    with state_path.open("wb") as handle:
        pickle.dump(captured, handle, protocol=pickle.HIGHEST_PROTOCOL)

    conditions: dict[str, Any] = {}
    for label, exponent in CONDITIONS:
        conditions[label] = replay_condition(sim, captured, exponent)
    return {
        "trial": trial,
        "captured": True,
        "attempt_at_capture": captured["attempt"],
        "state_file": str(state_path.resolve()),
        "conditions": conditions,
    }


def failure_bins(waves: list[int]) -> dict[str, int]:
    bins = {f"{start}-{start + 99}": 0 for start in range(2500, 5000, 100)}
    for wave in waves:
        start = min(4900, max(2500, (wave // 100) * 100))
        bins[f"{start}-{start + 99}"] += 1
    return {key: value for key, value in bins.items() if value}


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    captured_rows = [row for row in rows if row["captured"]]
    if not captured_rows:
        return {
            "method": {
                "design": "paired replay from identical post-W2500 Run/Permanent/RNG state",
                "prefix_simulated_once_per_seed": True,
                "post_w2500_retries": False,
                "core_injection": "formula flag only; no card count/tags/interaction/RNG side effects",
                "final_damage_power": "log10 DPS from simulator Snapshot.log_dps",
            },
            "requested_seed_count": len(rows),
            "captured_w2500_states": 0,
            "not_reached_w2500": len(rows),
            "capture_attempt_p50": None,
            "results": {},
        }
    results: dict[str, Any] = {}
    for label, exponent in CONDITIONS:
        entries = [row["conditions"][label] for row in captured_rows]

        def times(wave: int) -> list[float]:
            return [entry["reach_hours"][wave] for entry in entries if wave in entry["reach_hours"]]

        failures = [entry["failure_wave"] for entry in entries if entry["failure_wave"] is not None]
        checkpoint_summary: dict[str, Any] = {}
        for wave in CHECKPOINTS:
            cp = [entry["checkpoint_power"][wave] for entry in entries if wave in entry["checkpoint_power"]]
            checkpoint_summary[str(wave)] = {
                "reached": len(cp),
                "base_atk_power_p25": percentile([item["base_atk_power"] for item in cp], 0.25),
                "base_atk_power_p50": percentile([item["base_atk_power"] for item in cp], 0.50),
                "base_atk_power_p75": percentile([item["base_atk_power"] for item in cp], 0.75),
                "final_damage_power_p25": percentile([item["final_damage_power"] for item in cp], 0.25),
                "final_damage_power_p50": percentile([item["final_damage_power"] for item in cp], 0.50),
                "final_damage_power_p75": percentile([item["final_damage_power"] for item in cp], 0.75),
            }
        results[label] = {
            "exponent": exponent,
            "paired_states": len(entries),
            "reach_rate": {
                str(wave): sum(wave in entry["reach_hours"] for entry in entries) / len(entries)
                for wave in CHECKPOINTS[1:]
            },
            "w2500_to_w3000_hours_p50": percentile(times(3000), 0.50),
            "w2500_to_w5000_hours_p50": percentile(times(5000), 0.50),
            "post_w2500_deaths_p50": percentile(
                [float(entry["post_w2500_deaths"]) for entry in entries], 0.50
            ),
            "failure_wave": {
                "count": len(failures),
                "p25": percentile([float(value) for value in failures], 0.25),
                "p50": percentile([float(value) for value in failures], 0.50),
                "p75": percentile([float(value) for value in failures], 0.75),
                "bins_100_waves": failure_bins([int(value) for value in failures]),
            },
            "w2500_core_effect": {
                "base_atk_power_before_p50": percentile(
                    [entry["w2500_base_atk_power_without_core"] for entry in entries], 0.50
                ),
                "power_gain_p25": percentile([entry["w2500_core_power_gain"] for entry in entries], 0.25),
                "power_gain_p50": percentile([entry["w2500_core_power_gain"] for entry in entries], 0.50),
                "power_gain_p75": percentile([entry["w2500_core_power_gain"] for entry in entries], 0.75),
                "multiplier_p25": percentile([entry["w2500_core_multiplier"] for entry in entries], 0.25),
                "multiplier_p50": percentile([entry["w2500_core_multiplier"] for entry in entries], 0.50),
                "multiplier_p75": percentile([entry["w2500_core_multiplier"] for entry in entries], 0.75),
            },
            "checkpoint_power": checkpoint_summary,
        }
    return {
        "method": {
            "design": "paired replay from identical post-W2500 Run/Permanent/RNG state",
            "prefix_simulated_once_per_seed": True,
            "post_w2500_retries": False,
            "core_injection": "formula flag only; no card count/tags/interaction/RNG side effects",
            "final_damage_power": "log10 DPS from simulator Snapshot.log_dps",
        },
        "requested_seed_count": len(rows),
        "captured_w2500_states": len(captured_rows),
        "not_reached_w2500": len(rows) - len(captured_rows),
        "capture_attempt_p50": percentile(
            [float(row["attempt_at_capture"]) for row in captured_rows], 0.50
        ),
        "results": results,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "trial", "condition", "exponent", "success", "reached_wave", "failure_wave",
        "post_w2500_deaths", "w2500_to_w3000_hours", "w2500_to_w5000_hours",
        "w2500_base_atk_power_without_core", "w2500_base_atk_power_with_core",
        "w2500_core_power_gain", "w2500_core_multiplier",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            if not row["captured"]:
                continue
            for label, exponent in CONDITIONS:
                entry = row["conditions"][label]
                writer.writerow({
                    "trial": row["trial"],
                    "condition": label,
                    "exponent": exponent,
                    "success": entry["success"],
                    "reached_wave": entry["reached_wave"],
                    "failure_wave": entry["failure_wave"],
                    "post_w2500_deaths": entry["post_w2500_deaths"],
                    "w2500_to_w3000_hours": entry["reach_hours"].get(3000),
                    "w2500_to_w5000_hours": entry["reach_hours"].get(5000),
                    "w2500_base_atk_power_without_core": entry["w2500_base_atk_power_without_core"],
                    "w2500_base_atk_power_with_core": entry["w2500_base_atk_power_with_core"],
                    "w2500_core_power_gain": entry["w2500_core_power_gain"],
                    "w2500_core_multiplier": entry["w2500_core_multiplier"],
                })


def write_checkpoint_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["trial", "condition", "wave", "base_atk_power", "final_damage_power"]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            if not row["captured"]:
                continue
            for label, _ in CONDITIONS:
                for wave, values in row["conditions"][label]["checkpoint_power"].items():
                    writer.writerow({
                        "trial": row["trial"],
                        "condition": label,
                        "wave": wave,
                        "base_atk_power": values["base_atk_power"],
                        "final_damage_power": values["final_damage_power"],
                    })


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260828)
    parser.add_argument("--max-attempts", type=int, default=220)
    parser.add_argument("--workers", type=int, default=max(1, min(6, os.cpu_count() or 1)))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/w5000_exponential_core_paired_50"),
    )
    args = parser.parse_args()
    if args.trials <= 0 or args.max_attempts <= 0 or args.workers <= 0:
        parser.error("trials, max-attempts, and workers must be positive")

    output_dir = args.output_dir.resolve()
    state_dir = output_dir / "w2500_states"
    state_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(worker, trial, args.seed, args.max_attempts, str(state_dir)): trial
            for trial in range(args.trials)
        }
        for future in concurrent.futures.as_completed(futures):
            row = future.result()
            rows.append(row)
            print(
                f"trial {row['trial']:02d}: "
                + ("W2500 captured and replayed" if row["captured"] else "did not reach W2500"),
                flush=True,
            )

    rows.sort(key=lambda item: item["trial"])
    summary = summarize(rows)
    payload = {
        "settings": {
            "trials": args.trials,
            "seed": args.seed,
            "max_attempts_for_capture": args.max_attempts,
            "bot": "Standard/balanced",
            "target_wave": 5000,
            "enemy_curve": "formal through W2500; 3x compressed to formal W10000 at W5000",
            "defense": False,
            "final_equation": False,
            "card_refinement_cap": 1,
            "relic_selection_enabled": False,
            "reward_skip_enabled": True,
        },
        "summary": summary,
        "trials": rows,
    }
    json_path = output_dir / "w5000_exponential_core_paired_50.json"
    csv_path = output_dir / "w5000_exponential_core_paired_50.csv"
    checkpoint_path = output_dir / "w5000_exponential_core_paired_checkpoints_50.csv"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(csv_path, rows)
    write_checkpoint_csv(checkpoint_path, rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print(f"json={json_path}", flush=True)
    print(f"csv={csv_path}", flush=True)
    print(f"checkpoints={checkpoint_path}", flush=True)


if __name__ == "__main__":
    main()
