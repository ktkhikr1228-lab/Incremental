#!/usr/bin/env python3
"""Isolated new-W5000 Common/Uncommon progression probe.

The formal card table and formal simulator file are not modified.  This script
temporarily installs the candidate C/U pool in the imported simulator process,
runs Standard-bot trials only through W2500, and writes aggregate diagnostics.
"""

from __future__ import annotations

import argparse
import collections
import copy
import csv
import json
import math
import random
import sys
from pathlib import Path
from typing import Any

import simulate_first_prestige_v1 as sim


CHECKPOINTS = (100, 500, 1000, 1500, 2000, 2500)
DEFAULT_SEED = 20260828


def make_cards() -> tuple[sim.Card, ...]:
    return (
        sim.card("power_up", "Power Up", "C", "atk"),
        sim.card("weapon_training", "Weapon Training", "C", "dormant"),
        sim.card("rapid_fire", "Rapid Fire", "C", "as"),
        sim.card("critical_eye", "Critical Eye", "C", "crit"),
        sim.card("critical_power", "Critical Power", "C", "crit"),
        sim.card("steady_force", "Steady Force", "C", "damage"),
        sim.card("experience", "Experience", "C", "xp"),
        sim.card("boss_hunter", "Boss Hunter", "C", "boss", "damage"),
        sim.card("boss_scholar", "Boss Scholar", "C", "boss", "xp"),
        sim.card("salvager", "Salvager", "C", "dormant"),
        sim.card("overclock", "Overclock", "U", "as"),
        sim.card("brutal_force", "Brutal Force", "U", "atk", "damage"),
        sim.card("critical_training", "Critical Training", "U", "crit"),
        sim.card("critical_momentum", "Critical Momentum", "U", "crit", "as"),
        sim.card("boss_research", "Boss Research", "U", "boss", "xp"),
        sim.card("quick_learner", "Quick Learner", "U", "xp"),
        sim.card("first_strike", "First Strike", "U", "damage", "time"),
        sim.card("last_stand", "Last Stand", "U", "damage", "time"),
        sim.card("balanced_training", "Balanced Training", "U", "atk", "as"),
        sim.card("salvage_expert", "Salvage Expert", "U", "dormant"),
    )


NEW_CARDS = make_cards()
CARD_BY_KEY = {item.key: item for item in NEW_CARDS}


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return float(values[low])
    return float(values[low] + (values[high] - values[low]) * (position - low))


def quick_learner_multiplier(ttk: float, copies: int) -> float:
    return 1.0 + 0.30 * copies if ttk <= 3.0 + 1e-12 else 1.0


def critical_momentum_as_bonus(crit_rate: float, copies: int) -> float:
    return 0.05 * math.floor(max(0.0, crit_rate) / 0.25 + 1e-12) * copies


