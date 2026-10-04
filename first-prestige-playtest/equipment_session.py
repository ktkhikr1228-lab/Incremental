"""New W5000 candidate equipment UI adapter.

No monkeypatches. Formal/D/E and default PlaySession are unaffected.
"""
from dataclasses import asdict
import copy
import math
import new_w5000_rules as rules
from live_encounter import project
from new_w5000_session import NewW5000Session
from w5000_equipment_v01 import EquipmentInventory, EquipmentItem, WEAPON_DISMANTLE, RELIC_DISMANTLE


class EquipmentSession(NewW5000Session):
    def __init__(self, profile, seed):
        self.inventory = EquipmentInventory()
        self.next_uid = 0
        self.claimed_relic_waves = set()
        self.pending_equipment = []
        super().__init__(profile, seed)

    def _uid(self):
        self.next_uid += 1
        return f"equipment-{self.next_uid}"

    def _new_run(self):
        self.encounter_start = 0.0
        self.encounter_remaining = 1.0
        self.encounter_phase = 0.0
        super()._new_run()
        self.run.next_relic_drop = 10**20

    def _snapshot(self, run, wave):
        return super()._snapshot(run, wave)

    def _roll_boss_weapon(self, wave):
        return super()._roll_boss_weapon(wave)

    def _resolve_fight(self):
        if self.mode != "combat":
            return
        dead = self.fight["timeToKill"] is None
        unprocessed = list(self.pending_equipment) if dead else []
        super()._resolve_fight()
        self.permanent.relic_unlocked = False
        if dead:
            self.pending_cards.clear()
            self.card_hand.clear()
            self.card_forced_rarity = None
            self.echo_draft = False
            before = self.inventory.materials["weapon"]
            self.inventory.on_death()
            self.inventory.materials["weapon"] += sum(WEAPON_DISMANTLE[c.rarity] / 2 for c in unprocessed if c.kind == "weapon")
            self.pending_equipment.extend(c for c in unprocessed if c.kind == "relic")
            self.inventory.materials["weapon"] += (self.inventory.materials["weapon"] - before) * (self._salvage_multiplier() - 1)
            return

    def _prepare_fight(self):
        self.encounter_start = 0.0
        self.encounter_remaining = 1.0
        self.encounter_phase = 0.0
        super()._prepare_fight()
        self.fight["id"] = f"{self.attempt}:{self.wave}"
        self.fight["elapsed"] = 0.0

    def _refresh_encounter(self):
        if self.mode != "combat":
            return
        snap = self._snapshot(self.run, self.wave)
        self.pre_snapshot = snap
        self.fight.update(dpsPower=snap.log_dps, dps=__import__('sim_server').magnitude(snap.log_dps),
            attackSpeed=snap.attack_speed, critChance=snap.crit_chance,
            critMultiplier=snap.crit_multiplier, xpGain=snap.general_xp)
        ttk, hp = project(self.fight["enemyPower"], self.fight["timeLimit"], snap,
            self.encounter_start, self.encounter_remaining, self.encounter_phase)
        self.fight.update(timeToKill=ttk, willWin=ttk is not None, elapsed=self.encounter_start,
            hpSamples=[dict(time=self.encounter_start + (self.fight["timeLimit"] - self.encounter_start) * i / 100,
                remaining=hp(self.encounter_start + (self.fight["timeLimit"] - self.encounter_start) * i / 100)) for i in range(101)])

    def _capture_elapsed(self, body):
        if self.mode != "combat":
            return
        elapsed = float(body.get("elapsed", self.encounter_start))
        duration = self.fight["timeToKill"] if self.fight["willWin"] else self.fight["timeLimit"]
        if not math.isfinite(elapsed) or elapsed < self.encounter_start - 1e-9 or elapsed > duration + 1e-9:
            raise ValueError("Invalid encounter elapsed time")
        if elapsed >= duration:
            self._resolve_fight()
            return
        _, hp = project(self.fight["enemyPower"], self.fight["timeLimit"], self.pre_snapshot,
            self.encounter_start, self.encounter_remaining, self.encounter_phase)
        self.encounter_remaining = hp(elapsed)
        self.encounter_phase = (self.encounter_phase + (elapsed - self.encounter_start) * self.pre_snapshot.attack_speed) % 1
        self.encounter_start = elapsed

    def _open_card(self, forced_rarity, forced_key):
        # Drawing is lazy (open_cards), never blocks combat. Hand survives closing.
        self.card_forced_rarity, self.card_forced_key = forced_rarity, forced_key
        self.card_excluded = set()
        self.echo_draft = forced_rarity is None and bool(self.run.counts.get("knowledge_collapse"))
        self.card_hand = rules.draw_hand(self.rng, self.run, self.dp_state, forced_rarity, echo=self.echo_draft)

    def _ensure_hand(self):
        while not self.card_hand and self.pending_cards and self.mode == "combat":
            self._open_card(*self.pending_cards.popleft())
            if not self.card_hand:
                self._log("Echo可能なカードなし。この選択権を消費。")

    def _select_card(self, key):
        card = next((c for c in self.card_hand if c.key == key), None)
        if card is None or not self._card_payload(card)["eligible"]:
            raise ValueError("現在の合法候補から選択してください")
        rules.acquire(self.run, card, self.inventory.items.get(self.inventory.weapon_slot))
        self.card_hand.clear()
        self.card_forced_rarity = None
        self.echo_draft = False
        self._log(f"{card.name}を取得。")
        self._ensure_hand()

    def _salvage_multiplier(self):
        from new_w5000_rules import epic
        c, u, _ = epic.amps(self.run.counts)
        return 1 + .15 * c * self.run.counts.get("salvager", 0) + .20 * u * self.run.counts.get("salvage_expert", 0)
    def _continue_after_reward(self):
        self.permanent.relic_unlocked = False
        wave = self.run.kills
        if wave == 100 and wave not in self.claimed_relic_waves:
            self.claimed_relic_waves.add(wave)
            self.pending_equipment.append(EquipmentItem(
                self._uid(), "relic", "学習レンズ", "C", wave, unique_key="learning_lens"))
            self._log("Common 学習レンズを獲得候補へ追加。旧遺物効果は無効です。")
        if self.run.kills >= self.target_wave:
            self.mode = "complete"
            self.fight = None
        else:
            self._prepare_fight()

    def state(self):
        state = super().state()
        state.update(equipmentMode=True, equipment=self.inventory.to_dict(),
                     pendingEquipment=asdict(self.pending_equipment[0]) if self.pending_equipment else None,
                     candidateNotice="新W5000候補：新C/U/R/E/Lカード・DP v0.1 BC・個体Drop武器。Relic Apotheosis、全遺物報酬、武器固有、Core/UB/Finale、保存/拡張は未接続。旧W10000版とは別系統、12h調整は未完了。")
        state["canForgeWeapon"] = state["canForgeRelic"] = False
        state["equipmentDismantleMultiplier"] = self._salvage_multiplier()
        options = [self._card_payload(c) for c in self.card_hand]
        state.update(nonBlocking=True, options=options,
            cardDrafts=len(self.pending_cards) + int(bool(self.card_hand)),
            pendingEquipmentList=[asdict(c) for c in self.pending_equipment],
            rerollsLeft=max(0, 1 + int(self.dp_state.reroll_bought) - self.run_rerolls_used)
                if self.card_hand and self.card_forced_rarity is None else 0,
            recommendedCard=max(options, key=lambda c: c["score"])["key"] if options else None)
        return state

    def action(self, body):
        # Stale resolve/edit from another fight cannot mutate a new enemy.
        if body.get("fightId") is not None and (not self.fight or body["fightId"] != self.fight["id"]):
            return
        before = copy.deepcopy(self.__dict__)
        try:
            self._action(body)
        except Exception:
            self.__dict__.clear()
            self.__dict__.update(before)
            raise

    def _action(self, body):
        action = body.get("type")
        uid = str(body.get("uid", ""))
        if action in {"open_cards", "select_card", "reroll"}:
            if self.mode != "combat":
                return
            fight_id = self.fight["id"]
            self._capture_elapsed(body)
            if self.mode != "combat" or self.fight["id"] != fight_id:
                return
            if action == "open_cards":
                self._ensure_hand()
            elif action == "select_card":
                self._select_card(str(body.get("cardKey", "")))
            else:
                if not self.card_hand:
                    raise ValueError("選択中の手札なし")
                self._reroll()
            self._refresh_encounter()
            return
        gear_actions = {"gear_equip", "gear_unequip", "gear_enhance", "gear_dismantle", "gear_absorb", "gear_replace", "gear_receive", "gear_discard", "gear_done"}
        if action not in gear_actions:
            if action in {"forge_weapon", "forge_relic"}:
                raise ValueError("初版では生成は延期")
            return super().action(body)
        if self.mode == "combat":
            fight_id = self.fight["id"]
            self._capture_elapsed(body)
            if self.mode != "combat" or self.fight["id"] != fight_id:
                return
        if action == "gear_done":
            return
        if action in {"gear_receive", "gear_discard"}:
            if not self.pending_equipment:
                raise ValueError("取得候補なし")
            item = next((c for c in self.pending_equipment if c.uid == uid), None) if uid else self.pending_equipment[0]
            if item is None:
                raise ValueError("取得候補なし")
            if action == "gear_discard":
                table = WEAPON_DISMANTLE if item.kind == "weapon" else RELIC_DISMANTLE
                self.inventory.materials[item.kind] += table[item.rarity] * (self._salvage_multiplier() if item.kind == "weapon" else 1) + item.enhancement_spent // 2
            else:
                if body.get("equip"):
                    # Equip directly even at full storage if a slot is empty.
                    slot = int(body.get("slot", 0))
                    if item.kind == "relic" and slot not in range(3):
                        raise ValueError("Invalid relic slot")
                    occupied = self.inventory.weapon_slot if item.kind == "weapon" else self.inventory.relic_slots[slot]
                    if occupied and len(self.inventory.stored_ids(item.kind)) >= self.inventory.storage_capacity[item.kind]:
                        raise ValueError("保管満杯：先に不要品を分解してください")
                    item.validate()
                    self.inventory.items[item.uid] = item
                    self.inventory.equip(item.uid, slot)
                else:
                    self.inventory.receive(item)
            self.pending_equipment.remove(item)
        elif action == "gear_equip":
            self.inventory.equip(uid, int(body.get("slot", 0)))
        elif action == "gear_unequip":
            self.inventory.unequip(uid)
        elif action == "gear_enhance":
            self.inventory.enhance(uid)
        elif action == "gear_dismantle":
            item = self.inventory.items[uid]
            bonus = WEAPON_DISMANTLE[item.rarity] * (self._salvage_multiplier() - 1) if item.kind == "weapon" else 0
            self.inventory.dismantle(uid)
            self.inventory.materials[item.kind] += bonus
        elif action == "gear_absorb":
            self.inventory.absorb_duplicate(uid, str(body.get("otherUid", "")))
        elif action == "gear_replace":
            self.inventory.replace_relic(uid, str(body.get("otherUid", "")))
        self.run.effect_version += 1
        self.inventory.validate()
        self._refresh_encounter()
