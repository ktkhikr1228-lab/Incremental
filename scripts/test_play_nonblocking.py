"""Manual-session UX regression checks; not Monte Carlo/balance changes."""
import copy
import math
import sys
import unittest
from dataclasses import replace
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'first-prestige-playtest'))
from equipment_session import EquipmentSession
from w5000_equipment_v01 import EquipmentItem
from live_encounter import project
import new_w5000_rules as rules


class NonblockingTests(unittest.TestCase):
    def session(self):
        return EquipmentSession('balanced', 20260828)

    def fingerprint(self, s):
        values = {k: v for k, v in s.__dict__.items() if k != 'rng'}
        return copy.deepcopy(values), s.rng.getstate()

    def test_drafts_accumulate_no_rng_until_open_hand_survives_close(self):
        s = self.session()
        s.pending_cards.extend([(None, None), ('R', None)])
        rng = s.rng.getstate()
        s.state()
        self.assertEqual(s.rng.getstate(), rng)
        self.assertEqual(s.state()['cardDrafts'], 2)
        s.action(dict(type='open_cards', elapsed=1, fightId=s.fight['id']))
        hand, rng = list(s.card_hand), s.rng.getstate()
        s.action(dict(type='open_cards', elapsed=1.2))
        self.assertEqual(s.card_hand, hand)
        self.assertEqual(s.rng.getstate(), rng)
        s.action(dict(type='select_card', cardKey=hand[0].key, elapsed=1.2))
        self.assertEqual(s.mode, 'combat')
        self.assertEqual(s.state()['cardDrafts'], 1)
        self.assertTrue(all(c.rarity == 'R' for c in s.card_hand))

    def test_partial_damage_and_time_retained_card_immediate(self):
        s = self.session()
        s.pending_cards.append((None, None))
        s.action(dict(type='open_cards', elapsed=2))
        s.card_hand = [rules.BY_KEY['power_up']]
        remaining = s.encounter_remaining
        self.assertLess(remaining, 1)
        s.action(dict(type='select_card', cardKey='power_up', elapsed=2))
        self.assertEqual(s.encounter_start, 2)
        self.assertAlmostEqual(s.encounter_remaining, remaining)
        self.assertAlmostEqual(s.fight['dpsPower'], math.log10(1.01 * 1.25))
        self.assertEqual(s.fight['hpSamples'][0]['remaining'], remaining)
        self.assertGreaterEqual(s.fight['timeToKill'], 2)
        s.action(dict(type='resolve'))
        self.assertEqual(s.run.kills, 1)

    def test_repeated_read_refresh_keeps_attack_phase(self):
        s = self.session()
        original = s.fight['timeToKill']
        for time in (.2, .4, .7, 1.1, 1.7):
            s.action(dict(type='open_cards', elapsed=time))
        self.assertAlmostEqual(s.fight['timeToKill'], original)

    def test_equipment_combat_direct_equip_and_furnace(self):
        s = self.session()
        item = EquipmentItem('drop', 'weapon', '剣', 'C', 10, base_atk=1)
        s.pending_equipment.append(item)
        s.action(dict(type='gear_receive', uid='drop', equip=True, elapsed=1.2))
        self.assertEqual(s.inventory.weapon_slot, 'drop')
        self.assertEqual(s.encounter_start, 1.2)
        s.action(dict(type='gear_dismantle', uid='drop', elapsed=1.2))
        self.assertEqual(s.inventory.materials['weapon'], 1)
        self.assertNotIn('drop', s.inventory.items)

    def test_full_storage_empty_slot_equip_and_failed_swap_atomic(self):
        s = self.session()
        for i in range(5):
            s.inventory.receive(EquipmentItem(str(i), 'weapon', '剣', 'C', 10, base_atk=1))
        s.pending_equipment.append(EquipmentItem('new', 'weapon', '剣', 'R', 10, base_atk=2))
        s.action(dict(type='gear_receive', uid='new', equip=True))
        s.inventory.validate()
        s.pending_equipment.append(EquipmentItem('new2', 'weapon', '剣', 'R', 10, base_atk=3))
        before = self.fingerprint(s)
        with self.assertRaises(ValueError):
            s.action(dict(type='gear_receive', uid='new2', equip=True, elapsed=.5))
        self.assertEqual(self.fingerprint(s), before)

    def test_duplicate_stale_resolve_is_ignored(self):
        s = self.session()
        fight_id = s.fight['id']
        s.action(dict(type='resolve', fightId=fight_id))
        before = self.fingerprint(s)
        s.action(dict(type='resolve', fightId=fight_id))
        self.assertEqual(self.fingerprint(s), before)

    def test_death_clears_choices_recovers_unprocessed_weapon_retains_relic(self):
        s = self.session()
        s.pending_cards.append((None, None))
        s.action(dict(type='open_cards'))
        s.pending_equipment.extend([EquipmentItem('w', 'weapon', '剣', 'R', 10),
            EquipmentItem('r', 'relic', '学習レンズ', 'C', 100, unique_key='learning_lens')])
        s.fight['timeToKill'] = None
        s.action(dict(type='resolve'))
        self.assertEqual(s.mode, 'death')
        self.assertEqual(s.state()['cardDrafts'], 0)
        self.assertEqual(s.inventory.materials['weapon'], 4)
        self.assertEqual([c.uid for c in s.pending_equipment], ['r'])
        s.action(dict(type='resolve'))
        self.assertEqual(s.inventory.materials['weapon'], 4)

    def test_execution_time_collapse_segment_equivalent_without_edit(self):
        s = self.session()
        for execution in (1, 2.5):
            for collapse in (False, True):
                snap = replace(s.pre_snapshot, log_dps=math.log10(2.4), attack_speed=2.4,
                    execution_mult=execution, time_collapse=collapse)
                old = rules.time_to_kill(math.log10(29), 10, snap)
                new, hp = project(math.log10(29), 10, snap)
                self.assertEqual(old, new)
                self.assertAlmostEqual(hp(5), rules.remaining_hp(math.log10(29), 10, snap, 5))

    def test_invalid_card_does_not_change_rng_time_state(self):
        s = self.session()
        s.pending_cards.append((None, None))
        s.action(dict(type='open_cards'))
        before = self.fingerprint(s)
        with self.assertRaises(ValueError):
            s.action(dict(type='select_card', cardKey='not-in-hand', elapsed=1))
        self.assertEqual(self.fingerprint(s), before)


if __name__ == '__main__':
    unittest.main()
