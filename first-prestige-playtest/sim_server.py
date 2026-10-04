#!/usr/bin/env python3
"""Wave 1-500 playable adapter backed by the existing Python simulator.

Combat math, cards, XP, enemy Power, DP prices, weapons and relic growth call
the functions in scripts/simulate_first_prestige_v1.py.  This file only turns
the batch simulator into a user-driven state machine.
"""

from __future__ import annotations

import collections
import copy
import json
import math
import random
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE / "scripts"))

import simulate_first_prestige_v1 as sim  # noqa: E402


HOST = "127.0.0.1"
PORT = 8765
TARGET_WAVE = 500
PROFILE_NAMES = {"damage": "火力型", "balanced": "標準型", "synergy": "シナジー型"}

CARD_DESCRIPTIONS = {
    "power_up": "Base ATK +25%",
    "heavy_blow": "Base ATK +40% / Attack Speed x0.90",
    "rapid_fire": "Attack Speed +20%",
    "light_attack": "Attack Speed +30% / Base ATK x0.90",
    "critical_eye": "Crit率 +10%",
    "critical_power": "Crit率 +3% / Crit倍率 +0.50",
    "sharpened_edge": "Crit率 +6% / Crit倍率 +0.20",
    "precise_strike": "Crit率 +15% / Attack Speed x0.95",
    "heavy_critical": "Crit率 +3% / Crit倍率 x1.50 / Attack Speed x0.97",
    "experience": "XP +20%",
    "fast_learner": "XP +25% / Base ATK x0.98",
    "scholar": "Boss XP +100%",
    "study_break": "XP +30% / Attack Speed x0.98",
    "steady_force": "全Damage +15%",
    "glass_cannon": "Base ATK +50% / 制限時間 x0.90",
    "overclock": "Attack Speed +35% / Base ATK x0.90",
    "brutal_force": "Base ATK +50% / Attack Speed x0.90",
    "battle_focus": "全Damage +20% / XP x0.90",
    "risky_study": "XP +35% / 全Damage x0.90",
    "critical_training": "Crit率 +10% / Crit倍率 +0.20",
    "critical_momentum": "Crit率25%ごとにAttack Speed +5%",
    "boss_research": "Boss Damage +40% / Boss XP +25% / 通常Damage x0.95",
    "quick_learner": "3秒以内撃破時、その敵のXP +30%",
    "battle_scholar": "XP余剰倍率の10%を全Damageへ変換",
    "escalation": "10体撃破ごとに全Damage x1.05（ラン内累積）",
    "last_stand": "残り3秒以下でDamage x1.75",
    "first_strike": "最初の3秒間Damage x1.40",
    "critical_engine": "Crit率20%ごとにAttack Speed +5%",
    "critical_conversion": "Crit率10%ごとに全Damage +3%",
    "brutal_critical": "Crit倍率 x1.50 / Crit率 -10%",
    "overflow": "Crit率100%上限を撤廃（超過Tierはまだ無効）",
    "follow_up_strike": "10%で元Damageの50%追撃を解禁",
    "double_strike": "追撃率 +15% / 追撃Damage +25%",
    "knowledge_conversion": "XP余剰倍率の25%を全Damageへ変換",
    "accelerated_learning": "カード取得ごとにXP +3%",
    "growth_engine": "取得後、カード取得ごとに全Damage x1.05",
    "boss_devourer": "取得後、Boss撃破ごとに全Damage x1.15",
    "execution": "敵HP30%以下でDamage x2.50",
    "momentum": "3秒以内撃破で次敵Damage x1.50",
    "multi_crit": "100%超過Crit率をMulti-Critとして有効化",
    "critical_geometry": "Crit Tierを3段ごとに+1段",
    "follow_up_echo": "追撃から25%で1段階だけ追加追撃",
    "perfect_learning": "XP余剰倍率の50%を全Damageへ変換",
    "double_scaling": "Attack Speed余剰倍率の25%をBase ATKへ変換",
    "time_collapse": "時間経過でDamage上昇、終盤最大x5",
    "boss_assimilation": "Boss Powerの0.05%をDamage Powerへラン内累積",
    "limit_break": "Rare以下のプラス効果量 x1.20",
}


