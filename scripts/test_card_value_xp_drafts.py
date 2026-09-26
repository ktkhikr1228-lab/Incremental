"""XP draft timing, legal-pool, and shadow-only acceptance checks."""
import copy
import math
import random
import unittest
from unittest.mock import patch

import card_value_v01 as cv
import simulate_first_prestige_v1 as sim


def fixed_frames(waves, xp_gains, *, card_count=3):
    permanent = sim.PermanentState(atk=12, attack_speed=4, max_wave=1)
    config = sim.SimConfig(target_wave=max(waves) + 1)
    frames = []
    for wave, gained in zip(waves, xp_gains):
        run = sim.RunState(kills=wave - 1, card_count=card_count,
                           weapon=True, xp_level_count=2)
        snapshot = sim.compute_snapshot(run, permanent, wave % 10 == 0, config)
        frames.append(cv.Frame(wave, snapshot, run, permanent, gained, 0))
    forecast = cv.Forecast(waves[-1], "prestige", tuple(frames), 0, 0, 0, 0,
                           len(frames), 0, 0, "low", None)
    return forecast, config


class XPDraftHAcceptance(unittest.TestCase):
    def test_identical_level_wave_state_and_pool_cancel_exactly(self):
        forecast, config = fixed_frames([1, 2, 3, 4], [1] * 4)
        states = [frame.run for frame in forecast.frames]
        event = (1, 2, 0, 0)  # Same level and Wave in both trajectories.
        baseline_pool = {}
        candidate_pool = {}
        baseline = cv._xp_draft_value(sim, forecast, 2, event, states, [0] * 4,
                                      config, baseline_pool)
        candidate = cv._xp_draft_value(sim, forecast, 2, event, states, [0] * 4,
                                       config, candidate_pool)
        self.assertEqual(baseline_pool, candidate_pool)
        self.assertGreater(baseline, 0)
        self.assertEqual(candidate - baseline, 0.0)

    def test_integrated_early_level20_matches_independent_suffix_values(self):
        allowed = {"power_up", "rapid_fire", "steady_force"}
        config = sim.SimConfig(target_wave=900,
                               disabled_card_keys=frozenset(card.key for card in sim.CARDS
                                                            if card.key not in allowed))
        permanent = sim.PermanentState(atk=12, attack_speed=4, max_wave=599,
                                       relic_unlocked=True)
        frames = []
        level = 20
        cost = sim.CARD_COSTS[level]
        for wave in range(600, 901):
            # Baseline acquires exactly 0.25 XP on W600 and 0.75 on W700.
            # Candidate's one-XP W600 reward is injected below. No future
            # card identities or equipment changes are placed in the frames.
            balance = cost - 1 if wave == 600 else (cost - 0.75 if wave <= 700 else 0)
            state = sim.RunState(kills=wave - 1, xp=balance,
                                 xp_level_count=level if wave <= 700 else level + 1,
                                 card_count=4, weapon=True)
            gained = 0.25 if wave == 600 else (0.75 if wave == 700 else 0.0)
            snap = sim.compute_snapshot(state, permanent, wave % 10 == 0, config)
            frames.append(cv.Frame(wave, snap, state, permanent, gained, 0))
        forecast = cv.Forecast(900, "prestige", tuple(frames), 0, 1, 1, 1,
                               270, 27, 4, "low", None)

        def candidate_gain(simulator, run, snapshot, wave, config, quick):
            return 1.0 if wave == 600 else 0.0

        with patch.object(cv, "_xp_gain", side_effect=candidate_gain):
            result = cv.evaluate_card(sim, frames[0].run, permanent,
                                      sim.CARD_BY_KEY["experience"], 600, config,
                                      phase="guaranteed", forecast=forecast)
        self.assertEqual(result["remaining_encounters"], 301)
        self.assertEqual(len(result["xp_draft_events"]), 1)
        event = result["xp_draft_events"][0]
        self.assertEqual((event["level"], event["candidate_wave"], event["baseline_wave"]),
                         (20, 600, 700))
        self.assertEqual(set(event["candidate_pool"]["pool_keys"]), allowed)
        self.assertEqual(event["baseline_pool"]["pool_keys"], event["candidate_pool"]["pool_keys"])

        def independent_value(after_wave, candidate):
            # Independent direct Snapshot sums over every remaining encounter.
            # Exactly three legal distinct cards make the best hand's value
            # the maximum of the three raw suffix values.
            totals = []
            for key in sorted(allowed):
                raw = 0.0
                for frame in frames:
                    if frame.wave <= after_wave:
                        continue
                    before_state = copy.deepcopy(frame.run)
                    if candidate:
                        sim.acquire_card(before_state, sim.CARD_BY_KEY["experience"])
                    before = sim.compute_snapshot(before_state, permanent,
                                                  frame.wave % 10 == 0, config)
                    after_state = copy.deepcopy(before_state)
                    sim.acquire_card(after_state, sim.CARD_BY_KEY[key])
                    after = sim.compute_snapshot(after_state, permanent,
                                                 frame.wave % 10 == 0, config)
                    raw += after.log_dps - before.log_dps
                totals.append(raw / len(frames))
            return max(0.0, *totals)

        early = independent_value(600, candidate=True)
        late = independent_value(700, candidate=False)
        self.assertGreater(early, late)
        self.assertAlmostEqual(event["candidate_value"], early, delta=1e-10)
        self.assertAlmostEqual(event["baseline_value"], late, delta=1e-10)
        self.assertAlmostEqual(result["xp_pe"], early - late, delta=1e-10)
        self.assertEqual(result["growth_pe"], 0)
        self.assertAlmostEqual(result["total_pe"], 0.15 * result["xp_pe"], delta=1e-10)

    def test_threshold_before_after_and_paid_choice_phase(self):
        forecast, _ = fixed_frames([1, 2, 3], [1, 1, 1])
        just_before = cv._xp_draft_timeline(sim, forecast, 3, 2, [2, 1, 1])[0]
        self.assertEqual(just_before[0][2][1], 2)
        self.assertEqual(just_before[1][2][1], 1)
        self.assertEqual(just_before[0][2][0], 1)  # Baseline catches up on W2.
        self.assertEqual(just_before[1][2][0], 0)  # Candidate gets W1.
        just_after = cv._xp_draft_timeline(sim, forecast, 4, 2, [2, 1, 1])[0]
        self.assertEqual(just_after[0][2][0], 0)
        self.assertEqual(just_after[1][2][0], 0)
        run = sim.RunState(xp=4, xp_level_count=1)
        normalized, _ = cv._start(sim, run, sim.PermanentState(), "xp")
        self.assertEqual(normalized.xp_level_count, 2)
        self.assertEqual(normalized.xp, 4)  # Already paid: never pay the active draft again.
        self.assertEqual(run.xp_level_count, 1)

    def test_multiple_levels_from_one_kill_keep_all_costs_and_ordinals(self):
        forecast, _ = fixed_frames([1, 2], [100, 0])
        events, _ = cv._xp_draft_timeline(sim, forecast, 0, 0, [100, 0])
        expected = 0
        remaining = 100
        while expected < len(sim.CARD_COSTS) and remaining >= sim.CARD_COSTS[expected]:
            remaining -= sim.CARD_COSTS[expected]
            expected += 1
        self.assertGreater(expected, 2)
        self.assertEqual(list(events[0]), list(range(expected)))
        self.assertEqual(list(events[1]), list(range(expected)))
        self.assertEqual([event[3] for event in events[0].values()], list(range(expected)))
        self.assertTrue(all(event[1] == 1 for event in events[0].values()))
        self.assertAlmostEqual(events[0][expected - 1][2], remaining)

    def test_cost_array_tail_and_already_maxed_out(self):
        last = len(sim.CARD_COSTS) - 1
        # The final cost is ~4e23, so a one-XP change is below float ULP.
        ulp = math.ulp(float(sim.CARD_COSTS[last]))
        step = ulp * 32
        forecast, _ = fixed_frames([1, 2], [step / 2, step / 2 + 2 * ulp])
        near = cv._xp_draft_timeline(sim, forecast, float(sim.CARD_COSTS[last]) - step, last,
                                      [step + 2 * ulp, 0])[0]
        self.assertEqual(set(near[0]), {last})
        self.assertEqual(set(near[1]), {last})
        self.assertEqual(near[0][last][1], 2)
        self.assertEqual(near[1][last][1], 1)
        maxed = cv._xp_draft_timeline(sim, forecast, 1e40, len(sim.CARD_COSTS),
                                       [1e40, 1e40])[0]
        self.assertEqual(maxed, [{}, {}])

    def test_early_draft_beats_late_with_same_pool_and_future_effect(self):
        forecast, config = fixed_frames(list(range(1, 7)), [1] * 6)
        states = [frame.run for frame in forecast.frames]
        ledger = [0] * len(states)
        early = cv._xp_draft_value(sim, forecast, 2, (0, 1, 0, 0), states, ledger, config)
        late = cv._xp_draft_value(sim, forecast, 2, (2, 3, 0, 0), states, ledger, config)
        at_end = cv._xp_draft_value(sim, forecast, 2, (5, 6, 0, 0), states, ledger, config)
        self.assertGreater(early, late)
        self.assertGreater(late, 0)
        self.assertEqual(at_end, 0)

    def test_value_uses_future_snapshots_not_only_acquisition_snapshot(self):
        allowed = {"power_up", "rapid_fire", "steady_force"}
        config = sim.SimConfig(target_wave=7,
                               disabled_card_keys=frozenset(card.key for card in sim.CARDS
                                                            if card.key not in allowed))
        permanent = sim.PermanentState(atk=12, attack_speed=4, max_wave=1)
        original = []
        for wave in range(1, 5):
            run = sim.RunState(kills=wave - 1, card_count=3, weapon=True,
                               xp_level_count=2)
            original.append(cv.Frame(wave, sim.compute_snapshot(run, permanent, False, config),
                                     run, permanent, 1, 0))
        altered = copy.deepcopy(original)
        for frame in altered[2:]:
            # Acquisition state (W1/W2) and legal hand are identical. Only
            # later encounters make Power Up's marginal return smaller.
            frame.run.counts["power_up"] = 200
            frame.run.tag_counts["atk"] = 200
        def value(frames):
            forecast = cv.Forecast(4, "prestige", tuple(frames), 0, 0, 0, 0,
                                   4, 0, 0, "low", None)
            return cv._xp_draft_value(sim, forecast, 2, (0, 1, 0, 0),
                                      [frame.run for frame in frames], [0] * 4, config)
        self.assertGreater(value(original), value(altered) + 1e-3)

    def test_multiple_drafts_contribute_separately_to_xp_axis(self):
        config = sim.SimConfig(target_wave=6)
        run = sim.RunState(kills=0, xp=20, xp_level_count=2, card_count=3, weapon=True)
        permanent = sim.PermanentState(atk=12, attack_speed=4, max_wave=0)
        result = cv.evaluate_card(sim, run, permanent, sim.CARD_BY_KEY["experience"],
                                  1, config, phase="guaranteed")
        simultaneous = [event for event in result["xp_draft_events"]
                        if event["candidate_wave"] == 1]
        self.assertGreaterEqual(len(simultaneous), 2)
        self.assertEqual(len({event["level"] for event in simultaneous}), len(simultaneous))
        self.assertAlmostEqual(result["xp_pe"],
                               sum(event["xp_delta"] for event in result["xp_draft_events"]))
        self.assertEqual(result["growth_pe"], 0)

    def test_unique_disabled_overdrive_unlock_and_no_duplicate_hand(self):
        permanent = sim.PermanentState(max_wave=500)
        run = sim.RunState(kills=500, card_count=4)
        values = {card.key: 0.0 for card in sim.CARDS}
        values["execution"] = 3.0
        values["time_collapse"] = 2.0
        values["perfect_overdrive"] = 4.0
        values["final_equation"] = 5.0
        allowed = {"execution", "power_up", "rapid_fire"}
        only_three = sim.SimConfig(disabled_card_keys=frozenset(values.keys() - allowed))
        # Three choices are distinct: with exactly three legal options the
        # positive unique is present once, regardless of rolled rarities.
        self.assertAlmostEqual(cv._expected_draft_best(sim, run, permanent, only_three, values), 3.0)
        owned = copy.deepcopy(run)
        owned.counts["execution"] = 1
        self.assertEqual(cv._expected_draft_best(sim, owned, permanent, only_three, values), 0.0)
        all_legal = sim.SimConfig()
        run.allow_overdrive = False
        self.assertNotIn("perfect_overdrive", [item.key for item in
                         sim.available_cards("L", run, permanent, all_legal)])
        self.assertNotIn("final_equation", [item.key for item in
                         sim.available_cards("L", run, permanent, all_legal)])
        before_unlock = sim.RunState(kills=499, card_count=4)
        self.assertNotIn("time_collapse", [item.key for item in
                         sim.available_cards("E", before_unlock, sim.PermanentState(max_wave=499), all_legal)])
        self.assertIn("time_collapse", [item.key for item in
                      sim.available_cards("E", run, permanent, all_legal)])

    def test_candidate_and_baseline_pool_values_are_separate_even_same_wave(self):
        values = {card.key: 0.0 for card in sim.CARDS}
        values["execution"] = 1.0
        allowed = {"execution", "power_up", "rapid_fire"}
        config = sim.SimConfig(disabled_card_keys=frozenset(values.keys() - allowed))
        permanent = sim.PermanentState(max_wave=500)
        baseline = sim.RunState(kills=500, card_count=4)
        candidate = copy.deepcopy(baseline)
        candidate.counts["execution"] = 1
        base_value = cv._expected_draft_best(sim, baseline, permanent, config, values)
        candidate_value = cv._expected_draft_best(sim, candidate, permanent, config, values)
        self.assertAlmostEqual(base_value, 1.0)
        self.assertEqual(candidate_value, 0.0)
        self.assertEqual(candidate_value - base_value, -1.0)

    def test_candidate_order_independent_and_no_rng_or_state_mutation(self):
        config = sim.SimConfig(target_wave=15)
        run = sim.RunState(kills=9, xp=3, xp_level_count=2, card_count=3, weapon=True)
        permanent = sim.PermanentState(atk=12, attack_speed=4, max_wave=9)
        forecast = cv.predict_run_end(sim, run, permanent, 10, config, "guaranteed")
        original_run, original_permanent = copy.deepcopy(run), copy.deepcopy(permanent)
        global_state = random.getstate()

        def evaluate(order):
            return {key: cv.evaluate_card(sim, run, permanent, sim.CARD_BY_KEY[key], 10,
                                          config, phase="guaranteed", forecast=forecast)
                    for key in order}

        forward = evaluate(("experience", "scholar", "fast_learner"))
        backward = evaluate(("fast_learner", "scholar", "experience"))
        self.assertEqual(forward, backward)
        self.assertEqual(run, original_run)
        self.assertEqual(permanent, original_permanent)
        self.assertEqual(random.getstate(), global_state)
        same_wave = [event for event in forward["experience"]["xp_draft_events"]
                     if event["baseline_wave"] == event["candidate_wave"]
                     and event["baseline_wave"] is not None
                     and event["baseline_value"] != event["candidate_value"]]
        self.assertTrue(same_wave)  # Both states, not the candidate's pool twice.
        for result in forward.values():
            self.assertAlmostEqual(result["xp_pe"],
                                   sum(event["xp_delta"] for event in result["xp_draft_events"]))
            self.assertAlmostEqual(result["total_pe"],
                                   0.60 * (result["immediate_combat_pe"] + result["conditional_combat_pe"])
                                   + 0.25 * result["growth_pe"] + 0.15 * result["xp_pe"])

    def test_shadow_toggle_preserves_forced_xp_choice_trial_and_rng(self):
        old_limit = sim.SHADOW_CARD_VALUE_LIMIT
        old_hook = sim.record_card_decision
        def forced(shadow):
            sim.SHADOW_CARD_VALUE_ROWS.clear()
            sim.SHADOW_CARD_VALUE_LIMIT = 3 if shadow else 0
            rng = random.Random(238)
            run = sim.RunState(kills=9, xp_level_count=2, card_count=3, weapon=True)
            permanent = sim.PermanentState(atk=12, attack_speed=4, max_wave=9)
            global_rng = random.getstate()
            sim.choose_card(rng, "balanced", run, permanent, 10, sim.SimConfig(target_wave=20),
                            forced_rarity="C", forced_card="experience")
            self.assertEqual(random.getstate(), global_rng)
            return copy.deepcopy(run), copy.deepcopy(permanent), rng.getstate(), copy.deepcopy(sim.SHADOW_CARD_VALUE_ROWS)

        def trial(shadow):
            sim.SHADOW_CARD_VALUE_ROWS.clear()
            sim.SHADOW_CARD_VALUE_LIMIT = 8 if shadow else 0
            choices = []
            def recorder(permanent, item, rerolls_used, automated=False):
                choices.append((item.key, rerolls_used, automated))
                return old_hook(permanent, item, rerolls_used, automated)
            sim.record_card_decision = recorder
            rng = random.Random(112233)
            global_rng = random.getstate()
            result = sim.run_trial(rng, "balanced", sim.SimConfig(target_wave=50, max_attempts=3), True)
            self.assertEqual(random.getstate(), global_rng)
            return result, rng.getstate(), choices, copy.deepcopy(sim.SHADOW_CARD_VALUE_ROWS)

        try:
            off, on = forced(False), forced(True)
            self.assertEqual(off[:3], on[:3])
            self.assertFalse(off[3])
            self.assertTrue(any(row["card_id"] == "experience" for row in on[3]))
            trial_off, trial_on = trial(False), trial(True)
            self.assertEqual(trial_off[:3], trial_on[:3])
            self.assertGreater(trial_off[0].attempts, 1)
            self.assertTrue(any(row["card_id"] in cv.XP_DRAFT_KEYS for row in trial_on[3]))
        finally:
            sim.SHADOW_CARD_VALUE_LIMIT = old_limit
            sim.SHADOW_CARD_VALUE_ROWS.clear()
            sim.record_card_decision = old_hook


if __name__ == "__main__":
    unittest.main()
