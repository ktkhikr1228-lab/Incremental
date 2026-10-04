"""In-memory death regressions; no live API or balance simulation."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "first-prestige-playtest"))
from sim_server import PlaySession, sim
from equipment_session import EquipmentSession
from w5000_equipment_v01 import EquipmentItem


class PlaySessionDeathTests(unittest.TestCase):
    def prepare_death(self, cls):
        session = cls("balanced", 20260828)
        session.run.kills = 12
        session.run.combat_seconds = 3974.8
        session.run.counts["power_up"] = 1
        session.run.counts["steady_force"] = 1
        session.run.card_count = 2
        session.permanent.banked_dp = 776
        session._prepare_fight()
        session.fight["timeToKill"] = None
        session.fight["willWin"] = False
        session.fight["timeLimit"] = 10.0
        return session

    def snapshot(self, session):
        return copy.deepcopy(session.__dict__)

    def assert_unchanged(self, before, session):
        after = self.snapshot(session)
        self.assertEqual(before.pop("rng").getstate(), after.pop("rng").getstate())
        self.assertEqual(before, after)

    def test_death_awards_once_and_retry_starts_new_run(self):
        for cls in (PlaySession,):
            with self.subTest(session=cls.__name__):
                session = self.prepare_death(cls)
                with patch.object(sim, "store_memory_candidates", wraps=sim.store_memory_candidates) as store:
                    session.action({"type": "resolve"})
                    store.assert_called_once()
                    result = store.call_args.args[0]
                    self.assertEqual(result.reach_elapsed, session.run.reach_elapsed)
                    self.assertEqual(result.end_state, {})
                    self.assertIsNone(result.w2500_state)
                self.assertEqual(session.mode, "death")
                self.assertEqual(session.permanent.banked_dp, 778)
                self.assertEqual(session.total_dp, 2)
                self.assertAlmostEqual(session.run.combat_seconds, 3984.8)
                self.assertEqual(session.permanent.memory_candidate_keys, ("power_up", "steady_force"))
                self.assertEqual(session.last_death["failureWave"], 13)
                self.assertEqual(session.last_death["gainedDp"], 2)
                before = self.snapshot(session)
                session.action({"type": "resolve"})
                self.assert_unchanged(before, session)
                session.action({"type": "retry"})
                self.assertEqual(session.attempt, 2)
                self.assertEqual(session.mode, "combat")
                self.assertEqual(session.wave, 1)
                self.assertEqual(session.run.kills, 0)
                self.assertEqual(session.run.combat_seconds, 0)
                self.assertIsNone(session.last_death)
                self.assertAlmostEqual(session.total_combat_seconds, 3984.8)
                self.assertEqual(session.permanent.banked_dp, 778)
                before = self.snapshot(session)
                session.action({"type": "retry"})
                self.assert_unchanged(before, session)
                # A subsequent death still works and grants no DP at zero kills.
                session.fight["timeToKill"] = None
                session.action({"type": "resolve"})
                self.assertEqual(session.mode, "death")
                self.assertEqual(session.permanent.banked_dp, 778)
                self.assertEqual(session.total_dp, 2)

    def test_equipment_death_recovers_half_weapon_value_and_preserves_relics(self):
        session = self.prepare_death(EquipmentSession)
        inventory = session.inventory
        inventory.receive(EquipmentItem("equipped", "weapon", "sword", "C", 10,
                                        base_atk=1, enhancement=1, enhancement_spent=4))
        inventory.equip("equipped")
        inventory.receive(EquipmentItem("stored", "weapon", "sword", "R", 10, base_atk=1))
        inventory.receive(EquipmentItem("lens", "relic", "lens", "C", 100,
                                        unique_key="learning_lens"))
        inventory.equip("lens", 2)
        inventory.receive(EquipmentItem("stored-relic", "relic", "lens", "U", 100))
        inventory.materials = {"weapon": 7, "relic": 9}
        relics = copy.deepcopy({uid: item for uid, item in inventory.items.items() if item.kind == "relic"})
        with patch.object(inventory, "on_death", wraps=inventory.on_death) as on_death:
            session.action({"type": "resolve"})
            session.action({"type": "resolve"})
            on_death.assert_called_once()
        self.assertEqual(inventory.materials, {"weapon": 11.5, "relic": 9})
        self.assertIsNone(inventory.weapon_slot)
        self.assertEqual(inventory.items, relics)
        self.assertEqual(inventory.relic_slots, [None, None, "lens"])
        before = copy.deepcopy(inventory.to_dict())
        session.action({"type": "retry"})
        self.assertEqual(inventory.to_dict(), before)
        self.assertEqual(session.mode, "combat")

    def test_failed_death_preparation_does_not_commit_rewards_or_mutate_state(self):
        for cls in (PlaySession,):
            for failure in ("RunResult", "store_memory_candidates"):
                with self.subTest(session=cls.__name__, failure=failure):
                    session = self.prepare_death(cls)
                    before = self.snapshot(session)

                    def fail(*args, **kwargs):
                        if failure == "store_memory_candidates":
                            args[1].memory_candidate_keys = ("temporary",)
                        raise TypeError("injected death preparation failure")

                    with patch.object(sim, failure, side_effect=fail):
                        with self.assertRaises(TypeError):
                            session.action({"type": "resolve"})
                    self.assert_unchanged(before, session)
                    session.action({"type": "resolve"})
                    self.assertEqual(session.mode, "death")
                    self.assertEqual(session.permanent.banked_dp, 778)


if __name__ == "__main__":
    unittest.main()
