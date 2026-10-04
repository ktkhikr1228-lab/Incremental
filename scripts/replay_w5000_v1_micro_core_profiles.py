#!/usr/bin/env python3
"""Replay scaled-down Core profiles from paired W2500 states."""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import copy
import dataclasses
import gzip
import json
import math
import pickle
import random
import statistics
from pathlib import Path
from typing import Any

import diagnose_w5000_v1_precore as diag
import simulate_first_prestige_v1 as sim
import w5000_v1_profile as profile


CHECKPOINTS = tuple(range(2750, 5001, 250))
SCALES = {
    "A_no_core": 0.0,
    "B_micro_core": 0.05,
    "C_low_core": 0.10,
    "D_medium_core": 0.20,
}
WEAK_STAGES = profile.CORE_PROFILES["three_stage_weaker"].stages


class CheckpointReached(Exception):
    pass


def scaled_stages(scale: float) -> tuple[tuple[int, int, float], ...]:
    if scale == 0:
        return ()
    return tuple((start, end, increment * scale) for start, end, increment in WEAK_STAGES)


def base_config(max_attempts: int) -> sim.SimConfig:
    return dataclasses.replace(
        profile.build_config(
            max_attempts=max_attempts, core_profile="no_core", guaranteed_legendary=False,
        ),
        diagnostic_checkpoints=(2500,) + CHECKPOINTS,
        dp_v01=sim.DPV01Config(enabled=True),
        diagnostic_boss_devourer_growth_multiplier=0.75,
        diagnostic_boss_devourer_base_power=6.0,
    )


def profile_config(base: sim.SimConfig, scale: float) -> sim.SimConfig:
    return dataclasses.replace(
        base,
        exponential_core_guaranteed_wave=2500 if scale else None,
        exponential_core_growth_stages=scaled_stages(scale),
    )


def regenerate_checkpoints(trials: int, seed: int, max_attempts: int):
    config = base_config(max_attempts)
    captures = {}
    errors = []
    for trial in range(trials):
        streams = sim.make_split_rng_streams(seed, trial)

        def capture(attempt, wave, run, permanent, live_streams):
            if wave != 2500:
                return
            captures[trial] = {
                "trial": trial, "attempt": attempt,
                "wave": wave,
                "run": copy.deepcopy(run),
                "permanent": copy.deepcopy(permanent),
                "rng_states": {
                    name: copy.deepcopy(getattr(live_streams, name).getstate())
                    for name in ("card", "weapon", "relic", "combat")
                },
            }
            raise CheckpointReached

        try:
            sim.run_trial(
                streams.combat, "balanced", config, True,
                rng_streams=streams, attempt_checkpoint_capture=capture,
            )
        except CheckpointReached:
            pass
        except Exception as exc:
            errors.append({"trial": trial, "type": type(exc).__name__, "message": str(exc)})
    return captures, errors


def restore_streams(capture):
    rngs = {}
    for name in ("card", "weapon", "relic", "combat"):
        rng = random.Random()
        rng.setstate(capture["rng_states"][name])
        rngs[name] = rng
    return sim.RNGStreams(rngs["card"], rngs["weapon"], rngs["relic"], rngs["combat"])


def exponent_at(config: sim.SimConfig, wave: int, enabled: bool) -> float:
    run = sim.RunState(kills=wave)
    if enabled:
        run.counts["exponential_core"] = 1
    return sim.exponential_core_exponent(run, config)


