#!/usr/bin/env python3
"""Full Wave 1-10,000 Monte Carlo model for the first-prestige draft.

The simulator works in log10 damage space.  It models the agreed card pools,
guaranteed rarity milestones, XP, DP upgrades, the fixed weapon/relic, and the
five clarified Epic/Legendary mechanics.  Player choice is represented by
three simple scoring profiles; it is a balance model, not a perfect bot.
"""

from __future__ import annotations

import argparse
import bisect
import collections
import concurrent.futures
import copy
import csv
import functools
import hashlib
import json
import math
import os
import random
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

from first_prestige_defense_model import (
    DefenseConfig,
    FUTURE_TOTAL_POWER_ANCHORS,
    armor_break_time,
    defense_power,
    hp_power,
    remaining_defense_power,
)


SEED = 20260828
DEFAULT_TRIALS = 30
PRESTIGE_WAVE = 10_000
DP_GROWTH = 1.0315
POWER_ANCHORS = (
    (1, math.log10(5)),
    (10, math.log10(15)),
    (25, 1.325),
    (100, 2.97),
    (500, 4.50),
    (2500, 32.41),
    (5000, 98.55),
    (7500, 191.67),
    (10000, 308.0),
)
POWER_BONUS_ANCHORS = (
    (1, 0.0),
    (100, 0.0),
    (500, 5.0),
    (2500, 60.0),
    (5000, 70.0),
    (7500, 50.0),
    (10000, 0.0),
)
WEAPON_POWER_ANCHORS = (
    (10, 0.04),
    (100, 0.30),
    (500, 1.0),
    (1000, 2.0),
    (2500, 6.0),
    (5000, 15.0),
    (7500, 25.0),
    (10000, 35.0),
)
RELIC_POWER_ANCHORS = (
    (100, 0.05),
    (500, 0.50),
    (1000, 1.50),
    (2500, 4.0),
    (5000, 10.0),
    (7500, 18.0),
    (10000, 25.0),
)
CHECKPOINTS = (500, 2500, 5000, 7500, 10000)
REACH_WAVES = (100, 500, 2500, 5000, 7500)
VARIANT_REACH_WAVES = (500, 2500, 3500, 4500, 5000)
VARIANT_E_DEFENSE_POWER_ANCHORS = (
    (500, 0.0),
    (1000, 2.0),
    (2500, 8.0),
    (3500, 14.0),
    (4500, 20.0),
    (5000, 25.0),
)
VARIANT_E_ENEMY_WAVE_ANCHORS = (
    (2500, 2500.0),
    (3500, 5000.0),
    (4500, 9000.0),
    (5000, 10000.0),
)
VARIANT_E_ENEMY_POWER_RELIEF_ANCHORS = (
    (1, 0.0),
    (500, 0.0),
    (1000, 3.0),
    (1500, 6.0),
    (2000, 8.0),
    (2500, 8.0),
    (3500, 8.0),
    (4000, 12.0),
    (4500, 8.0),
    (5000, 0.0),
)
RARITY_ORDER = ("C", "U", "R", "E", "L")
RARITY_POWER = {"C": 0.0, "U": 0.15, "R": 0.40, "E": 0.80, "L": 1.30}
MATERIAL_VALUE = {"C": 1.0, "U": 2.0, "R": 4.0, "E": 8.0, "L": 16.0}
CARD_POINT_VALUE = {"C": 1, "U": 3, "R": 8, "E": 20, "L": 50}
CARD_UPGRADE_COSTS = (5, 15, 40)
CARD_DECISION_SECONDS = 1.0
NEW_CARD_DECISION_SECONDS = 4.0
REROLL_SECONDS = 1.5
EQUIPMENT_DECISION_SECONDS = 2.0
FORGE_OPERATION_SECONDS = 3.0
CARD_UPGRADE_SECONDS = 2.0
MEMORY_CARD_DECISION_SECONDS = 1.0
SHADOW_CARD_VALUE_ROWS: list[dict[str, object]] = []
SHADOW_CARD_VALUE_LIMIT = 0
TAKE_BRANCH_ROWS: list[dict[str, object]] = []
TAKE_BRANCH_ENABLED = False
TAKE_BRANCH_CONTEXT: dict[str, object] = {}
INTERVAL_DP_COSTS = (100, 300, 900, 2_700, 8_100, 24_300, 72_900, 218_700, 656_100)
INTERVAL_WAVE_GATES = (100, 250, 500, 1_000, 2_500, 5_000, 7_500, 10_000, PRESTIGE_WAVE + 1)
INTERVAL_DP_SHARES = {"damage": 0.30, "balanced": 0.25, "synergy": 0.20}
GAME_SPEED_MATERIAL_COSTS = (2_000.0, 6_000.0)
GAME_SPEED_WAVE_GATES = (2_500, 5_000)
GAME_SPEED_MULTIPLIERS = (1.10, 1.20)


def interpolate_anchors(wave: int, anchors: tuple[tuple[int, float], ...]) -> float:
    if wave <= anchors[0][0]:
        return anchors[0][1]
    for (left_wave, left_value), (right_wave, right_value) in zip(anchors, anchors[1:]):
        if wave <= right_wave:
            t = (wave - left_wave) / (right_wave - left_wave)
            return left_value + (right_value - left_value) * t
    return anchors[-1][1]


POWER_BASE_TABLE = tuple(interpolate_anchors(wave, POWER_ANCHORS) for wave in range(PRESTIGE_WAVE + 1))
POWER_BONUS_TABLE = tuple(interpolate_anchors(wave, POWER_BONUS_ANCHORS) for wave in range(PRESTIGE_WAVE + 1))
FUTURE_POWER_TABLE = tuple(
    interpolate_anchors(wave, FUTURE_TOTAL_POWER_ANCHORS)
    for wave in range(PRESTIGE_WAVE + 1)
)
MIDGAME_RELIEF_SHAPE = (
    (1, 0.0),
    (500, 0.0),
    (1000, 0.70),
    (1500, 1.00),
    (2000, 0.70),
    (2500, 0.0),
    (10000, 0.0),
)
MIDGAME_RELIEF_TABLE = tuple(
    interpolate_anchors(wave, MIDGAME_RELIEF_SHAPE)
    for wave in range(PRESTIGE_WAVE + 1)
)
WEAPON_POWER_TABLE = tuple(interpolate_anchors(max(10, wave), WEAPON_POWER_ANCHORS) for wave in range(PRESTIGE_WAVE + 1))
RELIC_POWER_TABLE = tuple(
    0.0 if wave < 100 else interpolate_anchors(wave, RELIC_POWER_ANCHORS)
    for wave in range(PRESTIGE_WAVE + 1)
)


@dataclass(frozen=True)
class Card:
    key: str
    name: str
    rarity: str
    tags: frozenset[str] = frozenset()
    unique: bool = False
    unlock_wave: int = 0


def card(
    key: str,
    name: str,
    rarity: str,
    *tags: str,
    unique: bool = False,
    unlock_wave: int = 0,
) -> Card:
    return Card(key, name, rarity, frozenset(tags), unique, unlock_wave)


CARDS = (
    # Common: tuned early-game version.
    card("power_up", "Power Up", "C", "atk"),
    card("heavy_blow", "Heavy Blow", "C", "atk", "risk"),
    card("rapid_fire", "Rapid Fire", "C", "as"),
    card("light_attack", "Light Attack", "C", "as", "risk"),
    card("critical_eye", "Critical Eye", "C", "crit"),
    card("critical_power", "Critical Power", "C", "crit"),
    card("sharpened_edge", "Sharpened Edge", "C", "crit"),
    card("precise_strike", "Precise Strike", "C", "crit", "risk"),
    card("heavy_critical", "Heavy Critical", "C", "crit", "risk"),
    card("experience", "Experience", "C", "xp"),
    card("fast_learner", "Fast Learner", "C", "xp", "risk"),
    card("scholar", "Scholar", "C", "xp", "boss"),
    card("study_break", "Study Break", "C", "xp", "risk"),
    card("steady_force", "Steady Force", "C", "damage"),
    card("glass_cannon", "Glass Cannon", "C", "atk", "risk"),
    # Uncommon connectors.
    card("overclock", "Overclock", "U", "as", "risk"),
    card("brutal_force", "Brutal Force", "U", "atk", "risk"),
    card("battle_focus", "Battle Focus", "U", "damage", "risk"),
    card("risky_study", "Risky Study", "U", "xp", "risk"),
    card("critical_training", "Critical Training", "U", "crit"),
    card("critical_momentum", "Critical Momentum", "U", "crit", "as"),
    card("boss_research", "Boss Research", "U", "boss", "xp"),
    card("quick_learner", "Quick Learner", "U", "xp"),
    card("battle_scholar", "Battle Scholar", "U", "xp", "damage"),
    card("escalation", "Escalation", "U", "damage", "growth"),
    card("last_stand", "Last Stand", "U", "damage", "time"),
    card("first_strike", "First Strike", "U", "damage", "time"),
    # Rare engines.
    card("critical_engine", "Critical Engine", "R", "crit", "as", "engine"),
    card("critical_conversion", "Critical Conversion", "R", "crit", "damage", "engine"),
    card("brutal_critical", "Brutal Critical", "R", "crit", "risk"),
    card("overflow", "Overflow", "R", "crit", "rule", unique=True),
    card("follow_up_strike", "Follow-Up Strike", "R", "followup", "rule", unique=True),
    card("double_strike", "Double Strike", "R", "followup"),
    card("knowledge_conversion", "Knowledge Conversion", "R", "xp", "damage", "engine"),
    card("accelerated_learning", "Accelerated Learning", "R", "xp", "growth", "engine"),
    card("growth_engine", "Growth Engine", "R", "damage", "growth", "engine"),
    card("boss_devourer", "Boss Devourer", "R", "boss", "damage", "growth"),
    card("execution", "Execution", "R", "damage", "rule", unique=True),
    card("momentum", "Momentum", "R", "damage", "time"),
    # Epic rule changes. Epic cards are unique in this first implementation.
    card("multi_crit", "Multi-Crit", "E", "crit", "rule", unique=True, unlock_wave=500),
    card("critical_geometry", "Critical Geometry", "E", "crit", "rule", unique=True, unlock_wave=500),
    card("follow_up_echo", "Follow-Up Echo", "E", "followup", "rule", unique=True, unlock_wave=500),
    card("perfect_learning", "Perfect Learning", "E", "xp", "damage", "engine", unique=True, unlock_wave=500),
    card("double_scaling", "Double Scaling", "E", "atk", "as", "engine", unique=True, unlock_wave=500),
    card("time_collapse", "Time Collapse", "E", "damage", "time", unique=True, unlock_wave=500),
    card("boss_assimilation", "Boss Assimilation", "E", "boss", "damage", "growth", unique=True, unlock_wave=500),
    card("limit_break", "Limit Break", "E", "rule", unique=True, unlock_wave=500),
    # Legendary cards are also unique.
    card("critical_singularity", "Critical Singularity", "L", "crit", "rule", unique=True, unlock_wave=2500),
    card("recursive_follow_up", "Recursive Follow-Up", "L", "followup", "rule", unique=True, unlock_wave=2500),
    card("infinite_barrage", "Infinite Barrage", "L", "as", "damage", "engine", unique=True, unlock_wave=2500),
    card("knowledge_collapse", "Knowledge Collapse", "L", "xp", "damage", "engine", unique=True, unlock_wave=2500),
    card("perfect_overdrive", "Perfect Overdrive", "L", "damage", "growth", "time", unique=True, unlock_wave=2500),
    card("limit_shatter", "Limit Shatter", "L", "rule", unique=True, unlock_wave=2500),
    card("exponential_core", "Exponential Core", "L", "atk", "exponent", unique=True, unlock_wave=5000),
    card("final_equation", "Final Equation", "L", "damage", "exponent", unique=True, unlock_wave=7500),
)

CARD_BY_KEY = {item.key: item for item in CARDS}
CARDS_BY_RARITY = {
    rarity: tuple(item for item in CARDS if item.rarity == rarity)
    for rarity in ("C", "U", "R", "E", "L")
}
STARTER_SAFE_KEYS = frozenset({"power_up", "rapid_fire", "steady_force"})
STARTER_SAFE_ORDER = ("power_up", "rapid_fire", "steady_force")


def round_to_five(value: float) -> int:
    return int(math.floor(value / 5 + 0.5)) * 5


def build_card_costs(size: int = 180) -> list[float]:
    costs: list[float] = [3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 30, 45]
    delta = 15
    while len(costs) < size:
        delta = round_to_five(delta * 1.35)
        costs.append(costs[-1] + delta)
    return costs


CARD_COSTS = build_card_costs()


def enemy_power(
    wave: int,
    bonus_scale: float = 0.0,
    midgame_relief: float = 0.0,
    use_future_curve: bool = False,
) -> float:
    """Return log10 enemy HP from the specification anchors."""
    if use_future_curve:
        return FUTURE_POWER_TABLE[wave]
    return (
        POWER_BASE_TABLE[wave]
        + POWER_BONUS_TABLE[wave] * bonus_scale
        - MIDGAME_RELIEF_TABLE[wave] * midgame_relief
    )


def weapon_base_power(wave: int, scale: float = 1.0) -> float:
    return WEAPON_POWER_TABLE[min(PRESTIGE_WAVE, max(0, wave))] * scale


def relic_average_power(wave: int, scale: float = 1.0) -> float:
    return RELIC_POWER_TABLE[min(PRESTIGE_WAVE, max(0, wave))] * scale


def wave_band_multiplier(wave: int) -> float:
    if wave >= 7500:
        return 5.06
    if wave >= 5000:
        return 3.38
    if wave >= 2500:
        return 2.25
    if wave >= 500:
        return 1.50
    return 1.0


def enemy_time_limit(wave: int, glass_cannons: int) -> float:
    base = 15.0 if wave % 10 == 0 else 10.0
    return max(1.0, base * 0.90**glass_cannons)


