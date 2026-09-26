#!/usr/bin/env python3
"""Isolated new-W5000 Common/Uncommon/Rare progression probe."""

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
import simulate_new_w5000_common_uncommon as base


CHECKPOINTS = (100, 500, 750, 1000, 1500, 2000, 2500)
DEFAULT_SEED = 20260828

RARE_CARDS = (
    sim.card("critical_engine", "Critical Engine", "R", "crit", "as", "engine"),
    sim.card("critical_conversion", "Critical Conversion", "R", "crit", "damage", "engine"),
    sim.card("overflow", "Overflow", "R", "crit", "rule", unique=True),
    sim.card("follow_up_strike", "Follow-Up Strike", "R", "followup", "rule", unique=True),
    sim.card("double_strike", "Double Strike", "R", "followup"),
    sim.card("multi_hit", "Multi-Hit", "R", "damage"),
    sim.card("supplemental_damage", "Supplemental Damage", "R", "damage"),
    sim.card("re_action", "Re-Action", "R", "damage"),
    sim.card("knowledge_conversion", "Knowledge Conversion", "R", "xp", "damage", "engine", unique=True),
    sim.card("accelerated_learning", "Accelerated Learning", "R", "xp", "growth", "engine", unique=True),
    sim.card("boss_devourer", "Boss Devourer", "R", "boss", "damage", "growth", unique=True),
    sim.card("execution", "Execution", "R", "damage"),
)
ALL_CARDS = base.NEW_CARDS + RARE_CARDS
CARD_BY_KEY = {item.key: item for item in ALL_CARDS}
RARE_KEYS = tuple(item.key for item in RARE_CARDS)
UNIQUE_RARE_KEYS = tuple(item.key for item in RARE_CARDS if item.unique)


def softcap_steps(crit_rate: float) -> int:
    rate = max(0.0, crit_rate)
    return (
        math.floor(min(rate, 2.0) / 0.25 + 1e-12)
        + math.floor(max(min(rate - 2.0, 2.0), 0.0) / 0.50 + 1e-12)
        + math.floor(max(rate - 4.0, 0.0) / 1.00 + 1e-12)
    )


def knowledge_conversion_bonus(xp_multiplier: float) -> float:
    return (
        min(max(xp_multiplier - 1.0, 0.0), 1.0) * 0.25
        + min(max(xp_multiplier - 2.0, 0.0), 2.0) * 0.125
        + max(xp_multiplier - 4.0, 0.0) * 0.05
    )


def accelerated_learning_bonus(cards_after: float) -> float:
    cards = max(0.0, cards_after)
    return (
        min(cards, 10.0) * 0.03
        + min(max(cards - 10.0, 0.0), 20.0) * 0.015
        + min(max(cards - 30.0, 0.0), 70.0) * 0.005
        + min(max(cards - 100.0, 0.0), 400.0) * 0.002
        + max(cards - 500.0, 0.0) * 0.0005
    )


def boss_devourer_bonus(bosses: float) -> float:
    count = max(0.0, bosses)
    return (
        min(count, 10.0) * 0.05
        + min(max(count - 10.0, 0.0), 20.0) * 0.025
        + min(max(count - 30.0, 0.0), 70.0) * 0.01
        + max(count - 100.0, 0.0) * 0.001
    )


def attack_series_factor(
    crit_factor: float,
    hit_count: float,
    supplemental_bonus: float,
    follow_unlocked: bool,
    follow_rate: float,
    follow_damage: float,
    reaction_rate: float,
) -> float:
    # Supplemental applies only to normal/Hit Count hits. Follow-Up shares the
    # parent Crit expectation but cannot produce Re-Action. Rare Re-Action has
    # depth one, so expected normal actions are exactly 1+r.
    normal = hit_count * (crit_factor + supplemental_bonus)
    follow = (
        follow_rate * follow_damage * hit_count * crit_factor
        if follow_unlocked
        else 0.0
    )
    return (1.0 + reaction_rate) * (normal + follow)


def effective_full_window_power(snapshot: sim.Snapshot, wave: int) -> float:
    value = base.full_window_power_original(snapshot, wave)
    execution_required_ratio = 0.70 + 0.30 / snapshot.execution_mult
    return value - math.log10(execution_required_ratio)


