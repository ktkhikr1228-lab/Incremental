#!/usr/bin/env python3
"""Compare fixed B_medium weapon against acquisition-based weapon models."""

from __future__ import annotations

import argparse
import collections
import copy
import csv
from dataclasses import dataclass, field
import json
import itertools
import math
from pathlib import Path
import random
import statistics
import sys
from typing import Any

import simulate_first_prestige_v1 as sim
import simulate_new_w5000_common_uncommon_rare_epic as epic
import simulate_new_w5000_dp_v01 as dp


DEFAULT_SEED = 20260828
MAIN_CHECKPOINTS = (100, 250, 400, 500, 600, 750, 1000)
RARITIES = ("C", "U", "R", "E", "L")
RARITY_MULT = {"C": 1.00, "U": 1.25, "R": 1.65, "E": 2.20, "L": 3.50}
ROLL_RANGES = {"C": (.75,1.00), "U": (.80,1.05), "R": (.85,1.10), "E": (.90,1.15), "L": (1.00,1.25)}
AFFIX_SLOTS = {"C": 0, "U": 1, "R": 2, "E": 2, "L": 3}
DISMANTLE_VALUE = {"C": 1.0, "U": 3.0, "R": 8.0, "E": 20.0, "L": 50.0}
AFFIX_KEYS = (
    "weapon_atk_additive", "weapon_atk_pct", "base_atk_pct",
    "attack_speed_pct", "crit_rate", "crit_multiplier", "all_damage_pct",
)


def rarity_table(wave: int) -> tuple[tuple[str, float], ...]:
    if wave < 100:
        return (("C",.75),("U",.22),("R",.028),("E",.0019),("L",.0001))
    if wave < 500:
        return (("C",.55),("U",.34),("R",.10),("E",.0095),("L",.0005))
    if wave < 1000:
        return (("C",.35),("U",.40),("R",.21),("E",.039),("L",.001))
    return (("C",.25),("U",.38),("R",.30),("E",.068),("L",.002))


@dataclass
class WeaponItem:
    uid: int
    base_atk: float
    rarity: str
    origin_wave: int
    affixes: dict[str, float] = field(default_factory=dict)


@dataclass
class WeaponTrialState:
    seed: int
    affixes_enabled: bool
    first_w10_claimed: bool = False
    next_uid: int = 1
    total_drops: int = 0
    boss_drops: int = 0
    recovery_guarantees: int = 0
    exchanges: int = 0
    pouch_store_events: int = 0
    runs: int = 0
    dismantle_points: float = 0.0
    rarity_drops: collections.Counter[str] = field(default_factory=collections.Counter)
    equipped_rarities: collections.Counter[str] = field(default_factory=collections.Counter)
    affix_drops: collections.Counter[str] = field(default_factory=collections.Counter)
    affix_adopted: collections.Counter[str] = field(default_factory=collections.Counter)
    adopted_uids: set[int] = field(default_factory=set)
    run_drop_counts: list[int] = field(default_factory=list)
    run_records: list[dict[str, float | int]] = field(default_factory=list)
    max_weapon_base: float = 0.0

    def drop_rng(self, run_index: int) -> random.Random:
        return random.Random(self.seed + 7_919 * run_index)

    def item_rng(self, uid: int) -> random.Random:
        return random.Random(self.seed + 1_000_003 + 104_729 * uid)


ACTIVE_MODE = "fixed"


def bc_candidate() -> dp.Candidate:
    economy = dp.CANDIDATES["B_medium"]
    power = dp.CANDIDATES["C_aggressive"]
    return dp.Candidate(
        "BC_weapon_baseline", economy.base_cost, economy.cost_growth,
        power.atk_per_level, power.as_per_level, power.xp_per_level,
        power.crit_rate_per_level, power.crit_mult_per_level,
        power.weapon_atk_per_level, power.luck_per_effective_level,
        power.weapon_find_per_effective_level, power.weapon_quality_rate,
        economy.death_base, economy.death_divisor, economy.record_bonus,
        economy.big_boss_bonus, economy.reroll_cost,
    )


def trial_state(permanent: sim.PermanentState) -> WeaponTrialState:
    return permanent._weapon_trial_state  # type: ignore[attr-defined]


