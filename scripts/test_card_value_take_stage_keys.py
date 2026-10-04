"""CardValue Take support checks for the formally audited combat keys."""
import copy
import math
import random
import unittest

import card_value_v01 as cv
import simulate_first_prestige_v1 as sim


STAGE_KEYS = ("steady_force", "heavy_blow", "critical_eye", "precise_strike",
              "glass_cannon", "heavy_critical", "light_attack",
              "sharpened_edge", "critical_power")


class CardValueTakeStageKeys(unittest.TestCase):
    def state(self, *, crit_cards=0, multi_crit=False, wave=10):
        run = sim.RunState(kills=wave - 1, weapon=True, weapon_power=1.0,
                           xp_level_count=8, card_count=3)
        run.counts["critical_eye"] = crit_cards
        if multi_crit:
            run.counts["multi_crit"] = 1
        permanent = sim.PermanentState(atk=100, attack_speed=10, max_wave=wave - 1)
        return run, permanent, sim.SimConfig(target_wave=wave)

    def test_new_combat_keys_are_explicitly_not_xp_drafts(self):
        self.assertTrue(set(STAGE_KEYS) <= cv.TARGET_KEYS)
        self.assertTrue(set(STAGE_KEYS).isdisjoint(cv.XP_DRAFT_KEYS))
        self.assertEqual(cv.XP_DRAFT_KEYS, frozenset({
            "experience", "fast_learner", "scholar", "study_break", "risky_study",
            "quick_learner", "boss_research", "battle_scholar", "accelerated_learning",
            "knowledge_conversion", "perfect_learning", "knowledge_collapse",
        }))

    def test_stage2_snapshot_effects_match_formal_values(self):
        for key in ("glass_cannon", "heavy_critical", "light_attack"):
            with self.subTest(key=key):
                run, permanent, config = self.state()
                before = sim.compute_snapshot(run, permanent, True, config)
                candidate = copy.deepcopy(run)
                sim.acquire_card(candidate, sim.CARD_BY_KEY[key])
                after = sim.compute_snapshot(candidate, permanent, True, config)
                if key == "glass_cannon":
                    self.assertAlmostEqual(after.base_attack_power - before.base_attack_power,
                                           math.log10(1.50), places=10)
                elif key == "heavy_critical":
                    self.assertAlmostEqual(after.crit_chance - before.crit_chance, .03, places=10)
                    self.assertAlmostEqual(after.crit_multiplier / before.crit_multiplier, 1.50)
                    self.assertAlmostEqual(after.attack_speed / before.attack_speed, .97)
                else:
                    self.assertAlmostEqual(after.attack_speed / before.attack_speed, 1.30)
                    self.assertAlmostEqual(after.base_attack_power - before.base_attack_power,
                                           math.log10(.90), places=10)

    def test_stage3_crit_cards_match_formal_snapshot_deltas(self):
        expected = {"sharpened_edge": (.06, .20), "critical_power": (.03, .50)}
        for key, (crit_delta, multiplier_delta) in expected.items():
            for multi in (False, True):
                with self.subTest(key=key, multi_crit=multi):
                    run, permanent, config = self.state(crit_cards=9, multi_crit=multi)
                    before = sim.compute_snapshot(run, permanent, True, config)
                    candidate = copy.deepcopy(run)
                    sim.acquire_card(candidate, sim.CARD_BY_KEY[key])
                    after = sim.compute_snapshot(candidate, permanent, True, config)
                    self.assertAlmostEqual(after.crit_chance - before.crit_chance,
                                           crit_delta, places=10)
                    self.assertAlmostEqual(after.crit_multiplier - before.crit_multiplier,
                                           multiplier_delta, places=10)
                    value = cv.evaluate_card(sim, run, permanent, sim.CARD_BY_KEY[key], 10,
                                             config, phase="guaranteed")
                    self.assertTrue(math.isfinite(value["total_pe"]))
                    self.assertEqual(value["conditional_status"], "ok")

    def test_glass_cannon_encounter_path_models_shortened_deadline(self):
        # At high existing ATK, Glass Cannon's +50% additive attack is small;
        # its 10% shorter timer can turn a marginal win into a timeout.
        run, permanent, config = self.state(wave=500)
        run.counts["power_up"] = 100
        run.card_count = 103
        run.weapon_power = 0.0
        before = sim.compute_snapshot(run, permanent, True, config)
        run.weapon_power = sim.configured_enemy_power(500, config) - math.log10(13.9) - before.log_dps
        baseline = cv.predict_run_end(sim, run, permanent, 500, config, "guaranteed")
        self.assertEqual(baseline.frames[-1].wave, 500)
        value = cv.evaluate_card(sim, run, permanent, sim.CARD_BY_KEY["glass_cannon"], 500,
                                 config, phase="guaranteed", forecast=baseline)
        fight = value["encounter_outcomes"][0]
        self.assertEqual(sim.enemy_time_limit(500, 0), 15.0)
        self.assertEqual(sim.enemy_time_limit(500, 1), 13.5)
        self.assertTrue(fight["baseline_win"])
        self.assertFalse(fight["candidate_win"])
        self.assertIsNone(fight["candidate_ttk"])
        self.assertLess(value["immediate_combat_pe"] + value["conditional_combat_pe"], 0)
        self.assertTrue(math.isfinite(value["total_pe"]))

    def test_each_key_zero_to_one_and_stacking_is_finite_and_nonmutating(self):
        for key in STAGE_KEYS:
            with self.subTest(key=key):
                run, permanent, config = self.state()
                original_run, original_permanent = copy.deepcopy(run), copy.deepcopy(permanent)
                local_rng = random.Random(887)
                rng_state, global_state = local_rng.getstate(), random.getstate()
                one = cv.evaluate_card(sim, run, permanent, sim.CARD_BY_KEY[key], 10,
                                       config, phase="guaranteed")
                self.assertIsNotNone(one["total_pe"])
                self.assertTrue(math.isfinite(one["total_pe"]))
                self.assertIsNone(one["terminal_pe"])
                self.assertFalse(one["terminal_included"])
                self.assertEqual(run, original_run)
                self.assertEqual(permanent, original_permanent)
                self.assertEqual(local_rng.getstate(), rng_state)
                self.assertEqual(random.getstate(), global_state)

                run.counts[key] = 2
                stacked = cv.evaluate_card(sim, run, permanent, sim.CARD_BY_KEY[key], 10,
                                           config, phase="guaranteed")
                self.assertTrue(math.isfinite(stacked["total_pe"]))

    def test_snapshot_deltas_are_the_existing_card_effects(self):
        expectations = {
            "steady_force": ("log_damage", math.log10(1.15)),
            "heavy_blow": ("log_attack", math.log10(1.40)),
            "critical_eye": ("crit_chance", 0.10),
            "precise_strike": ("crit_chance", 0.15),
        }
        for key, (attribute, expected) in expectations.items():
            with self.subTest(key=key):
                run, permanent, config = self.state()
                before = sim.compute_snapshot(run, permanent, True, config)
                candidate = copy.deepcopy(run)
                sim.acquire_card(candidate, sim.CARD_BY_KEY[key])
                after = sim.compute_snapshot(candidate, permanent, True, config)
                if attribute == "log_attack":
                    actual = after.base_attack_power - before.base_attack_power
                elif attribute == "log_damage":
                    actual = after.log_dps - before.log_dps
                else:
                    actual = getattr(after, attribute) - getattr(before, attribute)
                self.assertAlmostEqual(actual, expected, places=10)

    def test_drawbacks_are_not_amplified_by_refinement_or_limit_effects(self):
        for key, expected_as_ratio in (("heavy_blow", .90), ("precise_strike", .95)):
            with self.subTest(key=key):
                run, permanent, config = self.state()
                run.counts["limit_break"] = 1
                run.counts["limit_shatter"] = 1
                run.card_upgrades[key] = 3
                before = sim.compute_snapshot(run, permanent, True, config)
                candidate = copy.deepcopy(run)
                sim.acquire_card(candidate, sim.CARD_BY_KEY[key])
                after = sim.compute_snapshot(candidate, permanent, True, config)
                self.assertAlmostEqual(after.attack_speed / before.attack_speed,
                                       expected_as_ratio, places=10)
                amp = sim.limit_amplification(candidate.counts)
                if key == "heavy_blow":
                    expected_atk_add = .40 * amp * 1.30
                    self.assertAlmostEqual(after.base_attack_power - before.base_attack_power,
                                           math.log10(1 + expected_atk_add), places=10)
                else:
                    self.assertAlmostEqual(after.crit_chance - before.crit_chance,
                                           .15 * amp * 1.30, places=10)

    def test_crit_boundaries_and_multicrit_remain_finite(self):
        states = (
            (0.099999, {"critical_power": (0.099999 - .01) / .03}),
            (.10, {"critical_power": 3}),
            (.199999, {"critical_eye": 1, "critical_power": (.199999 - .11) / .03}),
            (.20, {"critical_eye": 1, "critical_power": 3}),
            (.249999, {"precise_strike": 1, "critical_power": (.249999 - .16) / .03}),
            (.25, {"precise_strike": 1, "critical_power": 3}),
            (.999999, {"precise_strike": 6, "critical_power": (.999999 - .91) / .03}),
            (1.0, {"precise_strike": 6, "critical_power": 3}),
            (1.25, {"precise_strike": 7, "critical_power": 3, "critical_eye": 1}),
            (2.0, {"precise_strike": 12, "critical_power": 3, "critical_eye": 1}),
        )
        for expected_rate, cards in states:
            for multi in (False, True):
                with self.subTest(crit_rate=expected_rate, multi_crit=multi):
                    run, permanent, config = self.state(multi_crit=multi)
                    run.counts.update(cards)
                    base = sim.compute_snapshot(run, permanent, True, config)
                    self.assertAlmostEqual(base.crit_chance, expected_rate, places=9)
                    for key in ("critical_eye", "precise_strike", "critical_power", "sharpened_edge"):
                        value = cv.evaluate_card(sim, run, permanent, sim.CARD_BY_KEY[key], 10,
                                                 config, phase="guaranteed")
                        self.assertTrue(math.isfinite(value["total_pe"]))
                    candidate = copy.deepcopy(run)
                    sim.acquire_card(candidate, sim.CARD_BY_KEY["critical_eye"])
                    upgraded = sim.compute_snapshot(candidate, permanent, True, config)
                    self.assertGreaterEqual(upgraded.crit_chance, base.crit_chance)
                    self.assertTrue(math.isfinite(upgraded.log_dps))

    def test_multi_copy_marginal_pe_is_finite_and_decreases_or_stays_valid(self):
        for key in ("steady_force", "heavy_blow", "critical_eye", "precise_strike"):
            immediate = []
            for owned in (0, 1, 2):
                run, permanent, config = self.state(crit_cards=0)
                run.counts[key] = owned
                result = cv.evaluate_card(sim, run, permanent, sim.CARD_BY_KEY[key], 10,
                                          config, phase="guaranteed")
                immediate.append(result["immediate_combat_pe"])
                forecast = cv.predict_run_end(sim, run, permanent, 10, config, "guaranteed")
                expected = []
                for frame in forecast.frames:
                    base = sim.compute_snapshot(frame.run, frame.permanent,
                                                frame.wave % 10 == 0, config)
                    candidate = copy.deepcopy(frame.run)
                    sim.acquire_card(candidate, sim.CARD_BY_KEY[key])
                    after = sim.compute_snapshot(candidate, frame.permanent,
                                                 frame.wave % 10 == 0, config)
                    expected.append(after.log_dps - base.log_dps)
                self.assertAlmostEqual(result["immediate_combat_pe"],
                                       sum(expected) / len(expected), places=10, msg=key)
                self.assertTrue(math.isfinite(result["total_pe"]), key)
            self.assertTrue(all(math.isfinite(value) for value in immediate), key)

    def test_take_path_evaluates_supported_key_and_falls_back_for_other_legal_unsupported(self):
        hand = [sim.CARD_BY_KEY[key] for key in ("steady_force", "heavy_blow", "overclock")]
        run = sim.RunState(card_count=3, kills=9, weapon=True, weapon_power=1.0)
        permanent = sim.PermanentState(atk=100, attack_speed=10, max_wave=9)
        rng = random.Random(3344)
        from unittest.mock import patch
        old_enabled = sim.TAKE_BRANCH_ENABLED
        sim.TAKE_BRANCH_ENABLED = True
        sim.TAKE_BRANCH_ROWS.clear()
        sim.TAKE_BRANCH_CONTEXT.clear()
        try:
            with patch.object(sim, "draw_hand", return_value=hand), \
                    patch.object(sim, "card_score", side_effect=lambda profile, card, *args: {
                        "steady_force": 1.0, "heavy_blow": 2.0, "overclock": 3.0}[card.key]):
                sim.choose_card(rng, "balanced", run, permanent, 10,
                                sim.SimConfig(target_wave=10, take_mode="pe"),
                                allow_reroll=False)
        finally:
            sim.TAKE_BRANCH_ENABLED = old_enabled
        # The legal unsupported Overclock makes the entire hand use legacy.
        self.assertEqual(run.counts["overclock"], 1)
        self.assertEqual(sim.TAKE_BRANCH_ROWS[-1]["decision_source"], "fallback_legacy")
        self.assertIn("unsupported_card:overclock", sim.TAKE_BRANCH_ROWS[-1]["fallback_reason"])
        sim.TAKE_BRANCH_ROWS.clear()
        sim.TAKE_BRANCH_CONTEXT.clear()

    def test_take_path_does_not_mark_stage_keys_unsupported(self):
        hand = [sim.CARD_BY_KEY[key] for key in ("steady_force", "heavy_blow", "precise_strike")]
        run, permanent, _ = self.state()
        old_enabled = sim.TAKE_BRANCH_ENABLED
        sim.TAKE_BRANCH_ENABLED = True
        sim.TAKE_BRANCH_ROWS.clear()
        sim.TAKE_BRANCH_CONTEXT.clear()
        from unittest.mock import patch
        try:
            with patch.object(sim, "draw_hand", return_value=hand):
                sim.choose_card(random.Random(773), "balanced", run, permanent, 10,
                                sim.SimConfig(target_wave=10, take_mode="pe"),
                                allow_reroll=False)
            row = sim.TAKE_BRANCH_ROWS[-1]
            self.assertEqual(row["decision_source"], "pe")
            self.assertEqual(row["evaluated_pe_keys"], [card.key for card in hand])
            self.assertTrue(all(candidate["pe_status"] == "ok" for candidate in row["candidates"]))
            self.assertIn(row["selected_card"], row["eligible_keys"])
        finally:
            sim.TAKE_BRANCH_ENABLED = old_enabled
            sim.TAKE_BRANCH_ROWS.clear()
            sim.TAKE_BRANCH_CONTEXT.clear()


if __name__ == "__main__":
    unittest.main()
