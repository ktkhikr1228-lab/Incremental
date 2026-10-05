"""Manual playable new-W5000 candidate. Legacy PlaySession remains separate."""
import collections
import copy
import math
from dataclasses import asdict

from sim_server import PlaySession, sim, magnitude
import new_w5000_rules as rules
import w5000_v1_profile
from w5000_equipment_v01 import EquipmentItem


class NewW5000Session(PlaySession):
    def __init__(self, profile, seed):
        self.dp_state = rules.dp.NewDPState(rules.acquisition.bc_candidate())
        self.w10_claimed = False
        self.run_rerolls_used = 0
        self.echo_draft = False
        super().__init__(profile, seed)

    def _new_run(self):
        self.config = w5000_v1_profile.build_config(guaranteed_legendary=False)
        self.target_wave = 5000
        self.permanent._new_dp_state = self.dp_state
        self.attempt += 1
        self.run = sim.RunState()
        self.run.next_relic_drop = 10**20
        self.run_rerolls_used = 0
        self.echo_draft = False
        self.recovery_pending = self.attempt > 1
        self.weapon_pity = 0
        self.wave = 1
        self.last_death = None
        self.pending_cards.clear()
        self.card_hand = []
        self.pending_weapon = None
        self._log(f"新W5000候補 Run {self.attempt}開始。カード・武器はリセット、DP・遺物は保持。")
        self._prepare_fight()

    def _snapshot(self, run, wave):
        return rules.snapshot(run, self.permanent, self.inventory, wave % 10 == 0)

    def _prepare_fight(self):
        self.mode = "combat"
        self.wave = self.run.kills + 1
        snap = self._snapshot(self.run, self.wave)
        power = sim.configured_enemy_power(self.wave, self.config)
        limit = 15 if self.wave % 10 == 0 else 10
        ttk = rules.time_to_kill(power, limit, snap)
        self.pre_snapshot = snap
        self.fight = dict(wave=self.wave, boss=self.wave % 10 == 0,
            enemyPower=power, hpPower=power, enemyHp=magnitude(power),
            defensePower=0, armorBreakEnabled=False, dpsPower=snap.log_dps,
            dps=magnitude(snap.log_dps), attackSpeed=snap.attack_speed,
            critChance=snap.crit_chance, critMultiplier=snap.crit_multiplier,
            xpGain=snap.general_xp, baseAttack=magnitude(snap.base_attack_power),
            followRate=snap.follow_rate, timeLimit=limit, timeToKill=ttk, willWin=ttk is not None)
        self.fight["hpSamples"] = [dict(time=limit * i / 100,
            remaining=rules.remaining_hp(power, limit, snap, limit * i / 100)) for i in range(101)]

    def _run_payload(self):
        return dict(attempt=self.attempt, kills=self.run.kills,
            combatSeconds=self.run.combat_seconds,
            totalCombatSeconds=self.total_combat_seconds + self.run.combat_seconds,
            xp=self.run.xp, nextCardCost=(sim.CARD_COSTS[self.run.xp_level_count]
                if self.run.xp_level_count < len(sim.CARD_COSTS) else None),
            cardCount=self.run.card_count,
            cards=[dict(key=key, name=rules.BY_KEY[key].name, rarity=rules.BY_KEY[key].rarity,
                        count=count, description=rules.DESCRIPTIONS[key])
                   for key, count in self.run.counts.items() if count > 0 and key in rules.BY_KEY],
            weapon=None, cardPoints=0)

    def _permanent_payload(self):
        result = super()._permanent_payload()
        state = self.dp_state
        labels = {"base_atk": "Base ATK", "attack_speed": "Attack Speed", "xp_gain": "XP Gain",
                  "crit_rate": "Crit Rate", "crit_multiplier": "Crit Multiplier",
                  "weapon_atk": "Weapon ATK", "luck": "Luck", "weapon_find": "Weapon Find",
                  "weapon_quality": "Weapon Quality"}
        effects = {"base_atk": "+28% / Lv", "attack_speed": "+22% / Lv", "xp_gain": "+14% / Lv",
                   "crit_rate": "+5.5pt / Lv", "crit_multiplier": "+0.140 / Lv", "weapon_atk": "+28% / Lv",
                   "luck": "rarity weight強化（段階減衰）", "weapon_find": "Drop率強化（段階減衰）",
                   "weapon_quality": "最低roll改善（上限roll不変）"}
        result.update(bankedDp=state.balance, totalDp=state.total_earned,
            levels=dict(atk=state.levels["base_atk"], attackSpeed=state.levels["attack_speed"],
                        xp=state.levels["xp_gain"], total=sum(state.levels.values())),
            nextDpCost=rules.dp.next_cost(state, "base_atk"),
            weaponMaterial=self.inventory.materials["weapon"], relicMaterial=self.inventory.materials["relic"],
            dpVersion="v0.1 BC candidate", dpSpent=state.total_spent,
            dpUpgrades=[dict(key=key, label=labels[key], level=state.levels[key], effect=effects[key],
                cost=rules.dp.next_cost(state, key), unlocked=key in state.unlocked_achievements,
                unlockWave=rules.dp.UNLOCK_WAVES[key]) for key in rules.dp.ITEM_ORDER],
            rerollUpgrade=dict(bought=state.reroll_bought, unlocked=self.permanent.max_wave >= 400,
                cost=state.candidate.reroll_cost))
        return result

    def _card_payload(self, item):
        before = self._snapshot(self.run, self.wave)
        candidate = copy.deepcopy(self.run)
        rules.acquire(candidate, item, self.inventory.items.get(self.inventory.weapon_slot))
        after = self._snapshot(candidate, self.wave)
        delta = after.log_dps - before.log_dps
        limit = 15 if self.wave % 10 == 0 else 10
        return dict(key=item.key, name=item.name, rarity=item.rarity,
            description=rules.DESCRIPTIONS[item.key], tags=sorted(item.tags),
            eligible=item in rules.legal_cards(self.run) or (self.echo_draft and not item.unique and self.run.counts.get(item.key, 0) > 0),
            score=delta, immediateMultiplier=10**delta if -20 < delta < 20 else None,
            afterDpsPower=after.log_dps, nextTtk=rules.time_to_kill(sim.configured_enemy_power(self.wave, self.config), limit, after),
            nextTimeLimit=limit)

    def _open_card(self, forced_rarity, forced_key):
        self.mode = "card"
        self.wave = self.run.kills + 1
        self.card_forced_rarity = forced_rarity
        self.card_forced_key = forced_key
        self.card_excluded = set()
        self.card_rerolls_used = 0
        self.echo_draft = forced_rarity is None and bool(self.run.counts.get("knowledge_collapse"))
        self.card_hand = rules.draw_hand(self.rng, self.run, self.dp_state, forced_rarity, echo=self.echo_draft)
        if not self.card_hand:
            # Collapse with no owned stackable card consumes the level-up, not
            # an infinite empty selection screen.
            self._log("Echo可能なカードなし。このLevel UpのEchoは発生しません。")
            self._continue_after_reward()

    def _select_card(self, key):
        selected = next((item for item in self.card_hand if item.key == key), None)
        if selected is None or not self._card_payload(selected)["eligible"]:
            raise ValueError("現在の合法候補から選択してください")
        rules.acquire(self.run, selected, self.inventory.items.get(self.inventory.weapon_slot))
        self.card_hand = []
        self.card_forced_rarity = None
        self.echo_draft = False
        self._log(f"{selected.name}を取得。")
        self._continue_after_reward()

    def _reroll(self):
        if self.card_forced_rarity or self.run_rerolls_used >= 1 + int(self.dp_state.reroll_bought):
            raise ValueError("このRunのRerollを使い切っています")
        excluded = self.card_excluded | {item.key for item in self.card_hand}
        hand = rules.draw_hand(self.rng, self.run, self.dp_state, excluded=excluded, echo=self.echo_draft)
        if not hand:
            raise ValueError("Reroll可能な別候補なし")
        self.card_excluded = excluded
        self.card_hand = hand
        self.run_rerolls_used += 1
        self._log("Rerollを1回消費（Run内共通）。")

    def _buy_dp(self, key):
        key = {"atk": "base_atk", "xp": "xp_gain"}.get(key, key)
        state = self.dp_state
        if key == "reroll":
            if self.permanent.max_wave < 400 or state.reroll_bought:
                raise ValueError("Reroll購入はW400解禁・転生内1回")
            cost = state.candidate.reroll_cost
        else:
            if key not in state.unlocked_achievements:
                raise ValueError("未解禁のDP項目です")
            cost = rules.dp.next_cost(state, key)
        if state.balance < cost:
            raise ValueError("DP不足")
        state.balance -= cost
        state.total_spent += cost
        if key == "reroll":
            state.reroll_bought = True
        else:
            state.levels[key] += 1
        self.permanent.banked_dp = state.balance
        self._log(f"{key}を強化。−{cost} DP")

    def _drop_weapon(self, wave, boss):
        fixed = wave == 10 and not self.w10_claimed
        guarantee = boss and self.recovery_pending
        bonus = min(.15 if boss else .02, self.weapon_pity * (.002 if boss else .0005))
        chance = min(1.0, ((.10 if boss else .01) + bonus) * rules.dp.weapon_find_multiplier(self.dp_state))
        if not (fixed or guarantee or self.rng.random() < chance):
            self.weapon_pity += 10 if boss else 1
            return
        self.weapon_pity = 0
        self.recovery_pending = False
        if fixed:
            self.w10_claimed = True
            rarity, base, quality, affixes = "C", 1.0, 1.0, {}
        else:
            weights = [(key, value * rules.dp.luck_rarity_weight_multiplier(self.dp_state, key))
                       for key, value in rules.acquisition.rarity_table(wave)]
            rarity = self.rng.choices([key for key, _ in weights], [value for _, value in weights])[0]
            reference = rules.weapon_reference(wave)
            low, high = rules.acquisition.ROLL_RANGES[rarity]
            quality = self.rng.uniform(low, high)
            quality += (high - quality) * rules.dp.weapon_quality_floor_progress(self.dp_state)
            base = reference * rules.acquisition.RARITY_MULT[rarity]
            affixes = rules.acquisition.roll_affixes(self.rng, rarity, reference)
            # Quality moves each ordinary affix minimum toward its unchanged
            # maximum, as in DP v0.1; it is not an extra max-roll multiplier.
            progress = rules.dp.weapon_quality_floor_progress(self.dp_state)
            tier = {"C": .70, "U": .85, "R": 1, "E": 1.15, "L": 1.30}[rarity]
            maxima = dict(weapon_atk_additive=reference * .15, weapon_atk_pct=.12,
                base_atk_pct=.12, attack_speed_pct=.10, crit_rate=.08,
                crit_multiplier=.20, all_damage_pct=.12)
            affixes = {key: value + (maxima[key] * tier - value) * progress
                       for key, value in affixes.items()}
        self.pending_equipment.append(EquipmentItem(self._uid(), "weapon", "剣", rarity, wave,
            base_atk=base, quality=quality, affixes=affixes))
        self.permanent.weapon_acquisitions += 1

    def _roll_boss_weapon(self, wave):
        self._drop_weapon(wave, True)

    def _resolve_fight(self):
        if self.mode != "combat":
            return
        ttk = self.fight["timeToKill"]
        if ttk is None:
            next_dp = copy.deepcopy(self.dp_state)
            earned = rules.dp.award_dp_after_death(next_dp, self.run.kills)
            rules.dp.unlock_for_wave(next_dp, self.permanent.max_wave)
            self.dp_state = next_dp
            self.permanent._new_dp_state = next_dp
            self.permanent.banked_dp = next_dp.balance
            self.total_dp = next_dp.total_earned
            self.run.combat_seconds += self.fight["timeLimit"]
            self.last_death = dict(failureWave=self.wave, reached=self.run.kills,
                gainedDp=earned["total"], runCombatSeconds=self.run.combat_seconds)
            self.pending_equipment.clear()
            self.mode = "death"
            self._log(f"Wave {self.wave}時間切れ。+{earned['total']} DP（旧totalLv倍率なし）")
            return
        wave = self.wave
        snap = self.pre_snapshot
        self.run.combat_seconds += ttk
        self.run.kills = wave
        self.permanent.max_wave = max(self.permanent.max_wave, wave)
        rules.dp.unlock_for_wave(self.dp_state, self.permanent.max_wave)
        if wave % 10 == 0:
            self._roll_boss_weapon(wave)
            self.run.boss_devourer_units += int(bool(self.run.counts.get("boss_devourer")))
        else:
            self._drop_weapon(wave, False)
        milestone = {25: "U", 100: "R", 500: "E"}.get(wave)
        if milestone:
            self.pending_cards.append((milestone, None))
        xp = (1 + (wave - 1) // 10) * ((10 if wave % 100 == 0 else 3) * snap.boss_xp if wave % 10 == 0 else snap.general_xp)
        if ttk <= 3 + 1e-12:
            xp *= 1 + .30 * rules.epic.amps(self.run.counts)[1] * self.run.counts.get("quick_learner", 0)
        self.run.xp += xp
        while self.run.xp_level_count < len(sim.CARD_COSTS) and self.run.xp + 1e-12 >= sim.CARD_COSTS[self.run.xp_level_count]:
            self.run.xp -= sim.CARD_COSTS[self.run.xp_level_count]
            self.run.xp_level_count += 1
            self.pending_cards.append((None, None))
        self._log(f"Wave {wave}撃破。+{xp:.1f} XP")
        self._continue_after_reward()

    def state(self):
        result = super().state()
        snap = self._snapshot(self.run, self.wave)
        values = rules.values(self.run, self.permanent, self.inventory, self.wave % 10 == 0)
        base = snap.base_attack_power
        speed = math.log10(snap.attack_speed)
        damage = math.log10(snap.all_damage)
        result['damageDetails'] = dict(
            totalPower=snap.log_dps,
            rows=[dict(label='基礎攻撃力（武器・DP込み）', power=base),
                  dict(label='攻撃速度', power=speed),
                  dict(label='All Damage', power=damage),
                  dict(label='Crit・Hit・追撃・再行動・Boss等（合算）', power=snap.log_dps-base-speed-damage)],
            rawBase=values['raw_base'], effectiveWeapon=values['effective_weapon'],
            allDamage=snap.all_damage, followDamage=values['follow_damage'],
            multiTier=snap.multi_crit_tier,
            firstStrike=snap.first_strike_mult, lastStand=snap.last_stand_mult,
            execution=snap.execution_mult, timeCollapse=snap.time_collapse,
            dpDelta=snap.dp_power, weaponDelta=snap.weapon_power)
        result.update(starterGuarantee=False,
            rerollsLeft=max(0, 1 + int(self.dp_state.reroll_bought) - self.run_rerolls_used)
                if self.mode == "card" and self.card_forced_rarity is None else 0,
            series="new_w5000_candidate", echoDraft=self.echo_draft,
            player=dict(baseAttack=magnitude(snap.base_attack_power), attackSpeed=snap.attack_speed,
                critChance=snap.crit_chance, critMultiplier=snap.crit_multiplier,
                followRate=snap.follow_rate, xpGain=snap.general_xp,
                hitCount=values["hit_count"], supplemental=values["supplemental"],
                reActionRate=values["reaction_rate"], effectiveWeaponAtk=values["effective_weapon"]))
        return result

    def _notice(self):
        if self.mode == "card":
            return "所持カードをEcho取得してください。" if self.echo_draft else "新W5000カードから1枚選択。初期カードの選択禁止はありません。"
        if self.mode == "complete":
            return "Wave5000撃破。候補版の第一転生到達（転生後システムは未実装）。"
        return super()._notice()
