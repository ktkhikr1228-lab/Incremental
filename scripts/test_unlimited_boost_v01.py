from __future__ import annotations

import dataclasses
import unittest

import simulate_first_prestige_v1 as sim


class UnlimitedBoostV01Tests(unittest.TestCase):
    def config(self) -> sim.SimConfig:
        return dataclasses.replace(
            sim.SimConfig(),
            unlimited_boost=sim.UnlimitedBoostConfig(enabled=True),
        )

    def test_default_is_disabled_and_inert(self) -> None:
        permanent = sim.PermanentState(max_wave=5000, weapon_material=10_000, relic_material=10_000)
        run = sim.RunState(weapon=True, weapon_power=2.0)
        before = sim.compute_snapshot(run, permanent, True, sim.SimConfig())
        self.assertFalse(sim.purchase_unlimited_boost(permanent, sim.SimConfig()))
        after = sim.compute_snapshot(run, permanent, True, sim.SimConfig())
        self.assertEqual(before, after)
        self.assertFalse(permanent.unlimited_boost_unlocked)
        self.assertEqual(sum(permanent.unlimited_boost_levels.values()), 0)

    def test_unlocks_only_at_w4000_and_purchases_persist(self) -> None:
        config = self.config()
        permanent = sim.PermanentState(max_wave=3999, weapon_material=500, relic_material=500)
        self.assertFalse(sim.purchase_unlimited_boost(permanent, config))
        permanent.max_wave = 4000
        self.assertTrue(sim.purchase_unlimited_boost(permanent, config))
        levels = permanent.unlimited_boost_levels.copy()
        self.assertTrue(permanent.unlimited_boost_unlocked)
        self.assertGreater(sum(levels.values()), 0)
        self.assertGreater(permanent.unlimited_boost_weapon_spent, 0)
        self.assertGreater(permanent.unlimited_boost_relic_spent, 0)
        sim.RunState()
        self.assertEqual(permanent.unlimited_boost_levels, levels)

    def test_softcap_structure(self) -> None:
        boost = sim.UnlimitedBoostConfig(enabled=True, softcap_start=5, softcap_rate=0.5)
        self.assertEqual(sim.unlimited_boost_effective_levels(5, boost), 5.0)
        self.assertEqual(sim.unlimited_boost_effective_levels(7, boost), 6.0)

    def test_each_node_has_positive_finite_effect(self) -> None:
        config = self.config()
        run = sim.RunState(weapon=True, weapon_power=2.0)
        for node in sim.UNLIMITED_BOOST_NODES:
            permanent = sim.PermanentState(max_wave=4000, unlimited_boost_unlocked=True)
            permanent.unlimited_boost_levels[node] = 1
            normal = sim.compute_snapshot(run, permanent, False, config)
            boss = sim.compute_snapshot(run, permanent, True, config)
            baseline_permanent = sim.PermanentState(
                max_wave=4000, unlimited_boost_unlocked=True
            )
            baseline_normal = sim.compute_snapshot(run, baseline_permanent, False, config)
            baseline_boss = sim.compute_snapshot(run, baseline_permanent, True, config)
            if node == "boss_damage":
                self.assertEqual(normal.log_dps, baseline_normal.log_dps)
                self.assertGreater(boss.log_dps, baseline_boss.log_dps)
            else:
                self.assertGreater(normal.log_dps, baseline_normal.log_dps, node)

    def test_suppression_keeps_purchase_economy_and_disables_only_effect(self) -> None:
        full = self.config()
        suppressed = dataclasses.replace(
            full,
            unlimited_boost=dataclasses.replace(
                full.unlimited_boost,
                suppressed_nodes=("attack_speed",),
            ),
        )
        full_permanent = sim.PermanentState(
            max_wave=4000, weapon_material=500, relic_material=500
        )
        suppressed_permanent = sim.PermanentState(
            max_wave=4000, weapon_material=500, relic_material=500
        )
        self.assertTrue(sim.purchase_unlimited_boost(full_permanent, full))
        self.assertTrue(sim.purchase_unlimited_boost(suppressed_permanent, suppressed))
        self.assertEqual(
            full_permanent.unlimited_boost_levels,
            suppressed_permanent.unlimited_boost_levels,
        )
        self.assertEqual(full_permanent.weapon_material, suppressed_permanent.weapon_material)
        self.assertEqual(full_permanent.relic_material, suppressed_permanent.relic_material)
        self.assertEqual(
            full_permanent.unlimited_boost_weapon_spent,
            suppressed_permanent.unlimited_boost_weapon_spent,
        )
        self.assertEqual(
            full_permanent.unlimited_boost_relic_spent,
            suppressed_permanent.unlimited_boost_relic_spent,
        )

        run = sim.RunState(weapon=True, weapon_power=2.0)
        only_as = sim.PermanentState(max_wave=4000, unlimited_boost_unlocked=True)
        only_as.unlimited_boost_levels["attack_speed"] = 1
        baseline = sim.compute_snapshot(
            run,
            sim.PermanentState(max_wave=4000, unlimited_boost_unlocked=True),
            False,
            full,
        )
        full_snapshot = sim.compute_snapshot(run, only_as, False, full)
        suppressed_snapshot = sim.compute_snapshot(run, only_as, False, suppressed)
        self.assertGreater(full_snapshot.attack_speed, baseline.attack_speed)
        self.assertEqual(suppressed_snapshot.attack_speed, baseline.attack_speed)
        self.assertEqual(suppressed_snapshot.log_dps, baseline.log_dps)

    def test_v02_replaces_attack_speed_with_finale_mastery(self) -> None:
        boost = sim.UnlimitedBoostConfig(
            enabled=True,
            version="v0.2",
            node_order=sim.UNLIMITED_BOOST_V02_NODES,
        )
        self.assertNotIn("attack_speed", boost.node_order)
        self.assertIn("finale_mastery", boost.node_order)

        config = dataclasses.replace(sim.SimConfig(), unlimited_boost=boost)
        permanent = sim.PermanentState(
            max_wave=4000, weapon_material=500, relic_material=500
        )
        sim.purchase_unlimited_boost(permanent, config)
        self.assertEqual(permanent.unlimited_boost_levels["attack_speed"], 0)
        self.assertGreater(permanent.unlimited_boost_levels["finale_mastery"], 0)

    def test_finale_mastery_only_applies_inside_enabled_finale(self) -> None:
        boost = sim.UnlimitedBoostConfig(
            enabled=True,
            version="v0.2",
            node_order=sim.UNLIMITED_BOOST_V02_NODES,
            finale_mastery_power_per_level=1.25,
        )
        permanent = sim.PermanentState(max_wave=4500, unlimited_boost_unlocked=True)
        permanent.unlimited_boost_levels["finale_mastery"] = 1
        before_run = sim.RunState(kills=4498)
        finale_run = sim.RunState(kills=4499)
        finale_on = dataclasses.replace(
            sim.SimConfig(), unlimited_boost=boost, finale=sim.FinaleConfig(enabled=True)
        )
        finale_off = dataclasses.replace(
            finale_on, finale=sim.FinaleConfig(enabled=False)
        )
        before = sim.compute_snapshot(before_run, permanent, True, finale_on)
        active = sim.compute_snapshot(finale_run, permanent, True, finale_on)
        inactive = sim.compute_snapshot(finale_run, permanent, True, finale_off)
        baseline = sim.compute_snapshot(
            finale_run,
            sim.PermanentState(max_wave=4500, unlimited_boost_unlocked=True),
            True,
            finale_on,
        )
        self.assertEqual(before.log_dps, sim.compute_snapshot(
            before_run,
            sim.PermanentState(max_wave=4500, unlimited_boost_unlocked=True),
            True,
            finale_on,
        ).log_dps)
        self.assertEqual(inactive.log_dps, baseline.log_dps)
        self.assertAlmostEqual(active.log_dps - baseline.log_dps, 1.25)


if __name__ == "__main__":
    unittest.main()
