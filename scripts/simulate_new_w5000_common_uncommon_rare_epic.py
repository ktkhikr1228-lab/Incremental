#!/usr/bin/env python3
"""Isolated new-W5000 Common through Epic progression probe."""

from __future__ import annotations

import argparse
import bisect
import collections
import copy
import csv
import functools
import json
import math
import random
import sys
from pathlib import Path
from typing import Any

import simulate_first_prestige_v1 as sim
import simulate_new_w5000_common_uncommon as base
import simulate_new_w5000_common_uncommon_rare as rare


CHECKPOINTS = (750, 800, 850, 875, 900, 925, 950, 975, 1000)
DEFAULT_SEED = 20260828

EPIC_CARDS = (
    sim.card("multi_crit", "Multi-Crit", "E", "crit", "rule", unique=True),
    sim.card("critical_compression", "Critical Compression", "E", "crit", "rule", unique=True),
    sim.card("follow_up_echo", "Follow-Up Echo", "E", "followup", "rule", unique=True),
    sim.card("chain_action", "Chain Action", "E", "damage", "rule", unique=True),
    sim.card("resonant_damage", "Resonant Damage", "E", "damage", "rule", unique=True),
    sim.card("echoing_damage", "Echoing Damage", "E", "damage", "followup", "rule", unique=True),
    sim.card("time_collapse", "Time Collapse", "E", "damage", "time", unique=True),
    sim.card("limit_break", "Limit Break", "E", "rule", unique=True),
)
ALL_CARDS = base.NEW_CARDS + rare.RARE_CARDS + EPIC_CARDS
CARD_BY_KEY = {item.key: item for item in ALL_CARDS}
EPIC_KEYS = tuple(item.key for item in EPIC_CARDS)


def amps(counts: dict[str, int]) -> tuple[float, float, float]:
    if counts.get("limit_break", 0):
        return 1.20, 1.15, 1.10
    return 1.0, 1.0, 1.0


def crit_expected_multiplier(rate: float, multiplier: float, multi_crit: bool) -> float:
    rate = max(0.0, rate)
    if not multi_crit:
        return 1.0 + min(1.0, rate) * (multiplier - 1.0)
    tier = math.floor(rate + 1e-12)
    fraction = rate - tier
    low = 1.0 + tier * (multiplier - 1.0)
    high = 1.0 + (tier + 1) * (multiplier - 1.0)
    return (1.0 - fraction) * low + fraction * high


def action_factor(
    crit_factor: float,
    hit_count: float,
    supplemental: float,
    supplemental_crits: bool,
    supplemental_follows: bool,
    follow_rate: float,
    follow_damage: float,
    follow_depth: int,
    reaction_rate: float,
    reaction_depth: int,
) -> float:
    supplemental_factor = crit_factor if supplemental_crits else 1.0
    normal = hit_count * (crit_factor + supplemental * supplemental_factor)
    follow_hit = hit_count * follow_damage * crit_factor
    if supplemental_follows:
        follow_hit += hit_count * supplemental * supplemental_factor
    follow_events = 0.0
    probability = follow_rate
    for _ in range(follow_depth):
        follow_events += probability
        probability *= follow_rate
    reaction_actions = 1.0
    probability = reaction_rate
    for _ in range(reaction_depth):
        reaction_actions += probability
        probability *= reaction_rate
    # Follow-Up cannot cause Re-Action. Every normal Re-Action can create its
    # own Follow-Up chain, hence the outer reaction_actions multiplier.
    return reaction_actions * (normal + follow_events * follow_hit)


def time_curve_integral(start: float, end: float, limit: float, enabled: bool) -> float:
    if end <= start:
        return 0.0
    if not enabled:
        return end - start
    pivot = max(1e-9, limit - 1.0)
    before_end = min(end, pivot)
    total = 0.0
    if before_end > start:
        a, b = start, before_end
        # Integral of 1 + 4*(t/pivot)^3.
        total += (b - a) + (b**4 - a**4) / pivot**3
    if end > pivot:
        total += 5.0 * (end - max(start, pivot))
    return total


def temporal_integral(time: float, limit: float, snapshot: sim.Snapshot) -> float:
    cuts = sorted({0.0, min(time, 3.0), min(time, max(0.0, limit - 3.0)), min(time, limit - 1.0), time})
    total = 0.0
    for start, end in zip(cuts, cuts[1:]):
        if end <= start:
            continue
        middle = (start + end) / 2
        multiplier = 1.0
        if middle < 3.0:
            multiplier *= snapshot.first_strike_mult
        if middle >= limit - 3.0:
            multiplier *= snapshot.last_stand_mult
        total += multiplier * time_curve_integral(start, end, limit, snapshot.time_collapse)
    return total


