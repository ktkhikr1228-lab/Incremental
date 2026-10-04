#!/usr/bin/env python3
"""Diagnose how much legacy Infinite Barrage contributed before/after W2500."""

from __future__ import annotations

import argparse
import collections
import copy
import dataclasses
import gzip
import json
import math
import pickle
import statistics
from pathlib import Path

import diagnose_w5000_v1_precore as diag
import experiment_w5000_v1_integrated_core_dp as integrated
import experiment_w5000_v1_unlimited_boost_v02 as boost_v02
import replay_w5000_v1_micro_core_profiles as core
import simulate_first_prestige_v1 as sim


CHECKPOINTS = (500, 750, 1000, 1250, 1500, 1750, 2000, 2250, 2500)
TRIALS_DEFAULT = 30
SEED_DEFAULT = 20260828
MAX_ATTEMPTS = 140
DP_SCALE = 0.10
CORE_SCALE = 0.15
PROFILES = {
    "A_old_barrage_37_5": "legacy",
    "B_barrage_v2_fixed_ratio": "v2_fixed_ratio",
}


def percentile(values: list[float], q: float) -> float | None:
    return diag.percentile(values, q) if values else None


def fmt(value, digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def rarity_counts(run: sim.RunState) -> dict[str, int]:
    rarity_by_key = {card.key: card.rarity for card in sim.CARDS}
    values = collections.Counter()
    for key, count in run.counts.items():
        if count > 0 and key in rarity_by_key:
            values[rarity_by_key[key]] += count
    return {rarity: values.get(rarity, 0) for rarity in sim.RARITY_ORDER}


def checkpoint_diagnostic(
    run: sim.RunState,
    permanent: sim.PermanentState,
    wave: int,
    config: sim.SimConfig,
) -> dict:
    boss = wave % 10 == 0
    snapshot = sim.compute_snapshot(run, permanent, boss, config)
    no_barrage = sim.compute_snapshot(
        run,
        permanent,
        boss,
        dataclasses.replace(
            config,
            diagnostic_suppressed_card_keys=(
                config.diagnostic_suppressed_card_keys | frozenset({"infinite_barrage"})
            ),
        ),
    )
    no_devourer = sim.compute_snapshot(
        run,
        permanent,
        boss,
        dataclasses.replace(config, diagnostic_suppress_boss_devourer=True),
    )
    return {
        "trial_wave": wave,
        "margin": snapshot.log_dps - sim.configured_enemy_power(wave, config),
        "player_power": snapshot.log_dps,
        "enemy_power": sim.configured_enemy_power(wave, config),
        "barrage_power": snapshot.log_dps - no_barrage.log_dps,
        "attack_speed": snapshot.attack_speed,
        "dp_power": snapshot.dp_power,
        "boss_devourer_power": snapshot.log_dps - no_devourer.log_dps,
        "weapon_power": snapshot.weapon_power,
        "relic_power": snapshot.relic_power,
        "card_count": run.card_count,
        "rarity": rarity_counts(run),
    }


def make_pre_config() -> sim.SimConfig:
    # W1-W2500 is common. A temporary target stops the run immediately after
    # capturing W2500; enemy/progression anchors remain the w5000_v1 values.
    return dataclasses.replace(
        core.base_config(MAX_ATTEMPTS),
        target_wave=2500,
        diagnostic_checkpoints=CHECKPOINTS,
        unlimited_boost=boost_v02.v02_config(),
        finale=sim.FinaleConfig(enabled=True),
        diagnostic_infinite_barrage_strength=0.375,
    )


def run_common_prefix(trials: int, seed: int):
    config = make_pre_config()
    results = {}
    captures = {}
    checkpoints = {trial: {} for trial in range(trials)}
    errors = []
    for trial in range(trials):
        streams = sim.make_split_rng_streams(seed, trial)

        def capture(attempt, wave, run, permanent, live_streams, *, _trial=trial):
            checkpoints[_trial].setdefault(
                wave,
                {
                    "run": copy.deepcopy(run),
                    "permanent": copy.deepcopy(permanent),
                },
            )
            if wave == 2500 and _trial not in captures:
                captures[_trial] = {
                    "trial": _trial,
                    "attempt": attempt,
                    "wave": wave,
                    "run": copy.deepcopy(run),
                    "permanent": copy.deepcopy(permanent),
                    "rng_states": {
                        name: copy.deepcopy(getattr(live_streams, name).getstate())
                        for name in ("card", "weapon", "relic", "combat")
                    },
                }

        try:
            results[trial] = sim.run_trial(
                streams.combat,
                "balanced",
                config,
                True,
                rng_streams=streams,
                attempt_checkpoint_capture=capture,
            )
        except Exception as exc:
            errors.append({
                "trial": trial,
                "type": type(exc).__name__,
                "message": str(exc),
            })
    return config, results, captures, checkpoints, errors


def replay_profiles(captures: dict[int, dict]):
    grouped = {label: {} for label in PROFILES}
    errors = []
    for label, mode in PROFILES.items():
        for trial, capture in captures.items():
            try:
                grouped[label][trial] = integrated.replay_one(
                    capture,
                    label,
                    DP_SCALE,
                    CORE_SCALE,
                    unlimited_boost_config=boost_v02.v02_config(),
                    finale_config=sim.FinaleConfig(enabled=True),
                    diagnostic_checkpoints=(4000,),
                    barrage_strength=0.375,
                    barrage_mode=mode,
                )
            except Exception as exc:
                errors.append({
                    "profile": label,
                    "trial": trial,
                    "type": type(exc).__name__,
                    "message": str(exc),
                })
    return grouped, errors


def death_band(wave: int) -> str:
    low = (wave // 250) * 250
    return f"{low}-{low + 249}"


def reattainment_rate(waves: list[int], threshold: int = 1500) -> float | None:
    first = next((index for index, wave in enumerate(waves) if wave >= threshold), None)
    if first is None or first + 1 >= len(waves):
        return None
    later = waves[first + 1:]
    return sum(wave >= threshold for wave in later) / len(later)


def summarize_profile(
    label: str,
    mode: str,
    common_config: sim.SimConfig,
    common_results: dict,
    captures: dict,
    checkpoint_captures: dict,
    replay_rows: dict,
) -> dict:
    profile_config = dataclasses.replace(
        common_config,
        diagnostic_infinite_barrage_mode=mode,
        diagnostic_infinite_barrage_strength=0.375,
    )
    checkpoint_rows: dict[int, list[dict]] = {wave: [] for wave in CHECKPOINTS}
    for trial, by_wave in checkpoint_captures.items():
        for wave, captured in by_wave.items():
            checkpoint_rows[wave].append(
                checkpoint_diagnostic(
                    captured["run"], captured["permanent"], wave, profile_config
                )
            )

    trial_rows = []
    all_deaths = []
    for trial, result in common_results.items():
        prefix_waves = list(result.run_reaches)
        prefix_deaths = [
            int(state["failure_wave"])
            for state in result.run_end_states
            if state["failure_wave"] is not None
        ]
        replay = replay_rows.get(trial)
        suffix_waves = [int(row["max_wave"]) for row in replay["run_rows"]] if replay else []
        suffix_deaths = [
            int(row["failure_wave"])
            for row in replay["run_rows"]
            if row["failure_wave"] is not None
        ] if replay else []
        # The common prefix's last run reaches W2500 and is continued by replay.
        combined_waves = prefix_waves[:-1] + suffix_waves if replay else prefix_waves
        death_waves = prefix_deaths + suffix_deaths
        all_deaths.extend(death_waves)
        best = max(combined_waves) if combined_waves else 0
        recent = statistics.median(combined_waves[-10:]) if combined_waves else 0.0
        trial_rows.append({
            "trial": trial,
            "highest_wave": best,
            "w2500": trial in captures,
            "w4000": bool(replay and "4000" in replay["checkpoints"]),
            "w1500_reattainment_rate": reattainment_rate(combined_waves),
            "best_minus_recent10_median": best - recent,
            "run_waves": combined_waves,
            "death_waves": death_waves,
        })

    checkpoint_summary = {}
    for wave, rows in checkpoint_rows.items():
        checkpoint_summary[str(wave)] = {
            "reached": len(rows),
            "reach_rate": len(rows) / len(common_results),
            "margin": diag.dist([row["margin"] for row in rows]),
            "barrage_power": diag.dist([row["barrage_power"] for row in rows]),
            "attack_speed": diag.dist([row["attack_speed"] for row in rows]),
            "dp_power": diag.dist([row["dp_power"] for row in rows]),
            "boss_devourer_power": diag.dist([
                row["boss_devourer_power"] for row in rows
            ]),
            "weapon_power": diag.dist([row["weapon_power"] for row in rows]),
            "relic_power": diag.dist([row["relic_power"] for row in rows]),
            "card_count": diag.dist([row["card_count"] for row in rows]),
            "rarity": {
                rarity: diag.dist([row["rarity"][rarity] for row in rows])
                for rarity in sim.RARITY_ORDER
            },
        }
    reattainment = [
        row["w1500_reattainment_rate"]
        for row in trial_rows if row["w1500_reattainment_rate"] is not None
    ]
    return {
        "checkpoints": checkpoint_summary,
        "highest_wave": diag.dist([row["highest_wave"] for row in trial_rows]),
        "death_wave_histogram": dict(sorted(collections.Counter(
            death_band(wave) for wave in all_deaths
        ).items(), key=lambda item: int(item[0].split("-")[0]))),
        "w1500_reattainment_rate": (
            sum(reattainment) / len(reattainment) if reattainment else None
        ),
        "w1500_reattainment_trials": len(reattainment),
        "best_minus_recent10_median": diag.dist([
            row["best_minus_recent10_median"] for row in trial_rows
        ]),
        "w2500_reached": sum(row["w2500"] for row in trial_rows),
        "w2500_rate": sum(row["w2500"] for row in trial_rows) / len(trial_rows),
        "w4000_reached": sum(row["w4000"] for row in trial_rows),
        "w4000_rate": sum(row["w4000"] for row in trial_rows) / len(trial_rows),
        "trial_rows": trial_rows,
    }


def markdown(payload: dict) -> str:
    lines = [
        "# Old Infinite Barrage vs v2 midgame diagnosis",
        "",
        f"{payload['trials']} paired trials / seed {payload['seed']}. Other baseline values are unchanged.",
        "",
        "## Reach and Power",
        "",
        "| W | Reach | Old Margin P25/P50/P75 | v2 Margin P25/P50/P75 | Old Barrage P50 | v2 Barrage P50 | Difference | AS P50 | DP P50 | Devourer P50 | Weapon P50 | Relic P50 | Cards P50 | C/U/R/E/L P50 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    old = payload["profiles"]["A_old_barrage_37_5"]
    v2 = payload["profiles"]["B_barrage_v2_fixed_ratio"]
    for wave in CHECKPOINTS:
        a = old["checkpoints"][str(wave)]
        b = v2["checkpoints"][str(wave)]
        am, bm = a["margin"], b["margin"]
        ap, bp = a["barrage_power"]["p50"], b["barrage_power"]["p50"]
        rarities = "/".join(
            fmt(a["rarity"][rarity]["p50"], 0) for rarity in sim.RARITY_ORDER
        )
        lines.append(
            f"| {wave} | {a['reach_rate']:.0%}"
            f" | {fmt(am['p25'])}/{fmt(am['p50'])}/{fmt(am['p75'])}"
            f" | {fmt(bm['p25'])}/{fmt(bm['p50'])}/{fmt(bm['p75'])}"
            f" | {fmt(ap,3)} | {fmt(bp,3)} | {fmt((ap or 0)-(bp or 0),3)}"
            f" | {fmt(a['attack_speed']['p50'])} | {fmt(a['dp_power']['p50'])}"
            f" | {fmt(a['boss_devourer_power']['p50'])}"
            f" | {fmt(a['weapon_power']['p50'])} | {fmt(a['relic_power']['p50'])}"
            f" | {fmt(a['card_count']['p50'],0)} | {rarities} |"
        )
    lines += [
        "",
        "## Overall",
        "",
        "| Profile | Highest P25/P50/P75 | W1500 reattainment | Best-recent10 P50 | W2500 | W4000 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, item in payload["profiles"].items():
        highest = item["highest_wave"]
        lines.append(
            f"| {label} | {fmt(highest['p25'],0)}/{fmt(highest['p50'],0)}/{fmt(highest['p75'],0)}"
            f" | {fmt(100 * item['w1500_reattainment_rate'],1) if item['w1500_reattainment_rate'] is not None else '—'}%"
            f" | {fmt(item['best_minus_recent10_median']['p50'],1)}"
            f" | {item['w2500_reached']}/{payload['trials']}"
            f" | {item['w4000_reached']}/{payload['trials']} |"
        )
    lines += ["", "## Death Wave histogram", ""]
    for label, item in payload["profiles"].items():
        lines.append(f"- {label}: `{json.dumps(item['death_wave_histogram'])}`")
    lines += [
        "",
        "## Validation",
        "",
        f"- errors/nonfinite/overflow: {payload['error_count']}/{payload['nonfinite_count']}/{payload['overflow_count']}",
        f"- W500-W2500 checkpoint payloads identical except Barrage mode: {payload['pre2500_non_barrage_fields_identical']}",
        "- Infinite Barrage unlock is W2500; it cannot supply Power at W500-W2250.",
        "- No compensation or new balance candidate was added.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=TRIALS_DEFAULT)
    parser.add_argument("--seed", type=int, default=SEED_DEFAULT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/w5000_v1_old_vs_v2_midgame_30"),
    )
    args = parser.parse_args()
    common_config, common_results, captures, checkpoint_captures, prefix_errors = (
        run_common_prefix(args.trials, args.seed)
    )
    replay_rows, replay_errors = replay_profiles(captures)
    profiles = {
        label: summarize_profile(
            label,
            mode,
            common_config,
            common_results,
            captures,
            checkpoint_captures,
            replay_rows[label],
        )
        for label, mode in PROFILES.items()
    }
    old_cp = profiles["A_old_barrage_37_5"]["checkpoints"]
    v2_cp = profiles["B_barrage_v2_fixed_ratio"]["checkpoints"]
    non_barrage_identical = all(
        {
            key: value for key, value in old_cp[str(wave)].items()
            if key != "barrage_power"
        } == {
            key: value for key, value in v2_cp[str(wave)].items()
            if key != "barrage_power"
        }
        for wave in CHECKPOINTS
    )
    errors = prefix_errors + replay_errors
    nonfinite = 0
    for rows in replay_rows.values():
        nonfinite += sum(len(row["nonfinite"]) for row in rows.values())
    payload = {
        "trials": args.trials,
        "seed": args.seed,
        "w2500_capture_count": len(captures),
        "profiles": profiles,
        "pre2500_non_barrage_fields_identical": non_barrage_identical,
        "error_count": len(errors),
        "nonfinite_count": nonfinite,
        "overflow_count": sum(error["type"] == "OverflowError" for error in errors),
        "errors": errors,
        "formal_changed": False,
        "balance_adopted": False,
    }
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "old_vs_v2_midgame_summary.json"
    report_path = output / "old_vs_v2_midgame_report.md"
    states_path = output / "w2500_states.pkl.gz"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(markdown(payload), encoding="utf-8")
    with gzip.open(states_path, "wb") as handle:
        pickle.dump(captures, handle)
    print(json.dumps({
        "report": str(report_path),
        "json": str(json_path),
        "states": str(states_path),
        "trials": args.trials,
        "w2500_captures": len(captures),
        "errors": len(errors),
        "nonfinite": nonfinite,
        "overflow": payload["overflow_count"],
        "pre2500_non_barrage_fields_identical": non_barrage_identical,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
