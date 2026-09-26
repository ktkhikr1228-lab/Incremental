#!/usr/bin/env python3
"""Paired replay of Big-Boss-growing Base ATK Exponential Core."""

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
from replay_w5000_freeze_legacy_growth import frozen_terms, growth_total, make_config


CHECKPOINTS = (2500, 2600, 2700, 2800, 2900, 3000, 3500, 4000, 4500, 5000)
REQUIRED_REACH_WAVES = (3000, 3500, 4000, 4500, 5000)
CONDITIONS: tuple[tuple[str, float | None], ...] = (
    ("A_no_core", None),
    ("B_growth_1.12", 1.12),
    ("C_growth_1.13", 1.13),
    ("D_growth_1.14", 1.14),
)
REPORT_TITLE = "成長型Exponential Core paired replay"
DEFAULT_OUTPUT_DIR = Path("output/w5000_growing_exponential_core")
OUTPUT_STEM = "w5000_growing_exponential_core"
FORMULA_DESCRIPTION = "BaseATK_after = BaseATK_before ^ (growth_rate ^ N)"
N_DESCRIPTION = "Big Bosses defeated after W2500; one per 100 waves"


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


def big_bosses_after_w2500(kills: int) -> int:
    return max(0, (kills - 2500) // 100)


def core_exponent(kills: int, growth_rate: float | None) -> float:
    if growth_rate is None:
        return 1.0
    return growth_rate ** big_bosses_after_w2500(kills)


def replay_condition(
    captured: dict[str, Any],
    label: str,
    growth_rate: float | None,
    config: Any,
) -> dict[str, Any]:
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

    def growing_core_compute(
        run_state: Any,
        permanent_state: Any,
        boss: bool,
        current_config: Any,
    ) -> Any:
        snapshot = original_compute(run_state, permanent_state, boss, current_config)
        current = frozen_terms(run_state, permanent_state, current_config)

        # First freeze only the post-W2500 increase from the named legacy
        # engines. Their exact W2500 contribution remains intact.
        legacy_adjustment = (
            growth_total(baseline, include_weapon=True)
            - growth_total(current, include_weapon=True)
        )
        weapon_delta = baseline["weapon"] - current["weapon"]
        relic_average_delta = baseline["relic_average"] - current["relic_average"]
        frozen_base_power = snapshot.base_attack_power + weapon_delta
        frozen_log_dps = snapshot.log_dps + legacy_adjustment

        exponent = core_exponent(int(run_state.kills), growth_rate)
        core_power_gain = frozen_base_power * (exponent - 1.0)
        adjusted = dataclasses.replace(
            snapshot,
            base_attack_power=frozen_base_power * exponent,
            log_dps=frozen_log_dps + core_power_gain,
            weapon_power=baseline["weapon"],
            relic_power=snapshot.relic_power + relic_average_delta,
        )
        wave = int(run_state.kills)
        if wave in CHECKPOINTS and wave not in observed:
            enemy = sim.configured_enemy_power(wave, current_config)
            observed[wave] = {
                "big_boss_count": big_bosses_after_w2500(wave),
                "core_exponent": exponent,
                "base_atk_power_before_core": float(frozen_base_power),
                "base_atk_power": float(adjusted.base_attack_power),
                "core_power_gain": float(core_power_gain),
                "final_damage_power": float(adjusted.log_dps),
                "enemy_power": float(enemy),
                "power_margin": float(adjusted.log_dps - enemy),
            }
        return adjusted

    def frozen_dynamic(run_state: Any, permanent_state: Any, current_config: Any) -> float:
        value = original_dynamic(run_state, permanent_state, current_config)
        current = frozen_terms(run_state, permanent_state, current_config)
        return (
            value
            + growth_total(baseline, include_weapon=False)
            - growth_total(current, include_weapon=False)
        )

    initial_snapshot = growing_core_compute(run, permanent, True, config)
    del initial_snapshot
    combat_before = float(run.combat_seconds)
    interaction_before = float(permanent.interaction_seconds)
    sim.compute_snapshot = growing_core_compute
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
            failure_snapshot = growing_core_compute(
                run,
                permanent,
                failure_wave % 10 == 0,
                config,
            )
            failure_enemy = sim.configured_enemy_power(failure_wave, config)
            failure_context = {
                "wave": failure_wave,
                "big_boss_count": big_bosses_after_w2500(int(run.kills)),
                "core_exponent": core_exponent(int(run.kills), growth_rate),
                "final_damage_power": float(failure_snapshot.log_dps),
                "enemy_power": float(failure_enemy),
                "power_margin": float(failure_snapshot.log_dps - failure_enemy),
            }
    finally:
        sim.compute_snapshot = original_compute
        sim.dynamic_damage_log = original_dynamic

    reach_hours: dict[int, float] = {2500: 0.0}
    for wave, (combat_elapsed, interaction_elapsed) in result.reach_elapsed.items():
        if wave >= 2600:
            reach_hours[int(wave)] = (
                float(combat_elapsed) - combat_before + float(interaction_elapsed)
            ) / 3600.0
    success = result.reached >= 5000
    return {
        "condition": label,
        "growth_rate": growth_rate,
        "success": success,
        "reached_wave": int(result.reached),
        "failure_wave": None if success else int(result.failure_wave or result.reached + 1),
        "post_w2500_deaths": 0 if success else 1,
        "elapsed_hours": (
            float(result.combat_seconds) - combat_before
            + float(permanent.interaction_seconds) - interaction_before
        ) / 3600.0,
        "reach_hours": reach_hours,
        "checkpoint": observed,
        "failure_context": failure_context,
    }


def failure_bins(waves: list[int]) -> dict[str, int]:
    bins: dict[str, int] = {}
    for wave in waves:
        start = max(2500, (wave // 100) * 100)
        key = f"{start}-{start + 99}"
        bins[key] = bins.get(key, 0) + 1
    return dict(sorted(bins.items()))


def summarize_condition(
    label: str,
    growth_rate: float | None,
    entries: list[dict[str, Any]],
    config: Any,
) -> dict[str, Any]:
    checkpoint_summary: dict[str, Any] = {}
    for wave in CHECKPOINTS:
        reached = [entry for entry in entries if wave in entry["checkpoint"]]
        times = [entry["reach_hours"][wave] for entry in entries if wave in entry["reach_hours"]]

        def p50(key: str) -> float | None:
            return percentile([entry["checkpoint"][wave][key] for entry in reached], 0.50)

        checkpoint_summary[str(wave)] = {
            "reach_count": len(reached),
            "reach_rate": len(reached) / len(entries),
            "hours_from_w2500_p10": percentile(times, 0.10),
            "hours_from_w2500_p50": percentile(times, 0.50),
            "hours_from_w2500_p90": percentile(times, 0.90),
            "big_boss_count": big_bosses_after_w2500(wave),
            "core_exponent": core_exponent(wave, growth_rate),
            "base_atk_power_before_core_p50": p50("base_atk_power_before_core"),
            "base_atk_power_p50": p50("base_atk_power"),
            "core_power_gain_p50": p50("core_power_gain"),
            "final_damage_power_p25": percentile(
                [entry["checkpoint"][wave]["final_damage_power"] for entry in reached], 0.25
            ),
            "final_damage_power_p50": p50("final_damage_power"),
            "final_damage_power_p75": percentile(
                [entry["checkpoint"][wave]["final_damage_power"] for entry in reached], 0.75
            ),
            "enemy_power": sim.configured_enemy_power(wave, config),
            "power_margin_p25": percentile(
                [entry["checkpoint"][wave]["power_margin"] for entry in reached], 0.25
            ),
            "power_margin_p50": p50("power_margin"),
            "power_margin_p75": percentile(
                [entry["checkpoint"][wave]["power_margin"] for entry in reached], 0.75
            ),
        }

    failures = [int(entry["failure_wave"]) for entry in entries if entry["failure_wave"] is not None]
    contexts = [entry["failure_context"] for entry in entries if entry["failure_context"] is not None]
    return {
        "condition": label,
        "growth_rate": growth_rate,
        "states": len(entries),
        "success_count": sum(entry["success"] for entry in entries),
        "success_rate": sum(entry["success"] for entry in entries) / len(entries),
        "post_w2500_deaths_p50": percentile(
            [float(entry["post_w2500_deaths"]) for entry in entries], 0.50
        ),
        "checkpoint": checkpoint_summary,
        "failure_wave": {
            "count": len(failures),
            "p10": percentile([float(value) for value in failures], 0.10),
            "p25": percentile([float(value) for value in failures], 0.25),
            "p50": percentile([float(value) for value in failures], 0.50),
            "p75": percentile([float(value) for value in failures], 0.75),
            "p90": percentile([float(value) for value in failures], 0.90),
            "bins_100_waves": failure_bins(failures),
            "final_damage_power_p50": percentile(
                [context["final_damage_power"] for context in contexts], 0.50
            ),
            "enemy_power_p50": percentile(
                [context["enemy_power"] for context in contexts], 0.50
            ),
            "power_margin_p50": percentile(
                [context["power_margin"] for context in contexts], 0.50
            ),
        },
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "trial", "condition", "growth_rate", "success", "reached_wave", "failure_wave",
        "post_w2500_deaths", "wave", "hours_from_w2500", "big_boss_count",
        "core_exponent", "base_atk_power_before_core", "base_atk_power",
        "core_power_gain", "final_damage_power", "enemy_power", "power_margin",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            for label, _ in CONDITIONS:
                entry = row["conditions"][label]
                for wave, checkpoint in sorted(entry["checkpoint"].items()):
                    writer.writerow({
                        "trial": row["trial"],
                        "condition": label,
                        "growth_rate": entry["growth_rate"],
                        "success": entry["success"],
                        "reached_wave": entry["reached_wave"],
                        "failure_wave": entry["failure_wave"],
                        "post_w2500_deaths": entry["post_w2500_deaths"],
                        "wave": wave,
                        "hours_from_w2500": entry["reach_hours"].get(wave),
                        **checkpoint,
                    })


def fmt(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    summaries = payload["summary"]["conditions"]
    lines = [
        f"# {REPORT_TITLE}",
        "",
        f"保存済みW2500状態: {payload['summary']['saved_states']}件  ",
        "旧成長追加分freeze / Exponential CoreはBase ATKのみ / Final Equation OFF",
        "",
        "## 到達率・時間",
        "",
        "| 条件 | "
        + " | ".join(f"W{wave}" for wave in REQUIRED_REACH_WAVES)
        + " | W5000時間P50 | 死亡P50 |",
        "|---|" + "---:|" * (len(REQUIRED_REACH_WAVES) + 2),
    ]
    for label, _ in CONDITIONS:
        item = summaries[label]
        cp = item["checkpoint"]
        lines.append(
            f"| {label} | "
            + " | ".join(f"{cp[str(wave)]['reach_rate']:.1%}" for wave in REQUIRED_REACH_WAVES)
            + f" | {fmt(cp['5000']['hours_from_w2500_p50'], 4)}h | "
            + f"{fmt(item['post_w2500_deaths_p50'], 1)} |"
        )

    for label, _ in CONDITIONS:
        item = summaries[label]
        lines += [
            "",
            f"## {label}",
            "",
            "| Wave | N | CoreExponent | Base ATK Power P50 | Final Damage P50 | Enemy | 余裕P50 | 時間P50 |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for wave in CHECKPOINTS:
            cp = item["checkpoint"][str(wave)]
            lines.append(
                f"| {wave} | {cp['big_boss_count']} | {cp['core_exponent']:.6f} | "
                f"{fmt(cp['base_atk_power_p50'])} | {fmt(cp['final_damage_power_p50'])} | "
                f"{fmt(cp['enemy_power'])} | {fmt(cp['power_margin_p50'])} | "
                f"{fmt(cp['hours_from_w2500_p50'], 4)}h |"
            )
        failure = item["failure_wave"]
        lines += [
            "",
            f"失敗数: {failure['count']} / {item['states']}  ",
            f"失敗Wave P25/P50/P75: {fmt(failure['p25'], 1)} / {fmt(failure['p50'], 1)} / {fmt(failure['p75'], 1)}",
        ]
        if failure["bins_100_waves"]:
            lines += ["", "| 失敗Wave帯 | 件数 |", "|---|---:|"]
            for band, count in failure["bins_100_waves"].items():
                lines.append(f"| {band} | {count} |")

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
        default=DEFAULT_OUTPUT_DIR,
    )
    args = parser.parse_args()
    state_paths = sorted(args.state_dir.resolve().glob("trial_*_w2500.pkl"))
    if not state_paths:
        parser.error(f"No saved W2500 states found in {args.state_dir}")

    sim.CHECKPOINTS = CHECKPOINTS
    sim.REACH_WAVES = CHECKPOINTS
    sim.VARIANT_REACH_WAVES = CHECKPOINTS
    config = make_config()
    rows: list[dict[str, Any]] = []
    for path in state_paths:
        with path.open("rb") as handle:
            captured = pickle.load(handle)
        condition_rows = {
            label: replay_condition(captured, label, rate, config)
            for label, rate in CONDITIONS
        }
        rows.append({"trial": int(captured["trial"]), "conditions": condition_rows})

    condition_summary = {
        label: summarize_condition(
            label,
            rate,
            [row["conditions"][label] for row in rows],
            config,
        )
        for label, rate in CONDITIONS
    }
    payload = {
        "settings": {
            "source": "25 saved post-W2500 paired states",
            "full_run_or_new_monte_carlo": False,
            "core_target": "Base ATK",
            "core_formula": FORMULA_DESCRIPTION,
            "N": N_DESCRIPTION,
            "enemy_curve": "formal through W2500; 3x compressed to formal W10000 at W5000",
            "legacy_growth_frozen_after_w2500": True,
            "final_equation": False,
        },
        "summary": {
            "saved_states": len(rows),
            "conditions": condition_summary,
        },
        "trials": rows,
    }

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{OUTPUT_STEM}.json"
    csv_path = output_dir / f"{OUTPUT_STEM}.csv"
    md_path = output_dir / f"{OUTPUT_STEM}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(csv_path, rows)
    write_markdown(md_path, payload)
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    print(f"json={json_path}")
    print(f"csv={csv_path}")
    print(f"markdown={md_path}")


if __name__ == "__main__":
    main()
