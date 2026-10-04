#!/usr/bin/env python3
"""30-pair Exponential Core comparison on the current w5000_v1 candidate."""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import copy
import dataclasses
import json
import math
import statistics
from pathlib import Path
from typing import Any

import diagnose_w5000_v1_precore as diag
import simulate_first_prestige_v1 as sim
import w5000_v1_profile as profile


PROFILE_MAP = {
    "A_no_core": "no_core",
    "B_weak": "three_stage_weaker",
    "C_baseline": "three_stage_candidate",
    "D_strong": "three_stage_stronger",
}
CHECKPOINTS = tuple(range(2500, 5001, 250))
CORE_FIELDS = {
    "exponential_core_guaranteed_wave", "exponential_core_growth_stages",
}


def make_configs(max_attempts: int) -> dict[str, sim.SimConfig]:
    return {
        label: dataclasses.replace(
            profile.build_config(
                max_attempts=max_attempts,
                core_profile=core_name,
                guaranteed_legendary=False,
            ),
            diagnostic_checkpoints=CHECKPOINTS,
            dp_v01=sim.DPV01Config(enabled=True),
            diagnostic_boss_devourer_growth_multiplier=0.75,
            diagnostic_boss_devourer_base_power=6.0,
        )
        for label, core_name in PROFILE_MAP.items()
    }


def state_signature(run: sim.RunState, permanent: sim.PermanentState) -> dict[str, Any]:
    return {"run": dataclasses.asdict(run), "permanent": dataclasses.asdict(permanent)}


def execute_profile(args):
    label, config, trials, seed = args
    completed = []
    errors = []
    for trial in range(trials):
        capture: dict[str, Any] = {}

        def pre_reward(wave, run, permanent, streams):
            if wave != 2500 or capture:
                return
            capture["state"] = copy.deepcopy(state_signature(run, permanent))
            capture["rng"] = {
                name: copy.deepcopy(getattr(streams, name).getstate())
                for name in ("card", "weapon", "relic", "combat")
            }

        try:
            streams = sim.make_split_rng_streams(seed, trial)
            result = sim.run_trial(
                streams.combat, "balanced", config, True,
                rng_streams=streams,
                pre_reward_checkpoint_capture=pre_reward,
            )
            completed.append((trial, result, capture))
        except Exception as exc:
            errors.append({
                "profile": label, "trial": trial,
                "type": type(exc).__name__, "message": str(exc),
            })
    return label, completed, errors


def dist(values):
    return diag.dist([float(value) for value in values])


def exponent_at(core_name: str, wave: int) -> float:
    config = profile.build_config(core_profile=core_name)
    run = sim.RunState(kills=wave)
    if profile.CORE_PROFILES[core_name].enabled and wave >= 2500:
        run.counts["exponential_core"] = 1
    return sim.exponential_core_exponent(run, config)


