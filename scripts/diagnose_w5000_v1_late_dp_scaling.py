#!/usr/bin/env python3
"""Paired diagnosis of post-W2500 DP combat contribution scaling."""

from __future__ import annotations

import argparse
import copy
import dataclasses
import gzip
import json
import math
import pickle
import statistics
from pathlib import Path

import diagnose_w5000_v1_precore as diag
import replay_w5000_v1_micro_core_profiles as replay
import simulate_first_prestige_v1 as sim


CHECKPOINTS = (3000, 3500, 4000, 4500, 5000)
SCALES = {
    "A_current": 1.00,
    "B_late_dp_50": 0.50,
    "C_late_dp_25": 0.25,
    "D_late_dp_10": 0.10,
}


def make_config(capture: dict, scale: float, barrage_strength: float = 1.0) -> sim.SimConfig:
    baseline = tuple(
        (key, int(capture["permanent"].dp_v01_levels[key]))
        for key in sim.DP_V01_ITEMS
    )
    return dataclasses.replace(
        replay.base_config(140),
        diagnostic_checkpoints=(2500,) + CHECKPOINTS,
        diagnostic_dp_baseline_levels=baseline,
        diagnostic_late_dp_effect_scale=scale,
        diagnostic_infinite_barrage_strength=barrage_strength,
    )


def zero_late_config(config: sim.SimConfig) -> sim.SimConfig:
    return dataclasses.replace(config, diagnostic_late_dp_effect_scale=0.0)


def replay_one(capture: dict, label: str, scale: float, barrage_strength: float = 1.0) -> dict:
    config = make_config(capture, scale, barrage_strength)
    zero_config = zero_late_config(config)
    permanent = copy.deepcopy(capture["permanent"])
    streams = replay.restore_streams(capture)
    run = copy.deepcopy(capture["run"])
    baseline_levels = dict(config.diagnostic_dp_baseline_levels)
    remaining_runs = config.max_attempts - int(capture["attempt"]) + 1
    run_rows = []
    checkpoints = {}
    success = False

    for run_index in range(remaining_runs):
        start = {}
        end = {}
        checkpoint_late_dp = {}

        def capture_start(live_run, live_permanent, live_streams):
            snapshot = sim.compute_snapshot(live_run, live_permanent, False, config)
            baseline = sim.compute_snapshot(live_run, live_permanent, False, zero_config)
            start.update({
                "power": snapshot.log_dps,
                "late_dp_power": snapshot.log_dps - baseline.log_dps,
            })

        def capture_checkpoint(wave, live_run, live_permanent, live_streams):
            snapshot = sim.compute_snapshot(live_run, live_permanent, wave % 10 == 0, config)
            baseline = sim.compute_snapshot(live_run, live_permanent, wave % 10 == 0, zero_config)
            checkpoint_late_dp[wave] = snapshot.log_dps - baseline.log_dps

        def capture_end(live_run, live_permanent, live_streams, failure_wave):
            snapshot = sim.compute_snapshot(live_run, live_permanent, False, config)
            baseline = sim.compute_snapshot(live_run, live_permanent, False, zero_config)
            end.update({
                "power": snapshot.log_dps,
                "late_dp_power": snapshot.log_dps - baseline.log_dps,
            })

        result = sim.run_once(
            streams.combat,
            "balanced",
            permanent,
            config,
            True,
            initial_run=run if run_index == 0 else None,
            start_wave=2501 if run_index == 0 else 1,
            rng_streams=streams,
            run_start_capture=capture_start,
            checkpoint_capture=capture_checkpoint,
            run_end_capture=capture_end,
        )
        for wave, state in result.checkpoint_states.items():
            if wave not in CHECKPOINTS or str(wave) in checkpoints:
                continue
            checkpoints[str(wave)] = {
                **copy.deepcopy(state),
                "late_dp_power": checkpoint_late_dp[wave],
            }
        levels_gained = {
            key: max(0, int(permanent.dp_v01_levels[key]) - baseline_levels[key])
            for key in sim.DP_V01_ITEMS
        }
        state = result.end_state
        terminal_wave = result.failure_wave or result.reached
        terminal_power = float(
            state["boss_power"] if terminal_wave % 10 == 0 else state["normal_power"]
        )
        run_rows.append({
            "run_index": run_index + 1,
            "max_wave": int(result.reached),
            "failure_wave": result.failure_wave,
            "start_power": float(start["power"]),
            "end_power": float(end["power"]),
            "start_late_dp_power": float(start["late_dp_power"]),
            "end_late_dp_power": float(end["late_dp_power"]),
            "late_dp_levels": levels_gained,
            "late_dp_total_levels": sum(levels_gained.values()),
            "card_count": int(state["card_count"]),
            "rarity": state["rarity_composition"],
            "weapon_power": float(state["weapon_power"]),
            "relic_power": float(state["relic_power"]),
            "boss_devourer_units": float(state["boss_devourer_units"]),
            "cards": state["cards"],
            "infinite_barrage_owned": state["cards"].get("infinite_barrage", 0) > 0,
            "terminal_margin": terminal_power - sim.configured_enemy_power(terminal_wave, config),
        })
        if result.reached >= 5000:
            success = True
            break
        sim.store_memory_candidates(result, permanent)
        sim.award_and_spend_dp_v01(permanent, result.reached, config)
        sim.purchase_game_speed(permanent, config)
        sim.convert_surplus_material(permanent, config)
        sim.forge_relics(streams.relic, permanent, config)
        run = None

    waves = [row["max_wave"] for row in run_rows]
    recent = waves[-10:]
    nonfinite = []
    for row in run_rows:
        for key in ("start_power", "end_power", "start_late_dp_power", "end_late_dp_power"):
            if not math.isfinite(row[key]):
                nonfinite.append({"run": row["run_index"], "key": key, "value": row[key]})
    return {
        "trial": int(capture["trial"]),
        "condition": label,
        "success": success,
        "runs": len(run_rows),
        "additional_runs": max(0, len(run_rows) - 1),
        "best_wave": max(waves),
        "best_minus_recent10_median": max(waves) - statistics.median(recent),
        "checkpoints": checkpoints,
        "run_rows": run_rows,
        "final_late_dp_levels": run_rows[-1]["late_dp_levels"],
        "final_late_dp_total_levels": run_rows[-1]["late_dp_total_levels"],
        "final_late_dp_power": run_rows[-1]["end_late_dp_power"],
        "terminal_margin": run_rows[-1]["terminal_margin"],
        "infinite_barrage_acquired": any(
            item["infinite_barrage_owned"] for item in run_rows
        ),
        "nonfinite": nonfinite,
    }


