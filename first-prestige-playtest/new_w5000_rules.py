"""Explicit new-card/BC-DP play rules. No simulator monkeypatches or bot hooks.

Candidate values, not formal adoption. Combat uses the existing candidate's
expected attack-series damage, temporal integral and discrete attack interval.
"""
import copy
import math
from dataclasses import replace

import simulate_first_prestige_v1 as sim
import simulate_new_w5000_common_uncommon_rare_epic as epic
import simulate_new_w5000_dp_v01 as dp
import simulate_new_w5000_legendary_v01 as legendary
import compare_new_w5000_weapon_acquisition as acquisition
import simulate_new_w5000_weapon_scale as scales

CARDS = legendary.POOL
PURE_DP_VALUES = dp._snapshot_values
BY_KEY = {item.key: item for item in CARDS}
# Relic Apotheosis requires the redesigned Relic calculation, not old Relic
# Power. Do not offer a card whose effect cannot yet be applied faithfully.
DEFERRED = frozenset({"relic_apotheosis"})
LEGENDARY_RATES = dict(legendary.ACTIVE_LEGENDARY_RATES)
DESCRIPTIONS = dict(zip((item.key for item in CARDS), (
    "Base ATK +25%", "Weapon ATK +25%（武器未装備中は休眠）",
    "Attack Speed +20%", "Crit率 +10pt", "Crit倍率 +0.25", "All Damage +15%",
    "XP +20%", "Boss Damage +25%", "Boss XP +50%", "武器分解Pt +15%",
    "AS +25% / Weapon ATK +10%", "Base ATK +35% / All Damage +5%",
    "Crit率 +8pt / Crit倍率 +0.20", "Crit率25ptごとにAS +5%",
    "Boss Damage +30% / Boss XP +30%", "3秒以内の撃破でXP +30%",
    "最初の3秒 Damage ×1.35", "最後の3秒 Damage ×2.00",
    "Base ATK +15% / AS +10%", "武器分解Pt +20%（Pity補助は未接続）",
    "Crit率からAS +5%：200%まで25pt、400%まで50pt、以降100ptごと",
    "Crit率からAll Damage +5%：200%まで25pt、400%まで50pt、以降100ptごと",
    "Crit率100%上限を解除（unique）", "追撃10% / Damage 50%を解禁（unique）",
    "追撃率 +15pt / 追撃Damage +25pt（未解禁なら休眠）", "Hit Count +0.20",
    "通常HitにSupplemental +25%（Crit・追撃には適用しない）",
    "Re-Action +15pt、上限80%、depth 1。追撃からは再行動しない",
    "XP余剰→Damage：×1–2は25%、×2–4は12.5%、以降5%",
    "取得後カードでXP成長：3% / 1.5% / 0.5% / 0.2% / 0.05%の段階減衰",
    "取得後BossでDamage成長：5% / 2.5% / 1% / 0.1%の段階減衰（乗算成長なし）",
    "HP30%以下でDamage ×2.5。重複はbonus +1.5ずつ",
    "超過CritをTier化：1 + Tier × (Crit倍率−1)。Compressionと排他",
    "Crit100%固定、倍率 +0.50、超過50ptごと +0.15。Multi-Critと排他",
    "追撃depth 2。未解禁なら10% / 50%保証", "Re-Action depth 2。未解禁なら15%保証",
    "Supplemental +15pt、Crit可能", "Supplemental +10pt、追撃にも適用",
    "Damage = 1 + 4×(経過/(制限−1秒))³、最後の1秒 ×5",
    "C/U/Rの正数値 ×1.20/1.15/1.10。独立倍率・ルールは対象外",
    "Multi-CritにTier減衰付き追加倍率（Overloadと排他）",
    "Crit系カードをBurn。Crit無効、Damage ×3×(1+0.40×Burn数)",
    "追撃を再帰。再帰率は現在追撃率、上限90%、安全上限100",
    "Re-Actionを再帰。率は現在値、最低15%・上限80%、安全上限100",
    "取得時の武器を65%のOffshootとして複製（固有効果は複製しない）",
    "以後のXP Level Upで、新種類でなく所持非uniqueカードをEcho取得",
    "遺物再設計の接続待ち（抽選対象外）",
    "Directを失い40%をSupplementalへ変換。Crit可能。ビルド次第で弱くなる",
)))