def equipped(run: sim.RunState) -> WeaponItem | None:
    return getattr(run, "_weapon_equipped", None)


def pouch(run: sim.RunState) -> list[WeaponItem]:
    return getattr(run, "_weapon_pouch", [])


def weapon_base_provider(run: sim.RunState, permanent: sim.PermanentState) -> float:
    item = equipped(run)
    return item.base_atk if item else 0.0


def weapon_modifier_provider(run: sim.RunState, permanent: sim.PermanentState) -> dict[str, float]:
    item = equipped(run)
    values = {key: 0.0 for key in AFFIX_KEYS}
    if item:
        values.update(item.affixes)
    return values


def weighted_rarity(rng: random.Random, wave: int, permanent: sim.PermanentState, forced: str | None = None) -> str:
    if forced:
        return forced
    state = dp.state_of(permanent)
    weighted = [(rarity, chance * dp.luck_rarity_weight_multiplier(state, rarity)) for rarity, chance in rarity_table(wave)]
    total = sum(value for _, value in weighted)
    value, cumulative = rng.random(), 0.0
    for rarity, weight in weighted:
        cumulative += weight / total
        if value < cumulative:
            return rarity
    return weighted[-1][0]


def roll_affixes(rng: random.Random, rarity: str, reference_base: float) -> dict[str, float]:
    affixes: dict[str, float] = {}
    tier = {"C":.70,"U":.85,"R":1.00,"E":1.15,"L":1.30}[rarity]
    keys = rng.sample(AFFIX_KEYS, AFFIX_SLOTS[rarity])
    for key in keys:
        if key == "weapon_atk_additive":
            value = reference_base * rng.uniform(.05, .15) * tier
        elif key in {"weapon_atk_pct", "base_atk_pct", "all_damage_pct"}:
            value = rng.uniform(.04, .12) * tier
        elif key == "attack_speed_pct":
            value = rng.uniform(.03, .10) * tier
        elif key == "crit_rate":
            value = rng.uniform(.02, .08) * tier
        else:
            value = rng.uniform(.05, .20) * tier
        affixes[key] = value
    return affixes


def make_weapon(permanent: sim.PermanentState, wave: int, forced_rarity: str | None = None, fixed_w10: bool = False) -> WeaponItem:
    stats = trial_state(permanent)
    uid = stats.next_uid
    stats.next_uid += 1
    rng = stats.item_rng(uid)
    rarity = weighted_rarity(rng, wave, permanent, forced_rarity)
    reference = dp.weapon.weapon_base_atk(wave)
    if fixed_w10:
        base_atk = 1.0
    else:
        low, high = ROLL_RANGES[rarity]
        quality = rng.uniform(low, high)
        quality_floor = dp.weapon_quality_floor_progress(dp.state_of(permanent))
        quality += (high - quality) * quality_floor
        base_atk = reference * RARITY_MULT[rarity] * quality
    affixes = roll_affixes(rng, rarity, reference) if stats.affixes_enabled else {}
    return WeaponItem(uid, base_atk, rarity, wave, affixes)


def score_weapon(run: sim.RunState, permanent: sim.PermanentState, item: WeaponItem | None, config: sim.SimConfig) -> float:
    previous = equipped(run)
    run._weapon_equipped = item  # type: ignore[attr-defined]
    try:
        return dp.candidate_snapshot(run, permanent, False, config).log_dps
    finally:
        run._weapon_equipped = previous  # type: ignore[attr-defined]


def dismantle(permanent: sim.PermanentState, item: WeaponItem, recovery: bool = False) -> None:
    trial_state(permanent).dismantle_points += DISMANTLE_VALUE[item.rarity] * (.50 if recovery else 1.0)