def summarize(rows: list[dict]) -> dict:
    successes = [row for row in rows if row["success"]]
    checkpoints = {}
    for wave in CHECKPOINTS:
        reached = [row["checkpoints"][str(wave)] for row in rows if str(wave) in row["checkpoints"]]
        checkpoints[str(wave)] = {
            "reached": len(reached),
            "reach_rate": len(reached) / len(rows),
            "margin": diag.dist([float(item["margin_power"]) for item in reached]),
            "late_dp_power": diag.dist([float(item["late_dp_power"]) for item in reached]),
        }
    all_runs = [run for row in rows for run in row["run_rows"]]
    best_waves = [float(row["best_wave"]) for row in rows]
    return {
        "samples": len(rows),
        "successes": len(successes),
        "checkpoints": checkpoints,
        "additional_runs_to_w5000": diag.dist([row["additional_runs"] for row in successes]),
        "w5000_margin": diag.dist([
            float(row["checkpoints"]["5000"]["margin_power"])
            for row in successes if "5000" in row["checkpoints"]
        ]),
        "run_start_power": diag.dist([run["start_power"] for run in all_runs]),
        "run_end_power": diag.dist([run["end_power"] for run in all_runs]),
        "late_dp_levels": diag.dist([row["final_late_dp_total_levels"] for row in rows]),
        "late_dp_levels_by_item": {
            key: diag.dist([row["final_late_dp_levels"][key] for row in rows])
            for key in sim.DP_V01_ITEMS
        },
        "late_dp_power": diag.dist([row["final_late_dp_power"] for row in rows]),
        "best_wave": diag.dist(best_waves),
        "best_wave_variance": statistics.pvariance(best_waves),
        "best_minus_recent10_median": diag.dist([
            row["best_minus_recent10_median"] for row in rows
        ]),
        "terminal_margin": diag.dist([row["terminal_margin"] for row in rows]),
        "rows": rows,
    }


