#!/usr/bin/env python3
"""Detailed Wave 1-100 Monte Carlo simulator for the incremental roguelite.

The model includes card offers, rerolls, XP overflow, expected critical damage,
discrete attack counts, the Wave 10 weapon, death points, and permanent upgrades.
It intentionally stops at Wave 100; later rarity pools are still provisional.
"""

from __future__ import annotations

import argparse
import collections
import math
import random
import statistics
from dataclasses import dataclass, field
from pathlib import Path


SEED = 20260827
DEFAULT_TRIALS = 5_000
RARITY_CHANCE = (("C", 0.94), ("U", 0.05), ("R", 0.01))


@dataclass(frozen=True)
class Card:
    key: str
    name: str
    rarity: str
    tags: frozenset[str] = frozenset()
    unique: bool = False


CARDS = (
    # Common parts.
    Card("power_up", "Power Up", "C", frozenset({"atk"})),
    Card("heavy_blow", "Heavy Blow", "C", frozenset({"atk"})),
    Card("rapid_fire", "Rapid Fire", "C", frozenset({"as"})),
    Card("light_attack", "Light Attack", "C", frozenset({"as"})),
    Card("critical_eye", "Critical Eye", "C", frozenset({"crit"})),
    Card("critical_power", "Critical Power", "C", frozenset({"crit"})),
    Card("sharpened_edge", "Sharpened Edge", "C", frozenset({"crit"})),
    Card("precise_strike", "Precise Strike", "C", frozenset({"crit"})),
    Card("heavy_critical", "Heavy Critical", "C", frozenset({"crit"})),
    Card("experience", "Experience", "C", frozenset({"xp"})),
    Card("fast_learner", "Fast Learner", "C", frozenset({"xp"})),
    Card("scholar", "Scholar", "C", frozenset({"xp", "boss"})),
    Card("study_break", "Study Break", "C", frozenset({"xp"})),
    Card("battle_focus", "Battle Focus", "C", frozenset({"damage"})),
    Card("glass_cannon", "Glass Cannon", "C", frozenset({"atk", "risk"})),
    # Initial Uncommon connectors.
    Card("overdrive", "Overdrive", "U", frozenset({"as", "risk"})),
    Card("battle_rhythm", "Battle Rhythm", "U", frozenset({"atk", "connector"})),
    Card("heavy_momentum", "Heavy Momentum", "U", frozenset({"as", "connector"})),
    Card("critical_training", "Critical Training", "U", frozenset({"crit", "connector"})),
    Card("knowledge_is_power", "Knowledge is Power", "U", frozenset({"xp", "connector"})),
    Card("critical_tempo", "Critical Tempo", "U", frozenset({"crit", "as", "connector"})),
    Card("risk_premium", "Risk Premium", "U", frozenset({"risk", "damage"})),
    Card("boss_hunter", "Boss Hunter", "U", frozenset({"boss", "xp"})),
    Card("weapon_resonance", "Weapon Resonance", "U", frozenset({"weapon"})),
    # Initial Rare engines. The nonlinear engines are unique.
    Card("twin_engine", "Twin Engine", "R", frozenset({"atk", "as", "engine"}), True),
    Card("critical_investment", "Critical Investment", "R", frozenset({"crit", "engine"}), True),
    Card("critical_cascade", "Critical Cascade", "R", frozenset({"crit", "followup"})),
    Card("applied_knowledge", "Applied Knowledge", "R", frozenset({"xp", "engine"}), True),
)

CARD_BY_KEY = {card.key: card for card in CARDS}
CARDS_BY_RARITY = {
    rarity: tuple(card for card in CARDS if card.rarity == rarity)
    for rarity in ("C", "U", "R")
}

# The first two level-ups always show at least one immediately useful card.
# Without this guard, a roughly one-in-ten tutorial run receives only setup/XP
# cards and dies around Wave 8 before the fixed weapon is introduced.
STARTER_SAFE_KEYS = frozenset(
    {"power_up", "heavy_blow", "rapid_fire", "glass_cannon"}
)


def c(counts: collections.Counter[str], key: str) -> int:
    return counts.get(key, 0)


def tag_count(counts: collections.Counter[str], tag: str) -> int:
    return sum(count * (tag in CARD_BY_KEY[key].tags) for key, count in counts.items())


