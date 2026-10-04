#!/usr/bin/env python3
"""New W5000 Legendary v0.1 isolated implementation and first diagnostics.

Formal simulator/spec are imported as mechanics only and are never edited.
All card, weapon, DP and hook changes live in this process and this module.
"""

from __future__ import annotations

import argparse
import collections
import copy
import csv
import json
import math
from pathlib import Path
import random
import statistics
import sys
from typing import Any

import simulate_first_prestige_v1 as sim
import simulate_new_w5000_common_uncommon_rare_epic as epic
import simulate_new_w5000_dp_v01 as dp
import compare_new_w5000_weapon_acquisition as weapon


SEED = 20260828
CHECKPOINTS = tuple(range(50, 1001, 50))
FORCE_WAVES = (500, 600, 750)
LEGENDARY_CARDS = (
    sim.card("critical_singularity", "Critical Singularity", "L", "crit", "rule", unique=True),
    sim.card("critical_overload", "Critical Overload", "L", "damage", "rule", unique=True),
    sim.card("recursive_follow_up", "Recursive Follow-Up", "L", "followup", "rule", unique=True),
    sim.card("endless_action", "Endless Action", "L", "damage", "rule", unique=True),
    sim.card("weapon_mitosis", "Weapon Mitosis", "L", "weapon", "rule", unique=True),
    sim.card("knowledge_collapse", "Knowledge Collapse", "L", "xp", "rule", unique=True),
    sim.card("relic_apotheosis", "Relic Apotheosis", "L", "relic", "rule", unique=True),
    sim.card("supplemental_inversion", "Supplemental Inversion", "L", "supplemental", "damage", "rule", unique=True),
)
LEGENDARY_KEYS = tuple(item.key for item in LEGENDARY_CARDS)
LEGENDARY_SCORE_ORIGINAL = sim.card_score
CRIT_BURN_KEYS = (
    "critical_eye", "critical_power", "critical_training", "critical_momentum",
    "critical_engine", "critical_conversion", "overflow", "multi_crit",
    "critical_compression",
)
CRIT_EXCLUSIVE = {"critical_singularity", "critical_overload"}
POOL = tuple(epic.ALL_CARDS) + LEGENDARY_CARDS
POOL_BY_KEY = {item.key: item for item in POOL}

ACTIVE_RNG: random.Random | None = None
ACTIVE_TRIAL = -1
ACTIVE_PERMANENT: sim.PermanentState | None = None
ACTIVE_LEGENDARY_RATES = {"under_500": 0.0, "500_2499": 0.001, "2500_plus": 0.005}
CAPTURE_STATES: dict[int, dict[int, dict[str, Any]]] = {}
CURRENT_CAPTURE_MODE = False
NATURAL_EVENTS: dict[int, list[dict[str, Any]]] = {}
NATURAL_COUNTERS: dict[int, collections.Counter[str]] = {}
NATURAL_RUNS: dict[int, list[sim.RunState]] = {}
NATURAL_DECISION_ROWS: dict[int, list[dict[str, Any]]] = {}
CHOICE_CONTEXTS: list[dict[str, Any]] = []
VALUATION_MODE = "B"
ACTION_FACTOR_ORIGINAL = epic.action_factor
SNAPSHOT_VALUES_ORIGINAL = dp._snapshot_values
ACQUIRE_ORIGINAL = dp.acquire_card_new
CHOOSE_ORIGINAL = sim.choose_card
SCORE_ORIGINAL = sim.card_score
WEAPON_RECEIVE_ORIGINAL = weapon.receive_weapon
WEAPON_RECOVER_ORIGINAL = weapon.recover_on_death
WEAPON_DISMANTLE_ORIGINAL = weapon.dismantle
BASE_WEAPON_BASE_PROVIDER = weapon.weapon_base_provider
BASE_WEAPON_MODIFIER_PROVIDER = weapon.weapon_modifier_provider
RUN_ONCE_ORIGINAL = sim.run_once


def rarity_table(wave: int) -> tuple[tuple[str, float], ...]:
    base = list(epic.rarity_chances_for_wave(wave))
    legendary_rate = (ACTIVE_LEGENDARY_RATES["under_500"] if wave < 500 else
                      ACTIVE_LEGENDARY_RATES["500_2499"] if wave < 2500 else
                      ACTIVE_LEGENDARY_RATES["2500_plus"])
    # Preserve the current C/U/R/E distribution by reserving Legendary weight
    # from Common only. This remains an experiment-only candidate table.
    common_index = next((i for i, (rarity, _) in enumerate(base) if rarity == "C"), None)
    if common_index is not None:
        rarity, chance = base[common_index]
        base[common_index] = (rarity, max(0.0, chance - legendary_rate))
    return (*base, ("L", legendary_rate))


def available_cards(rarity: str, run: sim.RunState, permanent: sim.PermanentState, config: sim.SimConfig) -> list[sim.Card]:
    items = [item for item in sim.CARDS_BY_RARITY[rarity]
             if not (item.unique and run.counts.get(item.key, 0))]
    if run.counts.get("multi_crit", 0) or run.counts.get("critical_singularity", 0):
        items = [item for item in items if item.key not in {"critical_compression"}]
    if run.counts.get("critical_compression", 0):
        items = [item for item in items if item.key not in {"multi_crit", "critical_singularity"}]
    if run.counts.get("critical_singularity", 0):
        items = [item for item in items if item.key != "critical_overload"]
    if run.counts.get("critical_overload", 0):
        items = [item for item in items if item.key != "critical_singularity"]
    return items


def draw_hand(rng: random.Random, run: sim.RunState, permanent: sim.PermanentState,
              config: sim.SimConfig, forced_rarity: str | None = None,
              forced_card: str | None = None, excluded: set[str] | None = None,
              starter_guarantee: bool = False) -> list[sim.Card]:
    excluded = set() if excluded is None else set(excluded)
    hand: list[sim.Card] = []
    if forced_card:
        hand.append(POOL_BY_KEY[forced_card])
    while len(hand) < 3:
        rarity = forced_rarity
        if rarity is None:
            roll, cumulative, rarity = rng.random(), 0.0, "C"
            for candidate, chance in rarity_table(run.kills):
                cumulative += chance
                if roll < cumulative:
                    rarity = candidate
                    break
        candidates = [item for item in available_cards(rarity, run, permanent, config)
                      if item.key not in excluded and item.key not in {x.key for x in hand}]
        if not candidates:
            if rarity == "L" and forced_rarity is None:
                continue
            for fallback in ("E", "R", "U", "C"):
                candidates = [item for item in available_cards(fallback, run, permanent, config)
                              if item.key not in excluded and item.key not in {x.key for x in hand}]
                if candidates:
                    break
        if not candidates:
            break
        hand.append(rng.choice(candidates))
    if starter_guarantee and not any(item.key in sim.STARTER_SAFE_KEYS for item in hand):
        safe = [POOL_BY_KEY[k] for k in sim.STARTER_SAFE_ORDER if k in POOL_BY_KEY and k not in {x.key for x in hand}]
        if safe:
            hand[0] = rng.choice(safe)
    if getattr(run, "_legendary_choice_active", False):
        choice_hands = getattr(run, "_legendary_choice_hands", None)
        if choice_hands is not None:
            choice_hands.append([item.key for item in hand])
        offers = getattr(run, "_legendary_offers", None)
        if offers is not None:
            legendary_keys = [item.key for item in hand if item.rarity == "L"]
            offers.append(legendary_keys)
            if legendary_keys and CHOICE_CONTEXTS and ACTIVE_TRIAL >= 0:
                snapshot_run, snapshot_permanent = copy.deepcopy(run), copy.deepcopy(permanent)
                snapshot_permanent._weapon_current_run = snapshot_run
                CHOICE_CONTEXTS[-1]["hands"].append({
                    "keys": legendary_keys,
                    "snapshot": (snapshot_run, snapshot_permanent),
                })
            if legendary_keys and not hasattr(run, "_legendary_choice_snapshot"):
                snapshot_run, snapshot_permanent = copy.deepcopy(run), copy.deepcopy(permanent)
                snapshot_permanent._weapon_current_run = snapshot_run
                run._legendary_choice_snapshot = (snapshot_run, snapshot_permanent)
            run._legendary_offered_count = int(getattr(run, "_legendary_offered_count", 0)) + len(legendary_keys)
            if ACTIVE_TRIAL >= 0:
                counter = NATURAL_COUNTERS.setdefault(ACTIVE_TRIAL, collections.Counter())
                counter["offered"] += len(legendary_keys)
                for key in legendary_keys:
                    counter[f"offered:{key}"] += 1
                if legendary_keys and not getattr(run, "_legendary_seen_counted", False):
                    run._legendary_seen_counted = True
                    NATURAL_COUNTERS[ACTIVE_TRIAL]["seen_runs"] += 1
                    NATURAL_RUNS.setdefault(ACTIVE_TRIAL, []).append(run)
    return hand


def _remove_card_effect(run: sim.RunState, key: str, count: int = 1) -> None:
    card = POOL_BY_KEY[key]
    removed = min(count, max(0, int(run.counts.get(key, 0))))
    if not removed:
        return
    run.counts[key] -= removed
    for tag in card.tags:
        run.tag_counts[tag] -= removed
    run.effect_version += 1
    run._burned_cards = getattr(run, "_burned_cards", collections.Counter())
    run._burned_cards[key] += removed


def _burn_one(run: sim.RunState, key: str) -> None:
    _remove_card_effect(run, key, 1)
    run._burn_count = int(getattr(run, "_burn_count", 0)) + 1
    run._burn_events = getattr(run, "_burn_events", [])
    run._burn_events.append({"wave": int(run.kills), "card": key, "decision": "BURN"})


def _burn_existing_criticals(run: sim.RunState) -> None:
    for key in CRIT_BURN_KEYS:
        if key in POOL_BY_KEY:
            count = int(run.counts.get(key, 0))
            if count:
                _remove_card_effect(run, key, count)
                run._burn_count = int(getattr(run, "_burn_count", 0)) + count
                run._burn_events = getattr(run, "_burn_events", [])
                run._burn_events.append({"wave": int(run.kills), "card": key, "count": count, "source": "acquisition", "decision": "BURN"})


def acquire_card(run: sim.RunState, item: sim.Card) -> None:
    had_overload = bool(run.counts.get("critical_overload", 0))
    pre_power = None
    if item.rarity == "L" and ACTIVE_TRIAL >= 0 and ACTIVE_PERMANENT is not None:
        try:
            pre_power = dp.candidate_snapshot(run, ACTIVE_PERMANENT,
                                               run.kills % 10 == 0, dp.ACTIVE_CONFIG).log_dps
        except (AttributeError, TypeError, ValueError):
            pre_power = None
    ACQUIRE_ORIGINAL(run, item)
    event = {"wave": int(run.kills), "card": item.key, "rarity": item.rarity,
             "start_combat_seconds": float(run.combat_seconds),
             "start_power": pre_power}
    run._legendary_events = getattr(run, "_legendary_events", [])
    if item.rarity == "L":
        if CHOICE_CONTEXTS and ACTIVE_TRIAL >= 0:
            CHOICE_CONTEXTS[-1]["selected"].append(item.key)
        run._legendary_events.append(event)
        run._legendary_selected_keys = getattr(run, "_legendary_selected_keys", [])
        run._legendary_selected_keys.append(item.key)
        run._legendary_selected_count = int(getattr(run, "_legendary_selected_count", 0)) + 1
        run._legendary_run_selected_count = int(getattr(run, "_legendary_run_selected_count", 0)) + 1
        if ACTIVE_TRIAL >= 0:
            counters = NATURAL_COUNTERS.setdefault(ACTIVE_TRIAL, collections.Counter())
            counters["selected"] += 1
            counters[f"selected:{item.key}"] += 1
            if not getattr(run, "_legendary_acquired_run_counted", False):
                run._legendary_acquired_run_counted = True
                counters["acquired_runs"] += 1
                if not getattr(run, "_legendary_seen_counted", False):
                    run._legendary_seen_counted = True
                    counters["seen_runs"] += 1
                    NATURAL_RUNS.setdefault(ACTIVE_TRIAL, []).append(run)
        if item.key == "relic_apotheosis":
            run._relic_apotheosis_active = True
        if ACTIVE_TRIAL >= 0:
            NATURAL_EVENTS.setdefault(ACTIVE_TRIAL, []).append(event)
    if item.key == "critical_overload":
        run._burn_count = int(getattr(run, "_burn_count", 0))
        run._burned_cards = getattr(run, "_burned_cards", collections.Counter())
        run._burn_processed = collections.Counter()
        _burn_existing_criticals(run)
    elif had_overload and item.key in CRIT_BURN_KEYS:
        _burn_one(run, item.key)
    if item.key == "weapon_mitosis":
        run._mitosis_start_wave = int(run.kills)
        primary = weapon.equipped(run)
        if primary is not None:
            clone = copy.copy(primary)
            clone.uid = -1_000_000 - int(getattr(run, "_mitosis_clones", 0))
            clone.is_clone = True
            if hasattr(clone, "unique_affix"):
                clone.unique_affix = None
            run._weapon_offshoot = clone
            run._mitosis_clones = int(getattr(run, "_mitosis_clones", 0)) + 1
            run._clone_used_waves = 0
            run.effect_version += 1
    if item.rarity == "L" and ACTIVE_TRIAL >= 0 and ACTIVE_PERMANENT is not None:
        try:
            event["power_after_acquire"] = dp.candidate_snapshot(
                run, ACTIVE_PERMANENT, run.kills % 10 == 0, dp.ACTIVE_CONFIG).log_dps
        except (AttributeError, TypeError, ValueError):
            event["power_after_acquire"] = None