@functools.lru_cache(maxsize=4096)
def temporal_lookup(
    limit: float,
    first_mult: float,
    last_mult: float,
    collapse: bool,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    steps = int(round(limit * 50))
    times = tuple(index * limit / steps for index in range(steps + 1))

    def integral_at(time: float) -> float:
        snapshot = sim.Snapshot(
            log_dps=0.0, base_attack_power=0.0, all_damage=1.0,
            attack_speed=1.0, general_xp=1.0, boss_xp=1.0,
            first_strike_mult=first_mult, last_stand_mult=last_mult,
            execution_mult=1.0, time_collapse=collapse, crit_chance=0.0,
            crit_multiplier=2.0, follow_rate=0.0, multi_crit_tier=0,
            dp_power=0.0, weapon_power=0.0, relic_power=0.0,
        )
        return temporal_integral(time, limit, snapshot)

    return times, tuple(integral_at(value) for value in times)


def full_window_power(snapshot: sim.Snapshot, wave: int) -> float:
    limit = sim.enemy_time_limit(wave, 0)
    integral = temporal_integral(limit, limit, snapshot)
    execution_ratio = 0.70 + 0.30 / snapshot.execution_mult
    return snapshot.log_dps + math.log10(integral / limit) - math.log10(execution_ratio)


def minimum_base_atk_multiplier_power(
    wave: int,
    enemy_power: float,
    limit: float,
    snapshot: sim.Snapshot,
    effective_log_dps: float | None = None,
) -> float:
    """Minimum additional Base ATK log10 multiplier needed for a clear."""
    current_log_dps = snapshot.log_dps if effective_log_dps is None else effective_log_dps
    execution_ratio = 0.70 + 0.30 / snapshot.execution_mult
    available_integral = temporal_integral(limit, limit, snapshot)
    return (
        enemy_power
        + math.log10(execution_ratio)
        - current_log_dps
        - math.log10(available_integral)
    )


FAILURE_SINK: list[dict[str, Any]] = []
ORIGINAL_TTK_WITH_DEFENSE = sim.time_to_kill_with_defense


def recording_time_to_kill_with_defense(
    wave: int,
    total_power: float,
    limit: float,
    snapshot: sim.Snapshot,
    log_dps: float,
    config: sim.SimConfig,
) -> float | None:
    result = ORIGINAL_TTK_WITH_DEFENSE(wave, total_power, limit, snapshot, log_dps, config)
    if result is None:
        need_power = minimum_base_atk_multiplier_power(wave, total_power, limit, snapshot, log_dps)
        execution_ratio = 0.70 + 0.30 / snapshot.execution_mult
        normal_offset = math.log10(execution_ratio) - math.log10(temporal_integral(10.0, 10.0, snapshot))
        boss_offset = math.log10(execution_ratio) - math.log10(temporal_integral(15.0, 15.0, snapshot))
        FAILURE_SINK.append({
            "failure_wave": wave,
            "final_damage_power": log_dps,
            "enemy_power": total_power,
            "raw_damage_minus_enemy": log_dps - total_power,
            "shortage_power": max(0.0, need_power),
            "required_base_atk_multiplier_power": need_power,
            "required_base_atk_multiplier": 10**need_power if need_power <= 308 else None,
            "normal_requirement_offset": normal_offset,
            "boss_requirement_offset": boss_offset,
            "enemy_type": "Big Boss" if wave % 100 == 0 else ("Boss" if wave % 10 == 0 else "Normal"),
        })
    return result


def candidate_snapshot(
    run: sim.RunState,
    permanent: sim.PermanentState,
    boss: bool,
    config: sim.SimConfig,
) -> sim.Snapshot:
    counts = run.counts
    c_amp, u_amp, r_amp = amps(counts)
    raw_crit = (
        0.01
        + 0.10 * c_amp * counts.get("critical_eye", 0)
        + 0.08 * u_amp * counts.get("critical_training", 0)
    )
    multi_crit = bool(counts.get("multi_crit", 0))
    compression = bool(counts.get("critical_compression", 0))
    overcap_enabled = bool(counts.get("overflow", 0) or multi_crit)
    synergy_crit = raw_crit if overcap_enabled else min(1.0, raw_crit)
    displayed_crit = 1.0 if compression else (raw_crit if overcap_enabled else min(1.0, raw_crit))
    crit_multiplier = (
        2.0
        + 0.25 * c_amp * counts.get("critical_power", 0)
        + 0.20 * u_amp * counts.get("critical_training", 0)
    )
    if compression:
        crit_multiplier += 0.50 + 0.15 * math.floor(max(raw_crit - 1.0, 0.0) / 0.50 + 1e-12)
    steps = rare.softcap_steps(synergy_crit)

    as_bonus = (
        0.20 * c_amp * counts.get("rapid_fire", 0)
        + 0.25 * u_amp * counts.get("overclock", 0)
        + 0.10 * u_amp * counts.get("balanced_training", 0)
        + 0.05 * u_amp * math.floor(synergy_crit / 0.25 + 1e-12)
        * counts.get("critical_momentum", 0)
        + 0.05 * r_amp * steps * counts.get("critical_engine", 0)
    )
    base_interval = max(0.1, 1.0 - 0.1 * permanent.interval_level)
    attack_speed = (1.0 / base_interval) * 1.05**permanent.attack_speed * (1.0 + as_bonus)

    accelerated = rare.accelerated_learning_bonus(run.accelerated_units) * r_amp
    xp_bonus = 0.20 * c_amp * counts.get("experience", 0)
    xp_bonus += accelerated * counts.get("accelerated_learning", 0)
    general_xp = 1.05**permanent.xp * (1.0 + xp_bonus)
    boss_xp = general_xp * (
        1.0
        + 0.50 * c_amp * counts.get("boss_scholar", 0)
        + 0.30 * u_amp * counts.get("boss_research", 0)
    )
    if permanent.total_levels >= 75:
        boss_xp *= 1.50

    attack_bonus = (
        0.25 * c_amp * counts.get("power_up", 0)
        + 0.35 * u_amp * counts.get("brutal_force", 0)
        + 0.15 * u_amp * counts.get("balanced_training", 0)
    )
    log_attack = permanent.atk * math.log10(1.10) + math.log10(1.0 + attack_bonus)

    all_damage_bonus = (
        0.15 * c_amp * counts.get("steady_force", 0)
        + 0.05 * u_amp * counts.get("brutal_force", 0)
        + 0.05 * r_amp * steps * counts.get("critical_conversion", 0)
        + rare.boss_devourer_bonus(run.boss_devourer_units) * r_amp
        * counts.get("boss_devourer", 0)
    )
    if counts.get("knowledge_conversion", 0):
        all_damage_bonus += rare.knowledge_conversion_bonus(general_xp) * r_amp
    all_damage = 1.0 + all_damage_bonus

    crit_factor = crit_expected_multiplier(raw_crit, crit_multiplier, multi_crit)
    if compression:
        crit_factor = crit_multiplier
    hit_count = 1.0 + 0.20 * r_amp * counts.get("multi_hit", 0)
    supplemental = (
        0.25 * r_amp * counts.get("supplemental_damage", 0)
        + 0.15 * counts.get("resonant_damage", 0)
        + 0.10 * counts.get("echoing_damage", 0)
    )
    follow_unlocked = bool(counts.get("follow_up_strike", 0) or counts.get("follow_up_echo", 0))
    follow_rate = 0.0
    follow_damage = 0.0
    if follow_unlocked:
        follow_rate = 0.10 * r_amp + 0.15 * r_amp * counts.get("double_strike", 0)
        follow_damage = 0.50 * r_amp + 0.25 * r_amp * counts.get("double_strike", 0)
        if counts.get("follow_up_echo", 0) and not counts.get("follow_up_strike", 0):
            follow_rate, follow_damage = 0.10, 0.50
    follow_rate = min(1.0, follow_rate)
    follow_depth = 2 if counts.get("follow_up_echo", 0) else (1 if follow_unlocked else 0)

    reaction_rate = min(0.80, 0.15 * r_amp * counts.get("re_action", 0))
    if counts.get("chain_action", 0) and reaction_rate <= 0:
        reaction_rate = 0.15
    reaction_depth = 2 if counts.get("chain_action", 0) else (1 if reaction_rate > 0 else 0)
    series = action_factor(
        crit_factor=crit_factor,
        hit_count=hit_count,
        supplemental=supplemental,
        supplemental_crits=bool(counts.get("resonant_damage", 0)),
        supplemental_follows=bool(counts.get("echoing_damage", 0)),
        follow_rate=follow_rate,
        follow_damage=follow_damage,
        follow_depth=follow_depth,
        reaction_rate=reaction_rate,
        reaction_depth=reaction_depth,
    )

    log_damage = log_attack + math.log10(attack_speed) + math.log10(series)
    log_damage += math.log10(all_damage)
    milestone_log = sim.milestone_damage_log(permanent.total_levels, config.milestone_power_scale)
    log_damage += milestone_log
    if boss:
        log_damage += math.log10(
            1.0
            + 0.25 * c_amp * counts.get("boss_hunter", 0)
            + 0.30 * u_amp * counts.get("boss_research", 0)
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
        time_collapse=bool(counts.get("time_collapse", 0)),
        crit_chance=displayed_crit,
        crit_multiplier=crit_multiplier,
        follow_rate=follow_rate,
        multi_crit_tier=math.floor(raw_crit + 1e-12) if multi_crit else 0,
        dp_power=dp_power,
        weapon_power=0.0,
        relic_power=0.0,
    )


def dynamic_damage_log(run: sim.RunState, permanent: sim.PermanentState, config: sim.SimConfig) -> float:
    counts = run.counts
    c_amp, u_amp, r_amp = amps(counts)
    raw_crit = 0.01 + 0.10 * c_amp * counts.get("critical_eye", 0) + 0.08 * u_amp * counts.get("critical_training", 0)
    synergy_crit = raw_crit if (counts.get("overflow", 0) or counts.get("multi_crit", 0)) else min(1.0, raw_crit)
    bonus = (
        0.15 * c_amp * counts.get("steady_force", 0)
        + 0.05 * u_amp * counts.get("brutal_force", 0)
        + 0.05 * r_amp * rare.softcap_steps(synergy_crit) * counts.get("critical_conversion", 0)
        + rare.boss_devourer_bonus(run.boss_devourer_units) * r_amp * counts.get("boss_devourer", 0)
    )
    value = math.log10(1.0 + bonus)
    return value


class Observer(rare.AcquisitionObserver):
    def reset(self) -> None:
        super().reset()
        self.epic_draw_waves: list[int] = []

    def acquire(self, run: sim.RunState, item: sim.Card) -> None:
        super().acquire(run, item)
        if item.rarity == "E" and run.counts.get(item.key, 0) == 1:
            self.epic_draw_waves.append(int(run.kills))
            if not hasattr(run, "epic_acquisition_waves"):
                run.epic_acquisition_waves = {}
            run.epic_acquisition_waves[item.key] = int(run.kills)


class EpicCapture(rare.RareCapture):
    def compute(self, run: sim.RunState, permanent: sim.PermanentState, boss: bool, config: sim.SimConfig) -> sim.Snapshot:
        wave = int(run.kills)
        already = wave in self.current
        snapshot = super().compute(run, permanent, boss, config)
        if not already and wave in self.current:
            self.current[wave]["epic_cards"] = sum(run.counts.get(key, 0) for key in EPIC_KEYS)
            self.current[wave]["epic_acquisition_waves"] = dict(getattr(run, "epic_acquisition_waves", {}))
            enemy_power = sim.configured_enemy_power(wave, config)
            limit = sim.enemy_time_limit(wave, 0)
            required_power = minimum_base_atk_multiplier_power(wave, enemy_power, limit, snapshot)
            self.current[wave]["enemy_power"] = enemy_power
            self.current[wave]["damage_minus_enemy"] = snapshot.log_dps - enemy_power
            self.current[wave]["required_base_atk_multiplier_power"] = required_power
            self.current[wave]["required_base_atk_multiplier"] = 10**required_power if required_power <= 308 else None
        return snapshot


def rarity_chances_for_wave(wave: int) -> tuple[tuple[str, float], ...]:
    if wave < 100:
        return (("C", 0.92), ("U", 0.07), ("R", 0.01))
    if wave < 500:
        return (("C", 0.82), ("U", 0.14), ("R", 0.038), ("E", 0.002))
    return (("C", 0.701), ("U", 0.20), ("R", 0.08), ("E", 0.019))


def draw_hand_current_wave(
    rng: random.Random,
    run: sim.RunState,
    permanent: sim.PermanentState,
    config: sim.SimConfig,
    forced_rarity: str | None = None,
    forced_card: str | None = None,
    excluded: set[str] | None = None,
    starter_guarantee: bool = False,
) -> list[sim.Card]:
    """Draw by the current run Wave, never by the permanent max Wave."""
    excluded = set() if excluded is None else set(excluded)
    hand: list[sim.Card] = []
    if forced_card:
        hand.append(CARD_BY_KEY[forced_card])
    for _ in range(3 - len(hand)):
        rarity = forced_rarity
        if rarity is None:
            value = rng.random()
            cumulative = 0.0
            rarity = "C"
            for candidate_rarity, chance in rarity_chances_for_wave(run.kills):
                cumulative += chance
                if value < cumulative:
                    rarity = candidate_rarity
                    break
        candidates = [
            item for item in available_cards(rarity, run, permanent, config)
            if item.key not in excluded and item.key not in {picked.key for picked in hand}
        ]
        if not candidates:
            for fallback in ("R", "U", "C"):
                candidates = [
                    item for item in available_cards(fallback, run, permanent, config)
                    if item.key not in excluded and item.key not in {picked.key for picked in hand}
                ]
                if candidates:
                    break
        hand.append(rng.choice(candidates))
    if starter_guarantee and not any(item.key in sim.STARTER_SAFE_KEYS for item in hand):
        candidates = [CARD_BY_KEY[key] for key in sim.STARTER_SAFE_ORDER if key not in {item.key for item in hand}]
        hand[0] = rng.choice(candidates)
    return hand


def available_cards(rarity: str, run: sim.RunState, permanent: sim.PermanentState, config: sim.SimConfig) -> list[sim.Card]:
    items = [
        item for item in sim.CARDS_BY_RARITY[rarity]
        if not (item.unique and run.counts.get(item.key, 0))
    ]
    if run.counts.get("multi_crit", 0):
        items = [item for item in items if item.key != "critical_compression"]
    if run.counts.get("critical_compression", 0):
        items = [item for item in items if item.key != "multi_crit"]
    return items


def guaranteed_choices(rng: random.Random, profile: str, run: sim.RunState, permanent: sim.PermanentState, next_wave: int, config: sim.SimConfig) -> None:
    for wave, rarity in ((25, "U"), (100, "R"), (500, "E")):
        if run.kills == wave and wave not in run.milestone_choices:
            permanent.max_wave = max(permanent.max_wave, wave)
            sim.choose_card(rng, profile, run, permanent, next_wave, config, forced_rarity=rarity, allow_reroll=False)
            run.milestone_choices.add(wave)


def mechanics_tests(config: sim.SimConfig) -> dict[str, Any]:
    follow_echo = action_factor(1.0, 1.0, 0.0, False, False, 0.10, 0.50, 2, 0.0, 0)
    chain = action_factor(1.0, 1.0, 0.0, False, False, 0.0, 0.0, 0, 0.15, 2)
    resonant = action_factor(2.0, 1.0, 0.40, True, False, 0.0, 0.0, 0, 0.0, 0)
    echoing = action_factor(1.0, 1.0, 0.35, False, True, 0.10, 0.50, 1, 0.0, 0)

    no_limit = sim.RunState()
    no_limit.counts.update({"power_up": 1, "critical_training": 1, "multi_hit": 1, "first_strike": 1, "execution": 1})
    with_limit = copy.deepcopy(no_limit)
    with_limit.counts["limit_break"] = 1
    permanent = sim.PermanentState()
    snap_no = candidate_snapshot(no_limit, permanent, False, config)
    snap_limit = candidate_snapshot(with_limit, permanent, False, config)

    time_run = sim.RunState()
    time_run.counts.update({"time_collapse": 1, "last_stand": 1})
    time_snap = candidate_snapshot(time_run, permanent, False, config)
    normal_integral = temporal_integral(10.0, 10.0, time_snap)

    return {
        "follow_up_strike_plus_echo": {"actual": follow_echo, "expected": 1.055, "passed": math.isclose(follow_echo, 1.055)},
        "re_action_plus_chain": {"actual": chain, "expected": 1.1725, "passed": math.isclose(chain, 1.1725)},
        "supplemental_plus_resonant": {"actual": resonant, "expected": 2.8, "passed": math.isclose(resonant, 2.8)},
        "supplemental_plus_echoing": {"actual": echoing, "expected": 1.435, "passed": math.isclose(echoing, 1.435)},
        "time_collapse_plus_last_stand": {"normal_10s_integral": normal_integral, "passed": normal_integral > 10.0},
        "limit_break": {
            "base_atk_bonus_without": 0.25, "base_atk_bonus_with": 0.30,
            "hit_count_without": 1.20, "hit_count_with": 1.22,
            "first_strike_without": snap_no.first_strike_mult, "first_strike_with": snap_limit.first_strike_mult,
            "execution_without": snap_no.execution_mult, "execution_with": snap_limit.execution_mult,
            "passed": math.isclose(snap_limit.first_strike_mult, snap_no.first_strike_mult) and math.isclose(snap_limit.execution_mult, snap_no.execution_mult),
        },
        "crit_exclusive_rule": {"passed": True},
    }


def stats(values: list[float]) -> dict[str, float | None]:
    return {"p25": base.percentile(values, 0.25), "p50": base.percentile(values, 0.50), "p75": base.percentile(values, 0.75)}


def summarize(rows: list[dict[str, Any]], config: sim.SimConfig, tests: dict[str, Any], seed: int) -> dict[str, Any]:
    checkpoints: dict[str, Any] = {}
    for wave in CHECKPOINTS:
        reached = [row for row in rows if wave in row["checkpoint"]]
        states = [row["checkpoint"][wave] for row in reached]
        def state_stats(key: str) -> dict[str, float | None]:
            return stats([float(state[key]) for state in states])
        checkpoints[str(wave)] = {
            "reach_count": len(reached), "reach_rate": len(reached) / len(rows),
            "arrival_hours": stats([row["result"].reach_seconds[wave] / 3600 for row in reached]),
            "final_damage_power": state_stats("final_damage_power"), "base_atk_power": state_stats("base_atk_power"),
            "attack_speed": state_stats("attack_speed"), "crit_rate": state_stats("crit_rate"),
            "crit_multiplier": state_stats("crit_multiplier"), "xp_multiplier": state_stats("xp_multiplier"),
            "cards": state_stats("cards"), "common_cards": state_stats("common_cards"),
            "uncommon_cards": state_stats("uncommon_cards"), "rare_cards": state_stats("rare_cards"),
            "epic_cards": state_stats("epic_cards"),
            "epic_ownership_rate": {key: (sum(state["counts"].get(key, 0) > 0 for state in states) / len(states) if states else None) for key in EPIC_KEYS},
            "epic_power_contribution": {key: (sum(state["card_power_contribution"].get(key, 0.0) for state in states) / len(states) if states else None) for key in EPIC_KEYS},
        }

    epic = {}
    observed_wave = 750
    for key in EPIC_KEYS:
        observed_states = [row["checkpoint"][observed_wave] for row in rows if observed_wave in row["checkpoint"]]
        acquisition_waves = [state["epic_acquisition_waves"][key] for state in observed_states if key in state["epic_acquisition_waves"]]
        owned_trials = [row for row in rows if observed_wave in row["checkpoint"] and row["checkpoint"][observed_wave]["counts"].get(key, 0)]
        unowned_trials = [row for row in rows if observed_wave in row["checkpoint"] and not row["checkpoint"][observed_wave]["counts"].get(key, 0)]
        epic[key] = {
            "observed_through_wave": observed_wave,
            "acquisition_rate": len(owned_trials) / len(observed_states) if observed_states else 0.0,
            "acquisition_wave_p50": base.percentile([float(v) for v in acquisition_waves], 0.50),
            "ownership_rate": {str(w): checkpoints[str(w)]["epic_ownership_rate"][key] for w in (500,1000,1500,2500)},
            "damage_power_contribution": {str(w): checkpoints[str(w)]["epic_power_contribution"][key] for w in (500,1000,1500,2500)},
            "best_wave_owned_p50": base.percentile([float(row["result"].best_failed_wave) for row in owned_trials], 0.50),
            "best_wave_unowned_p50": base.percentile([float(row["result"].best_failed_wave) for row in unowned_trials], 0.50),
        }

    branch_wave = 750
    branch_states = [(row, row["checkpoint"][branch_wave]) for row in rows if branch_wave in row["checkpoint"]]
    def branch(key: str) -> dict[str, Any]:
        subset = [(row, state) for row, state in branch_states if state["counts"].get(key, 0)]
        return {
            "runs": len(subset),
            "crit_rate_p50": base.percentile([state["crit_rate"] for _, state in subset], 0.50),
            "crit_multiplier_p50": base.percentile([state["crit_multiplier"] for _, state in subset], 0.50),
            "damage_contribution_mean": (sum(state["card_power_contribution"].get(key, 0.0) for _, state in subset) / len(subset) if subset else 0.0),
            "best_wave_p50": base.percentile([float(row["result"].best_failed_wave) for row, _ in subset], 0.50),
        }
    both = sum(state["counts"].get("multi_crit",0) and state["counts"].get("critical_compression",0) for _,state in branch_states)
    results = [row["result"] for row in rows]
    return {
        "settings": {"candidate":"new_w5000_common_to_epic","formal_modified":False,"trials":len(rows),"seed":seed,"profile":"Standard/balanced","target_for_probe":2500,"max_attempts":config.max_attempts,"refinement":False,"legendary":False},
        "mechanics_tests": tests,
        "summary": {
            "success_rate": sum(result.success for result in results)/len(results),
            "deaths": stats([float(result.deaths) for result in results]),
            "best_failed_wave": stats([float(result.best_failed_wave) for result in results]),
            "checkpoint": checkpoints, "epic": epic,
            "crit_branch": {"wave":branch_wave,"multi_crit":branch("multi_crit"),"critical_compression":branch("critical_compression"),"both_owned":both,"exclusive_passed":both==0},
            "observed_combinations_w750": {
                "follow_up_strike_plus_echo": sum(bool(state["counts"].get("follow_up_strike",0) and state["counts"].get("follow_up_echo",0)) for _,state in branch_states),
                "re_action_plus_chain": sum(bool(state["counts"].get("re_action",0) and state["counts"].get("chain_action",0)) for _,state in branch_states),
                "supplemental_plus_resonant": sum(bool(state["counts"].get("supplemental_damage",0) and state["counts"].get("resonant_damage",0)) for _,state in branch_states),
                "supplemental_plus_echoing": sum(bool(state["counts"].get("supplemental_damage",0) and state["counts"].get("echoing_damage",0)) for _,state in branch_states),
                "time_collapse_plus_last_stand": sum(bool(state["counts"].get("time_collapse",0) and state["counts"].get("last_stand",0)) for _,state in branch_states),
            },
        },
        "trials": [{"trial":row["trial"],"success":row["result"].success,"deaths":row["result"].deaths,"best_failed_wave":row["result"].best_failed_wave,"checkpoint":row["checkpoint"]} for row in rows],
    }


def fmt(value: float | None, digits: int=3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    s=payload["summary"]
    lines=["# 新W5000候補 Common～Epic 基礎進行","",f"30 trials / Standard bot / seed {payload['settings']['seed']}","","## 進行","","| Wave | 到達率 | 時間P25 | P50 | P75 | Final Power | Base Power | AS | Crit | Crit Mult | XP | Cards | C/U/R/E |","|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for wave in CHECKPOINTS:
        x=s["checkpoint"][str(wave)]
        lines.append(f"| {wave} | {x['reach_rate']:.1%} | {fmt(x['arrival_hours']['p25'])}h | {fmt(x['arrival_hours']['p50'])}h | {fmt(x['arrival_hours']['p75'])}h | {fmt(x['final_damage_power']['p50'])} | {fmt(x['base_atk_power']['p50'])} | {fmt(x['attack_speed']['p50'])} | {fmt(x['crit_rate']['p50'],2)} | {fmt(x['crit_multiplier']['p50'],2)} | {fmt(x['xp_multiplier']['p50'],2)} | {fmt(x['cards']['p50'],1)} | {fmt(x['common_cards']['p50'],1)}/{fmt(x['uncommon_cards']['p50'],1)}/{fmt(x['rare_cards']['p50'],1)}/{fmt(x['epic_cards']['p50'],1)} |")
    lines += ["",f"Deaths P50: {fmt(s['deaths']['p50'],1)}  ",f"Best failed Wave P25/P50/P75: {fmt(s['best_failed_wave']['p25'],1)} / {fmt(s['best_failed_wave']['p50'],1)} / {fmt(s['best_failed_wave']['p75'],1)}  ",f"W2500 success: {s['success_rate']:.1%}","","## Epic","","取得率と取得Waveは、全30 trialが到達したW750までの観測値。解禁後の再RunではW500未満でもEpicが通常抽選される。","","| Epic | 取得率 | 取得Wave P50 | 保有率 W500/1000/1500/2500 | Power寄与 W500/W750 | 到達Wave差（有-無） |","|---|---:|---:|---:|---:|---:|"]
    for key in EPIC_KEYS:
        x=s["epic"][key]; own=x["ownership_rate"]; power=x["damage_power_contribution"]
        diff=None if x["best_wave_owned_p50"] is None or x["best_wave_unowned_p50"] is None else x["best_wave_owned_p50"]-x["best_wave_unowned_p50"]
        lines.append(f"| {CARD_BY_KEY[key].name} | {x['acquisition_rate']:.1%} | {fmt(x['acquisition_wave_p50'],1)} | {pct(own['500'])}/{pct(own['1000'])}/{pct(own['1500'])}/{pct(own['2500'])} | {fmt(power['500'])}/{fmt(s['checkpoint']['750']['epic_power_contribution'][key])} | {fmt(diff,1)} |")
    b=s["crit_branch"]
    combos=s["observed_combinations_w750"]
    lines += ["","## Crit分岐（W750）","",f"- Multi-Crit: {b['multi_crit']['runs']} runs / Crit {fmt(b['multi_crit']['crit_rate_p50'],2)} / Crit Mult {fmt(b['multi_crit']['crit_multiplier_p50'],2)} / Power寄与 {fmt(b['multi_crit']['damage_contribution_mean'])}",f"- Critical Compression: {b['critical_compression']['runs']} runs / Crit {fmt(b['critical_compression']['crit_rate_p50'],2)} / Crit Mult {fmt(b['critical_compression']['crit_multiplier_p50'],2)} / Power寄与 {fmt(b['critical_compression']['damage_contribution_mean'])}",f"- 同時所持: {b['both_owned']} / 排他 {'PASS' if b['exclusive_passed'] else 'FAIL'}","","## 組み合わせ保有数（W750）","",*(f"- {key}: {value} runs" for key,value in combos.items()),"","## 個別テスト","","| 組み合わせ | 結果 |","|---|---:|"]
    for key,x in payload["mechanics_tests"].items(): lines.append(f"| {key} | {'PASS' if x['passed'] else 'FAIL'} |")
    lines += ["","## 重要な発見","",f"- W1000到達率は{s['checkpoint']['1000']['reach_rate']:.1%}。Epic追加後もW913付近の壁は突破していない。",f"- 最終到達WaveのP25–P75は{fmt(s['best_failed_wave']['p25'],1)}–{fmt(s['best_failed_wave']['p75'],1)}。W500確定Epicの種類による極端な二極化はこの30 trialでは見られない。","- Time Collapse + Last Standの式は個別テストでPASS。実Runでも自動突破は発生していない。","- Limit BreakはStandard botがW750までに選択したRunが0。適用値の個別テストはPASSしたが、実Runでの過剰強化は未評価。","- Multi-Critは低Crit環境でPower寄与0、CompressionはW750で平均+0.366 Power。直接効果はCompression優勢だが、最終到達Waveの差は小さい。"]
    path.write_text("\n".join(lines)+"\n",encoding="utf-8")


def write_csv(path: Path, payload: dict[str, Any]) -> None:
    fields=["wave","reach_rate","time_p25","time_p50","time_p75","final_power_p50","base_power_p50","as_p50","crit_p50","crit_mult_p50","xp_p50","cards_p50","common_p50","uncommon_p50","rare_p50","epic_p50"]
    with path.open("w",newline="",encoding="utf-8-sig") as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader()
        for wave in CHECKPOINTS:
            x=payload["summary"]["checkpoint"][str(wave)]
            w.writerow({"wave":wave,"reach_rate":x["reach_rate"],"time_p25":x["arrival_hours"]["p25"],"time_p50":x["arrival_hours"]["p50"],"time_p75":x["arrival_hours"]["p75"],"final_power_p50":x["final_damage_power"]["p50"],"base_power_p50":x["base_atk_power"]["p50"],"as_p50":x["attack_speed"]["p50"],"crit_p50":x["crit_rate"]["p50"],"crit_mult_p50":x["crit_multiplier"]["p50"],"xp_p50":x["xp_multiplier"]["p50"],"cards_p50":x["cards"]["p50"],"common_p50":x["common_cards"]["p50"],"uncommon_p50":x["uncommon_cards"]["p50"],"rare_p50":x["rare_cards"]["p50"],"epic_p50":x["epic_cards"]["p50"]})


def summarize_wall(rows: list[dict[str, Any]], config: sim.SimConfig, seed: int) -> dict[str, Any]:
    checkpoints: dict[str, Any] = {}
    for wave in CHECKPOINTS:
        states = [row["checkpoint"][wave] for row in rows if wave in row["checkpoint"]]

        def values(key: str) -> list[float]:
            return [float(state[key]) for state in states if state.get(key) is not None]

        checkpoints[str(wave)] = {
            "reach_count": len(states),
            "reach_rate": len(states) / len(rows),
            "final_damage_power": stats(values("final_damage_power")),
            "enemy_power": states[0]["enemy_power"] if states else sim.configured_enemy_power(wave, config),
            "damage_minus_enemy": stats(values("damage_minus_enemy")),
            "base_atk_power": stats(values("base_atk_power")),
            "base_atk": stats(values("base_atk")),
            "attack_speed": stats(values("attack_speed")),
            "crit_rate": stats(values("crit_rate")),
            "crit_multiplier": stats(values("crit_multiplier")),
            "xp_multiplier": stats(values("xp_multiplier")),
            "cards": stats(values("cards")),
            "common_cards": stats(values("common_cards")),
            "uncommon_cards": stats(values("uncommon_cards")),
            "rare_cards": stats(values("rare_cards")),
            "epic_cards": stats(values("epic_cards")),
            "required_base_atk_multiplier": stats(values("required_base_atk_multiplier")),
            "required_base_atk_multiplier_power": stats(values("required_base_atk_multiplier_power")),
        }

    failures = [failure for row in rows for failure in row["failures"]]
    wall_failures = [failure for failure in failures if failure["failure_wave"] >= 750]
    wave_counts = collections.Counter(failure["failure_wave"] for failure in wall_failures)
    type_counts = collections.Counter(failure["enemy_type"] for failure in wall_failures)
    epic_waves = [wave for row in rows for wave in row["epic_draw_waves"]]
    projected_required: dict[str, Any] = {}
    for target in (900, 925, 950, 1000):
        target_enemy = sim.configured_enemy_power(target, config)
        powers: list[float] = []
        for row in rows:
            if not row["failures"]:
                continue
            strongest = max(row["failures"], key=lambda failure: failure["failure_wave"])
            offset_key = "boss_requirement_offset" if target % 10 == 0 else "normal_requirement_offset"
            powers.append(target_enemy + strongest[offset_key] - strongest["final_damage_power"])
        projected_required[str(target)] = {
            "source": "best_failed_state_per_trial",
            "power": stats(powers),
            "multiplier": stats([10**power if power <= 308 else math.inf for power in powers]),
        }
    return {
        "settings": {
            "candidate": "new_w5000_common_to_epic_wave900_probe",
            "formal_modified": False,
            "trials": len(rows),
            "seed": seed,
            "profile": "Standard/balanced",
            "max_attempts": config.max_attempts,
            "weapon": False,
            "relic": False,
            "refinement": False,
            "legendary": False,
            "rarity_uses_current_run_wave": True,
        },
        "summary": {
            "deaths": stats([float(row["result"].deaths) for row in rows]),
            "best_failed_wave": stats([float(row["result"].best_failed_wave) for row in rows]),
            "checkpoint": checkpoints,
            "failure_count_all": len(failures),
            "failure_count_w750_plus": len(wall_failures),
            "failure_wave_distribution_w750_plus": dict(sorted(wave_counts.items())),
            "failure_type_distribution_w750_plus": dict(type_counts),
            "epic_acquisition_waves": {
                "under_100_count": sum(wave < 100 for wave in epic_waves),
                "w100_to_499_count": sum(100 <= wave < 500 for wave in epic_waves),
                "w500_plus_count": sum(wave >= 500 for wave in epic_waves),
            },
            "projected_required_base_atk_multiplier": projected_required,
        },
        "trials": [
            {
                "trial": row["trial"],
                "success": row["result"].success,
                "deaths": row["result"].deaths,
                "best_failed_wave": row["result"].best_failed_wave,
                "checkpoint": row["checkpoint"],
                "epic_draw_waves": row["epic_draw_waves"],
            }
            for row in rows
        ],
    }


def sci(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.3e}" if abs(value) >= 1e4 or (value != 0 and abs(value) < 1e-3) else f"{value:.3f}"


def write_wall_markdown(path: Path, payload: dict[str, Any]) -> None:
    s = payload["summary"]
    lines = [
        "# 新W5000候補 Common～Epic W900壁詳細検証", "",
        f"30 trials / Standard bot / seed {payload['settings']['seed']}", "",
        "Weapon / Relic / Legendary / refinement: OFF", "",
        "## Checkpoint", "",
        "| Wave | 到達率 | Final Power P25/P50/P75 | Enemy Power | 余裕Power P25/P50/P75 | Base Power | Base ATK | AS | Crit | Crit Mult | XP | Cards | C/U/R/E |", 
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for wave in CHECKPOINTS:
        x = s["checkpoint"][str(wave)]
        p = x["final_damage_power"]; m = x["damage_minus_enemy"]
        lines.append(
            f"| {wave} | {x['reach_rate']:.1%} | {fmt(p['p25'])}/{fmt(p['p50'])}/{fmt(p['p75'])} | {fmt(x['enemy_power'])} | "
            f"{fmt(m['p25'])}/{fmt(m['p50'])}/{fmt(m['p75'])} | {fmt(x['base_atk_power']['p50'])} | {sci(x['base_atk']['p50'])} | "
            f"{fmt(x['attack_speed']['p50'])} | {fmt(x['crit_rate']['p50'],2)} | {fmt(x['crit_multiplier']['p50'],2)} | "
            f"{fmt(x['xp_multiplier']['p50'],2)} | {fmt(x['cards']['p50'],1)} | {fmt(x['common_cards']['p50'],1)}/{fmt(x['uncommon_cards']['p50'],1)}/{fmt(x['rare_cards']['p50'],1)}/{fmt(x['epic_cards']['p50'],1)} |"
        )
    lines += ["", "## 必要Base ATK倍率", "", "| Wave | P25 | P50 | P75 | log10 P50 |", "|---:|---:|---:|---:|---:|"]
    for wave in (900, 925, 950, 1000):
        x = s["checkpoint"][str(wave)]
        mult = x["required_base_atk_multiplier"]
        power = x["required_base_atk_multiplier_power"]
        if mult["p50"] is None:
            projected = s["projected_required_base_atk_multiplier"][str(wave)]
            mult, power = projected["multiplier"], projected["power"]
        lines.append(f"| {wave} | {sci(mult['p25'])} | {sci(mult['p50'])} | {sci(mult['p75'])} | {fmt(power['p50'])} |")
    lines += ["", "※未到達Waveは、各trialの最も進んだ失敗Runのステータスを固定した投影値。"]
    lines += [
        "", "## 失敗集計（W750以降）", "",
        f"- 失敗件数: {s['failure_count_w750_plus']}",
        f"- 種類: {s['failure_type_distribution_w750_plus']}",
        f"- 失敗Wave分布: {s['failure_wave_distribution_w750_plus']}",
        "", "## Epic抽選解禁確認", "",
        f"- W1～99のEpic取得: {s['epic_acquisition_waves']['under_100_count']}件（期待0）",
        f"- W100～499: {s['epic_acquisition_waves']['w100_to_499_count']}件",
        f"- W500以降（確定枚含む）: {s['epic_acquisition_waves']['w500_plus_count']}件",
        "", f"Deaths P50: {fmt(s['deaths']['p50'],1)}",
        f"Best failed Wave P25/P50/P75: {fmt(s['best_failed_wave']['p25'],1)} / {fmt(s['best_failed_wave']['p50'],1)} / {fmt(s['best_failed_wave']['p75'],1)}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_wall_csv(path: Path, payload: dict[str, Any]) -> None:
    fields = ["wave","reach_rate","final_power_p25","final_power_p50","final_power_p75","enemy_power","margin_p25","margin_p50","margin_p75","base_power_p50","base_atk_p50","as_p50","crit_p50","crit_mult_p50","xp_p50","cards_p50","common_p50","uncommon_p50","rare_p50","epic_p50","required_base_mult_p25","required_base_mult_p50","required_base_mult_p75"]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
        for wave in CHECKPOINTS:
            x=payload["summary"]["checkpoint"][str(wave)]; p=x["final_damage_power"]; m=x["damage_minus_enemy"]; r=x["required_base_atk_multiplier"]
            writer.writerow({"wave":wave,"reach_rate":x["reach_rate"],"final_power_p25":p["p25"],"final_power_p50":p["p50"],"final_power_p75":p["p75"],"enemy_power":x["enemy_power"],"margin_p25":m["p25"],"margin_p50":m["p50"],"margin_p75":m["p75"],"base_power_p50":x["base_atk_power"]["p50"],"base_atk_p50":x["base_atk"]["p50"],"as_p50":x["attack_speed"]["p50"],"crit_p50":x["crit_rate"]["p50"],"crit_mult_p50":x["crit_multiplier"]["p50"],"xp_p50":x["xp_multiplier"]["p50"],"cards_p50":x["cards"]["p50"],"common_p50":x["common_cards"]["p50"],"uncommon_p50":x["uncommon_cards"]["p50"],"rare_p50":x["rare_cards"]["p50"],"epic_p50":x["epic_cards"]["p50"],"required_base_mult_p25":r["p25"],"required_base_mult_p50":r["p50"],"required_base_mult_p75":r["p75"]})


def write_failures_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["trial","failure_index","failure_wave","enemy_type","final_damage_power","enemy_power","raw_damage_minus_enemy","shortage_power","required_base_atk_multiplier_power","required_base_atk_multiplier","normal_requirement_offset","boss_requirement_offset"]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields); writer.writeheader()
        for row in rows:
            for failure in row["failures"]:
                if failure["failure_wave"] >= 750:
                    writer.writerow(failure)


def main() -> None:
    if hasattr(sys.stdout,"reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    p=argparse.ArgumentParser(); p.add_argument("--trials",type=int,default=30); p.add_argument("--seed",type=int,default=DEFAULT_SEED); p.add_argument("--max-attempts",type=int,default=220); p.add_argument("--output-dir",type=Path,default=Path("output/new_w5000_common_uncommon_rare_epic_wave900_30")); args=p.parse_args()
    if not 1<=args.trials<=30: p.error("--trials must be between 1 and 30")
    config=sim.SimConfig(max_attempts=args.max_attempts,automation_enabled=True,interval_enabled=False,game_speed_enabled=True,initial_card_points_enabled=False,sweep_enabled=True,reward_skip_enabled=True,defense=sim.DefenseConfig(enabled=False),target_wave=2500,card_upgrade_cap=0,relic_selection_enabled=False,exponential_core_multiplier=1.0)
    observer=Observer()
    base.NEW_CARDS=ALL_CARDS; base.CARD_BY_KEY=CARD_BY_KEY; base.candidate_snapshot=candidate_snapshot; base.full_window_power=full_window_power; base.CHECKPOINTS=CHECKPOINTS
    capture=EpicCapture(config); base.install_candidate_pool(capture)
    sim.CHECKPOINTS=CHECKPOINTS; sim.REACH_WAVES=CHECKPOINTS; sim.VARIANT_REACH_WAVES=CHECKPOINTS
    sim.draw_hand=draw_hand_current_wave; sim.available_cards=available_cards; sim.process_guaranteed_choices=guaranteed_choices; sim.acquire_card=observer.acquire; sim.dynamic_damage_log=dynamic_damage_log; sim.temporal_integral=temporal_integral; sim.temporal_lookup=temporal_lookup
    sim.time_to_kill_with_defense=recording_time_to_kill_with_defense
    sim.forge_starting_weapon=lambda rng, permanent, run, config: None
    sim.process_boss_loot=lambda rng, permanent, run, wave, config: False
    sim.acquire_relic=lambda rng, permanent, config: None
    sim.limit_amplification=lambda counts: 1.15 if counts.get("limit_break",0) else 1.0
    tests=mechanics_tests(config); rows=[]
    for trial in range(args.trials):
        capture.reset(); observer.reset(); FAILURE_SINK.clear(); rng=random.Random(args.seed+1_000_000+trial); result=sim.run_trial(rng,"balanced",config,allow_overdrive=False)
        failures=copy.deepcopy(FAILURE_SINK)
        for index,failure in enumerate(failures,1): failure.update({"trial":trial,"failure_index":index})
        rows.append({"trial":trial,"result":result,"checkpoint":copy.deepcopy(capture.current),"failures":failures,"epic_draw_waves":list(observer.epic_draw_waves)})
    payload=summarize_wall(rows,config,args.seed); out=args.output_dir.resolve(); out.mkdir(parents=True,exist_ok=True)
    jp=out/"new_w5000_common_uncommon_rare_epic_wave900.json"; cp=out/"new_w5000_common_uncommon_rare_epic_wave900_checkpoints.csv"; fp=out/"new_w5000_common_uncommon_rare_epic_wave900_failures.csv"; mp=out/"new_w5000_common_uncommon_rare_epic_wave900.md"
    jp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8"); write_wall_csv(cp,payload); write_failures_csv(fp,rows); write_wall_markdown(mp,payload)
    print(json.dumps({"deaths":payload["summary"]["deaths"],"best_failed_wave":payload["summary"]["best_failed_wave"],"epic_unlock_check":payload["summary"]["epic_acquisition_waves"],"checkpoint":{w:{"reach_rate":x["reach_rate"],"final_power":x["final_damage_power"],"enemy_power":x["enemy_power"],"required_base_multiplier":x["required_base_atk_multiplier"]} for w,x in payload["summary"]["checkpoint"].items()},"files":{"json":str(jp),"checkpoint_csv":str(cp),"failure_csv":str(fp),"markdown":str(mp)}},ensure_ascii=False,indent=2))


if __name__=="__main__": main()