def round_to_five(value: float) -> int:
    return int(math.floor(value / 5 + 0.5)) * 5


def build_card_costs(size: int = 100) -> list[int]:
    costs = [3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 30, 45]
    delta = 15
    while len(costs) < size:
        delta = round_to_five(delta * 1.35)
        costs.append(costs[-1] + delta)
    return costs


CARD_COSTS = build_card_costs()


@dataclass
class PermanentState:
    atk: int = 0
    attack_speed: int = 0
    xp: int = 0
    banked_dp: int = 0

    @property
    def total_levels(self) -> int:
        return self.atk + self.attack_speed + self.xp


@dataclass(frozen=True)
class CombatStats:
    attack: float
    attack_speed: float
    crit_chance: float
    crit_multiplier: float
    damage_per_attack: float
    general_xp: float
    boss_xp: float
    time_factor: float


@dataclass
class RunResult:
    reached: int
    combat_seconds: float
    cards: int
    counts: collections.Counter[str]
    weapon_obtained: bool


@dataclass
class TrialResult:
    profile: str
    first_reached: int
    first_seconds: float
    first_cards: int
    deaths_to_100: int
    attempts_to_100: int
    total_dp: int
    levels_at_100: int
    selected_cards: collections.Counter[str] = field(default_factory=collections.Counter)


def enemy_hp(wave: int, hp_growth: float, mid_growth: float | None = None) -> int:
    if wave <= 9:
        return (5, 6, 7, 8, 9, 10, 11, 12, 13)[wave - 1]
    mid_growth = hp_growth if mid_growth is None else mid_growth
    if wave <= 50:
        normal_hp = 10 * hp_growth ** (wave - 10)
    else:
        normal_hp = 10 * hp_growth**40 * mid_growth ** (wave - 50)
    if wave % 10 == 0:
        normal_hp *= 1.5
    return max(1, round(normal_hp))


def enemy_time_limit(wave: int) -> float:
    return 15.0 if wave % 10 == 0 else 10.0


def compute_stats(
    counts: collections.Counter[str],
    permanent: PermanentState,
    weapon: bool,
    boss: bool,
) -> CombatStats:
    crit_chance = (
        0.10 * c(counts, "critical_eye")
        + 0.03 * c(counts, "critical_power")
        + 0.06 * c(counts, "sharpened_edge")
        + 0.15 * c(counts, "precise_strike")
        + 0.03 * c(counts, "heavy_critical")
    )
    crit_steps = math.floor((crit_chance + 1e-12) / 0.10)

    atk_cards = tag_count(counts, "atk")
    as_cards = tag_count(counts, "as")
    crit_cards = tag_count(counts, "crit")
    xp_cards = tag_count(counts, "xp")

    attack_bonus = (
        0.25 * c(counts, "power_up")
        + 0.40 * c(counts, "heavy_blow")
        + 0.50 * c(counts, "glass_cannon")
        + 0.15 * c(counts, "battle_rhythm") * as_cards
    )
    attack_penalty = (
        0.90 ** c(counts, "light_attack")
        * 0.98 ** c(counts, "fast_learner")
        * 0.85 ** c(counts, "overdrive")
    )
    weapon_multiplier = 1.0
    if weapon:
        weapon_multiplier = 1.10 * 1.25 ** c(counts, "weapon_resonance")
    attack_multiplier = (
        1.10 ** permanent.atk
        * weapon_multiplier
        * (1 + attack_bonus)
        * attack_penalty
    )

    attack_speed_bonus = (
        0.20 * c(counts, "rapid_fire")
        + 0.30 * c(counts, "light_attack")
        + 0.50 * c(counts, "overdrive")
        + 0.08 * c(counts, "heavy_momentum") * atk_cards
        + 0.08 * c(counts, "critical_tempo") * crit_steps
    )
    attack_speed_penalty = (
        0.90 ** c(counts, "heavy_blow")
        * 0.95 ** c(counts, "precise_strike")
        * 0.97 ** c(counts, "heavy_critical")
        * 0.98 ** c(counts, "study_break")
    )
    attack_speed_multiplier = (
        1.05 ** permanent.attack_speed
        * (1 + attack_speed_bonus)
        * attack_speed_penalty
    )

    xp_multiplier = 1.05 ** permanent.xp * (
        1
        + 0.20 * c(counts, "experience")
        + 0.25 * c(counts, "fast_learner")
        + 0.30 * c(counts, "study_break")
    )
    boss_xp_multiplier = xp_multiplier * (
        1 + 1.00 * c(counts, "scholar") + 1.00 * c(counts, "boss_hunter")
    )

    time_factor = 0.90 ** c(counts, "glass_cannon")
    risk_steps = c(counts, "glass_cannon")
    all_damage = (
        1
        + 0.15 * c(counts, "battle_focus")
        + 0.12 * c(counts, "critical_training") * crit_cards
        + 0.15 * c(counts, "knowledge_is_power") * xp_cards
        + 0.25 * c(counts, "risk_premium") * risk_steps
    )

    crit_multiplier = (
        2.0
        + 0.50 * c(counts, "critical_power")
        + 0.20 * c(counts, "sharpened_edge")
        + 0.50 * c(counts, "critical_investment") * crit_steps
    ) * 1.50 ** c(counts, "heavy_critical")
    capped_crit = min(1.0, crit_chance)
    expected_crit = 1 + capped_crit * (crit_multiplier - 1)
    cascade = 1 + 0.50 * c(counts, "critical_cascade") * capped_crit

    if c(counts, "twin_engine"):
        all_damage *= math.sqrt(attack_multiplier * attack_speed_multiplier)
    if c(counts, "applied_knowledge"):
        all_damage *= xp_multiplier**2
    if permanent.total_levels >= 5:
        all_damage *= 1.20

    boss_damage = 1 + 1.00 * c(counts, "boss_hunter") if boss else 1.0
    damage_per_attack = attack_multiplier * expected_crit * cascade * all_damage * boss_damage

    return CombatStats(
        attack=attack_multiplier,
        attack_speed=attack_speed_multiplier,
        crit_chance=crit_chance,
        crit_multiplier=crit_multiplier,
        damage_per_attack=damage_per_attack,
        general_xp=xp_multiplier,
        boss_xp=boss_xp_multiplier,
        time_factor=time_factor,
    )


