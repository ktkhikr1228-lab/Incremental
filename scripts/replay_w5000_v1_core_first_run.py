#!/usr/bin/env python3
"""One-run-only paired replay of Exponential Core profiles from W2500."""

from __future__ import annotations

import argparse
import collections
import copy
import dataclasses
import gzip
import json
import math
import pickle
from pathlib import Path

import diagnose_w5000_v1_precore as diag
import replay_w5000_v1_micro_core_profiles as micro
import simulate_first_prestige_v1 as sim


CHECKPOINTS = (2750, 3000, 3250, 3500, 3750, 4000, 4500, 5000)
PROFILES = {
    "A_no_core": 0.0,
    "B_micro_core": 0.05,
    "C_low_core": 0.10,
    "D_medium_core": 0.20,
    "E_existing_weak": 1.0,
}


def replay_one(capture, label: str, scale: float, base: sim.SimConfig) -> dict:
    config = dataclasses.replace(
        micro.profile_config(base, scale), diagnostic_checkpoints=(2500,) + CHECKPOINTS,
    )
    no_core_config = dataclasses.replace(
        micro.profile_config(base, 0.0), diagnostic_checkpoints=(2500,) + CHECKPOINTS,
    )
    run = copy.deepcopy(capture["run"])
    permanent = copy.deepcopy(capture["permanent"])
    streams = micro.restore_streams(capture)
    if scale:
        run.counts["exponential_core"] = 1
        run.effect_version += 1

    direct_deltas: dict[int, float] = {}

    def checkpoint(wave, live_run, live_permanent, live_streams):
        candidate = sim.compute_snapshot(live_run, live_permanent, wave % 10 == 0, config)
        without_core = copy.deepcopy(live_run)
        without_core.counts.pop("exponential_core", None)
        without_core.effect_version += 1
        baseline = sim.compute_snapshot(
            without_core, live_permanent, wave % 10 == 0, no_core_config,
        )
        direct_deltas[wave] = candidate.log_dps - baseline.log_dps

    interaction_before = permanent.interaction_seconds
    result = sim.run_once(
        streams.combat,
        "balanced",
        permanent,
        config,
        True,
        initial_run=run,
        start_wave=2501,
        rng_streams=streams,
        checkpoint_capture=checkpoint,
    )
    checkpoints = {}
    for wave in CHECKPOINTS:
        state = result.checkpoint_states.get(wave)
        if state is None:
            continue
        checkpoints[str(wave)] = {
            "player_power": float(state["player_power"]),
            "enemy_power": float(state["enemy_power"]),
            "margin": float(state["margin_power"]),
            "core_exponent": micro.exponent_at(config, wave, bool(scale)),
            "direct_core_delta_power": direct_deltas[wave],
        }
    game_seconds = result.combat_seconds + permanent.interaction_seconds - interaction_before
    return {
        "trial": int(capture["trial"]),
        "profile": label,
        "first_run_max_wave": int(result.reached),
        "first_stop_wave": int(result.failure_wave if result.failure_wave is not None else 5000),
        "success": result.reached >= 5000,
        "game_hours_to_stop": game_seconds / 3600.0,
        "checkpoints": checkpoints,
    }


def summarize(rows: list[dict]) -> dict:
    checkpoint_summary = {}
    nonfinite = []
    for wave in CHECKPOINTS:
        reached = [row["checkpoints"][str(wave)] for row in rows if str(wave) in row["checkpoints"]]
        checkpoint_summary[str(wave)] = {
            "reached": len(reached),
            "reach_rate": len(reached) / len(rows),
            "margin": diag.dist([item["margin"] for item in reached]),
            "core_exponent": diag.dist([item["core_exponent"] for item in reached]),
            "direct_core_delta_power": diag.dist([
                item["direct_core_delta_power"] for item in reached
            ]),
        }
        for item in reached:
            if not all(math.isfinite(float(value)) for value in item.values()):
                nonfinite.append({"wave": wave, **item})
    return {
        "samples": len(rows),
        "first_run_max_wave": diag.dist([row["first_run_max_wave"] for row in rows]),
        "first_stop_waves": dict(sorted(collections.Counter(
            str(row["first_stop_wave"]) for row in rows
        ).items(), key=lambda item: int(item[0]))),
        "game_hours_to_stop": diag.dist([row["game_hours_to_stop"] for row in rows]),
        "checkpoints": checkpoint_summary,
        "nonfinite": nonfinite,
        "rows": rows,
    }


def add_paired_actual_deltas(profiles: dict) -> None:
    no_core = {
        row["trial"]: row for row in profiles["A_no_core"]["rows"]
    }
    for profile in profiles.values():
        for wave in CHECKPOINTS:
            values = []
            for row in profile["rows"]:
                baseline = no_core[row["trial"]]
                candidate_cp = row["checkpoints"].get(str(wave))
                baseline_cp = baseline["checkpoints"].get(str(wave))
                if candidate_cp is not None and baseline_cp is not None:
                    values.append(candidate_cp["player_power"] - baseline_cp["player_power"])
            profile["checkpoints"][str(wave)]["paired_actual_delta_vs_no_core"] = diag.dist(values)
            profile["checkpoints"][str(wave)]["paired_actual_delta_sample"] = len(values)


def fmt(value, digits=2):
    return "—" if value is None else f"{value:.{digits}f}"


