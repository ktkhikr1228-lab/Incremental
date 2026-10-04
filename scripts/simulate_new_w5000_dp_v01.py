#!/usr/bin/env python3
"""Isolated DP v0.1 probe for the new W5000 candidate.

This module intentionally leaves the formal simulator untouched.  It reuses
the new Common-through-Epic card pool and B_medium deterministic weapon curve,
but owns its permanent-progression loop and DP formulas.
"""

from __future__ import annotations

import argparse
import collections
import copy
import csv
from dataclasses import dataclass, field, replace
import json
import math
import random
import sys
from pathlib import Path
from typing import Any

import simulate_first_prestige_v1 as sim
import simulate_new_w5000_common_uncommon as base
import simulate_new_w5000_common_uncommon_rare as rare
import simulate_new_w5000_common_uncommon_rare_epic as epic
import simulate_new_w5000_weapon_scale as weapon


DEFAULT_SEED = 20260828
TARGET_WAVE = 1000
MAIN_CHECKPOINTS = (100, 250, 400, 500, 600, 750, 1000)
FIFTY_CHECKPOINTS = tuple(range(50, TARGET_WAVE + 1, 50))
CHECKPOINTS = tuple(sorted(set(MAIN_CHECKPOINTS + FIFTY_CHECKPOINTS)))

UNLOCK_WAVES = {
    "base_atk": 0,
    "attack_speed": 0,
    "xp_gain": 0,
    "crit_rate": 100,
    "crit_multiplier": 250,
    "weapon_atk": 500,
    "luck": 750,
    "weapon_find": 1000,
    "weapon_quality": 1500,
}
ITEM_ORDER = tuple(UNLOCK_WAVES)
ACTIVE_IN_THIS_PROBE = {
    "base_atk", "attack_speed", "xp_gain", "crit_rate",
    "crit_multiplier", "weapon_atk", "luck",
}
GAME_SPEED_COSTS = (5000, 15000)
GAME_SPEED_MULTIPLIERS = (1.25, 1.50)
COST_WEIGHTS = {
    "base_atk": 1.00,
    "attack_speed": 1.10,
    "xp_gain": 0.90,
    "crit_rate": 1.60,
    "crit_multiplier": 2.00,
    "weapon_atk": 1.30,
    "luck": 2.20,
    "weapon_find": 2.50,
    "weapon_quality": 2.80,
}


@dataclass(frozen=True)
class Candidate:
    name: str
    base_cost: float
    cost_growth: float
    atk_per_level: float
    as_per_level: float
    xp_per_level: float
    crit_rate_per_level: float
    crit_mult_per_level: float
    weapon_atk_per_level: float
    luck_per_effective_level: float
    weapon_find_per_effective_level: float
    weapon_quality_rate: float
    death_base: int
    death_divisor: int
    record_bonus: int
    big_boss_bonus: int
    reroll_cost: int


CANDIDATES = {
    "A_conservative": Candidate(
        "A_conservative", 10.0, 1.08, .17, .120, .09, .0350, .085,
        .170, .015, .05, .030, 7, 13, 2, 2, 120,
    ),
    "B_medium": Candidate(
        "B_medium", 8.0, 1.065, .22, .170, .11, .0450, .110,
        .220, .020, .07, .040, 9, 11, 3, 3, 90,
    ),
    "C_aggressive": Candidate(
        "C_aggressive", 6.0, 1.05, .28, .220, .14, .0550, .140,
        .280, .025, .09, .050, 11, 9, 4, 4, 70,
    ),
}


@dataclass
class NewDPState:
    candidate: Candidate
    levels: dict[str, int] = field(default_factory=lambda: {key: 0 for key in ITEM_ORDER})
    unlocked_achievements: set[str] = field(default_factory=lambda: {"base_atk", "attack_speed", "xp_gain"})
    claimed_records: set[int] = field(default_factory=set)
    balance: int = 0
    total_earned: int = 0
    total_spent: int = 0
    reroll_bought: bool = False
    game_speed_level: int = 0
    game_speed_unlock_wave: int = 1250

    def reset_for_prestige(self) -> None:
        """Reset purchases/currency while preserving unlock achievements."""
        self.levels = {key: 0 for key in ITEM_ORDER}
        self.claimed_records.clear()
        self.balance = 0
        self.total_earned = 0
        self.total_spent = 0
        self.reroll_bought = False
        self.game_speed_level = 0


def state_of(permanent: sim.PermanentState) -> NewDPState:
    return permanent._new_dp_state  # type: ignore[attr-defined]


def soft_levels(level: int, first: int, second: int) -> float:
    """No hard cap: full rate, then 50%, then 20%."""
    return min(level, first) + max(min(level - first, second - first), 0) * .5 + max(level - second, 0) * .2


def luck_rarity_weight_multiplier(state: NewDPState, rarity: str) -> float:
    """Shared Card/Weapon rarity weight modifier; never changes drop rate."""
    effective = soft_levels(state.levels["luck"], 10, 25)
    bonus = state.candidate.luck_per_effective_level * effective
    rarity_scale = {"C": 0.0, "U": 1.0, "R": 1.5, "E": 2.0, "L": 2.5}.get(rarity, 0.0)
    return 1.0 + rarity_scale * bonus


def weapon_find_multiplier(state: NewDPState) -> float:
    effective = soft_levels(state.levels["weapon_find"], 10, 25)
    return 1.0 + state.candidate.weapon_find_per_effective_level * effective