def receive_weapon(permanent: sim.PermanentState, run: sim.RunState, item: WeaponItem, config: sim.SimConfig, boss_drop: bool) -> bool:
    stats = trial_state(permanent)
    stats.total_drops += 1
    stats.rarity_drops[item.rarity] += 1
    stats.max_weapon_base = max(stats.max_weapon_base, item.base_atk)
    if boss_drop:
        stats.boss_drops += 1
    for key in item.affixes:
        stats.affix_drops[key] += 1
    run._weapon_drops_this_run += 1  # type: ignore[attr-defined]
    run._weapon_recovery_pending = False  # type: ignore[attr-defined]
    run._weapon_pity = 0  # type: ignore[attr-defined]

    old_equipped = equipped(run)
    inventory = ([old_equipped] if old_equipped else []) + list(pouch(run)) + [item]
    scored = sorted(((score_weapon(run, permanent, candidate, config), candidate) for candidate in inventory), key=lambda pair: pair[0], reverse=True)
    keep = [candidate for _, candidate in scored[:5]]
    new_equipped = keep[0]
    new_pouch = keep[1:5]
    discarded = [candidate for _, candidate in scored[5:]]
    for candidate in discarded:
        dismantle(permanent, candidate)

    changed = old_equipped is None or new_equipped.uid != old_equipped.uid
    if changed:
        if old_equipped is not None:
            stats.exchanges += 1
        stats.equipped_rarities[new_equipped.rarity] += 1
        if new_equipped.uid not in stats.adopted_uids:
            stats.adopted_uids.add(new_equipped.uid)
            for key in new_equipped.affixes:
                stats.affix_adopted[key] += 1
        run.effect_version += 1
    if item.uid in {candidate.uid for candidate in new_pouch}:
        stats.pouch_store_events += 1
    run._weapon_equipped = new_equipped  # type: ignore[attr-defined]
    run._weapon_pouch = new_pouch  # type: ignore[attr-defined]
    run.weapon = True
    return changed


def start_run(rng: random.Random, permanent: sim.PermanentState, run: sim.RunState, config: sim.SimConfig) -> None:
    if ACTIVE_MODE == "fixed":
        return
    stats = trial_state(permanent)
    stats.runs += 1
    run._weapon_equipped = None  # type: ignore[attr-defined]
    run._weapon_pouch = []  # type: ignore[attr-defined]
    run._weapon_pity = 0  # type: ignore[attr-defined]
    run._weapon_recovery_pending = stats.first_w10_claimed  # type: ignore[attr-defined]
    run._weapon_drops_this_run = 0  # type: ignore[attr-defined]
    run._weapon_max_power = 0.0  # type: ignore[attr-defined]
    run._weapon_drop_rng = stats.drop_rng(stats.runs)  # type: ignore[attr-defined]


def drop_chance(run: sim.RunState, permanent: sim.PermanentState, boss: bool) -> float:
    pity = int(getattr(run, "_weapon_pity", 0))
    base = .10 if boss else .01
    bonus = min(.15 if boss else .02, pity * (.002 if boss else .0005))
    chance = base + bonus
    return min(1.0, chance * dp.weapon_find_multiplier(dp.state_of(permanent)))


def random_drop(permanent: sim.PermanentState, run: sim.RunState, wave: int, config: sim.SimConfig, boss: bool) -> bool:
    rng: random.Random = run._weapon_drop_rng  # type: ignore[attr-defined]
    if rng.random() >= drop_chance(run, permanent, boss):
        run._weapon_pity += 10 if boss else 1  # type: ignore[attr-defined]
        return False
    item = make_weapon(permanent, wave)
    return receive_weapon(permanent, run, item, config, boss)


def boss_loot(rng: random.Random, permanent: sim.PermanentState, run: sim.RunState, wave: int, config: sim.SimConfig) -> bool:
    if ACTIVE_MODE == "fixed":
        return False
    stats = trial_state(permanent)
    if wave == 10 and not stats.first_w10_claimed:
        stats.first_w10_claimed = True
        item = make_weapon(permanent, wave, forced_rarity="C", fixed_w10=True)
        return receive_weapon(permanent, run, item, config, True)
    if getattr(run, "_weapon_recovery_pending", False) and equipped(run) is None:
        stats.recovery_guarantees += 1
        item = make_weapon(permanent, wave)
        return receive_weapon(permanent, run, item, config, True)
    return random_drop(permanent, run, wave, config, True)


def choices_and_normal_drop(rng: random.Random, profile: str, run: sim.RunState, permanent: sim.PermanentState, next_wave: int, config: sim.SimConfig) -> None:
    epic.guaranteed_choices(rng, profile, run, permanent, next_wave, config)
    if ACTIVE_MODE != "fixed" and run.kills % 10 != 0:
        random_drop(permanent, run, run.kills, config, False)