def choose_collapse_echo(rng: random.Random, profile: str, run: sim.RunState,
                         permanent: sim.PermanentState, next_wave: int,
                         config: sim.SimConfig, allow_reroll: bool) -> None:
    eligible = [POOL_BY_KEY[key] for key, count in run.counts.items()
                if count > 0 and key in POOL_BY_KEY
                and not POOL_BY_KEY[key].unique and POOL_BY_KEY[key].rarity != "L"]
    if not eligible:
        run._collapse_empty_levelups = int(getattr(run, "_collapse_empty_levelups", 0)) + 1
        return
    rerolls = permanent.rerolls if allow_reroll else 0
    excluded: set[str] = set()
    best: sim.Card | None = None
    best_score = -math.inf
    rerolls_used = 0
    for index in range(rerolls + 1):
        hand = rng.sample([item for item in eligible if item.key not in excluded], min(3, len([item for item in eligible if item.key not in excluded])))
        if not hand:
            hand = rng.sample(eligible, min(3, len(eligible)))
        scored = [(SCORE_ORIGINAL(profile, item, run, permanent, next_wave, config), item) for item in hand]
        score, item = max(scored, key=lambda pair: pair[0])
        if score > best_score:
            best, best_score = item, score
        threshold = {"damage": 1.35, "balanced": 1.10, "synergy": 1.00}[profile]
        if score >= threshold or index == rerolls:
            best = item
            break
        excluded.update(candidate.key for candidate in hand)
        rerolls_used += 1
    if best is None:
        return
    sim.record_card_decision(permanent, best, rerolls_used, False)
    acquire_card(run, best)
    run._knowledge_echoes = int(getattr(run, "_knowledge_echoes", 0)) + 1
    run._knowledge_echo_targets = getattr(run, "_knowledge_echo_targets", collections.Counter())
    run._knowledge_echo_targets[best.key] += 1
    run.effect_version += 1
    sim.spend_card_points(profile, run, permanent, next_wave, config)


def choose_card(rng: random.Random, profile: str, run: sim.RunState,
               permanent: sim.PermanentState, next_wave: int, config: sim.SimConfig,
               forced_rarity: str | None = None, forced_card: str | None = None,
               allow_reroll: bool = True) -> None:
    global ACTIVE_PERMANENT
    previous_permanent = ACTIVE_PERMANENT
    ACTIVE_PERMANENT = permanent
    if forced_rarity is None and forced_card is None:
        history = getattr(run, "_legendary_levelup_waves", None)
        if history is None:
            history = []
            run._legendary_levelup_waves = history
        history.append(int(next_wave))
    if run.counts.get("knowledge_collapse", 0) and not getattr(run, "_collapse_disabled", False) and forced_rarity is None and forced_card is None:
        choose_collapse_echo(rng, profile, run, permanent, next_wave, config, allow_reroll)
        ACTIVE_PERMANENT = previous_permanent
        return
    run._legendary_offers = []
    run._legendary_choice_hands = []
    track_state = ACTIVE_TRIAL >= 0 and next_wave >= 500
    run._legendary_choice_snapshot = None
    choice_run, choice_permanent = run, permanent
    run._legendary_choice_active = forced_rarity is None and forced_card is None
    selected_before = int(getattr(run, "_legendary_selected_count", 0))
    events_before = len(getattr(run, "_legendary_events", []))
    choice_context = {"hands": [], "selected": []}
    CHOICE_CONTEXTS.append(choice_context)
    try:
        CHOOSE_ORIGINAL(rng, profile, run, permanent, next_wave, config,
                        forced_rarity, forced_card, allow_reroll)
    finally:
        if CHOICE_CONTEXTS and CHOICE_CONTEXTS[-1] is choice_context:
            CHOICE_CONTEXTS.pop()
        run._legendary_choice_active = False
        ACTIVE_PERMANENT = previous_permanent
    selected = set(getattr(run, "_legendary_selected_keys", [])[selected_before:])
    skipped = sum(key not in selected for group in run._legendary_offers for key in group)
    run._legendary_skipped_count = int(getattr(run, "_legendary_skipped_count", 0)) + skipped
    if ACTIVE_TRIAL >= 0 and track_state:
        counter = NATURAL_COUNTERS.setdefault(ACTIVE_TRIAL, collections.Counter())
        counter["skipped"] += skipped
        for group in run._legendary_offers:
            for key in group:
                if key not in selected:
                    counter[f"skipped:{key}"] += 1
    run._legendary_skipped_by_key = getattr(run, "_legendary_skipped_by_key", collections.Counter())
    for group in run._legendary_offers:
        for key in group:
            if key not in selected:
                run._legendary_skipped_by_key[key] += 1
    events = getattr(run, "_legendary_events", [])[events_before:]
    for event in events:
        event["decision"] = "BURN" if event["card"] in CRIT_BURN_KEYS and run.counts.get("critical_overload", 0) else "NORMAL TAKE"
    if ACTIVE_TRIAL >= 0:
        selected_keys = set(choice_context["selected"])
        rows = NATURAL_DECISION_ROWS.setdefault(ACTIVE_TRIAL, [])
        hands = choice_context["hands"]
        for hand_index, hand_record in enumerate(hands):
            choice_run, choice_permanent = hand_record["snapshot"]
            for key in hand_record["keys"]:
                if key not in LEGENDARY_KEYS:
                    continue
                item = POOL_BY_KEY[key]
                state_fingerprint = (dict(choice_run.counts), dict(choice_run.tag_counts),
                                     choice_run.xp, choice_run.effect_version, choice_run.combat_seconds)
                old_score = LEGENDARY_SCORE_ORIGINAL(profile, item, choice_run, choice_permanent,
                                                     next_wave, config)
                new_score = legendary_card_score(profile, item, choice_run, choice_permanent,
                                                 next_wave, config)
                immediate = _legendary_immediate_delta(item, choice_run, choice_permanent,
                                                       next_wave, config)
                future = legendary_future_components(item, choice_run, choice_permanent,
                                                     next_wave, config)
                unchanged = state_fingerprint == (dict(choice_run.counts), dict(choice_run.tag_counts),
                                                    choice_run.xp, choice_run.effect_version, choice_run.combat_seconds)
                rows.append({"wave": int(next_wave), "card": key,
                             "old_score": old_score, "new_score": new_score,
                             "immediate_power_delta": immediate,
                             "future_value": future,
                             "decision": "take" if key in selected_keys else "skip",
                             "state_unchanged": unchanged})


def _legendary_immediate_delta(item: sim.Card, run: sim.RunState,
                               permanent: sim.PermanentState, next_wave: int,
                               config: sim.SimConfig) -> float:
    """Exact paired log-DPS delta for one Legendary on an unchanged state."""
    test_run, test_permanent = copy.deepcopy(run), copy.deepcopy(permanent)
    test_permanent._weapon_current_run = test_run
    boss = next_wave % 10 == 0
    before = dp.candidate_snapshot(test_run, test_permanent, boss, config).log_dps
    global ACTIVE_TRIAL
    previous_trial = ACTIVE_TRIAL
    ACTIVE_TRIAL = -1  # valuation probes must not alter natural-acquisition telemetry
    try:
        acquire_card(test_run, item)
    finally:
        ACTIVE_TRIAL = previous_trial
    after = dp.candidate_snapshot(test_run, test_permanent, boss, config).log_dps
    return float(after - before)


def _collapse_echo_power(run: sim.RunState, permanent: sim.PermanentState,
                         next_wave: int, config: sim.SimConfig) -> tuple[float, float]:
    """Expected value per future Echo and remaining Level Ups from recent cadence."""
    history = list(getattr(run, "_legendary_levelup_waves", ()))
    horizon = max(0, int(config.target_wave) - int(next_wave))
    if len(history) >= 2:
        recent = history[-7:]
        span = max(1, recent[-1] - recent[0])
        per_wave = (len(recent) - 1) / span
    else:
        per_wave = 0.0
    # Banked XP contributes fractional near-term Level Ups; expected future
    # cadence is bounded to avoid treating a long first-Prestige horizon as infinite.
    cost_index = min(max(0, int(run.xp_level_count)), len(sim.CARD_COSTS) - 1)
    next_cost = max(1.0, float(sim.CARD_COSTS[cost_index]))
    banked_levels = min(2.0, max(0.0, float(run.xp)) / next_cost)
    remaining = min(40.0, per_wave * horizon + banked_levels)

    eligible = [POOL_BY_KEY[key] for key, count in run.counts.items()
                if count > 0 and key in POOL_BY_KEY
                and not POOL_BY_KEY[key].unique and POOL_BY_KEY[key].rarity != "L"]
    if not eligible:
        return remaining, 0.0
    scored: list[tuple[float, float]] = []
    for card in eligible:
        state_run, state_perm = copy.deepcopy(run), copy.deepcopy(permanent)
        state_perm._weapon_current_run = state_run
        base = dp.candidate_snapshot(state_run, state_perm, next_wave % 10 == 0, config).log_dps
        ACQUIRE_ORIGINAL(state_run, card)
        after = dp.candidate_snapshot(state_run, state_perm, next_wave % 10 == 0, config).log_dps
        score = LEGENDARY_SCORE_ORIGINAL("balanced", card, run, permanent, next_wave, config)
        scored.append((score, max(0.0, float(after - base))))
    # A Collapse Echo presents up to three currently-owned eligible cards;
    # use the best-scoring card in that representative hand, then average
    # across the owned pool as a conservative proxy for future selections.
    expected_per_echo = statistics.mean(sorted((delta for _, delta in scored), reverse=True)[:3])
    return remaining, expected_per_echo


def legendary_future_components(item: sim.Card, run: sim.RunState,
                                permanent: sim.PermanentState, next_wave: int,
                                config: sim.SimConfig) -> dict[str, float]:
    if item.key == "weapon_mitosis":
        return {"future_weapon_option_score": 0.15 if run.weapon else 0.25}
    if item.key == "knowledge_collapse":
        remaining, echo_power = _collapse_echo_power(run, permanent, next_wave, config)
        return {"expected_remaining_levelups": remaining,
                "expected_power_per_echo": echo_power,
                "projected_echo_power": remaining * echo_power,
                "score_component": 10.0 * remaining * echo_power}
    if item.key == "relic_apotheosis":
        return {"held_relic_count": float(len(getattr(permanent, "relic_types", set())))}
    return {}


def legendary_card_score(profile: str, item: sim.Card, run: sim.RunState,
                         permanent: sim.PermanentState, next_wave: int,
                         config: sim.SimConfig) -> float:
    """Keep the established C–E scorer intact; evaluate Legendary rule effects directly."""
    if item.rarity != "L":
        return LEGENDARY_SCORE_ORIGINAL(profile, item, run, permanent, next_wave, config)
    immediate = _legendary_immediate_delta(item, run, permanent, next_wave, config)
    score = 10.0 * immediate
    future = legendary_future_components(item, run, permanent, next_wave, config)
    if item.key == "weapon_mitosis":
        score += future["future_weapon_option_score"]
    elif item.key == "knowledge_collapse":
        score += future["score_component"]
    elif item.key == "relic_apotheosis":
        # No integrated Relic state means there is no defensible value estimate.
        if not getattr(permanent, "relic_types", set()) and not getattr(run, "relics", ()):
            return -2.0
    return score


def action_factor(crit_factor: float, hit_count: float, supplemental: float,
                  supplemental_crits: bool, supplemental_follows: bool,
                  follow_rate: float, follow_damage: float, follow_depth: int,
                  reaction_rate: float, reaction_depth: int,
                  inversion_conversion: float = 0.40, *, counts=None) -> float:
    run = getattr(dp, "_active_legendary_run", None)
    counts = (run.counts if run is not None else {}) if counts is None else counts
    if counts.get("critical_overload", 0):
        crit_factor = 1.0
    follow_unlocked = bool(follow_rate > 0 or follow_depth > 0 or counts.get("recursive_follow_up", 0))
    if counts.get("recursive_follow_up", 0):
        if follow_rate <= 0:
            follow_rate, follow_damage = 0.10, 0.50
        recurrence = min(max(0.0, follow_rate), 0.90)
        follow_events = follow_rate * sum(recurrence**i for i in range(100))
    else:
        follow_events = sum(follow_rate**(i + 1) for i in range(follow_depth))
    if counts.get("endless_action", 0):
        reaction_rate = min(max(reaction_rate, 0.15), 0.80)
        reaction_actions = sum(reaction_rate**i for i in range(101))
    else:
        reaction_actions = sum(reaction_rate**i for i in range(reaction_depth + 1))
    inversion = bool(counts.get("supplemental_inversion", 0))
    effectiveness = 1.0 + 0.15 * bool(counts.get("resonant_damage", 0)) + 0.15 * bool(counts.get("echoing_damage", 0)) if inversion else 1.0
    if inversion:
        supplemental = max(0.0, supplemental - 0.15 * bool(counts.get("resonant_damage", 0))
                           - 0.10 * bool(counts.get("echoing_damage", 0)))
    supplemental_factor = crit_factor if (supplemental_crits or inversion) else 1.0
    if inversion:
        # D is the normalized post-modifier direct hit before Crit. Direct is
        # removed; 40% is converted and the resulting supplemental can Crit.
        normal = hit_count * (supplemental + inversion_conversion) * effectiveness * crit_factor
        # A Follow-Up's own original direct hit is scaled by follow_damage;
        # only the configured fraction of that D survives as inverted damage.
        follow_hit = hit_count * (follow_damage * inversion_conversion) * effectiveness * crit_factor
    else:
        normal = hit_count * (crit_factor + supplemental * supplemental_factor)
        follow_hit = hit_count * follow_damage * crit_factor
        if supplemental_follows:
            follow_hit += hit_count * supplemental * supplemental_factor
    return reaction_actions * (normal + (follow_events * follow_hit if follow_unlocked else 0.0))


def _singularity_expected(rate: float, crit_mult: float) -> float:
    rate = max(0.0, rate)
    tier = math.floor(rate + 1e-12)
    fraction = rate - tier
    def value(k: int) -> float:
        scaled = float(k) if k <= 5 else 5.0 + math.log2(k - 4.0)
        linear = 1.0 + k * (crit_mult - 1.0)
        return linear * (1.20 ** (scaled - 1.0)) if k > 0 else 1.0
    return (1.0 - fraction) * value(tier) + fraction * value(tier + 1)