def magnitude(power: float) -> str:
    if power < 6:
        value = 10**power
        return f"{value:,.2f}" if value < 1_000 else f"{value:,.0f}"
    return f"1e{power:.2f}"


class PlaySession:
    def __init__(self, profile: str, seed: int) -> None:
        self.profile = profile
        self.target_wave = TARGET_WAVE
        self.seed = seed
        self.rng = random.Random(seed)
        self.config = sim.SimConfig(max_attempts=500)
        self.permanent = sim.PermanentState(automation_enabled=False)
        self.run = sim.RunState()
        self.attempt = 0
        self.total_combat_seconds = 0.0
        self.total_dp = 0
        self.mode = "starting"
        self.wave = 1
        self.fight: dict[str, Any] | None = None
        self.pre_snapshot: sim.Snapshot | None = None
        self.pending_cards: collections.deque[tuple[str | None, str | None]] = collections.deque()
        self.card_hand: list[sim.Card] = []
        self.card_excluded: set[str] = set()
        self.card_rerolls_used = 0
        self.card_forced_rarity: str | None = None
        self.card_forced_key: str | None = None
        self.pending_weapon: dict[str, Any] | None = None
        self.weapon_context = "after_wave"
        self.starting_weapon: dict[str, Any] | None = None
        self.last_death: dict[str, Any] | None = None
        self.logs: list[str] = []
        self._new_run()

    def _log(self, message: str) -> None:
        self.logs = [message, *self.logs][:14]

    def _new_run(self) -> None:
        self.attempt += 1
        self.run = sim.RunState(
            xp=self.permanent.initial_xp,
            card_points=self.permanent.initial_card_points,
        )
        self.run.next_relic_drop = sim.next_geometric_drop(self.rng, 0)
        if self.starting_weapon:
            weapon = self.starting_weapon
            self.run.weapon = True
            self.run.weapon_power = weapon["power"]
            self.run.weapon_rarity = weapon["rarity"]
            self.run.weapon_origin_wave = weapon["originWave"]
            self.starting_weapon = None
        self.wave = 1
        self.last_death = None
        self.pending_cards.clear()
        self._log(f"Run {self.attempt}開始。")
        self._prepare_fight()

    def _snapshot(self, run: sim.RunState, wave: int) -> sim.Snapshot:
        return sim.compute_snapshot(run, self.permanent, wave % 10 == 0, self.config)

    def _effective_log_dps(self, run: sim.RunState, wave: int) -> float:
        return self._snapshot(run, wave).log_dps

    def _prepare_fight(self) -> None:
        self.mode = "combat"
        self.wave = self.run.kills + 1
        snapshot = self._snapshot(self.run, self.wave)
        log_dps = snapshot.log_dps
        enemy_power = sim.configured_enemy_power(self.wave, self.config)
        limit = sim.enemy_time_limit(self.wave, sim.n(self.run.counts, "glass_cannon"))
        ttk = sim.time_to_kill_with_defense(
            self.wave,
            enemy_power,
            limit,
            snapshot,
            log_dps,
            self.config,
        )
        hp = sim.hp_power(enemy_power, self.wave, self.config.defense)
        defense = sim.defense_power(self.wave, self.config.defense)
        self.pre_snapshot = snapshot
        self.fight = {
            "wave": self.wave,
            "boss": self.wave % 10 == 0,
            "enemyPower": enemy_power,
            "hpPower": hp,
            "enemyHp": magnitude(hp),
            "defensePower": defense,
            "armorBreakEnabled": self.config.defense.enabled,
            "dpsPower": log_dps,
            "dps": magnitude(log_dps),
            "attackSpeed": snapshot.attack_speed,
            "critChance": snapshot.crit_chance,
            "critMultiplier": snapshot.crit_multiplier,
            "xpGain": snapshot.general_xp,
            "baseAttack": magnitude(snapshot.base_attack_power),
            "followRate": snapshot.follow_rate,
            "timeLimit": limit,
            "timeToKill": ttk,
            "willWin": ttk is not None,
        }

    def _permanent_payload(self) -> dict[str, Any]:
        return {
            "maxWave": self.permanent.max_wave,
            "bankedDp": self.permanent.banked_dp,
            "totalDp": self.total_dp,
            "levels": {
                "atk": self.permanent.atk,
                "attackSpeed": self.permanent.attack_speed,
                "xp": self.permanent.xp,
                "total": self.permanent.total_levels,
            },
            "nextDpCost": sim.next_dp_cost(self.permanent.total_levels, self.config.dp_growth),
            "weaponMaterial": self.permanent.weapon_material,
            "relicMaterial": self.permanent.relic_material,
            "weaponAcquisitions": self.permanent.weapon_acquisitions,
            "weaponGenerations": self.permanent.weapon_generations,
            "relicDrops": self.permanent.relic_drops,
            "relicGenerations": self.permanent.relic_generations,
            "relicTypes": len(self.permanent.relic_types),
            "relicDuplicates": self.permanent.relic_duplicates,
            "relicQuality": self.permanent.relic_quality,
            "relicUnlocked": self.permanent.relic_unlocked,
        }

    def _run_payload(self) -> dict[str, Any]:
        cards = [
            {"key": key, "name": sim.CARD_BY_KEY[key].name, "count": count}
            for key, count in sorted(self.run.counts.items())
            if count > 0
        ]
        return {
            "attempt": self.attempt,
            "kills": self.run.kills,
            "combatSeconds": self.run.combat_seconds,
            "totalCombatSeconds": self.total_combat_seconds + self.run.combat_seconds,
            "xp": self.run.xp,
            "nextCardCost": (
                sim.CARD_COSTS[self.run.xp_level_count]
                if self.run.xp_level_count < len(sim.CARD_COSTS)
                else None
            ),
            "cardCount": self.run.card_count,
            "cards": cards,
            "weapon": (
                {
                    "power": self.run.weapon_power,
                    "rarity": self.run.weapon_rarity,
                    "originWave": self.run.weapon_origin_wave,
                    "multiplier": 10**self.run.weapon_power,
                }
                if self.run.weapon
                else None
            ),
            "cardPoints": self.run.card_points,
        }

    def _card_payload(self, item: sim.Card) -> dict[str, Any]:
        starter = self.card_forced_rarity is None and self.run.card_count < 2
        eligible = not starter or item.key in sim.STARTER_SAFE_KEYS
        before = self._effective_log_dps(self.run, self.wave)
        candidate = copy.deepcopy(self.run)
        sim.acquire_card(candidate, item, self.config)
        after = self._effective_log_dps(candidate, self.wave)
        diff = after - before
        preview_snapshot = self._snapshot(candidate, self.wave)
        enemy_power = self.fight["enemyPower"] if self.fight else sim.configured_enemy_power(self.wave, self.config)
        limit = sim.enemy_time_limit(self.wave, sim.n(candidate.counts, "glass_cannon"))
        ttk = sim.time_to_kill_with_defense(
            self.wave,
            enemy_power,
            limit,
            preview_snapshot,
            after,
            self.config,
        )
        return {
            "key": item.key,
            "name": item.name,
            "rarity": item.rarity,
            "description": CARD_DESCRIPTIONS.get(item.key, "詳細式は既存シミュレーター定義を使用"),
            "tags": sorted(item.tags),
            "eligible": eligible,
            "score": sim.card_score(self.profile, item, self.run, self.permanent, self.wave, self.config),
            "immediateMultiplier": 10**diff if -20 < diff < 20 else None,
            "afterDpsPower": after,
            "nextTtk": ttk,
            "nextTimeLimit": limit,
        }

    def state(self) -> dict[str, Any]:
        starter = self.mode == "card" and self.card_forced_rarity is None and self.run.card_count < 2
        options = [self._card_payload(item) for item in self.card_hand] if self.mode == "card" else []
        eligible = [option for option in options if option["eligible"]]
        recommended = max(eligible, key=lambda option: option["score"])["key"] if eligible else None
        forge_cost = 5.0 * sim.wave_band_multiplier(max(10, self.permanent.max_wave))
        return {
            "status": self.mode,
            "profile": self.profile,
            "profileName": PROFILE_NAMES[self.profile],
            "seed": self.seed,
            "targetWave": self.target_wave,
            "fight": self.fight if self.mode == "combat" else None,
            "run": self._run_payload(),
            "permanent": self._permanent_payload(),
            "options": options,
            "starterGuarantee": starter,
            "forcedRarity": self.card_forced_rarity,
            "rerollsLeft": max(0, self.permanent.rerolls - self.card_rerolls_used) if self.mode == "card" and self.card_forced_rarity is None else 0,
            "recommendedCard": recommended,
            "pendingWeapon": self.pending_weapon,
            "weaponContext": self.weapon_context if self.mode == "weapon" else None,
            "death": self.last_death,
            "canForgeWeapon": self.mode == "death" and self.permanent.weapon_acquisitions >= 5 and self.permanent.max_wave >= 10 and self.permanent.weapon_material + 1e-12 >= forge_cost,
            "forgeWeaponCost": forge_cost,
            "canForgeRelic": self.mode == "death" and self.permanent.relic_material + 1e-12 >= 10.0 * 2**self.permanent.relic_generations,
            "forgeRelicCost": 10.0 * 2**self.permanent.relic_generations,
            "logs": self.logs,
            "notice": self._notice(),
        }

    def _notice(self) -> str:
        if self.mode == "combat":
            return "戦闘はシミュレーターの攻撃回数・制限時間判定で進行します。"
        if self.mode == "card":
            return "最初の2枚は現行シミュレーター通り、火力保証対象だけ選択できます。" if self.run.card_count < 2 and self.card_forced_rarity is None else "カードを1枚選択してください。"
        if self.mode == "weapon":
            return "新しい武器を装備するか、武器素材へ変換してください。"
        if self.mode == "death":
            return "DPを好きなステータスへ振り分けてから再挑戦できます。"
        if self.mode == "complete":
            return "Wave500到達。Epic確定報酬まで処理済みです。"
        return ""

    def action(self, body: dict[str, Any]) -> None:
        action = body.get("type")
        if action == "resolve" and self.mode == "combat":
            self._resolve_fight()
        elif action == "select_card" and self.mode == "card":
            self._select_card(str(body.get("cardKey", "")))
        elif action == "reroll" and self.mode == "card":
            self._reroll()
        elif action in {"equip_weapon", "smelt_weapon"} and self.mode == "weapon":
            self._resolve_weapon(action == "equip_weapon")
        elif action == "buy_dp" and self.mode == "death":
            self._buy_dp(str(body.get("upgrade", "")))
        elif action == "forge_weapon" and self.mode == "death":
            self._forge_weapon()
        elif action == "forge_relic" and self.mode == "death":
            self._forge_relic()
        elif action == "retry" and self.mode == "death":
            self.total_combat_seconds += self.run.combat_seconds
            self._new_run()

    def _resolve_fight(self) -> None:
        if self.mode != "combat":
            return
        assert self.fight is not None and self.pre_snapshot is not None
        ttk = self.fight["timeToKill"]
        if ttk is None:
            combat_seconds = self.run.combat_seconds + self.fight["timeLimit"]
            gained = self.run.kills // 5
            # Prepare fallible result/memory work before committing death rewards.
            memory_permanent = copy.deepcopy(self.permanent)
            sim.store_memory_candidates(
                sim.RunResult(
                    reached=self.run.kills,
                    combat_seconds=combat_seconds,
                    choices=self.run.choices,
                    cards=self.run.card_count,
                    cards_dissolved=sum(self.run.cards_dissolved.values()),
                    card_upgrades=self.run.card_upgrades_bought,
                    card_points_spent=self.run.card_points_spent,
                    card_points_left=self.run.card_points,
                    counts=self.run.counts.copy(),
                    failure_wave=self.wave,
                    checkpoints=dict(self.run.checkpoint_power),
                    checkpoint_states=copy.deepcopy(self.run.checkpoint_states),
                    reach_elapsed=dict(self.run.reach_elapsed),
                    end_state={},
                    w2500_state=copy.deepcopy(self.run.w2500_state),
                ),
                memory_permanent,
            )
            self.run.combat_seconds = combat_seconds
            self.permanent.memory_candidate_keys = memory_permanent.memory_candidate_keys
            self.permanent.banked_dp += gained
            self.total_dp += gained
            self.permanent.max_wave = max(self.permanent.max_wave, self.run.kills)
            self.last_death = {
                "failureWave": self.wave,
                "reached": self.run.kills,
                "gainedDp": gained,
                "runCombatSeconds": self.run.combat_seconds,
            }
            self.mode = "death"
            self._log(f"Wave {self.wave}で時間切れ。+{gained} DP")
            return

        self.run.combat_seconds += ttk
        wave = self.wave
        quick = ttk <= 3.0 + 1e-12
        had_momentum = sim.n(self.run.counts, "momentum") > 0
        had_overdrive = sim.n(self.run.counts, "perfect_overdrive") > 0
        pre_quick_learner = sim.n(self.run.counts, "quick_learner")
        pre_limit_amp = sim.limit_amplification(self.run.counts)
        self.run.kills = wave
        self.permanent.max_wave = max(self.permanent.max_wave, wave)

        if wave == 100:
            self.permanent.relic_unlocked = True
            self._log("Wave100：始まりの遺物を獲得。")
        if wave % 10 == 0:
            self._roll_boss_weapon(wave)
            self.run.boss_devourer_units += sim.n(self.run.counts, "boss_devourer")
            self.run.assimilation_power += (
                sim.enemy_power(wave, self.config.hp_bonus_scale, self.config.midgame_relief)
                * 0.0005
                * sim.n(self.run.counts, "boss_assimilation")
            )
        tier_logs: list[int] = []
        if sim.n(self.run.counts, "critical_singularity"):
            tier_logs.append(math.floor(self.pre_snapshot.crit_chance + 1e-12))
        if sim.n(self.run.counts, "recursive_follow_up"):
            tier_logs.append(math.floor(self.pre_snapshot.follow_rate + 1e-12))
        if sim.n(self.run.counts, "infinite_barrage"):
            tier_logs.append(math.floor(max(0.0, self.pre_snapshot.attack_speed - 1.0) + 1e-12))
        if sim.n(self.run.counts, "knowledge_collapse"):
            tier_logs.append(math.floor(max(0.0, self.pre_snapshot.general_xp - 1.0) + 1e-12))
        for tier in tier_logs:
            self.run.legendary_growth_log += math.log10(1 + min(0.01, 0.002 * tier))
        if quick and had_overdrive:
            self.run.perfect_overdrive_stacks += 1
        self.run.momentum_ready = quick and had_momentum

        if wave >= self.run.next_relic_drop:
            sim.acquire_relic(self.rng, self.permanent, self.config)
            self.run.next_relic_drop = sim.next_geometric_drop(self.rng, wave)

        milestone = {25: "U", 100: "R", 500: "E"}.get(wave)
        if milestone:
            self.pending_cards.append((milestone, None))

        base_xp = 1 + (wave - 1) // 10
        boss_factor = 10 if wave % 100 == 0 else 3
        gained_xp = base_xp * (boss_factor * self.pre_snapshot.boss_xp if wave % 10 == 0 else self.pre_snapshot.general_xp)
        if quick and pre_quick_learner:
            gained_xp *= 1 + 0.30 * pre_limit_amp * pre_quick_learner
        self.run.xp += gained_xp
        while self.run.xp_level_count < len(sim.CARD_COSTS) and self.run.xp + 1e-12 >= sim.CARD_COSTS[self.run.xp_level_count]:
            self.run.xp -= sim.CARD_COSTS[self.run.xp_level_count]
            self.pending_cards.append((None, None))
            self.run.xp_level_count += 1
        self._log(f"Wave {wave}撃破。+{gained_xp:.1f} XP")
        self._continue_after_reward()

    def _roll_boss_weapon(self, wave: int) -> None:
        candidate: dict[str, Any] | None = None
        if wave == 10:
            candidate = {"power": math.log10(1.10), "rarity": "C", "originWave": wave, "fixed": True}
        elif wave >= 20:
            guaranteed = wave % 100 == 0
            chance = (0.50, 0.75, 1.0)[min(2, self.run.weapon_pity)]
            if guaranteed or self.rng.random() < chance:
                candidate = self._generate_weapon(wave, "C")
                self.run.weapon_pity = 0
            else:
                self.run.weapon_pity += 1
        if wave % 100 == 0:
            band = sim.wave_band_multiplier(wave)
            self.permanent.weapon_material += 5.0 * band
            self.permanent.relic_material += 1.0
            if wave not in self.permanent.first_big_bosses:
                self.permanent.first_big_bosses.add(wave)
                self.permanent.weapon_material += 5.0
                self.permanent.relic_material += 2.0
        if candidate:
            self.pending_weapon = candidate
            self.weapon_context = "after_wave"

    def _generate_weapon(self, wave: int, minimum: str) -> dict[str, Any]:
        distribution = sim.weapon_rarity_distribution(wave)
        allowed = [(rarity, chance) for rarity, chance in distribution if sim.RARITY_ORDER.index(rarity) >= sim.RARITY_ORDER.index(minimum)]
        total = sum(chance for _, chance in allowed)
        rarity = sim.draw_from_distribution(self.rng, tuple((key, chance / total) for key, chance in allowed))
        power = sim.weapon_base_power(wave, self.config.weapon_scale) + sim.RARITY_POWER[rarity] + self.rng.uniform(-0.10, 0.10)
        return {"power": max(0.0, power), "rarity": rarity, "originWave": wave, "fixed": False}

    def _continue_after_reward(self) -> None:
        if self.pending_weapon:
            self.mode = "weapon"
            return
        if self.pending_cards:
            forced_rarity, forced_key = self.pending_cards.popleft()
            self._open_card(forced_rarity, forced_key)
            return
        if self.run.kills >= self.target_wave:
            self.mode = "complete"
            self.fight = None
            return
        self._prepare_fight()

    def _open_card(self, forced_rarity: str | None, forced_key: str | None) -> None:
        self.mode = "card"
        self.wave = self.run.kills + 1
        self.card_forced_rarity = forced_rarity
        self.card_forced_key = forced_key
        self.card_excluded = set()
        self.card_rerolls_used = 0
        starter = forced_rarity is None and self.run.card_count < 2
        self.card_hand = sim.draw_hand(
            self.rng,
            self.run,
            self.permanent,
            self.config,
            forced_rarity,
            forced_key,
            starter_guarantee=starter,
        )

    def _select_card(self, key: str) -> None:
        starter = self.card_forced_rarity is None and self.run.card_count < 2
        selected = next((item for item in self.card_hand if item.key == key), None)
        if selected is None or (starter and selected.key not in sim.STARTER_SAFE_KEYS):
            return
        sim.record_card_decision(self.permanent, selected, self.card_rerolls_used)
        sim.acquire_card(self.run, selected, self.config)
        if self.profile == "synergy" and self.run.synergy_tag is None and selected.rarity in {"R", "E", "L"}:
            for tag in ("crit", "followup", "xp", "as", "atk", "damage"):
                if tag in selected.tags:
                    self.run.synergy_tag = tag
                    break
        self._log(f"{selected.name}を取得。")
        self.card_hand = []
        self.card_forced_rarity = None
        self._continue_after_reward()

    def _reroll(self) -> None:
        if self.card_forced_rarity is not None or self.card_rerolls_used >= self.permanent.rerolls:
            return
        self.card_excluded.update(item.key for item in self.card_hand)
        starter = self.run.card_count < 2
        self.card_hand = sim.draw_hand(
            self.rng,
            self.run,
            self.permanent,
            self.config,
            excluded=self.card_excluded,
            starter_guarantee=starter,
        )
        self.card_rerolls_used += 1
        self._log("カードをReroll。")

    def _resolve_weapon(self, equip: bool) -> None:
        assert self.pending_weapon is not None
        candidate = self.pending_weapon
        self.permanent.weapon_acquisitions += 1
        if equip:
            if self.weapon_context == "next_run":
                self.starting_weapon = candidate
            else:
                if self.run.weapon:
                    self.permanent.weapon_material += sim.MATERIAL_VALUE[self.run.weapon_rarity] * sim.wave_band_multiplier(self.run.weapon_origin_wave)
                self.run.weapon = True
                self.run.weapon_power = candidate["power"]
                self.run.weapon_rarity = candidate["rarity"]
                self.run.weapon_origin_wave = candidate["originWave"]
            self._log(f"{candidate['rarity']}武器を装備予約。Power {candidate['power']:.3f}")
        else:
            self.permanent.weapon_material += sim.MATERIAL_VALUE[candidate["rarity"]] * sim.wave_band_multiplier(candidate["originWave"])
            self._log(f"{candidate['rarity']}武器を溶解。")
        context = self.weapon_context
        self.pending_weapon = None
        if context == "next_run":
            self.mode = "death"
        else:
            self._continue_after_reward()

    def _buy_dp(self, upgrade: str) -> None:
        cost = sim.next_dp_cost(self.permanent.total_levels, self.config.dp_growth)
        if self.permanent.banked_dp < cost or upgrade not in {"atk", "attack_speed", "xp"}:
            return
        self.permanent.banked_dp -= cost
        setattr(self.permanent, upgrade, getattr(self.permanent, upgrade) + 1)
        self._log(f"DP強化：{upgrade} Lv{getattr(self.permanent, upgrade)}")

    def _forge_weapon(self) -> None:
        cost = 5.0 * sim.wave_band_multiplier(max(10, self.permanent.max_wave))
        if self.permanent.weapon_acquisitions < 5 or self.permanent.max_wave < 10 or self.permanent.weapon_material + 1e-12 < cost:
            return
        self.permanent.weapon_material -= cost
        self.permanent.weapon_generations += 1
        origin = max(10, self.permanent.max_wave - self.permanent.max_wave % 10)
        self.pending_weapon = self._generate_weapon(origin, "C")
        self.weapon_context = "next_run"
        self.mode = "weapon"
        self._log(f"武器素材{cost:.0f}で次ラン武器を生成。")

    def _forge_relic(self) -> None:
        cost = 10.0 * 2**self.permanent.relic_generations
        if self.permanent.relic_material + 1e-12 < cost:
            return
        self.permanent.relic_material -= cost
        sim.acquire_relic(self.rng, self.permanent, generated=True)
        self._log(f"遺物素材{cost:.0f}で遺物を生成。")