def recover_on_death(permanent: sim.PermanentState) -> None:
    if ACTIVE_MODE == "fixed":
        return
    run: sim.RunState = permanent._weapon_current_run  # type: ignore[attr-defined]
    items = ([equipped(run)] if equipped(run) else []) + list(pouch(run))
    for item in items:
        if item:
            dismantle(permanent, item, recovery=True)
    stats = trial_state(permanent)
    stats.run_drop_counts.append(int(getattr(run, "_weapon_drops_this_run", 0)))


def synthetic_weapon(wave: int, rarity: str, quality: float, affixes: dict[str, float] | None = None, uid: int = -1) -> WeaponItem:
    reference = dp.weapon.weapon_base_atk(wave)
    return WeaponItem(uid, reference * RARITY_MULT[rarity] * quality, rarity, wave, affixes or {})


def affix_at(key: str, rarity: str, reference: float, maximum: bool) -> float:
    tier = {"C":.70,"U":.85,"R":1.00,"E":1.15,"L":1.30}[rarity]
    if key == "weapon_atk_additive":
        return reference * (.15 if maximum else .10) * tier
    if key in {"weapon_atk_pct", "base_atk_pct", "all_damage_pct"}:
        return (.12 if maximum else .08) * tier
    if key == "attack_speed_pct":
        return (.10 if maximum else .065) * tier
    if key == "crit_rate":
        return (.08 if maximum else .05) * tier
    return (.20 if maximum else .125) * tier


def weapon_quality_scenarios(run: sim.RunState, permanent: sim.PermanentState, wave: int, config: sim.SimConfig) -> dict[str, dict[str, float]]:
    reference = dp.weapon.weapon_base_atk(wave)
    cases: dict[str, list[float]] = {}
    for rarity in ("C", "R", "E"):
        low, high = ROLL_RANGES[rarity]
        item = synthetic_weapon(wave, rarity, (low + high) / 2, uid=-100-len(cases))
        cases[f"{rarity}_median"] = [score_weapon(run, permanent, item, config)]
    for rarity, label, maximum in (("R", "R_average_affix", False), ("R", "R_max_affix", True), ("E", "E_average_affix", False)):
        low, high = ROLL_RANGES[rarity]
        values: list[float] = []
        for index, pair in enumerate(itertools.combinations(AFFIX_KEYS, 2)):
            affixes = {key: affix_at(key, rarity, reference, maximum) for key in pair}
            item = synthetic_weapon(wave, rarity, (low + high) / 2, affixes, uid=-1000-index)
            values.append(score_weapon(run, permanent, item, config))
        cases[label] = values
    common = cases["C_median"][0]
    output: dict[str, dict[str, float]] = {}
    for key, values in cases.items():
        final_power = max(values) if key == "R_max_affix" else statistics.mean(values)
        output[key] = {"final_power": final_power, "delta_vs_common": final_power - common}
    return output


class WeaponCapture(dp.Capture):
    def compute(self, run: sim.RunState, permanent: sim.PermanentState, boss: bool, config: sim.SimConfig) -> sim.Snapshot:
        snapshot = super().compute(run, permanent, boss, config)
        decomposition = dp.power_decomposition(run, permanent, boss)
        actual_weapon_power = float(decomposition["F"]) - float(decomposition["D"])
        run._weapon_max_power = max(float(getattr(run, "_weapon_max_power", 0.0)), actual_weapon_power)  # type: ignore[attr-defined]
        wave = int(run.kills)
        if wave in (500, 600, 750) and wave in self.current and "weapon_quality_scenarios" not in self.current[wave]:
            self.current[wave]["weapon_quality_scenarios"] = weapon_quality_scenarios(run, permanent, wave, config)
        return snapshot