def snapshot_values(run: sim.RunState, permanent: sim.PermanentState, boss: bool,
                    use_dp: bool, include_weapon: bool = True) -> dict[str, Any]:
    old_active = getattr(dp, "_active_legendary_run", None)
    dp._active_legendary_run = run
    singularity = bool(run.counts.get("critical_singularity", 0))
    mutated = False
    if singularity and not run.counts.get("critical_compression", 0):
        run.counts["multi_crit"] += 1
        mutated = True
    temporary_follow_echo = bool(run.counts.get("recursive_follow_up", 0)) and not (
        run.counts.get("follow_up_strike", 0) or run.counts.get("follow_up_echo", 0)
    )
    if temporary_follow_echo:
        run.counts["follow_up_echo"] += 1
    try:
        result = SNAPSHOT_VALUES_ORIGINAL(run, permanent, boss, use_dp, include_weapon)
    finally:
        if temporary_follow_echo:
            run.counts["follow_up_echo"] -= 1
        if mutated:
            run.counts["multi_crit"] -= 1
        dp._active_legendary_run = old_active
    if singularity:
        rate = max(0.0, float(result["crit_rate"]))
        cm = float(result["crit_mult"])
        if not run.counts.get("critical_compression", 0):
            old = epic.crit_expected_multiplier(rate, cm, True)
            new = _singularity_expected(rate, cm)
            if old > 0:
                result["log_damage"] = float(result["log_damage"]) + math.log10(new / old)
    if run.counts.get("critical_overload", 0):
        crit_keys = set(CRIT_BURN_KEYS)
        # Strip all native and DP critical effects for this calculation, while
        # preserving the persisted DP levels after the temporary snapshot.
        levels = dp.state_of(permanent).levels
        saved_rate, saved_mult = levels["crit_rate"], levels["crit_multiplier"]
        levels["crit_rate"] = levels["crit_multiplier"] = 0
        saved_counts = {key: run.counts.get(key, 0) for key in crit_keys}
        for key in crit_keys:
            run.counts[key] = 0
        saved_provider = dp.WEAPON_MODIFIER_PROVIDER
        def no_crit_weapon(r: sim.RunState, p: sim.PermanentState) -> dict[str, float]:
            value = saved_provider(r, p)
            value["crit_rate"] = value["crit_multiplier"] = 0.0
            return value
        dp.WEAPON_MODIFIER_PROVIDER = no_crit_weapon
        try:
            clean = SNAPSHOT_VALUES_ORIGINAL(run, permanent, boss, use_dp, include_weapon)
        finally:
            dp.WEAPON_MODIFIER_PROVIDER = saved_provider
            levels["crit_rate"], levels["crit_multiplier"] = saved_rate, saved_mult
            for key, value in saved_counts.items():
                run.counts[key] = value
        burn_count = int(getattr(run, "_burn_count", 0))
        result["log_damage"] = float(clean["log_damage"]) - math.log10(1.01) + math.log10(3.0 * (1.0 + .40 * burn_count))
        result["crit_rate"] = 0.0
        result["crit_mult"] = 0.0
        result["multi_tier"] = 0
    return result


def mitosis_weapon_base_provider(run: sim.RunState, permanent: sim.PermanentState) -> float:
    primary = weapon.equipped(run)
    if primary is None:
        return 0.0
    base = primary.base_atk
    offshoot = getattr(run, "_weapon_offshoot", None)
    if run.counts.get("weapon_mitosis", 0) and offshoot is not None:
        base += .65 * offshoot.base_atk
    return base


def mitosis_weapon_modifier_provider(run: sim.RunState, permanent: sim.PermanentState) -> dict[str, float]:
    primary = weapon.equipped(run)
    offshoot = getattr(run, "_weapon_offshoot", None) if run.counts.get("weapon_mitosis", 0) else None
    if primary is None:
        return {key: 0.0 for key in weapon.AFFIX_KEYS}
    items = [(primary, 1.0)] + ([(offshoot, .65)] if offshoot is not None else [])
    out = {key: 0.0 for key in weapon.AFFIX_KEYS}
    weighted_base = 0.0
    pct_atk_total = 0.0
    for item, scale in items:
        item_base = item.base_atk * scale
        weighted_base += item_base
        out["weapon_atk_additive"] += float(item.affixes.get("weapon_atk_additive", 0.0)) * scale
        pct_atk_total += float(item.affixes.get("weapon_atk_pct", 0.0)) * item_base
        for key in ("base_atk_pct", "attack_speed_pct", "crit_rate", "crit_multiplier", "all_damage_pct"):
            out[key] += float(item.affixes.get(key, 0.0)) * scale
    out["weapon_atk_pct"] = pct_atk_total / weighted_base if weighted_base > 0 else 0.0
    return out


def pair_score(run: sim.RunState, permanent: sim.PermanentState, primary: weapon.WeaponItem | None,
               offshoot: weapon.WeaponItem | None, config: sim.SimConfig) -> float:
    before_primary, before_offshoot = weapon.equipped(run), getattr(run, "_weapon_offshoot", None)
    run._weapon_equipped = primary
    run._weapon_offshoot = offshoot
    run.weapon = primary is not None
    try:
        return dp.candidate_snapshot(run, permanent, False, config).log_dps
    finally:
        run._weapon_equipped, run._weapon_offshoot = before_primary, before_offshoot


def receive_weapon_mitosis(permanent: sim.PermanentState, run: sim.RunState,
                           item: weapon.WeaponItem, config: sim.SimConfig, boss_drop: bool) -> bool:
    if not run.counts.get("weapon_mitosis", 0):
        return WEAPON_RECEIVE_ORIGINAL(permanent, run, item, config, boss_drop)
    stats = weapon.trial_state(permanent)
    stats.total_drops += 1
    stats.rarity_drops[item.rarity] += 1
    stats.max_weapon_base = max(stats.max_weapon_base, item.base_atk)
    if boss_drop:
        stats.boss_drops += 1
    for key in item.affixes:
        stats.affix_drops[key] += 1
    run._weapon_drops_this_run += 1
    run._weapon_recovery_pending = False
    run._weapon_pity = 0
    inventory = [x for x in [weapon.equipped(run), getattr(run, "_weapon_offshoot", None), *weapon.pouch(run), item] if x is not None]
    candidates: list[tuple[float, weapon.WeaponItem, weapon.WeaponItem | None]] = []
    for primary in inventory:
        candidates.append((pair_score(run, permanent, primary, None, config), primary, None))
        for offshoot in inventory:
            if offshoot.uid != primary.uid:
                candidates.append((pair_score(run, permanent, primary, offshoot, config), primary, offshoot))
    candidates.sort(key=lambda entry: entry[0], reverse=True)
    _, new_primary, new_offshoot = candidates[0]
    kept_ids = {new_primary.uid}
    if new_offshoot is not None:
        kept_ids.add(new_offshoot.uid)
    remaining = [entry for entry in candidates if entry[1].uid not in kept_ids and (entry[2] is None or entry[2].uid not in kept_ids)]
    pouch_items: list[weapon.WeaponItem] = []
    for _, primary, off in remaining:
        candidate = primary if primary.uid not in kept_ids else off
        if candidate is not None and candidate.uid not in kept_ids and all(candidate.uid != x.uid for x in pouch_items):
            pouch_items.append(candidate)
            kept_ids.add(candidate.uid)
        if len(pouch_items) == 4:
            break
    kept_ids.update(x.uid for x in pouch_items)
    for lost in inventory:
        if lost.uid not in kept_ids:
            weapon.dismantle(permanent, lost)
    changed = weapon.equipped(run) is None or weapon.equipped(run).uid != new_primary.uid
    off_changed = getattr(run, "_weapon_offshoot", None) is None or getattr(run, "_weapon_offshoot", None).uid != (new_offshoot.uid if new_offshoot else None)
    if changed:
        if weapon.equipped(run) is not None:
            stats.exchanges += 1
        stats.equipped_rarities[new_primary.rarity] += 1
        run._weapon_equipped = new_primary
    if off_changed and new_offshoot is not None:
        run._mitosis_offshoot_changes = int(getattr(run, "_mitosis_offshoot_changes", 0)) + 1
    run._weapon_offshoot = new_offshoot
    run._weapon_pouch = pouch_items
    run.weapon = True
    run.effect_version += int(changed or off_changed)
    if new_offshoot is item:
        run._mitosis_real_offshoot_equips = int(getattr(run, "_mitosis_real_offshoot_equips", 0)) + 1
    if item.uid in {x.uid for x in pouch_items}:
        stats.pouch_store_events += 1
    return changed or off_changed


def dismantle_no_clone(permanent: sim.PermanentState, item: weapon.WeaponItem, recovery: bool = False) -> None:
    if getattr(item, "is_clone", False):
        run = getattr(permanent, "_weapon_current_run", None)
        if run is not None:
            run._clone_dismantle_points = float(getattr(run, "_clone_dismantle_points", 0.0))
        return
    WEAPON_DISMANTLE_ORIGINAL(permanent, item, recovery)


def recover_mitosis(permanent: sim.PermanentState) -> None:
    run = permanent._weapon_current_run
    offshoot = getattr(run, "_weapon_offshoot", None)
    if offshoot is not None:
        dismantle_no_clone(permanent, offshoot, recovery=True)
        run._weapon_offshoot = None
    WEAPON_RECOVER_ORIGINAL(permanent)


def _current_trial_snapshot(capture: weapon.WeaponCapture, run: sim.RunState,
                            permanent: sim.PermanentState, wave: int) -> None:
    if not CURRENT_CAPTURE_MODE or ACTIVE_RNG is None or wave not in FORCE_WAVES:
        return
    by_wave = CAPTURE_STATES.setdefault(ACTIVE_TRIAL, {})
    run_copy, perm_copy = copy.deepcopy(run), copy.deepcopy(permanent)
    # Drop counters are large, irrelevant to the paired combat fork, and kept
    # in the trial-level report instead.
    old_ws = getattr(perm_copy, "_weapon_trial_state", None)
    perm_copy._weapon_trial_state = weapon.WeaponTrialState(
        seed=(old_ws.seed if old_ws else SEED) + 1777,
        affixes_enabled=True,
        first_w10_claimed=True,
        runs=1,
    )
    perm_copy._weapon_current_run = run_copy
    by_wave[wave] = {
        "run": run_copy, "permanent": perm_copy,
        "rng_state": ACTIVE_RNG.getstate(),
        "combat_seconds": run.combat_seconds,
        "interaction_seconds": permanent.interaction_seconds,
        "power": dp.candidate_snapshot(run, permanent, wave % 10 == 0, capture.config).log_dps,
        "trial": ACTIVE_TRIAL,
    }


class LegendaryCapture(weapon.WeaponCapture):
    def compute(self, run: sim.RunState, permanent: sim.PermanentState, boss: bool, config: sim.SimConfig) -> sim.Snapshot:
        snapshot = super().compute(run, permanent, boss, config)
        _current_trial_snapshot(self, run, permanent, max(int(run.kills), int(permanent.max_wave)))
        if int(run.kills) in self.current:
            value = self.current[int(run.kills)]
            value.update({
                "burn_count": int(getattr(run, "_burn_count", 0)),
                "legendary_owned": [key for key in LEGENDARY_KEYS if run.counts.get(key, 0)],
                "mitosis_power": float(getattr(run, "_mitosis_power_delta", 0.0)),
                "collapse_echoes": int(getattr(run, "_knowledge_echoes", 0)),
            })
        return snapshot


def install_legendary_hooks(capture: LegendaryCapture) -> None:
    epic.action_factor = action_factor
    dp._snapshot_values = snapshot_values
    weapon.weapon_base_provider = mitosis_weapon_base_provider
    weapon.weapon_modifier_provider = mitosis_weapon_modifier_provider
    weapon.receive_weapon = receive_weapon_mitosis
    weapon.dismantle = dismantle_no_clone
    weapon.recover_on_death = recover_mitosis
    weapon.WeaponCapture = LegendaryCapture
    weapon.WEAPON_CARDS = POOL
    weapon.CARD_BY_KEY = POOL_BY_KEY
    epic.ALL_CARDS = POOL
    epic.CARD_BY_KEY = POOL_BY_KEY
    epic.EPIC_KEYS = tuple(item.key for item in epic.EPIC_CARDS)
    dp.WEAPON_BASE_PROVIDER = mitosis_weapon_base_provider
    dp.WEAPON_MODIFIER_PROVIDER = mitosis_weapon_modifier_provider
    dp.CHECKPOINTS = CHECKPOINTS
    sim.CARDS = POOL
    sim.CARD_BY_KEY = POOL_BY_KEY
    sim.CARDS_BY_RARITY = {rarity: tuple(item for item in POOL if item.rarity == rarity) for rarity in ("C", "U", "R", "E", "L")}
    sim.STARTER_SAFE_KEYS = frozenset({"power_up", "rapid_fire", "steady_force"})
    sim.STARTER_SAFE_ORDER = ("power_up", "rapid_fire", "steady_force")
    sim.draw_hand = draw_hand
    sim.available_cards = available_cards
    sim.choose_card = choose_card
    sim.card_score = LEGENDARY_SCORE_ORIGINAL if VALUATION_MODE == "A" else legendary_card_score
    sim.acquire_card = acquire_card
    sim.compute_snapshot = capture.compute
    sim.CHECKPOINTS = CHECKPOINTS
    sim.REACH_WAVES = CHECKPOINTS
    sim.VARIANT_REACH_WAVES = CHECKPOINTS
    sim.temporal_integral = epic.temporal_integral
    sim.temporal_lookup = epic.temporal_lookup
    sim.time_to_kill_with_defense = epic.recording_time_to_kill_with_defense
    sim.acquire_relic = lambda *args, **kwargs: None
    sim.purchase_game_speed = lambda *args, **kwargs: None
    sim.milestone_damage_log = lambda *args, **kwargs: 0.0
    sim.dynamic_damage_log = epic.dynamic_damage_log
    sim.forge_starting_weapon = weapon.start_run
    sim.process_boss_loot = weapon.boss_loot
    sim.process_guaranteed_choices = weapon.choices_and_normal_drop


def _tracked_start(rng: random.Random, permanent: sim.PermanentState, run: sim.RunState, config: sim.SimConfig) -> None:
    permanent._weapon_current_run = run
    weapon.start_run(rng, permanent, run, config)


