"""Shadow-only, deterministic CardValue probe for the formal Balanced bot.

The simulator module is injected instead of imported so that CLI execution as
__main__ and test imports use exactly the same classes and card pool.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass


TARGET_KEYS = frozenset({
    "power_up", "rapid_fire", "execution", "time_collapse",
    "steady_force", "heavy_blow", "critical_eye", "precise_strike",
    "glass_cannon", "heavy_critical", "light_attack",
    "sharpened_edge", "critical_power",
    "experience", "fast_learner", "scholar", "study_break",
    "risky_study", "quick_learner", "boss_research", "battle_scholar",
    "accelerated_learning", "knowledge_conversion", "perfect_learning",
    "knowledge_collapse",
})
ENCOUNTER_CONDITIONAL_KEYS = frozenset({"execution", "time_collapse", "glass_cannon"})
# Keep XP-axis semantics explicit: adding a combat target must never silently
# route it through the XP Draft timeline.
XP_DRAFT_KEYS = frozenset({
    "experience", "fast_learner", "scholar", "study_break", "risky_study",
    "quick_learner", "boss_research", "battle_scholar", "accelerated_learning",
    "knowledge_conversion", "perfect_learning", "knowledge_collapse",
})


def _encounter_ttk(sim, frame, snapshot, run, config, extra_power=0.0):
    limit = sim.enemy_time_limit(frame.wave, run.counts.get("glass_cannon", 0))
    return sim.time_to_kill_with_defense(
        frame.wave, sim.configured_enemy_power(frame.wave, config), limit,
        snapshot, snapshot.log_dps + extra_power, config,
    )


def _required_power_for_time(sim, frame, snapshot, run, config, target_time):
    """Minimum final-DPS Power to match an actual, discrete combat deadline.

    The scalar changes neither attack cadence nor the timing/HP rules. Return
    None if even arbitrarily large damage cannot achieve this time (e.g. an
    unbreakable Defense layer or a faster-than-one-attack target).
    """
    limit = sim.enemy_time_limit(frame.wave, run.counts.get("glass_cannon", 0))
    if target_time < 1.0 / snapshot.attack_speed - 1e-12:
        return None

    def succeeds(power):
        ttk = _encounter_ttk(sim, frame, snapshot, run, config, power)
        return ttk is not None and ttk <= target_time + 1e-12
    if succeeds(0.0):
        return 0.0
    high = 0.01
    while high < 320.0 and not succeeds(high):
        high *= 2.0
    if not succeeds(high):
        return None
    low = 0.0
    for _ in range(52):
        middle = (low + high) / 2.0
        if succeeds(middle):
            high = middle
        else:
            low = middle
    return high


def _encounter_equivalent_pe(sim, frame, before, after, after_run, config):
    """Convert actual success/TTK to final-DPS Power, without future waves."""
    t0 = _encounter_ttk(sim, frame, before, frame.run, config)
    t1 = _encounter_ttk(sim, frame, after, after_run, config)
    if t0 is not None and t1 is not None and abs(t0 - t1) <= 1e-12:
        equivalent = 0.0
    elif t0 is None and t1 is None:
        limit = sim.enemy_time_limit(frame.wave, frame.run.counts.get("glass_cannon", 0))
        before_need = _required_power_for_time(sim, frame, before, frame.run, config, limit)
        after_need = _required_power_for_time(sim, frame, after, after_run, config, limit)
        equivalent = (before_need - after_need
                      if before_need is not None and after_need is not None else None)
    elif t1 is not None and (t0 is None or t1 < t0):
        equivalent = _required_power_for_time(sim, frame, before, frame.run, config, t1)
    else:
        assert t0 is not None
        needed = _required_power_for_time(sim, frame, after, after_run, config, t0)
        equivalent = None if needed is None else -needed
    required_hits = available_hits = None
    if (not before.time_collapse and before.first_strike_mult == 1.0
            and before.last_stand_mult == 1.0 and not config.defense.enabled):
        required_log = (sim.configured_enemy_power(frame.wave, config)
                        + math.log10(0.70 + 0.30 / before.execution_mult)
                        - before.log_dps)
        if required_log + math.log10(before.attack_speed) <= 308.0:
            required_hits = max(1, math.ceil(10**required_log * before.attack_speed - 1e-12))
        limit = sim.enemy_time_limit(frame.wave, frame.run.counts.get("glass_cannon", 0))
        available_hits = math.floor(limit * before.attack_speed + 1e-12)
    return equivalent, {
        "wave": frame.wave, "baseline_ttk": t0, "candidate_ttk": t1,
        "baseline_win": t0 is not None, "candidate_win": t1 is not None,
        "baseline_required_hits": required_hits, "baseline_available_hits": available_hits,
        "encounter_pe": equivalent,
        "status": "ok" if equivalent is not None else "unresolved_by_damage",
    }


@dataclass(frozen=True)
class Frame:
    wave: int
    snapshot: object
    run: object
    permanent: object
    xp_gain: float
    acquired: float


@dataclass(frozen=True)
class Forecast:
    predicted_end_wave: int
    reason: str
    frames: tuple[Frame, ...]
    remaining_xp: float
    remaining_xp_gross: float
    expected_drafts: float
    remaining_card_acquisitions: float
    normal_encounters: int
    boss_encounters: int
    big_boss_encounters: int
    confidence: str
    frontier: Frame | None


def _snapshot(sim, run, permanent, boss, config):
    # max_wave in the combat model controls the average relic power. Freeze it
    # independently of the (unmodelled) future random relic/weapon loot.
    return sim.compute_snapshot(run, permanent, boss, config)


def _start(sim, run, permanent, phase):
    r, p = copy.deepcopy(run), copy.deepcopy(permanent)
    if phase == "xp":
        r.xp_level_count += 1  # Cost was already paid before choose_card.
    elif phase == "guaranteed":
        pass  # The guarantee is marked used by the caller after choose_card.
    else:
        raise ValueError(f"unknown choice phase: {phase}")
    return r, p


def _xp_gain(sim, run, snap, wave, config, quick):
    boss = wave % 10 == 0
    base = 1 + (sim.progression_wave(wave, config) - 1) // 10
    factor = 10 if wave % 100 == 0 else 3
    gained = sim.progression_units(wave, config) * base * (
        factor * snap.boss_xp if boss else snap.general_xp
    )
    if quick and run.counts.get("quick_learner", 0):
        gained *= 1 + 0.30 * sim.limit_amplification(run.counts) * run.counts["quick_learner"]
    return gained


def _spend_expected_xp(sim, run):
    picks = 0
    while run.xp_level_count < len(sim.CARD_COSTS) and run.xp + 1e-12 >= sim.CARD_COSTS[run.xp_level_count]:
        run.xp -= sim.CARD_COSTS[run.xp_level_count]
        run.xp_level_count += 1
        picks += 1
    return picks


def _growth_after_kill(sim, run, snap, wave, config, quick):
    units = sim.progression_units(wave, config)
    if wave % 10 == 0:
        run.boss_devourer_units += units * run.counts.get("boss_devourer", 0)
        run.assimilation_power += units * sim.configured_enemy_power(wave, config) * 0.0005 * run.counts.get("boss_assimilation", 0)
    tiers = (
        ("critical_singularity", snap.crit_chance),
        ("recursive_follow_up", snap.follow_rate),
        ("infinite_barrage", max(0.0, snap.attack_speed - 1)),
        ("knowledge_collapse", max(0.0, snap.general_xp - 1)),
    )
    for key, tier in tiers:
        if run.counts.get(key, 0):
            run.legendary_growth_log += units * math.log10(1 + min(0.01, 0.002 * math.floor(tier + 1e-12)))
    if quick and run.allow_overdrive and run.counts.get("perfect_overdrive", 0):
        run.perfect_overdrive_stacks += units
    run.momentum_ready = quick and bool(run.counts.get("momentum", 0))


def predict_run_end(sim, run, permanent, next_wave, config, phase="xp"):
    """No RNG, no candidate or future random acquisition; all states are copies."""
    r, p = _start(sim, run, permanent, phase)
    frames = []
    drafts = 0.0
    acquired = 0.0
    xp_gross = 0.0
    boss_count = big_count = 0
    skip_end = sim.reward_preserving_skip_end(permanent, config)
    # No future random equipment or exploration. The mean relic curve is
    # frozen, except for the guaranteed first W100 relic unlock.
    fixed_relic_wave = p.max_wave
    for wave in range(next_wave, config.target_wave + 1):
        boss = wave % 10 == 0
        if boss:
            if wave % 100 == 0:
                big_count += 1
            else:
                boss_count += 1
        p.max_wave = fixed_relic_wave
        snap = _snapshot(sim, r, p, boss, config)
        limit = sim.enemy_time_limit(wave, r.counts.get("glass_cannon", 0))
        ttk = sim.time_to_kill_with_defense(wave, sim.configured_enemy_power(wave, config), limit, snap, snap.log_dps, config)
        if ttk is None and wave <= skip_end:
            ttk = limit
        frame = Frame(wave, snap, copy.deepcopy(r), copy.deepcopy(p), 0.0, acquired)
        if ttk is None:
            frames.append(frame)
            return Forecast(wave, "failed_battle", tuple(frames), r.xp, xp_gross, drafts, acquired,
                            len(frames) - boss_count - big_count, boss_count, big_count,
                            "low" if wave > next_wave else "medium", frame)
        quick = ttk <= 3.0 + 1e-12
        r.kills = wave
        if wave == 10 and (not r.weapon or r.weapon_power < math.log10(1.10)):
            # The first W10 weapon is deterministic; later weapon rolls are not.
            r.weapon = True
            r.weapon_power = math.log10(1.10)
            r.weapon_rarity = "C"
            r.weapon_origin_wave = 10
        if wave == 100 and not p.relic_unlocked:
            p.relic_unlocked = True
            fixed_relic_wave = max(100, fixed_relic_wave)
        _growth_after_kill(sim, r, snap, wave, config, quick)
        # Guaranteed rewards contribute an acquisition event, but not a card
        # effect. In the actual game guaranteed choices precede XP gain.
        guaranteed = 1 if wave in (25, 100, 500, 2500) else 0
        if guaranteed:
            r.growth_units += guaranteed * r.counts.get("growth_engine", 0)
            r.accelerated_units += guaranteed * r.counts.get("accelerated_learning", 0)
            acquired += guaranteed
        gained = _xp_gain(sim, r, snap, wave, config, quick)
        xp_gross += gained
        r.xp += gained
        picks = _spend_expected_xp(sim, r)
        drafts += picks
        # Upper-bound take assumption until a measured per-band table exists;
        # the forecast is low confidence after refinement is available.
        r.growth_units += picks * r.counts.get("growth_engine", 0)
        r.accelerated_units += picks * r.counts.get("accelerated_learning", 0)
        acquired += picks
        frames.append(Frame(wave, snap, frame.run, frame.permanent, gained, frame.acquired))
        if wave == config.target_wave:
            return Forecast(wave, "prestige", tuple(frames), r.xp, xp_gross, drafts, acquired,
                            len(frames) - boss_count - big_count, boss_count, big_count, "low", None)
    return Forecast(next_wave - 1, "prestige", (), r.xp, 0.0, drafts, acquired,
                    0, 0, 0, "low", None)


def _margin(sim, snap, wave, config, run):
    limit = sim.enemy_time_limit(wave, run.counts.get("glass_cannon", 0))
    integral = sim.temporal_integral(limit, limit, snap)
    ratio = 0.70 + 0.30 / snap.execution_mult
    return snap.log_dps + math.log10(integral) - sim.configured_enemy_power(wave, config) - math.log10(ratio)


def _candidate_snapshot(sim, frame, card, config):
    r, p = copy.deepcopy(frame.run), copy.deepcopy(frame.permanent)
    sim.acquire_card(r, card)
    if card.key == "accelerated_learning":
        r.accelerated_units += frame.acquired
    if card.key == "growth_engine":
        r.growth_units += frame.acquired
    return _snapshot(sim, r, p, frame.wave % 10 == 0, config), r


def _xp_draft_timeline(sim, forecast, start_xp, start_level, candidate_gains):
    """Pair drafts by paid XP level, retaining all drafts from a single kill."""
    xp = [start_xp, start_xp]
    levels = [start_level, start_level]
    events = [{}, {}]
    xp_before = [[], []]
    for index, frame in enumerate(forecast.frames):
        for side, gained in enumerate((frame.xp_gain, candidate_gains[index])):
            xp_before[side].append(xp[side])
            if not frame.xp_gain:
                continue  # Failed encounter: no XP and no Draft.
            xp[side] += gained
            ordinal = 0
            while (levels[side] < len(sim.CARD_COSTS)
                   and xp[side] + 1e-12 >= sim.CARD_COSTS[levels[side]]):
                level = levels[side]
                xp[side] -= sim.CARD_COSTS[level]
                events[side][level] = (index, frame.wave, xp[side], ordinal)
                levels[side] += 1
                ordinal += 1
    return events, xp_before


def _expected_draft_best(sim, run, permanent, config, raw_values):
    """Exact three distinct options, via a deterministic no-replacement CDF."""
    rarities = tuple(sim.CARDS_BY_RARITY)
    pools = {rarity: sim.available_cards(rarity, run, permanent, config) for rarity in rarities}
    if sum(map(len, pools.values())) < 3:
        return 0.0
    chances = sim.rarity_chances(permanent)

    def picked_rarity(rolled, counts):
        if len(pools.get(rolled, ())) > counts[rolled]:
            return rolled
        for fallback in ("R", "U", "C"):
            if len(pools.get(fallback, ())) > counts[fallback]:
                return fallback
        return None

    if run.card_count < 2:
        # The live starter hand selects among safe cards and replaces one
        # option with a random safe card if none were drawn. Enumerate only
        # this short early-game branch; no game RNG or imagined run is used.
        safe = [sim.CARD_BY_KEY[key] for key in sim.STARTER_SAFE_ORDER
                if key not in config.disabled_card_keys
                and key in {card.key for pool in pools.values() for card in pool}]
        if not safe:
            return 0.0

        def starter_draw(hand, probability):
            if len(hand) == 3:
                eligible = [card for card in hand if card.key in sim.STARTER_SAFE_KEYS]
                if eligible:
                    return probability * max(0.0, *(raw_values[card.key] for card in eligible))
                remaining = [card for card in safe if card not in hand]
                return probability * (sum(max(0.0, raw_values[card.key]) for card in remaining)
                                      / len(remaining) if remaining else 0.0)
            counts = {rarity: sum(card.rarity == rarity for card in hand) for rarity in rarities}
            result = 0.0
            for rolled, chance in chances:
                rarity = picked_rarity(rolled, counts)
                if rarity is None:
                    continue
                available = [card for card in pools[rarity] if card not in hand]
                for card in available:
                    result += starter_draw(hand + (card,), probability * chance / len(available))
            return result

        return starter_draw((), 1.0)

    totals = tuple(len(pools[rarity]) for rarity in rarities)
    positive = sorted({max(0.0, value) for value in raw_values.values()} - {0.0})
    if not positive:
        return 0.0

    def cdf(threshold):
        low = tuple(sum(max(0.0, raw_values[card.key]) <= threshold for card in pools[rarity])
                    for rarity in rarities)
        zero = (0,) * len(rarities)
        states = {zero: 1.0}
        positions = {rarity: i for i, rarity in enumerate(rarities)}
        for _ in range(3):
            following = {}
            for counts, probability in states.items():
                used = dict(zip(rarities, counts))
                for rolled, chance in chances:
                    rarity = picked_rarity(rolled, used)
                    if rarity is None:
                        continue
                    pos = positions[rarity]
                    fraction = (low[pos] - counts[pos]) / (totals[pos] - counts[pos])
                    if fraction <= 0:
                        continue
                    next_counts = counts[:pos] + (counts[pos] + 1,) + counts[pos + 1:]
                    following[next_counts] = following.get(next_counts, 0.0) + probability * chance * fraction
            states = following
        return sum(states.values())

    expectation = previous = 0.0
    for value in positive:
        expectation += (value - previous) * (1.0 - cdf(previous))
        previous = value
    return expectation


def _legacy_draft_value(sim, run, permanent, config):
    """Retain the earlier XP proxy for non-XP candidate cards."""
    base = sim.compute_snapshot(run, permanent, False, config)
    limit = sim.enemy_time_limit(max(1, run.kills + 1), run.counts.get("glass_cannon", 0))
    before = base.log_dps + math.log10(sim.temporal_integral(limit, limit, base)) - math.log10(
        0.70 + 0.30 / base.execution_mult)
    choices = []
    for rarity, chance in sim.rarity_chances(permanent):
        pool = sim.available_cards(rarity, run, permanent, config)
        if not pool:
            continue
        for card in pool:
            r = copy.deepcopy(run)
            sim.acquire_card(r, card)
            snap = sim.compute_snapshot(r, permanent, False, config)
            limit_after = sim.enemy_time_limit(max(1, run.kills + 1), r.counts.get("glass_cannon", 0))
            after = snap.log_dps + math.log10(sim.temporal_integral(limit_after, limit_after, snap)) - math.log10(
                0.70 + 0.30 / snap.execution_mult)
            choices.append((max(0.0, after - before), chance / len(pool)))
    if not choices:
        return 0.0
    choices.sort()
    cumulative = result = 0.0
    mass = sum(prob for _, prob in choices)
    for value, prob in choices:
        next_cumulative = cumulative + prob / mass
        result += value * (next_cumulative**3 - cumulative**3)
        cumulative = next_cumulative
    return result


def _xp_draft_value(sim, forecast, level, event, states, xp_before, config, diagnostics=None):
    """One draft after its kill, evaluated against every remaining H encounter."""
    index, wave, paid_xp, ordinal = event
    # The next pre-fight frame contains known post-kill rewards and owned
    # growth; it never contains an imagined future Draft card. At H's last
    # successful wave no next frame exists, so use the current pre-fight copy.
    next_frame = forecast.frames[min(index + 1, len(forecast.frames) - 1)]
    pool_run = copy.deepcopy(states[min(index + 1, len(states) - 1)])
    pool_run.kills = wave
    pool_run.xp = paid_xp
    pool_run.xp_level_count = level
    pool_run.card_count += int(forecast.frames[index].acquired) + (1 if wave in (25, 100, 500, 2500) else 0) + ordinal
    pool_permanent = copy.deepcopy(next_frame.permanent)
    pool_permanent.max_wave = max(pool_permanent.max_wave, wave)  # Pool only, NOT combat power.
    legal = [card for rarity in sim.CARDS_BY_RARITY
             for card in sim.available_cards(rarity, pool_run, pool_permanent, config)]
    if diagnostics is not None:
        diagnostics.update({"pool_size": len(legal),
                            "pool_keys": tuple(sorted(card.key for card in legal)),
                            "status": "ok" if len(legal) >= 3 else "no_legal_hand"})
    if index + 1 == len(forecast.frames):
        return 0.0
    if len(legal) < 3:
        return 0.0
    raw_values = {}
    origin_acquired = next_frame.acquired
    for card in legal:
        raw = 0.0
        for later in range(index + 1, len(forecast.frames)):
            frame = forecast.frames[later]
            base_run = copy.deepcopy(states[later])
            base_run.xp = xp_before[later]
            baseline = _snapshot(sim, base_run, frame.permanent, frame.wave % 10 == 0, config)
            virtual = copy.deepcopy(base_run)
            sim.acquire_card(virtual, card)
            future_acquisitions = max(0.0, frame.acquired - origin_acquired)
            if card.key == "growth_engine":
                virtual.growth_units += future_acquisitions
            if card.key == "accelerated_learning":
                virtual.accelerated_units += future_acquisitions
            gained = _snapshot(sim, virtual, frame.permanent, frame.wave % 10 == 0, config)
            if card.key in ENCOUNTER_CONDITIONAL_KEYS:
                before_frame = Frame(frame.wave, baseline, base_run, frame.permanent, 0.0, frame.acquired)
                encounter_pe, _ = _encounter_equivalent_pe(
                    sim, before_frame, baseline, gained, virtual, config)
                if encounter_pe is None:
                    raise ValueError("XP draft encounter value is unresolved by damage")
                raw += encounter_pe
            else:
                raw += (_margin(sim, gained, frame.wave, config, virtual)
                        - _margin(sim, baseline, frame.wave, config, base_run))
        raw_values[card.key] = raw / len(forecast.frames)
    return _expected_draft_best(sim, pool_run, pool_permanent, config, raw_values)


def evaluate_card(sim, run, permanent, card, next_wave, config, *, phase="xp", forecast=None):
    if card.key not in TARGET_KEYS:
        raise ValueError(f"outside v0.1 shadow set: {card.key}")
    forecast = forecast or predict_run_end(sim, run, permanent, next_wave, config, phase)
    if not forecast.frames:
        raise ValueError("no encounters to evaluate")
    immediate_sum = conditional_sum = xp_sum = growth_sum = 0.0
    encounter_outcomes = []
    conditional_status = "ok"
    start_run = _start(sim, run, permanent, phase)[0]
    old_base_xp = old_candidate_xp = start_run.xp
    old_base_level = old_candidate_level = start_run.xp_level_count
    old_draft_value = None
    candidate_gains = []
    candidate_states = []
    total = len(forecast.frames)
    reach_baseline = reach_candidate = 1.0
    candidate_growth_log = 0.0
    prior_snapshot = None
    prior_wave = None
    last_candidate_margin = None
    def gate(value):
        # A measurement proxy only; temperature is not PE-calibrated.
        return 1 / (1 + math.exp(-max(-60.0, min(60.0, value / 0.10))))
    for index, frame in enumerate(forecast.frames):
        if card.key == "knowledge_collapse" and prior_snapshot is not None:
            tier = math.floor(max(0.0, prior_snapshot.general_xp - 1.0) + 1e-12)
            candidate_growth_log += sim.progression_units(prior_wave, config) * math.log10(
                1 + min(0.01, 0.002 * tier))
        snap, candidate_run = _candidate_snapshot(sim, frame, card, config)
        if candidate_growth_log:
            candidate_run.legendary_growth_log += candidate_growth_log
            full_snap = _snapshot(sim, candidate_run, frame.permanent, frame.wave % 10 == 0, config)
            growth_sum += full_snap.log_dps - snap.log_dps
        else:
            full_snap = snap
        candidate_states.append(candidate_run)
        prior_snapshot, prior_wave = full_snap, frame.wave
        baseline = frame.snapshot
        immediate = snap.log_dps - baseline.log_dps
        immediate_sum += immediate
        candidate_margin = _margin(sim, snap, frame.wave, config, candidate_run)
        last_candidate_margin = _margin(sim, full_snap, frame.wave, config, candidate_run)
        baseline_margin = _margin(sim, baseline, frame.wave, config, frame.run)
        if card.key in ENCOUNTER_CONDITIONAL_KEYS:
            encounter_pe, outcome = _encounter_equivalent_pe(
                sim, frame, baseline, snap, candidate_run, config)
            if encounter_pe is None:
                conditional_status = "unresolved_by_damage"
            else:
                conditional_sum += encounter_pe - immediate
            encounter_outcomes.append(outcome)
        else:
            conditional_sum += candidate_margin - baseline_margin - immediate
        if forecast.frontier is not None and index + 1 < total:
            reach_baseline *= gate(baseline_margin)
            reach_candidate *= gate(last_candidate_margin)
        if frame.xp_gain:
            # Compare the same baseline encounter schedule. XP gained by an
            # additional draft is not applied again as Growth.
            quick = sim.time_to_kill_with_defense(
                frame.wave, sim.configured_enemy_power(frame.wave, config),
                sim.enemy_time_limit(frame.wave, candidate_run.counts.get("glass_cannon", 0)),
                full_snap, full_snap.log_dps, config)
            gain = _xp_gain(sim, candidate_run, full_snap, frame.wave, config,
                            quick is not None and quick <= 3.0 + 1e-12)
            candidate_gains.append(gain)
            if card.key not in XP_DRAFT_KEYS:
                old_base_xp += frame.xp_gain
                old_candidate_xp += gain
                while old_base_level < len(sim.CARD_COSTS) and old_base_xp + 1e-12 >= sim.CARD_COSTS[old_base_level]:
                    old_base_xp -= sim.CARD_COSTS[old_base_level]
                    old_base_level += 1
                while (old_candidate_level < len(sim.CARD_COSTS)
                       and old_candidate_xp + 1e-12 >= sim.CARD_COSTS[old_candidate_level]):
                    old_candidate_xp -= sim.CARD_COSTS[old_candidate_level]
                    old_candidate_level += 1
                active_extra = old_candidate_level - old_base_level
                if active_extra and index + 1 < total:
                    if old_draft_value is None:
                        old_draft_value = _legacy_draft_value(sim, frame.run, frame.permanent, config)
                    xp_sum += active_extra * old_draft_value / total
        else:
            candidate_gains.append(0.0)
    draft_events = []
    if card.key in XP_DRAFT_KEYS:
        events, xp_before = _xp_draft_timeline(sim, forecast, start_run.xp,
                                               start_run.xp_level_count, candidate_gains)
        states = ([frame.run for frame in forecast.frames], candidate_states)
        for level in sorted(events[0].keys() | events[1].keys()):
            contributions = []
            pool_details = []
            for side in (0, 1):
                event = events[side].get(level)
                details = {}
                contributions.append(_xp_draft_value(sim, forecast, level, event, states[side],
                                                     xp_before[side], config, details) if event else 0.0)
                pool_details.append(details)
            xp_sum += contributions[1] - contributions[0]
            draft_events.append({"level": level,
                                 "baseline_wave": events[0][level][1] if level in events[0] else None,
                                 "candidate_wave": events[1][level][1] if level in events[1] else None,
                                 "baseline_value": contributions[0],
                                 "candidate_value": contributions[1],
                                 "xp_delta": contributions[1] - contributions[0],
                                 "baseline_pool": pool_details[0],
                                 "candidate_pool": pool_details[1]})
    immediate = immediate_sum / total
    conditional = conditional_sum / total if conditional_status == "ok" else None
    xp = xp_sum
    # For the initial set, Accelerated Learning's own future XP effect is
    # included in the XP branch, not charged again to Growth.
    growth = growth_sum / total
    total_pe = (0.60 * (immediate + conditional) + 0.25 * growth + 0.15 * xp
                if conditional is not None else None)
    delta = None
    if forecast.frontier is not None:
        frontier = forecast.frontier
        m0 = _margin(sim, frontier.snapshot, frontier.wave, config, frontier.run)
        delta = reach_candidate * gate(last_candidate_margin) - reach_baseline * gate(m0)
    return {
        "card_id": card.key,
        "legacy_score": sim.card_score("balanced", card, run, permanent, next_wave, config),
        "immediate_combat_pe": immediate,
        "conditional_combat_pe": conditional,
        "conditional_status": conditional_status,
        "growth_pe": growth,
        "xp_pe": xp,
        "total_pe": total_pe,
        "predicted_run_end_wave": forecast.predicted_end_wave,
        "terminal_break_probability_delta": delta,
        "terminal_pe": None,
        "terminal_included": False,
        "prediction_confidence": forecast.confidence,
        "prediction_reason": forecast.reason,
        "remaining_encounters": total,
        "remaining_xp": forecast.remaining_xp,
        "remaining_xp_gross": forecast.remaining_xp_gross,
        "expected_drafts": forecast.expected_drafts,
        "xp_draft_events": draft_events,
        "remaining_card_acquisitions": forecast.remaining_card_acquisitions,
        "normal_encounters": forecast.normal_encounters,
        "boss_encounters": forecast.boss_encounters,
        "big_boss_encounters": forecast.big_boss_encounters,
        "encounter_outcomes": encounter_outcomes,
    }