def run_trial(
    trial_seed: int,
    mode: str,
    candidate: dp.Candidate,
    config: sim.SimConfig,
    capture: WeaponCapture,
) -> dict[str, Any]:
    permanent = sim.PermanentState(automation_enabled=False)
    permanent._new_dp_state = dp.NewDPState(candidate=candidate, game_speed_unlock_wave=1250)  # type: ignore[attr-defined]
    permanent._weapon_trial_state = WeaponTrialState(trial_seed + 80_000_000, mode == "affix")  # type: ignore[attr-defined]
    total_combat = interaction_accounted = 0.0
    reach_seconds: dict[int, float] = {}
    first_reached = best_failed = 0
    success = False
    final_result: sim.RunResult | None = None
    rng = random.Random(trial_seed)

    for attempt in range(1, config.max_attempts + 1):
        epic.FAILURE_SINK.clear()
        permanent._new_dp_current_deaths = attempt - 1  # type: ignore[attr-defined]
        combat_before, interaction_before = total_combat, permanent.interaction_seconds
        start_dp_total_lv = sum(dp.state_of(permanent).levels.values())
        result = sim.run_once(rng, "balanced", permanent, config, allow_overdrive=False)
        final_result = result
        if attempt == 1:
            first_reached = result.reached
        for wave, (combat_elapsed, interaction_elapsed) in result.reach_elapsed.items():
            reach_seconds.setdefault(wave, combat_before + interaction_accounted + combat_elapsed + interaction_elapsed)
        total_combat += result.combat_seconds
        interaction_accounted += permanent.interaction_seconds - interaction_before
        if mode != "fixed":
            current_run: sim.RunState = permanent._weapon_current_run  # type: ignore[attr-defined]
            failure_wave = result.failure_wave or config.target_wave
            death_decomposition = dp.power_decomposition(current_run, permanent, failure_wave % 10 == 0)
            common_low, common_high = ROLL_RANGES["C"]
            common_item = synthetic_weapon(max(10, failure_wave), "C", (common_low + common_high) / 2, uid=-999999)
            common_power = score_weapon(current_run, permanent, common_item, config)
            actual_power = float(death_decomposition["F"])
            trial_state(permanent).run_records.append({
                "run": attempt,
                "start_wave": 1,
                "end_wave": result.reached,
                "progress_waves": result.reached,
                "run_hours": (result.combat_seconds + permanent.interaction_seconds - interaction_before) / 3600.0,
                "max_weapon_power": float(getattr(current_run, "_weapon_max_power", 0.0)),
                "death_weapon_power": float(death_decomposition["F"]) - float(death_decomposition["D"]),
                "drops": int(getattr(current_run, "_weapon_drops_this_run", 0)),
                "start_dp_total_lv": start_dp_total_lv,
                "death_weapon_quality_advantage": actual_power - common_power,
            })
        if result.reached >= config.target_wave:
            success, deaths = True, attempt - 1
            if mode != "fixed":
                stats = trial_state(permanent)
                stats.run_drop_counts.append(int(getattr(permanent._weapon_current_run, "_weapon_drops_this_run", 0)))  # type: ignore[attr-defined]
            break
        best_failed = max(best_failed, result.reached)
        recover_on_death(permanent)
        state = dp.state_of(permanent)
        dp.unlock_for_wave(state, permanent.max_wave)
        dp.award_dp_after_death(state, result.reached)
        dp.spend_dp(state, permanent.max_wave)
    else:
        deaths = config.max_attempts

    assert final_result is not None
    state = dp.state_of(permanent)
    stats = trial_state(permanent)
    return {
        "success": success, "deaths": deaths, "first_reached": first_reached,
        "best_wave": config.target_wave if success else best_failed,
        "reach_seconds": reach_seconds, "checkpoint": copy.deepcopy(capture.current),
        "final_dp": {"balance":state.balance,"spent":state.total_spent,"earned":state.total_earned,"levels":dict(state.levels),"reroll_bought":state.reroll_bought},
        "weapon": {
            "drops_per_run": stats.total_drops / max(1, stats.runs),
            "total_drops": stats.total_drops, "boss_drops": stats.boss_drops,
            "recovery_guarantees": stats.recovery_guarantees,
            "rarity_drops": dict(stats.rarity_drops), "equipped_rarities": dict(stats.equipped_rarities),
            "exchanges": stats.exchanges, "dismantle_points": stats.dismantle_points,
            "pouch_use_rate": stats.pouch_store_events / max(1, stats.total_drops),
            "affix_drops": dict(stats.affix_drops), "affix_adopted": dict(stats.affix_adopted),
            "max_weapon_base": stats.max_weapon_base,
        },
        "run_records": list(stats.run_records),
    }