SESSION_LOCK = threading.Lock()
SESSION: PlaySession | None = None


class Handler(BaseHTTPRequestHandler):
    server_version = "FirstPrestigePlayable/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

    def do_OPTIONS(self) -> None:
        self._send(200, {})

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self._send(200, {"ok": True, "engine": "new_w5000_candidate / legacy_500 (separate sessions)",
                             "targetWave": 5000, "profiles": {"new_w5000_candidate": 5000, "legacy_500": TARGET_WAVE}})
            return
        if self.path == "/api/state":
            with SESSION_LOCK:
                payload = SESSION.state() if SESSION else {"status": "idle", "targetWave": 5000}
            self._send(200, payload)
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        global SESSION
        body = self._body()
        if self.path == "/api/start":
            profile = body.get("profile", "balanced")
            if profile not in PROFILE_NAMES:
                self._send(400, {"error": "invalid profile"})
                return
            seed = int(body.get("seed", sim.SEED + 1_000_000))
            with SESSION_LOCK:
                if body.get("equipmentMode"):
                    from equipment_session import EquipmentSession
                    SESSION = EquipmentSession(profile, seed)
                else:
                    SESSION = PlaySession(profile, seed)
                payload = SESSION.state()
            self._send(200, payload)
            return
        if self.path == "/api/action":
            with SESSION_LOCK:
                if not SESSION:
                    self._send(409, {"error": "session not started"})
                    return
                try:
                    SESSION.action(body)
                except (ValueError, KeyError, IndexError) as error:
                    self._send(400, {"error": str(error)})
                    return
                payload = SESSION.state()
            self._send(200, payload)
            return
        self._send(404, {"error": "not found"})


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"First prestige playable API: http://{HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