def weapon_quality_floor_progress(state: NewDPState) -> float:
    """Asymptotically moves the minimum roll toward max; max is unchanged."""
    effective = soft_levels(state.levels["weapon_quality"], 10, 25)
    return 1.0 - math.exp(-state.candidate.weapon_quality_rate * effective)


def next_cost(state: NewDPState, key: str) -> int:
    level = state.levels[key]
    return math.ceil(state.candidate.base_cost * COST_WEIGHTS[key] * state.candidate.cost_growth**level)


def unlock_for_wave(state: NewDPState, max_wave: int) -> None:
    for key, gate in UNLOCK_WAVES.items():
        if max_wave >= gate:
            state.unlocked_achievements.add(key)


def death_dp(reached: int, candidate: Candidate) -> int:
    return candidate.death_base + reached // candidate.death_divisor


def award_dp_after_death(state: NewDPState, reached: int) -> dict[str, int]:
    regular = death_dp(reached, state.candidate)
    new_records = [wave for wave in range(25, reached + 1, 25) if wave not in state.claimed_records]
    state.claimed_records.update(new_records)
    record = len(new_records) * state.candidate.record_bonus
    big_boss = (reached // 100) * state.candidate.big_boss_bonus
    gained = regular + record + big_boss
    state.balance += gained
    state.total_earned += gained
    return {"regular": regular, "record": record, "big_boss": big_boss, "total": gained}


def spend_dp(state: NewDPState, max_wave: int) -> None:
    unlock_for_wave(state, max_wave)
    if max_wave >= 400 and not state.reroll_bought and state.balance >= state.candidate.reroll_cost:
        state.balance -= state.candidate.reroll_cost
        state.total_spent += state.candidate.reroll_cost
        state.reroll_bought = True

    while state.game_speed_level < len(GAME_SPEED_COSTS) and max_wave >= state.game_speed_unlock_wave:
        cost = GAME_SPEED_COSTS[state.game_speed_level]
        if state.balance < cost:
            break
        state.balance -= cost
        state.total_spent += cost
        state.game_speed_level += 1

    # The deterministic B_medium weapon has no rarity/drop/roll RNG.  Find and
    # Quality remain structurally implemented but are intentionally dormant.
    while True:
        eligible = [
            key for key in ITEM_ORDER
            if key in state.unlocked_achievements and key in ACTIVE_IN_THIS_PROBE
            and next_cost(state, key) <= state.balance
        ]
        if not eligible:
            break
        key = min(eligible, key=lambda item: (next_cost(state, item), ITEM_ORDER.index(item)))
        cost = next_cost(state, key)
        state.balance -= cost
        state.total_spent += cost
        state.levels[key] += 1


def rarity_weights(wave: int, state: NewDPState) -> tuple[tuple[str, float], ...]:
    base_weights = dict(epic.rarity_chances_for_wave(wave))
    weighted = {key: value * luck_rarity_weight_multiplier(state, key) for key, value in base_weights.items()}
    total = sum(weighted.values())
    return tuple((key, weighted[key] / total) for key in ("C", "U", "R", "E") if key in weighted)


def draw_hand_new_dp(
    rng: random.Random,
    run: sim.RunState,
    permanent: sim.PermanentState,
    config: sim.SimConfig,
    forced_rarity: str | None = None,
    forced_card: str | None = None,
    excluded: set[str] | None = None,
    starter_guarantee: bool = False,
) -> list[sim.Card]:
    excluded = set() if excluded is None else set(excluded)
    hand: list[sim.Card] = []
    if forced_card:
        hand.append(epic.CARD_BY_KEY[forced_card])
    chances = rarity_weights(run.kills, state_of(permanent))
    for _ in range(3 - len(hand)):
        rarity = forced_rarity
        if rarity is None:
            value, cumulative, rarity = rng.random(), 0.0, "C"
            for candidate_rarity, chance in chances:
                cumulative += chance
                if value < cumulative:
                    rarity = candidate_rarity
                    break
        candidates = [
            item for item in epic.available_cards(rarity, run, permanent, config)
            if item.key not in excluded and item.key not in {picked.key for picked in hand}
        ]
        if not candidates:
            for fallback in ("R", "U", "C"):
                candidates = [
                    item for item in epic.available_cards(fallback, run, permanent, config)
                    if item.key not in excluded and item.key not in {picked.key for picked in hand}
                ]
                if candidates:
                    break
        hand.append(rng.choice(candidates))
    if starter_guarantee and not any(item.key in sim.STARTER_SAFE_KEYS for item in hand):
        choices = [epic.CARD_BY_KEY[key] for key in sim.STARTER_SAFE_ORDER if key in epic.CARD_BY_KEY and key not in {item.key for item in hand}]
        if choices:
            hand[0] = rng.choice(choices)
    return hand


def acquire_card_new(run: sim.RunState, item: sim.Card) -> None:
    accelerated_before = run.counts.get("accelerated_learning", 0)
    run.counts[item.key] += 1
    for tag in item.tags:
        run.tag_counts[tag] += 1
    run.accelerated_units += accelerated_before
    run.card_count += 1
    run.choices += 1
    run.effect_version += 1


def default_weapon_base_provider(run: sim.RunState, permanent: sim.PermanentState) -> float:
    return weapon.weapon_base_atk(run.kills) if run.kills >= 10 else 0.0


def default_weapon_modifier_provider(run: sim.RunState, permanent: sim.PermanentState) -> dict[str, float]:
    return {
        "weapon_atk_additive": 0.0,
        "weapon_atk_pct": 0.0,
        "base_atk_pct": 0.0,
        "attack_speed_pct": 0.0,
        "crit_rate": 0.0,
        "crit_multiplier": 0.0,
        "all_damage_pct": 0.0,
    }


WEAPON_BASE_PROVIDER = default_weapon_base_provider
WEAPON_MODIFIER_PROVIDER = default_weapon_modifier_provider


def _snapshot_values(
    run: sim.RunState,
    permanent: sim.PermanentState,
    boss: bool,
    use_dp: bool,
    include_weapon: bool = True,
    *,
    weapon_base_provider=None,
    weapon_modifier_provider=None,
    action_factor_provider=None,
    crit_factor_provider=None,
    follow_values_provider=None,
    xp_multiplier: float = 1.0,
) -> dict[str, float | bool | int]:
    counts = run.counts
    state = state_of(permanent)
    c = state.candidate
    levels = state.levels if use_dp else {key: 0 for key in ITEM_ORDER}
    c_amp, u_amp, r_amp = epic.amps(counts)
    weapon_mods = (
        (weapon_modifier_provider or WEAPON_MODIFIER_PROVIDER)(run, permanent)
        if include_weapon else default_weapon_modifier_provider(run, permanent)
    )

    raw_crit = .01 + .10 * c_amp * counts.get("critical_eye", 0) + .08 * u_amp * counts.get("critical_training", 0)
    raw_crit += levels["crit_rate"] * c.crit_rate_per_level
    raw_crit += weapon_mods["crit_rate"]
    multi_crit = bool(counts.get("multi_crit", 0))
    compression = bool(counts.get("critical_compression", 0))
    overcap = bool(counts.get("overflow", 0) or multi_crit)
    synergy_crit = raw_crit if overcap else min(1.0, raw_crit)
    displayed_crit = 1.0 if compression else (raw_crit if overcap else min(1.0, raw_crit))
    crit_mult = 2.0 + .25 * c_amp * counts.get("critical_power", 0) + .20 * u_amp * counts.get("critical_training", 0)
    crit_mult += levels["crit_multiplier"] * c.crit_mult_per_level
    crit_mult += weapon_mods["crit_multiplier"]
    if compression:
        crit_mult += .50 + .15 * math.floor(max(raw_crit - 1.0, 0.0) / .50 + 1e-12)
    steps = rare.softcap_steps(synergy_crit)

    as_bonus = (
        .20 * c_amp * counts.get("rapid_fire", 0)
        + .25 * u_amp * counts.get("overclock", 0)
        + .10 * u_amp * counts.get("balanced_training", 0)
        + .05 * u_amp * math.floor(synergy_crit / .25 + 1e-12) * counts.get("critical_momentum", 0)
        + .05 * r_amp * steps * counts.get("critical_engine", 0)
        + weapon_mods["attack_speed_pct"]
    )
    attack_speed = (1.0 + c.as_per_level) ** levels["attack_speed"] * (1.0 + as_bonus)

    accelerated = rare.accelerated_learning_bonus(run.accelerated_units) * r_amp
    xp_bonus = .20 * c_amp * counts.get("experience", 0) + accelerated * counts.get("accelerated_learning", 0)
    general_xp = (1.0 + c.xp_per_level) ** levels["xp_gain"] * (1.0 + xp_bonus) * xp_multiplier
    boss_xp = general_xp * (1.0 + .50 * c_amp * counts.get("boss_scholar", 0) + .30 * u_amp * counts.get("boss_research", 0))

    attack_bonus = .25 * c_amp * counts.get("power_up", 0) + .35 * u_amp * counts.get("brutal_force", 0) + .15 * u_amp * counts.get("balanced_training", 0)
    raw_base = 1.0 + attack_bonus
    if (run.kills >= 10 or weapon_base_provider is not None) and include_weapon:
        weapon_add = .25 * c_amp * counts.get("weapon_training", 0) + .10 * u_amp * counts.get("overclock", 0)
        weapon_mult = 1.10 * (1.0 + c.weapon_atk_per_level) ** levels["weapon_atk"]
        weapon_base = (weapon_base_provider or WEAPON_BASE_PROVIDER)(run, permanent)
        effective_weapon = (weapon_base + weapon_mods["weapon_atk_additive"]) * (
            1.0 + weapon_add + weapon_mods["weapon_atk_pct"]
        ) * weapon_mult
    else:
        effective_weapon = 0.0
    pre_dp_base = raw_base + effective_weapon
    total_base = pre_dp_base * (1.0 + weapon_mods["base_atk_pct"]) * (1.0 + c.atk_per_level) ** levels["base_atk"]
    log_attack = math.log10(total_base)

    all_damage_bonus = (
        .15 * c_amp * counts.get("steady_force", 0)
        + .05 * u_amp * counts.get("brutal_force", 0)
        + .05 * r_amp * steps * counts.get("critical_conversion", 0)
        + rare.boss_devourer_bonus(run.boss_devourer_units) * r_amp * counts.get("boss_devourer", 0)
        + weapon_mods["all_damage_pct"]
    )
    if counts.get("knowledge_conversion", 0):
        all_damage_bonus += rare.knowledge_conversion_bonus(general_xp) * r_amp
    all_damage = 1.0 + all_damage_bonus

    crit_factor = (crit_factor_provider or epic.crit_expected_multiplier)(raw_crit, crit_mult, multi_crit)
    if compression:
        crit_factor = crit_mult
    hit_count = 1.0 + .20 * r_amp * counts.get("multi_hit", 0)
    supplemental = .25 * r_amp * counts.get("supplemental_damage", 0) + .15 * counts.get("resonant_damage", 0) + .10 * counts.get("echoing_damage", 0)
    follow_unlocked = bool(counts.get("follow_up_strike", 0) or counts.get("follow_up_echo", 0))
    follow_rate = follow_damage = 0.0
    if follow_unlocked:
        follow_rate = .10 * r_amp + .15 * r_amp * counts.get("double_strike", 0)
        follow_damage = .50 * r_amp + .25 * r_amp * counts.get("double_strike", 0)
        if counts.get("follow_up_echo", 0) and not counts.get("follow_up_strike", 0):
            follow_rate, follow_damage = .10, .50
    if follow_values_provider is not None:
        follow_rate, follow_damage = follow_values_provider(follow_rate, follow_damage)
    follow_rate = min(1.0, follow_rate)
    follow_depth = 2 if counts.get("follow_up_echo", 0) else (1 if follow_unlocked else 0)
    reaction_rate = min(.80, .15 * r_amp * counts.get("re_action", 0))
    if counts.get("chain_action", 0) and reaction_rate <= 0:
        reaction_rate = .15
    reaction_depth = 2 if counts.get("chain_action", 0) else (1 if reaction_rate > 0 else 0)
    series = (action_factor_provider or epic.action_factor)(
        crit_factor, hit_count, supplemental,
        bool(counts.get("resonant_damage", 0)), bool(counts.get("echoing_damage", 0)),
        follow_rate, follow_damage, follow_depth, reaction_rate, reaction_depth,
    )
    log_damage = log_attack + math.log10(attack_speed) + math.log10(series) + math.log10(all_damage)
    if boss:
        log_damage += math.log10(1.0 + .25 * c_amp * counts.get("boss_hunter", 0) + .30 * u_amp * counts.get("boss_research", 0))
    return {
        "log_damage": log_damage, "log_attack": log_attack, "raw_base": raw_base,
        "effective_weapon": effective_weapon, "all_damage": all_damage,
        "attack_speed": attack_speed, "general_xp": general_xp, "boss_xp": boss_xp,
        "crit_rate": displayed_crit, "crit_mult": crit_mult, "follow_rate": follow_rate,
        "multi_tier": math.floor(raw_crit + 1e-12) if multi_crit else 0,
        "time_collapse": bool(counts.get("time_collapse", 0)),
        "hit_count": hit_count, "supplemental": supplemental,
        "reaction_rate": reaction_rate, "follow_damage": follow_damage,
    }


def power_decomposition(run: sim.RunState, permanent: sim.PermanentState, boss: bool) -> dict[str, Any]:
    """Two-factor DP/Weapon decomposition in log10 Final Damage Power."""
    f_values = _snapshot_values(run, permanent, boss, True, True)
    d_values = _snapshot_values(run, permanent, boss, True, False)
    w_values = _snapshot_values(run, permanent, boss, False, True)
    n_values = _snapshot_values(run, permanent, boss, False, False)
    f = float(f_values["log_damage"])
    d = float(d_values["log_damage"])
    w = float(w_values["log_damage"])
    n = float(n_values["log_damage"])
    interaction = f - d - w + n
    return {
        "F": f, "D": d, "W": w, "N": n,
        "dp_legacy": f - w,
        "weapon_legacy": w - n,
        "dp_shapley": .5 * ((f - w) + (d - n)),
        "weapon_shapley": .5 * ((f - d) + (w - n)),
        "interaction": interaction,
        "current": f_values,
    }


def candidate_snapshot(run: sim.RunState, permanent: sim.PermanentState, boss: bool, config: sim.SimConfig) -> sim.Snapshot:
    decomposition = power_decomposition(run, permanent, boss)
    current = decomposition["current"]
    dp_power = float(decomposition["dp_shapley"])
    weapon_power = float(decomposition["weapon_shapley"])
    return sim.Snapshot(
        log_dps=float(current["log_damage"]), base_attack_power=float(current["log_attack"]),
        all_damage=float(current["all_damage"]), attack_speed=float(current["attack_speed"]),
        general_xp=float(current["general_xp"]), boss_xp=float(current["boss_xp"]),
        first_strike_mult=1.35 ** run.counts.get("first_strike", 0),
        last_stand_mult=2.00 ** run.counts.get("last_stand", 0),
        execution_mult=1.0 + 1.50 * run.counts.get("execution", 0),
        time_collapse=bool(current["time_collapse"]), crit_chance=float(current["crit_rate"]),
        crit_multiplier=float(current["crit_mult"]), follow_rate=float(current["follow_rate"]),
        multi_crit_tier=int(current["multi_tier"]), dp_power=dp_power,
        weapon_power=weapon_power, relic_power=0.0,
    )


class Capture:
    def __init__(self, config: sim.SimConfig) -> None:
        self.config = config
        self.current: dict[int, dict[str, Any]] = {}

    def reset(self) -> None:
        self.current = {}

    def compute(self, run: sim.RunState, permanent: sim.PermanentState, boss: bool, config: sim.SimConfig) -> sim.Snapshot:
        snapshot = candidate_snapshot(run, permanent, boss, config)
        wave = int(run.kills)
        if wave in CHECKPOINTS and wave not in self.current:
            state = state_of(permanent)
            card_power = snapshot.log_dps - snapshot.dp_power - snapshot.weapon_power
            decomposition = power_decomposition(run, permanent, boss)
            self.current[wave] = {
                "final_damage_power": snapshot.log_dps,
                "dp_power": snapshot.dp_power,
                "weapon_power": snapshot.weapon_power,
                "card_power": card_power,
                "dp_balance": state.balance,
                "dp_spent": state.total_spent,
                "dp_earned": state.total_earned,
                "dp_levels": dict(state.levels),
                "F": decomposition["F"], "D": decomposition["D"],
                "W": decomposition["W"], "N": decomposition["N"],
                "dp_power_legacy": decomposition["dp_legacy"],
                "weapon_power_legacy": decomposition["weapon_legacy"],
                "dp_weapon_interaction": decomposition["interaction"],
                "next_costs": {key: next_cost(state, key) for key in ITEM_ORDER if key in state.unlocked_achievements},
                "reroll_bought": state.reroll_bought,
                "deaths": int(getattr(permanent, "_new_dp_current_deaths", 0)),
            }
        return snapshot


def run_trial_new_dp(
    rng: random.Random,
    candidate: Candidate,
    config: sim.SimConfig,
    capture: Capture,
    game_speed_unlock_wave: int,
) -> dict[str, Any]:
    permanent = sim.PermanentState(automation_enabled=config.automation_enabled)
    permanent._new_dp_state = NewDPState(candidate=candidate, game_speed_unlock_wave=game_speed_unlock_wave)  # type: ignore[attr-defined]
    total_combat = 0.0
    interaction_accounted = 0.0
    reach_seconds: dict[int, float] = {}
    run_reaches: list[int] = []
    awards: list[dict[str, int]] = []
    first_reached = 0
    best_failed = 0
    final_result: sim.RunResult | None = None
    success = False

    for attempt in range(1, config.max_attempts + 1):
        epic.FAILURE_SINK.clear()
        permanent._new_dp_current_deaths = attempt - 1  # type: ignore[attr-defined]
        combat_before = total_combat
        interaction_before = permanent.interaction_seconds
        speed_before = permanent.game_speed
        result = sim.run_once(rng, "balanced", permanent, config, allow_overdrive=False)
        final_result = result
        if attempt == 1:
            first_reached = result.reached
        run_reaches.append(result.reached)
        for wave, (combat_elapsed, interaction_elapsed) in result.reach_elapsed.items():
            reach_seconds.setdefault(wave, combat_before + interaction_accounted + combat_elapsed + interaction_elapsed / speed_before)
        total_combat += result.combat_seconds
        interaction_accounted += (permanent.interaction_seconds - interaction_before) / speed_before
        if result.reached >= config.target_wave:
            success = True
            deaths = attempt - 1
            break
        best_failed = max(best_failed, result.reached)
        state = state_of(permanent)
        unlock_for_wave(state, permanent.max_wave)
        award = award_dp_after_death(state, result.reached)
        awards.append(award)
        spend_dp(state, permanent.max_wave)
    else:
        deaths = config.max_attempts

    assert final_result is not None
    state = state_of(permanent)
    return {
        "success": success, "deaths": deaths, "first_reached": first_reached,
        "best_wave": config.target_wave if success else best_failed,
        "reach_seconds": reach_seconds, "run_reaches": run_reaches,
        "checkpoint": copy.deepcopy(capture.current),
        "final_dp": {
            "balance": state.balance, "spent": state.total_spent, "earned": state.total_earned,
            "levels": dict(state.levels), "reroll_bought": state.reroll_bought,
            "unlocks": sorted(state.unlocked_achievements),
        },
        "awards": awards,
    }


def percentile(values: list[float], q: float) -> float | None:
    return base.percentile(values, q)


def stats(values: list[float]) -> dict[str, float | None]:
    return {"p25": percentile(values, .25), "p50": percentile(values, .50), "p75": percentile(values, .75)}


def med(states: list[dict[str, Any]], key: str) -> float | None:
    return percentile([float(state[key]) for state in states], .50)


def summarize_condition(name: str, candidate: Candidate, rows: list[dict[str, Any]], trials: int) -> dict[str, Any]:
    checkpoints: dict[str, Any] = {}
    for wave in CHECKPOINTS:
        reached_rows = [row for row in rows if wave in row["checkpoint"]]
        states = [row["checkpoint"][wave] for row in reached_rows]
        times = [row["reach_seconds"][wave] / 3600 for row in reached_rows if wave in row["reach_seconds"]]
        levels = {
            key: percentile([float(state["dp_levels"][key]) for state in states], .50)
            for key in ITEM_ORDER
        }
        next_costs = {
            key: percentile([float(state["next_costs"][key]) for state in states if key in state["next_costs"]], .50)
            for key in ITEM_ORDER
        }
        checkpoints[str(wave)] = {
            "reach_rate": len(states) / trials,
            "time_hours": stats(times),
            "deaths_p50": med(states, "deaths"),
            "dp_balance_p50": med(states, "dp_balance"),
            "dp_spent_p50": med(states, "dp_spent"),
            "dp_earned_p50": med(states, "dp_earned"),
            "reroll_purchase_rate": (
                sum(bool(state["reroll_bought"]) for state in states) / len(states)
                if states else 0.0
            ),
            "dp_levels_p50": levels,
            "next_costs_p50": next_costs,
            "final_damage_power_p50": med(states, "final_damage_power"),
            "enemy_power": sim.configured_enemy_power(wave, ACTIVE_CONFIG),
            "dp_power_p50": med(states, "dp_power"),
            "weapon_power_p50": med(states, "weapon_power"),
            "card_power_p50": med(states, "card_power"),
            "F_p50": med(states, "F") if states and "F" in states[0] else None,
            "D_p50": med(states, "D") if states and "D" in states[0] else None,
            "W_p50": med(states, "W") if states and "W" in states[0] else None,
            "N_p50": med(states, "N") if states and "N" in states[0] else None,
            "dp_power_legacy_p50": med(states, "dp_power_legacy") if states and "dp_power_legacy" in states[0] else None,
            "weapon_power_legacy_p50": med(states, "weapon_power_legacy") if states and "weapon_power_legacy" in states[0] else None,
            "dp_weapon_interaction_p50": med(states, "dp_weapon_interaction") if states and "dp_weapon_interaction" in states[0] else None,
        }

    intervals: list[dict[str, Any]] = []
    for left, right in zip(FIFTY_CHECKPOINTS, FIFTY_CHECKPOINTS[1:]):
        a, b = checkpoints[str(left)], checkpoints[str(right)]
        player_delta = None if a["final_damage_power_p50"] is None or b["final_damage_power_p50"] is None else b["final_damage_power_p50"] - a["final_damage_power_p50"]
        dp_delta = None if a["dp_power_p50"] is None or b["dp_power_p50"] is None else b["dp_power_p50"] - a["dp_power_p50"]
        weapon_delta = None if a["weapon_power_p50"] is None or b["weapon_power_p50"] is None else b["weapon_power_p50"] - a["weapon_power_p50"]
        legacy_dp_delta = None if a["dp_power_legacy_p50"] is None or b["dp_power_legacy_p50"] is None else b["dp_power_legacy_p50"] - a["dp_power_legacy_p50"]
        interaction_delta = None if a["dp_weapon_interaction_p50"] is None or b["dp_weapon_interaction_p50"] is None else b["dp_weapon_interaction_p50"] - a["dp_weapon_interaction_p50"]
        intervals.append({
            "from": left, "to": right,
            "enemy_power_delta": b["enemy_power"] - a["enemy_power"],
            "player_power_delta": player_delta,
            "dp_power_delta": dp_delta,
            "weapon_power_delta": weapon_delta,
            "dp_power_legacy_delta": legacy_dp_delta,
            "dp_weapon_interaction_delta": interaction_delta,
            "residual_power_delta": (
                player_delta - dp_delta - weapon_delta
                if player_delta is not None and dp_delta is not None and weapon_delta is not None else None
            ),
            "dp_share_of_player_growth": (
                dp_delta / player_delta
                if dp_delta is not None and player_delta is not None and abs(player_delta) > 1e-12
                else None
            ),
            "dp_share_of_player_growth_legacy": (
                legacy_dp_delta / player_delta
                if legacy_dp_delta is not None and player_delta is not None and abs(player_delta) > 1e-12
                else None
            ),
        })
    final_dp = {
        key: percentile([float(row["final_dp"]["levels"][key]) for row in rows], .50)
        for key in ITEM_ORDER
    }
    return {
        "candidate": name,
        "parameters": {
            **candidate.__dict__,
            "cost_weights": COST_WEIGHTS,
            "unlock_waves": UNLOCK_WAVES,
            "luck_softcap": "Lv1-10 100%, Lv11-25 50%, Lv26+ 20%",
            "weapon_find_softcap": "Lv1-10 100%, Lv11-25 50%, Lv26+ 20% (dormant in deterministic Weapon probe)",
            "weapon_quality_softcap": "Lv1-10 100%, Lv11-25 50%, Lv26+ 20% (dormant in deterministic Weapon probe)",
        },
        "success_rate": sum(row["success"] for row in rows) / trials,
        "final_deaths": stats([float(row["deaths"]) for row in rows]),
        "final_wave": stats([float(row["best_wave"]) for row in rows]),
        "final_wave_distribution": dict(sorted(collections.Counter(int(row["best_wave"]) for row in rows).items())),
        "final_dp_levels_p50": final_dp,
        "checkpoint": checkpoints,
        "intervals": intervals,
        "max_dp_power_delta_w500_750": max(
            (item["dp_power_delta"] for item in intervals if 500 <= item["from"] < 750 and item["dp_power_delta"] is not None),
            default=None,
        ),
        "largest_plain_multiplicative_level_power": max(
            math.log10(1.0 + candidate.atk_per_level),
            math.log10(1.0 + candidate.as_per_level),
            math.log10(1.0 + candidate.weapon_atk_per_level),
        ),
    }


ACTIVE_CONFIG: sim.SimConfig


def run_condition(
    name: str,
    candidate: Candidate,
    trials: int,
    seed: int,
    max_attempts: int,
    game_speed_unlock_wave: int,
    *,
    automation_enabled: bool = True,
    sweep_enabled: bool = True,
    reward_skip_enabled: bool = True,
) -> dict[str, Any]:
    global ACTIVE_CONFIG
    ACTIVE_CONFIG = sim.SimConfig(
        max_attempts=max_attempts, automation_enabled=automation_enabled, interval_enabled=False,
        game_speed_enabled=False, initial_card_points_enabled=False,
        sweep_enabled=sweep_enabled, reward_skip_enabled=reward_skip_enabled,
        defense=sim.DefenseConfig(enabled=False), target_wave=TARGET_WAVE,
        card_upgrade_cap=0, relic_selection_enabled=False,
        exponential_core_multiplier=1.0,
    )
    capture = Capture(ACTIVE_CONFIG)
    sim.compute_snapshot = capture.compute
    rows: list[dict[str, Any]] = []
    for trial in range(trials):
        capture.reset()
        rng = random.Random(seed + 1_000_000 + trial)
        rows.append(run_trial_new_dp(rng, candidate, ACTIVE_CONFIG, capture, game_speed_unlock_wave))
    return summarize_condition(name, candidate, rows, trials)


def fmt(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# 新W5000候補 DP v0.1 比較", "",
        f"各{payload['trials_per_condition']} trials / Standard bot / seed {payload['seed']} / target W{TARGET_WAVE}", "",
        "Common～Epic新カード、B_medium固定Weapon。Legendary / Relic / refinement / Weapon rarity・drop RNG・affix: OFF。", "",
        "formal旧DPは未変更。new_w5000では旧totalLv Damage/報酬/Rare率/Card Pointマイルストーンを使用しない。", "",
    ]
    for name, result in payload["conditions"].items():
        p = result["parameters"]
        lines += [
            f"## {name}", "",
            f"Cost=`ceil({p['base_cost']:.0f}×itemWeight×{p['cost_growth']:.3f}^itemLv)` / Death DP=`{p['death_base']}+floor(W/{p['death_divisor']})` / Record={p['record_bonus']} / Big Boss={p['big_boss_bonus']} / Reroll={p['reroll_cost']} DP", "",
            f"1Lv: ATK +{p['atk_per_level']:.1%}, AS +{p['as_per_level']:.1%}, XP +{p['xp_per_level']:.1%}, Crit +{p['crit_rate_per_level']*100:.2f}pt, Crit Mult +{p['crit_mult_per_level']:.3f}, Weapon ATK +{p['weapon_atk_per_level']:.1%}", "",
            f"Success W1000: {result['success_rate']:.1%} / Final deaths P50: {fmt(result['final_deaths']['p50'],1)} / Final Wave P50: {fmt(result['final_wave']['p50'],1)}", "",
            "| W | Reach | Time P25/P50/P75 | Deaths | DP balance/spent | DP Lv ATK/AS/XP/Crit/CM/WATK/Luck | Final | DP | Weapon | Card |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for wave in MAIN_CHECKPOINTS:
            x = result["checkpoint"][str(wave)]
            t, lv = x["time_hours"], x["dp_levels_p50"]
            level_text = "/".join(fmt(lv[key],1) for key in ("base_atk","attack_speed","xp_gain","crit_rate","crit_multiplier","weapon_atk","luck"))
            lines.append(
                f"| {wave} | {x['reach_rate']:.1%} | {fmt(t['p25'])}/{fmt(t['p50'])}/{fmt(t['p75'])}h | {fmt(x['deaths_p50'],1)} | {fmt(x['dp_balance_p50'],1)}/{fmt(x['dp_spent_p50'],1)} | {level_text} | {fmt(x['final_damage_power_p50'])} | {fmt(x['dp_power_p50'])} | {fmt(x['weapon_power_p50'])} | {fmt(x['card_power_p50'])} |"
            )
        lines += ["", "### 50Wave区間（W500～750）", "", "| 区間 | Enemy +Power | Player +Power | DP +Power |", "|---:|---:|---:|---:|"]
        for item in result["intervals"]:
            if 500 <= item["from"] < 750:
                lines.append(f"| {item['from']}→{item['to']} | {fmt(item['enemy_power_delta'])} | {fmt(item['player_power_delta'])} | {fmt(item['dp_power_delta'])} |")
        lines += [
            "",
            f"最大の通常乗算1Lv: +{result['largest_plain_multiplicative_level_power']:.3f} Power。W500～750の50Wave区間DP増加最大: {fmt(result['max_dp_power_delta_w500_750'])} Power。",
        ]
        lines += ["", "### 次Lvコスト（到達時中央値）", "", "| W | Base | AS | XP | Crit | Crit Mult | Weapon | Luck |", "|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for wave in MAIN_CHECKPOINTS:
            c = result["checkpoint"][str(wave)]["next_costs_p50"]
            lines.append(f"| {wave} | {fmt(c['base_atk'],0)} | {fmt(c['attack_speed'],0)} | {fmt(c['xp_gain'],0)} | {fmt(c['crit_rate'],0)} | {fmt(c['crit_multiplier'],0)} | {fmt(c['weapon_atk'],0)} | {fmt(c['luck'],0)} |")
        lines.append("")

    lines += [
        "## 判定", "",
        "- DP Powerは個別Lvの連続倍率だけで計算され、totalLv境界による+Powerは存在しない。",
        "- Weapon Find / Weapon Qualityは仕様・Softcap・価格を実装したが、固定B_medium Weapon条件では効果がないためStandard botは購入しない。",
        "- Game Speed解禁WaveはCLIで1000/1250/1500を選べる構造。今回既定は1250で、W1000探索には影響しない。",
        "- 候補の正式採用・自動調整は行っていない。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv(path: Path, payload: dict[str, Any]) -> None:
    fields = [
        "candidate","wave","reach_rate","time_p25","time_p50","time_p75","deaths_p50",
        "dp_balance_p50","dp_spent_p50","final_power_p50","dp_power_p50","weapon_power_p50","card_power_p50",
    ] + [f"lv_{key}" for key in ITEM_ORDER] + [f"next_{key}" for key in ITEM_ORDER]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for name, result in payload["conditions"].items():
            for wave in CHECKPOINTS:
                x = result["checkpoint"][str(wave)]
                row = {
                    "candidate":name,"wave":wave,"reach_rate":x["reach_rate"],
                    "time_p25":x["time_hours"]["p25"],"time_p50":x["time_hours"]["p50"],"time_p75":x["time_hours"]["p75"],
                    "deaths_p50":x["deaths_p50"],"dp_balance_p50":x["dp_balance_p50"],"dp_spent_p50":x["dp_spent_p50"],
                    "final_power_p50":x["final_damage_power_p50"],"dp_power_p50":x["dp_power_p50"],
                    "weapon_power_p50":x["weapon_power_p50"],"card_power_p50":x["card_power_p50"],
                }
                row.update({f"lv_{key}":x["dp_levels_p50"][key] for key in ITEM_ORDER})
                row.update({f"next_{key}":x["next_costs_p50"][key] for key in ITEM_ORDER})
                writer.writerow(row)


def install_isolated_candidate(capture: Capture) -> None:
    global WEAPON_BASE_PROVIDER, WEAPON_MODIFIER_PROVIDER
    WEAPON_BASE_PROVIDER = default_weapon_base_provider
    WEAPON_MODIFIER_PROVIDER = default_weapon_modifier_provider
    weapon.ACTIVE_CURVE = weapon.CURVES["B_medium"]
    base.NEW_CARDS = weapon.WEAPON_CARDS
    base.CARD_BY_KEY = weapon.CARD_BY_KEY
    base.candidate_snapshot = candidate_snapshot
    base.full_window_power = epic.full_window_power
    base.CHECKPOINTS = CHECKPOINTS
    base.install_candidate_pool(capture)
    sim.CHECKPOINTS = CHECKPOINTS
    sim.REACH_WAVES = CHECKPOINTS
    sim.VARIANT_REACH_WAVES = CHECKPOINTS
    sim.compute_snapshot = capture.compute
    sim.draw_hand = draw_hand_new_dp
    sim.acquire_card = acquire_card_new
    sim.available_cards = epic.available_cards
    sim.process_guaranteed_choices = epic.guaranteed_choices
    sim.dynamic_damage_log = epic.dynamic_damage_log
    sim.temporal_integral = epic.temporal_integral
    sim.temporal_lookup = epic.temporal_lookup
    sim.time_to_kill_with_defense = epic.recording_time_to_kill_with_defense
    sim.forge_starting_weapon = lambda rng, permanent, run, config: None
    sim.process_boss_loot = lambda rng, permanent, run, wave, config: False
    sim.acquire_relic = lambda rng, permanent, config: None
    sim.purchase_game_speed = lambda permanent, config: None
    sim.milestone_damage_log = lambda levels, scale=1.0: 0.0
    sim.PermanentState.rerolls = property(lambda self: 2 if hasattr(self, "_new_dp_state") and state_of(self).reroll_bought else 1)
    sim.PermanentState.initial_xp = property(lambda self: 0.0)
    sim.PermanentState.initial_card_points = property(lambda self: 0)
    sim.PermanentState.game_speed = property(
        lambda self: GAME_SPEED_MULTIPLIERS[state_of(self).game_speed_level - 1]
        if hasattr(self, "_new_dp_state") and state_of(self).game_speed_level > 0 else 1.0
    )


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--max-attempts", type=int, default=220)
    parser.add_argument("--game-speed-unlock", type=int, choices=(1000,1250,1500), default=1250)
    parser.add_argument("--output-dir", type=Path, default=Path("output/new_w5000_dp_v01_30"))
    args = parser.parse_args()
    if not 1 <= args.trials <= 30:
        parser.error("--trials must be between 1 and 30")

    # One capture instance is installed once; it is reset for every trial.
    global ACTIVE_CONFIG
    ACTIVE_CONFIG = sim.SimConfig(target_wave=TARGET_WAVE)
    capture = Capture(ACTIVE_CONFIG)
    install_isolated_candidate(capture)
    conditions: dict[str, Any] = {}
    for name, candidate in CANDIDATES.items():
        result = run_condition(name, candidate, args.trials, args.seed, args.max_attempts, args.game_speed_unlock)
        conditions[name] = result
        # Save each completed condition immediately.
        partial_dir = args.output_dir.resolve()
        partial_dir.mkdir(parents=True, exist_ok=True)
        (partial_dir / f"{name}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    payload = {
        "settings": {
            "formal_modified": False, "new_w5000_isolated": True,
            "old_total_level_milestones": False, "old_rare_bonus": False,
            "old_initial_card_points": False, "target_wave": TARGET_WAVE,
            "trials_per_condition": args.trials, "seed": args.seed,
            "max_attempts": args.max_attempts, "profile": "Standard/balanced",
            "weapon_curve": "B_medium deterministic", "game_speed_unlock_wave": args.game_speed_unlock,
        },
        "seed": args.seed, "trials_per_condition": args.trials,
        "conditions": conditions, "automatic_adoption": False,
    }
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "new_w5000_dp_v01.json"
    csv_path = out / "new_w5000_dp_v01_checkpoints.csv"
    md_path = out / "new_w5000_dp_v01.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(csv_path, payload)
    write_markdown(md_path, payload)
    print(json.dumps({
        "conditions": {name: {"success_rate": value["success_rate"], "deaths_p50": value["final_deaths"]["p50"], "final_wave_p50": value["final_wave"]["p50"]} for name, value in conditions.items()},
        "files": {"json": str(json_path), "csv": str(csv_path), "markdown": str(md_path)},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
