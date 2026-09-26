#!/usr/bin/env python3
"""Replay saved W2500 states with selected legacy growth frozen at W2500."""

from __future__ import annotations

import argparse
import copy
import csv
import dataclasses
import json
import math
import pickle
import random
import sys
from pathlib import Path
from typing import Any

import simulate_first_prestige_v1 as sim


CHECKPOINTS = (2500, 3000, 3500, 4000, 4500, 5000)


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


def make_config() -> Any:
    return sim.SimConfig(
        max_attempts=1,
        reward_skip_enabled=True,
        defense=sim.DefenseConfig(enabled=False),
        target_wave=5000,
        enemy_curve_scale=1.0,
        card_upgrade_cap=1,
        relic_selection_enabled=False,
        exponential_core_multiplier=1.0,
        exponential_core_unlock_wave=2500,
        disabled_card_keys=frozenset({"exponential_core", "final_equation"}),
    )


def frozen_terms(run: Any, permanent: Any, config: Any) -> dict[str, float]:
    counts = run.counts
    effective_kills = sim.progression_wave(run.kills, config)
    escalation = (
        (effective_kills // 10)
        * sim.n(counts, "escalation")
        * math.log10(1 + 0.05 * sim.positive_amp(run, "escalation"))
    )
    boss_devourer = run.boss_devourer_units * math.log10(
        1 + 0.15 * sim.positive_amp(run, "boss_devourer")
    )
    relic_average = (
        sim.relic_average_power(sim.progression_wave(permanent.max_wave, config), config.relic_scale)
        * permanent.relic_quality
    )
    return {
        "boss_devourer": boss_devourer,
        "boss_assimilation": float(run.assimilation_power),
        "escalation": escalation,
        "legendary_growth": float(run.legendary_growth_log),
        "perfect_overdrive": run.perfect_overdrive_stacks * math.log10(1.01),
        "weapon": float(run.weapon_power if run.weapon else 0.0),
        "relic_average": relic_average,
    }


def growth_total(terms: dict[str, float], include_weapon: bool) -> float:
    keys = (
        "boss_devourer",
        "boss_assimilation",
        "escalation",
        "legendary_growth",
        "perfect_overdrive",
        "relic_average",
    )
    total = sum(terms[key] for key in keys)
    return total + (terms["weapon"] if include_weapon else 0.0)


def replay_state(path: Path, config: Any) -> dict[str, Any]:
    with path.open("rb") as handle:
        captured = pickle.load(handle)
    run = copy.deepcopy(captured["run"])
    permanent = copy.deepcopy(captured["permanent"])
    run.counts.pop("exponential_core", None)
    run.counts.pop("final_equation", None)
    rng = random.Random()
    rng.setstate(captured["rng_state"])

    baseline = frozen_terms(run, permanent, config)
    original_compute = sim.compute_snapshot
    original_dynamic = sim.dynamic_damage_log
    observed: dict[int, dict[str, float]] = {}

    def frozen_compute(run_state: Any, permanent_state: Any, boss: bool, current_config: Any) -> Any:
        snapshot = original_compute(run_state, permanent_state, boss, current_config)
        current = frozen_terms(run_state, permanent_state, current_config)
        adjustment = growth_total(baseline, include_weapon=True) - growth_total(current, include_weapon=True)
        weapon_delta = baseline["weapon"] - current["weapon"]
        relic_average_delta = baseline["relic_average"] - current["relic_average"]
        frozen_snapshot = dataclasses.replace(
            snapshot,
            log_dps=snapshot.log_dps + adjustment,
            base_attack_power=snapshot.base_attack_power + weapon_delta,
            weapon_power=baseline["weapon"],
            relic_power=snapshot.relic_power + relic_average_delta,
        )
        wave = int(run_state.kills)
        if wave in CHECKPOINTS and wave not in observed:
            enemy = sim.configured_enemy_power(wave, current_config)
            observed[wave] = {
                "final_damage_power": float(frozen_snapshot.log_dps),
                "enemy_power": float(enemy),
                "power_margin": float(frozen_snapshot.log_dps - enemy),
            }
        return frozen_snapshot

    def frozen_dynamic(run_state: Any, permanent_state: Any, current_config: Any) -> float:
        value = original_dynamic(run_state, permanent_state, current_config)
        current = frozen_terms(run_state, permanent_state, current_config)
        # Weapon is static and absent from dynamic_damage_log.
        return value + growth_total(baseline, include_weapon=False) - growth_total(current, include_weapon=False)

    initial_snapshot = frozen_compute(run, permanent, True, config)
    observed[2500] = {
        "final_damage_power": float(initial_snapshot.log_dps),
        "enemy_power": float(sim.configured_enemy_power(2500, config)),
        "power_margin": float(initial_snapshot.log_dps - sim.configured_enemy_power(2500, config)),
    }
    combat_before = float(run.combat_seconds)
    interaction_before = float(permanent.interaction_seconds)
    sim.compute_snapshot = frozen_compute
    sim.dynamic_damage_log = frozen_dynamic
    failure_context: dict[str, float] | None = None
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
        if result.reached < 5000:
            failure_wave = int(result.failure_wave or result.reached + 1)
            failure_snapshot = frozen_compute(
                run,
                permanent,
                failure_wave % 10 == 0,
                config,
            )
            failure_enemy = sim.configured_enemy_power(failure_wave, config)
            failure_context = {
                "wave": failure_wave,
                "final_damage_power": float(failure_snapshot.log_dps),
                "enemy_power": float(failure_enemy),
                "power_margin": float(failure_snapshot.log_dps - failure_enemy),
            }
    finally:
        sim.compute_snapshot = original_compute
        sim.dynamic_damage_log = original_dynamic

    reach_hours: dict[int, float] = {2500: 0.0}
    for wave, (combat_elapsed, interaction_elapsed) in result.reach_elapsed.items():
        if wave >= 3000:
            reach_hours[int(wave)] = (
                float(combat_elapsed) - combat_before + float(interaction_elapsed)
            ) / 3600.0
    success = result.reached >= 5000
    return {
        "trial": int(captured["trial"]),
        "attempt_at_capture": int(captured["attempt"]),
        "success": success,
        "reached_wave": int(result.reached),
        "failure_wave": None if success else int(result.failure_wave or result.reached + 1),
        "reach_hours": reach_hours,
        "checkpoint": observed,
        "frozen_baseline": baseline,
        "failure_context": failure_context,
        "elapsed_hours": (
            float(result.combat_seconds) - combat_before
            + float(permanent.interaction_seconds) - interaction_before
        ) / 3600.0,
    }


def failure_bins(waves: list[int]) -> dict[str, int]:
    bins: dict[str, int] = {}
    for wave in waves:
        start = max(2500, (wave // 100) * 100)
        key = f"{start}-{start + 99}"
        bins[key] = bins.get(key, 0) + 1
    return dict(sorted(bins.items()))


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    checkpoint_summary: dict[str, Any] = {}
    for wave in CHECKPOINTS:
        reached = [row for row in rows if wave in row["checkpoint"]]
        times = [row["reach_hours"][wave] for row in rows if wave in row["reach_hours"]]
        checkpoint_summary[str(wave)] = {
            "reach_count": len(reached),
            "reach_rate": len(reached) / len(rows),
            "hours_from_w2500_p10": percentile(times, 0.10),
            "hours_from_w2500_p50": percentile(times, 0.50),
            "hours_from_w2500_p90": percentile(times, 0.90),
            "final_damage_power_p25": percentile(
                [row["checkpoint"][wave]["final_damage_power"] for row in reached], 0.25
            ),
            "final_damage_power_p50": percentile(
                [row["checkpoint"][wave]["final_damage_power"] for row in reached], 0.50
            ),
            "final_damage_power_p75": percentile(
                [row["checkpoint"][wave]["final_damage_power"] for row in reached], 0.75
            ),
            "enemy_power": sim.configured_enemy_power(wave, make_config()),
            "power_margin_p25": percentile(
                [row["checkpoint"][wave]["power_margin"] for row in reached], 0.25
            ),
            "power_margin_p50": percentile(
                [row["checkpoint"][wave]["power_margin"] for row in reached], 0.50
            ),
            "power_margin_p75": percentile(
                [row["checkpoint"][wave]["power_margin"] for row in reached], 0.75
            ),
        }
    failures = [int(row["failure_wave"]) for row in rows if row["failure_wave"] is not None]
    failure_contexts = [row["failure_context"] for row in rows if row["failure_context"] is not None]
    return {
        "saved_states": len(rows),
        "success_count": sum(row["success"] for row in rows),
        "success_rate": sum(row["success"] for row in rows) / len(rows),
        "core": False,
        "final_equation": False,
        "enemy_curve": "formal through W2500; W2500-W5000 maps at 3x to formal W10000; W5000 Power=308",
        "frozen_after_w2500": [
            "Boss Devourer contribution",
            "Boss Assimilation contribution",
            "Escalation contribution",
            "Legendary Growth Log contribution",
            "Perfect Overdrive kill-stack contribution",
            "equipped legacy Weapon Power contribution",
            "legacy average Relic Power curve contribution",
        ],
        "checkpoint": checkpoint_summary,
        "failure_wave": {
            "count": len(failures),
            "p10": percentile([float(wave) for wave in failures], 0.10),
            "p25": percentile([float(wave) for wave in failures], 0.25),
            "p50": percentile([float(wave) for wave in failures], 0.50),
            "p75": percentile([float(wave) for wave in failures], 0.75),
            "p90": percentile([float(wave) for wave in failures], 0.90),
            "bins_100_waves": failure_bins(failures),
            "final_damage_power_p50": percentile(
                [item["final_damage_power"] for item in failure_contexts], 0.50
            ),
            "enemy_power_p50": percentile(
                [item["enemy_power"] for item in failure_contexts], 0.50
            ),
            "power_margin_p50": percentile(
                [item["power_margin"] for item in failure_contexts], 0.50
            ),
            "hours_from_w2500_p50": percentile(
                [row["elapsed_hours"] for row in rows if row["failure_context"] is not None], 0.50
            ),
        },
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "trial", "success", "reached_wave", "failure_wave", "wave",
        "hours_from_w2500", "final_damage_power", "enemy_power", "power_margin",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            for wave, item in sorted(row["checkpoint"].items()):
                writer.writerow({
                    "trial": row["trial"],
                    "success": row["success"],
                    "reached_wave": row["reached_wave"],
                    "failure_wave": row["failure_wave"],
                    "wave": wave,
                    "hours_from_w2500": row["reach_hours"].get(wave),
                    **item,
                })


def fmt(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def write_markdown(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# W2500以降・旧成長freeze paired replay",
        "",
        f"保存済みW2500状態: {summary['saved_states']}件  ",
        f"W5000成功: {summary['success_count']}件（{summary['success_rate']:.1%}）  ",
        "Exponential Core: OFF / Final Equation: OFF",
        "",
        "W2500時点の寄与は維持し、指定された旧成長の追加分だけをfreeze。",
        "",
        "## Checkpoint結果",
        "",
        "| Wave | 到達率 | W2500からの時間P50 | Final Damage Power P50 | Enemy Power | 余裕Power P50 | 余裕P25–P75 |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for wave in CHECKPOINTS:
        item = summary["checkpoint"][str(wave)]
        lines.append(
            f"| {wave} | {item['reach_rate']:.1%} | {fmt(item['hours_from_w2500_p50'], 4)}h | "
            f"{fmt(item['final_damage_power_p50'])} | {fmt(item['enemy_power'])} | "
            f"{fmt(item['power_margin_p50'])} | {fmt(item['power_margin_p25'])}～{fmt(item['power_margin_p75'])} |"
        )
    failure = summary["failure_wave"]
    lines += [
        "",
        "## 失敗Wave",
        "",
        f"失敗数: {failure['count']} / {summary['saved_states']}  ",
        f"P25 / P50 / P75: {fmt(failure['p25'], 1)} / {fmt(failure['p50'], 1)} / {fmt(failure['p75'], 1)}",
        f"失敗時Damage / Enemy / 余裕 P50: {fmt(failure['final_damage_power_p50'])} / "
        f"{fmt(failure['enemy_power_p50'])} / {fmt(failure['power_margin_p50'])}",
        f"W2500から失敗までの時間P50: {fmt(failure['hours_from_w2500_p50'], 4)}h",
        "",
        "| Wave帯 | 件数 |",
        "|---|---:|",
    ]
    for band, count in failure["bins_100_waves"].items():
        lines.append(f"| {band} | {count} |")
    lines += [
        "",
        "## 判定",
        "",
    ]
    first_drop = next(
        (wave for wave in CHECKPOINTS[1:] if summary["checkpoint"][str(wave)]["reach_rate"] < 1.0),
        None,
    )
    if first_drop is None:
        lines.append("全保存状態がW5000へ到達し、Checkpoint単位の壁は確認されなかった。")
    else:
        lines.append(f"到達率が最初に低下するCheckpointはW{first_drop}。詳細な壁は失敗Wave分布を参照。")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=Path("output/w5000_exponential_core_paired_50/w2500_states"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/w5000_freeze_legacy_growth"),
    )
    args = parser.parse_args()
    state_paths = sorted(args.state_dir.resolve().glob("trial_*_w2500.pkl"))
    if not state_paths:
        parser.error(f"No saved W2500 states found in {args.state_dir}")

    sim.CHECKPOINTS = CHECKPOINTS
    sim.REACH_WAVES = CHECKPOINTS
    sim.VARIANT_REACH_WAVES = CHECKPOINTS
    config = make_config()
    rows = [replay_state(path, config) for path in state_paths]
    summary = summarize(rows)

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "w5000_freeze_legacy_growth.json"
    csv_path = output_dir / "w5000_freeze_legacy_growth.csv"
    md_path = output_dir / "w5000_freeze_legacy_growth.md"
    json_path.write_text(
        json.dumps({"summary": summary, "trials": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_csv(csv_path, rows)
    write_markdown(md_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"json={json_path}")
    print(f"csv={csv_path}")
    print(f"markdown={md_path}")


if __name__ == "__main__":
    main()