@dataclass
class PermanentState:
    atk: int = 0
    attack_speed: int = 0
    xp: int = 0
    banked_dp: int = 0
    interval_banked_dp: int = 0
    interval_dp_spent: int = 0
    interval_level: int = 0
    game_speed_level: int = 0
    game_speed_material_spent: float = 0.0
    max_wave: int = 0
    relic_unlocked: bool = False
    weapon_material: float = 0.0
    relic_material: float = 0.0
    weapon_acquisitions: int = 0
    weapon_generations: int = 0
    relic_drops: int = 0
    relic_generations: int = 0
    relic_duplicates: int = 0
    relic_types: set[int] = field(default_factory=set)
    first_big_bosses: set[int] = field(default_factory=set)
    relic_quality: float = 1.0
    seen_cards: set[str] = field(default_factory=set)
    interaction_seconds: float = 0.0
    card_decision_seconds: float = 0.0
    equipment_decision_seconds: float = 0.0
    forge_seconds: float = 0.0
    card_upgrade_seconds: float = 0.0
    automation_enabled: bool = False
    rare_card_automation_enabled: bool = False
    one_tap_workshop_enabled: bool = False
    memory_candidate_keys: tuple[str, ...] = ()
    memory_carries: int = 0
    memory_card_seconds: float = 0.0

    @property
    def total_levels(self) -> int:
        return self.atk + self.attack_speed + self.xp

    @property
    def rerolls(self) -> int:
        return 2 if self.total_levels >= 10 else 1

    @property
    def initial_xp(self) -> float:
        return 10.0 if self.total_levels >= 30 else 0.0

    @property
    def initial_card_points(self) -> int:
        if self.max_wave < 500:
            return 0
        points = 5 if self.total_levels >= 75 else 0
        if self.total_levels >= 125:
            points += 10
        return points

    @property
    def game_speed(self) -> float:
        if self.game_speed_level <= 0:
            return 1.0
        return GAME_SPEED_MULTIPLIERS[self.game_speed_level - 1]


@dataclass
class RunState:
    counts: collections.Counter[str] = field(default_factory=collections.Counter)
    tag_counts: collections.Counter[str] = field(default_factory=collections.Counter)
    xp: float = 0.0
    card_count: int = 0
    xp_level_count: int = 0
    weapon: bool = False
    weapon_power: float = 0.0
    weapon_rarity: str = "C"
    weapon_origin_wave: int = 0
    weapon_pity: int = 0
    kills: int = 0
    combat_seconds: float = 0.0
    choices: int = 0
    effect_version: int = 0
    card_points: int = 0
    card_points_spent: int = 0
    card_upgrades: collections.Counter[str] = field(default_factory=collections.Counter)
    cards_dissolved: collections.Counter[str] = field(default_factory=collections.Counter)
    card_upgrades_bought: int = 0
    growth_units: int = 0
    accelerated_units: int = 0
    boss_devourer_units: int = 0
    assimilation_power: float = 0.0
    perfect_overdrive_stacks: int = 0
    legendary_growth_log: float = 0.0
    momentum_ready: bool = False
    milestone_choices: set[int] = field(default_factory=set)
    synergy_tag: str | None = None
    allow_overdrive: bool = True
    checkpoint_power: dict[int, tuple[float, float, float, float]] = field(default_factory=dict)
    reach_elapsed: dict[int, tuple[float, float]] = field(default_factory=dict)
    w2500_state: dict[str, object] | None = None
    next_relic_drop: int = 0


@dataclass(frozen=True)
class Snapshot:
    log_dps: float
    base_attack_power: float
    all_damage: float
    attack_speed: float
    general_xp: float
    boss_xp: float
    first_strike_mult: float
    last_stand_mult: float
    execution_mult: float
    time_collapse: bool
    crit_chance: float
    crit_multiplier: float
    follow_rate: float
    multi_crit_tier: int
    dp_power: float
    weapon_power: float
    relic_power: float


@dataclass(frozen=True)
class RunResult:
    reached: int
    combat_seconds: float
    choices: int
    cards: int
    cards_dissolved: int
    card_upgrades: int
    card_points_spent: int
    card_points_left: int
    counts: collections.Counter[str]
    failure_wave: int | None
    checkpoints: dict[int, tuple[float, float, float, float]]
    reach_elapsed: dict[int, tuple[float, float]]
    w2500_state: dict[str, object] | None


@dataclass(frozen=True)
class TrialResult:
    profile: str
    success: bool
    first_reached: int
    best_failed_wave: int
    deaths: int
    attempts: int
    total_kills: int
    total_dp: int
    total_combat_seconds: float
    total_interaction_seconds: float
    total_card_decision_seconds: float
    total_equipment_decision_seconds: float
    total_forge_seconds: float
    total_card_upgrade_seconds: float
    total_choices: int
    total_cards_dissolved: int
    total_card_upgrades: int
    total_card_points_spent: int
    permanent_levels: int
    atk_levels: int
    as_levels: int
    xp_levels: int
    interval_level: int
    interval_dp_spent: int
    game_speed_level: int
    game_speed_material_spent: float
    final_cards: int
    final_cards_dissolved: int
    final_card_upgrades: int
    final_card_points_left: int
    final_counts: collections.Counter[str]
    allow_overdrive: bool
    run_reaches: tuple[int, ...]
    reach_seconds: dict[int, float]
    weapon_material: float
    relic_material: float
    weapon_generations: int
    relic_generations: int
    relic_drops: int
    memory_carries: int
    memory_card_seconds: float
    checkpoints: dict[int, tuple[float, float, float, float]]
    w2500_state: dict[str, object] | None


@dataclass(frozen=True)
class SimConfig:
    dp_growth: float = DP_GROWTH
    weapon_scale: float = 1.0
    relic_scale: float = 1.0
    milestone_power_scale: float = 1.0
    hp_bonus_scale: float = 1.0
    midgame_relief: float = 0.0
    max_attempts: int = 140
    automation_enabled: bool = True
    interval_enabled: bool = False
    game_speed_enabled: bool = True
    initial_card_points_enabled: bool = True
    sweep_enabled: bool = True
    reward_skip_enabled: bool = False
    reward_skip_unlock_wave: int = 1000
    reward_skip_rate: float = 0.10
    reward_skip_cap_wave: int = 500
    defense: DefenseConfig = field(default_factory=DefenseConfig)
    future_qol_enabled: bool = False
    future_sweep_multiplier: float = 0.55
    memory_card_enabled: bool = False
    memory_card_unlock_wave: int = 500
    target_wave: int = PRESTIGE_WAVE
    enemy_curve_scale: float = 1.0
    card_upgrade_cap: int = len(CARD_UPGRADE_COSTS)
    relic_selection_enabled: bool = True
    exponential_core_multiplier: float = 1.05
    exponential_core_unlock_wave: int = 5000
    disabled_card_keys: frozenset[str] = frozenset()
    take_mode: str = "legacy"


def enemy_progression_wave(wave: int, config: SimConfig) -> int:
    if config.target_wave == 5000:
        if config.defense.enabled and wave > 2500:
            return min(PRESTIGE_WAVE, round(interpolate_anchors(wave, VARIANT_E_ENEMY_WAVE_ANCHORS)))
        return min(PRESTIGE_WAVE, wave if wave <= 2500 else 2500 + (wave - 2500) * 3)
    return min(PRESTIGE_WAVE, max(1, round(wave * config.enemy_curve_scale)))


def progression_wave(wave: int, config: SimConfig) -> int:
    if config.target_wave == 5000:
        return min(
            PRESTIGE_WAVE,
            wave if wave <= 2500 else 2500 + round((wave - 2500) * 2.20),
        )
    return min(PRESTIGE_WAVE, max(1, round(wave * config.enemy_curve_scale)))


def progression_units(wave: int, config: SimConfig) -> float:
    return 2.20 if config.target_wave == 5000 and wave > 2500 else 1.0


def configured_enemy_power(wave: int, config: SimConfig) -> float:
    source_wave = enemy_progression_wave(wave, config)
    power = enemy_power(
        source_wave,
        config.hp_bonus_scale,
        config.midgame_relief,
        config.defense.use_future_power_curve,
    )
    if config.target_wave == 5000 and config.defense.enabled:
        power -= interpolate_anchors(wave, VARIANT_E_ENEMY_POWER_RELIEF_ANCHORS)
    return power


def n(counts: collections.Counter[str], key: str) -> int:
    return counts.get(key, 0)


def card_enhancement(run: RunState, key: str) -> float:
    """Multiplier for the positive numeric portion of one card name."""
    return 1.0 + 0.10 * run.card_upgrades.get(key, 0)


def enhanced_count(run: RunState, key: str) -> float:
    return float(n(run.counts, key)) * card_enhancement(run, key)


def positive_amp(run: RunState, key: str) -> float:
    return limit_amplification(run.counts) * card_enhancement(run, key)


def enhanceable(item: Card) -> bool:
    return item.rarity in {"C", "U", "R"} and "rule" not in item.tags


def limit_amplification(counts: collections.Counter[str]) -> float:
    amplification = 1.0
    if counts.get("limit_break", 0):
        amplification *= 1.20
    if counts.get("limit_shatter", 0):
        amplification *= 1.50
    return amplification


def milestone_damage_log(levels: int, scale: float = 1.0) -> float:
    multiplier = 1.0
    for requirement, reward in ((5, 1.20), (20, 1.50)):
        if levels >= requirement:
            multiplier *= reward
    power = sum(value for requirement, value in ((50, 1), (75, 2), (100, 3), (125, 4), (150, 5)) if levels >= requirement)
    return math.log10(multiplier) + power * scale


def log10_weighted(values: list[tuple[float, float]]) -> float:
    """log10(sum(weight * 10**log_value)) for positive weights."""
    peak = max(log_value for weight, log_value in values if weight > 0)
    scaled = sum(weight * 10 ** (log_value - peak) for weight, log_value in values if weight > 0)
    return peak + math.log10(scaled)


def crit_log_multiplier(chance: float, multiplier: float, counts: collections.Counter[str]) -> float:
    chance = max(0.0, chance)
    if not n(counts, "multi_crit"):
        return math.log10(1 + min(1.0, chance) * (multiplier - 1))

    raw_tier = math.floor(chance + 1e-12)
    fraction = chance - raw_tier

    def effective_tier(tier: int) -> int:
        if n(counts, "critical_geometry"):
            return tier + tier // 3
        return tier

    def tier_log(tier: int) -> float:
        effective = effective_tier(tier)
        if n(counts, "critical_singularity"):
            return effective * math.log10(multiplier)
        return math.log10(1 + effective * (multiplier - 1))

    if fraction <= 1e-12:
        return tier_log(raw_tier)
    return log10_weighted(((1 - fraction, tier_log(raw_tier)), (fraction, tier_log(raw_tier + 1))))