def first_stop_band(wave: int) -> str:
    if wave >= 5000:
        return "success"
    start = max(2500, (wave // 250) * 250)
    return f"{start}-{start + 249}"


def summarize(label, rows, errors, config, trials):
    reached_2500 = [(trial, row, capture) for trial, row, capture in rows if 2500 in row.reach_seconds]
    denominator = len(reached_2500)
    checkpoints = {}
    nonfinite = []
    for wave in CHECKPOINTS:
        states = [row.first_reach_checkpoint_states[wave] for _, row, _ in rows if wave in row.reach_seconds]
        player = [float(state["player_power"]) for state in states]
        enemy = [float(state["enemy_power"]) for state in states]
        margin = [float(state["margin_power"]) for state in states]
        exponent = exponent_at(PROFILE_MAP[label], wave)
        checkpoints[str(wave)] = {
            "reached": len(states),
            "reach_rate_all": len(states) / trials,
            "reach_rate_conditional_w2500": len(states) / denominator if denominator else None,
            "player_power": dist(player), "enemy_power": dist(enemy),
            "margin": dist(margin),
            "core_exponent": dist([exponent] * len(states)),
        }
        for index, values in enumerate(zip(player, enemy, margin)):
            if not all(math.isfinite(value) for value in values) or not math.isfinite(exponent):
                nonfinite.append({"wave": wave, "index": index, "values": values, "exponent": exponent})
    progression = []
    stop_bands = collections.Counter()
    for trial, row, _ in reached_2500:
        first_index = next(i for i, wave in enumerate(row.run_reaches) if wave >= 2500)
        post = row.run_reaches[first_index:]
        same_run = post[0]
        stop_bands[first_stop_band(same_run)] += 1
        total_time = row.total_combat_seconds + row.total_interaction_seconds
        progression.append({
            "trial": trial,
            "final_highest_wave": max(post),
            "post_w2500_runs": len(post),
            "post_w2500_deaths": sum(wave < 5000 for wave in post),
            "post_w2500_game_hours": (total_time - row.reach_seconds[2500]) / 3600.0,
            "same_run_reached_wave": same_run,
            "first_stop_band": first_stop_band(same_run),
            "final_core_exponent": exponent_at(PROFILE_MAP[label], max(post)),
        })
    jumps = {}
    for start, end in ((2500, 2750), (3000, 3500), (4000, 4500), (4500, 5000)):
        left, right = checkpoints[str(start)], checkpoints[str(end)]
        jumps[f"{start}-{end}"] = {
            "player_power_p50_delta": (
                right["player_power"]["p50"] - left["player_power"]["p50"]
                if right["player_power"]["p50"] is not None and left["player_power"]["p50"] is not None else None
            ),
            "enemy_power_p50_delta": (
                right["enemy_power"]["p50"] - left["enemy_power"]["p50"]
                if right["enemy_power"]["p50"] is not None and left["enemy_power"]["p50"] is not None else None
            ),
        }
    return {
        "completed": len(rows), "w2500_sample": denominator,
        "checkpoints": checkpoints,
        "progression": {
            "final_highest_wave": dist([item["final_highest_wave"] for item in progression]),
            "post_w2500_runs": dist([item["post_w2500_runs"] for item in progression]),
            "post_w2500_deaths": dist([item["post_w2500_deaths"] for item in progression]),
            "post_w2500_game_hours": dist([item["post_w2500_game_hours"] for item in progression]),
            "same_run_reached_wave": dist([item["same_run_reached_wave"] for item in progression]),
            "first_stop_bands": dict(sorted(stop_bands.items())),
            "final_core_exponent": dist([item["final_core_exponent"] for item in progression]),
            "trials": progression,
        },
        "power_jumps": jumps,
        "big_boss_exponent_progression": {
            str(wave): exponent_at(PROFILE_MAP[label], wave)
            for wave in range(2500, 5001, 100)
        },
        "nonfinite": nonfinite, "errors": errors,
        "overflow_errors": sum(item["type"] == "OverflowError" for item in errors),
    }


def normalized_config(config):
    values = dataclasses.asdict(config)
    return {key: value for key, value in values.items() if key not in CORE_FIELDS}


def paired_invariants(results, configs, trials):
    labels = list(PROFILE_MAP)
    config_match = all(
        normalized_config(configs[label]) == normalized_config(configs[labels[0]])
        for label in labels[1:]
    )
    mismatches = []
    for trial in range(trials):
        captures = []
        times = []
        reached = []
        for label in labels:
            mapping = {item[0]: item for item in results[label]}
            if trial not in mapping:
                captures.append(None); times.append(None); reached.append(False)
                continue
            _, row, capture = mapping[trial]
            reached.append(2500 in row.reach_seconds)
            times.append(row.reach_seconds.get(2500))
            captures.append(capture or None)
        available_states = [item.get("state") for item in captures if item]
        state_equal = (
            not available_states
            or all(item == available_states[0] for item in available_states[1:])
        )
        rng_equal = len({repr(item.get("rng")) for item in captures if item}) <= 1
        time_equal = len(set(times)) <= 1
        reach_equal = len(set(reached)) <= 1
        if not (state_equal and rng_equal and time_equal and reach_equal):
            differing_state_keys = []
            if len(available_states) > 1:
                reference = available_states[0]
                for section in ("run", "permanent"):
                    for key in reference[section]:
                        if any(
                            item[section][key] != reference[section][key]
                            for item in available_states[1:]
                        ):
                            differing_state_keys.append(f"{section}.{key}")
            mismatches.append({
                "trial": trial, "reached": reached, "times": times,
                "state_equal": state_equal, "rng_equal": rng_equal,
                "differing_state_keys": differing_state_keys,
            })
    return {
        "non_core_config_match": config_match,
        "w2500_pre_reward_state_time_rng_match": not mismatches,
        "mismatches": mismatches,
        "seed_formula": "split RNG streams from base seed and trial index",
    }


def fmt(value, digits=1):
    return "—" if value is None else f"{value:.{digits}f}"


def markdown(payload):
    lines = [
        "# w5000_v1 Exponential Core 30-pair comparison", "",
        f"DP v0.1 / Boss Devourer base-heavy B / W2500 guaranteed Legendary OFF / seed {payload['seed']}", "",
        "Core係数は既存profileを無変更で使用。", "",
        "| Profile | W2500 sample | W2750 | W3000 | W3500 | W4000 | W4500 | W5000 | conditional W5000 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label in PROFILE_MAP:
        item = payload["profiles"][label]
        cp = item["checkpoints"]
        lines.append(
            f"| {label} | {item['w2500_sample']} | "
            + " | ".join(f"{cp[str(w)]['reach_rate_all']:.1%}" for w in (2750, 3000, 3500, 4000, 4500, 5000))
            + f" | {fmt(cp['5000']['reach_rate_conditional_w2500'] * 100 if cp['5000']['reach_rate_conditional_w2500'] is not None else None)}% |"
        )
    lines += [
        "", "## All / conditional reach rates", "",
        "各セルは全trial基準 / W2500到達trial基準。", "",
        "| W | " + " | ".join(PROFILE_MAP) + " |",
        "|---:|" + "---:|" * len(PROFILE_MAP),
    ]
    for wave in CHECKPOINTS:
        cells = []
        for label in PROFILE_MAP:
            cp = payload["profiles"][label]["checkpoints"][str(wave)]
            conditional = cp["reach_rate_conditional_w2500"]
            cells.append(f"{cp['reach_rate_all']:.1%}/{fmt(conditional * 100 if conditional is not None else None)}%")
        lines.append(f"| {wave} | " + " | ".join(cells) + " |")
    lines += [
        "", "## Post-W2500 progression", "",
        "| Profile | Final Wave P25/P50/P75 | Runs P50 | Deaths P50 | Hours P50 | Same-run Wave P50 | Final exponent P50 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label in PROFILE_MAP:
        x = payload["profiles"][label]["progression"]
        final = x["final_highest_wave"]
        lines.append(
            f"| {label} | {fmt(final['p25'])}/{fmt(final['p50'])}/{fmt(final['p75'])} | "
            f"{fmt(x['post_w2500_runs']['p50'])} | {fmt(x['post_w2500_deaths']['p50'])} | "
            f"{fmt(x['post_w2500_game_hours']['p50'],3)} | {fmt(x['same_run_reached_wave']['p50'])} | "
            f"{fmt(x['final_core_exponent']['p50'],3)} |"
        )
    lines += ["", "## Checkpoint Power P50 (Player / Enemy / Margin / Exponent)", ""]
    for label in PROFILE_MAP:
        lines += [f"### {label}", "", "| W | Player | Enemy | Margin | Exponent |", "|---:|---:|---:|---:|---:|"]
        for wave in CHECKPOINTS:
            cp = payload["profiles"][label]["checkpoints"][str(wave)]
            lines.append(
                f"| {wave} | {fmt(cp['player_power']['p50'],3)} | {fmt(cp['enemy_power']['p50'],3)} | "
                f"{fmt(cp['margin']['p50'],3)} | {fmt(cp['core_exponent']['p50'],3)} |"
            )
        lines += ["", "First-stop bands: `" + json.dumps(payload["profiles"][label]["progression"]["first_stop_bands"], ensure_ascii=False) + "`", ""]
    lines += [
        "## Power jump audit", "",
        "Player Δ / Enemy Δ。到達者集合がcheckpointごとに異なる点に注意。", "",
        "| Profile | 2500→2750 | 3000→3500 | 4000→4500 | 4500→5000 |",
        "|---|---:|---:|---:|---:|",
    ]
    for label in PROFILE_MAP:
        jumps = payload["profiles"][label]["power_jumps"]
        cells = [
            f"{fmt(jumps[key]['player_power_p50_delta'],2)}/{fmt(jumps[key]['enemy_power_p50_delta'],2)}"
            for key in ("2500-2750", "3000-3500", "4000-4500", "4500-5000")
        ]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    inv = payload["paired_invariants"]
    lines += [
        "", "## Validation", "",
        f"- Core以外のconfig一致: {inv['non_core_config_match']}",
        f"- W2500報酬前state/time/RNG一致: {inv['w2500_pre_reward_state_time_rng_match']}",
        f"- errors/nonfinite/overflow: {payload['error_count']}/{payload['nonfinite_count']}/{payload['overflow_count']}",
        "- Core正式採用・係数変更なし。", "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--seed", type=int, default=sim.SEED)
    parser.add_argument("--max-attempts", type=int, default=140)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output-dir", type=Path, default=Path("output/w5000_v1_core_profiles_current_30"))
    args = parser.parse_args()
    if not 1 <= args.trials <= 30:
        parser.error("comparison is limited to 1..30 paired trials")
    configs = make_configs(args.max_attempts)
    tasks = [(label, config, args.trials, args.seed) for label, config in configs.items()]
    results, errors = {}, {}
    with concurrent.futures.ProcessPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for label, rows, task_errors in pool.map(execute_profile, tasks):
            results[label] = rows
            errors[label] = task_errors
    profiles = {
        label: summarize(label, results[label], errors[label], configs[label], args.trials)
        for label in PROFILE_MAP
    }
    payload = {
        "trials": args.trials, "seed": args.seed, "max_attempts": args.max_attempts,
        "core_profiles": {
            label: dataclasses.asdict(profile.CORE_PROFILES[name])
            for label, name in PROFILE_MAP.items()
        },
        "common_conditions": {
            "dp": "v0.1 candidate", "boss_devourer": "base-heavy B: growth 75%, fixed +6 Power",
            "guaranteed_legendary_w2500": False, "enemy_curve": "w5000_v1",
        },
        "paired_invariants": paired_invariants(results, configs, args.trials),
        "profiles": profiles,
        "error_count": sum(len(value) for value in errors.values()),
        "nonfinite_count": sum(len(item["nonfinite"]) for item in profiles.values()),
        "overflow_count": sum(item["overflow_errors"] for item in profiles.values()),
        "formal_changed": False, "core_adopted": False,
    }
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "w5000_v1_core_profiles_current_30.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "w5000_v1_core_profiles_current_30.md").write_text(markdown(payload), encoding="utf-8")
    print(json.dumps({
        "report": str(output / "w5000_v1_core_profiles_current_30.md"),
        "json": str(output / "w5000_v1_core_profiles_current_30.json"),
        "w2500_samples": {label: item["w2500_sample"] for label, item in profiles.items()},
        "paired_invariants": payload["paired_invariants"],
        "errors": payload["error_count"], "nonfinite": payload["nonfinite_count"],
        "overflow": payload["overflow_count"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