def draw_rarity(rng: random.Random) -> str:
    value = rng.random()
    cumulative = 0.0
    for rarity, chance in RARITY_CHANCE:
        cumulative += chance
        if value < cumulative:
            return rarity
    return "C"


def draw_hand(
    rng: random.Random,
    counts: collections.Counter[str],
    excluded: set[str] | None = None,
    guarantee_starter: bool = False,
) -> list[Card]:
    excluded = set() if excluded is None else set(excluded)
    hand: list[Card] = []
    for _ in range(3):
        rarity = draw_rarity(rng)
        candidates = [
            card
            for card in CARDS_BY_RARITY[rarity]
            if card.key not in excluded
            and card.key not in {picked.key for picked in hand}
            and not (card.unique and counts.get(card.key, 0))
        ]
        if not candidates:
            candidates = [
                card
                for card in CARDS_BY_RARITY["C"]
                if card.key not in excluded and card.key not in {picked.key for picked in hand}
            ]
        hand.append(rng.choice(candidates))
    if guarantee_starter and not any(card.key in STARTER_SAFE_KEYS for card in hand):
        candidates = [
            CARD_BY_KEY[key]
            for key in STARTER_SAFE_KEYS
            if key not in excluded and key not in {card.key for card in hand}
        ]
        if candidates:
            hand[0] = rng.choice(candidates)
    return hand