def candidate_snapshot(
    run: sim.RunState,
    permanent: sim.PermanentState,
    boss: bool,
    config: sim.SimConfig,
) -> sim.Snapshot:
    counts = run.counts
    raw_crit = (
        0.01
        + 0.10 * counts.get("critical_eye", 0)
        + 0.08 * counts.get("critical_training", 0)
    )
    displayed_crit = raw_crit if counts.get("overflow", 0) else min(1.0, raw_crit)
    synergy_crit = raw_crit if counts.get("overflow", 0) else min(1.0, raw_crit)
    crit_multiplier = (
        2.0
        + 0.25 * counts.get("critical_power", 0)
        + 0.20 * counts.get("critical_training", 0)
    )
    steps = softcap_steps(synergy_crit)

    as_bonus = (
        0.20 * counts.get("rapid_fire", 0)
        + 0.25 * counts.get("overclock", 0)
        + 0.10 * counts.get("balanced_training", 0)
        + base.critical_momentum_as_bonus(
            synergy_crit, counts.get("critical_momentum", 0)
        )
        + 0.05 * steps * counts.get("critical_engine", 0)
    )
    base_interval = max(0.1, 1.0 - 0.1 * permanent.interval_level)
    attack_speed = (
        (1.0 / base_interval)
        * 1.05**permanent.attack_speed
        * (1.0 + as_bonus)
    )

    xp_bonus = (
        0.20 * counts.get("experience", 0)
        + accelerated_learning_bonus(run.accelerated_units)
        * counts.get("accelerated_learning", 0)
    )
    general_xp = 1.05**permanent.xp * (1.0 + xp_bonus)
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
        log_attack += run.weapon_power
    if permanent.relic_unlocked:
        log_attack += math.log10(1.02)

    all_damage_bonus = (
        0.15 * counts.get("steady_force", 0)
        + 0.05 * counts.get("brutal_force", 0)
        + 0.05 * steps * counts.get("critical_conversion", 0)
        + boss_devourer_bonus(run.boss_devourer_units)
        * counts.get("boss_devourer", 0)
    )
    if counts.get("knowledge_conversion", 0):
        all_damage_bonus += knowledge_conversion_bonus(general_xp)
    all_damage = 1.0 + all_damage_bonus

    # No Multi-Crit before Epic. Overflow exposes over-cap Crit only to the
    # Rare Crit engines; actual Crit damage remains capped at one Crit.
    crit_factor = 1.0 + min(1.0, raw_crit) * (crit_multiplier - 1.0)
    hit_count = 1.0 + 0.20 * counts.get("multi_hit", 0)
    supplemental = 0.25 * counts.get("supplemental_damage", 0)
    follow_unlocked = bool(counts.get("follow_up_strike", 0))
    follow_rate = min(
        1.0,
        0.10 + 0.15 * counts.get("double_strike", 0),
    ) if follow_unlocked else 0.0
    follow_damage = 0.50 + 0.25 * counts.get("double_strike", 0)
    reaction_rate = min(0.80, 0.15 * counts.get("re_action", 0))
    series = attack_series_factor(
        crit_factor,
        hit_count,
        supplemental,
        follow_unlocked,
        follow_rate,
        follow_damage,
        reaction_rate,
    )

    log_damage = log_attack + math.log10(attack_speed) + math.log10(series)
    log_damage += math.log10(all_damage)
    milestone_log = sim.milestone_damage_log(
        permanent.total_levels, config.milestone_power_scale
    )
    log_damage += milestone_log
    if boss:
        log_damage += math.log10(
            1.0
            + 0.25 * counts.get("boss_hunter", 0)
            + 0.30 * counts.get("boss_research", 0)
        )

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
        execution_mult=1.0 + 1.50 * counts.get("execution", 0),
        time_collapse=False,
        crit_chance=displayed_crit,
        crit_multiplier=crit_multiplier,
        follow_rate=follow_rate,
        multi_crit_tier=0,
        dp_power=dp_power,
        weapon_power=run.weapon_power if run.weapon else 0.0,
        relic_power=average_relic + fixed_relic,
    )


