"""Acceptance criteria for the shadow-only Encounter Conditional PE."""
import copy
import math
import random
import unittest

import card_value_v01 as cv
import simulate_first_prestige_v1 as sim
from first_prestige_defense_model import DefenseConfig


def combat_case(wave, desired_seconds):
    permanent = sim.PermanentState(
        atk=5, attack_speed=10, max_wave=wave - 1, relic_unlocked=wave > 100,
    )
    run = sim.RunState(kills=wave - 1, weapon=True, xp_level_count=8)
    config = sim.SimConfig(target_wave=wave)
    without_weapon = sim.compute_snapshot(run, permanent, wave % 10 == 0, config)
    run.weapon_power = (sim.configured_enemy_power(wave, config)
                        - math.log10(desired_seconds) - without_weapon.log_dps)
    return run, permanent, config


def evaluate(wave, seconds, key):
    run, permanent, config = combat_case(wave, seconds)
    return cv.evaluate_card(sim, run, permanent, sim.CARD_BY_KEY[key], wave,
                            config, phase="guaranteed")


class EncounterConditionalAcceptance(unittest.TestCase):
    def test_time_collapse_instant_kill_has_no_conditional_value(self):
        value = evaluate(501, 1.0, "time_collapse")
        fight = value["encounter_outcomes"][0]
        self.assertAlmostEqual(fight["baseline_ttk"], fight["candidate_ttk"], places=10)
        self.assertLessEqual(abs(value["conditional_combat_pe"]), 1e-9)
        self.assertLessEqual(abs(value["total_pe"]), 1e-9)

    def test_time_collapse_near_timeout_is_more_valuable(self):
        easy = evaluate(501, 1.0, "time_collapse")
        near = evaluate(501, 9.8, "time_collapse")
        fight = near["encounter_outcomes"][0]
        self.assertAlmostEqual(fight["baseline_ttk"], 9.822612056652146, places=8)
        self.assertAlmostEqual(fight["candidate_ttk"], 6.139132535407591, places=8)
        self.assertGreater(near["conditional_combat_pe"], easy["conditional_combat_pe"] + 1e-6)
        self.assertGreater(near["total_pe"], easy["total_pe"] + 1e-6)

    def test_execution_instant_kill_has_no_conditional_value(self):
        value = evaluate(500, 1.0, "execution")
        fight = value["encounter_outcomes"][0]
        self.assertAlmostEqual(fight["baseline_ttk"], fight["candidate_ttk"], places=10)
        self.assertLessEqual(abs(value["conditional_combat_pe"]), 1e-9)

    def test_execution_near_timeout_is_more_valuable(self):
        easy = evaluate(500, 1.0, "execution")
        near = evaluate(500, 14.0, "execution")
        fight = near["encounter_outcomes"][0]
        self.assertAlmostEqual(fight["baseline_ttk"], 14.12000483143746, places=8)
        self.assertAlmostEqual(fight["candidate_ttk"], 11.664351817274424, places=8)
        self.assertGreater(near["conditional_combat_pe"], easy["conditional_combat_pe"] + 1e-6)

    def test_execution_discrete_hit_loss_is_not_a_win(self):
        run, permanent, config = combat_case(500, 14.8)
        old = sim.compute_snapshot(run, permanent, True, config)
        self.assertGreater(cv._margin(sim, old, 500, config, run), 0)
        value = cv.evaluate_card(sim, run, permanent, sim.CARD_BY_KEY["execution"],
                                 500, config, phase="guaranteed")
        fight = value["encounter_outcomes"][0]
        self.assertFalse(fight["baseline_win"])
        self.assertIsNone(fight["baseline_ttk"])
        self.assertTrue(fight["candidate_win"])
        self.assertAlmostEqual(fight["candidate_ttk"], 12.278265070815182, places=8)
        self.assertGreater(fight["baseline_required_hits"], fight["baseline_available_hits"])
        self.assertGreater(value["conditional_combat_pe"], 1e-6)
        self.assertIsNone(value["terminal_pe"])
        self.assertFalse(value["terminal_included"])
        self.assertGreater(value["terminal_break_probability_delta"], 0)

    def test_encounter_result_has_no_rng_or_state_side_effects(self):
        for key, wave in (("execution", 500), ("time_collapse", 501)):
            with self.subTest(card=key):
                run, permanent, config = combat_case(wave, 9.8)
                old_run, old_permanent = copy.deepcopy(run), copy.deepcopy(permanent)
                global_rng = random.getstate()
                result = cv.evaluate_card(sim, run, permanent, sim.CARD_BY_KEY[key], wave,
                                          config, phase="guaranteed")
                self.assertEqual(run, old_run)
                self.assertEqual(permanent, old_permanent)
                self.assertEqual(random.getstate(), global_rng)
                self.assertAlmostEqual(result["immediate_combat_pe"] + result["conditional_combat_pe"],
                                       sum(row["encounter_pe"] for row in result["encounter_outcomes"])
                                       / result["remaining_encounters"])
                self.assertAlmostEqual(result["total_pe"],
                                       0.60 * (result["immediate_combat_pe"] + result["conditional_combat_pe"])
                                       + 0.25 * result["growth_pe"] + 0.15 * result["xp_pe"])

    def test_unbreakable_defense_marks_pe_unresolved(self):
        config = sim.SimConfig(
            target_wave=10000, defense=DefenseConfig(enabled=True, armor_break_base=1e-6))
        run = sim.RunState(kills=9999, weapon=True)
        permanent = sim.PermanentState(max_wave=9999)
        result = cv.evaluate_card(sim, run, permanent, sim.CARD_BY_KEY["execution"],
                                  10000, config, phase="guaranteed")
        self.assertEqual(result["conditional_status"], "unresolved_by_damage")
        self.assertIsNone(result["conditional_combat_pe"])
        self.assertIsNone(result["total_pe"])
        self.assertIsNone(result["terminal_pe"])

    def test_simple_card_pe_matches_previous_shadow_golden_values(self):
        permanent = sim.PermanentState(atk=5, attack_speed=5, max_wave=49)
        config = sim.SimConfig(target_wave=80)
        initial = sim.RunState(kills=49, weapon=True, xp_level_count=8)
        weapon_power = (sim.configured_enemy_power(50, config) - math.log10(10)
                        - sim.compute_snapshot(initial, permanent, True, config).log_dps + 0.5)
        expected = {
            "power_up": ((0.09691001300805643, 0.05814600780483399),
                         (0.04575749056067502, 0.027454494336405143),
                         (0.017728766960431575, 0.010637260176258944)),
            "rapid_fire": ((0.07918124604762489, 0.047508747628575064),
                           (0.04139268515822492, 0.024835611094935216),
                           (0.017033339298780703, 0.010220003579268421)),
        }
        for key, entries in expected.items():
            previous = float("inf")
            for n, (immediate, total) in zip((0, 5, 20), entries):
                with self.subTest(card=key, stacks=n):
                    run = sim.RunState(kills=49, weapon=True, weapon_power=weapon_power,
                                       xp_level_count=8, card_count=n)
                    run.counts[key] = n
                    run.tag_counts["atk" if key == "power_up" else "as"] = n
                    result = cv.evaluate_card(sim, run, permanent, sim.CARD_BY_KEY[key],
                                              50, config, phase="guaranteed")
                    self.assertAlmostEqual(result["immediate_combat_pe"], immediate, delta=1e-9)
                    self.assertAlmostEqual(result["total_pe"], total, delta=1e-9)
                    self.assertLessEqual(abs(result["conditional_combat_pe"]), 1e-9)
                    self.assertLess(result["total_pe"], previous)
                    previous = result["total_pe"]

    def test_shadow_toggle_keeps_decisions_trial_and_rng_identical(self):
        config = sim.SimConfig(target_wave=50, max_attempts=3)
        old_hook = sim.record_card_decision
        original_limit = sim.SHADOW_CARD_VALUE_LIMIT
        def capture(shadow):
            choices = []
            def recorder(permanent, item, rerolls_used, automated=False):
                choices.append((item.key, rerolls_used, automated))
                return old_hook(permanent, item, rerolls_used, automated)
            sim.record_card_decision = recorder
            sim.SHADOW_CARD_VALUE_LIMIT = 8 if shadow else 0
            sim.SHADOW_CARD_VALUE_ROWS.clear()
            rng = random.Random(112233)
            initial_rng_state = rng.getstate()
            initial_global_state = random.getstate()
            result = sim.run_trial(rng, "balanced", config, True)
            self.assertEqual(random.getstate(), initial_global_state)
            return result, initial_rng_state, rng.getstate(), choices, len(sim.SHADOW_CARD_VALUE_ROWS)
        try:
            off = capture(False)
            on = capture(True)
        finally:
            sim.record_card_decision = old_hook
            sim.SHADOW_CARD_VALUE_LIMIT = original_limit
            sim.SHADOW_CARD_VALUE_ROWS.clear()
        self.assertEqual(off[:4], on[:4])
        self.assertGreater(off[0].attempts, 1)
        self.assertEqual(off[4], 0)
        self.assertGreater(on[4], 0)

    def test_shadow_toggle_keeps_single_run_and_mutable_state_identical(self):
        config = sim.SimConfig(target_wave=20)
        old_limit = sim.SHADOW_CARD_VALUE_LIMIT
        def capture(shadow):
            sim.SHADOW_CARD_VALUE_ROWS.clear()
            sim.SHADOW_CARD_VALUE_LIMIT = 4 if shadow else 0
            rng = random.Random(42)
            permanent = sim.PermanentState()
            result = sim.run_once(rng, "balanced", permanent, config, True)
            return result, copy.deepcopy(permanent), rng.getstate(), len(sim.SHADOW_CARD_VALUE_ROWS)
        try:
            off, on = capture(False), capture(True)
        finally:
            sim.SHADOW_CARD_VALUE_LIMIT = old_limit
            sim.SHADOW_CARD_VALUE_ROWS.clear()
        self.assertEqual(off[:3], on[:3])
        self.assertEqual(off[3], 0)
        self.assertGreater(on[3], 0)

    def test_shadow_toggle_with_forced_execution_choice(self):
        config = sim.SimConfig(target_wave=500)
        old_limit = sim.SHADOW_CARD_VALUE_LIMIT
        def capture(shadow):
            sim.SHADOW_CARD_VALUE_ROWS.clear()
            sim.SHADOW_CARD_VALUE_LIMIT = 3 if shadow else 0
            rng = random.Random(98765)
            run, permanent, _ = combat_case(500, 14.8)
            before = rng.getstate()
            sim.choose_card(rng, "balanced", run, permanent, 500, config,
                            forced_rarity="E", forced_card="execution")
            return run, permanent, before, rng.getstate(), copy.deepcopy(sim.SHADOW_CARD_VALUE_ROWS)
        try:
            off, on = capture(False), capture(True)
        finally:
            sim.SHADOW_CARD_VALUE_LIMIT = old_limit
            sim.SHADOW_CARD_VALUE_ROWS.clear()
        self.assertEqual(off[:4], on[:4])
        self.assertEqual(off[4], [])
        self.assertTrue(any(row["card_id"] == "execution" and row["conditional_status"] == "ok"
                            for row in on[4]))

    def test_both_fail_can_have_positive_marginal_rescue_value(self):
        value = evaluate(501, 50.0, "time_collapse")
        fight = value["encounter_outcomes"][0]
        self.assertFalse(fight["baseline_win"])
        self.assertFalse(fight["candidate_win"])
        self.assertGreater(value["conditional_combat_pe"], 0)


if __name__ == "__main__":
    unittest.main()