def dynamic_damage_log(run: RunState, permanent: PermanentState, config: SimConfig) -> float:
    counts = run.counts
    effective_kills = progression_wave(run.kills, config)
    value = (effective_kills // 10) * counts.get("escalation", 0) * math.log10(1 + 0.05 * positive_amp(run, "escalation"))
    value += run.growth_units * math.log10(1 + 0.05 * positive_amp(run, "growth_engine"))
    value += run.boss_devourer_units * math.log10(1 + 0.15 * positive_amp(run, "boss_devourer"))
    value += run.assimilation_power
    value += run.legendary_growth_log
    if run.momentum_ready and counts.get("momentum", 0):
        value += counts["momentum"] * math.log10(1 + 0.50 * positive_amp(run, "momentum"))
    if permanent.relic_unlocked:
        value += math.log10(1 + 0.01 * (effective_kills // 10))
    value += relic_average_power(progression_wave(permanent.max_wave, config), config.relic_scale) * permanent.relic_quality
    value += run.perfect_overdrive_stacks * math.log10(1.01)
    if counts.get("final_equation", 0):
        value *= 1.10
    return value


def compute_snapshot(
    run: RunState,
    permanent: PermanentState,
    boss: bool,
    config: SimConfig = SimConfig(),
) -> Snapshot:
    counts = run.counts
    amp = limit_amplification(counts)

    crit_chance = (
        0.01
        + 0.10 * amp * enhanced_count(run, "critical_eye")
        + 0.03 * amp * enhanced_count(run, "critical_power")
        + 0.06 * amp * enhanced_count(run, "sharpened_edge")
        + 0.15 * amp * enhanced_count(run, "precise_strike")
        + 0.03 * amp * enhanced_count(run, "heavy_critical")
        + 0.10 * amp * enhanced_count(run, "critical_training")
        - 0.10 * n(counts, "brutal_critical")
    )
    crit_chance = max(0.0, crit_chance)

    crit_multiplier = (
        2.0
        + 0.50 * amp * enhanced_count(run, "critical_power")
        + 0.20 * amp * enhanced_count(run, "sharpened_edge")
        + 0.20 * amp * enhanced_count(run, "critical_training")
    )
    crit_multiplier *= (1 + 0.50 * positive_amp(run, "heavy_critical")) ** n(counts, "heavy_critical")
    crit_multiplier *= (1 + 0.50 * positive_amp(run, "brutal_critical")) ** n(counts, "brutal_critical")

    as_bonus = (
        0.20 * amp * enhanced_count(run, "rapid_fire")
        + 0.30 * amp * enhanced_count(run, "light_attack")
        + 0.35 * amp * enhanced_count(run, "overclock")
        + 0.05 * amp * (crit_chance // 0.25) * enhanced_count(run, "critical_momentum")
        + 0.05 * amp * (crit_chance // 0.20) * enhanced_count(run, "critical_engine")
    )
    base_interval = max(0.1, 1.0 - 0.1 * permanent.interval_level)
    attack_speed = (1.0 / base_interval) * 1.05**permanent.attack_speed * (1 + as_bonus)
    attack_speed *= 0.90 ** (n(counts, "heavy_blow") + n(counts, "brutal_force"))
    attack_speed *= 0.95 ** n(counts, "precise_strike")
    attack_speed *= 0.97 ** n(counts, "heavy_critical")
    attack_speed *= 0.98 ** n(counts, "study_break")

    xp_bonus = (
        0.20 * amp * enhanced_count(run, "experience")
        + 0.25 * amp * enhanced_count(run, "fast_learner")
        + 0.30 * amp * enhanced_count(run, "study_break")
        + 0.35 * amp * enhanced_count(run, "risky_study")
        + 0.03 * positive_amp(run, "accelerated_learning") * run.accelerated_units
    )
    general_xp = 1.05**permanent.xp * (1 + xp_bonus)
    general_xp *= 0.90 ** n(counts, "battle_focus")
    if permanent.relic_unlocked:
        general_xp *= 1.02
    boss_xp = general_xp * (
        1 + 1.00 * amp * enhanced_count(run, "scholar") + 0.25 * amp * enhanced_count(run, "boss_research")
    )
    if permanent.total_levels >= 75:
        boss_xp *= 1.50

    attack_bonus = (
        0.25 * amp * enhanced_count(run, "power_up")
        + 0.40 * amp * enhanced_count(run, "heavy_blow")
        + 0.50 * amp * enhanced_count(run, "glass_cannon")
        + 0.50 * amp * enhanced_count(run, "brutal_force")
    )
    log_attack = permanent.atk * math.log10(1.10) + math.log10(1 + attack_bonus)
    log_attack += n(counts, "light_attack") * math.log10(0.90)
    log_attack += n(counts, "fast_learner") * math.log10(0.98)
    log_attack += n(counts, "overclock") * math.log10(0.90)
    if run.weapon:
        log_attack += run.weapon_power
    if permanent.relic_unlocked:
        log_attack += math.log10(1.02)
    if n(counts, "double_scaling"):
        log_attack += math.log10(1 + 0.25 * max(0.0, attack_speed - 1))
    if n(counts, "exponential_core"):
        log_attack *= config.exponential_core_multiplier

    xp_excess = max(0.0, general_xp - 1.0)
    all_damage_bonus = (
        0.15 * amp * enhanced_count(run, "steady_force")
        + 0.20 * amp * enhanced_count(run, "battle_focus")
        + 0.10 * amp * xp_excess * enhanced_count(run, "battle_scholar")
        + 0.03 * amp * (crit_chance // 0.10) * enhanced_count(run, "critical_conversion")
        + 0.25 * amp * xp_excess * enhanced_count(run, "knowledge_conversion")
        + 0.50 * xp_excess * n(counts, "perfect_learning")
    )
    log_damage = log_attack + math.log10(attack_speed)
    log_damage += crit_log_multiplier(crit_chance, crit_multiplier, counts)
    log_damage += math.log10(1 + all_damage_bonus)
    # Event-driven growth stacks are separate multiplicative engines. Static
    # all-Damage bonuses above remain additive within their shared category.
    effective_kills = progression_wave(run.kills, config)
    log_damage += (effective_kills // 10) * n(counts, "escalation") * math.log10(1 + 0.05 * positive_amp(run, "escalation"))
    log_damage += run.growth_units * math.log10(1 + 0.05 * positive_amp(run, "growth_engine"))
    log_damage += run.boss_devourer_units * math.log10(1 + 0.15 * positive_amp(run, "boss_devourer"))
    milestone_log = milestone_damage_log(permanent.total_levels, config.milestone_power_scale)
    log_damage += milestone_log
    log_damage += run.assimilation_power
    log_damage += run.legendary_growth_log

    # Negative effects are deliberately not amplified by Limit Break/Shatter.
    log_damage += n(counts, "risky_study") * math.log10(0.90)
    if boss:
        log_damage += math.log10(1 + 0.40 * amp * enhanced_count(run, "boss_research"))
    else:
        log_damage += n(counts, "boss_research") * math.log10(0.95)

    # Expected follow-up damage, including the agreed recursion cap.
    if n(counts, "follow_up_strike"):
        follow_rate = 0.10 * amp + 0.15 * amp * enhanced_count(run, "double_strike")
        follow_damage = 0.50 * amp + 0.25 * amp * enhanced_count(run, "double_strike")
        q = min(0.50, 0.25 * follow_rate)
        chain = 1.0
        if n(counts, "recursive_follow_up"):
            chain = 1 / (1 - q)
        elif n(counts, "follow_up_echo"):
            chain = 1 + q
        log_damage += math.log10(1 + follow_rate * chain * follow_damage)

    if n(counts, "infinite_barrage"):
        excess_steps = math.floor(max(0.0, attack_speed - 1.0) + 1e-12)
        log_damage += excess_steps * math.log10(1.25)
    if n(counts, "knowledge_collapse"):
        excess_steps = math.floor(xp_excess + 1e-12)
        log_damage += excess_steps * math.log10(1.30)
    if run.momentum_ready and n(counts, "momentum"):
        log_damage += n(counts, "momentum") * math.log10(1 + 0.50 * positive_amp(run, "momentum"))
    if permanent.relic_unlocked:
        log_damage += math.log10(1 + 0.01 * (effective_kills // 10))
    average_relic = relic_average_power(progression_wave(permanent.max_wave, config), config.relic_scale) * permanent.relic_quality
    log_damage += average_relic
    log_damage += run.perfect_overdrive_stacks * math.log10(1.01)

    if n(counts, "final_equation"):
        log_damage *= 1.10

    follow_rate = 0.0
    if n(counts, "follow_up_strike"):
        follow_rate = 0.10 * amp + 0.15 * amp * enhanced_count(run, "double_strike")
    fixed_relic = 0.0
    if permanent.relic_unlocked:
        fixed_relic = math.log10(1.02) + math.log10(1 + 0.01 * (effective_kills // 10))
    dp_power = (
        permanent.atk * math.log10(1.10)
        + permanent.attack_speed * math.log10(1.05)
        + math.log10(1.0 / base_interval)
        + milestone_log
    )

    return Snapshot(
        log_dps=log_damage,
        base_attack_power=log_attack,
        all_damage=1 + all_damage_bonus,
        attack_speed=attack_speed,
        general_xp=general_xp,
        boss_xp=boss_xp,
        first_strike_mult=(1 + 0.40 * positive_amp(run, "first_strike")) ** n(counts, "first_strike"),
        last_stand_mult=(1 + 0.75 * positive_amp(run, "last_stand")) ** n(counts, "last_stand"),
        execution_mult=(1 + 1.50 * amp) if n(counts, "execution") else 1.0,
        time_collapse=bool(n(counts, "time_collapse")),
        crit_chance=crit_chance,
        crit_multiplier=crit_multiplier,
        follow_rate=follow_rate,
        multi_crit_tier=math.floor(crit_chance + 1e-12) if n(counts, "multi_crit") else 0,
        dp_power=dp_power,
        weapon_power=run.weapon_power if run.weapon else 0.0,
        relic_power=average_relic + fixed_relic,
    )


def time_curve_integral(start: float, end: float, limit: float, enabled: bool) -> float:
    if end <= start:
        return 0.0
    if not enabled:
        return end - start
    pivot = max(1e-9, limit - 1.0)
    before_end = min(end, pivot)
    total = 0.0
    if before_end > start:
        a = start
        b = before_end
        total += (b - a) + 4 * (b**3 - a**3) / (3 * pivot**2)
    if end > pivot:
        total += 5 * (end - max(start, pivot))
    return total


def temporal_integral(time: float, limit: float, snapshot: Snapshot) -> float:
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
        cuts = sorted({0.0, min(time, 3.0), min(time, max(0.0, limit - 3.0)), min(time, limit - 1.0), time})
        total = 0.0
        for start, end in zip(cuts, cuts[1:]):
            if end <= start:
                continue
            middle = (start + end) / 2
            multiplier = 1.0
            if middle < 3.0:
                multiplier *= first_mult
            if middle >= limit - 3.0:
                multiplier *= last_mult
            total += multiplier * time_curve_integral(start, end, limit, collapse)
        return total

    return times, tuple(integral_at(value) for value in times)


def time_to_kill(
    log_hp: float,
    limit: float,
    snapshot: Snapshot,
    log_dps: float | None = None,
) -> float | None:
    required_ratio = 0.70 + 0.30 / snapshot.execution_mult
    effective_log_dps = snapshot.log_dps if log_dps is None else log_dps
    log_required_integral = log_hp + math.log10(required_ratio) - effective_log_dps
    if log_required_integral > 308:
        return None
    required = 10**log_required_integral
    if (
        not snapshot.time_collapse
        and abs(snapshot.first_strike_mult - 1.0) < 1e-12
        and abs(snapshot.last_stand_mult - 1.0) < 1e-12
    ):
        attacks = max(1, math.ceil(required * snapshot.attack_speed - 1e-12))
        discrete_time = attacks / snapshot.attack_speed
        return discrete_time if discrete_time <= limit + 1e-12 else None
    first = round(snapshot.first_strike_mult, 10)
    last = round(snapshot.last_stand_mult, 10)
    times, integrals = temporal_lookup(limit, first, last, snapshot.time_collapse)
    if required > integrals[-1] + 1e-12:
        return None
    index = bisect.bisect_left(integrals, required)
    if index <= 0:
        return 0.0
    low_i, high_i = integrals[index - 1], integrals[index]
    if high_i <= low_i:
        return times[index]
    fraction = (required - low_i) / (high_i - low_i)
    continuous_time = times[index - 1] + (times[index] - times[index - 1]) * fraction
    attacks = max(1, math.ceil(continuous_time * snapshot.attack_speed - 1e-12))
    discrete_time = attacks / snapshot.attack_speed
    return discrete_time if discrete_time <= limit + 1e-12 else None


def time_to_kill_with_defense(
    wave: int,
    total_power: float,
    limit: float,
    snapshot: Snapshot,
    log_dps: float,
    config: SimConfig,
) -> float | None:
    """Approximate a fight with log-space Defense and Armor Break.

    Normal enemies use a short fixed-point solve: Break is sampled near the
    middle of the prospective fight, then the remaining Defense is added to
    the HP requirement.  The final W10,000 boss is intentionally different:
    its Armor must break completely before its literal 1e308 HP phase starts.
    This is a balance-model approximation, not per-hit object simulation.
    """
    defense_config = config.defense
    if not defense_config.enabled:
        return time_to_kill(total_power, limit, snapshot, log_dps)

    final_boss = wave == config.target_wave
    hp = total_power if final_boss else hp_power(total_power, wave, defense_config)
    defense = defense_power(wave, defense_config)
    if defense <= 1e-12:
        return time_to_kill(hp, limit, snapshot, log_dps)

    if final_boss and defense_config.final_boss_requires_full_break:
        break_seconds = armor_break_time(
            wave=wave,
            attack_speed=snapshot.attack_speed,
            crit_chance=snapshot.crit_chance,
            crit_multiplier=snapshot.crit_multiplier,
            follow_rate=snapshot.follow_rate,
            limit=limit,
            config=defense_config,
        )
        if break_seconds is None:
            return None
        hp_seconds = time_to_kill(hp, limit - break_seconds, snapshot, log_dps)
        if hp_seconds is None:
            return None
        return break_seconds + hp_seconds

    estimate = time_to_kill(hp + defense, limit, snapshot, log_dps)
    if estimate is None:
        estimate = limit
    for _ in range(4):
        sample_seconds = min(limit, estimate * defense_config.average_break_time_ratio)
        residual = remaining_defense_power(
            wave=wave,
            attack_speed=snapshot.attack_speed,
            crit_chance=snapshot.crit_chance,
            crit_multiplier=snapshot.crit_multiplier,
            follow_rate=snapshot.follow_rate,
            seconds=sample_seconds,
            config=defense_config,
        )
        next_estimate = time_to_kill(hp + residual, limit, snapshot, log_dps)
        if next_estimate is None:
            return None
        if abs(next_estimate - estimate) <= 0.001:
            return next_estimate
        estimate = next_estimate
    return estimate


def rarity_chances(permanent: PermanentState) -> tuple[tuple[str, float], ...]:
    rare_bonus = 0.01 if permanent.total_levels >= 100 else 0.0
    if permanent.max_wave >= 2500:
        return (("C", 0.9345 - rare_bonus), ("U", 0.05), ("R", 0.01 + rare_bonus), ("E", 0.005), ("L", 0.0005))
    if permanent.max_wave >= 500:
        return (("C", 0.938 - rare_bonus), ("U", 0.05), ("R", 0.01 + rare_bonus), ("E", 0.002))
    return (("C", 0.94 - rare_bonus), ("U", 0.05), ("R", 0.01 + rare_bonus))


def available_cards(
    rarity: str,
    run: RunState,
    permanent: PermanentState,
    config: SimConfig,
) -> list[Card]:
    unlocked_wave = max(run.kills, permanent.max_wave)
    return [
        item
        for item in CARDS_BY_RARITY[rarity]
        if (
            config.exponential_core_unlock_wave
            if item.key == "exponential_core"
            else item.unlock_wave
        )
        <= unlocked_wave
        and item.key not in config.disabled_card_keys
        and (run.allow_overdrive or item.key != "perfect_overdrive")
        and not (item.unique and n(run.counts, item.key))
    ]


def draw_rarity(rng: random.Random, permanent: PermanentState) -> str:
    value = rng.random()
    cumulative = 0.0
    for rarity, chance in rarity_chances(permanent):
        cumulative += chance
        if value < cumulative:
            return rarity
    return "C"


def draw_hand(
    rng: random.Random,
    run: RunState,
    permanent: PermanentState,
    config: SimConfig,
    forced_rarity: str | None = None,
    forced_card: str | None = None,
    excluded: set[str] | None = None,
    starter_guarantee: bool = False,
) -> list[Card]:
    excluded = set() if excluded is None else set(excluded)
    hand: list[Card] = []
    if forced_card:
        hand.append(CARD_BY_KEY[forced_card])
    for _ in range(3 - len(hand)):
        rarity = forced_rarity or draw_rarity(rng, permanent)
        candidates = [
            item
            for item in available_cards(rarity, run, permanent, config)
            if item.key not in excluded and item.key not in {picked.key for picked in hand}
        ]
        if not candidates:
            for fallback in ("R", "U", "C"):
                candidates = [
                    item
                    for item in available_cards(fallback, run, permanent, config)
                    if item.key not in excluded and item.key not in {picked.key for picked in hand}
                ]
                if candidates:
                    break
        hand.append(rng.choice(candidates))
    if starter_guarantee and not any(item.key in STARTER_SAFE_KEYS for item in hand):
        candidates = [CARD_BY_KEY[key] for key in STARTER_SAFE_ORDER if key not in {item.key for item in hand}]
        hand[0] = rng.choice(candidates)
    return hand


def acquire_card(run: RunState, item: Card) -> None:
    run.counts[item.key] += 1
    for tag in item.tags:
        run.tag_counts[tag] += 1
    # These engines count their own acquisition and every later card acquisition.
    run.growth_units += n(run.counts, "growth_engine")
    run.accelerated_units += n(run.counts, "accelerated_learning")
    run.card_count += 1
    run.choices += 1
    run.effect_version += 1


def carry_memory_card(
    rng: random.Random,
    profile: str,
    run: RunState,
    permanent: PermanentState,
    config: SimConfig,
) -> None:
    """Carry one prior-run Common/Uncommon card after the Wave 500 unlock.

    The live design is a random three-choice restart bonus: the pool contains
    distinct C/U card names actually taken in the immediately previous run.
    It is free in XP/Card Point terms, but still costs one second to select.
    """
    if (
        not config.memory_card_enabled
        or permanent.max_wave < config.memory_card_unlock_wave
        or not permanent.memory_candidate_keys
    ):
        return
    # Do not advance the main gameplay RNG merely by enabling this QoL.
    # The clone keeps paired seed comparisons focused on the carried card,
    # while downstream draft/drop divergence still happens naturally when the
    # extra card changes the run.
    memory_rng = random.Random()
    memory_rng.setstate(rng.getstate())
    option_keys = memory_rng.sample(
        permanent.memory_candidate_keys,
        k=min(3, len(permanent.memory_candidate_keys)),
    )
    options = [CARD_BY_KEY[key] for key in option_keys]
    selected = max(
        options,
        key=lambda item: card_score(profile, item, run, permanent, 1, config),
    )
    acquire_card(run, selected)
    permanent.memory_carries += 1
    permanent.memory_card_seconds += MEMORY_CARD_DECISION_SECONDS
    permanent.interaction_seconds += MEMORY_CARD_DECISION_SECONDS


def store_memory_candidates(result: RunResult, permanent: PermanentState) -> None:
    """Keep only distinct prior-run C/U names; card refinement never carries."""
    permanent.memory_candidate_keys = tuple(
        sorted(
            key
            for key, count in result.counts.items()
            if count > 0 and CARD_BY_KEY[key].rarity in {"C", "U"}
        )
    )


def record_card_decision(
    permanent: PermanentState,
    item: Card,
    rerolls_used: int,
    automated: bool = False,
) -> None:
    if automated:
        permanent.seen_cards.add(item.key)
        return
    seconds = (
        NEW_CARD_DECISION_SECONDS if item.key not in permanent.seen_cards else CARD_DECISION_SECONDS
    )
    seconds += rerolls_used * REROLL_SECONDS
    permanent.interaction_seconds += seconds
    permanent.card_decision_seconds += seconds
    permanent.seen_cards.add(item.key)


def dissolve_card(run: RunState, item: Card) -> None:
    run.card_points += CARD_POINT_VALUE[item.rarity]
    run.cards_dissolved[item.rarity] += 1
    run.choices += 1


POTENTIAL = {
    "overflow": 0.05,
    "follow_up_strike": 0.08,
    "accelerated_learning": 0.08,
    "growth_engine": 0.10,
    "boss_devourer": 0.10,
    "multi_crit": 0.12,
    "critical_geometry": 0.12,
    "follow_up_echo": 0.10,
    "boss_assimilation": 0.35,
    "limit_break": 0.18,
    "critical_singularity": 0.25,
    "recursive_follow_up": 0.15,
    "perfect_overdrive": 0.70,
    "limit_shatter": 0.30,
    "exponential_core": 0.40,
    "final_equation": 0.60,
}


def card_score(
    profile: str,
    item: Card,
    run: RunState,
    permanent: PermanentState,
    next_wave: int,
    config: SimConfig,
) -> float:
    # This intentionally cheap heuristic replaces the former full combat
    # recomputation for every card in every hand.  The three weights are the
    # declared player policies, not an omniscient optimizer.
    rarity = {"C": 1.0, "U": 1.25, "R": 1.65, "E": 2.20, "L": 3.0}[item.rarity]
    damage = rarity * (
        1.0 * ("atk" in item.tags)
        + 1.0 * ("as" in item.tags)
        + 1.0 * ("damage" in item.tags)
        + 0.55 * ("crit" in item.tags)
        + 0.70 * ("followup" in item.tags)
        + (1.0 if next_wave % 10 == 0 and "boss" in item.tags else 0.0)
    )
    xp = rarity * (1.0 if "xp" in item.tags else 0.0)
    future = rarity * (
        0.8 * ("growth" in item.tags)
        + 0.7 * ("engine" in item.tags)
        + 0.5 * ("rule" in item.tags)
        + 0.8 * ("exponent" in item.tags)
    )
    future += 5.0 * POTENTIAL.get(item.key, 0.0)

    # Defense is a late-run check.  These tags do not add a new card effect;
    # they tell the choice model that AS, Crit, and Follow-Up also contribute
    # to Armor Break, not only to displayed DPS.
    armor_break = rarity * (
        1.30 * ("as" in item.tags)
        + 1.00 * ("crit" in item.tags)
        + 1.00 * ("followup" in item.tags)
    )

    synergy = 0.0
    build_tags = ("crit", "followup", "xp", "as", "atk", "damage")
    if run.synergy_tag and run.synergy_tag in item.tags:
        synergy += 2.0 * rarity
    for tag in build_tags:
        owned = run.tag_counts.get(tag, 0)
        if tag in item.tags:
            synergy += min(2.0, owned * 0.12) * rarity
    if item.rarity in {"C", "U"}:
        synergy *= 0.25

    # Immediate downsides matter most to the damage profile.
    risk = 0.45 * rarity if "risk" in item.tags else 0.0
    boss_soon = 0.35 * rarity if next_wave % 10 == 0 and "boss" in item.tags else 0.0
    if profile == "damage":
        # A pure present-DPS picker repeatedly reaches the same later wall.
        # Keep damage dominant, but reserve enough XP and engines to convert
        # an early lead into a boss breakthrough.
        break_priority = (0.10 if next_wave < 2_500 else 0.50) * armor_break
        return 1.00 * damage + 0.20 * xp + 0.55 * future + 0.25 * synergy + break_priority + boss_soon - 0.80 * risk
    if profile == "balanced":
        break_priority = 0.0
        if config.defense.enabled:
            unlocked_wave = max(next_wave, permanent.max_wave)
            if unlocked_wave >= 2_500:
                break_priority = 0.10 * armor_break
        return (
            0.60 * damage
            + 0.15 * xp
            + 0.25 * future
            + 0.20 * synergy
            + break_priority
            + 0.5 * boss_soon
            - 0.5 * risk
        )
    # The first Rare+ card still defines the axis, but a synergy run must
    # first survive the immediate DPS check long enough to assemble it.
    return 0.65 * damage + 0.12 * xp + 0.35 * future + 0.30 * synergy + 0.25 * boss_soon - 0.25 * risk


def spend_card_points(
    profile: str,
    run: RunState,
    permanent: PermanentState,
    next_wave: int,
    config: SimConfig,
) -> None:
    """Focus shared run-only points into the strongest owned numeric card."""
    while True:
        candidates = [
            item
            for item in CARDS
            if n(run.counts, item.key)
            and enhanceable(item)
            and run.card_upgrades.get(item.key, 0)
            < min(config.card_upgrade_cap, len(CARD_UPGRADE_COSTS))
        ]
        if not candidates:
            return
        target = max(
            candidates,
            key=lambda item: card_score(profile, item, run, permanent, next_wave, config)
            * n(run.counts, item.key),
        )
        level = run.card_upgrades.get(target.key, 0)
        cost = CARD_UPGRADE_COSTS[level]
        if run.card_points < cost:
            return
        run.card_points -= cost
        run.card_points_spent += cost
        run.card_upgrades[target.key] += 1
        run.card_upgrades_bought += 1
        run.effect_version += 1
        if not (permanent.automation_enabled and permanent.max_wave >= 500):
            permanent.interaction_seconds += CARD_UPGRADE_SECONDS
            permanent.card_upgrade_seconds += CARD_UPGRADE_SECONDS


def _take_rng_digest(rng: random.Random) -> str:
    return hashlib.sha256(repr(rng.getstate()).encode("ascii")).hexdigest()[:16]


def _pe_take_winner(run, permanent, next_wave, config, phase, hand, eligible, legacy_winner):
    """Validate and rank only Take-eligible cards in the final hand."""
    from card_value_v01 import TARGET_KEYS, evaluate_card, predict_run_end

    eligible_keys = {item.key for item in eligible}
    details = [{"card_id": item.key, "take_eligible": item.key in eligible_keys,
                "legacy_score": card_score("balanced", item, run, permanent, next_wave, config),
                "pe_status": "not_evaluated" if item.key in eligible_keys else "ineligible_take"}
               for item in hand]
    unsupported = [item.key for item in eligible if item.key not in TARGET_KEYS]
    if unsupported:
        for entry in details:
            if entry["card_id"] in unsupported:
                entry["pe_status"] = "unsupported_card"
        return legacy_winner, "fallback_legacy", "unsupported_card:" + ",".join(unsupported), details

    try:
        forecast = predict_run_end(sys.modules[__name__], run, permanent,
                                   next_wave, config, phase)
    except Exception as error:
        return legacy_winner, "fallback_legacy", f"forecast_error:{type(error).__name__}:{error}", details

    invalid = []
    entries = {entry["card_id"]: entry for entry in details}
    for item in eligible:
        entry = entries[item.key]
        try:
            value = evaluate_card(sys.modules[__name__], run, permanent, item,
                                  next_wave, config, phase=phase, forecast=forecast)
            entry.update({key: value.get(key) for key in (
                "immediate_combat_pe", "conditional_combat_pe", "growth_pe", "xp_pe",
                "total_pe", "predicted_run_end_wave", "prediction_confidence",
                "terminal_break_probability_delta", "conditional_status",
            )})
            total = value.get("total_pe")
            if total is None or not isinstance(total, (int, float)) or not math.isfinite(total):
                entry["pe_status"] = "invalid_total_pe"
                invalid.append(f"{item.key}:invalid_total_pe")
            else:
                entry["pe_status"] = "ok"
        except Exception as error:
            entry["pe_status"] = "evaluation_error"
            entry["pe_error"] = f"{type(error).__name__}:{error}"
            invalid.append(f"{item.key}:evaluation_error")
    if invalid:
        return legacy_winner, "fallback_legacy", ",".join(invalid), details
    values = {item.key: entries[item.key]["total_pe"] for item in eligible}
    winner = max(eligible, key=lambda item: values[item.key])
    return winner, "pe", None, details


def choose_card(
    rng: random.Random,
    profile: str,
    run: RunState,
    permanent: PermanentState,
    next_wave: int,
    config: SimConfig,
    forced_rarity: str | None = None,
    forced_card: str | None = None,
    allow_reroll: bool = True,
) -> None:
    if config.take_mode not in {"legacy", "pe"}:
        raise ValueError(f"unknown take mode: {config.take_mode}")
    log_decision = TAKE_BRANCH_ENABLED and profile == "balanced"
    if log_decision:
        TAKE_BRANCH_CONTEXT["decision_index"] = int(TAKE_BRANCH_CONTEXT.get("decision_index", 0)) + 1
        initial_rng = _take_rng_digest(rng)
        reroll_trace = []
    starter = forced_rarity is None and run.card_count < 2
    hand = draw_hand(
        rng,
        run,
        permanent,
        config,
        forced_rarity,
        forced_card,
        starter_guarantee=starter,
    )
    rerolls = permanent.rerolls if allow_reroll and forced_rarity is None else 0
    excluded: set[str] = set()
    best: Card | None = None
    best_score = -math.inf
    rerolls_used = 0
    for reroll_index in range(rerolls + 1):
        eligible = [item for item in hand if item.key in STARTER_SAFE_KEYS] if starter else hand
        if not eligible:
            eligible = hand
        if profile == "balanced" and SHADOW_CARD_VALUE_LIMIT > len(SHADOW_CARD_VALUE_ROWS):
            from card_value_v01 import TARGET_KEYS, evaluate_card, predict_run_end

            targets = [item for item in eligible if item.key in TARGET_KEYS]
            if targets:
                phase = "xp" if forced_rarity is None else "guaranteed"
                try:
                    forecast = predict_run_end(sys.modules[__name__], run, permanent, next_wave, config, phase)
                except Exception as error:
                    forecast = None
                    forecast_error = f"{type(error).__name__}: {error}"
                for candidate in targets[:SHADOW_CARD_VALUE_LIMIT - len(SHADOW_CARD_VALUE_ROWS)]:
                    try:
                        if forecast is None:
                            raise ValueError(forecast_error)
                        row = evaluate_card(sys.modules[__name__], run, permanent, candidate,
                                            next_wave, config, phase=phase, forecast=forecast)
                    except Exception as error:
                        # A diagnostic must never interrupt the legacy choice.
                        row = {"card_id": candidate.key,
                               "legacy_score": card_score(profile, candidate, run, permanent, next_wave, config),
                               "prediction_confidence": "error",
                               "prediction_reason": f"{type(error).__name__}: {error}",
                               "terminal_pe": None, "terminal_included": False}
                    row.update({"wave": next_wave, "hand": ",".join(item.key for item in hand),
                                "reroll_index": reroll_index, "forced_rarity": forced_rarity or ""})
                    SHADOW_CARD_VALUE_ROWS.append(row)
        scored = [
            (card_score(profile, item, run, permanent, next_wave, config), item)
            for item in eligible
        ]
        score, item = max(scored, key=lambda pair: pair[0])
        if log_decision:
            reroll_trace.append({"hand": [card.key for card in hand],
                                 "eligible": [card.key for card in eligible],
                                 "legacy_winner": item.key, "legacy_score": score,
                                 "reroll_index": reroll_index})
        if score > best_score:
            best_score, best = score, item
        threshold = {"damage": 1.35, "balanced": 1.10, "synergy": 1.00}[profile]
        if score >= threshold or reroll_index == rerolls:
            if log_decision:
                reroll_trace[-1]["stop_reason"] = "threshold" if score >= threshold else "exhausted"
            best = item
            break
        if log_decision:
            reroll_trace[-1]["stop_reason"] = "reroll"
        excluded.update(candidate.key for candidate in hand)
        hand = draw_hand(
            rng,
            run,
            permanent,
            config,
            excluded=excluded,
            starter_guarantee=starter,
        )
        rerolls_used += 1
    assert best is not None
    legacy_winner = best
    selected_score = card_score(profile, legacy_winner, run, permanent, next_wave, config)
    unlocked_wave = max(run.kills, permanent.max_wave)
    automated = False
    if permanent.automation_enabled and forced_rarity is None and forced_card is None:
        if permanent.rare_card_automation_enabled and unlocked_wave >= 5000:
            automated = all(item.rarity in {"C", "U", "R"} for item in hand)
        elif unlocked_wave >= 2500:
            automated = all(item.rarity in {"C", "U"} for item in hand)
        elif unlocked_wave >= 500:
            automated = all(item.rarity == "C" for item in hand)
    can_dissolve = (
        forced_rarity is None
        and forced_card is None
        and not starter
        and max(run.kills, permanent.max_wave) >= 500
    )
    dissolve_threshold = {"damage": 0.65, "balanced": 0.55, "synergy": 0.55}[profile]
    if log_decision:
        eligible_key_set = {item.key for item in eligible}
        log = {**TAKE_BRANCH_CONTEXT, "take_mode": config.take_mode,
               "next_wave": next_wave, "phase": "xp" if forced_rarity is None else "guaranteed",
               "forced_rarity": forced_rarity, "forced_card": forced_card, "starter": starter,
               "reroll_trace": reroll_trace, "rerolls_used": rerolls_used,
               "hand_keys": [card.key for card in hand],
               "hand_legacy_scores": {card.key: card_score(profile, card, run, permanent, next_wave, config)
                                      for card in hand},
               "eligible_keys": [card.key for card in eligible],
               "ineligible_keys": [card.key for card in hand if card.key not in eligible_key_set],
               "evaluated_pe_keys": [],
               "legacy_winner": legacy_winner.key, "legacy_score": selected_score,
               "legacy_refine_gate": can_dissolve and selected_score < dissolve_threshold,
               "pre_decision_rng_digest": initial_rng,
               "candidates": [{"card_id": card.key, "take_eligible": card.key in eligible_key_set,
                               "legacy_score": card_score(profile, card, run, permanent, next_wave, config),
                               "pe_status": "not_evaluated" if card.key in eligible_key_set else "ineligible_take"}
                              for card in hand]}
        before_upgrades = run.card_upgrades.copy()
    if can_dissolve and selected_score < dissolve_threshold:
        dissolved = max(
            hand,
            key=lambda item: (
                CARD_POINT_VALUE[item.rarity],
                -card_score(profile, item, run, permanent, next_wave, config),
            ),
        )
        record_card_decision(permanent, dissolved, rerolls_used, automated)
        dissolve_card(run, dissolved)
        spend_card_points(profile, run, permanent, next_wave, config)
        if log_decision:
            log.update({"action": "refine", "selected_card": dissolved.key,
                        "decision_source": "legacy", "fallback_reason": None,
                        "upgrades": dict(run.card_upgrades - before_upgrades),
                        "post_decision_rng_digest": _take_rng_digest(rng)})
            TAKE_BRANCH_ROWS.append(log)
        return
    decision_source = "legacy"
    fallback_reason = None
    if profile == "balanced" and config.take_mode == "pe":
        best, decision_source, fallback_reason, details = _pe_take_winner(
            run, permanent, next_wave, config,
            "xp" if forced_rarity is None else "guaranteed", hand, eligible, legacy_winner)
        if log_decision:
            log["candidates"] = details
            log["evaluated_pe_keys"] = [entry["card_id"] for entry in details
                                        if entry["pe_status"] in {"ok", "invalid_total_pe", "evaluation_error"}]
    if profile == "synergy" and run.synergy_tag is None and best.rarity in {"R", "E", "L"}:
        for tag in ("crit", "followup", "xp", "as", "atk", "damage"):
            if tag in best.tags:
                run.synergy_tag = tag
                break
    record_card_decision(permanent, best, rerolls_used, automated)
    acquire_card(run, best)
    spend_card_points(profile, run, permanent, next_wave, config)
    if log_decision:
        log.update({"action": "take", "selected_card": best.key,
                    "decision_source": decision_source, "fallback_reason": fallback_reason,
                    "upgrades": dict(run.card_upgrades - before_upgrades),
                    "post_decision_rng_digest": _take_rng_digest(rng)})
        TAKE_BRANCH_ROWS.append(log)


def matching_legendary(rng: random.Random, run: RunState) -> str:
    candidates: list[tuple[float, str]] = []
    if n(run.counts, "multi_crit"):
        candidates.append((float(run.tag_counts.get("crit", 0)), "critical_singularity"))
    if n(run.counts, "follow_up_strike"):
        candidates.append((float(run.tag_counts.get("followup", 0)), "recursive_follow_up"))
    candidates.append((float(run.tag_counts.get("as", 0)), "infinite_barrage"))
    candidates.append((float(run.tag_counts.get("xp", 0)), "knowledge_collapse"))
    positive = [entry for entry in candidates if entry[0] > 0]
    pool = positive if positive else candidates
    best_score = max(score for score, _ in pool)
    tied = [key for score, key in pool if score == best_score]
    return rng.choice(tied)


def process_guaranteed_choices(
    rng: random.Random,
    profile: str,
    run: RunState,
    permanent: PermanentState,
    next_wave: int,
    config: SimConfig,
) -> None:
    milestones = ((25, "U"), (100, "R"), (500, "E"), (2500, "L"))
    for wave, rarity in milestones:
        if run.kills == wave and wave not in run.milestone_choices:
            permanent.max_wave = max(permanent.max_wave, wave)
            forced = matching_legendary(rng, run) if wave == 2500 else None
            choose_card(
                rng,
                profile,
                run,
                permanent,
                next_wave,
                config,
                rarity,
                forced,
                allow_reroll=False,
            )
            run.milestone_choices.add(wave)


def draw_from_distribution(rng: random.Random, distribution: tuple[tuple[str, float], ...]) -> str:
    value = rng.random()
    cumulative = 0.0
    for rarity, chance in distribution:
        cumulative += chance
        if value < cumulative:
            return rarity
    return distribution[-1][0]


def weapon_rarity_distribution(wave: int) -> tuple[tuple[str, float], ...]:
    if wave < 100:
        return (("C", 0.75), ("U", 0.22), ("R", 0.03))
    if wave < 500:
        return (("C", 0.60), ("U", 0.32), ("R", 0.08))
    if wave < 2500:
        return (("C", 0.35), ("U", 0.45), ("R", 0.18), ("E", 0.02))
    if wave < 5000:
        return (("C", 0.10), ("U", 0.30), ("R", 0.55), ("E", 0.049), ("L", 0.001))
    if wave < 7500:
        return (("C", 0.05), ("U", 0.20), ("R", 0.60), ("E", 0.149), ("L", 0.001))
    return (("C", 0.03), ("U", 0.15), ("R", 0.62), ("E", 0.198), ("L", 0.002))


def relic_rarity(rng: random.Random) -> str:
    return draw_from_distribution(rng, (("C", 0.60), ("U", 0.30), ("R", 0.095), ("E", 0.005)))


def next_geometric_drop(rng: random.Random, current_kills: int, rate: float = 0.0001) -> int:
    value = max(1e-15, 1.0 - rng.random())
    distance = max(1, math.ceil(math.log(value) / math.log(1.0 - rate)))
    return current_kills + distance


def refresh_relic_quality(permanent: PermanentState) -> None:
    acquisitions = permanent.relic_drops + permanent.relic_generations
    permanent.relic_quality = min(1.25, 0.98 + 0.015 * min(acquisitions, 15) + 0.005 * permanent.relic_duplicates)


def acquire_relic(
    rng: random.Random,
    permanent: PermanentState,
    config: SimConfig,
    generated: bool = False,
) -> None:
    if not config.relic_selection_enabled:
        return
    rarity = relic_rarity(rng)
    automated = permanent.automation_enabled and permanent.max_wave >= 500
    if not automated:
        permanent.interaction_seconds += EQUIPMENT_DECISION_SECONDS
        permanent.equipment_decision_seconds += EQUIPMENT_DECISION_SECONDS
    if generated:
        permanent.relic_generations += 1
        if not automated:
            permanent.interaction_seconds += FORGE_OPERATION_SECONDS
            permanent.forge_seconds += FORGE_OPERATION_SECONDS
    else:
        permanent.relic_drops += 1
    unowned = [index for index in range(12) if index not in permanent.relic_types]
    if unowned and rng.random() < (1.5 * len(unowned)) / (1.5 * len(unowned) + len(permanent.relic_types)):
        permanent.relic_types.add(rng.choice(unowned))
    elif rng.random() < 0.60:
        permanent.relic_duplicates += 1
    else:
        permanent.relic_material += MATERIAL_VALUE[rarity]
    refresh_relic_quality(permanent)


def forge_relics(rng: random.Random, permanent: PermanentState, config: SimConfig) -> None:
    if not config.relic_selection_enabled:
        return
    generated_any = False
    while True:
        cost = 10.0 * 2**permanent.relic_generations
        if permanent.relic_material + 1e-12 < cost:
            break
        permanent.relic_material -= cost
        acquire_relic(rng, permanent, config, generated=True)
        generated_any = True
    if (
        generated_any
        and permanent.automation_enabled
        and permanent.max_wave >= 500
        and not permanent.one_tap_workshop_enabled
    ):
        permanent.interaction_seconds += FORGE_OPERATION_SECONDS
        permanent.forge_seconds += FORGE_OPERATION_SECONDS


def equip_or_smelt_weapon(
    permanent: PermanentState,
    run: RunState,
    power: float,
    rarity: str,
    origin_wave: int,
) -> None:
    automated = permanent.automation_enabled and permanent.max_wave >= 500
    if not automated:
        permanent.interaction_seconds += EQUIPMENT_DECISION_SECONDS
        permanent.equipment_decision_seconds += EQUIPMENT_DECISION_SECONDS
    permanent.weapon_acquisitions += 1
    if not run.weapon or power > run.weapon_power:
        if run.weapon:
            permanent.weapon_material += MATERIAL_VALUE[run.weapon_rarity] * wave_band_multiplier(run.weapon_origin_wave)
        run.weapon = True
        run.weapon_power = power
        run.weapon_rarity = rarity
        run.weapon_origin_wave = origin_wave
    else:
        permanent.weapon_material += MATERIAL_VALUE[rarity] * wave_band_multiplier(origin_wave)


def roll_weapon(
    rng: random.Random,
    permanent: PermanentState,
    run: RunState,
    wave: int,
    config: SimConfig,
    minimum_rarity: str = "C",
    generated: bool = False,
) -> None:
    reward_wave = progression_wave(wave, config)
    distribution = weapon_rarity_distribution(reward_wave)
    allowed = [(rarity, chance) for rarity, chance in distribution if RARITY_ORDER.index(rarity) >= RARITY_ORDER.index(minimum_rarity)]
    total = sum(chance for _, chance in allowed)
    normalized = tuple((rarity, chance / total) for rarity, chance in allowed)
    rarity = draw_from_distribution(rng, normalized)
    power = weapon_base_power(reward_wave, config.weapon_scale) + RARITY_POWER[rarity] + rng.uniform(-0.10, 0.10)
    equip_or_smelt_weapon(permanent, run, max(0.0, power), rarity, reward_wave)
    if generated:
        permanent.weapon_generations += 1
        if not permanent.one_tap_workshop_enabled:
            permanent.interaction_seconds += FORGE_OPERATION_SECONDS
            permanent.forge_seconds += FORGE_OPERATION_SECONDS


def forge_starting_weapon(
    rng: random.Random,
    permanent: PermanentState,
    run: RunState,
    config: SimConfig,
) -> None:
    if permanent.weapon_acquisitions < 5 or permanent.max_wave < 10:
        return
    if permanent.max_wave >= 5000:
        input_units, minimum = 40.0, "E"
    elif permanent.max_wave >= 2500:
        input_units, minimum = 20.0, "R"
    elif permanent.max_wave >= 500:
        input_units, minimum = 10.0, "U"
    else:
        input_units, minimum = 5.0, "C"
    cost = input_units * wave_band_multiplier(permanent.max_wave)
    if permanent.weapon_material + 1e-12 < cost:
        return
    permanent.weapon_material -= cost
    boss_wave = max(10, permanent.max_wave - permanent.max_wave % 10)
    roll_weapon(rng, permanent, run, boss_wave, config, minimum, generated=True)


def process_boss_loot(
    rng: random.Random,
    permanent: PermanentState,
    run: RunState,
    wave: int,
    config: SimConfig,
) -> bool:
    changed_weapon = False
    if wave == 10:
        equip_or_smelt_weapon(permanent, run, math.log10(1.10), "C", wave)
        changed_weapon = True
    elif wave >= 20:
        guaranteed_big = wave % 100 == 0
        drop_chance = (0.50, 0.75, 1.0)[min(2, run.weapon_pity)]
        if guaranteed_big or rng.random() < drop_chance:
            roll_weapon(rng, permanent, run, wave, config)
            run.weapon_pity = 0
            changed_weapon = True
        else:
            run.weapon_pity += 1

    if wave % 100 == 0:
        band = wave_band_multiplier(wave)
        permanent.weapon_material += 5.0 * band
        permanent.relic_material += 1.0
        if wave not in permanent.first_big_bosses:
            permanent.first_big_bosses.add(wave)
            permanent.weapon_material += 5.0
            permanent.relic_material += 2.0
        forge_relics(rng, permanent, config)
    return changed_weapon


def convert_surplus_material(permanent: PermanentState, config: SimConfig) -> None:
    if not config.relic_selection_enabled:
        return
    next_relic_cost = 10.0 * 2**permanent.relic_generations
    if permanent.relic_material >= next_relic_cost:
        return
    reserve = 20.0 * wave_band_multiplier(max(10, permanent.max_wave))
    surplus = max(0.0, permanent.weapon_material - reserve)
    convertible = math.floor(surplus / 20.0)
    needed = math.ceil(next_relic_cost - permanent.relic_material)
    amount = min(convertible, needed)
    if amount > 0:
        permanent.weapon_material -= amount * 20.0
        permanent.relic_material += amount


def purchase_game_speed(permanent: PermanentState, config: SimConfig) -> None:
    """Buy unlocked first-prestige speed levels before optional material conversion."""
    if not config.game_speed_enabled:
        return
    while permanent.game_speed_level < len(GAME_SPEED_MATERIAL_COSTS):
        level_index = permanent.game_speed_level
        if permanent.max_wave < GAME_SPEED_WAVE_GATES[level_index]:
            break
        cost = GAME_SPEED_MATERIAL_COSTS[level_index]
        if permanent.weapon_material + 1e-12 < cost:
            break
        permanent.weapon_material -= cost
        permanent.game_speed_material_spent += cost
        permanent.game_speed_level += 1


def sweep_time_multiplier(wave: int, boss: bool, permanent: PermanentState, config: SimConfig) -> float:
    """Compress only previously proven normal-wave encounters.

    A player who has reached Wave 500 can sweep the older half of their best
    run in two-enemy packs.  Rewards and all wave milestones remain intact;
    this only represents fewer visible combat encounters during a reset.
    """
    if not config.sweep_enabled or boss or permanent.max_wave < 500:
        return 1.0
    if config.future_qol_enabled:
        # Proposed post-W2,500 compression: known normal enemies resolve in
        # four-enemy packs.  Once an enemy is known, replaying it is a QoL
        # action rather than a second combat check.  Rewards and game-time
        # card checks remain intact.
        sweep_end = min(2_500, permanent.max_wave)
        return config.future_sweep_multiplier if wave <= sweep_end else 1.0
    sweep_end = min(500, max(100, permanent.max_wave // 2))
    return 0.5 if wave <= sweep_end else 1.0


def reward_preserving_skip_end(permanent: PermanentState, config: SimConfig) -> int:
    """Return the last zero-combat-time wave for the next run.

    The waves are still resolved in order so rewards, cards, drops and pity
    remain identical to a normal run.  Only their combat time and failure
    check are skipped after the account has already proved the unlock wave.
    """
    if not config.reward_skip_enabled or permanent.max_wave < config.reward_skip_unlock_wave:
        return 0
    raw_end = int(permanent.max_wave * config.reward_skip_rate)
    rounded_end = raw_end // 10 * 10
    return min(config.reward_skip_cap_wave, permanent.max_wave, rounded_end)


def run_once(
    rng: random.Random,
    profile: str,
    permanent: PermanentState,
    config: SimConfig,
    allow_overdrive: bool,
    target_wave: int | None = None,
    initial_run: RunState | None = None,
    start_wave: int = 1,
) -> RunResult:
    target_wave = config.target_wave if target_wave is None else target_wave
    interaction_at_start = permanent.interaction_seconds
    run = initial_run
    if run is None:
        run = RunState(
            xp=permanent.initial_xp,
            card_points=permanent.initial_card_points if config.initial_card_points_enabled else 0,
            allow_overdrive=allow_overdrive,
        )
        run.next_relic_drop = next_geometric_drop(rng, 0)
    reward_skip_end = reward_preserving_skip_end(permanent, config)
    if initial_run is None:
        forge_starting_weapon(rng, permanent, run, config)
        carry_memory_card(rng, profile, run, permanent, config)
        while run.xp_level_count < len(CARD_COSTS) and run.xp >= CARD_COSTS[run.xp_level_count]:
            run.xp -= CARD_COSTS[run.xp_level_count]
            choose_card(rng, profile, run, permanent, 1, config)
            run.xp_level_count += 1

    snapshot_cache: dict[bool, tuple[Snapshot, float]] = {}
    for wave in range(start_wave, target_wave + 1):
        boss = wave % 10 == 0
        if boss not in snapshot_cache:
            snapshot_cache[boss] = (compute_snapshot(run, permanent, boss, config), dynamic_damage_log(run, permanent, config))
        snapshot, cached_dynamic = snapshot_cache[boss]
        effective_log_dps = snapshot.log_dps + dynamic_damage_log(run, permanent, config) - cached_dynamic
        pre_quick_learner = n(run.counts, "quick_learner")
        pre_limit_amp = limit_amplification(run.counts)
        limit = enemy_time_limit(wave, n(run.counts, "glass_cannon"))
        total_power = configured_enemy_power(wave, config)
        ttk = time_to_kill_with_defense(
            wave,
            total_power,
            limit,
            snapshot,
            effective_log_dps,
            config,
        )
        reward_skipped = wave <= reward_skip_end
        if reward_skipped and ttk is None:
            # A previously cleared wave is guaranteed during reward-preserving
            # sweep.  Keep it non-quick so conditional quick-kill bonuses are
            # not fabricated for a build that could not currently beat it.
            ttk = limit
        time_multiplier = (
            0.0
            if reward_skipped
            else sweep_time_multiplier(wave, boss, permanent, config)
        )
        if ttk is None:
            run.combat_seconds += limit * time_multiplier / permanent.game_speed
            permanent.max_wave = max(permanent.max_wave, run.kills)
            return RunResult(
                run.kills,
                run.combat_seconds,
                run.choices,
                run.card_count,
                sum(run.cards_dissolved.values()),
                run.card_upgrades_bought,
                run.card_points_spent,
                run.card_points,
                run.counts.copy(),
                wave,
                dict(run.checkpoint_power),
                dict(run.reach_elapsed),
                run.w2500_state,
            )

        run.combat_seconds += ttk * time_multiplier / permanent.game_speed
        quick = ttk <= 3.0 + 1e-12
        had_momentum = n(run.counts, "momentum") > 0
        had_overdrive = allow_overdrive and n(run.counts, "perfect_overdrive") > 0
        run.kills = wave
        permanent.max_wave = max(permanent.max_wave, wave)
        progress_units = progression_units(wave, config)

        if wave == 100:
            permanent.relic_unlocked = True
            snapshot_cache.clear()
        if boss:
            if process_boss_loot(rng, permanent, run, wave, config):
                snapshot_cache.clear()
            purchase_game_speed(permanent, config)
        if boss:
            run.boss_devourer_units += progress_units * n(run.counts, "boss_devourer")
            run.assimilation_power += (
                progress_units * total_power * 0.0005 * n(run.counts, "boss_assimilation")
            )
        tier_logs = []
        if n(run.counts, "critical_singularity"):
            tier_logs.append(math.floor(snapshot.crit_chance + 1e-12))
        if n(run.counts, "recursive_follow_up"):
            tier_logs.append(math.floor(snapshot.follow_rate + 1e-12))
        if n(run.counts, "infinite_barrage"):
            tier_logs.append(math.floor(max(0.0, snapshot.attack_speed - 1.0) + 1e-12))
        if n(run.counts, "knowledge_collapse"):
            tier_logs.append(math.floor(max(0.0, snapshot.general_xp - 1.0) + 1e-12))
        for tier in tier_logs:
            run.legendary_growth_log += progress_units * math.log10(1 + min(0.01, 0.002 * tier))
        if quick and had_overdrive:
            run.perfect_overdrive_stacks += progress_units
        run.momentum_ready = quick and had_momentum

        if wave >= run.next_relic_drop:
            acquire_relic(rng, permanent, config)
            run.next_relic_drop = next_geometric_drop(rng, wave)

        effect_version_before = run.effect_version
        process_guaranteed_choices(rng, profile, run, permanent, wave + 1, config)

        base_xp = 1 + (progression_wave(wave, config) - 1) // 10
        # Use the pre-fight snapshot: milestone/card rewards earned after the
        # kill do not retroactively increase that enemy's XP.
        boss_factor = 10 if wave % 100 == 0 else 3
        gained = progress_units * base_xp * (
            boss_factor * snapshot.boss_xp if boss else snapshot.general_xp
        )
        if quick and pre_quick_learner:
            gained *= 1 + 0.30 * pre_limit_amp * pre_quick_learner
        run.xp += gained
        while run.xp_level_count < len(CARD_COSTS) and run.xp + 1e-12 >= CARD_COSTS[run.xp_level_count]:
            run.xp -= CARD_COSTS[run.xp_level_count]
            choose_card(rng, profile, run, permanent, wave + 1, config)
            run.xp_level_count += 1
        if run.effect_version != effect_version_before:
            snapshot_cache.clear()

        if wave in CHECKPOINTS:
            checkpoint = compute_snapshot(run, permanent, boss, config)
            card_power = checkpoint.log_dps - checkpoint.dp_power - checkpoint.weapon_power - checkpoint.relic_power
            run.checkpoint_power[wave] = (
                card_power,
                checkpoint.weapon_power,
                checkpoint.relic_power,
                checkpoint.dp_power,
            )
            if wave == 2500 and run.w2500_state is None:
                run.w2500_state = {
                    "base_atk": (
                        10**checkpoint.base_attack_power
                        if checkpoint.base_attack_power <= 308
                        else None
                    ),
                    "base_atk_power": checkpoint.base_attack_power,
                    "all_damage": checkpoint.all_damage,
                    "attack_speed": checkpoint.attack_speed,
                    "xp_multiplier": checkpoint.general_xp,
                    "crit_rate": checkpoint.crit_chance,
                    "crit_multiplier": checkpoint.crit_multiplier,
                    "multi_crit_tier": checkpoint.multi_crit_tier,
                    "follow_up_rate": checkpoint.follow_rate,
                    "legendary": sorted(
                        item.name
                        for item in CARDS
                        if item.rarity == "L" and n(run.counts, item.key)
                    ),
                }

        if wave in REACH_WAVES or wave in VARIANT_REACH_WAVES:
            run.reach_elapsed[wave] = (
                run.combat_seconds,
                permanent.interaction_seconds - interaction_at_start,
            )

        if wave >= target_wave:
            return RunResult(
                run.kills,
                run.combat_seconds,
                run.choices,
                run.card_count,
                sum(run.cards_dissolved.values()),
                run.card_upgrades_bought,
                run.card_points_spent,
                run.card_points,
                run.counts.copy(),
                None,
                dict(run.checkpoint_power),
                dict(run.reach_elapsed),
                run.w2500_state,
            )

    raise AssertionError("unreachable")


def next_dp_cost(total_levels: int, growth: float) -> int:
    return math.ceil(5 * growth**total_levels)


def spend_dp(permanent: PermanentState, profile: str, growth: float) -> None:
    cycles = {
        "damage": ("atk", "atk", "attack_speed", "atk", "attack_speed", "xp"),
        "balanced": ("atk", "attack_speed", "atk", "xp", "attack_speed"),
        "synergy": ("xp", "atk", "attack_speed", "atk", "attack_speed"),
    }
    choices = cycles[profile]
    while permanent.banked_dp >= next_dp_cost(permanent.total_levels, growth):
        cost = next_dp_cost(permanent.total_levels, growth)
        permanent.banked_dp -= cost
        stat = choices[permanent.total_levels % len(choices)]
        setattr(permanent, stat, getattr(permanent, stat) + 1)


def allocate_and_spend_dp(
    permanent: PermanentState,
    profile: str,
    gained: int,
    config: SimConfig,
) -> None:
    if not config.interval_enabled:
        permanent.banked_dp += gained
        spend_dp(permanent, profile, config.dp_growth)
        return
    share = INTERVAL_DP_SHARES[profile]
    interval_allocation = min(gained, int(round(gained * share)))
    permanent.interval_banked_dp += interval_allocation
    permanent.banked_dp += gained - interval_allocation
    while permanent.interval_level < len(INTERVAL_DP_COSTS):
        level_index = permanent.interval_level
        if permanent.max_wave < INTERVAL_WAVE_GATES[level_index]:
            break
        cost = INTERVAL_DP_COSTS[level_index]
        if permanent.interval_banked_dp < cost:
            break
        permanent.interval_banked_dp -= cost
        permanent.interval_dp_spent += cost
        permanent.interval_level += 1
    if permanent.interval_level >= len(INTERVAL_DP_COSTS):
        permanent.banked_dp += permanent.interval_banked_dp
        permanent.interval_banked_dp = 0
    spend_dp(permanent, profile, config.dp_growth)


def run_trial(
    rng: random.Random,
    profile: str,
    config: SimConfig,
    allow_overdrive: bool,
) -> TrialResult:
    permanent = PermanentState(
        automation_enabled=config.automation_enabled,
        rare_card_automation_enabled=config.future_qol_enabled,
        one_tap_workshop_enabled=config.future_qol_enabled,
    )
    total_kills = 0
    total_dp = 0
    total_seconds = 0.0
    total_choices = 0
    total_dissolved = 0
    total_card_upgrades = 0
    total_card_points_spent = 0
    first_reached = 0
    best_failed = 0
    final_result: RunResult | None = None
    reaches: list[int] = []
    reach_seconds: dict[int, float] = {}
    w2500_state: dict[str, object] | None = None

    for attempt in range(1, config.max_attempts + 1):
        if TAKE_BRANCH_ENABLED:
            TAKE_BRANCH_CONTEXT.update({"attempt": attempt, "decision_index": 0})
        combat_before = total_seconds
        interaction_before = permanent.interaction_seconds
        result = run_once(rng, profile, permanent, config, allow_overdrive)
        for wave, (combat_elapsed, interaction_elapsed) in result.reach_elapsed.items():
            reach_seconds.setdefault(
                wave,
                combat_before + interaction_before + combat_elapsed + interaction_elapsed,
            )
        reaches.append(result.reached)
        if attempt == 1:
            first_reached = result.reached
        total_kills += result.reached
        total_seconds += result.combat_seconds
        total_choices += result.choices
        total_dissolved += result.cards_dissolved
        total_card_upgrades += result.card_upgrades
        total_card_points_spent += result.card_points_spent
        final_result = result
        if w2500_state is None and result.w2500_state is not None:
            w2500_state = result.w2500_state
        store_memory_candidates(result, permanent)
        if result.reached >= config.target_wave:
            return TrialResult(
                profile=profile,
                success=True,
                first_reached=first_reached,
                best_failed_wave=best_failed,
                deaths=attempt - 1,
                attempts=attempt,
                total_kills=total_kills,
                total_dp=total_dp,
                total_combat_seconds=total_seconds,
                total_interaction_seconds=permanent.interaction_seconds,
                total_card_decision_seconds=permanent.card_decision_seconds,
                total_equipment_decision_seconds=permanent.equipment_decision_seconds,
                total_forge_seconds=permanent.forge_seconds,
                total_card_upgrade_seconds=permanent.card_upgrade_seconds,
                total_choices=total_choices,
                total_cards_dissolved=total_dissolved,
                total_card_upgrades=total_card_upgrades,
                total_card_points_spent=total_card_points_spent,
                permanent_levels=permanent.total_levels,
                atk_levels=permanent.atk,
                as_levels=permanent.attack_speed,
                xp_levels=permanent.xp,
                interval_level=permanent.interval_level,
                interval_dp_spent=permanent.interval_dp_spent,
                game_speed_level=permanent.game_speed_level,
                game_speed_material_spent=permanent.game_speed_material_spent,
                final_cards=result.cards,
                final_cards_dissolved=result.cards_dissolved,
                final_card_upgrades=result.card_upgrades,
                final_card_points_left=result.card_points_left,
                final_counts=result.counts,
                allow_overdrive=allow_overdrive,
                run_reaches=tuple(reaches),
                reach_seconds=reach_seconds,
                weapon_material=permanent.weapon_material,
                relic_material=permanent.relic_material,
                weapon_generations=permanent.weapon_generations,
                relic_generations=permanent.relic_generations,
                relic_drops=permanent.relic_drops,
                memory_carries=permanent.memory_carries,
                memory_card_seconds=permanent.memory_card_seconds,
                checkpoints=result.checkpoints,
                w2500_state=w2500_state,
            )

        best_failed = max(best_failed, result.reached)
        gained = result.reached // 5
        total_dp += gained
        allocate_and_spend_dp(permanent, profile, gained, config)
        purchase_game_speed(permanent, config)
        convert_surplus_material(permanent, config)
        forge_relics(rng, permanent, config)

    assert final_result is not None
    return TrialResult(
        profile=profile,
        success=False,
        first_reached=first_reached,
        best_failed_wave=best_failed,
        deaths=config.max_attempts,
        attempts=config.max_attempts,
        total_kills=total_kills,
        total_dp=total_dp,
        total_combat_seconds=total_seconds,
        total_interaction_seconds=permanent.interaction_seconds,
        total_card_decision_seconds=permanent.card_decision_seconds,
        total_equipment_decision_seconds=permanent.equipment_decision_seconds,
        total_forge_seconds=permanent.forge_seconds,
        total_card_upgrade_seconds=permanent.card_upgrade_seconds,
        total_choices=total_choices,
        total_cards_dissolved=total_dissolved,
        total_card_upgrades=total_card_upgrades,
        total_card_points_spent=total_card_points_spent,
        permanent_levels=permanent.total_levels,
        atk_levels=permanent.atk,
        as_levels=permanent.attack_speed,
        xp_levels=permanent.xp,
        interval_level=permanent.interval_level,
        interval_dp_spent=permanent.interval_dp_spent,
        game_speed_level=permanent.game_speed_level,
        game_speed_material_spent=permanent.game_speed_material_spent,
        final_cards=final_result.cards,
        final_cards_dissolved=final_result.cards_dissolved,
        final_card_upgrades=final_result.card_upgrades,
        final_card_points_left=final_result.card_points_left,
        final_counts=final_result.counts,
        allow_overdrive=allow_overdrive,
        run_reaches=tuple(reaches),
        reach_seconds=reach_seconds,
        weapon_material=permanent.weapon_material,
        relic_material=permanent.relic_material,
        weapon_generations=permanent.weapon_generations,
        relic_generations=permanent.relic_generations,
        relic_drops=permanent.relic_drops,
        memory_carries=permanent.memory_carries,
        memory_card_seconds=permanent.memory_card_seconds,
        checkpoints=final_result.checkpoints,
        w2500_state=w2500_state,
    )


def percentile(values: list[float] | list[int], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    position = (len(ordered) - 1) * q
    lo, hi = math.floor(position), math.ceil(position)
    if lo == hi:
        return float(ordered[lo])
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo)


def stat(values: list[float] | list[int], digits: int = 1) -> str:
    if not values:
        return "—"
    entries = (statistics.fmean(values), percentile(values, 0.10), percentile(values, 0.50), percentile(values, 0.90))
    return " / ".join(f"{value:.{digits}f}" for value in entries)


def simulate_batch(
    profile: str,
    allow_overdrive: bool,
    config: SimConfig,
    start: int,
    count: int,
    seed: int = SEED,
) -> tuple[str, bool, list[TrialResult]]:
    profile_offset = {"damage": 0, "balanced": 1_000_000, "synergy": 2_000_000}[profile]
    rows = []
    for trial_index in range(start, start + count):
        if TAKE_BRANCH_ENABLED:
            TAKE_BRANCH_CONTEXT.update({"seed": seed, "trial_index": trial_index,
                                        "profile": profile, "allow_overdrive": allow_overdrive})
        rng = random.Random(seed + profile_offset + trial_index)
        rows.append(run_trial(rng, profile, config, allow_overdrive))
    return profile, allow_overdrive, rows


def simulate(
    trials: int,
    config: SimConfig,
    workers: int = 1,
    seed: int = SEED,
) -> dict[tuple[str, bool], list[TrialResult]]:
    conditions = [(profile, allowed) for profile in ("damage", "balanced", "synergy") for allowed in (True, False)]
    output: dict[tuple[str, bool], list[TrialResult]] = {key: [] for key in conditions}
    if workers <= 1:
        for profile, allowed in conditions:
            _, _, rows = simulate_batch(profile, allowed, config, 0, trials, seed)
            output[(profile, allowed)] = rows
        return output

    jobs = []
    chunk = max(1, math.ceil(trials / workers))
    for profile, allowed in conditions:
        for start in range(0, trials, chunk):
            jobs.append((profile, allowed, config, start, min(chunk, trials - start), seed))
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(simulate_batch, *job) for job in jobs]
        for future in concurrent.futures.as_completed(futures):
            profile, allowed, rows = future.result()
            output[(profile, allowed)].extend(rows)
    for rows in output.values():
        rows.sort(key=lambda row: row.run_reaches)
    return output


def simulate_standard_batch(
    config: SimConfig,
    seed: int,
    start: int,
    count: int,
) -> list[TrialResult]:
    rows = []
    for trial_index in range(start, start + count):
        if TAKE_BRANCH_ENABLED:
            TAKE_BRANCH_CONTEXT.update({"seed": seed, "trial_index": trial_index,
                                        "profile": "balanced", "allow_overdrive": True})
        rng = random.Random(seed + 1_000_000 + trial_index)
        rows.append(run_trial(rng, "balanced", config, allow_overdrive=True))
    return rows


def simulate_standard(
    trials: int,
    config: SimConfig,
    seed: int,
    workers: int = 1,
) -> list[TrialResult]:
    if workers <= 1:
        return simulate_standard_batch(config, seed, 0, trials)

    rows: list[TrialResult] = []
    chunk = max(1, math.ceil(trials / workers))
    jobs = [
        (config, seed, start, min(chunk, trials - start))
        for start in range(0, trials, chunk)
    ]
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(simulate_standard_batch, *job) for job in jobs]
        for future in futures:
            rows.extend(future.result())
    return rows


def build_json_result(
    variant: str,
    rows: list[TrialResult],
    config: SimConfig,
) -> dict[str, object]:
    successes = [row for row in rows if row.success]
    reached_w2500 = [row for row in rows if 2500 in row.reach_seconds]

    def quantile(values: list[float], q: float) -> float | None:
        if not values:
            return None
        return round(percentile(values, q), 6)

    play_times = [
        (row.total_combat_seconds + row.total_interaction_seconds) / 3600
        for row in successes
    ]

    def reach_median(wave: int) -> float | None:
        values = [
            row.reach_seconds[wave] / 3600
            for row in successes
            if wave in row.reach_seconds
        ]
        return quantile(values, 0.50)

    w2500_trials = []
    for trial_index, row in enumerate(rows):
        state = row.w2500_state
        entry: dict[str, object] = {
            "trial": trial_index,
            "success": row.success,
            "best_wave": max(row.run_reaches),
            "reached_w2500": state is not None,
        }
        if state is not None:
            entry.update(
                {
                    key: round(value, 6) if isinstance(value, float) else value
                    for key, value in state.items()
                }
            )
        w2500_trials.append(entry)

    return {
        "variant": variant,
        "reward_skip_enabled": config.reward_skip_enabled,
        "reward_skip_unlock_wave": config.reward_skip_unlock_wave,
        "reward_skip_rate": config.reward_skip_rate,
        "reward_skip_cap_wave": config.reward_skip_cap_wave,
        "midgame_relief": config.midgame_relief,
        "success_rate": round(len(successes) / len(rows), 6),
        "reached_w2500_count": len(reached_w2500),
        "post_w2500_success_rate": (
            round(len(successes) / len(reached_w2500), 6) if reached_w2500 else None
        ),
        "play_time_p10": quantile(play_times, 0.10),
        "play_time_p50": quantile(play_times, 0.50),
        "play_time_p90": quantile(play_times, 0.90),
        "deaths_p50": quantile([float(row.deaths) for row in rows], 0.50),
        "best_wave_p50": quantile([float(max(row.run_reaches)) for row in rows], 0.50),
        "reach_w500_p50": reach_median(500),
        "reach_w2500_p50": reach_median(2500),
        "reach_w3500_p50": reach_median(3500),
        "reach_w4500_p50": reach_median(4500),
        "reach_w5000_p50": reach_median(5000),
        "w2500_trials": w2500_trials,
    }


def build_report(
    results: dict[tuple[str, bool], list[TrialResult]],
    trials: int,
    config: SimConfig,
    phase: str,
    seed: int = SEED,
) -> str:
    names = {"damage": "火力型", "balanced": "標準型", "synergy": "シナジー型"}

    def triplet(values: list[float], digits: int = 1) -> str:
        if not values:
            return "—"
        return f"{percentile(values, 0.10):.{digits}f} / {percentile(values, 0.50):.{digits}f} / {percentile(values, 0.90):.{digits}f}"

    lines = [
        f"# 第一転生までの第1版シミュレーション（{phase}）",
        "",
        "## 前提",
        "",
        f"- 3方針×Perfect Overdrive通常/除外、各条件{trials:,}試行（合計{trials * 6:,}試行、seed={seed}）",
        f"- 第一転生: Wave {PRESTIGE_WAVE:,} Boss、HP `1e308`",
        f"- DP価格`ceil(5×{config.dp_growth:.4f}^合計Lv)`、Weapon倍率{config.weapon_scale:.3f}、遺物倍率{config.relic_scale:.3f}、マイルストーンPower倍率{config.milestone_power_scale:.3f}、中盤敵Power補正倍率{config.hp_bonus_scale:.3f}、Wave500～2500最大緩和{config.midgame_relief:.2f} Power",
        f"- 統合工房: {'有効' if config.automation_enabled else '無効'}、ゲーム速度強化: {'有効' if config.game_speed_enabled else '無効'}、Lv75/125初期Card Point: {'有効' if config.initial_card_points_enabled else '無効'}、既踏破掃討: {'有効' if config.sweep_enabled else '無効'}、基礎攻撃間隔DP: {'有効' if config.interval_enabled else '無効'}",
        f"- Defense/Armor Break: {'有効' if config.defense.enabled else '無効'}、将来Enemy曲線: {'有効' if config.defense.use_future_power_curve else '無効'}、後半QoL圧縮: {'有効' if config.future_qol_enabled else '無効'}",
        f"- Memory Card: {'有効（Wave' + format(config.memory_card_unlock_wave, ',') + '初回到達後、前ランC/Uからランダム3択で1枚）' if config.memory_card_enabled else '無効'}",
        f"- 最大試行回数{config.max_attempts}。実プレイ時間は戦闘と仕様書記載の選択・装備・炉・カード強化操作を合算",
        "- 初期Crit率1%、Wave25 Power 1.325、Wave2500でビルド対応Legendaryを1枠確定、Wave500からカード精錬",
        "- 詳細仕様: `first_prestige_v1_spec.md`",
    ]

    lines.extend([
        "",
        "## 第一転生結果",
        "",
        "範囲表記は`P10 / 中央値 / P90`。失敗試行は時間分布から除外し、成功率を併記する。",
        "",
        "| 方針 | PO | 成功率 | 実プレイ時間(h) | 戦闘時間(h) | 死亡回数 | 初ランWave | 合計Lv |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ])
    for (profile, allowed), rows in results.items():
        successes = [row for row in rows if row.success]
        success_rate = len(successes) / len(rows)
        base = successes if successes else rows
        lines.append(
            f"| {names[profile]} | {'通常' if allowed else '除外'} | {success_rate:.1%} | "
            f"{triplet([(r.total_combat_seconds + r.total_interaction_seconds) / 3600 for r in successes], 2)} | "
            f"{triplet([r.total_combat_seconds / 3600 for r in successes], 2)} | "
            f"{triplet([float(r.deaths) for r in base], 0)} | {triplet([float(r.first_reached) for r in rows], 0)} | "
            f"{triplet([float(r.permanent_levels) for r in base], 0)} |"
        )

    lines.extend([
        "",
        "## DP振り分けと操作時間",
        "",
        "| 方針 | PO | ATK/AS/XP Lv中央値 | 間隔Lv/消費DP | 加速Lv/消費素材 | 操作合計 | カード | 装備判断 | 炉 | カード強化 | 総カード判断数 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for (profile, allowed), rows in results.items():
        successes = [row for row in rows if row.success]
        if successes:
            split = (
                f"{percentile([r.atk_levels for r in successes], .5):.0f}/"
                f"{percentile([r.as_levels for r in successes], .5):.0f}/"
                f"{percentile([r.xp_levels for r in successes], .5):.0f}"
            )
            interval = (
                f"{percentile([r.interval_level for r in successes], .5):.0f}/"
                f"{percentile([r.interval_dp_spent for r in successes], .5):.0f}"
            )
            game_speed = (
                f"{percentile([r.game_speed_level for r in successes], .5):.0f}/"
                f"{percentile([r.game_speed_material_spent for r in successes], .5):.0f}"
            )
            interaction = percentile([r.total_interaction_seconds / 3600 for r in successes], .5)
            card_time = percentile([r.total_card_decision_seconds / 3600 for r in successes], .5)
            equipment_time = percentile([r.total_equipment_decision_seconds / 3600 for r in successes], .5)
            forge_time = percentile([r.total_forge_seconds / 3600 for r in successes], .5)
            upgrade_time = percentile([r.total_card_upgrade_seconds / 3600 for r in successes], .5)
            choices = percentile([float(r.total_choices) for r in successes], .5)
            lines.append(
                f"| {names[profile]} | {'通常' if allowed else '除外'} | {split} | {interval} | {game_speed} | {interaction:.2f}h | "
                f"{card_time:.2f}h | {equipment_time:.2f}h | {forge_time:.2f}h | {upgrade_time:.2f}h | {choices:.0f} |"
            )
        else:
            lines.append(f"| {names[profile]} | {'通常' if allowed else '除外'} | — | — | — | — | — | — | — | — | — |")

    lines.extend(["", "## 各ランの到達Wave推移", "", "通常条件の中央値。", "", "| 方針 | Run1 | Run5 | Run10 | Run20 | Run40 | Run60 | 最終Run |", "|---|---:|---:|---:|---:|---:|---:|---:|"])
    for profile in ("damage", "balanced", "synergy"):
        rows = results[(profile, True)]
        cells = []
        for attempt in (1, 5, 10, 20, 40, 60):
            values = [row.run_reaches[min(attempt - 1, len(row.run_reaches) - 1)] for row in rows]
            cells.append(f"{percentile(values, .5):.0f}")
        finals = [row.run_reaches[-1] for row in rows]
        lines.append(f"| {names[profile]} | " + " | ".join(cells) + f" | {percentile(finals, .5):.0f} |")

    lines.extend([
        "",
        "## 初到達時刻",
        "",
        "通常条件の成功試行における、累積実プレイ時間の中央値。",
        "",
        "| 方針 | W100 | W500 | W2,500 | W5,000 | W7,500 |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for profile in ("damage", "balanced", "synergy"):
        rows = [row for row in results[(profile, True)] if row.success]
        cells = []
        for wave in REACH_WAVES:
            values = [row.reach_seconds[wave] / 3600 for row in rows if wave in row.reach_seconds]
            cells.append(f"{percentile(values, .5):.2f}h" if values else "—")
        lines.append(f"| {names[profile]} | " + " | ".join(cells) + " |")

    lines.extend(["", "## 成功ランのPower内訳", "", "通常条件の中央値。カード列にはカードによる指数・相互作用の残差を含む。", "", "| 方針 | Wave | カード | 武器 | 遺物 | DP/マイルストーン | 合計DPS Power | 敵Power |", "|---|---:|---:|---:|---:|---:|---:|---:|"])
    for profile in ("damage", "balanced", "synergy"):
        rows = [row for row in results[(profile, True)] if row.success]
        for wave in CHECKPOINTS:
            entries = [row.checkpoints[wave] for row in rows if wave in row.checkpoints]
            if not entries:
                continue
            medians = [percentile([entry[index] for entry in entries], .5) for index in range(4)]
            lines.append(
                f"| {names[profile]} | {wave:,} | {medians[0]:.2f} | {medians[1]:.2f} | {medians[2]:.2f} | {medians[3]:.2f} | "
                f"{sum(medians):.2f} | {enemy_power(wave, config.hp_bonus_scale, config.midgame_relief, config.defense.use_future_power_curve):.2f} |"
            )

    lines.extend(["", "## カード精錬", "", "成功試行の`P10 / 中央値 / P90`。", "", "| 方針 | PO | 累計溶解 | 累計強化 | 消費Point | 最終ラン溶解 | 最終ラン強化 | 残Point |", "|---|---|---:|---:|---:|---:|---:|---:|"])
    for (profile, allowed), rows in results.items():
        successes = [row for row in rows if row.success]
        lines.append(
            f"| {names[profile]} | {'通常' if allowed else '除外'} | {triplet([float(r.total_cards_dissolved) for r in successes], 0)} | "
            f"{triplet([float(r.total_card_upgrades) for r in successes], 0)} | {triplet([float(r.total_card_points_spent) for r in successes], 0)} | "
            f"{triplet([float(r.final_cards_dissolved) for r in successes], 0)} | {triplet([float(r.final_card_upgrades) for r in successes], 0)} | "
            f"{triplet([float(r.final_card_points_left) for r in successes], 0)} |"
        )

    lines.extend(["", "## Legendary取得状況", ""])
    for (profile, allowed), rows in results.items():
        successes = [row for row in rows if row.success]
        rates = []
        for item in CARDS:
            if item.rarity == "L" and successes:
                rate = sum(bool(n(row.final_counts, item.key)) for row in successes) / len(successes)
                rates.append((rate, item.name))
        top = ", ".join(f"{name} {rate:.0%}" for rate, name in sorted(rates, reverse=True))
        lines.append(f"- {names[profile]}・{'通常' if allowed else 'PO除外'}: {top or '成功なし'}")

    lines.extend(["", "## Perfect Overdrive依存度", "", "| 方針 | 通常成功率 | 除外成功率 | 通常時間中央値 | 除外時間中央値 | 時間差 |", "|---|---:|---:|---:|---:|---:|"])
    for profile in ("damage", "balanced", "synergy"):
        normal = results[(profile, True)]
        excluded = results[(profile, False)]
        normal_success = [(r.total_combat_seconds + r.total_interaction_seconds) / 3600 for r in normal if r.success]
        excluded_success = [(r.total_combat_seconds + r.total_interaction_seconds) / 3600 for r in excluded if r.success]
        normal_med = percentile(normal_success, .5) if normal_success else math.nan
        excluded_med = percentile(excluded_success, .5) if excluded_success else math.nan
        gap = (excluded_med / normal_med - 1) if normal_success and excluded_success else math.nan
        lines.append(
            f"| {names[profile]} | {sum(r.success for r in normal)/len(normal):.1%} | {sum(r.success for r in excluded)/len(excluded):.1%} | "
            f"{normal_med:.2f}h | {excluded_med:.2f}h | {gap:+.1%} |"
        )

    lines.extend(["", "## 武器・遺物経済", "", "成功試行の`P10 / 中央値 / P90`。", "", "| 方針 | PO | 武器素材残量 | 遺物素材残量 | 武器生成回数 | 遺物生成回数 | 通常遺物Drop |", "|---|---|---:|---:|---:|---:|---:|"])
    for (profile, allowed), rows in results.items():
        successes = [row for row in rows if row.success]
        lines.append(
            f"| {names[profile]} | {'通常' if allowed else '除外'} | {triplet([r.weapon_material for r in successes], 1)} | "
            f"{triplet([r.relic_material for r in successes], 1)} | {triplet([float(r.weapon_generations) for r in successes], 0)} | "
            f"{triplet([float(r.relic_generations) for r in successes], 0)} | {triplet([float(r.relic_drops) for r in successes], 0)} |"
        )

    balanced_normal = [r for r in results[("balanced", True)] if r.success]
    balanced_no_po = [r for r in results[("balanced", False)] if r.success]
    normal_median = percentile([(r.total_combat_seconds + r.total_interaction_seconds) / 3600 for r in balanced_normal], .5) if balanced_normal else math.nan
    no_po_median = percentile([(r.total_combat_seconds + r.total_interaction_seconds) / 3600 for r in balanced_no_po], .5) if balanced_no_po else math.nan
    no_po_gap = no_po_median / normal_median - 1 if balanced_normal and balanced_no_po else math.inf
    lines.extend([
        "",
        "## 今回追加した現在案",
        "",
        "- 初期Crit率を0%から1%へ変更。",
        "- 初回ラン緩和の仮値としてWave25 Power 1.325を追加（旧補間値から約-0.15）。",
        "- Wave2500のLegendary確定3択に、成立済みビルド軸へ対応するLegendaryを1枠保証。",
        "- Wave500から共通Card Pointによるカード溶解・同名カード強化を追加。Cost 5/15/40、正の数値効果×1.10/1.20/1.30。",
        f"- 実プレイ時間としてカード、Reroll、装備、炉、カード強化の仮操作時間を加算。統合工房は{'導入' if config.automation_enabled else '未導入'}。",
        f"- 武器素材によるゲーム速度強化（W2,500で×1.10、W5,000で×1.20）は{'導入' if config.game_speed_enabled else '未導入'}。",
        f"- Lv75で初期Card Point+5、Lv125でさらに+10は{'導入' if config.initial_card_points_enabled else '未導入'}。",
        f"- Wave500～2500の敵Powerは最大{config.midgame_relief:.2f} Power緩和。",
        f"- 最大Wave500以降、踏破済み区間の通常敵を2体ずつ掃討する時間圧縮は{'導入' if config.sweep_enabled else '未導入'}。",
        f"- 高額DPによる基礎攻撃間隔Lvは{'導入' if config.interval_enabled else '未導入'}。",
        "- DP、Weapon Power、平均遺物Power、合計Lvマイルストーン、武器生成費は今回変更なし。",
        "",
        "## 目標判定",
        "",
        f"- 標準型実プレイ時間中央値10.5～13.5時間: {'達成' if 10.5 <= normal_median <= 13.5 else '未達'}（{normal_median:.2f}時間）",
        f"- Perfect Overdrive除外時の時間増加25%以内: {'達成' if no_po_gap <= .25 else '未達'}（{no_po_gap:+.1%}）",
        f"- 標準型通常成功率: {len(balanced_normal)/len(results[('balanced', True)]):.1%}",
        "- 強いLegendary複合による上振れはP10～P90幅として許容する。",
        "",
        "## 解釈上の注意",
        "",
        "- 時間分布は最大試行回数以内に成功した試行だけを集計する。成功率が100%未満の場合、表示中央値は条件付き中央値。",
        "- 死亡回数、初ランWave、素材残量、最終Power余剰は時間目標と独立して確認し、進行の滑らかさを判断する。",
    ])

    return "\n".join(lines) + "\n"


def main() -> None:
    global SHADOW_CARD_VALUE_LIMIT, TAKE_BRANCH_ENABLED
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=("formal", "D", "E"), default="formal")
    parser.add_argument("--trials", type=int, default=DEFAULT_TRIALS)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--dp-growth", type=float, default=DP_GROWTH)
    parser.add_argument("--weapon-scale", type=float, default=1.0)
    parser.add_argument("--relic-scale", type=float, default=1.0)
    parser.add_argument("--milestone-power-scale", type=float, default=1.0)
    parser.add_argument("--hp-bonus-scale", type=float, default=1.0)
    parser.add_argument("--midgame-relief", type=float, default=0.0)
    parser.add_argument("--max-attempts", type=int, default=140)
    parser.add_argument("--automation", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--game-speed", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--initial-card-points", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--sweep", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--reward-skip",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="D/E only: after reaching W1000, resolve up to 10%% of best Wave (cap W500) with zero combat time",
    )
    parser.add_argument("--attack-interval", action="store_true")
    parser.add_argument("--future-qol", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--future-sweep-multiplier", type=float, default=0.55)
    parser.add_argument("--memory-card", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--memory-card-unlock-wave", type=int, default=500)
    parser.add_argument("--armor-break-base", type=float, default=2.00)
    parser.add_argument("--crit-break-weight", type=float, default=0.35)
    parser.add_argument("--followup-break-weight", type=float, default=0.20)
    parser.add_argument("--average-break-time-ratio", type=float, default=0.20)
    parser.add_argument("--final-boss-full-break", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--workers", type=int, default=max(1, min(6, os.cpu_count() or 1)))
    parser.add_argument("--card-value-shadow-output", type=Path,
                        help="write Balanced v0.1 shadow-only candidate diagnostics as CSV")
    parser.add_argument("--card-value-shadow-limit", type=int, default=30,
                        help="maximum shadow candidates to evaluate per invocation")
    parser.add_argument("--take-mode", choices=("legacy", "pe"), default="legacy",
                        help="Balanced Take ranking only; Reroll/Refine/Upgrade remain legacy")
    parser.add_argument("--take-branch-output", type=Path,
                        help="write Balanced selection decisions as JSONL (requires --workers 1)")
    parser.add_argument("--phase", default="計測")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.trials <= 0:
        parser.error("--trials must be greater than zero")
    if args.card_value_shadow_output and args.workers != 1:
        parser.error("--card-value-shadow-output requires --workers 1")
    if args.take_branch_output and args.workers != 1:
        parser.error("--take-branch-output requires --workers 1")
    if args.variant != "formal" and args.take_mode == "pe":
        parser.error("--take-mode pe is limited to the formal Balanced profile")
    if args.card_value_shadow_limit < 0:
        parser.error("--card-value-shadow-limit must be nonnegative")
    SHADOW_CARD_VALUE_ROWS.clear()
    SHADOW_CARD_VALUE_LIMIT = args.card_value_shadow_limit if args.card_value_shadow_output else 0
    TAKE_BRANCH_ROWS.clear()
    TAKE_BRANCH_CONTEXT.clear()
    TAKE_BRANCH_ENABLED = bool(args.take_branch_output)
    experimental = args.variant in {"D", "E"}
    config = SimConfig(
        dp_growth=args.dp_growth,
        weapon_scale=args.weapon_scale,
        relic_scale=args.relic_scale,
        milestone_power_scale=args.milestone_power_scale,
        hp_bonus_scale=args.hp_bonus_scale,
        midgame_relief=args.midgame_relief,
        max_attempts=args.max_attempts,
        automation_enabled=args.automation,
        game_speed_enabled=args.game_speed,
        initial_card_points_enabled=args.initial_card_points,
        sweep_enabled=args.sweep,
        reward_skip_enabled=(
            experimental if args.reward_skip is None else experimental and args.reward_skip
        ),
        interval_enabled=args.attack_interval,
        defense=DefenseConfig(
            enabled=args.variant == "E",
            start_wave=500 if args.variant == "E" else 1,
            power_anchors=(
                VARIANT_E_DEFENSE_POWER_ANCHORS
                if args.variant == "E"
                else DefenseConfig().power_anchors
            ),
            use_future_power_curve=False,
            armor_break_base=args.armor_break_base,
            crit_break_weight=args.crit_break_weight,
            followup_break_weight=args.followup_break_weight,
            average_break_time_ratio=args.average_break_time_ratio,
            final_boss_requires_full_break=args.final_boss_full_break,
        ),
        future_qol_enabled=args.future_qol,
        future_sweep_multiplier=args.future_sweep_multiplier,
        memory_card_enabled=args.memory_card,
        memory_card_unlock_wave=args.memory_card_unlock_wave,
        target_wave=5000 if experimental else PRESTIGE_WAVE,
        enemy_curve_scale=1.0,
        card_upgrade_cap=1 if experimental else len(CARD_UPGRADE_COSTS),
        relic_selection_enabled=not experimental,
        exponential_core_multiplier=1.02 if experimental else 1.05,
        exponential_core_unlock_wave=2500 if experimental else 5000,
        disabled_card_keys=frozenset({"final_equation"}) if experimental else frozenset(),
        take_mode=args.take_mode,
    )
    if args.variant == "formal":
        results = simulate(args.trials, config, args.workers, args.seed)
        output_text = build_report(results, args.trials, config, args.phase, args.seed)
    else:
        if args.output is None:
            parser.error("--output is required for Variant D/E")
        rows = simulate_standard(args.trials, config, args.seed, args.workers)
        payload = build_json_result(args.variant, rows, config)
        output_text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_text, encoding="utf-8")
    if args.card_value_shadow_output:
        args.card_value_shadow_output.parent.mkdir(parents=True, exist_ok=True)
        with args.card_value_shadow_output.open("w", newline="", encoding="utf-8") as file:
            if SHADOW_CARD_VALUE_ROWS:
                fields = list(dict.fromkeys(key for row in SHADOW_CARD_VALUE_ROWS for key in row))
                writer = csv.DictWriter(file, fieldnames=fields)
                writer.writeheader()
                writer.writerows(SHADOW_CARD_VALUE_ROWS)
    if args.take_branch_output:
        args.take_branch_output.parent.mkdir(parents=True, exist_ok=True)
        with args.take_branch_output.open("w", encoding="utf-8") as file:
            for row in TAKE_BRANCH_ROWS:
                file.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    if args.variant == "formal":
        print(output_text, end="")
    else:
        terminal_payload = {
            key: value for key, value in payload.items() if key != "w2500_trials"
        }
        print(json.dumps(terminal_payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
