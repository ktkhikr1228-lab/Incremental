"""Connection/regression tests; no balance Monte Carlo."""
import copy
import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "first-prestige-playtest"))
from equipment_session import EquipmentSession
from sim_server import PlaySession, sim
import new_w5000_rules as rules
from w5000_equipment_v01 import EquipmentItem


class NewW5000PlayTests(unittest.TestCase):
    def session(self):
        return EquipmentSession("balanced", 20260828)

    def test_new_pool_exact_and_legacy_unchanged(self):
        old_pool = sim.CARDS
        old = PlaySession("balanced", 21)
        session = self.session()
        self.assertEqual(len(rules.CARDS), 48)
        self.assertEqual([sum(c.rarity == r for c in rules.CARDS) for r in "CUREL"], [10, 10, 12, 8, 8])
        self.assertIs(old_pool, sim.CARDS)
        self.assertEqual(old.target_wave, 500)
        self.assertEqual(session.target_wave, 5000)
        self.assertNotIn("escalation", rules.BY_KEY)
        self.assertNotIn("infinite_barrage", rules.BY_KEY)
        self.assertEqual(sim.configured_enemy_power(5000, session.config), 308)
        self.assertFalse(session.config.defense.enabled)
        self.assertFalse(session.config.reward_skip_enabled)
        self.assertEqual(session.config.card_upgrade_cap, 1)

    def test_every_supported_card_finite_and_preview_is_pure(self):
        for item in rules.CARDS:
            if item.key in rules.DEFERRED:
                continue
            with self.subTest(card=item.key):
                s = self.session()
                s.run.kills = 750
                s.inventory.receive(EquipmentItem("w", "weapon", "剣", "R", 750, base_atk=5000))
                s.inventory.equip("w")
                rules.acquire(s.run, rules.BY_KEY["power_up"])
                s._prepare_fight()
                before = (copy.deepcopy(s.run), copy.deepcopy(s.permanent), s.rng.getstate(), s.inventory.to_dict())
                payload = s._card_payload(item)
                self.assertTrue(math.isfinite(payload["afterDpsPower"]))
                self.assertEqual(before, (s.run, s.permanent, s.rng.getstate(), s.inventory.to_dict()))
                rules.acquire(s.run, item, s.inventory.items["w"])
                self.assertTrue(math.isfinite(s._snapshot(s.run, 751).log_dps))

    def test_new_numbers_and_no_starter_restriction(self):
        s = self.session()
        before = s._snapshot(s.run, 1)
        rules.acquire(s.run, rules.BY_KEY["power_up"])
        after = s._snapshot(s.run, 1)
        self.assertAlmostEqual(after.log_dps - before.log_dps, math.log10(1.25))
        s = self.session()
        s._open_card(None, None)
        s.card_hand = [rules.BY_KEY["critical_eye"], rules.BY_KEY["critical_power"], rules.BY_KEY["experience"]]
        self.assertFalse(s.state()["starterGuarantee"])
        self.assertTrue(all(c["eligible"] for c in s.state()["options"]))
        s.action(dict(type="select_card", cardKey="experience"))
        self.assertEqual(s.run.counts["experience"], 1)
        self.assertAlmostEqual(s._snapshot(s.run, 1).general_xp, 1.2)

    def test_dp_bc_per_item_cost_no_old_milestones(self):
        s = self.session()
        s.mode = "death"
        s.dp_state.balance = 10000
        self.assertEqual(rules.dp.next_cost(s.dp_state, "base_atk"), 8)
        s.action(dict(type="buy_dp", upgrade="base_atk"))
        self.assertEqual(s.dp_state.balance, 9992)
        self.assertEqual(rules.dp.next_cost(s.dp_state, "base_atk"), 9)
        self.assertEqual(rules.dp.next_cost(s.dp_state, "xp_gain"), 8)
        self.assertAlmostEqual(10 ** s._snapshot(s.run, 1).base_attack_power, 1.28)
        before = s._snapshot(s.run, 1)
        s.permanent.atk, s.permanent.attack_speed, s.permanent.xp = 60, 60, 30
        s.permanent.relic_quality = 99
        s.run.weapon = True
        s.run.weapon_power = 123
        self.assertEqual(before, s._snapshot(s.run, 1))
        with self.assertRaises(ValueError):
            s.action(dict(type="buy_dp", upgrade="crit_rate"))

    def test_new_death_once_retains_dp_and_relic_retry_clears_cards(self):
        s = self.session()
        s.run.kills = 100
        s.permanent.max_wave = 100
        rules.acquire(s.run, rules.BY_KEY["power_up"])
        s.inventory.receive(EquipmentItem("lens", "relic", "学習レンズ", "C", 100, unique_key="learning_lens"))
        s.inventory.equip("lens")
        s._prepare_fight()
        s.fight["timeToKill"] = None
        s.action(dict(type="resolve"))
        # Economy B: death 9+floor(100/11), records 4*3, Big Boss 1*3.
        self.assertEqual(s.dp_state.balance, 33)
        self.assertEqual(s.mode, "death")
        before = (copy.deepcopy(s.dp_state), s.run.combat_seconds, s.inventory.to_dict())
        s.action(dict(type="resolve"))
        self.assertEqual(before, (s.dp_state, s.run.combat_seconds, s.inventory.to_dict()))
        s.action(dict(type="buy_dp", upgrade="crit_rate"))
        self.assertEqual(s.dp_state.levels["crit_rate"], 1)
        balance = s.dp_state.balance
        s.action(dict(type="retry"))
        self.assertEqual(s.dp_state.balance, balance)
        self.assertEqual(s.run.card_count, 0)
        self.assertFalse(s.run.counts)
        self.assertEqual(s.inventory.relic_slots[0], "lens")

    def test_same_wall_pays_death_dp_without_record_again(self):
        s = self.session()
        for expected in (33, 54):
            s.run.kills = 100
            s.permanent.max_wave = 100
            s._prepare_fight()
            s.fight["timeToKill"] = None
            s.action(dict(type="resolve"))
            self.assertEqual(s.dp_state.balance, expected)
            s.action(dict(type="retry"))

    def test_new_death_preparation_failure_is_atomic(self):
        s = self.session()
        s.fight["timeToKill"] = None
        before = (copy.deepcopy(s.dp_state), copy.deepcopy(s.run), s.inventory.to_dict(), s.mode)
        def fail(state, reached):
            state.balance += 999
            raise ValueError("injected DP failure")
        with patch.object(rules.dp, "award_dp_after_death", side_effect=fail):
            with self.assertRaises(ValueError):
                s.action(dict(type="resolve"))
        self.assertEqual(before, (s.dp_state, s.run, s.inventory.to_dict(), s.mode))

    def test_high_as_small_required_time_uses_relative_tolerance(self):
        s = self.session()
        snap = __import__('dataclasses').replace(s._snapshot(s.run, 1), log_dps=13, attack_speed=1e15)
        time = rules.time_to_kill(math.log10(2), 10, snap)
        self.assertAlmostEqual(time / 1e-15, 200, places=5)

    def test_reroll_is_per_run_and_epic_gate_does_not_leak(self):
        s = self.session()
        s._open_card(None, None)
        s.action(dict(type="reroll"))
        self.assertEqual(s.state()["rerollsLeft"], 0)
        s._open_card(None, None)
        with self.assertRaises(ValueError):
            s.action(dict(type="reroll"))
        s.permanent.max_wave = 2500
        s._new_run()
        self.assertEqual(s.run_rerolls_used, 0)
        self.assertNotIn("E", dict(rules.epic.rarity_chances_for_wave(s.run.kills)))

    def test_unique_exclusion_and_crit_exclusion(self):
        s = self.session()
        rules.acquire(s.run, rules.BY_KEY["multi_crit"])
        keys = {item.key for item in rules.legal_cards(s.run)}
        self.assertNotIn("multi_crit", keys)
        self.assertNotIn("critical_compression", keys)
        self.assertNotIn("relic_apotheosis", keys)
        rules.acquire(s.run, rules.BY_KEY["critical_singularity"])
        self.assertNotIn("critical_overload", {item.key for item in rules.legal_cards(s.run)})

    def test_follow_echo_keeps_dormant_double_strike_and_recursive_caps_are_not_rates(self):
        s = self.session()
        rules.acquire(s.run, rules.BY_KEY["double_strike"])
        self.assertEqual(s._snapshot(s.run, 1).follow_rate, 0)
        rules.acquire(s.run, rules.BY_KEY["follow_up_echo"])
        self.assertAlmostEqual(s._snapshot(s.run, 1).follow_rate, .25)
        self.assertAlmostEqual(rules.values(s.run, s.permanent, s.inventory, False)["follow_damage"], .75)
        for key, expected in (("recursive_follow_up", 1 + .5 * .1 / .9), ("endless_action", 1 / .85)):
            s = self.session()
            before = s._snapshot(s.run, 1).log_dps
            rules.acquire(s.run, rules.BY_KEY[key])
            self.assertAlmostEqual(10 ** (s._snapshot(s.run, 1).log_dps - before), expected)

    def test_hp_display_failure_does_not_show_zero_and_salvage(self):
        s = self.session()
        snap = __import__('dataclasses').replace(s._snapshot(s.run, 1), log_dps=0, attack_speed=1)
        self.assertAlmostEqual(rules.remaining_hp(math.log10(20), 10, snap, 10), .5)
        s._prepare_fight()
        self.assertEqual(len(s.fight["hpSamples"]), 101)
        self.assertAlmostEqual(s.fight["hpSamples"][0]["remaining"], 1)
        rules.acquire(s.run, rules.BY_KEY["salvager"])
        s.inventory.receive(EquipmentItem("w", "weapon", "剣", "C", 10, base_atk=1))
        s.mode = "card"
        s.action(dict(type="gear_dismantle", uid="w"))
        self.assertAlmostEqual(s.inventory.materials["weapon"], 1.15)

    def test_weapon_reference_initial_guarantee_and_training(self):
        s = self.session()
        s.run.kills = 10
        s._roll_boss_weapon(10)
        self.assertEqual(s.pending_equipment, [])
        item = next(iter(s.inventory.items.values()))
        self.assertEqual((item.rarity, item.base_atk, item.quality), ("C", 1, 1))
        s.inventory.equip(item.uid)
        self.assertAlmostEqual(10 ** s._snapshot(s.run, 11).base_attack_power, 2.1)
        rules.acquire(s.run, rules.BY_KEY["weapon_training"])
        self.assertAlmostEqual(10 ** s._snapshot(s.run, 11).base_attack_power, 2.375)
        self.assertAlmostEqual(rules.weapon_reference(500), 500)
        self.assertEqual(rules.weapon_reference(5000), 5e7)

    def test_execution_discrete_timeout_and_time_collapse(self):
        s = self.session()
        snapshot = s._snapshot(s.run, 1)
        snapshot = __import__('dataclasses').replace(snapshot, log_dps=math.log10(2.4), attack_speed=2.4, execution_mult=2.5)
        # 21 initial full-damage attacks and 4 finishing attacks = 25;
        # the 10 second limit allows only 24.
        self.assertIsNone(rules.time_to_kill(math.log10(29), 10, snapshot))
        self.assertIsNotNone(rules.time_to_kill(math.log10(29), 11, snapshot))
        no_collapse = __import__('dataclasses').replace(snapshot, log_dps=0, attack_speed=1, execution_mult=1)
        collapse = __import__('dataclasses').replace(no_collapse, time_collapse=True)
        self.assertIsNone(rules.time_to_kill(math.log10(20), 10, no_collapse))
        self.assertIsNotNone(rules.time_to_kill(math.log10(20), 10, collapse))

    def test_synthetic_checkpoint_and_early_loop_smoke(self):
        s = self.session()
        for wave, rarity in ((25, "U"), (100, "R"), (500, "E")):
            s.run.kills = wave - 1
            s._prepare_fight()
            s.fight["timeToKill"] = 1
            s.action(dict(type="resolve"))
            while s.mode == "equipment":
                s.action(dict(type="gear_discard")) if s.pending_equipment else s.action(dict(type="gear_done"))
            self.assertEqual(s.mode, "combat")
            s.action(dict(type="open_cards"))
            self.assertTrue(all(item.rarity == rarity for item in s.card_hand))
            s.pending_cards.clear()
            s.card_hand.clear()
        s = self.session()
        for _ in range(60):
            if s.mode == "combat":
                s.action(dict(type="resolve"))
            elif s.mode == "card":
                s.action(dict(type="select_card", cardKey=s.card_hand[0].key))
            elif s.mode == "equipment":
                s.action(dict(type="gear_discard")) if s.pending_equipment else s.action(dict(type="gear_done"))
            elif s.mode == "death":
                break
        self.assertIn(s.mode, ("combat", "card", "equipment", "death"))
        self.assertTrue(math.isfinite(s._snapshot(s.run, s.wave).log_dps))


if __name__ == "__main__":
    unittest.main()
