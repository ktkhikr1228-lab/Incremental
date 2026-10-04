"""Small state-machine tests, not balance simulations."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'first-prestige-playtest'))
from sim_server import PlaySession, sim
from equipment_session import EquipmentSession
from w5000_equipment_v01 import EquipmentItem


class EquipmentPlaySessionTests(unittest.TestCase):
    def test_legacy_defaults_unchanged(self):
        session = PlaySession('balanced', 20260828)
        self.assertEqual(session.target_wave, 500)
        self.assertNotIn('equipment', session.state())
        self.assertEqual(session.fight['enemyPower'], sim.enemy_power(1, session.config.hp_bonus_scale, session.config.midgame_relief))

    def test_pending_receive_equip_and_resume(self):
        session = EquipmentSession('balanced', 20260828)
        session.run.kills = 10
        session._roll_boss_weapon(10)
        session._continue_after_reward()
        self.assertEqual(session.mode, 'combat')
        session.action({'type': 'gear_receive'})
        uid = next(iter(session.inventory.items))
        before = session._snapshot(session.run, 11)
        session.action({'type': 'gear_equip', 'uid': uid})
        after = session._snapshot(session.run, 11)
        self.assertAlmostEqual(after.log_dps - before.log_dps, __import__('math').log10(2.1))
        session.action({'type': 'gear_done'})
        self.assertEqual(session.mode, 'combat')
        self.assertEqual(session.wave, 11)
        session.action({'type': 'gear_unequip', 'uid': uid})
        self.assertIsNone(session.inventory.weapon_slot)

    def test_relic_once_and_xp_effect(self):
        session = EquipmentSession('balanced', 21)
        session.run.kills = 100
        session._continue_after_reward()
        session.action({'type': 'gear_receive'})
        uid = next(iter(session.inventory.items))
        before = session._snapshot(session.run, 101)
        session.action({'type': 'gear_equip', 'uid': uid, 'slot': 2})
        after = session._snapshot(session.run, 101)
        self.assertAlmostEqual(after.general_xp / before.general_xp, 1.1)
        session._continue_after_reward()
        self.assertEqual(len(session.inventory.items), 1)
        self.assertEqual(len(session.pending_equipment), 0)
        self.assertFalse(session.permanent.relic_unlocked)
        session.inventory.on_death()
        session._new_run()
        self.assertEqual(session.inventory.relic_slots[2], uid)

    def test_overflow_keeps_reward_and_discard_is_explicit(self):
        session = EquipmentSession('balanced', 21)
        for i in range(5):
            session.inventory.receive(EquipmentItem(f'w{i}', 'weapon', '剣', 'C', 10, base_atk=1))
        session._roll_boss_weapon(10)
        session._continue_after_reward()
        before = copy.deepcopy(session.inventory.to_dict())
        with self.assertRaises(ValueError):
            session.action({'type': 'gear_receive'})
        self.assertEqual(before, session.inventory.to_dict())
        self.assertEqual(len(session.pending_equipment), 1)
        session.action({'type': 'gear_discard'})
        self.assertEqual(session.inventory.materials['weapon'], 1)

    def test_snapshot_does_not_mutate_rng_or_state(self):
        session = EquipmentSession('balanced', 21)
        before = (copy.deepcopy(session.run), copy.deepcopy(session.permanent), session.rng.getstate(), session.inventory.to_dict())
        session._snapshot(session.run, 100)
        self.assertEqual(before, (session.run, session.permanent, session.rng.getstate(), session.inventory.to_dict()))

    def test_learning_lens_feeds_new_xp_conversion(self):
        session = EquipmentSession('balanced', 21)
        sim.acquire_card(session.run, sim.CARD_BY_KEY['knowledge_conversion'], session.config)
        before = session._snapshot(session.run, 101)
        session.inventory.receive(EquipmentItem('lens', 'relic', '学習レンズ', 'C', 100, unique_key='learning_lens'))
        session.inventory.equip('lens', 0)
        after = session._snapshot(session.run, 101)
        self.assertAlmostEqual(after.log_dps - before.log_dps, __import__('math').log10(1.025))

    def test_profile_target_and_illegal_resume(self):
        session = EquipmentSession('balanced', 21)
        self.assertEqual(session.target_wave, 5000)
        self.assertEqual(sim.configured_enemy_power(5000, session.config), 308)
        session.action({'type': 'gear_done'})
        self.assertEqual(session.mode, 'combat')

    def test_first_draft_and_selection_use_live_config(self):
        for cls in (PlaySession, EquipmentSession):
            session = cls('balanced', 21)
            session._open_card(None, None)
            self.assertEqual(len(session.card_hand), 3)
            card = (session.card_hand[0] if cls is EquipmentSession else
                    next(card for card in session.card_hand if card.key in sim.STARTER_SAFE_KEYS))
            session.action({'type': 'select_card', 'cardKey': card.key})
            self.assertEqual(session.run.card_count, 1)