def fmt(value, digits=2):
    return "—" if value is None else f"{value:.{digits}f}"


def markdown(payload: dict) -> str:
    lines = [
        "# w5000_v1 late-game DP contribution scaling", "",
        "Only DP levels earned after each saved W2500 checkpoint are scaled in combat. DP gains, costs, purchases, pre-W2500 levels, and all non-DP systems remain unchanged.", "",
        "| Condition | W3000 | W3500 | W4000 | W4500 | W5000 | Add Runs P25/P50/P75 | W5000 Margin P50 | Late DP Lv P50 | Late DP Power P50 | Best Wave variance | Best-recent10 P50 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label in SCALES:
        item = payload["conditions"][label]
        runs = item["additional_runs_to_w5000"]
        lines.append(
            f"| {label} | "
            + " | ".join(f"{item['checkpoints'][str(w)]['reach_rate']:.0%}" for w in CHECKPOINTS)
            + f" | {fmt(runs['p25'],1)}/{fmt(runs['p50'],1)}/{fmt(runs['p75'],1)} | "
            f"{fmt(item['w5000_margin']['p50'],2)} | {fmt(item['late_dp_levels']['p50'],1)} | "
            f"{fmt(item['late_dp_power']['p50'],2)} | {fmt(item['best_wave_variance'],1)} | "
            f"{fmt(item['best_minus_recent10_median']['p50'],1)} |"
        )
    lines += ["", "## Checkpoint late-DP contribution", "", "| Condition | W3000 | W3500 | W4000 | W4500 | W5000 |", "|---|---:|---:|---:|---:|---:|"]
    for label in SCALES:
        item = payload["conditions"][label]
        lines.append(
            f"| {label} | " + " | ".join(
                fmt(item["checkpoints"][str(w)]["late_dp_power"]["p50"], 2)
                for w in CHECKPOINTS
            ) + " |"
        )
    lines += ["", "## Validation", "", f"- paired W2500 states: {payload['state_count']}", f"- error/nonfinite/overflow: {payload['error_count']}/{payload['nonfinite_count']}/{payload['overflow_count']}", "- no Core; no card/enemy/weapon/relic balance changes; no new Core profile.", "- Medium 20% remains provisional and disabled in this diagnosis.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260828)
    parser.add_argument("--states", type=Path, default=Path("output/w5000_v1_micro_core_10_states_final/w2500_checkpoint_states.pkl.gz"))
    parser.add_argument("--output-dir", type=Path, default=Path("output/w5000_v1_late_dp_scaling_10_states"))
    args = parser.parse_args()
    with gzip.open(args.states, "rb") as handle:
        captures = pickle.load(handle)
    if len(captures) != 10:
        raise ValueError(f"expected 10 states, found {len(captures)}")
    grouped = {label: [] for label in SCALES}
    errors = []
    for label, scale in SCALES.items():
        for capture in captures.values():
            try:
                grouped[label].append(replay_one(capture, label, scale))
            except Exception as exc:
                errors.append({"condition": label, "trial": capture["trial"], "type": type(exc).__name__, "message": str(exc)})
    conditions = {label: summarize(grouped[label]) for label in SCALES}
    nonfinite_count = sum(len(row["nonfinite"]) for rows in grouped.values() for row in rows)
    overflow_count = sum(error["type"] == "OverflowError" for error in errors)
    payload = {
        "seed": args.seed,
        "state_count": len(captures),
        "trial_ids": sorted(captures),
        "scales": SCALES,
        "conditions": conditions,
        "error_count": len(errors),
        "nonfinite_count": nonfinite_count,
        "overflow_count": overflow_count,
        "errors": errors,
        "formal_changed": False,
        "core_enabled": False,
    }
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = output / "late_dp_scaling_report.md"
    summary = output / "late_dp_scaling_summary.json"
    report.write_text(markdown(payload), encoding="utf-8")
    summary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report), "json": str(summary), "states": len(captures), "errors": len(errors), "nonfinite": nonfinite_count, "overflow": overflow_count}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