def card_score(
    profile: str,
    card: Card,
    counts: collections.Counter[str],
    permanent: PermanentState,
    weapon: bool,
    next_wave: int,
    hp_growth: float,
    mid_growth: float,
) -> float:
    boss = next_wave % 10 == 0
    before = compute_stats(counts, permanent, weapon, boss)
    after_counts = counts.copy()
    after_counts[card.key] += 1
    after = compute_stats(after_counts, permanent, weapon, boss)

    before_capacity = before.damage_per_attack * before.attack_speed * before.time_factor
    after_capacity = after.damage_per_attack * after.attack_speed * after.time_factor
    damage_gain = math.log(max(after_capacity / before_capacity, 1e-12))
    # Bosses provide roughly 25% of base XP over each ten-wave block. Valuing
    # only the immediately next enemy made Scholar look worthless for nine
    # choices out of ten, so use the long-run 75/25 normal/boss mix.
    xp_gain = 0.75 * math.log(max(after.general_xp / before.general_xp, 1e-12))
    xp_gain += 0.25 * math.log(max(after.boss_xp / before.boss_xp, 1e-12))

    def can_kill(stats: CombatStats) -> bool:
        hits = max(
            1,
            math.ceil(
                enemy_hp(next_wave, hp_growth, mid_growth) / stats.damage_per_attack - 1e-12
            ),
        )
        ttk = hits / stats.attack_speed
        return ttk <= enemy_time_limit(next_wave) * stats.time_factor + 1e-12

    before_survives = can_kill(before)
    after_survives = can_kill(after)
    survival_adjustment = 0.0
    if before_survives and not after_survives:
        survival_adjustment = -10.0
    elif not before_survives and after_survives:
        survival_adjustment = 1.0

    if profile == "damage":
        return damage_gain + survival_adjustment
    if profile == "balanced":
        return damage_gain + 0.45 * xp_gain + survival_adjustment

    rarity_bonus = {"C": 0.0, "U": 0.025, "R": 0.06}[card.rarity]
    potential = 0.0
    if card.key == "battle_rhythm":
        potential += 0.02 * tag_count(counts, "as")
    elif card.key == "heavy_momentum":
        potential += 0.02 * tag_count(counts, "atk")
    elif card.key == "critical_training":
        potential += 0.015 * tag_count(counts, "crit")
    elif card.key == "knowledge_is_power":
        potential += 0.015 * tag_count(counts, "xp")
    elif card.key in {"critical_investment", "critical_cascade"}:
        potential += 0.025 * tag_count(counts, "crit")
    elif card.key == "applied_knowledge":
        potential += 0.03 * tag_count(counts, "xp")
    elif card.key == "weapon_resonance" and not weapon:
        potential += 0.02
    return damage_gain + 0.35 * xp_gain + rarity_bonus + potential + survival_adjustment


def choose_card(
    rng: random.Random,
    profile: str,
    counts: collections.Counter[str],
    permanent: PermanentState,
    weapon: bool,
    next_wave: int,
    hp_growth: float,
    mid_growth: float,
    rerolls: int,
    card_number: int,
) -> Card:
    guarantee_starter = card_number < 2
    hand = draw_hand(rng, counts, guarantee_starter=guarantee_starter)
    threshold = {"damage": math.log(1.08), "balanced": math.log(1.06), "synergy": math.log(1.05)}[
        profile
    ]
    excluded: set[str] = set()
    for reroll_index in range(rerolls + 1):
        scored = [
            (
                card_score(
                    profile,
                    card,
                    counts,
                    permanent,
                    weapon,
                    next_wave,
                    hp_growth,
                    mid_growth,
                ),
                card,
            )
            for card in hand
        ]
        best_score, best_card = max(scored, key=lambda item: item[0])
        if best_score >= threshold or reroll_index == rerolls:
            break
        excluded.update(card.key for card in hand)
        hand = draw_hand(rng, counts, excluded, guarantee_starter)
    return best_card


def run_once(
    rng: random.Random,
    profile: str,
    permanent: PermanentState,
    hp_growth: float,
    mid_growth: float,
    target_wave: int = 100,
    rerolls: int = 1,
) -> RunResult:
    counts: collections.Counter[str] = collections.Counter()
    xp = 0.0
    cards = 0
    combat_seconds = 0.0
    weapon = False

    for wave in range(1, target_wave + 1):
        boss = wave % 10 == 0
        stats = compute_stats(counts, permanent, weapon, boss)
        hp = enemy_hp(wave, hp_growth, mid_growth)
        hits = max(1, math.ceil(hp / stats.damage_per_attack - 1e-12))
        ttk = hits / stats.attack_speed
        limit = enemy_time_limit(wave) * stats.time_factor
        if ttk > limit + 1e-12:
            combat_seconds += limit
            return RunResult(wave - 1, combat_seconds, cards, counts, weapon)

        combat_seconds += ttk
        if wave == 10:
            weapon = True

        base_xp = 1 + (wave - 1) // 10
        if boss:
            xp += base_xp * 3 * stats.boss_xp
        else:
            xp += base_xp * stats.general_xp

        while cards < len(CARD_COSTS) and xp + 1e-12 >= CARD_COSTS[cards]:
            xp -= CARD_COSTS[cards]
            picked = choose_card(
                rng,
                profile,
                counts,
                permanent,
                weapon,
                wave + 1,
                hp_growth,
                mid_growth,
                rerolls,
                cards,
            )
            counts[picked.key] += 1
            cards += 1

    return RunResult(target_wave, combat_seconds, cards, counts, weapon)