def legal_cards(run, rarity=None):
    blocked = set(DEFERRED)
    counts = run.counts
    if counts.get("multi_crit") or counts.get("critical_singularity"):
        blocked.add("critical_compression")
    if counts.get("critical_compression"):
        blocked.update({"multi_crit", "critical_singularity"})
    if counts.get("critical_singularity"):
        blocked.add("critical_overload")
    if counts.get("critical_overload"):
        blocked.add("critical_singularity")
    return [item for item in CARDS if item.key not in blocked
            and (rarity is None or item.rarity == rarity)
            and not (item.unique and counts.get(item.key, 0))]


def draw_hand(rng, run, dp_state, forced_rarity=None, excluded=(), echo=False):
    pool = ([item for item in CARDS if run.counts.get(item.key, 0)
             and not item.unique and item.rarity != "L"] if echo else legal_cards(run))
    hand = []
    for _ in range(3):
        rarity = forced_rarity
        if rarity is None and not echo:
            base_weights = dict(epic.rarity_chances_for_wave(run.kills))
            rate = LEGENDARY_RATES["under_500" if run.kills < 500 else "500_2499" if run.kills < 2500 else "2500_plus"]
            base_weights["C"] -= rate
            base_weights["L"] = rate
            weights = tuple((key, weight * dp.luck_rarity_weight_multiplier(dp_state, key))
                            for key, weight in base_weights.items())
            rarity = rng.choices([k for k, _ in weights], [w for _, w in weights])[0]
        eligible = [item for item in pool if (echo or item.rarity == rarity)
                    and item.key not in excluded and item not in hand]
        if not eligible:
            eligible = [item for item in pool if item.key not in excluded and item not in hand]
        if not eligible:
            break
        hand.append(rng.choice(eligible))
    return hand


def acquire(run, item, equipped_weapon=None):
    overloaded = bool(run.counts.get("critical_overload"))
    dp.acquire_card_new(run, item)
    if item.key == "critical_overload":
        legendary._burn_existing_criticals(run)
    elif overloaded and item.key in legendary.CRIT_BURN_KEYS:
        legendary._burn_one(run, item.key)
    if item.key == "weapon_mitosis":
        run._equipment_offshoot = copy.deepcopy(equipped_weapon)


def weapon_reference(wave):
    anchors = scales.CURVES["B_medium"]
    if wave <= anchors[0][0]:
        return anchors[0][1]
    for (a, x), (b, y) in zip(anchors, anchors[1:]):
        if wave <= b:
            return 10 ** (math.log10(x) + (math.log10(y) - math.log10(x)) * (wave - a) / (b - a))
    # No approved post-W2500 curve: preserve the last candidate anchor rather
    # than silently borrowing the huge old Weapon Power curve.
    return anchors[-1][1]


def values(run, permanent, inventory, boss, use_dp=True, include_weapon=True):
    r, p = copy.deepcopy(run), copy.deepcopy(permanent)
    counts = r.counts
    overload = bool(counts.get("critical_overload"))
    if overload:
        for key in legendary.CRIT_BURN_KEYS:
            counts[key] = 0
        dp.state_of(p).levels["crit_rate"] = dp.state_of(p).levels["crit_multiplier"] = 0
    if counts.get("critical_singularity"):
        counts["multi_crit"] = 1
    if counts.get("recursive_follow_up") and not (counts.get("follow_up_strike") or counts.get("follow_up_echo")):
        counts["follow_up_strike"] = 1
    primary = inventory.items.get(inventory.weapon_slot)
    offshoot = getattr(r, "_equipment_offshoot", None) if counts.get("weapon_mitosis") else None
    items = ([(primary, 1.0)] if primary else []) + ([(offshoot, .65)] if primary and offshoot else [])
    def weapon_base(_r, _p):
        return sum(item.base_atk * item.quality * item.enhancement_multiplier * weight for item, weight in items)
    def modifiers(_r, _p):
        result = {key: 0.0 for key in acquisition.AFFIX_KEYS}
        weighted_base = 0.0
        weighted_pct = 0.0
        for item, weight in items:
            base_weight = item.base_atk * item.quality * item.enhancement_multiplier * weight
            weighted_base += base_weight
            weighted_pct += item.affixes.get("weapon_atk_pct", 0) * item.enhancement_multiplier * base_weight
            for key, amount in item.affixes.items():
                if key in result and key != "weapon_atk_pct":
                    result[key] += amount * item.enhancement_multiplier * weight
        result["weapon_atk_pct"] = weighted_pct / weighted_base if weighted_base else 0
        if overload:
            result["crit_rate"] = result["crit_multiplier"] = 0
        return result
    xp_bonus = 0.0
    for uid in inventory.relic_slots:
        relic = inventory.items.get(uid)
        if relic and relic.unique_key == "learning_lens":
            xp_bonus += .10 * {"C": 1, "U": 1.25, "R": 1.5}[relic.rarity] * relic.enhancement_multiplier * relic.duplicate_multiplier
    def factor(*args):
        return legendary.action_factor(*args, counts=counts)
    def crit(rate, mult, multi):
        return legendary._singularity_expected(rate, mult) if counts.get("critical_singularity") else epic.crit_expected_multiplier(rate, mult, multi)
    def follow(rate, damage):
        if not run.counts.get("follow_up_strike") and (counts.get("follow_up_echo") or counts.get("recursive_follow_up")):
            amp = epic.amps(counts)[2]
            doubles = counts.get("double_strike", 0)
            return .10 + .15 * amp * doubles, .50 + .25 * amp * doubles
        return rate, damage
    result = PURE_DP_VALUES(r, p, boss, use_dp, include_weapon,
        weapon_base_provider=weapon_base, weapon_modifier_provider=modifiers,
        action_factor_provider=factor, crit_factor_provider=crit,
        follow_values_provider=follow, xp_multiplier=1 + xp_bonus)
    if overload:
        result["log_damage"] += -math.log10(1.01) + math.log10(3 * (1 + .40 * getattr(r, "_burn_count", 0)))
        result.update(crit_rate=0.0, crit_mult=0.0, multi_tier=0)
    return result