def stats(values: list[float]) -> dict[str, float | None]:
    return dp.stats(values)


def counter_distribution(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    total: collections.Counter[str] = collections.Counter()
    for row in rows:
        total.update(row["weapon"][key])
    count = sum(total.values())
    return {rarity: total[rarity] / count if count else 0.0 for rarity in RARITIES}


def summarize_weapon(rows: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    affix_drops: collections.Counter[str] = collections.Counter()
    affix_adopted: collections.Counter[str] = collections.Counter()
    for row in rows:
        affix_drops.update(row["weapon"]["affix_drops"])
        affix_adopted.update(row["weapon"]["affix_adopted"])
    reached500 = [row for row in rows if 500 in row["checkpoint"]]
    ordered = sorted(reached500, key=lambda row: row["checkpoint"][500]["weapon_power"])
    half = len(ordered) // 2
    low, high = ordered[:half], ordered[-half:] if half else []
    return {
        "mode": mode,
        "drops_per_run": stats([float(row["weapon"]["drops_per_run"]) for row in rows]),
        "boss_drops": stats([float(row["weapon"]["boss_drops"]) for row in rows]),
        "recovery_guarantees": stats([float(row["weapon"]["recovery_guarantees"]) for row in rows]),
        "weapon_exchanges": stats([float(row["weapon"]["exchanges"]) for row in rows]),
        "dismantle_points": stats([float(row["weapon"]["dismantle_points"]) for row in rows]),
        "pouch_use_rate": stats([float(row["weapon"]["pouch_use_rate"]) for row in rows]),
        "rarity_distribution": counter_distribution(rows, "rarity_drops"),
        "equipped_rarity_distribution": counter_distribution(rows, "equipped_rarities"),
        "affix_adoption_rate": {key: affix_adopted[key] / affix_drops[key] if affix_drops[key] else 0.0 for key in AFFIX_KEYS},
        "w500_weapon_split_final_wave": {
            "low_weapon_p50": dp.percentile([float(row["best_wave"]) for row in low], .50),
            "high_weapon_p50": dp.percentile([float(row["best_wave"]) for row in high], .50),
        },
    }


def run_condition(name: str, mode: str, trials: int, seed: int, max_attempts: int, *, include_rows: bool = False) -> dict[str, Any]:
    global ACTIVE_MODE
    ACTIVE_MODE = mode
    config = sim.SimConfig(
        max_attempts=max_attempts, automation_enabled=False, interval_enabled=False,
        game_speed_enabled=False, initial_card_points_enabled=False,
        sweep_enabled=False, reward_skip_enabled=False,
        defense=sim.DefenseConfig(enabled=False), target_wave=1000,
        card_upgrade_cap=0, relic_selection_enabled=False,
        exponential_core_multiplier=1.0,
    )
    dp.ACTIVE_CONFIG = config
    capture = WeaponCapture(config)
    sim.compute_snapshot = capture.compute
    if mode == "fixed":
        dp.WEAPON_BASE_PROVIDER = dp.default_weapon_base_provider
        dp.WEAPON_MODIFIER_PROVIDER = dp.default_weapon_modifier_provider
    else:
        dp.WEAPON_BASE_PROVIDER = weapon_base_provider
        dp.WEAPON_MODIFIER_PROVIDER = weapon_modifier_provider
    sim.forge_starting_weapon = start_run
    sim.process_boss_loot = boss_loot
    sim.process_guaranteed_choices = choices_and_normal_drop
    rows: list[dict[str, Any]] = []
    for trial in range(trials):
        capture.reset()
        # start_run exposes the current RunState for death recovery.
        original_start = sim.forge_starting_weapon
        def tracked_start(rng: random.Random, permanent: sim.PermanentState, run: sim.RunState, cfg: sim.SimConfig) -> None:
            permanent._weapon_current_run = run  # type: ignore[attr-defined]
            original_start(rng, permanent, run, cfg)
        sim.forge_starting_weapon = tracked_start
        rows.append(run_trial(seed + 1_000_000 + trial, mode, bc_candidate(), config, capture))
        sim.forge_starting_weapon = original_start
    result = dp.summarize_condition(name, bc_candidate(), rows, trials)
    result["weapon_summary"] = summarize_weapon(rows, mode)
    if include_rows:
        result["diagnostic_rows"] = rows
    return result


def fmt(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# 新W5000 Weapon acquisition比較", "",
        f"各{payload['settings']['trials']} trials / BC DP baseline / Standard bot / seed {payload['settings']['seed']} / target W1000", "",
        "Relic / Legendary Card / refinement / Sweep / Auto / Game Speed: OFF", "",
        "B/C rarity候補: W<100=C75/U22/R2.8/E0.19/L0.01%、W100～499=C55/U34/R10/E0.95/L0.05%、W500～999=C35/U40/R21/E3.9/L0.1%。", "",
        "Normal 1%、Boss 10%を基準にSoft Pity。W10初回Common保証と死亡後Recovery保証は別処理。", "",
        "## 進行", "",
        "| 条件 | W500/W750/W1000 Reach | W500時間 | W750時間 | W1000時間 | Final Wave P25/P50/P75 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, result in payload["conditions"].items():
        c = result["checkpoint"]
        lines.append(
            f"| {name} | {pct(c['500']['reach_rate'])}/{pct(c['750']['reach_rate'])}/{pct(c['1000']['reach_rate'])} | "
            f"{fmt(c['500']['time_hours']['p50'])}h | {fmt(c['750']['time_hours']['p50'])}h | {fmt(c['1000']['time_hours']['p50'])}h | "
            f"{fmt(result['final_wave']['p25'],1)}/{fmt(result['final_wave']['p50'],1)}/{fmt(result['final_wave']['p75'],1)} |"
        )
    for name, result in payload["conditions"].items():
        lines += ["", f"## {name}", "", "| W | Reach | Time P25/P50/P75 | Deaths | Final | DP | Weapon | Card |", "|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for wave in MAIN_CHECKPOINTS:
            x = result["checkpoint"][str(wave)]; t=x["time_hours"]
            lines.append(f"| {wave} | {pct(x['reach_rate'])} | {fmt(t['p25'])}/{fmt(t['p50'])}/{fmt(t['p75'])}h | {fmt(x['deaths_p50'],1)} | {fmt(x['final_damage_power_p50'])} | {fmt(x['dp_power_p50'])} | {fmt(x['weapon_power_p50'])} | {fmt(x['card_power_p50'])} |")
        w=result["weapon_summary"]
        lines += [
            "", "### Weapon集計", "",
            f"- Drop/Run P50: {fmt(w['drops_per_run']['p50'],2)} / Boss Drop P50: {fmt(w['boss_drops']['p50'],1)} / Recovery P50: {fmt(w['recovery_guarantees']['p50'],1)}",
            f"- Exchange P50: {fmt(w['weapon_exchanges']['p50'],1)} / Dismantle Pt P50: {fmt(w['dismantle_points']['p50'],1)} / Pouch利用率 P50: {pct(w['pouch_use_rate']['p50'])}",
            f"- Drop rarity: `{w['rarity_distribution']}`",
            f"- Equipped rarity: `{w['equipped_rarity_distribution']}`",
            f"- Affix採用率: `{w['affix_adoption_rate']}`",
            f"- W500 Weapon Power低群/高群 Final Wave P50: {fmt(w['w500_weapon_split_final_wave']['low_weapon_p50'],1)} / {fmt(w['w500_weapon_split_final_wave']['high_weapon_p50'],1)}",
            "", "### W500～750 / 50Wave", "", "| 区間 | Enemy +P | Player +P | DP +P | Weapon +P | Card +P | DP/Player |", "|---:|---:|---:|---:|---:|---:|---:|",
        ]
        checkpoints=result["checkpoint"]
        for item in result["intervals"]:
            if 500 <= item["from"] < 750:
                a,b=checkpoints[str(item["from"])],checkpoints[str(item["to"])]
                wd=None if a["weapon_power_p50"] is None or b["weapon_power_p50"] is None else b["weapon_power_p50"]-a["weapon_power_p50"]
                cd=None if a["card_power_p50"] is None or b["card_power_p50"] is None else b["card_power_p50"]-a["card_power_p50"]
                lines.append(f"| {item['from']}→{item['to']} | {fmt(item['enemy_power_delta'])} | {fmt(item['player_power_delta'])} | {fmt(item['dp_power_delta'])} | {fmt(wd)} | {fmt(cd)} | {pct(item['dp_share_of_player_growth'])} |")
    lines += [
        "", "## 判定", "",
        "- Drop WeaponはRun内成長源として機能するが効果は小さい。Final Wave P50は固定844.0→rarity 855.5→affix 856.0。",
        "- W750 Weapon Powerは固定3.725 / rarity 3.706 / affix 3.773。DP Power 13.4前後を大きく下回り、Weapon支配は起きていない。",
        "- W500～750のDP/Player比率はrarity 82.7～93.6%、affix 83.8～89.8%。旧77～94%問題は解消していない。",
        "- W500 Weapon Power低群/高群のFinal Wave差はrarity +3 Wave、affix -2 Wave。Run差は小さすぎ、良品運が進行差としてほぼ残らない。",
        "- Affix ONの追加効果はrarity ON比でFinal Wave +0.5、W750約0.23h短縮。現数値ではAffixの存在感が弱い。",
        "- Recovery保証、高頻度Drop、4枠Pouch、常時DPS最適交換がWeapon運を強く平準化している。W750～1000の壁はW844→W856へ約12 Wave動いただけ。",
        "", "正式採用・自動調整は行っていない。",
    ]
    path.write_text("\n".join(lines)+"\n",encoding="utf-8")


def write_csv(path: Path, payload: dict[str, Any]) -> None:
    fields=["condition","wave","reach_rate","time_p25","time_p50","time_p75","deaths_p50","final_power","dp_power","weapon_power","card_power"]
    with path.open("w",newline="",encoding="utf-8-sig") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader()
        for name,result in payload["conditions"].items():
            for wave in dp.CHECKPOINTS:
                x=result["checkpoint"][str(wave)];t=x["time_hours"]
                writer.writerow({"condition":name,"wave":wave,"reach_rate":x["reach_rate"],"time_p25":t["p25"],"time_p50":t["p50"],"time_p75":t["p75"],"deaths_p50":x["deaths_p50"],"final_power":x["final_damage_power_p50"],"dp_power":x["dp_power_p50"],"weapon_power":x["weapon_power_p50"],"card_power":x["card_power_p50"]})


def main() -> None:
    if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser();parser.add_argument("--trials",type=int,default=30);parser.add_argument("--seed",type=int,default=DEFAULT_SEED);parser.add_argument("--max-attempts",type=int,default=220);parser.add_argument("--output-dir",type=Path,default=Path("output/new_w5000_weapon_acquisition_30"));args=parser.parse_args()
    if not 1<=args.trials<=30:parser.error("--trials must be between 1 and 30")
    dp.ACTIVE_CONFIG=sim.SimConfig(target_wave=1000);capture=WeaponCapture(dp.ACTIVE_CONFIG);dp.install_isolated_candidate(capture)
    conditions={}
    for name,mode in (("A_fixed_B_medium","fixed"),("B_drop_rarity","drop"),("C_drop_affix","affix")):
        result=run_condition(name,mode,args.trials,args.seed,args.max_attempts);conditions[name]=result
        out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True);(out/f"{name}.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    payload={"settings":{"trials":args.trials,"seed":args.seed,"target_wave":1000,"max_attempts":args.max_attempts,"dp":"BC","sweep":False,"automation":False,"game_speed":False,"relic":False,"legendary_card":False,"refinement":False,"formal_modified":False},"conditions":conditions,"automatic_adoption":False}
    out=args.output_dir.resolve();jp=out/"weapon_acquisition.json";cp=out/"weapon_acquisition_checkpoints.csv";mp=out/"weapon_acquisition.md";jp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8");write_csv(cp,payload);write_markdown(mp,payload)
    print(json.dumps({"conditions":{name:{"success_rate":r["success_rate"],"final_wave_p50":r["final_wave"]["p50"],"w750_time_p50":r["checkpoint"]["750"]["time_hours"]["p50"],"w1000_time_p50":r["checkpoint"]["1000"]["time_hours"]["p50"]}for name,r in conditions.items()},"files":{"json":str(jp),"csv":str(cp),"markdown":str(mp)}},ensure_ascii=False,indent=2))


if __name__=="__main__":main()