def next_dp_cost(total_levels: int, growth: float) -> int:
    return math.ceil(5 * growth**total_levels)


def spend_dp(permanent: PermanentState, profile: str, growth: float) -> None:
    cycle = {
        "balanced": ("atk", "attack_speed", "atk", "attack_speed", "xp"),
        "synergy": ("xp", "atk", "attack_speed"),
    }
    while permanent.banked_dp >= next_dp_cost(permanent.total_levels, growth):
        permanent.banked_dp -= next_dp_cost(permanent.total_levels, growth)
        if profile == "damage":
            choice = "atk"
        else:
            choices = cycle[profile]
            choice = choices[permanent.total_levels % len(choices)]
        setattr(permanent, choice, getattr(permanent, choice) + 1)


def run_trial(
    rng: random.Random,
    profile: str,
    hp_growth: float,
    mid_growth: float,
    dp_growth: float,
) -> TrialResult:
    permanent = PermanentState()
    selected: collections.Counter[str] = collections.Counter()
    total_dp = 0
    first: RunResult | None = None
    best_wave = 0

    for attempt in range(1, 61):
        result = run_once(
            rng,
            profile,
            permanent,
            hp_growth,
            mid_growth,
            rerolls=2 if best_wave >= 50 else 1,
        )
        selected.update(result.counts)
        best_wave = max(best_wave, result.reached)
        if first is None:
            first = result
        if result.reached >= 100:
            assert first is not None
            return TrialResult(
                profile=profile,
                first_reached=first.reached,
                first_seconds=first.combat_seconds,
                first_cards=first.cards,
                deaths_to_100=attempt - 1,
                attempts_to_100=attempt,
                total_dp=total_dp,
                levels_at_100=permanent.total_levels,
                selected_cards=selected,
            )

        if result.reached >= 25:
            gained = result.reached // 5
            total_dp += gained
            permanent.banked_dp += gained
            spend_dp(permanent, profile, dp_growth)

    raise RuntimeError(f"{profile} profile did not reach Wave 100")


def percentile(values: list[float] | list[int], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lo = math.floor(position)
    hi = math.ceil(position)
    if lo == hi:
        return float(ordered[lo])
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo)


def stats_line(values: list[float] | list[int], digits: int = 1) -> str:
    entries = (
        statistics.fmean(values),
        percentile(values, 0.10),
        percentile(values, 0.50),
        percentile(values, 0.90),
    )
    return " / ".join(f"{value:.{digits}f}" for value in entries)


def simulate(
    trials: int,
    hp_growth: float,
    mid_growth: float,
    dp_growth: float,
) -> dict[str, list[TrialResult]]:
    output: dict[str, list[TrialResult]] = {}
    for offset, profile in enumerate(("damage", "balanced", "synergy")):
        rng = random.Random(SEED + offset)
        output[profile] = [
            run_trial(rng, profile, hp_growth, mid_growth, dp_growth) for _ in range(trials)
        ]
    return output


