#!/usr/bin/env python3
"""Read-only balance diagnosis for the W5000 v1 pre-Core progression."""

from __future__ import annotations

import argparse
import collections
import dataclasses
import json
import math
import random
from pathlib import Path
from typing import Any

import simulate_first_prestige_v1 as sim
import w5000_v1_profile as profile


CHECKPOINTS = (100, 250, 500, 750, 1000, 1250, 1500, 1750, 2000, 2250, 2500)


def dist(values: list[float]) -> dict[str, float | None]:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    return {
        "count": len(finite),
        "p25": sim.percentile(finite, 0.25) if finite else None,
        "p50": sim.percentile(finite, 0.50) if finite else None,
        "p75": sim.percentile(finite, 0.75) if finite else None,
        "min": min(finite) if finite else None,
        "max": max(finite) if finite else None,
    }


def numeric_state_summary(states: list[dict[str, object]]) -> dict[str, dict[str, float | None]]:
    keys: set[str] = set()
    for state in states:
        keys.update(
            key for key, value in state.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        )
    return {
        key: dist([float(state[key]) for state in states if key in state])
        for key in sorted(keys)
    }


def band_label(wave: int) -> str:
    lo = (wave // 100) * 100
    return f"{lo}-{lo + 99}"


def fmt(value: float | None, digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# w5000_v1 W2500前ボトルネック診断",
        "",
        f"no_core / Standard bot / {payload['requested_trials']} trials / seed {payload['seed']} / "
        f"max attempts {payload['max_attempts']}",
        "",
        "## 到達状況",
        "",
        "| W | 到達率 | Margin Power P25/P50/P75 | DP Lv P50 (ATK/AS/XP) | Base Power | AS | XP | Weapon所持 | Weapon Power | Relic Power |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for wave in CHECKPOINTS:
        item = payload["checkpoints"][str(wave)]
        states = item["state"]
        def p50(key: str) -> float | None:
            return states.get(key, {}).get("p50")
        margin = states.get("margin_power", {})
        dp = f"{fmt(p50('dp_total_level'), 1)} ({fmt(p50('dp_atk_level'), 1)}/{fmt(p50('dp_as_level'), 1)}/{fmt(p50('dp_xp_level'), 1)})"
        lines.append(
            f"| {wave} | {item['reach_rate']:.1%} | "
            f"{fmt(margin.get('p25'))}/{fmt(margin.get('p50'))}/{fmt(margin.get('p75'))} | "
            f"{dp} | {fmt(p50('base_attack_power'))} | {fmt(p50('attack_speed'))} | "
            f"{fmt(p50('xp_multiplier'))} | {item['weapon_owned_rate']:.1%} | "
            f"{fmt(p50('weapon_power'))} | {fmt(p50('relic_power'))} |"
        )
    deaths = payload["deaths"]
    lines += [
        "",
        "## Trial終了状況",
        "",
        f"- Deaths P25/P50/P75: {fmt(deaths['p25'], 1)} / {fmt(deaths['p50'], 1)} / {fmt(deaths['p75'], 1)}",
        f"- 最大Run数到達: {payload['max_attempts_reached']} / {payload['requested_trials']}",
        f"- nonfinite: {len(payload['nonfinite'])}",
        f"- errors: {len(payload['errors'])}",
        "",
        "### 最高Wave（trial別）",
        "",
        "| Trial | Highest Wave | Final death Wave | Deaths | Attempts |",
        "|---:|---:|---:|---:|---:|",
    ]
    for row in payload["trials"]:
        lines.append(
            f"| {row['trial']} | {row['highest_wave']} | {row['final_death_wave']} | "
            f"{row['deaths']} | {row['attempts']} |"
        )
    lines += ["", "### 最終死亡Wave帯", "", "| Wave帯 | trials |", "|---:|---:|"]
    for band, count in payload["final_death_wave_bands"].items():
        lines.append(f"| {band} | {count} |")
    lines += [
        "",
        "本レポートは停止地点の診断のみ。Core係数・DP・Weapon・Relic・敵曲線等のバランス値は変更していない。",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--seed", type=int, default=sim.SEED)
    parser.add_argument("--max-attempts", type=int, default=140)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("output/w5000_v1_precore_bottleneck_30")
    )
    args = parser.parse_args()
    if not 1 <= args.trials <= 30:
        parser.error("pre-Core diagnosis is limited to 1-30 trials")

    config = dataclasses.replace(
        profile.build_config(max_attempts=args.max_attempts, core_profile="no_core"),
        diagnostic_checkpoints=CHECKPOINTS,
    )
    rows: list[sim.TrialResult] = []
    errors: list[dict[str, object]] = []
    for trial in range(args.trials):
        try:
            rng = random.Random(args.seed + 1_000_000 + trial)
            rows.append(sim.run_trial(rng, "balanced", config, allow_overdrive=True))
        except Exception as exc:  # preserve partial diagnostics instead of hiding a bad trial
            errors.append({"trial": trial, "type": type(exc).__name__, "message": str(exc)})

    trial_rows: list[dict[str, object]] = []
    nonfinite: list[dict[str, object]] = []
    for trial, row in enumerate(rows):
        highest = max(row.run_reaches) if row.run_reaches else 0
        final_wave = row.run_reaches[-1] if row.run_reaches else 0
        trial_rows.append({
            "trial": trial,
            "highest_wave": highest,
            "final_death_wave": None if row.success else final_wave,
            "deaths": row.deaths,
            "attempts": row.attempts,
            "success": row.success,
        })
        scalar_values = {
            "total_combat_seconds": row.total_combat_seconds,
            "total_interaction_seconds": row.total_interaction_seconds,
        }
        for key, value in scalar_values.items():
            if not math.isfinite(float(value)):
                nonfinite.append({"trial": trial, "field": key, "value": value})
        for wave, state in row.first_reach_checkpoint_states.items():
            for key, value in state.items():
                if isinstance(value, float) and not math.isfinite(value):
                    nonfinite.append({"trial": trial, "wave": wave, "field": key, "value": value})

    checkpoints: dict[str, object] = {}
    for wave in CHECKPOINTS:
        reached_rows = [row for row in rows if wave in row.reach_seconds]
        states = [
            row.first_reach_checkpoint_states[wave]
            for row in reached_rows
            if wave in row.first_reach_checkpoint_states
        ]
        checkpoints[str(wave)] = {
            "reached": len(reached_rows),
            "reach_rate": len(reached_rows) / args.trials,
            "state_records": len(states),
            "state": numeric_state_summary(states),
            "weapon_owned_rate": (
                sum(bool(state.get("weapon_owned")) for state in states) / len(states) if states else 0.0
            ),
            "weapon_rarity": dict(collections.Counter(
                str(state.get("weapon_rarity")) for state in states if state.get("weapon_owned")
            )),
            "relic_unlocked_rate": (
                sum(bool(state.get("relic_unlocked")) for state in states) / len(states) if states else 0.0
            ),
        }

    failed_final_waves = [
        int(row["final_death_wave"]) for row in trial_rows if row["final_death_wave"] is not None
    ]
    payload = {
        "profile": profile.PROFILE_NAME,
        "core_profile": "no_core",
        "requested_trials": args.trials,
        "completed_trials": len(rows),
        "seed": args.seed,
        "max_attempts": args.max_attempts,
        "checkpoints": checkpoints,
        "trials": trial_rows,
        "highest_wave": dist([float(row["highest_wave"]) for row in trial_rows]),
        "final_death_wave": dist([float(value) for value in failed_final_waves]),
        "final_death_wave_exact": dict(sorted(collections.Counter(failed_final_waves).items())),
        "final_death_wave_bands": dict(sorted(collections.Counter(
            band_label(value) for value in failed_final_waves
        ).items(), key=lambda item: int(item[0].split("-")[0]))),
        "deaths": dist([float(row.deaths) for row in rows]),
        "max_attempts_reached": sum(
            not row.success and row.attempts >= config.max_attempts for row in rows
        ),
        "final_permanent_state": {
            "dp_total_level": dist([float(row.permanent_levels) for row in rows]),
            "dp_atk_level": dist([float(row.atk_levels) for row in rows]),
            "dp_as_level": dist([float(row.as_levels) for row in rows]),
            "dp_xp_level": dist([float(row.xp_levels) for row in rows]),
            "weapon_material": dist([row.weapon_material for row in rows]),
            "relic_material": dist([row.relic_material for row in rows]),
            "weapon_generations": dist([float(row.weapon_generations) for row in rows]),
            "relic_generations": dist([float(row.relic_generations) for row in rows]),
            "relic_drops": dist([float(row.relic_drops) for row in rows]),
            "game_speed_level": dist([float(row.game_speed_level) for row in rows]),
            "memory_carries": dist([float(row.memory_carries) for row in rows]),
        },
        "nonfinite": nonfinite,
        "errors": errors,
        "balance_changed": False,
    }
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "w5000_v1_precore_bottleneck.json"
    md_path = output_dir / "w5000_v1_precore_bottleneck.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(markdown(payload), encoding="utf-8")
    print(json.dumps({
        "json": str(json_path),
        "markdown": str(md_path),
        "completed_trials": len(rows),
        "errors": len(errors),
        "nonfinite": len(nonfinite),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