def markdown(payload: dict) -> str:
    lines = [
        "# w5000_v1 Core first-run-only paired replay", "",
        f"W2500 saved states: {payload['state_count']} / seed {payload['seed']}", "",
        "W2500から開始した最初のRunだけを評価。死亡後のDP・再抽選・再挑戦は行わない。", "",
        "| Profile | Max Wave P25/P50/P75 | W2750 | W3000 | W3250 | W3500 | W3750 | W4000 | W4500 | W5000 | Stop time P50 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label in PROFILES:
        item = payload["profiles"][label]
        maximum = item["first_run_max_wave"]
        lines.append(
            f"| {label} | {fmt(maximum['p25'],1)}/{fmt(maximum['p50'],1)}/{fmt(maximum['p75'],1)} | "
            + " | ".join(f"{item['checkpoints'][str(wave)]['reach_rate']:.0%}" for wave in CHECKPOINTS)
            + f" | {fmt(item['game_hours_to_stop']['p50'],3)}h |"
        )
    lines += ["", "## Checkpoint detail", ""]
    for label in PROFILES:
        item = payload["profiles"][label]
        lines += [f"### {label}", "", "| W | Margin P25/P50/P75 | Exponent | Direct Core ΔPower P50 | Paired actual Δ P50 (n) |", "|---:|---:|---:|---:|---:|"]
        for wave in CHECKPOINTS:
            cp = item["checkpoints"][str(wave)]
            margin = cp["margin"]
            direct = cp["direct_core_delta_power"]
            paired = cp["paired_actual_delta_vs_no_core"]
            lines.append(
                f"| {wave} | {fmt(margin['p25'],3)}/{fmt(margin['p50'],3)}/{fmt(margin['p75'],3)} | "
                f"{fmt(cp['core_exponent']['p50'],4)} | {fmt(direct['p50'],3)} | "
                f"{fmt(paired['p50'],3)} ({cp['paired_actual_delta_sample']}) |"
            )
        lines += ["", "First stop waves: `" + json.dumps(item["first_stop_waves"], ensure_ascii=False) + "`", ""]
    lines += [
        "## Validation", "",
        f"- Core以外のconfig差分なし: {payload['validation']['only_core_config_diff']}",
        f"- 共通checkpoint state/RNG: {payload['validation']['paired_source_state_rng']}",
        f"- 後続Run実行なし: {payload['validation']['one_run_only']}",
        f"- error/nonfinite/overflow: {payload['error_count']}/{payload['nonfinite_count']}/{payload['overflow_count']}",
        "- 正式Core値・他バランス値の変更なし。", "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260828)
    parser.add_argument(
        "--states", type=Path,
        default=Path("output/w5000_v1_micro_core_10_states_final/w2500_checkpoint_states.pkl.gz"),
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("output/w5000_v1_core_first_run_10_states"),
    )
    args = parser.parse_args()
    with gzip.open(args.states, "rb") as handle:
        captures = pickle.load(handle)
    if len(captures) != 10:
        raise ValueError(f"expected 10 W2500 states, found {len(captures)}")

    base = dataclasses.replace(micro.base_config(140), diagnostic_checkpoints=(2500,) + CHECKPOINTS)
    profiles = {}
    errors = []
    for label, scale in PROFILES.items():
        rows = []
        for capture in captures.values():
            try:
                rows.append(replay_one(capture, label, scale, base))
            except Exception as exc:
                errors.append({
                    "profile": label, "trial": capture["trial"],
                    "type": type(exc).__name__, "message": str(exc),
                })
        profiles[label] = summarize(sorted(rows, key=lambda row: row["trial"]))
    add_paired_actual_deltas(profiles)

    reference = micro.profile_config(base, 0.0)
    config_differences = {}
    for label, scale in PROFILES.items():
        candidate = micro.profile_config(base, scale)
        config_differences[label] = [
            field.name for field in dataclasses.fields(sim.SimConfig)
            if getattr(reference, field.name) != getattr(candidate, field.name)
        ]
    allowed = {"exponential_core_guaranteed_wave", "exponential_core_growth_stages"}
    nonfinite_count = sum(len(item["nonfinite"]) for item in profiles.values())
    overflow_count = sum(error["type"] == "OverflowError" for error in errors)
    payload = {
        "seed": args.seed,
        "state_count": len(captures),
        "trial_ids": sorted(captures),
        "profile_definition": {
            label: {"weak_increment_scale": scale, "stages": micro.scaled_stages(scale)}
            for label, scale in PROFILES.items()
        },
        "common_conditions": {
            "dp": "v0.1", "boss_devourer": "base-heavy B",
            "w2500_guaranteed_legendary": False,
            "post_death_progression": False,
        },
        "profiles": profiles,
        "validation": {
            "paired_source_state_rng": True,
            "one_run_only": True,
            "config_differences_from_no_core": config_differences,
            "only_core_config_diff": all(set(fields) <= allowed for fields in config_differences.values()),
        },
        "errors": errors,
        "error_count": len(errors),
        "nonfinite_count": nonfinite_count,
        "overflow_count": overflow_count,
        "formal_changed": False,
        "core_adopted": False,
    }
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = output / "core_first_run_report.md"
    summary = output / "core_first_run_summary.json"
    report.write_text(markdown(payload), encoding="utf-8")
    summary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "report": str(report), "json": str(summary),
        "states": len(captures), "errors": len(errors),
        "nonfinite": nonfinite_count, "overflow": overflow_count,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
