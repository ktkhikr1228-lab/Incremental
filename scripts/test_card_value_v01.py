import copy
import math
import random
import unittest

import card_value_v01 as cv
import simulate_first_prestige_v1 as sim


class CardValueShadowTests(unittest.TestCase):
    def setUp(self):
        self.config = sim.SimConfig(target_wave=5)
        self.run = sim.RunState()
        self.permanent = sim.PermanentState(atk=12, attack_speed=4)

    def value(self, key, run=None, permanent=None, config=None):
        return cv.evaluate_card(sim, run or self.run, permanent or self.permanent,
                                sim.CARD_BY_KEY[key], 1, config or self.config,
                                phase="guaranteed")

    def test_power_up_uses_current_marginal_attack(self):
        low = self.value("power_up")
        high_run = copy.deepcopy(self.run)
        high_run.counts["power_up"] = 10
        high = self.value("power_up", high_run)
        self.assertGreater(low["immediate_combat_pe"], high["immediate_combat_pe"])
        self.assertGreater(high["immediate_combat_pe"], 0)

    def test_rapid_fire_and_execution_have_different_axes(self):
        rapid = self.value("rapid_fire")
        execution = self.value("execution")
        self.assertGreater(rapid["immediate_combat_pe"], 0)
        self.assertAlmostEqual(execution["immediate_combat_pe"], 0, places=10)
        self.assertGreater(execution["conditional_combat_pe"], 0)

    def test_time_collapse_same_ttk_has_no_conditional_value(self):
        value = self.value("time_collapse")
        self.assertAlmostEqual(value["immediate_combat_pe"], 0, places=10)
        fight = value["encounter_outcomes"][0]
        self.assertEqual(fight["baseline_ttk"], fight["candidate_ttk"])
        self.assertAlmostEqual(value["conditional_combat_pe"], 0, places=10)
        self.assertAlmostEqual(value["total_pe"], 0.6 * value["conditional_combat_pe"] + 0.15 * value["xp_pe"])

    def test_xp_added_draft_is_only_in_xp_axis(self):
        config = sim.SimConfig(target_wave=25)
        value = self.value("experience", config=config)
        self.assertAlmostEqual(value["immediate_combat_pe"], 0, places=10)
        self.assertEqual(value["growth_pe"], 0)
        self.assertGreater(value["xp_pe"], 0)
        self.assertAlmostEqual(value["total_pe"], 0.15 * value["xp_pe"])

    def test_knowledge_collapse_owned_future_engine_is_growth(self):
        permanent = sim.PermanentState(atk=12, attack_speed=4, xp=50)
        value = self.value("knowledge_collapse", permanent=permanent)
        self.assertGreater(value["growth_pe"], 0)
        self.assertAlmostEqual(value["total_pe"],
                               0.60 * (value["immediate_combat_pe"] + value["conditional_combat_pe"])
                               + 0.25 * value["growth_pe"] + 0.15 * value["xp_pe"])

    def test_forecast_counts_failed_wave_without_its_xp(self):
        weak = sim.RunState()
        weak_permanent = sim.PermanentState()
        result = cv.predict_run_end(sim, weak, weak_permanent, 10,
                                    sim.SimConfig(target_wave=10), "guaranteed")
        self.assertEqual(result.predicted_end_wave, 10)
        self.assertEqual(len(result.frames), 1)
        self.assertEqual(result.big_boss_encounters, 0)
        self.assertEqual(result.boss_encounters, 1)
        self.assertEqual(result.remaining_xp, 0)

    def test_only_deterministic_first_weapon_is_projected(self):
        run = sim.RunState(kills=9)
        result = cv.predict_run_end(sim, run, sim.PermanentState(atk=15), 10,
                                    sim.SimConfig(target_wave=11), "guaranteed")
        self.assertEqual(result.predicted_end_wave, 11)
        self.assertFalse(result.frames[0].run.weapon)
        self.assertTrue(result.frames[1].run.weapon)
        self.assertAlmostEqual(result.frames[1].run.weapon_power, math.log10(1.10))

    def test_no_mutation_or_rng_use_and_terminal_excluded(self):
        state, permanent = copy.deepcopy(self.run), copy.deepcopy(self.permanent)
        rng = random.getstate()
        value = self.value("power_up")
        self.assertEqual(self.run, state)
        self.assertEqual(self.permanent, permanent)
        self.assertEqual(random.getstate(), rng)
        self.assertIsNone(value["terminal_pe"])
        self.assertFalse(value["terminal_included"])
        self.assertTrue(math.isfinite(value["total_pe"]))

    def test_shadow_disabled_preserves_old_choice(self):
        self.assertEqual(sim.SHADOW_CARD_VALUE_LIMIT, 0)
        config = sim.SimConfig(target_wave=20)
        first = sim.run_once(random.Random(42), "balanced", sim.PermanentState(), config, True)
        second = sim.run_once(random.Random(42), "balanced", sim.PermanentState(), config, True)
        self.assertEqual(first, second)
        self.assertEqual(sim.SHADOW_CARD_VALUE_ROWS, [])

    def test_shadow_enabled_does_not_change_live_run_or_rng(self):
        config = sim.SimConfig(target_wave=20)
        sim.SHADOW_CARD_VALUE_LIMIT = 0
        first_rng = random.Random(42)
        first = sim.run_once(first_rng, "balanced", sim.PermanentState(), config, True)
        state = first_rng.getstate()
        try:
            sim.SHADOW_CARD_VALUE_ROWS.clear()
            sim.SHADOW_CARD_VALUE_LIMIT = 3
            shadow_rng = random.Random(42)
            second = sim.run_once(shadow_rng, "balanced", sim.PermanentState(), config, True)
            self.assertEqual(second, first)
            self.assertEqual(shadow_rng.getstate(), state)
            self.assertGreater(len(sim.SHADOW_CARD_VALUE_ROWS), 0)
        finally:
            sim.SHADOW_CARD_VALUE_LIMIT = 0
            sim.SHADOW_CARD_VALUE_ROWS.clear()


if __name__ == "__main__":
    unittest.main()