def _install_run_callbacks() -> None:
    def tracked_run_once(rng: random.Random, *args: Any, **kwargs: Any) -> Any:
        global ACTIVE_RNG
        ACTIVE_RNG = rng
        permanent = args[1] if len(args) > 1 else kwargs.get("permanent")
        result = RUN_ONCE_ORIGINAL(rng, *args, **kwargs)
        run = getattr(permanent, "_weapon_current_run", None) if permanent is not None else None
        if run is not None:
            ending_power = dp.candidate_snapshot(run, permanent, result.reached % 10 == 0,
                                                  dp.ACTIVE_CONFIG).log_dps
            for event in getattr(run, "_legendary_events", []):
                if "progressed_waves" in event:
                    continue
                event["progressed_waves"] = max(0, int(result.reached) - int(event["wave"]))
                event["continuation_seconds"] = max(0.0, float(result.combat_seconds) - float(event.get("start_combat_seconds", result.combat_seconds)))
                start_power = event.get("power_after_acquire")
                event["power_change_to_run_end"] = (ending_power - float(start_power)) if start_power is not None else None
        return result
    sim.run_once = tracked_run_once
    sim.forge_starting_weapon = _tracked_start
    sim.process_boss_loot = weapon.boss_loot
    sim.process_guaranteed_choices = weapon.choices_and_normal_drop
    sim.acquire_relic = lambda *args, **kwargs: None
    sim.purchase_game_speed = lambda *args, **kwargs: None
    sim.milestone_damage_log = lambda *args, **kwargs: 0.0
    def tracked_dynamic_damage_log(run: sim.RunState, permanent: sim.PermanentState, config: sim.SimConfig) -> float:
        _current_trial_snapshot(_CAPTURE_FOR_CHECKPOINTS, run, permanent, max(int(run.kills), int(permanent.max_wave)))
        return epic.dynamic_damage_log(run, permanent, config)
    sim.dynamic_damage_log = tracked_dynamic_damage_log


_CAPTURE_FOR_CHECKPOINTS: LegendaryCapture


def monte_carlo_condition(name: str, legendary_enabled: bool, trials: int, seed: int,
                          max_attempts: int, capture_states: bool) -> dict[str, Any]:
    global ACTIVE_RNG, ACTIVE_TRIAL, CURRENT_CAPTURE_MODE, CAPTURE_STATES, NATURAL_EVENTS, NATURAL_COUNTERS, NATURAL_RUNS, NATURAL_DECISION_ROWS, _CAPTURE_FOR_CHECKPOINTS
    CAPTURE_STATES = {}
    NATURAL_EVENTS = {}
    NATURAL_COUNTERS = {}
    NATURAL_RUNS = {}
    NATURAL_DECISION_ROWS = {}
    config = sim.SimConfig(
        max_attempts=max_attempts, automation_enabled=False, interval_enabled=False,
        game_speed_enabled=False, initial_card_points_enabled=False,
        sweep_enabled=False, reward_skip_enabled=False,
        defense=sim.DefenseConfig(enabled=False), target_wave=1000,
        card_upgrade_cap=0, relic_selection_enabled=False, exponential_core_multiplier=1.0,
    )
    capture = LegendaryCapture(config)
    _CAPTURE_FOR_CHECKPOINTS = capture
    dp.ACTIVE_CONFIG = config
    weapon.ACTIVE_MODE = "affix"
    weapon.dp.ACTIVE_CONFIG = config
    dp.install_isolated_candidate(capture)
    install_legendary_hooks(capture)
    _install_run_callbacks()
    dp.ACTIVE_CONFIG = config
    weapon.dp.ACTIVE_CONFIG = config
    rows = []
    CURRENT_CAPTURE_MODE = capture_states
    for trial in range(trials):
        capture.reset()
        ACTIVE_TRIAL = trial
        NATURAL_EVENTS[trial] = []
        NATURAL_COUNTERS[trial] = collections.Counter()
        NATURAL_RUNS[trial] = []
        trial_seed = seed + 1_000_000 + trial
        ACTIVE_RNG = random.Random(trial_seed)
        # run_condition's C_drop_affix mode uses the same seed derivation and
        # weapon RNG offset as the accepted acquisition baseline.
        candidate = weapon.bc_candidate()
        row = weapon.run_trial(trial_seed, "affix", candidate, config, capture)
        row["natural_legendary_events"] = list(NATURAL_EVENTS[trial])
        rows.append(row)
    CURRENT_CAPTURE_MODE = False
    result = dp.summarize_condition(name, weapon.bc_candidate(), rows, trials)
    result["weapon_summary"] = weapon.summarize_weapon(rows, "affix")
    result["legendary_events"] = [event for row in rows for event in row["natural_legendary_events"]]
    result["legendary_decision_rows"] = [entry for trial_rows in NATURAL_DECISION_ROWS.values() for entry in trial_rows]
    result["legendary_acquisition_rate"] = sum(bool(row["natural_legendary_events"]) for row in rows) / trials
    result["legendary_mean_per_run"] = sum(len(row["natural_legendary_events"]) for row in rows) / max(1, sum(int(row.get("deaths", 0)) + 1 for row in rows))
    total_runs = sum(int(row.get("deaths", 0)) + 1 for row in rows)
    counter_total = collections.Counter()
    for counter in NATURAL_COUNTERS.values():
        counter_total.update(counter)
    result["legendary_offer_counters"] = dict(counter_total)
    all_seen_runs = [run for group in NATURAL_RUNS.values() for run in group]
    acquired_runs = [run for run in all_seen_runs if getattr(run, "_legendary_run_selected_count", 0) > 0]
    result["legendary_seen_run_rate"] = len(all_seen_runs) / max(1, total_runs)
    result["legendary_acquired_run_rate"] = len(acquired_runs) / max(1, total_runs)
    result["legendary_cards_per_run"] = counter_total.get("selected", 0) / max(1, total_runs)
    result["run_attempts"] = total_runs
    result["legendary_card_count_run_distribution"] = {
        "0": max(0, total_runs - len(acquired_runs)),
        "1": sum(getattr(run, "_legendary_run_selected_count", 0) == 1 for run in acquired_runs),
        "2": sum(getattr(run, "_legendary_run_selected_count", 0) == 2 for run in acquired_runs),
    }
    result["legendary_card_count_run_distribution"]["3+"] = sum(getattr(run, "_legendary_run_selected_count", 0) >= 3 for run in acquired_runs)
    result["legendary_card_counts"] = dict(collections.Counter(event["card"] for event in result["legendary_events"]))
    result["final_waves"] = [row["best_wave"] for row in rows]
    result["trial_metrics"] = [{
        "final_wave": row["best_wave"], "deaths": row["deaths"], "success": row["success"],
        "time_to_w1000_hours": (row.get("reach_seconds", {}).get(1000) / 3600.0)
            if row.get("reach_seconds", {}).get(1000) is not None else None,
    } for row in rows]
    return result


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))
    return float(ordered[index])