def candidate_snapshot(
    run: sim.RunState,
    permanent: sim.PermanentState,
    boss: bool,
    config: sim.SimConfig,
) -> sim.Snapshot:
    counts = run.counts

    crit_chance = max(
        0.0,
        0.01
        + 0.10 * counts.get("critical_eye", 0)
        + 0.08 * counts.get("critical_training", 0),
    )
    crit_multiplier = (
        2.0
        + 0.25 * counts.get("critical_power", 0)
        + 0.20 * counts.get("critical_training", 0)
    )

    as_bonus = (
        0.20 * counts.get("rapid_fire", 0)
        + 0.25 * counts.get("overclock", 0)
        + 0.10 * counts.get("balanced_training", 0)
        + critical_momentum_as_bonus(
            crit_chance, counts.get("critical_momentum", 0)
        )
    )
    base_interval = max(0.1, 1.0 - 0.1 * permanent.interval_level)
    attack_speed = (
        (1.0 / base_interval)
        * 1.05**permanent.attack_speed
        * (1.0 + as_bonus)
    )

    general_xp = 1.05**permanent.xp * (
        1.0 + 0.20 * counts.get("experience", 0)
    )
    if permanent.relic_unlocked:
        general_xp *= 1.02
    boss_xp = general_xp * (
        1.0
        + 0.50 * counts.get("boss_scholar", 0)
        + 0.30 * counts.get("boss_research", 0)
    )
    if permanent.total_levels >= 75:
        boss_xp *= 1.50

    attack_bonus = (
        0.25 * counts.get("power_up", 0)
        + 0.35 * counts.get("brutal_force", 0)
        + 0.15 * counts.get("balanced_training", 0)
    )
    log_attack = permanent.atk * math.log10(1.10) + math.log10(1.0 + attack_bonus)
    if run.weapon:
        # Existing legacy weapon baseline remains active. Candidate Weapon ATK
        # card bonuses deliberately remain dormant until the new weapon model.
        log_attack += run.weapon_power
    if permanent.relic_unlocked:
        log_attack += math.log10(1.02)

    all_damage = (
        1.0
        + 0.15 * counts.get("steady_force", 0)
        + 0.05 * counts.get("brutal_force", 0)
    )
    log_damage = log_attack + math.log10(attack_speed)
    log_damage += sim.crit_log_multiplier(crit_chance, crit_multiplier, counts)
    log_damage += math.log10(all_damage)
    milestone_log = sim.milestone_damage_log(
        permanent.total_levels, config.milestone_power_scale
    )
    log_damage += milestone_log

    if boss:
        boss_damage = (
            1.0
            + 0.25 * counts.get("boss_hunter", 0)
            + 0.30 * counts.get("boss_research", 0)
        )
        log_damage += math.log10(boss_damage)

    effective_kills = sim.progression_wave(run.kills, config)
    if permanent.relic_unlocked:
        log_damage += math.log10(1.0 + 0.01 * (effective_kills // 10))
    average_relic = (
        sim.relic_average_power(
            sim.progression_wave(permanent.max_wave, config), config.relic_scale
        )
        * permanent.relic_quality
    )
    log_damage += average_relic

    fixed_relic = 0.0
    if permanent.relic_unlocked:
        fixed_relic = math.log10(1.02) + math.log10(
            1.0 + 0.01 * (effective_kills // 10)
        )
    dp_power = (
        permanent.atk * math.log10(1.10)
        + permanent.attack_speed * math.log10(1.05)
        + math.log10(1.0 / base_interval)
        + milestone_log
    )

    return sim.Snapshot(
        log_dps=log_damage,
        base_attack_power=log_attack,
        all_damage=all_damage,
        attack_speed=attack_speed,
        general_xp=general_xp,
        boss_xp=boss_xp,
        first_strike_mult=1.35 ** counts.get("first_strike", 0),
        last_stand_mult=2.00 ** counts.get("last_stand", 0),
        execution_mult=1.0,
        time_collapse=False,
        crit_chance=crit_chance,
        crit_multiplier=crit_multiplier,
        follow_rate=0.0,
        multi_crit_tier=0,
        dp_power=dp_power,
        weapon_power=run.weapon_power if run.weapon else 0.0,
        relic_power=average_relic + fixed_relic,
    )


def full_window_power(snapshot: sim.Snapshot, wave: int) -> float:
    limit = sim.enemy_time_limit(wave, 0)
    integral = sim.temporal_integral(limit, limit, snapshot)
    return snapshot.log_dps + math.log10(integral / limit)


def card_contributions(
    run: sim.RunState,
    permanent: sim.PermanentState,
    wave: int,
    config: sim.SimConfig,
    full: sim.Snapshot,
) -> dict[str, float]:
    full_power = full_window_power(full, wave)
    output: dict[str, float] = {}
    for item in NEW_CARDS:
        if run.counts.get(item.key, 0) <= 0:
            output[item.key] = 0.0
            continue
        without = copy.deepcopy(run)
        without.counts[item.key] = 0
        reduced = candidate_snapshot(without, permanent, True, config)
        output[item.key] = full_power - full_window_power(reduced, wave)
    return output


class Capture:
    def __init__(self, config: sim.SimConfig) -> None:
        self.config = config
        self.current: dict[int, dict[str, Any]] = {}

    def reset(self) -> None:
        self.current = {}

    def compute(
        self,
        run: sim.RunState,
        permanent: sim.PermanentState,
        boss: bool,
        config: sim.SimConfig,
    ) -> sim.Snapshot:
        snapshot = candidate_snapshot(run, permanent, boss, config)
        wave = int(run.kills)
        if wave in CHECKPOINTS and wave not in self.current:
            common = sum(run.counts.get(item.key, 0) for item in NEW_CARDS if item.rarity == "C")
            uncommon = sum(run.counts.get(item.key, 0) for item in NEW_CARDS if item.rarity == "U")
            self.current[wave] = {
                "final_damage_power": snapshot.log_dps,
                "full_window_damage_power": full_window_power(snapshot, wave),
                "base_atk_power": snapshot.base_attack_power,
                "base_atk": (
                    10**snapshot.base_attack_power
                    if snapshot.base_attack_power <= 308
                    else None
                ),
                "attack_speed": snapshot.attack_speed,
                "crit_rate": snapshot.crit_chance,
                "crit_multiplier": snapshot.crit_multiplier,
                "xp_multiplier": snapshot.general_xp,
                "cards": run.card_count,
                "common_cards": common,
                "uncommon_cards": uncommon,
                "counts": dict(run.counts),
                "card_power_contribution": card_contributions(
                    run, permanent, wave, config, snapshot
                ),
            }
        return snapshot


def candidate_rarity_chances(_permanent: sim.PermanentState) -> tuple[tuple[str, float], ...]:
    return (("C", 0.95), ("U", 0.05))


def candidate_guaranteed_choices(
    rng: random.Random,
    profile: str,
    run: sim.RunState,
    permanent: sim.PermanentState,
    next_wave: int,
    config: sim.SimConfig,
) -> None:
    if run.kills == 25 and 25 not in run.milestone_choices:
        permanent.max_wave = max(permanent.max_wave, 25)
        sim.choose_card(
            rng,
            profile,
            run,
            permanent,
            next_wave,
            config,
            forced_rarity="U",
            allow_reroll=False,
        )
        run.milestone_choices.add(25)


def install_candidate_pool(capture: Capture) -> None:
    sim.CARDS = NEW_CARDS
    sim.CARD_BY_KEY = CARD_BY_KEY
    sim.CARDS_BY_RARITY = {
        rarity: tuple(item for item in NEW_CARDS if item.rarity == rarity)
        for rarity in ("C", "U", "R", "E", "L")
    }
    sim.STARTER_SAFE_KEYS = frozenset({"power_up", "rapid_fire", "steady_force"})
    sim.STARTER_SAFE_ORDER = ("power_up", "rapid_fire", "steady_force")
    sim.rarity_chances = candidate_rarity_chances
    sim.process_guaranteed_choices = candidate_guaranteed_choices
    sim.compute_snapshot = capture.compute
    sim.CHECKPOINTS = CHECKPOINTS
    sim.REACH_WAVES = CHECKPOINTS
    sim.VARIANT_REACH_WAVES = CHECKPOINTS


def focused_activation_tests(config: sim.SimConfig) -> dict[str, Any]:
    permanent = sim.PermanentState()

    first_run = sim.RunState()
    first_run.counts["first_strike"] = 1
    first = candidate_snapshot(first_run, permanent, False, config)

    last_run = sim.RunState()
    last_run.counts["last_stand"] = 1
    last = candidate_snapshot(last_run, permanent, False, config)

    momentum_run = sim.RunState()
    momentum_run.counts["critical_eye"] = 3
    momentum_run.counts["critical_momentum"] = 1
    momentum = candidate_snapshot(momentum_run, permanent, False, config)

    tests = {
        "first_strike": {
            "expected_multiplier": 1.35,
            "actual_multiplier": first.first_strike_mult,
            "passed": math.isclose(first.first_strike_mult, 1.35),
        },
        "last_stand": {
            "expected_multiplier": 2.0,
            "actual_multiplier": last.last_stand_mult,
            "passed": math.isclose(last.last_stand_mult, 2.0),
        },
        "quick_learner": {
            "ttk_3s_multiplier": quick_learner_multiplier(3.0, 1),
            "ttk_over_3s_multiplier": quick_learner_multiplier(3.0001, 1),
            "passed": math.isclose(quick_learner_multiplier(3.0, 1), 1.30)
            and math.isclose(quick_learner_multiplier(3.0001, 1), 1.0),
        },
        "critical_momentum": {
            "crit_rate": momentum.crit_chance,
            "expected_as": 1.05,
            "actual_as": momentum.attack_speed,
            "passed": math.isclose(momentum.attack_speed, 1.05),
        },
    }
    return tests


def summarize(
    trials: list[dict[str, Any]],
    config: sim.SimConfig,
    activation: dict[str, Any],
    seed: int,
) -> dict[str, Any]:
    checkpoint_summary: dict[str, Any] = {}
    for wave in CHECKPOINTS:
        reached = [row for row in trials if wave in row["checkpoint"]]
        times = [row["result"].reach_seconds[wave] / 3600.0 for row in reached]
        states = [row["checkpoint"][wave] for row in reached]

        def stats(key: str) -> dict[str, float | None]:
            values = [float(state[key]) for state in states]
            return {
                "p25": percentile(values, 0.25),
                "p50": percentile(values, 0.50),
                "p75": percentile(values, 0.75),
            }

        per_card_counts = {
            item.key: (
                sum(state["counts"].get(item.key, 0) for state in states) / len(states)
                if states else 0.0
            )
            for item in NEW_CARDS
        }
        contributions = {
            item.key: (
                sum(state["card_power_contribution"].get(item.key, 0.0) for state in states)
                / len(states)
                if states else 0.0
            )
            for item in NEW_CARDS
        }
        ranking = sorted(contributions.items(), key=lambda pair: pair[1], reverse=True)
        checkpoint_summary[str(wave)] = {
            "reach_count": len(reached),
            "reach_rate": len(reached) / len(trials),
            "arrival_hours": {
                "p25": percentile(times, 0.25),
                "p50": percentile(times, 0.50),
                "p75": percentile(times, 0.75),
            },
            "final_damage_power": stats("final_damage_power"),
            "full_window_damage_power": stats("full_window_damage_power"),
            "base_atk_power": stats("base_atk_power"),
            "base_atk": stats("base_atk"),
            "attack_speed": stats("attack_speed"),
            "crit_rate": stats("crit_rate"),
            "crit_multiplier": stats("crit_multiplier"),
            "xp_multiplier": stats("xp_multiplier"),
            "cards": stats("cards"),
            "common_cards": stats("common_cards"),
            "uncommon_cards": stats("uncommon_cards"),
            "mean_card_counts": per_card_counts,
            "mean_damage_power_contribution": contributions,
            "damage_power_ranking": [
                {"card": key, "mean_power": value} for key, value in ranking
            ],
        }

    results = [row["result"] for row in trials]
    return {
        "settings": {
            "candidate": "new_w5000_common_uncommon_only",
            "formal_modified": False,
            "profile": "Standard/balanced",
            "trials": len(trials),
            "seed": seed,
            "target_for_this_probe": 2500,
            "max_attempts": config.max_attempts,
            "rarity_chances": {"Common": 0.95, "Uncommon": 0.05},
            "guaranteed_choice": {"wave": 25, "rarity": "Uncommon"},
            "rare_epic_legendary_enabled": False,
            "card_refinement_enabled": False,
            "legacy_weapon_relic_baseline_retained": True,
            "candidate_weapon_card_effects_dormant": True,
        },
        "activation_tests": activation,
        "summary": {
            "w2500_success_rate": sum(result.success for result in results) / len(results),
            "deaths": {
                "p25": percentile([float(result.deaths) for result in results], 0.25),
                "p50": percentile([float(result.deaths) for result in results], 0.50),
                "p75": percentile([float(result.deaths) for result in results], 0.75),
            },
            "checkpoint": checkpoint_summary,
        },
        "trials": [
            {
                "trial": row["trial"],
                "success": row["result"].success,
                "deaths": row["result"].deaths,
                "best_failed_wave": row["result"].best_failed_wave,
                "checkpoint": row["checkpoint"],
            }
            for row in trials
        ],
    }


def fmt(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    lines = [
        "# 新W5000候補 Common / Uncommon 基礎進行",
        "",
        f"Trials: {payload['settings']['trials']} / Standard bot / seed {payload['settings']['seed']}  ",
        "Rare以上なし、カード精錬なし、Weapon系カード効果休眠。",
        "",
        "## 進行",
        "",
        "| Wave | 到達率 | 時間P25 | P50 | P75 | Final Power P50 | Base ATK Power | AS | Crit | Crit Mult | XP | Cards | C / U |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for wave in CHECKPOINTS:
        item = summary["checkpoint"][str(wave)]
        lines.append(
            f"| {wave} | {item['reach_rate']:.1%} | "
            f"{fmt(item['arrival_hours']['p25'])}h | {fmt(item['arrival_hours']['p50'])}h | "
            f"{fmt(item['arrival_hours']['p75'])}h | {fmt(item['final_damage_power']['p50'])} | "
            f"{fmt(item['base_atk_power']['p50'])} | {fmt(item['attack_speed']['p50'])} | "
            f"{fmt(item['crit_rate']['p50'], 2)} | {fmt(item['crit_multiplier']['p50'], 2)} | "
            f"{fmt(item['xp_multiplier']['p50'], 2)} | {fmt(item['cards']['p50'], 1)} | "
            f"{fmt(item['common_cards']['p50'], 1)} / {fmt(item['uncommon_cards']['p50'], 1)} |"
        )
    lines += [
        "",
        f"Deaths P25/P50/P75: {fmt(summary['deaths']['p25'], 1)} / {fmt(summary['deaths']['p50'], 1)} / {fmt(summary['deaths']['p75'], 1)}  ",
        f"W2500 success: {summary['w2500_success_rate']:.1%}",
        "",
        "平均カード枚数（到達者）:",
    ]
    common_keys = {item.key for item in NEW_CARDS if item.rarity == "C"}
    for wave in CHECKPOINTS:
        checkpoint = summary["checkpoint"][str(wave)]
        if checkpoint["reach_count"] <= 0:
            continue
        counts = checkpoint["mean_card_counts"]
        common_mean = sum(value for key, value in counts.items() if key in common_keys)
        uncommon_mean = sum(value for key, value in counts.items() if key not in common_keys)
        lines.append(f"- W{wave}: 全体 {common_mean + uncommon_mean:.2f} / Common {common_mean:.2f} / Uncommon {uncommon_mean:.2f}")

    lines += [
        "",
        "## 発動検証",
        "",
        "| 効果 | 結果 | 詳細 |",
        "|---|---:|---|",
    ]
    for key, test in payload["activation_tests"].items():
        details = ", ".join(
            f"{name}={value}" for name, value in test.items() if name != "passed"
        )
        lines.append(f"| {key} | {'PASS' if test['passed'] else 'FAIL'} | {details} |")

    ranking_wave = max(
        wave
        for wave in CHECKPOINTS
        if summary["checkpoint"][str(wave)]["reach_count"] > 0
    )
    lines += ["", f"## W{ranking_wave} Damage Power寄与", "", "| 順位 | Card | Mean Power |", "|---:|---|---:|"]
    ranking = summary["checkpoint"][str(ranking_wave)]["damage_power_ranking"]
    for index, entry in enumerate(ranking[:10], 1):
        lines.append(f"| {index} | {entry['card']} | {entry['mean_power']:.4f} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_checkpoint_csv(path: Path, payload: dict[str, Any]) -> None:
    fields = [
        "wave", "reach_rate", "time_p25", "time_p50", "time_p75",
        "final_damage_power_p50", "base_atk_p50", "base_atk_power_p50",
        "attack_speed_p50", "crit_rate_p50", "crit_multiplier_p50",
        "xp_multiplier_p50", "cards_p50", "common_p50", "uncommon_p50",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for wave in CHECKPOINTS:
            item = payload["summary"]["checkpoint"][str(wave)]
            writer.writerow({
                "wave": wave,
                "reach_rate": item["reach_rate"],
                "time_p25": item["arrival_hours"]["p25"],
                "time_p50": item["arrival_hours"]["p50"],
                "time_p75": item["arrival_hours"]["p75"],
                "final_damage_power_p50": item["final_damage_power"]["p50"],
                "base_atk_p50": item["base_atk"]["p50"],
                "base_atk_power_p50": item["base_atk_power"]["p50"],
                "attack_speed_p50": item["attack_speed"]["p50"],
                "crit_rate_p50": item["crit_rate"]["p50"],
                "crit_multiplier_p50": item["crit_multiplier"]["p50"],
                "xp_multiplier_p50": item["xp_multiplier"]["p50"],
                "cards_p50": item["cards"]["p50"],
                "common_p50": item["common_cards"]["p50"],
                "uncommon_p50": item["uncommon_cards"]["p50"],
            })


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--max-attempts", type=int, default=220)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/new_w5000_common_uncommon_30"),
    )
    args = parser.parse_args()
    if not 1 <= args.trials <= 30:
        parser.error("--trials must be between 1 and 30")

    config = sim.SimConfig(
        max_attempts=args.max_attempts,
        automation_enabled=True,
        interval_enabled=False,
        game_speed_enabled=True,
        initial_card_points_enabled=False,
        sweep_enabled=True,
        reward_skip_enabled=True,
        defense=sim.DefenseConfig(enabled=False),
        target_wave=2500,
        enemy_curve_scale=1.0,
        card_upgrade_cap=0,
        relic_selection_enabled=False,
        exponential_core_multiplier=1.0,
        exponential_core_unlock_wave=5000,
    )
    capture = Capture(config)
    install_candidate_pool(capture)
    activation = focused_activation_tests(config)

    rows: list[dict[str, Any]] = []
    for trial in range(args.trials):
        capture.reset()
        rng = random.Random(args.seed + 1_000_000 + trial)
        result = sim.run_trial(rng, "balanced", config, allow_overdrive=False)
        rows.append({
            "trial": trial,
            "result": result,
            "checkpoint": copy.deepcopy(capture.current),
        })

    payload = summarize(rows, config, activation, args.seed)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "new_w5000_common_uncommon.json"
    csv_path = output_dir / "new_w5000_common_uncommon_checkpoints.csv"
    md_path = output_dir / "new_w5000_common_uncommon.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_checkpoint_csv(csv_path, payload)
    write_markdown(md_path, payload)

    print(json.dumps({
        "settings": payload["settings"],
        "activation_tests": payload["activation_tests"],
        "summary": {
            "w2500_success_rate": payload["summary"]["w2500_success_rate"],
            "deaths": payload["summary"]["deaths"],
            "checkpoint": {
                wave: {
                    "reach_rate": item["reach_rate"],
                    "arrival_hours": item["arrival_hours"],
                    "final_damage_power": item["final_damage_power"],
                }
                for wave, item in payload["summary"]["checkpoint"].items()
            },
        },
        "files": {
            "json": str(json_path),
            "csv": str(csv_path),
            "markdown": str(md_path),
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