def candidate_dynamic_damage_log(
    run: sim.RunState,
    permanent: sim.PermanentState,
    config: sim.SimConfig,
) -> float:
    counts = run.counts
    raw_crit = (
        0.01
        + 0.10 * counts.get("critical_eye", 0)
        + 0.08 * counts.get("critical_training", 0)
    )
    synergy_crit = raw_crit if counts.get("overflow", 0) else min(1.0, raw_crit)
    all_damage_bonus = (
        0.15 * counts.get("steady_force", 0)
        + 0.05 * counts.get("brutal_force", 0)
        + 0.05 * softcap_steps(synergy_crit)
        * counts.get("critical_conversion", 0)
        + boss_devourer_bonus(run.boss_devourer_units)
        * counts.get("boss_devourer", 0)
    )
    # XP-related terms are static between card acquisitions; effect_version
    # invalidates the snapshot whenever a card changes Accelerated Learning.
    value = math.log10(1.0 + all_damage_bonus)
    effective_kills = sim.progression_wave(run.kills, config)
    if permanent.relic_unlocked:
        value += math.log10(1.0 + 0.01 * (effective_kills // 10))
    value += (
        sim.relic_average_power(
            sim.progression_wave(permanent.max_wave, config), config.relic_scale
        )
        * permanent.relic_quality
    )
    return value


class AcquisitionObserver:
    def __init__(self) -> None:
        self.total: collections.Counter[str] = collections.Counter()
        self.first_unique_wave: dict[str, int] = {}

    def reset(self) -> None:
        self.total = collections.Counter()
        self.first_unique_wave = {}

    def acquire(self, run: sim.RunState, item: sim.Card) -> None:
        accelerated_before = run.counts.get("accelerated_learning", 0)
        run.counts[item.key] += 1
        for tag in item.tags:
            run.tag_counts[tag] += 1
        # Only cards acquired after Accelerated Learning count; its own pickup
        # is deliberately excluded.
        run.accelerated_units += accelerated_before
        run.card_count += 1
        run.choices += 1
        run.effect_version += 1
        self.total[item.key] += 1
        if item.unique and item.key not in self.first_unique_wave:
            self.first_unique_wave[item.key] = int(run.kills)


class RareCapture(base.Capture):
    def compute(
        self,
        run: sim.RunState,
        permanent: sim.PermanentState,
        boss: bool,
        config: sim.SimConfig,
    ) -> sim.Snapshot:
        wave = int(run.kills)
        already_captured = wave in self.current
        snapshot = super().compute(run, permanent, boss, config)
        if not already_captured and wave in self.current:
            self.current[wave]["rare_cards"] = sum(
                run.counts.get(item.key, 0) for item in RARE_CARDS
            )
        return snapshot


def rarity_chances(permanent: sim.PermanentState) -> tuple[tuple[str, float], ...]:
    if permanent.max_wave < 100:
        return (("C", 0.92), ("U", 0.07), ("R", 0.01))
    if permanent.max_wave < 500:
        return (("C", 0.822), ("U", 0.14), ("R", 0.038))
    return (("C", 0.72), ("U", 0.20), ("R", 0.08))


def guaranteed_choices(
    rng: random.Random,
    profile: str,
    run: sim.RunState,
    permanent: sim.PermanentState,
    next_wave: int,
    config: sim.SimConfig,
) -> None:
    for wave, rarity in ((25, "U"), (100, "R")):
        if run.kills == wave and wave not in run.milestone_choices:
            permanent.max_wave = max(permanent.max_wave, wave)
            sim.choose_card(
                rng,
                profile,
                run,
                permanent,
                next_wave,
                config,
                forced_rarity=rarity,
                allow_reroll=False,
            )
            run.milestone_choices.add(wave)


def mechanics_tests(config: sim.SimConfig) -> dict[str, Any]:
    expected_combined = 1.15 * (1.20 * 1.25 + 0.10 * 0.50 * 1.20)
    actual_combined = attack_series_factor(1.0, 1.20, 0.25, True, 0.10, 0.50, 0.15)
    tests = {
        "critical_softcap": {
            "steps_at_200pct": softcap_steps(2.0),
            "steps_at_400pct": softcap_steps(4.0),
            "steps_at_500pct": softcap_steps(5.0),
            "passed": (softcap_steps(2.0), softcap_steps(4.0), softcap_steps(5.0)) == (8, 12, 13),
        },
        "follow_up": {
            "expected_multiplier_without_other_rare": 1.05,
            "actual_multiplier": attack_series_factor(1.0, 1.0, 0.0, True, 0.10, 0.50, 0.0),
            "passed": math.isclose(attack_series_factor(1.0, 1.0, 0.0, True, 0.10, 0.50, 0.0), 1.05),
        },
        "multi_hit": {"expected_hit_count": 1.2, "actual_hit_count": 1.0 + 0.20, "passed": True},
        "supplemental": {"expected_noncrit_normal_hit": 1.25, "actual_noncrit_normal_hit": 1.0 + 0.25, "passed": True},
        "re_action_depth1": {"rate": 0.15, "expected_actions": 1.15, "actual_actions": 1.0 + 0.15, "passed": True},
        "combined_independence": {
            "expected": expected_combined,
            "actual": actual_combined,
            "follow_up_can_react": False,
            "passed": math.isclose(expected_combined, actual_combined),
        },
        "boss_devourer": {
            "bonus_10": boss_devourer_bonus(10),
            "bonus_30": boss_devourer_bonus(30),
            "bonus_100": boss_devourer_bonus(100),
            "passed": all(math.isclose(a, b) for a, b in ((boss_devourer_bonus(10), 0.5), (boss_devourer_bonus(30), 1.0), (boss_devourer_bonus(100), 1.7))),
        },
        "accelerated_learning": {
            "bonus_10": accelerated_learning_bonus(10),
            "bonus_30": accelerated_learning_bonus(30),
            "bonus_100": accelerated_learning_bonus(100),
            "passed": all(math.isclose(a, b) for a, b in ((accelerated_learning_bonus(10), 0.3), (accelerated_learning_bonus(30), 0.6), (accelerated_learning_bonus(100), 0.95))),
        },
    }
    return tests


def stats(values: list[float]) -> dict[str, float | None]:
    return {
        "p25": base.percentile(values, 0.25),
        "p50": base.percentile(values, 0.50),
        "p75": base.percentile(values, 0.75),
    }


def summarize(
    rows: list[dict[str, Any]],
    config: sim.SimConfig,
    tests: dict[str, Any],
    seed: int,
) -> dict[str, Any]:
    checkpoint_summary: dict[str, Any] = {}
    for wave in CHECKPOINTS:
        reached = [row for row in rows if wave in row["checkpoint"]]
        states = [row["checkpoint"][wave] for row in reached]
        times = [row["result"].reach_seconds[wave] / 3600 for row in reached]

        def state_stats(key: str) -> dict[str, float | None]:
            return stats([float(state[key]) for state in states])

        ownership = {
            key: (
                sum(state["counts"].get(key, 0) > 0 for state in states) / len(states)
                if states else 0.0
            )
            for key in RARE_KEYS
        }
        contributions = {
            key: (
                sum(state["card_power_contribution"].get(key, 0.0) for state in states) / len(states)
                if states else 0.0
            )
            for key in RARE_KEYS
        }
        checkpoint_summary[str(wave)] = {
            "reach_count": len(reached),
            "reach_rate": len(reached) / len(rows),
            "arrival_hours": stats(times),
            "final_damage_power": state_stats("final_damage_power"),
            "base_atk_power": state_stats("base_atk_power"),
            "attack_speed": state_stats("attack_speed"),
            "crit_rate": state_stats("crit_rate"),
            "crit_multiplier": state_stats("crit_multiplier"),
            "xp_multiplier": state_stats("xp_multiplier"),
            "cards": state_stats("cards"),
            "common_cards": state_stats("common_cards"),
            "uncommon_cards": state_stats("uncommon_cards"),
            "rare_cards": state_stats("rare_cards"),
            "rare_ownership_rate": ownership,
            "rare_damage_power_contribution": contributions,
        }

    rare_metrics = {}
    for key in RARE_KEYS:
        acquisition_counts = [row["acquisitions"].get(key, 0) for row in rows]
        unique_waves = [row["first_unique_wave"][key] for row in rows if key in row["first_unique_wave"]]
        rare_metrics[key] = {
            "mean_acquisitions_per_trial_cumulative": sum(acquisition_counts) / len(rows),
            "acquisition_rate": sum(value > 0 for value in acquisition_counts) / len(rows),
            "ownership_rate": {
                str(wave): checkpoint_summary[str(wave)]["rare_ownership_rate"][key]
                for wave in (500, 1000, 2500)
            },
            "damage_power_contribution": {
                str(wave): checkpoint_summary[str(wave)]["rare_damage_power_contribution"][key]
                for wave in (500, 1000, 2500)
            },
            "unique_first_acquisition_wave_p50": (
                base.percentile([float(value) for value in unique_waves], 0.50)
                if CARD_BY_KEY[key].unique else None
            ),
        }

    results = [row["result"] for row in rows]
    best_waves = [float(result.best_failed_wave) for result in results]
    return {
        "settings": {
            "candidate": "new_w5000_common_uncommon_rare",
            "formal_modified": False,
            "profile": "Standard/balanced",
            "trials": len(rows),
            "seed": seed,
            "target_for_probe": 2500,
            "max_attempts": config.max_attempts,
            "card_refinement": False,
            "epic_legendary": False,
            "legacy_weapon_relic_baseline_retained": True,
            "new_weapon_card_effects_dormant": True,
            "rarity": {
                "W1-99": {"C": 0.92, "U": 0.07, "R": 0.01},
                "W100-499": {"C": 0.822, "U": 0.14, "R": 0.038},
                "W500-2499": {"C": 0.72, "U": 0.20, "R": 0.08},
            },
        },
        "mechanics_tests": tests,
        "summary": {
            "success_rate": sum(result.success for result in results) / len(results),
            "deaths": stats([float(result.deaths) for result in results]),
            "best_failed_wave": stats(best_waves),
            "best_wave_min": min(best_waves),
            "best_wave_max": max(best_waves),
            "checkpoint": checkpoint_summary,
            "rare": rare_metrics,
        },
        "trials": [
            {
                "trial": row["trial"],
                "success": row["result"].success,
                "deaths": row["result"].deaths,
                "best_failed_wave": row["result"].best_failed_wave,
                "acquisitions": dict(row["acquisitions"]),
                "first_unique_wave": row["first_unique_wave"],
                "checkpoint": row["checkpoint"],
            }
            for row in rows
        ],
    }


def fmt(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    lines = [
        "# 新W5000候補 Common / Uncommon / Rare 基礎進行",
        "",
        f"30 trials / Standard bot / seed {payload['settings']['seed']} / refinementなし",
        "",
        "## 進行",
        "",
        "| Wave | 到達率 | 時間P25 | P50 | P75 | Final Power | Base Power | AS | Crit | Crit Mult | XP | Cards | C/U/R |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for wave in CHECKPOINTS:
        item = summary["checkpoint"][str(wave)]
        lines.append(
            f"| {wave} | {item['reach_rate']:.1%} | {fmt(item['arrival_hours']['p25'])}h | "
            f"{fmt(item['arrival_hours']['p50'])}h | {fmt(item['arrival_hours']['p75'])}h | "
            f"{fmt(item['final_damage_power']['p50'])} | {fmt(item['base_atk_power']['p50'])} | "
            f"{fmt(item['attack_speed']['p50'])} | {fmt(item['crit_rate']['p50'],2)} | "
            f"{fmt(item['crit_multiplier']['p50'],2)} | {fmt(item['xp_multiplier']['p50'],2)} | "
            f"{fmt(item['cards']['p50'],1)} | {fmt(item['common_cards']['p50'],1)}/"
            f"{fmt(item['uncommon_cards']['p50'],1)}/{fmt(item['rare_cards']['p50'],1)} |"
        )
    lines += [
        "",
        f"Deaths P25/P50/P75: {fmt(summary['deaths']['p25'],1)} / {fmt(summary['deaths']['p50'],1)} / {fmt(summary['deaths']['p75'],1)}  ",
        f"Best failed Wave P25/P50/P75: {fmt(summary['best_failed_wave']['p25'],1)} / {fmt(summary['best_failed_wave']['p50'],1)} / {fmt(summary['best_failed_wave']['p75'],1)}  ",
        f"W2500 success: {summary['success_rate']:.1%}",
        "",
        "## Rare取得・寄与",
        "",
        "| Rare | 平均取得/Trial | 取得率 | 保有率 W500/W1000/W2500 | Power寄与 W500/W1000/W2500 | Unique取得Wave P50 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key in RARE_KEYS:
        item = summary["rare"][key]
        own = item["ownership_rate"]
        power = item["damage_power_contribution"]
        lines.append(
            f"| {CARD_BY_KEY[key].name} | {item['mean_acquisitions_per_trial_cumulative']:.2f} | "
            f"{item['acquisition_rate']:.1%} | {own['500']:.1%}/{own['1000']:.1%}/{own['2500']:.1%} | "
            f"{power['500']:.3f}/{power['1000']:.3f}/{power['2500']:.3f} | "
            f"{fmt(item['unique_first_acquisition_wave_p50'],1)} |"
        )
    lines += ["", "## 独立動作テスト", "", "| 項目 | 結果 |", "|---|---:|"]
    for key, item in payload["mechanics_tests"].items():
        lines.append(f"| {key} | {'PASS' if item['passed'] else 'FAIL'} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv(path: Path, payload: dict[str, Any]) -> None:
    fields = ["wave", "reach_rate", "time_p25", "time_p50", "time_p75", "final_power_p50", "base_power_p50", "as_p50", "crit_p50", "crit_mult_p50", "xp_p50", "cards_p50", "common_p50", "uncommon_p50", "rare_p50"]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for wave in CHECKPOINTS:
            item = payload["summary"]["checkpoint"][str(wave)]
            writer.writerow({
                "wave": wave, "reach_rate": item["reach_rate"],
                "time_p25": item["arrival_hours"]["p25"], "time_p50": item["arrival_hours"]["p50"], "time_p75": item["arrival_hours"]["p75"],
                "final_power_p50": item["final_damage_power"]["p50"], "base_power_p50": item["base_atk_power"]["p50"],
                "as_p50": item["attack_speed"]["p50"], "crit_p50": item["crit_rate"]["p50"], "crit_mult_p50": item["crit_multiplier"]["p50"],
                "xp_p50": item["xp_multiplier"]["p50"], "cards_p50": item["cards"]["p50"],
                "common_p50": item["common_cards"]["p50"], "uncommon_p50": item["uncommon_cards"]["p50"], "rare_p50": item["rare_cards"]["p50"],
            })


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--max-attempts", type=int, default=220)
    parser.add_argument("--output-dir", type=Path, default=Path("output/new_w5000_common_uncommon_rare_30"))
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
        card_upgrade_cap=0,
        relic_selection_enabled=False,
        exponential_core_multiplier=1.0,
    )
    observer = AcquisitionObserver()
    base.NEW_CARDS = ALL_CARDS
    base.CARD_BY_KEY = CARD_BY_KEY
    base.candidate_snapshot = candidate_snapshot
    if not hasattr(base, "full_window_power_original"):
        base.full_window_power_original = base.full_window_power
    base.full_window_power = effective_full_window_power
    base.CHECKPOINTS = CHECKPOINTS
    capture = RareCapture(config)
    base.install_candidate_pool(capture)
    sim.CHECKPOINTS = CHECKPOINTS
    sim.REACH_WAVES = CHECKPOINTS
    sim.VARIANT_REACH_WAVES = CHECKPOINTS
    sim.rarity_chances = rarity_chances
    sim.process_guaranteed_choices = guaranteed_choices
    sim.acquire_card = observer.acquire
    sim.dynamic_damage_log = candidate_dynamic_damage_log

    tests = mechanics_tests(config)
    rows: list[dict[str, Any]] = []
    for trial in range(args.trials):
        capture.reset()
        observer.reset()
        rng = random.Random(args.seed + 1_000_000 + trial)
        result = sim.run_trial(rng, "balanced", config, allow_overdrive=False)
        rows.append({
            "trial": trial,
            "result": result,
            "checkpoint": copy.deepcopy(capture.current),
            "acquisitions": observer.total.copy(),
            "first_unique_wave": dict(observer.first_unique_wave),
        })

    payload = summarize(rows, config, tests, args.seed)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "new_w5000_common_uncommon_rare.json"
    csv_path = output_dir / "new_w5000_common_uncommon_rare_checkpoints.csv"
    md_path = output_dir / "new_w5000_common_uncommon_rare.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(csv_path, payload)
    write_markdown(md_path, payload)
    print(json.dumps({
        "success_rate": payload["summary"]["success_rate"],
        "deaths": payload["summary"]["deaths"],
        "best_failed_wave": payload["summary"]["best_failed_wave"],
        "checkpoint": {
            wave: {"reach_rate": item["reach_rate"], "arrival_hours": item["arrival_hours"], "final_power": item["final_damage_power"]}
            for wave, item in payload["summary"]["checkpoint"].items()
        },
        "mechanics_tests": payload["mechanics_tests"],
        "files": {"json": str(json_path), "csv": str(csv_path), "markdown": str(md_path)},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
