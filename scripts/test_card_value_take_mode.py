"""Take-only PE mode: legacy action gates and eligible-hand fallback."""
import copy
import math
import random
import unittest
from unittest.mock import patch

import card_value_v01 as cv
import run_card_value_take_experiment as experiment
import simulate_first_prestige_v1 as sim


class TakeModeTests(unittest.TestCase):
    def setUp(self):
        self.old_log = sim.TAKE_BRANCH_ENABLED
        self.old_limit = sim.SHADOW_CARD_VALUE_LIMIT
        sim.SHADOW_CARD_VALUE_LIMIT = 0
        sim.TAKE_BRANCH_ENABLED = True
        sim.TAKE_BRANCH_ROWS.clear()
        sim.TAKE_BRANCH_CONTEXT.clear()

    def tearDown(self):
        sim.TAKE_BRANCH_ENABLED = self.old_log
        sim.SHADOW_CARD_VALUE_LIMIT = self.old_limit
        sim.TAKE_BRANCH_ROWS.clear()
        sim.TAKE_BRANCH_CONTEXT.clear()

    def choose(self, mode, hand, legacy, pe, *, wave=1, run=None, permanent=None, hands=None,
               evaluated_keys=None):
        sim.TAKE_BRANCH_CONTEXT.clear()
        run = run or sim.RunState(card_count=3, kills=wave - 1)
        permanent = permanent or sim.PermanentState(max_wave=wave - 1)
        rng = random.Random(101)
        before = rng.getstate()
        def evaluate(simulator, state, perm, card, *args, **kwargs):
            if evaluated_keys is not None:
                evaluated_keys.append(card.key)
            return {"total_pe": pe[card.key]}
        with patch.object(sim, "draw_hand", side_effect=hands or [hand]), \
             patch.object(sim, "card_score", side_effect=lambda profile, item, *args: legacy[item.key]), \
             patch.object(cv, "predict_run_end", return_value=object()), \
             patch.object(cv, "evaluate_card", side_effect=evaluate):
            sim.choose_card(rng, "balanced", run, permanent, wave,
                            sim.SimConfig(target_wave=max(wave, 2), take_mode=mode))
        self.assertEqual(rng.getstate(), before)
        return run, permanent, copy.deepcopy(sim.TAKE_BRANCH_ROWS[-1])

    def test_pe_changes_only_final_take_with_deterministic_hand_order_tie(self):
        hand = [sim.CARD_BY_KEY[key] for key in ("power_up", "rapid_fire", "experience")]
        legacy = {"power_up": 1.3, "rapid_fire": 1.2, "experience": 1.1}
        pe = {"power_up": 0.1, "rapid_fire": 0.4, "experience": 0.4}
        old, _, old_log = self.choose("legacy", hand, legacy, pe)
        sim.TAKE_BRANCH_ROWS.clear()
        new, _, new_log = self.choose("pe", hand, legacy, pe)
        self.assertEqual(old.counts["power_up"], 1)
        self.assertEqual(new.counts["rapid_fire"], 1)  # Equal PE: first in hand.
        self.assertEqual(new_log["decision_source"], "pe")
        self.assertEqual(old_log["legacy_winner"], new_log["legacy_winner"])
        self.assertEqual([entry["pe_status"] for entry in new_log["candidates"]], ["ok"] * 3)
        self.assertEqual(new_log["pre_decision_rng_digest"], old_log["pre_decision_rng_digest"])

    def test_unsupported_or_nonfinite_card_falls_back_whole_hand(self):
        for keys, pe, reason in (
            (("power_up", "growth_engine", "rapid_fire"),
             {"power_up": 100.0, "rapid_fire": 2.0}, "unsupported_card"),
            (("power_up", "rapid_fire", "experience"),
             {"power_up": 100.0, "rapid_fire": math.nan, "experience": 1.0}, "invalid_total_pe"),
            (("power_up", "rapid_fire", "experience"),
             {"power_up": 100.0, "rapid_fire": None, "experience": 1.0}, "invalid_total_pe"),
        ):
            with self.subTest(reason=reason, keys=keys):
                hand = [sim.CARD_BY_KEY[key] for key in keys]
                legacy = {key: 1.2 - index * .1 for index, key in enumerate(keys)}
                run, _, row = self.choose("pe", hand, legacy, pe)
                self.assertEqual(row["decision_source"], "fallback_legacy")
                self.assertIn(reason, row["fallback_reason"])
                self.assertEqual(run.counts[keys[0]], 1)

    def test_ineligible_starter_card_never_blocks_or_receives_pe_evaluation(self):
        for third, value in (("battle_focus", 1.0),
                             ("experience", None),
                             ("experience", math.nan),
                             ("experience", 1000.0)):
            with self.subTest(third=third):
                hand = [sim.CARD_BY_KEY[key] for key in ("power_up", "rapid_fire", third)]
                legacy = {"power_up": 1.3, "rapid_fire": 1.2, third: .1}
                pe = {"power_up": .1, "rapid_fire": 10.0, third: value}
                evaluated = []
                run, _, row = self.choose("pe", hand, legacy, pe, run=sim.RunState(),
                                          evaluated_keys=evaluated)
                self.assertTrue(row["starter"])
                self.assertEqual(row["hand_keys"], ["power_up", "rapid_fire", third])
                self.assertEqual(row["eligible_keys"], ["power_up", "rapid_fire"])
                self.assertEqual(row["ineligible_keys"], [third])
                self.assertEqual(row["evaluated_pe_keys"], ["power_up", "rapid_fire"])
                self.assertEqual(evaluated, ["power_up", "rapid_fire"])
                self.assertEqual(row["candidates"][-1]["pe_status"], "ineligible_take")
                self.assertEqual(row["decision_source"], "pe")
                self.assertIsNone(row["fallback_reason"])
                self.assertEqual(run.counts["rapid_fire"], 1)
                self.assertEqual(run.counts[third], 0)

    def test_unsupported_eligible_falls_back_whole_hand(self):
        hand = [sim.CARD_BY_KEY[key] for key in ("power_up", "overclock", "experience")]
        # The legal unsupported card forces whole-hand fallback.
        legacy = {"power_up": 1.3, "overclock": 1.2, "experience": .1}
        evaluated = []
        run, _, row = self.choose("pe", hand, legacy, {"power_up": 100.0},
                                  run=sim.RunState(card_count=3), evaluated_keys=evaluated)
        self.assertEqual(row["eligible_keys"], ["power_up", "overclock", "experience"])
        self.assertEqual(row["ineligible_keys"], [])
        self.assertEqual(row["decision_source"], "fallback_legacy")
        self.assertEqual(row["fallback_reason"], "unsupported_card:overclock")
        self.assertEqual(row["evaluated_pe_keys"], [])
        self.assertEqual(evaluated, [])
        self.assertEqual(run.counts["power_up"], 1)

    def test_ineligible_starter_card_not_evaluated_with_shadow_enabled(self):
        hand = [sim.CARD_BY_KEY[key] for key in ("power_up", "rapid_fire", "experience")]
        legacy = {"power_up": 1.3, "rapid_fire": 1.2, "experience": .1}
        sim.SHADOW_CARD_VALUE_ROWS.clear()
        sim.SHADOW_CARD_VALUE_LIMIT = 3
        evaluated = []
        try:
            _, _, row = self.choose("pe", hand, legacy,
                                    {"power_up": .1, "rapid_fire": .5},
                                    run=sim.RunState(), evaluated_keys=evaluated)
        finally:
            sim.SHADOW_CARD_VALUE_ROWS.clear()
        self.assertEqual(evaluated, ["power_up", "rapid_fire"] * 2)
        self.assertEqual(row["evaluated_pe_keys"], ["power_up", "rapid_fire"])
        self.assertEqual(row["candidates"][-1]["pe_status"], "ineligible_take")

    def test_reroll_uses_only_legacy_threshold_and_exclusions(self):
        first = [sim.CARD_BY_KEY[key] for key in ("power_up", "rapid_fire", "experience")]
        second = [sim.CARD_BY_KEY[key] for key in ("execution", "time_collapse", "fast_learner")]
        legacy = {**dict.fromkeys((item.key for item in first), .2),
                  **dict.fromkeys((item.key for item in second), 1.2)}
        pe = {**dict.fromkeys((item.key for item in first), 999.0),
              **dict.fromkeys((item.key for item in second), 0.1)}
        run, _, row = self.choose("pe", first, legacy, pe, hands=[first, second])
        self.assertEqual(run.counts["execution"], 1)
        self.assertEqual(row["rerolls_used"], 1)
        self.assertEqual([trace["stop_reason"] for trace in row["reroll_trace"]],
                         ["reroll", "threshold"])
        self.assertEqual(row["hand_keys"], [item.key for item in second])

    def test_refine_gate_is_legacy_even_when_pe_favors_take(self):
        hand = [sim.CARD_BY_KEY[key] for key in ("power_up", "rapid_fire", "execution")]
        legacy = {"power_up": .40, "rapid_fire": .30, "execution": .20}
        pe = {"power_up": 0.0, "rapid_fire": 0.0, "execution": 10.0}
        run, _, row = self.choose("pe", hand, legacy, pe, wave=500,
                                  run=sim.RunState(card_count=3, kills=499),
                                  permanent=sim.PermanentState(max_wave=500),
                                  hands=[hand, hand])
        self.assertTrue(row["legacy_refine_gate"])
        self.assertEqual(row["action"], "refine")
        self.assertEqual(row["decision_source"], "legacy")
        self.assertEqual(run.counts["execution"], 0)
        self.assertEqual(run.cards_dissolved["R"], 1)
        self.assertTrue(all(entry["pe_status"] == "not_evaluated" for entry in row["candidates"]))

    def test_legacy_take_gate_does_not_reconsider_pe_winner_for_refine(self):
        hand = [sim.CARD_BY_KEY[key] for key in ("power_up", "rapid_fire", "experience")]
        legacy = {"power_up": 1.3, "rapid_fire": 0.1, "experience": 0.0}
        pe = {"power_up": 0.0, "rapid_fire": 1.0, "experience": 0.1}
        run, _, row = self.choose("pe", hand, legacy, pe, wave=500,
                                  run=sim.RunState(card_count=3, kills=499),
                                  permanent=sim.PermanentState(max_wave=500))
        self.assertEqual(row["action"], "take")
        self.assertEqual(run.counts["rapid_fire"], 1)
        self.assertFalse(row["legacy_refine_gate"])

    def test_identical_take_keeps_legacy_upgrade_and_state(self):
        hand = [sim.CARD_BY_KEY[key] for key in ("power_up", "rapid_fire", "experience")]
        legacy = {"power_up": 1.3, "rapid_fire": 1.2, "experience": 1.1}
        pe = {"power_up": 2.0, "rapid_fire": 1.0, "experience": .1}
        start = sim.RunState(card_count=3, kills=499, card_points=5)
        start.counts["power_up"] = 1
        first, old_perm, old_log = self.choose("legacy", hand, legacy, pe, wave=500,
                                               run=copy.deepcopy(start),
                                               permanent=sim.PermanentState(max_wave=500))
        sim.TAKE_BRANCH_ROWS.clear()
        second, new_perm, new_log = self.choose("pe", hand, legacy, pe, wave=500,
                                                run=copy.deepcopy(start),
                                                permanent=sim.PermanentState(max_wave=500))
        self.assertEqual(first, second)
        self.assertEqual(old_perm, new_perm)
        self.assertEqual(first.card_upgrades["power_up"], 1)
        self.assertEqual(old_log["upgrades"], new_log["upgrades"])

    def test_paired_first_branch_reports_full_pe_hand(self):
        hand = [sim.CARD_BY_KEY[key] for key in ("power_up", "rapid_fire", "experience")]
        legacy = {"power_up": 1.3, "rapid_fire": 1.2, "experience": 1.1}
        pe = {"power_up": 0.1, "rapid_fire": 0.3, "experience": 0.2}
        _, _, old = self.choose("legacy", hand, legacy, pe)
        sim.TAKE_BRANCH_ROWS.clear()
        _, _, new = self.choose("pe", hand, legacy, pe)
        branch = experiment.first_divergence([old], [new])
        self.assertEqual(branch["kind"], "selection_divergence")
        self.assertEqual((branch["legacy"]["selected_card"], branch["pe"]["selected_card"]),
                         ("power_up", "rapid_fire"))
        self.assertEqual({entry["card_id"] for entry in branch["pe"]["candidates"]},
                         {item.key for item in hand})
        self.assertEqual(experiment.first_divergence([old], [old]), None)

    def test_report_accepts_pe_take_with_ineligible_unscored_card(self):
        hand = [sim.CARD_BY_KEY[key] for key in ("power_up", "rapid_fire", "battle_focus")]
        legacy = {"power_up": 1.3, "rapid_fire": 1.2, "battle_focus": .1}
        pe = {"power_up": .1, "rapid_fire": .5}
        _, _, old = self.choose("legacy", hand, legacy, pe, run=sim.RunState())
        _, _, new = self.choose("pe", hand, legacy, pe, run=sim.RunState())
        old.update({"attempt": 1, "trial_index": 0})
        new.update({"attempt": 1, "trial_index": 0})
        pair = {"trial_index": 0, "results": {mode: {"first_reached": 1, "attempts": 1}
                                                for mode in ("legacy", "pe")},
                "branches": {"legacy": [old], "pe": [new]},
                "take_opportunities": 1, "pe_applied": 1, "fallback_count": 0,
                "first_divergence": experiment.first_divergence([old], [new])}
        summary, report = experiment.build_report(101, 1, [pair])
        self.assertEqual(summary["red_flags"], [])
        self.assertEqual(summary["pe_applied"], 1)
        self.assertIn("| battle_focus | no |", report)
        self.assertIn("ineligible_take", report)

    def test_report_separates_zero_and_positive_pe_ties_and_old_spec_delta(self):
        hand = [sim.CARD_BY_KEY[key] for key in ("power_up", "rapid_fire", "experience")]
        legacy = {"power_up": 1.3, "rapid_fire": 1.2, "experience": 1.1}
        pairs = []
        for trial_index, pe in enumerate((
                {"power_up": -.1, "rapid_fire": 0.0, "experience": 0.0},
                {"power_up": .1, "rapid_fire": .3, "experience": .3})):
            _, _, row = self.choose("pe", hand, legacy, pe)
            row.update({"trial_index": trial_index, "attempt": 1, "decision_index": 1})
            row["candidates"][1].update({"immediate_combat_pe": .2,
                                          "conditional_combat_pe": .1})
            old_row = copy.deepcopy(row)
            old_row["selected_card"] = "power_up"
            old_row["take_mode"] = "legacy"
            pairs.append({"trial_index": trial_index, "branches": {"pe": [row], "legacy": [old_row]},
                          "first_divergence": {"kind": "selection_divergence",
                                               "legacy": old_row, "pe": row}, "take_opportunities": 1,
                          "pe_applied": 1, "fallback_count": 0})
        old = {"pe_applied": 54, "pe_take_opportunities": 1477, "fallback_count": 1423}
        summary, report = experiment.build_report(20260828, 10, pairs, old)
        self.assertEqual(summary["tie_counts"], {"zero_pe": 1, "positive": 1, "negative": 0})
        self.assertEqual(summary["exact_tie_counts"], {"zero_pe": 1, "positive": 1, "negative": 0})
        self.assertEqual(summary["red_flags"], [])
        self.assertEqual(summary["old_spec_comparison"]["applied_delta"], -52)
        self.assertIn("| rapid_fire | yes |", report)
        self.assertIn("+0.30000 |", report)  # Immediate + Conditional = Combat PE.
        self.assertIn("zero-PE tie 1件、positive tie 1件", report)
        self.assertIn("54/1477", report)

    def test_real_pe_take_is_independent_of_shadow_row_limit(self):
        hand = [sim.CARD_BY_KEY[key] for key in ("power_up", "rapid_fire", "experience")]
        previous_limit = sim.SHADOW_CARD_VALUE_LIMIT
        def once(limit):
            sim.SHADOW_CARD_VALUE_LIMIT = limit
            sim.SHADOW_CARD_VALUE_ROWS.clear()
            sim.TAKE_BRANCH_ROWS.clear()
            sim.TAKE_BRANCH_CONTEXT.clear()
            rng = random.Random(222)
            run = sim.RunState(kills=9, xp=3, xp_level_count=2, card_count=3, weapon=True)
            permanent = sim.PermanentState(atk=12, attack_speed=4, max_wave=9)
            with patch.object(sim, "draw_hand", return_value=hand):
                sim.choose_card(rng, "balanced", run, permanent, 10,
                                sim.SimConfig(target_wave=15, take_mode="pe"),
                                forced_rarity="C")
            return (run, permanent, rng.getstate(), copy.deepcopy(sim.TAKE_BRANCH_ROWS[-1]),
                    len(sim.SHADOW_CARD_VALUE_ROWS))
        try:
            without = once(0)
            with_shadow = once(2)
        finally:
            sim.SHADOW_CARD_VALUE_LIMIT = previous_limit
            sim.SHADOW_CARD_VALUE_ROWS.clear()
        self.assertEqual(without[:4], with_shadow[:4])
        self.assertEqual(without[4], 0)
        self.assertEqual(with_shadow[4], 2)
        self.assertEqual(without[3]["decision_source"], "pe")
        self.assertTrue(all(entry["pe_status"] == "ok" for entry in without[3]["candidates"]))

    def test_pe_branch_logging_does_not_change_trial_or_game_rng(self):
        config = sim.SimConfig(target_wave=50, max_attempts=3, take_mode="pe")
        def capture(logging):
            sim.TAKE_BRANCH_ENABLED = logging
            sim.TAKE_BRANCH_CONTEXT.clear()
            sim.TAKE_BRANCH_ROWS.clear()
            rng = random.Random(112233)
            global_rng = random.getstate()
            result = sim.run_trial(rng, "balanced", config, True)
            self.assertEqual(random.getstate(), global_rng)
            return result, rng.getstate(), copy.deepcopy(sim.TAKE_BRANCH_ROWS)
        off = capture(False)
        on = capture(True)
        self.assertEqual(off[:2], on[:2])
        self.assertEqual(off[2], [])
        self.assertTrue(on[2])


if __name__ == "__main__":
    unittest.main()