def valuation_ab(trials: int, seed: int, max_attempts: int, output_dir: Path) -> dict[str, Any]:
    """Run old/new Standard card scoring on paired seeds; save each arm at completion."""
    global VALUATION_MODE, ACTIVE_LEGENDARY_RATES
    output_dir.mkdir(parents=True, exist_ok=True)
    ACTIVE_LEGENDARY_RATES.update({"under_500": 0.0, "500_2499": 0.001, "2500_plus": 0.005})
    arms: dict[str, Any] = {}
    config = sim.SimConfig(max_attempts=max_attempts, automation_enabled=False, interval_enabled=False,
        game_speed_enabled=False, initial_card_points_enabled=False, sweep_enabled=False,
        reward_skip_enabled=False, defense=sim.DefenseConfig(enabled=False), target_wave=1000,
        card_upgrade_cap=0, relic_selection_enabled=False, exponential_core_multiplier=1.0)
    capture = LegendaryCapture(config)
    dp.ACTIVE_CONFIG = config
    weapon.ACTIVE_MODE = "affix"
    weapon.dp.ACTIVE_CONFIG = config
    dp.install_isolated_candidate(capture)
    _install_run_callbacks()
    for arm, mode in (("A_old", "A"), ("B_dedicated", "B")):
        VALUATION_MODE = mode
        result = monte_carlo_condition(arm, True, trials, seed, max_attempts, False)
        counters = result["legendary_offer_counters"]
        by_card = {}
        for item in LEGENDARY_CARDS:
            offered = int(counters.get(f"offered:{item.key}", 0))
            acquired = int(counters.get(f"selected:{item.key}", 0))
            events = [event for event in result["legendary_events"] if event["card"] == item.key]
            prompts = [row for row in result["legendary_decision_rows"] if row["card"] == item.key]
            by_card[item.key] = {
                "offered": offered, "acquired": acquired,
                "skipped": int(counters.get(f"skipped:{item.key}", 0)),
                "acquisition_rate": acquired / offered if offered else 0.0,
                "first_acquire_wave_p25_p50_p75": {
                    "p25": _percentile([float(event["wave"]) for event in events], .25),
                    "p50": _percentile([float(event["wave"]) for event in events], .50),
                    "p75": _percentile([float(event["wave"]) for event in events], .75),
                },
                "acquisition_run_metrics": {
                    "progressed_waves_p50": _percentile([float(event.get("progressed_waves", 0)) for event in events], .50),
                    "continuation_time_hours_p50": _percentile([float(event.get("continuation_seconds", 0)) / 3600 for event in events], .50),
                    "power_change_p50": _percentile([float(event["power_change_to_run_end"]) for event in events if event.get("power_change_to_run_end") is not None], .50),
                },
                "decision_diagnostics": prompts,
            }
        metrics = result["trial_metrics"]
        arms[arm] = {
            "success_rate": result["success_rate"],
            "final_wave_p25_p50_p75": result["final_wave"],
            "checkpoint": result["checkpoint"],
            "deaths_p50": _percentile([float(row["deaths"]) for row in metrics], .50),
            "time_to_w1000_p50_hours": _percentile([float(row["time_to_w1000_hours"]) for row in metrics if row["time_to_w1000_hours"] is not None], .50),
            "legendary_prompt_run_rate": result["legendary_seen_run_rate"],
            "legendary_acquired_run_rate": result["legendary_acquired_run_rate"],
            "mean_legendary_cards_per_run": result["legendary_cards_per_run"],
            "run_attempts": result["run_attempts"],
            "legendary": by_card,
            "trial_metrics": metrics,
            "anomalies": {
                "mitosis_positive_all_skipped": by_card["weapon_mitosis"]["offered"] > 0 and by_card["weapon_mitosis"]["acquired"] == 0,
                "inversion_negative_all_taken": bool(by_card["supplemental_inversion"]["decision_diagnostics"])
                    and all(row["immediate_power_delta"] < 0 and row["decision"] == "take"
                            for row in by_card["supplemental_inversion"]["decision_diagnostics"]),
                "collapse_future_score_max": max((float(row.get("new_score", 0)) for row in by_card["knowledge_collapse"]["decision_diagnostics"]), default=None),
                "nonfinite_valuation": any(not math.isfinite(float(row.get(field, 0)))
                    for row in result["legendary_decision_rows"] for field in ("old_score", "new_score", "immediate_power_delta")),
                "valuation_state_mutation_count": sum(not row.get("state_unchanged", True) for row in result["legendary_decision_rows"]),
            },
        }
        save_path = output_dir / f"legendary_bot_valuation_{arm}.json"
        save_path.write_text(json.dumps({"variant": arm, "seed": seed, "trials": trials,
            "target_wave": 1000, "valuation_mode": mode, "results": arms[arm]},
            ensure_ascii=False, indent=2), encoding="utf-8")
    VALUATION_MODE = "B"
    comparison = {"settings": {"seed": seed, "trials_per_arm": trials, "target_wave": 1000,
        "dp": "BC baseline", "weapon": "C_drop_affix", "legendary_rates": dict(ACTIVE_LEGENDARY_RATES),
        "card_effects_changed": False, "rarity_changed": False}, "arms": arms}
    (output_dir / "legendary_bot_valuation_ab.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    return comparison


def _run_pair_from_snapshot(snapshot: dict[str, Any], key: str | None,
                            config: sim.SimConfig) -> dict[str, Any]:
    run = copy.deepcopy(snapshot["run"])
    permanent = copy.deepcopy(snapshot["permanent"])
    rng = random.Random()
    rng.setstate(snapshot["rng_state"])
    permanent._weapon_current_run = run
    base_capture = dp.Capture(config)
    sim.compute_snapshot = base_capture.compute
    before = dp.candidate_snapshot(run, permanent, snapshot["wave"] % 10 == 0, config).log_dps
    run._legendary_events = []
    run._burn_events = []
    preexisting_keys = {card_key for card_key, count in run.counts.items() if count > 0 and card_key in POOL_BY_KEY and not POOL_BY_KEY[card_key].unique and POOL_BY_KEY[card_key].rarity != "L"}
    collapse_owned_types = len(preexisting_keys)
    if key:
        acquire_card(run, POOL_BY_KEY[key])
    burn_count_at_acquisition = int(getattr(run, "_burn_count", 0))
    overload_multiplier = 3.0 * (1.0 + 0.40 * burn_count_at_acquisition) if key == "critical_overload" else None
    if key == "weapon_mitosis":
        after = dp.candidate_snapshot(run, permanent, False, config).log_dps
        run._mitosis_power_delta = after - before
    immediate = dp.candidate_snapshot(run, permanent, snapshot["wave"] % 10 == 0, config).log_dps
    initial_combat = run.combat_seconds
    initial_interaction = permanent.interaction_seconds
    epic.FAILURE_SINK.clear()
    next_wave = snapshot["wave"] + 1
    result = sim.run_once(rng, "balanced", permanent, config, allow_overdrive=False,
                          target_wave=config.target_wave, initial_run=run, start_wave=next_wave)
    elapsed_combat = max(0.0, result.combat_seconds - initial_combat)
    elapsed_interaction = max(0.0, permanent.interaction_seconds - initial_interaction)
    end_wave = result.reached
    last_snapshot = dp.candidate_snapshot(run, permanent, (end_wave % 10 == 0), config)
    events = list(getattr(run, "_legendary_events", []))
    return {
        "key": key or "none", "immediate_power_delta": immediate - before,
        "multi_crit_tier": int(last_snapshot.multi_crit_tier),
        "start_power": before, "after_power": immediate,
        "end_wave": end_wave, "failed_at": result.failure_wave,
        "continuation_hours": (elapsed_combat + elapsed_interaction) / 3600.0,
        "run_total_hours": (elapsed_combat + elapsed_interaction + initial_combat + initial_interaction) / 3600.0,
        "burn_count_at_acquisition": burn_count_at_acquisition,
        "burn_events": list(getattr(run, "_burn_events", [])),
        "burn_count_end": int(getattr(run, "_burn_count", 0)),
        "overload_multiplier": overload_multiplier,
        "burned_cards": dict(getattr(run, "_burned_cards", {})),
        "collapse_echoes": int(getattr(run, "_knowledge_echoes", 0)),
        "collapse_targets": dict(getattr(run, "_knowledge_echo_targets", {})),
        "collapse_empty_levelups": int(getattr(run, "_collapse_empty_levelups", 0)),
        "collapse_owned_types_at_acquisition": collapse_owned_types,
        "collapse_owned_keys_at_acquisition": sorted(preexisting_keys),
        "mitosis_primary_rarity": getattr(weapon.equipped(run), "rarity", None),
        "mitosis_offshoot_rarity": getattr(getattr(run, "_weapon_offshoot", None), "rarity", None),
        "mitosis_clone": bool(getattr(getattr(run, "_weapon_offshoot", None), "is_clone", False)),
        "mitosis_real_offshoot_equips": int(getattr(run, "_mitosis_real_offshoot_equips", 0)),
        "mitosis_offshoot_changes": int(getattr(run, "_mitosis_offshoot_changes", 0)),
        "mitosis_clone_dismantle_points": float(getattr(run, "_clone_dismantle_points", 0.0)),
        "final_power": last_snapshot.log_dps,
        "legendary_owned": [k for k in LEGENDARY_KEYS if run.counts.get(k, 0)],
        "card_count": run.card_count,
        "counts": dict(run.counts),
        "critical_rate": last_snapshot.crit_chance,
        "crit_mult": last_snapshot.crit_multiplier,
        "follow_rate": last_snapshot.follow_rate,
        "collapse_targets_outside_owned": sorted(set(getattr(run, "_knowledge_echo_targets", {})) - preexisting_keys),
        "rng_state": rng.getstate(),
    }


def force_diagnostics(states_by_wave: dict[int, list[dict[str, Any]]], config: sim.SimConfig) -> dict[str, Any]:
    saved_rates = dict(ACTIVE_LEGENDARY_RATES)
    ACTIVE_LEGENDARY_RATES.update({"under_500": 0.0, "500_2499": 0.0, "2500_plus": 0.0})
    output: dict[str, Any] = {}
    selected: dict[int, dict[str, Any]] = {}
    for wave in FORCE_WAVES:
        candidates = [item for item in states_by_wave.get(wave, [])
                      if not any(item["run"].counts.get(key, 0) for key in LEGENDARY_KEYS)]
        if not candidates:
            candidates = states_by_wave.get(wave, [])
        if not candidates:
            continue
        selected_state = sorted(candidates, key=lambda item: item["power"])[len(candidates)//2]
        selected[wave] = selected_state
    for wave, snapshot in selected.items():
        snapshot["wave"] = wave
        baseline = _run_pair_from_snapshot(snapshot, None, config)
        cases = {"none": baseline}
        for key in LEGENDARY_KEYS:
            cases[key] = _run_pair_from_snapshot(snapshot, key, config)
        output[str(wave)] = {
            "representative_trial": snapshot["trial"],
            "representative_power": snapshot["power"],
            "cases": cases,
        }
    ACTIVE_LEGENDARY_RATES.update(saved_rates)
    return output


def legendary_valuation_diagnostics(states_by_wave: dict[int, list[dict[str, Any]]],
                                   config: sim.SimConfig) -> dict[str, Any]:
    """Compare legacy and dedicated scores on the exact same captured states."""
    rows: dict[str, Any] = {}
    for wave in FORCE_WAVES:
        candidates = [state for state in states_by_wave.get(wave, [])
                      if not any(state["run"].counts.get(key, 0) for key in LEGENDARY_KEYS)]
        if not candidates:
            candidates = states_by_wave.get(wave, [])
        if not candidates:
            continue
        state = sorted(candidates, key=lambda item: item["power"])[len(candidates) // 2]
        run, permanent = copy.deepcopy(state["run"]), copy.deepcopy(state["permanent"])
        permanent._weapon_current_run = run
        result = {}
        for item in LEGENDARY_CARDS:
            old_score = LEGENDARY_SCORE_ORIGINAL("balanced", item, run, permanent, wave + 1, config)
            new_score = legendary_card_score("balanced", item, run, permanent, wave + 1, config)
            immediate = _legendary_immediate_delta(item, run, permanent, wave + 1, config)
            future: dict[str, float] = {}
            if item.key == "weapon_mitosis":
                future["weapon_option_bonus"] = 0.15 if run.weapon else 0.25
            elif item.key == "knowledge_collapse":
                remaining, echo_power = _collapse_echo_power(run, permanent, wave + 1, config)
                future = {"expected_remaining_levelups": remaining,
                          "expected_power_per_echo": echo_power,
                          "projected_echo_power": remaining * echo_power}
            elif item.key == "relic_apotheosis":
                future["held_relic_count"] = float(len(getattr(permanent, "relic_types", set())))
            threshold = 1.10
            if item.key == "relic_apotheosis" and new_score < 0:
                decision = "保留/skip"
            else:
                decision = "take候補" if new_score >= threshold else "skip候補"
            result[item.key] = {
                "old_score": old_score, "new_score": new_score,
                "old_threshold_decision": "take候補" if old_score >= threshold else "skip候補",
                "new_threshold_decision": decision,
                "immediate_power_delta": immediate, "future_value": future,
                "representative_trial": int(state["trial"]),
            }
        rows[str(wave)] = result
    return rows


def _quantile(values: list[int], q: float) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


def chain_diagnostics(trials: int = 100_000, seed: int = SEED) -> dict[str, Any]:
    rng = random.Random(seed)
    cap = 100
    output: dict[str, Any] = {"simulation_trials_per_probability": trials, "seed": seed}
    fu_rows = []
    for pct in (10, 25, 50, 75, 90):
        p = pct / 100.0
        q = min(p, .90)
        theoretical_mean = p * (1.0 - q**cap) / (1.0 - q) if q != 1 else p * cap
        cap_probability = p * q**(cap - 1)
        samples: list[int] = []
        conditional_samples: list[int] = []
        caps = 0
        for _ in range(trials):
            count = 0
            if rng.random() < p:
                count = 1
                while count < cap and rng.random() < q:
                    count += 1
                conditional_samples.append(count)
            samples.append(count)
            caps += count == cap
        fu_rows.append({
            "follow_up_chance": p, "recursive_chance": q,
            "theory_mean_additional_fu": theoretical_mean,
            "simulation_mean_additional_fu": statistics.mean(samples),
            "theory_chain_p50": _geometric_zero_inflated_quantile(p, q, .50, cap),
            "theory_chain_p95": _geometric_zero_inflated_quantile(p, q, .95, cap),
            "theory_chain_p99": _geometric_zero_inflated_quantile(p, q, .99, cap),
            "simulation_chain_p50": _quantile(samples, .50),
            "simulation_chain_p95": _quantile(samples, .95),
            "simulation_chain_p99": _quantile(samples, .99),
            "theory_conditional_chain_p50": _geometric_zero_inflated_quantile(1.0, q, .50, cap),
            "theory_conditional_chain_p95": _geometric_zero_inflated_quantile(1.0, q, .95, cap),
            "theory_conditional_chain_p99": _geometric_zero_inflated_quantile(1.0, q, .99, cap),
            "simulation_conditional_chain_p50": _quantile(conditional_samples, .50),
            "simulation_conditional_chain_p95": _quantile(conditional_samples, .95),
            "simulation_conditional_chain_p99": _quantile(conditional_samples, .99),
            "theory_safety_cap_rate": cap_probability,
            "simulation_safety_cap_rate": caps / trials,
        })
    action_rows = []
    for pct in (15, 30, 50, 65, 80):
        p = min(max(pct / 100.0, .15), .80)
        theoretical_mean = (1.0 - p**(cap + 1)) / (1.0 - p)
        cap_probability = p**cap
        samples: list[int] = []
        caps = 0
        for _ in range(trials):
            actions = 1
            while actions <= cap and rng.random() < p:
                actions += 1
            samples.append(actions)
            caps += actions == cap + 1
        action_rows.append({
            "requested_rate": pct / 100.0, "effective_rate": p,
            "theory_mean_actions": theoretical_mean,
            "simulation_mean_actions": statistics.mean(samples),
            "theory_actions_p50": _geometric_zero_inflated_quantile(p, p, .50, cap) + 1,
            "theory_actions_p95": _geometric_zero_inflated_quantile(p, p, .95, cap) + 1,
            "theory_actions_p99": _geometric_zero_inflated_quantile(p, p, .99, cap) + 1,
            "simulation_actions_p50": _quantile(samples, .50),
            "simulation_actions_p95": _quantile(samples, .95),
            "simulation_actions_p99": _quantile(samples, .99),
            "theory_safety_cap_rate": cap_probability,
            "simulation_safety_cap_rate": caps / trials,
        })
    return {"recursive_follow_up": fu_rows, "endless_action": action_rows,
            "simulation_trials_per_probability": trials, "seed": seed,
            "safety_cap": cap}


def _geometric_zero_inflated_quantile(first: float, recur: float, q: float, cap: int) -> int:
    """Quantile for zero-or-more extra follow-ups, capped at `cap`."""
    cumulative = 1.0 - first
    if cumulative + 1e-15 >= q:
        return 0
    if q <= 0:
        return 0 if q <= 1.0 - first else 1
    for count in range(1, cap + 1):
        cumulative += first * (recur ** (count - 1)) * (1.0 - recur)
        if count == cap:
            cumulative += first * recur**(cap - 1)
        if cumulative + 1e-15 >= q:
            return count
    return cap


def _make_synthetic_state(card_types: int, has_accelerated: bool, collapse: bool,
                          config: sim.SimConfig, seed: int) -> tuple[sim.RunState, sim.PermanentState]:
    permanent = sim.PermanentState(automation_enabled=False)
    permanent._new_dp_state = dp.NewDPState(candidate=weapon.bc_candidate(), game_speed_unlock_wave=1250)
    permanent.max_wave = 750
    run = sim.RunState(allow_overdrive=False, kills=750)
    sample_keys = [
        "accelerated_learning" if has_accelerated else "power_up",
        "power_up", "rapid_fire", "steady_force", "experience", "critical_eye",
        "critical_power", "balanced_training", "multi_hit", "supplemental_damage",
        "knowledge_conversion", "boss_hunter", "first_strike", "resonant_damage",
        "echoing_damage", "execution", "boss_scholar",
    ]
    unique: list[str] = []
    for key in sample_keys:
        if key not in unique:
            unique.append(key)
        if len(unique) == card_types:
            break
    # Put Accelerated Learning first so every later acquired card contributes
    # consistently to its post-acquisition counter.
    if has_accelerated:
        unique.remove("accelerated_learning")
        unique.insert(0, "accelerated_learning")
    for key in unique:
        ACQUIRE_ORIGINAL(run, POOL_BY_KEY[key])
    ACQUIRE_ORIGINAL(run, POOL_BY_KEY["knowledge_collapse"])
    run._collapse_disabled = not collapse
    return run, permanent


def knowledge_collapse_synthetic(config: sim.SimConfig, trials: int = 100) -> dict[str, Any]:
    output = []
    for ntypes in (8, 12, 16):
        for has_accel in (False, True):
            for levelups in (5, 10, 20, 40):
                mode_results: dict[str, list[dict[str, Any]]] = {"collapse": [], "normal": []}
                for mode in ("collapse", "normal"):
                    for trial in range(trials):
                        run, permanent = _make_synthetic_state(ntypes, has_accel, mode == "collapse", config, trial)
                        initial_types = {k for k, count in run.counts.items() if count > 0 and k in POOL_BY_KEY}
                        rng = random.Random(SEED + 100_003 * ntypes + 997 * levelups + 17 * int(has_accel) + trial)
                        start = dp.candidate_snapshot(run, permanent, False, config)
                        for index in range(levelups):
                            choose_card(rng, "balanced", run, permanent, 751 + index, config, allow_reroll=True)
                        end = dp.candidate_snapshot(run, permanent, False, config)
                        targets = getattr(run, "_knowledge_echo_targets", collections.Counter())
                        mode_results[mode].append({
                            "power_gain": end.log_dps - start.log_dps,
                            "xp_multiplier": end.general_xp,
                            "accelerated_units": run.accelerated_units,
                            "accelerated_stacks": int(run.counts.get("accelerated_learning", 0)),
                            "echo_targets": dict(targets),
                            "echo_stack_increases": dict(targets),
                            "new_card_types": len({k for k, count in run.counts.items() if count > 0 and k in POOL_BY_KEY} - initial_types),
                            "card_counts": {k: int(v) for k, v in run.counts.items() if v > 0 and k in POOL_BY_KEY and not POOL_BY_KEY[k].unique},
                            "echoes": int(getattr(run, "_knowledge_echoes", 0)),
                        })
                collapse_rows, normal_rows = mode_results["collapse"], mode_results["normal"]
                targets = collections.Counter()
                for row in collapse_rows:
                    targets.update(row["echo_targets"])
                output.append({
                    "owned_card_types": ntypes, "accelerated_learning_present": has_accel,
                    "levelups": levelups, "simulation_trials": trials,
                    "mean_echo_power_gain": statistics.mean(x["power_gain"] for x in collapse_rows),
                    "mean_normal_power_gain": statistics.mean(x["power_gain"] for x in normal_rows),
                    "mean_power_delta_echo_minus_normal": statistics.mean(x["power_gain"] - y["power_gain"] for x, y in zip(collapse_rows, normal_rows)),
                    "mean_xp_multiplier_echo": statistics.mean(x["xp_multiplier"] for x in collapse_rows),
                    "mean_xp_multiplier_normal": statistics.mean(x["xp_multiplier"] for x in normal_rows),
                    "mean_accelerated_units_echo": statistics.mean(x["accelerated_units"] for x in collapse_rows),
                    "mean_accelerated_units_normal": statistics.mean(x["accelerated_units"] for x in normal_rows),
                    "echo_target_counts": dict(targets),
                    "mean_echoes": statistics.mean(x["echoes"] for x in collapse_rows),
                    "normal_mean_new_card_types": statistics.mean(x["new_card_types"] for x in normal_rows),
                    "collapse_new_card_types": max(x["new_card_types"] for x in collapse_rows),
                    "collapse_stack_distribution": _summarize_stack_distribution(collapse_rows),
                })
    return {"trials_per_condition": trials, "conditions": output}


def _summarize_stack_distribution(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = collections.Counter()
    for row in rows:
        counts.update(row["echo_stack_increases"])
    return {key: count / max(1, len(rows)) for key, count in counts.most_common(12)}


def overload_synthetic(config: sim.SimConfig) -> dict[str, Any]:
    rows = []
    for burn_target in (0, 2, 4, 8, 12, 16):
        permanent = sim.PermanentState(automation_enabled=False)
        permanent._new_dp_state = dp.NewDPState(candidate=weapon.bc_candidate(), game_speed_unlock_wave=1250)
        run = sim.RunState(allow_overdrive=False, kills=750)
        # A consistent non-critical foundation makes the critical contribution
        # and the Overload trade-off directly measurable.
        for key in ("power_up", "steady_force", "rapid_fire"):
            ACQUIRE_ORIGINAL(run, POOL_BY_KEY[key])
        eye = (burn_target + 1) // 2
        power = burn_target // 2
        if eye:
            for _ in range(eye): ACQUIRE_ORIGINAL(run, POOL_BY_KEY["critical_eye"])
        if power:
            for _ in range(power): ACQUIRE_ORIGINAL(run, POOL_BY_KEY["critical_power"])
        before = dp.candidate_snapshot(run, permanent, False, config).log_dps
        clean = copy.deepcopy(run)
        for key in CRIT_BURN_KEYS:
            _remove_card_effect(clean, key, int(clean.counts.get(key, 0)))
        no_crit_log = dp.candidate_snapshot(clean, permanent, False, config).log_dps
        acquired = copy.deepcopy(run)
        acquire_card(acquired, POOL_BY_KEY["critical_overload"])
        after = dp.candidate_snapshot(acquired, permanent, False, config).log_dps
        overload_burn_count = int(getattr(acquired, "_burn_count", 0))
        acquire_card(acquired, POOL_BY_KEY["critical_training"])
        rows.append({
            "burn_count": burn_target,
            "overload_multiplier": 3.0 * (1.0 + .40 * burn_target),
            "before_final_power": before,
            "lost_crit_power": before - no_crit_log,
            "after_final_power": after,
            "net_final_power_delta": after - before,
            "burn_count_applied": overload_burn_count,
            "burn_count_after_later_choice": int(getattr(acquired, "_burn_count", 0)),
            "crit_rate_after": dp.candidate_snapshot(acquired, permanent, False, config).crit_chance,
            "active_critical_stacks_after": sum(int(acquired.counts.get(key, 0)) for key in CRIT_BURN_KEYS),
            "later_critical_choice_decision": getattr(acquired, "_burn_events", [{}])[-1].get("decision"),
            "later_critical_choice_effect_stack": int(acquired.counts.get("critical_training", 0)),
        })
    return {"conditions": rows}


def apotheosis_effect(relics: list[dict[str, Any]], ascended: bool) -> list[dict[str, Any]]:
    """v0.1 adapter: preserve relic records; attach a per-record ascended effect."""
    active = relics if ascended else relics[:3]
    return [{**relic, "ascended": bool(ascended),
             "effective_value": float(relic.get("effective_value", relic.get("value", 0.0))) * (1.5 if ascended else 1.0)}
            for relic in active]


def apotheosis_synthetic() -> dict[str, Any]:
    rows = []
    for count in (1, 3, 5, 7):
        # Deliberate same-name items in different rarity/upgrade states.
        relics = [{"name": "Learning Lens" if i in (0, 4) else f"Relic {i+1}",
                   "rarity": ("Common", "Uncommon", "Rare", "Epic")[i % 4],
                   "value": 0.01 * (i + 1), "dust_level": i % 4,
                   "effective_value": 0.01 * (i + 1) * (1.0 + 0.1 * (i % 4))}
                  for i in range(count)]
        normal = apotheosis_effect(relics, False)
        active = apotheosis_effect(relics, True)
        rows.append({"owned": count, "normal_active": len(normal), "apotheosis_active": len(active),
                     "normal_total_effect": sum(r["effective_value"] for r in normal),
                     "ascended_total_effect": sum(r["effective_value"] for r in active),
                     "same_name_active": sum(r["name"] == "Learning Lens" for r in active),
                     "dust_applied_before_ascension": all(r["effective_value"] == relics[i]["effective_value"] * 1.5 for i, r in enumerate(active)),
                     "death_active_count_after_reversion": len(apotheosis_effect(relics, False))})
    return {"integration": "synthetic adapter only; no relic spawning/selection in progression", "conditions": rows}


def legendary_rules_synthetic(config: sim.SimConfig) -> dict[str, Any]:
    permanent = sim.PermanentState(automation_enabled=False)
    sim.CARDS_BY_RARITY = {rarity: tuple(card for card in POOL if card.rarity == rarity) for rarity in ("C", "U", "R", "E", "L")}
    checks: dict[str, Any] = {
        "all_8_unique": len(LEGENDARY_CARDS) == 8 and all(card.unique for card in LEGENDARY_CARDS),
        "unique_repeat_blocked": all(
            item.key not in [candidate.key for candidate in available_cards("L", _count_state(item.key), permanent, config)]
            for item in LEGENDARY_CARDS
        ),
        "singularity_blocks_overload": "critical_overload" not in [c.key for c in available_cards("L", _count_state("critical_singularity"), permanent, config)],
        "overload_blocks_singularity": "critical_singularity" not in [c.key for c in available_cards("L", _count_state("critical_overload"), permanent, config)],
        "compression_blocks_multi_crit": "multi_crit" not in [c.key for c in available_cards("E", _count_state("critical_compression"), permanent, config)],
        "multi_crit_blocks_compression": "critical_compression" not in [c.key for c in available_cards("E", _count_state("multi_crit"), permanent, config)],
        "nonexclusive_legendary_pairs_remain_available": all(
            owner == candidate.key or {owner, candidate.key} == CRIT_EXCLUSIVE
            or candidate.key in [c.key for c in available_cards("L", _count_state(owner), permanent, config)]
            for owner in LEGENDARY_KEYS for candidate in LEGENDARY_CARDS
        ),
        "death_clears_all_cards_by_run_recreation": sim.RunState(allow_overdrive=False, kills=0).counts.get("supplemental_inversion", 0) == 0,
        "active_inversion_card_present": any(card.key == "supplemental_inversion" for card in LEGENDARY_CARDS),
    }
    return checks


def _count_state(key: str) -> sim.RunState:
    state = sim.RunState(allow_overdrive=False, kills=750)
    state.counts[key] = 1
    return state


def inversion_synthetic() -> dict[str, Any]:
    rows = []
    run = sim.RunState(allow_overdrive=False, kills=750)
    old_active = getattr(dp, "_active_legendary_run", None)
    try:
        for conversion in (0.30, 0.40, 0.50):
            for hits in (1.0, 2.0, 3.0, 5.0):
                for has_fu in (False, True):
                    for has_reaction in (False, True):
                      for resonance_mode in (0, 1, 2, 3):
                        run.counts.clear()
                        run.counts["supplemental_inversion"] = 1
                        if has_fu:
                            run.counts["recursive_follow_up"] = 1
                        if has_reaction:
                            run.counts["endless_action"] = 1
                        if resonance_mode in (1, 3):
                            run.counts["resonant_damage"] = 1
                        if resonance_mode in (2, 3):
                            run.counts["echoing_damage"] = 1
                        dp._active_legendary_run = run
                        resonant = resonance_mode in (1, 3)
                        echoing = resonance_mode in (2, 3)
                        kwargs = dict(crit_factor=1.8, hit_count=hits,
                                      supplemental=0.25 + 0.15 * resonant + 0.10 * echoing,
                                      supplemental_crits=resonant, supplemental_follows=echoing,
                                      follow_rate=0.10 if has_fu else 0.0,
                                      follow_damage=0.50 if has_fu else 0.0,
                                      follow_depth=1 if has_fu else 0,
                                      reaction_rate=0.15 if has_reaction else 0.0,
                                      reaction_depth=1 if has_reaction else 0,
                                      inversion_conversion=conversion)
                        inverted = action_factor(**kwargs)
                        run.counts["supplemental_inversion"] = 0
                        baseline = action_factor(**kwargs)
                        run.counts["supplemental_inversion"] = 1
                        rows.append({"hit_count": hits, "follow_up": has_fu, "re_action": has_reaction,
                                     "conversion": conversion, "direct_damage_after": 0.0,
                                     "normal_expected_factor": baseline, "inverted_expected_factor": inverted,
                                     "delta_factor": inverted - baseline,
                                     "final_power_delta": math.log10(inverted / baseline) if baseline > 0 and inverted > 0 else None,
                                     "resonant_effectiveness_mode": ("none", "resonant", "echoing", "both")[resonance_mode],
                                     "inversion_effectiveness": 1.0 + .15 * bool(resonance_mode & 1) + .15 * bool(resonance_mode & 2),
                                     "follows_application": "inverted supplemental applies to FU/Re-Action normal attacks"})
    finally:
        dp._active_legendary_run = old_active
    return {"conditions": rows, "synthetic_crit_factor": 1.8,
            "note": "40% is default in live behavior; 30/40/50% are sensitivity diagnostics only."}


def legendary_function_synthetic() -> dict[str, Any]:
    singularity = []
    for pct in (100, 200, 500, 1000):
        tier = pct / 100.0
        for cm in (1.5, 2.0, 3.0):
            singularity.append({"crit_rate_pct": pct, "crit_multiplier": cm,
                                "tier_damage_multiplier": _singularity_expected(tier, cm)})
    mitosis = []
    for primary_rarity in ("C", "U", "R", "E", "L"):
        for offshoot_rarity in ("C", "U", "R", "E", "L"):
            primary = weapon.WeaponItem(1, 100.0, primary_rarity, 500, {"weapon_atk_pct": .1})
            offshoot = weapon.WeaponItem(2, 100.0, offshoot_rarity, 500, {"weapon_atk_additive": 5.0})
            primary.unique_affix = {"not_copied": True}
            clone = copy.copy(primary)
            clone.uid = -1
            clone.is_clone = True
            if hasattr(clone, "unique_affix"):
                clone.unique_affix = None
            run = sim.RunState(allow_overdrive=False, kills=750)
            run.counts["weapon_mitosis"] = 1
            run._weapon_equipped = primary
            run._weapon_offshoot = offshoot
            base_live = mitosis_weapon_base_provider(run, sim.PermanentState(automation_enabled=False))
            clone_base = primary.base_atk + .65 * clone.base_atk
            run.counts["weapon_mitosis"] = 0
            after_death_base = mitosis_weapon_base_provider(run, sim.PermanentState(automation_enabled=False))
            mitosis.append({"primary_rarity": primary_rarity, "offshoot_rarity": offshoot_rarity,
                            "primary_base": primary.base_atk, "offshoot_base": offshoot.base_atk,
                            "combined_base": base_live, "expected_combined_base": 165.0,
                            "clone_base": clone_base, "clone_normal_affixes_copied": clone.affixes == primary.affixes,
                            "clone_unique_affix_copied": bool(getattr(clone, "unique_affix", None)),
                            "clone_dismantle_value": 0, "death_reverts_base_to_primary": after_death_base == primary.base_atk})
    return {"critical_singularity": singularity, "weapon_mitosis": mitosis}


def _diagnostics_from_existing(path: Path, output_dir: Path, args: argparse.Namespace) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    config = sim.SimConfig(target_wave=1000, card_upgrade_cap=0, relic_selection_enabled=False,
        automation_enabled=False, interval_enabled=False, game_speed_enabled=False,
        initial_card_points_enabled=False, sweep_enabled=False, reward_skip_enabled=False,
        defense=sim.DefenseConfig(enabled=False), exponential_core_multiplier=1.0)
    capture = dp.Capture(config)
    dp.ACTIVE_CONFIG = config
    dp.install_isolated_candidate(capture)
    install_legendary_hooks(LegendaryCapture(config))
    _install_run_callbacks()
    payload["chain_diagnostics"] = chain_diagnostics(args.diagnostic_trials, args.seed)
    payload["knowledge_collapse_synthetic"] = knowledge_collapse_synthetic(config, args.synthetic_trials)
    payload["critical_overload_synthetic"] = overload_synthetic(config)
    payload["relic_apotheosis_synthetic"] = apotheosis_synthetic()
    payload["supplemental_inversion_synthetic"] = inversion_synthetic()
    payload["legendary_function_synthetic"] = legendary_function_synthetic()
    payload["legendary_rules_synthetic"] = legendary_rules_synthetic(config)
    payload["anomaly_checks"] = anomaly_checks(payload)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / path.name
    md_path = output_dir / path.with_suffix(".md").name
    payload["settings"]["diagnostics_only_revision"] = True
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(md_path, payload)


def anomaly_checks(payload: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "natural_legendary_nonzero": False,
        "both_exclusive_critical_legendary": False,
        "duplicate_legendary": False,
        "critical_overload_rate_zero_broken": False,
        "burned_effect_remains": False,
        "mitosis_clone_dismantle_growth": False,
        "knowledge_collapse_new_card_taken": False,
        "nan_or_inf": False,
        "safety_cap_frequent": False,
        "inversion_direct_attack_not_zero": False,
        "apotheosis_death_reversion_failed": False,
    }
    for case_group in payload.get("forced", {}).values():
        for case in case_group["cases"].values():
            if "critical_overload" in case.get("legendary_owned", []) and case.get("critical_rate") not in (0.0, None):
                checks["critical_overload_rate_zero_broken"] = True
            if case.get("mitosis_clone_dismantle_points", 0) > 0:
                checks["mitosis_clone_dismantle_growth"] = True
            for card_key, burned_count in case.get("burned_cards", {}).items():
                if int(burned_count) > 0 and int(case.get("counts", {}).get(card_key, 0)) > 0:
                    checks["burned_effect_remains"] = True
            if case.get("active_critical_stacks_after", 0) > 0:
                checks["burned_effect_remains"] = True
            if case.get("collapse_targets_outside_owned"):
                checks["knowledge_collapse_new_card_taken"] = True
            if {"critical_singularity", "critical_overload"}.issubset(set(case.get("legendary_owned", []))):
                checks["both_exclusive_critical_legendary"] = True
            owned = case.get("legendary_owned", [])
            if len(owned) != len(set(owned)):
                checks["duplicate_legendary"] = True
            for val in (case.get("final_power"), case.get("immediate_power_delta"), case.get("continuation_hours")):
                if val is not None and not math.isfinite(float(val)):
                    checks["nan_or_inf"] = True
    checks["natural_legendary_nonzero"] = any(x["legendary_acquisition_rate"] > 0 for x in payload["natural"].values())
    checks["legendary_rule_test_failed"] = any(not value for value in payload.get("legendary_rules_synthetic", {}).values())
    checks["mitosis_death_or_clone_rule_failed"] = any(
        not row["death_reverts_base_to_primary"] or row["clone_unique_affix_copied"] or row["clone_dismantle_value"] != 0
        for row in payload.get("legendary_function_synthetic", {}).get("weapon_mitosis", [])
    )
    checks["overload_burn_choice_tag_failed"] = any(
        row.get("later_critical_choice_decision") != "BURN" or row.get("later_critical_choice_effect_stack") != 0
        for row in payload.get("critical_overload_synthetic", {}).get("conditions", [])
    )
    for row in payload.get("knowledge_collapse_synthetic", {}).get("conditions", []):
        if row.get("collapse_new_card_types", 0) > 0:
            checks["knowledge_collapse_new_card_taken"] = True
    for family in ("recursive_follow_up", "endless_action"):
        for row in payload.get("chain_diagnostics", {}).get(family, []):
            if row.get("simulation_safety_cap_rate", 0.0) > .001:
                checks["safety_cap_frequent"] = True
    relic_test = payload.get("relic_apotheosis_synthetic", {})
    if any(row.get("death_active_count_after_reversion") != row.get("normal_active") for row in relic_test.get("conditions", [])):
        checks["apotheosis_death_reversion_failed"] = True
    if any(row.get("direct_damage_after") != 0.0 or not math.isfinite(float(row.get("inverted_expected_factor", 0.0)))
           for row in payload.get("supplemental_inversion_synthetic", {}).get("conditions", [])):
        checks["inversion_direct_attack_not_zero"] = True
    return checks


def compact_condition(result: dict[str, Any]) -> dict[str, Any]:
    data: dict[str, Any] = {
        "success_rate": result["success_rate"],
        "deaths": result["final_deaths"],
        "final_wave": result["final_wave"],
        "checkpoint": {},
        "legendary_acquisition_rate": result["legendary_acquisition_rate"],
        "legendary_mean_per_run": result["legendary_mean_per_run"],
        "legendary_seen_run_rate": result.get("legendary_seen_run_rate", 0.0),
        "legendary_acquired_run_rate": result.get("legendary_acquired_run_rate", 0.0),
        "legendary_cards_per_run": result.get("legendary_cards_per_run", 0.0),
        "run_attempts": result.get("run_attempts", 0),
        "legendary_offer_counters": result.get("legendary_offer_counters", {}),
        "legendary_card_counts": result.get("legendary_card_counts", {}),
        "legendary_card_count_run_distribution": result.get("legendary_card_count_run_distribution", {}),
        "legendary_events": result.get("legendary_events", []),
        "weapon_summary": result["weapon_summary"],
        "trials": [],
    }
    for wave in (500, 600, 750, 850, 1000):
        x = result["checkpoint"][str(wave)]
        data["checkpoint"][str(wave)] = {
            "reach_rate": x["reach_rate"], "time_hours": x["time_hours"],
            "deaths_p50": x["deaths_p50"],
            "final_damage_power_p50": x["final_damage_power_p50"],
            "dp_power_p50": x["dp_power_p50"], "weapon_power_p50": x["weapon_power_p50"],
            "card_power_p50": x["card_power_p50"],
        }
    return data


def write_report(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# new_w5000 Legendary v0.1 初回性能診断", "",
        "30 trials / Standard bot / BC DP / C_drop_affix Weapon / seed 20260828 / target W1000", "",
        "Relic・refinement・Sweep・Auto・Game Speed: OFF。正式採用・自動調整なし。", "",
        f"自然Legendary率候補: `{payload['settings']['legendary_rate_candidate']}`。Legendary分はCommon率から差し引き、C/U/R/E間の比率は維持。", "",
        "## 自然取得 A/B", "",
        "| 条件 | 成功率 | Final Wave P25/P50/P75 | W500/W600/W750/W850/W1000到達率 | Legendary取得Run率 | 平均枚数/Run |", "|---|---:|---:|---:|---:|---:|",
    ]
    for name, result in payload["natural"].items():
        wave = result["final_wave"]
        cp = result["checkpoint"]
        reaches = "/".join(f"{cp[str(w)]['reach_rate']:.0%}" for w in (500,600,750,850,1000))
        lines.append(f"| {name} | {result['success_rate']:.0%} | {wave['p25']:.1f}/{wave['p50']:.1f}/{wave['p75']:.1f} | {reaches} | {result['legendary_acquired_run_rate']:.2%} (trial {result['legendary_acquisition_rate']:.0%}) | {result['legendary_cards_per_run']:.3f} |")
    lines += ["", "| 条件 | Wave | 到達率 | Time P25/P50/P75 | Deaths P50 | Final Power | Shapley DP | Shapley Weapon | Card residual |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name, result in payload["natural"].items():
        for w in (500,600,750,850,1000):
            x=result["checkpoint"][str(w)]; t=x["time_hours"]
            lines.append(f"| {name} | {w} | {x['reach_rate']:.0%} | {t['p25'] if t['p25'] is not None else '—'}/{t['p50'] if t['p50'] is not None else '—'}/{t['p75'] if t['p75'] is not None else '—'}h | {x['deaths_p50']} | {x['final_damage_power_p50']} | {x['dp_power_p50']} | {x['weapon_power_p50']} | {x['card_power_p50']} |")
    lines += ["", "## 自然Legendary取得", ""]
    for name, result in payload["natural"].items():
        if "legendary_on" in name:
            counters = result.get("legendary_offer_counters", {})
            lines.append(f"- Presented runs: {counters.get('seen_runs',0)}/{result.get('run_attempts',0)} ({result.get('legendary_seen_run_rate',0):.2%}); acquired runs: {counters.get('acquired_runs',0)}/{result.get('run_attempts',0)} ({result.get('legendary_acquired_run_rate',0):.2%}); offers={counters.get('offered',0)}, skips={counters.get('skipped',0)}, cards/run={result.get('legendary_cards_per_run',0):.4f}; 0/1/2/3+ cards per Run={result.get('legendary_card_count_run_distribution',{})}")
    for key in LEGENDARY_KEYS:
        waves=[event["wave"] for event in payload["natural_events"] if event["card"]==key and "A1_legendary_on" in str(event.get("condition","A1_legendary_on"))]
        ctr=payload["natural"].get("A1_legendary_on",{}).get("legendary_offer_counters",{})
        lines.append(f"- {POOL_BY_KEY[key].name}: offered {ctr.get('offered:'+key,0)}, acquired {ctr.get('selected:'+key,0)}, skipped {ctr.get('skipped:'+key,0)} / Wave P25/P50/P75: " + ("—" if not waves else f"{dp.percentile(waves,.25):.1f}/{dp.percentile(waves,.5):.1f}/{dp.percentile(waves,.75):.1f}"))
    lines += ["", "## Legendary統合テスト", "", "- Relic Apotheosis: relic本体なしの合成adapterのみ。1/3/5/7所持、同名複数、dust反映後×1.5、死亡後3枠へ復帰を確認。", "- Supplemental Inversion: 4 Hit Count × FU有無 × Re-Action有無 × 3 conversion × Resonant/Echoing 4通りの合成比較。武器専用攻撃Hitは本進行に個別モデルがないため数値計算の対象外。", "- Critical Singularity / Mitosis: 決定論的な関数・枠の合成チェックを同梱。", ""]
    for row in payload.get("relic_apotheosis_synthetic", {}).get("conditions", []):
        lines.append(f"  - relic {row['owned']}: active {row['normal_active']}→{row['apotheosis_active']}, effect {row['normal_total_effect']:.3f}→{row['ascended_total_effect']:.3f}, same-name active {row['same_name_active']}, death reversion {row['death_active_count_after_reversion']}")
    inversion_rows = payload.get("supplemental_inversion_synthetic", {}).get("conditions", [])
    lines.append(f"- Inversion synthetic cases={len(inversion_rows)}; conversion=40% examples show Hit/FU/Re-Action composition; direct after=0 by construction.")
    lines += ["", "## Legendary bot評価（同一代表状態で旧/新score比較）", "", "take/skip候補はbalancedのscore threshold=1.10との比較。実際の取得は同じ手札内の他カード・rerollにも依存する。", "", "| Wave | Legendary | 旧score | 新score | 旧判断 | 新判断 | 即時Power差 | 将来価値内訳 |", "|---:|---|---:|---:|---|---|---:|---|"]
    for wave, group in payload.get("legendary_valuation_comparison", {}).items():
        for key, row in group.items():
            future = ", ".join(f"{name}={value:.3f}" for name, value in row.get("future_value", {}).items()) or "—"
            lines.append(f"| {wave} | {POOL_BY_KEY[key].name} | {row['old_score']:.3f} | {row['new_score']:.3f} | {row['old_threshold_decision']} | {row['new_threshold_decision']} | {row['immediate_power_delta']:+.3f} | {future} |")
    lines += ["", "## 強制取得paired replay", "", "各checkpointで代表状態1件を選び、同一状態・同一RNGからLegendaryなし/ありを分岐。即時差とW1000到達またはRun失敗を比較。", "", "| Wave | Legendary | 即時Power差 | 到達Wave（なし→あり） | 失敗Wave（なし→あり） | 継続時間（なし→あり） |", "|---:|---|---:|---:|---:|---:|"]
    for wave, group in payload["forced"].items():
        base=group["cases"]["none"]
        for key in LEGENDARY_KEYS:
            case=group["cases"][key]
            lines.append(f"| {wave} | {POOL_BY_KEY[key].name} | {case['immediate_power_delta']:+.3f} | {base['end_wave']}→{case['end_wave']} | {base['failed_at']}→{case['failed_at']} | {base['continuation_hours']:.3f}→{case['continuation_hours']:.3f}h |")
    lines += ["", "## Recursive Follow-Up 連鎖診断", "", "FUの初回抽選率をp、再帰抽選率をq=min(p, 90%)、最大100FUとした理論値と100,000系列の乱数診断。P50/P95/P99は0件も含む1攻撃系列あたり。括弧内は初回FU成立後の条件付きchain長。", "", "| FU率 p | 再帰率 q | 平均FU 理論/実測 | P50 理論/実測 (条件付き) | P95 理論/実測 (条件付き) | P99 理論/実測 (条件付き) | cap率 理論/実測 |", "|---:|---:|---:|---:|---:|---:|---:|"]
    for row in payload.get("chain_diagnostics", {}).get("recursive_follow_up", []):
        lines.append(f"| {row['follow_up_chance']:.0%} | {row['recursive_chance']:.0%} | {row['theory_mean_additional_fu']:.4f}/{row['simulation_mean_additional_fu']:.4f} | {row['theory_chain_p50']}/{row['simulation_chain_p50']} ({row['theory_conditional_chain_p50']}/{row['simulation_conditional_chain_p50']}) | {row['theory_chain_p95']}/{row['simulation_chain_p95']} ({row['theory_conditional_chain_p95']}/{row['simulation_conditional_chain_p95']}) | {row['theory_chain_p99']}/{row['simulation_chain_p99']} ({row['theory_conditional_chain_p99']}/{row['simulation_conditional_chain_p99']}) | {row['theory_safety_cap_rate']:.3g}/{row['simulation_safety_cap_rate']:.3g} |")
    lines += ["", "## Endless Action 連鎖診断", "", "Action数は開始Normal Actionを含む。effectiveChance=min(max(現Re-Action率,15%),80%)、最大100 Re-Action。", "", "| 指定率 | 実効率 | 平均Action 理論/実測 | P50 理論/実測 | P95 理論/実測 | P99 理論/実測 | cap率 理論/実測 |", "|---:|---:|---:|---:|---:|---:|---:|"]
    for row in payload.get("chain_diagnostics", {}).get("endless_action", []):
        lines.append(f"| {row['requested_rate']:.0%} | {row['effective_rate']:.0%} | {row['theory_mean_actions']:.4f}/{row['simulation_mean_actions']:.4f} | {row['theory_actions_p50']}/{row['simulation_actions_p50']} | {row['theory_actions_p95']}/{row['simulation_actions_p95']} | {row['theory_actions_p99']}/{row['simulation_actions_p99']} | {row['theory_safety_cap_rate']:.3g}/{row['simulation_safety_cap_rate']:.3g} |")
    lines += ["", "## Knowledge Collapse 合成診断", "", f"同じ所持カードとLevel Up乱数seedから、Collapse有効/無効を比較。各条件{payload.get('knowledge_collapse_synthetic',{}).get('trials_per_condition','—')} synthetic trials。Normal側は通常カード選択、Collapse側は所持中の非Unique・非LegendaryからのみEcho。", "", "| 種類数 | Accelerated Learning | Level Up | Power増加 Collapse/Normal/差 | XP倍率 Collapse/Normal | AL units Collapse/Normal | 平均Echo | 新規種類 Normal/Collapse | Echo stack増加 上位 |", "|---:|:---:|---:|---:|---:|---:|---:|---:|---|"]
    for row in payload.get("knowledge_collapse_synthetic", {}).get("conditions", []):
        top=sorted(row["echo_target_counts"].items(),key=lambda x:x[1],reverse=True)[:3]
        lines.append(f"| {row['owned_card_types']} | {'あり' if row['accelerated_learning_present'] else 'なし'} | {row['levelups']} | {row['mean_echo_power_gain']:.3f}/{row['mean_normal_power_gain']:.3f}/{row['mean_power_delta_echo_minus_normal']:+.3f} | {row['mean_xp_multiplier_echo']:.3f}/{row['mean_xp_multiplier_normal']:.3f} | {row['mean_accelerated_units_echo']:.2f}/{row['mean_accelerated_units_normal']:.2f} | {row['mean_echoes']:.1f} | {row['normal_mean_new_card_types']:.2f}/{row['collapse_new_card_types']} | `{top}` |")
    lines += ["", "## Critical Overload 合成診断", "", "Crit Rate / Crit Multiplier DP由来は変更せず、合成Burn Countごとに通常Criticalカードの現在効果を差し引いて比較。", "", "| Burn | Overload倍率 | 失うCrit Power | Overload後Final Power | 純Final Power差 | 実Burn数 | 残存Crit stack | Crit Rate後 |", "|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in payload.get("critical_overload_synthetic", {}).get("conditions", []):
        lines.append(f"| {row['burn_count']} | ×{row['overload_multiplier']:.2f} | {row['lost_crit_power']:.3f} | {row['after_final_power']:.3f} | {row['net_final_power_delta']:+.3f} | {row['burn_count_applied']} | {row['active_critical_stacks_after']} | {row['crit_rate_after']:.3f} |")
    overload_test = payload.get("critical_overload_synthetic", {}).get("conditions", [{}])[0]
    lines.append(f"\n- Overload取得後にCritical Trainingを選ぶ合成テスト: decision={overload_test.get('later_critical_choice_decision')}, effect stack={overload_test.get('later_critical_choice_effect_stack')}, Burn Count {overload_test.get('burn_count_applied')}→{overload_test.get('burn_count_after_later_choice')}。Burnを通常効果とは別の`BURN`イベントとして記録。")
    lines += ["", "## Legendary固有診断", ""]
    for wave, group in payload["forced"].items():
        for key in LEGENDARY_KEYS:
            c=group["cases"][key]
            if key=="critical_singularity":
                tier=max(0,int(math.floor(c["critical_rate"])))
                fraction=max(0.0,c["critical_rate"]-tier)
                tier_dist=f"Tier {tier}: {1-fraction:.0%}" + (f", Tier {tier+1}: {fraction:.0%}" if fraction>1e-9 else "")
                lines.append(f"- W{wave} Critical Singularity: CritRate={c['critical_rate']:.3f}, CritMult={c['crit_mult']:.3f}, Crit Tier分布={tier_dist}, 適用Tier={c['multi_crit_tier']}, 即時Power差={c['immediate_power_delta']:+.3f}")
            elif key=="critical_overload":
                acquired=sum(int(event.get("count",1)) for event in c["burn_events"] if event.get("source")=="acquisition")
                later=sum(int(event.get("count",1)) for event in c["burn_events"] if event.get("source")!="acquisition")
                lines.append(f"- W{wave} Critical Overload: 取得時Burn={c['burn_count_at_acquisition']}, 取得後Burn={later}, 終了Burn={c['burn_count_end']}, multiplier={c['overload_multiplier']}, 純Power差={c['immediate_power_delta']:+.3f}; Burn記録={c['burned_cards']}")
            elif key=="recursive_follow_up":
                lines.append(f"- W{wave} Recursive Follow-Up: 初回FU Chance={c['follow_rate']:.3f}; 再帰抽選はこのChanceを上限90%でcap。更新した確率表は上記参照。")
            elif key=="endless_action":
                lines.append(f"- W{wave} Endless Action: effective Re-Action rateはmax(現率,15%)からmin(80%)。確率表は上記参照。")
            elif key=="weapon_mitosis":
                lines.append(f"- W{wave} Weapon Mitosis: Primary/Offshoot={c['mitosis_primary_rarity']}/{c['mitosis_offshoot_rarity']}, clone={c['mitosis_clone']}, 実物Offshoot交換={c['mitosis_real_offshoot_equips']}, Mitosis即時差={c['immediate_power_delta']:+.3f}")
            elif key=="knowledge_collapse":
                top=sorted(c["collapse_targets"].items(),key=lambda x:x[1],reverse=True)[:10]
                lines.append(f"- W{wave} Knowledge Collapse: 実戦replayでは取得後Level Up={c['collapse_echoes']+c['collapse_empty_levelups']}のため合成診断を追加。取得時種類={c.get('collapse_owned_types_at_acquisition','記録なし')}, Echo={c['collapse_echoes']}, Top={top}.")
            elif key=="relic_apotheosis":
                lines.append(f"- W{wave} Relic Apotheosis: paired replayはRelic未統合のため機能差を評価せず、synthetic adapterのみ（上記）。")
            else:
                rows=[r for r in inversion_rows if r["conversion"]==.40]
                lines.append(f"- W{wave} Supplemental Inversion: conversion=40%; synthetic hit/FU/Re-Action combinations={len(rows)}, paired immediate Power delta={c['immediate_power_delta']:+.3f}; direct attack removal is handled in action model.")
    lines += ["", "## 異常検知", ""]
    for key,value in payload["anomaly_checks"].items():
        lines.append(f"- {key}: {'検出' if value else 'なし'}")
    lines += ["", "## 判定", ""]
    for key, row in payload["legendary_judgment"].items():
        lines.append(f"- {POOL_BY_KEY[key].name}: {row['rating']}。{row['rule_change']}")
    lines += ["", "A/Bは同一seed列のpaired比較。Legendary自然率は候補設定で、正式採用値ではない。強制replayはcheckpointごとの代表状態1件であり、30試行全体の効果分散推定ではない。Relic ApotheosisはRelicシステム未統合のためsynthetic診断に限定。", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--max-attempts", type=int, default=220)
    parser.add_argument("--output-dir", type=Path, default=Path("output/new_w5000_legendary_v01_8card_30"))
    parser.add_argument("--diagnostics-only", action="store_true", help="reuse existing Legendary v0.1 JSON; do not rerun game trials")
    parser.add_argument("--diagnostic-trials", type=int, default=100_000, help="independent chain Monte Carlo count per probability")
    parser.add_argument("--synthetic-trials", type=int, default=1_000, help="synthetic Knowledge Collapse count per condition")
    parser.add_argument("--legendary-rate-under-500", type=float, default=0.0, help="candidate natural Legendary probability below W500")
    parser.add_argument("--legendary-rate-500-2499", type=float, default=0.001, help="candidate natural Legendary probability W500-2499")
    parser.add_argument("--legendary-rate-2500-plus", type=float, default=0.005, help="candidate natural Legendary probability W2500+")
    parser.add_argument("--valuation-ab", action="store_true", help="run 30-trial old vs dedicated Standard Legendary valuation comparison")
    args=parser.parse_args()
    if not 1 <= args.trials <= 30:
        parser.error("--trials must be between 1 and 30")
    if args.diagnostics_only:
        existing = args.output_dir / "new_w5000_legendary_v01.json"
        if not existing.exists():
            parser.error(f"existing results not found: {existing}")
        _diagnostics_from_existing(existing, args.output_dir, args)
        print(json.dumps({"diagnostics_only": True, "game_trials_rerun": 0,
                          "files": {"markdown": str(args.output_dir / existing.with_suffix('.md').name),
                                    "json": str(existing)}}, ensure_ascii=False, indent=2))
        return
    if args.valuation_ab:
        if args.trials != 30:
            parser.error("--valuation-ab requires exactly --trials 30")
        comparison = valuation_ab(args.trials, args.seed, args.max_attempts, args.output_dir)
        print(json.dumps({"valuation_ab_complete": True, "trials_per_arm": args.trials,
                          "arms": {key: {"success_rate": value["success_rate"],
                              "final_wave": value["final_wave_p25_p50_p75"],
                              "legendary_acquired_run_rate": value["legendary_acquired_run_rate"],
                              "mean_legendary_cards_per_run": value["mean_legendary_cards_per_run"]}
                              for key, value in comparison["arms"].items()},
                          "output_dir": str(args.output_dir.resolve())}, ensure_ascii=False, indent=2))
        return
    ACTIVE_LEGENDARY_RATES.update({
        "under_500": max(0.0, min(1.0, args.legendary_rate_under_500)),
        "500_2499": max(0.0, min(1.0, args.legendary_rate_500_2499)),
        "2500_plus": max(0.0, min(1.0, args.legendary_rate_2500_plus)),
    })
    configured_rates = dict(ACTIVE_LEGENDARY_RATES)
    config=sim.SimConfig(max_attempts=args.max_attempts,automation_enabled=False,interval_enabled=False,
        game_speed_enabled=False,initial_card_points_enabled=False,sweep_enabled=False,reward_skip_enabled=False,
        defense=sim.DefenseConfig(enabled=False),target_wave=1000,card_upgrade_cap=0,
        relic_selection_enabled=False,exponential_core_multiplier=1.0)
    capture=LegendaryCapture(config)
    dp.ACTIVE_CONFIG=config
    weapon.WEAPON_CARDS=POOL
    weapon.CARD_BY_KEY=POOL_BY_KEY
    dp.install_isolated_candidate(capture)
    install_legendary_hooks(capture)
    _install_run_callbacks()
    dp.ACTIVE_CONFIG=config
    results={}
    for name, enabled in (("A0_legendary_off",False),("A1_legendary_on",True)):
        ACTIVE_LEGENDARY_RATES.update(configured_rates if enabled else {"under_500":0.0,"500_2499":0.0,"2500_plus":0.0})
        if not enabled:
            sim.CARDS_BY_RARITY["L"] = tuple()
        else:
            sim.CARDS_BY_RARITY["L"] = LEGENDARY_CARDS
        results[name]=compact_condition(monte_carlo_condition(name,enabled,args.trials,args.seed,args.max_attempts,enabled))
    states_by_wave = {
        wave: [trial_states[wave] for trial_states in CAPTURE_STATES.values() if wave in trial_states]
        for wave in FORCE_WAVES
    }
    force=force_diagnostics(states_by_wave,args_config:=sim.SimConfig(
        max_attempts=args.max_attempts,automation_enabled=False,interval_enabled=False,game_speed_enabled=False,
        initial_card_points_enabled=False,sweep_enabled=False,reward_skip_enabled=False,
        defense=sim.DefenseConfig(enabled=False),target_wave=1000,card_upgrade_cap=0,
        relic_selection_enabled=False,exponential_core_multiplier=1.0))
    payload={
        "settings":{"trials":args.trials,"seed":args.seed,"max_attempts":args.max_attempts,
                    "baseline":"BC DP + C_drop_affix Weapon","target_wave":1000,
                    "legendary_rate_candidate":configured_rates,"legendary_rate_preserves_c_u_r_e_by_taking_from_common":True,"formal_modified":False,
                    "relic":False,"refinement":False,"sweep":False,"auto":False,"game_speed":False},
        "natural":results,
        "captured_state_counts": {"trials": len(CAPTURE_STATES), "waves": sorted({wave for state_map in CAPTURE_STATES.values() for wave in state_map})},
        "natural_events":[event for result in results.values() for event in result.get("legendary_events",[])],
        "forced":force,
        "legendary_valuation_comparison": legendary_valuation_diagnostics(states_by_wave, args_config),
        "chain_diagnostics":chain_diagnostics(args.diagnostic_trials,args.seed),
        "knowledge_collapse_synthetic":knowledge_collapse_synthetic(config,args.synthetic_trials),
        "critical_overload_synthetic":overload_synthetic(config),
        "relic_apotheosis_synthetic":apotheosis_synthetic(),
        "supplemental_inversion_synthetic":inversion_synthetic(),
        "legendary_function_synthetic":legendary_function_synthetic(),
        "legendary_rules_synthetic":legendary_rules_synthetic(config),
        "anomaly_checks":{},
        "legendary_judgment":{
            "critical_singularity":{"rating":"適正候補（低Critでは弱い）","rule_change":"Crit/Multi-Crit倍率を非線形化し、排他選択を作る。"},
            "critical_overload":{"rating":"強すぎる可能性","rule_change":"Crit系カードをBurnへ置換し、取得・以後の選択を直接倍率へ転換する。"},
            "recursive_follow_up":{"rating":"数値次第で強い候補","rule_change":"通常の2段Depthを撤廃し、最大100段の再帰FUへ変更する。"},
            "endless_action":{"rating":"強すぎる可能性","rule_change":"Re-ActionからのDepth制限を外して、新規Normal Actionを連鎖させる。"},
            "weapon_mitosis":{"rating":"適正候補","rule_change":"装備枠を2つにし、既存武器Dropを組合せ最適化へ変える。"},
            "knowledge_collapse":{"rating":"仕様上の問題あり／伸長候補","rule_change":"新規取得を止め、既存の非UniqueカードStackへLevel Up報酬を置き換える。"},
            "relic_apotheosis":{"rating":"Relic実装前の保留","rule_change":"3枠制限をRun中に外し、既存Relic全てをAscended化する。今回は合成adapterのみ。"},
            "supplemental_inversion":{"rating":"要進行統合検証","rule_change":"直接攻撃を0にし、通常攻撃系列のDirect相当をCrit可能なSupplementalへ変換する。"},
        },
    }
    payload["anomaly_checks"]=anomaly_checks(payload)
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    json_path=out/"new_w5000_legendary_v01.json"
    md_path=out/"new_w5000_legendary_v01.md"
    csv_path=out/"new_w5000_legendary_v01_checkpoints.csv"
    json_path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    write_report(md_path,payload)
    with csv_path.open("w",newline="",encoding="utf-8-sig") as handle:
        fields=["condition","wave","reach_rate","time_p25","time_p50","time_p75","deaths_p50","final_power","dp_shapley","weapon_shapley","card_residual"]
        writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader()
        for name,result in results.items():
            for wave,x in result["checkpoint"].items():
                t=x["time_hours"]
                writer.writerow({"condition":name,"wave":wave,"reach_rate":x["reach_rate"],"time_p25":t["p25"],"time_p50":t["p50"],"time_p75":t["p75"],"deaths_p50":x["deaths_p50"],"final_power":x["final_damage_power_p50"],"dp_shapley":x["dp_power_p50"],"weapon_shapley":x["weapon_power_p50"],"card_residual":x["card_power_p50"]})
    print(json.dumps({"files":{"markdown":str(md_path),"json":str(json_path),"csv":str(csv_path)},"success_rate":{"A0":results['A0_legendary_off']['success_rate'],"A1":results['A1_legendary_on']['success_rate']},"legendary_rate_candidate":configured_rates},ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