def stop_band(wave: int) -> str:
    if wave >= 5000:
        return "success"
    start = max(2500, (wave // 250) * 250)
    return f"{start}-{start + 249}"


def replay_one(capture, label, scale, base):
    config = profile_config(base, scale)
    run = copy.deepcopy(capture["run"])
    permanent = copy.deepcopy(capture["permanent"])
    streams = restore_streams(capture)
    if scale:
        run.counts["exponential_core"] = 1
        run.effect_version += 1
    initial_interaction = permanent.interaction_seconds
    checkpoints = {}
    initial = sim.compute_snapshot(run, permanent, True, config)
    checkpoints[2500] = {
        "player_power": initial.log_dps,
        "enemy_power": sim.configured_enemy_power(2500, config),
        "margin": initial.log_dps - sim.configured_enemy_power(2500, config),
        "core_exponent": exponent_at(config, 2500, bool(scale)),
    }
    runs = 0
    deaths = 0
    combat_seconds = 0.0
    same_run_wave = 2500
    final_wave = 2500
    success = False
    remaining_runs = base.max_attempts - int(capture["attempt"]) + 1
    while runs < remaining_runs:
        result = sim.run_once(
            streams.combat, "balanced", permanent, config, True,
            initial_run=run if runs == 0 else None,
            start_wave=2501 if runs == 0 else 1,
            rng_streams=streams,
        )
        runs += 1
        combat_seconds += result.combat_seconds
        final_wave = max(final_wave, result.reached)
        if runs == 1:
            same_run_wave = result.reached
        for wave, state in result.checkpoint_states.items():
            if wave < 2500 or wave in checkpoints:
                continue
            checkpoints[wave] = {
                "player_power": float(state["player_power"]),
                "enemy_power": float(state["enemy_power"]),
                "margin": float(state["margin_power"]),
                "core_exponent": exponent_at(config, wave, bool(scale)),
            }
        if result.reached >= 5000:
            success = True
            break
        deaths += 1
        sim.store_memory_candidates(result, permanent)
        sim.award_and_spend_dp_v01(permanent, result.reached, config)
        sim.purchase_game_speed(permanent, config)
        sim.convert_surplus_material(permanent, config)
        sim.forge_relics(streams.relic, permanent, config)
        run = None
    final_exponent = exponent_at(config, final_wave, bool(scale))
    post_seconds = combat_seconds + permanent.interaction_seconds - initial_interaction
    return {
        "trial": int(capture["trial"]), "profile": label,
        "w2500_attempt": int(capture["attempt"]),
        "remaining_runs_at_w2500": remaining_runs,
        "success": success, "same_run_wave": same_run_wave,
        "first_stop_band": stop_band(same_run_wave),
        "runs_from_w2500": runs, "additional_runs": max(0, runs - 1),
        "deaths_from_w2500": deaths, "game_hours_from_w2500": post_seconds / 3600.0,
        "final_wave": final_wave, "final_exponent": final_exponent,
        "checkpoints": checkpoints,
    }


def replay_task(args):
    capture, label, scale, base = args
    try:
        return replay_one(capture, label, scale, base), None
    except Exception as exc:
        return None, {
            "trial": capture["trial"], "profile": label,
            "type": type(exc).__name__, "message": str(exc),
        }


def summarize(label, rows, errors, base):
    checkpoint_summary = {}
    nonfinite = []
    for wave in CHECKPOINTS:
        reached = [row["checkpoints"][wave] for row in rows if wave in row["checkpoints"]]
        checkpoint_summary[str(wave)] = {
            "reached": len(reached), "reach_rate": len(reached) / len(rows) if rows else None,
            "core_exponent": diag.dist([item["core_exponent"] for item in reached]),
            "margin": diag.dist([item["margin"] for item in reached]),
        }
        for index, item in enumerate(reached):
            if not all(math.isfinite(float(item[key])) for key in ("player_power", "enemy_power", "margin", "core_exponent")):
                nonfinite.append({"wave": wave, "index": index, **item})
    successes = [row for row in rows if row["success"]]
    same_run_successes = [row for row in rows if row["same_run_wave"] >= 5000]
    return {
        "samples": len(rows), "successes": len(successes),
        "same_run_successes": len(same_run_successes),
        "same_run_success_rate": len(same_run_successes) / len(rows) if rows else None,
        "checkpoints": checkpoint_summary,
        "same_run_wave": diag.dist([row["same_run_wave"] for row in rows]),
        "first_stop_bands": dict(sorted(collections.Counter(row["first_stop_band"] for row in rows).items())),
        "additional_runs": diag.dist([row["additional_runs"] for row in successes]),
        "game_hours": diag.dist([row["game_hours_from_w2500"] for row in successes]),
        "w5000_margin": diag.dist([
            row["checkpoints"][5000]["margin"] for row in successes if 5000 in row["checkpoints"]
        ]),
        "final_exponent": diag.dist([row["final_exponent"] for row in rows]),
        "rows": rows, "errors": errors, "nonfinite": nonfinite,
        "overflow_errors": sum(item["type"] == "OverflowError" for item in errors),
        "exponent_by_big_boss": {
            str(wave): exponent_at(
                profile_config(base, SCALES[label]), wave, bool(SCALES[label])
            )
            for wave in range(2500, 5001, 100)
        },
    }


def fmt(value, digits=1):
    return "—" if value is None else f"{value:.{digits}f}"


def markdown(payload):
    lines = [
        "# w5000_v1 scaled weak-Core paired replay", "",
        f"{payload['checkpoint_count']} saved/reproduced W2500 states / seed {payload['seed']}", "",
        "weak Coreのincrement部分のみを0/5/10/20%へscale。段階構造とBig Boss timingは不変。", "",
        "| Profile | W2750 | W3000 | W3500 | W4000 | W4500 | W5000 | Same-run Wave P50 | Additional Runs P50 | Hours P50 | W5000 Margin P50 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label in SCALES:
        item = payload["profiles"][label]
        lines.append(
            f"| {label} | "
            + " | ".join(f"{item['checkpoints'][str(w)]['reach_rate']:.1%}" for w in (2750, 3000, 3500, 4000, 4500, 5000))
            + f" | {fmt(item['same_run_wave']['p50'])} | {fmt(item['additional_runs']['p50'])} | "
            f"{fmt(item['game_hours']['p50'],3)} | {fmt(item['w5000_margin']['p50'],3)} |"
        )
    lines += ["", "Same-run W5000 rates: " + ", ".join(
        f"{label}={payload['profiles'][label]['same_run_success_rate']:.1%}" for label in SCALES
    ) + ".", ""]
    lines += ["", "## All checkpoint reach rates", "", "| W | " + " | ".join(SCALES) + " |", "|---:|" + "---:|" * len(SCALES)]
    for wave in CHECKPOINTS:
        lines.append(
            f"| {wave} | " + " | ".join(
                f"{payload['profiles'][label]['checkpoints'][str(wave)]['reach_rate']:.1%}"
                for label in SCALES
            ) + " |"
        )
    lines += ["", "## Margin P25/P50/P75 and exponent", ""]
    for label in SCALES:
        lines += [f"### {label}", "", "| W | Margin P25/P50/P75 | Exponent |", "|---:|---:|---:|"]
        for wave in CHECKPOINTS:
            cp = payload["profiles"][label]["checkpoints"][str(wave)]
            margin = cp["margin"]
            exponent = cp["core_exponent"]
            lines.append(
                f"| {wave} | {fmt(margin['p25'],3)}/{fmt(margin['p50'],3)}/{fmt(margin['p75'],3)} | "
                f"{fmt(exponent['p50'],4)} |"
            )
        lines += ["", "First-stop bands: `" + json.dumps(payload["profiles"][label]["first_stop_bands"], ensure_ascii=False) + "`", ""]
    lines += [
        "## Validation", "",
        f"- 前回W2500 trial IDs一致: {payload['validation']['previous_trial_ids_match']}",
        f"- checkpoint state/RNG source共通: {payload['validation']['single_source_states']}",
        f"- Core以外のconfig差分なし: {payload['validation']['only_core_config_diff']}",
        f"- 元trialの残りRun上限を維持: {payload['validation']['remaining_run_cap_preserved']}",
        f"- errors/nonfinite/overflow: {payload['error_count']}/{payload['nonfinite_count']}/{payload['overflow_count']}",
        "- 正式Core値変更・自動採用なし。", "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--seed", type=int, default=sim.SEED)
    parser.add_argument("--max-attempts", type=int, default=140)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--previous-core-json", type=Path,
        default=Path("output/w5000_v1_core_profiles_current_30_final/w5000_v1_core_profiles_current_30.json"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("output/w5000_v1_micro_core_10_states"))
    args = parser.parse_args()
    if args.trials != 30:
        parser.error("this paired replay expects the original 30-trial seed set")
    captures, capture_errors = regenerate_checkpoints(args.trials, args.seed, args.max_attempts)
    previous = json.loads(args.previous_core_json.read_text(encoding="utf-8"))
    previous_ids = sorted(
        item["trial"] for item in previous["profiles"]["A_no_core"]["progression"]["trials"]
    )
    current_ids = sorted(captures)
    base = base_config(args.max_attempts)
    tasks = [
        (capture, label, scale, base)
        for capture in captures.values() for label, scale in SCALES.items()
    ]
    grouped = {label: [] for label in SCALES}
    replay_errors = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for row, error in pool.map(replay_task, tasks):
            if error:
                replay_errors.append(error)
            else:
                grouped[row["profile"]].append(row)
    profiles = {
        label: summarize(
            label, sorted(grouped[label], key=lambda row: row["trial"]),
            [error for error in replay_errors if error["profile"] == label], base,
        )
        for label in SCALES
    }
    reference_config = profile_config(base, SCALES["A_no_core"])
    config_differences = {}
    for label, scale in SCALES.items():
        candidate_config = profile_config(base, scale)
        config_differences[label] = [
            field.name for field in dataclasses.fields(sim.SimConfig)
            if getattr(reference_config, field.name) != getattr(candidate_config, field.name)
        ]
    allowed_core_fields = {"exponential_core_guaranteed_wave", "exponential_core_growth_stages"}
    payload = {
        "seed": args.seed, "checkpoint_count": len(captures),
        "trial_ids": current_ids,
        "profiles_definition": {
            label: {"weak_increment_scale": scale, "stages": scaled_stages(scale)}
            for label, scale in SCALES.items()
        },
        "common_conditions": {
            "dp": "v0.1", "boss_devourer": "base-heavy B",
            "w2500_guaranteed_legendary": False, "enemy_curve": "w5000_v1",
        },
        "profiles": profiles,
        "validation": {
            "previous_trial_ids": previous_ids,
            "previous_trial_ids_match": previous_ids == current_ids,
            "single_source_states": True,
            "config_differences_from_no_core": config_differences,
            "only_core_config_diff": all(
                set(fields) <= allowed_core_fields for fields in config_differences.values()
            ),
            "remaining_run_cap_preserved": True,
            "capture_errors": capture_errors,
        },
        "error_count": len(capture_errors) + len(replay_errors),
        "nonfinite_count": sum(len(item["nonfinite"]) for item in profiles.values()),
        "overflow_count": sum(item["overflow_errors"] for item in profiles.values()),
        "formal_changed": False, "core_adopted": False,
    }
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with gzip.open(output / "w2500_checkpoint_states.pkl.gz", "wb") as handle:
        pickle.dump(captures, handle, protocol=pickle.HIGHEST_PROTOCOL)
    (output / "micro_core_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "micro_core_report.md").write_text(markdown(payload), encoding="utf-8")
    print(json.dumps({
        "report": str(output / "micro_core_report.md"),
        "json": str(output / "micro_core_summary.json"),
        "checkpoints": len(captures), "trial_ids_match": previous_ids == current_ids,
        "errors": payload["error_count"], "nonfinite": payload["nonfinite_count"],
        "overflow": payload["overflow_count"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