def build_report(
    results: dict[str, list[TrialResult]],
    trials: int,
    hp_growth: float,
    mid_growth: float,
    dp_growth: float,
) -> str:
    names = {"damage": "火力型", "balanced": "標準型", "synergy": "シナジー型"}
    lines = [
        "# Wave 1〜100 詳細シミュレーション",
        "",
        "## 前提",
        "",
        f"- 各方針 {trials:,}試行（合計 {trials * 3:,}試行、seed={SEED}）",
        f"- Wave 10以降の通常HP成長率: ×{hp_growth:.4f}/Wave",
        f"- Wave 51〜100の通常HP成長率: ×{mid_growth:.4f}/Wave",
        "- Boss HP: 通常HP×1.50、制限時間15秒",
        "- Common 94%、Uncommon 5%、Rare 1%、3択内重複なし",
        "- 最初の2回の3択には即時火力カードを最低1枚保証",
        "- Growing PowerをBattle Focus（全Damage+15%）に置換",
        f"- DP価格: `ceil(5×{dp_growth:.4f}^合計Lv)`",
        "- 恒久強化合計Lv5で全Damage×1.20",
        "- Wave 10撃破後、そのラン中に固定武器×1.10を装備",
        "",
        "## HPチェックポイント",
        "",
        "| Wave | HP |",
        "|---:|---:|",
        f"| 10 Boss | {enemy_hp(10, hp_growth, mid_growth):,} |",
        f"| 25 | {enemy_hp(25, hp_growth, mid_growth):,} |",
        f"| 34 | {enemy_hp(34, hp_growth, mid_growth):,} |",
        f"| 50 Boss | {enemy_hp(50, hp_growth, mid_growth):,} |",
        f"| 75 | {enemy_hp(75, hp_growth, mid_growth):,} |",
        f"| 100 Boss | {enemy_hp(100, hp_growth, mid_growth):,} |",
        "",
        "## 今回反映したカード調整",
        "",
        "- Glass Cannon: 基礎攻撃力+50%、制限時間×0.90",
        "- Experience: XP+20%",
        "- Fast Learner: XP+25%、基礎攻撃力×0.98",
        "- Study Break: XP+30%、AS×0.98",
        "- Critical Eye: Crit率+10%",
        "- Critical Power: Crit率+3%、Crit倍率+0.50x",
        "- Sharpened Edge: Crit率+6%、Crit倍率+0.20x",
        "- Precise Strike: Crit率+15%、AS×0.95",
        "- Heavy Critical: Crit率+3%、Crit倍率×1.50、AS×0.97",
        "- UncommonのATK/AS/Crit/XP変換率を初期案から約1.5倍",
        "",
        "## 結果",
        "",
        "各セルは `平均 / P10 / 中央値 / P90` です。",
        "",
        "| 方針 | 初ラン撃退数 | 初ラン戦闘分 | 初ランカード数 | Wave 100までの死亡 | Wave 100時Lv |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for profile, trials_for_profile in results.items():
        first_reached = [r.first_reached for r in trials_for_profile]
        first_minutes = [r.first_seconds / 60 for r in trials_for_profile]
        first_cards = [r.first_cards for r in trials_for_profile]
        deaths = [r.deaths_to_100 for r in trials_for_profile]
        levels = [r.levels_at_100 for r in trials_for_profile]
        lines.append(
            f"| {names[profile]} | {stats_line(first_reached, 1)} | "
            f"{stats_line(first_minutes, 2)} | {stats_line(first_cards, 1)} | "
            f"{stats_line(deaths, 1)} | {stats_line(levels, 1)} |"
        )

    lines.extend(["", "## 選択されたカード", ""])
    for profile, trials_for_profile in results.items():
        picked: collections.Counter[str] = collections.Counter()
        total = 0
        for result in trials_for_profile:
            picked.update(result.selected_cards)
            total += sum(result.selected_cards.values())
        ordered = sorted(picked.items(), key=lambda item: item[1], reverse=True)
        top = ", ".join(f"{CARD_BY_KEY[key].name} {count / total:.1%}" for key, count in ordered[:6])
        bottom = ", ".join(f"{CARD_BY_KEY[key].name} {count / total:.1%}" for key, count in ordered[-6:])
        lines.extend(
            [
                f"### {names[profile]}",
                "",
                f"- 上位: {top}",
                f"- 下位: {bottom}",
                "",
            ]
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=DEFAULT_TRIALS)
    parser.add_argument("--hp-growth", type=float, default=1.062)
    parser.add_argument("--mid-growth", type=float, default=1.035)
    parser.add_argument("--dp-growth", type=float, default=1.021)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    mid_growth = args.hp_growth if args.mid_growth is None else args.mid_growth
    results = simulate(args.trials, args.hp_growth, mid_growth, args.dp_growth)
    report = build_report(results, args.trials, args.hp_growth, mid_growth, args.dp_growth)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