def snapshot(run, permanent, inventory, boss):
    current = values(run, permanent, inventory, boss)
    no_dp = values(run, permanent, inventory, boss, use_dp=False)
    no_weapon = values(run, permanent, inventory, boss, include_weapon=False)
    return sim.Snapshot(
        log_dps=current["log_damage"], base_attack_power=current["log_attack"],
        all_damage=current["all_damage"], attack_speed=current["attack_speed"],
        general_xp=current["general_xp"], boss_xp=current["boss_xp"],
        first_strike_mult=1.35 ** run.counts.get("first_strike", 0),
        last_stand_mult=2.0 ** run.counts.get("last_stand", 0),
        execution_mult=1 + 1.5 * run.counts.get("execution", 0),
        time_collapse=current["time_collapse"], crit_chance=current["crit_rate"],
        crit_multiplier=current["crit_mult"], follow_rate=current["follow_rate"],
        multi_crit_tier=current["multi_tier"],
        dp_power=current["log_damage"] - no_dp["log_damage"],
        weapon_power=current["log_damage"] - no_weapon["log_damage"], relic_power=0.0)


def time_to_kill(enemy_power, limit, snap):
    difference = enemy_power - snap.log_dps
    if difference > 308:
        return None
    required = 10 ** max(-308, difference)
    # Candidate temporal model; after integrating, round to an actual attack.
    # Resolve the execution threshold at a discrete attack, including overkill.
    max_attacks = int(math.floor(limit * snap.attack_speed + 1e-12))
    def units(n):
        return epic.temporal_integral(n / snap.attack_speed, limit, snap)
    def first_above(target):
        lo, hi = 0, max_attacks
        tolerance = abs(target) * 1e-12
        if units(hi) + tolerance < target:
            return None
        while lo < hi:
            middle = (lo + hi) // 2
            if units(middle) + tolerance >= target:
                hi = middle
            else:
                lo = middle + 1
        return max(1, lo)
    if snap.execution_mult > 1:
        crossing = first_above(.70 * required)
        if crossing is None:
            return None
        at_crossing = units(crossing)
        if at_crossing >= required:
            return crossing / snap.attack_speed
        required = at_crossing + (required - at_crossing) / snap.execution_mult
    attacks = first_above(required)
    return attacks / snap.attack_speed if attacks is not None else None


def remaining_hp(enemy_power, limit, snap, elapsed):
    """Use the same discrete/temporal calculation for display as for resolve."""
    difference = enemy_power - snap.log_dps
    if difference > 308:
        return 1.0
    required = 10 ** max(-308, difference)
    elapsed = min(limit, max(0, elapsed))
    attacks = math.floor(elapsed * snap.attack_speed + 1e-12)
    units = epic.temporal_integral(attacks / snap.attack_speed, limit, snap)
    if snap.execution_mult > 1:
        normal = replace(snap, execution_mult=1)
        crossing_time = time_to_kill(enemy_power + math.log10(.70), limit, normal)
        if crossing_time is not None and elapsed >= crossing_time:
            crossing_units = epic.temporal_integral(crossing_time, limit, snap)
            units = crossing_units + (units - crossing_units) * snap.execution_mult
    return min(1.0, max(0.0, 1 - units / required))
