import dataclasses
import random
import unittest

import simulate_first_prestige_v1 as sim
import w5000_v1_profile as profile
import diagnose_w5000_v1_rng_split as diagnosis
import diagnose_w5000_v1_card_rng_split as card_diagnosis


class RNGSplitDiagnosticTests(unittest.TestCase):
    def test_default_shared_rng_result_is_unchanged_by_explicit_shared_streams(self):
        config = dataclasses.replace(profile.build_config(max_attempts=2), target_wave=200)
        seed = 918273
        implicit_rng = random.Random(seed)
        explicit_rng = random.Random(seed)
        implicit = sim.run_trial(implicit_rng, "balanced", config, True)
        explicit = sim.run_trial(
            explicit_rng,
            "balanced",
            config,
            True,
            rng_streams=sim.RNGStreams.shared(explicit_rng),
        )
        self.assertEqual(implicit, explicit)
        self.assertEqual(implicit_rng.getstate(), explicit_rng.getstate())

    def test_split_stream_consumption_is_isolated(self):
        left = sim.make_split_rng_streams(20260828)
        right = sim.make_split_rng_streams(20260828)
        for _ in range(100):
            left.weapon.random()
            left.relic.random()
            left.combat.random()
        self.assertEqual(
            [left.card.random() for _ in range(20)],
            [right.card.random() for _ in range(20)],
        )

    def test_split_stream_derivation_is_deterministic_and_branch_specific(self):
        first = sim.make_split_rng_streams(20260828, branch=7)
        again = sim.make_split_rng_streams(20260828, branch=7)
        other = sim.make_split_rng_streams(20260828, branch=8)
        self.assertEqual(first.card.getstate(), again.card.getstate())
        self.assertNotEqual(first.card.getstate(), other.card.getstate())
        self.assertNotEqual(first.card.getstate(), first.weapon.getstate())

    def test_counterfactual_conditions_share_variable_stream_draws(self):
        saved = sim.make_split_rng_streams(1234)
        capture = {
            "trial": 2,
            "wave": 1250,
            "rng_states": {
                name: getattr(saved, name).getstate()
                for name in ("card", "weapon", "relic", "combat")
            },
        }
        all_variable = diagnosis.replay_streams(capture, "A_all_variable", 3, 99)
        weapon_fixed = diagnosis.replay_streams(capture, "C_weapon_fixed", 3, 99)
        self.assertEqual(all_variable.card.getstate(), weapon_fixed.card.getstate())
        self.assertEqual(all_variable.relic.getstate(), weapon_fixed.relic.getstate())
        self.assertNotEqual(all_variable.weapon.getstate(), weapon_fixed.weapon.getstate())

    def test_explicit_shared_card_substreams_preserve_legacy_result(self):
        config = dataclasses.replace(profile.build_config(max_attempts=2), target_wave=200)
        seed = 741852
        implicit_rng = random.Random(seed)
        explicit_rng = random.Random(seed)
        implicit = sim.run_trial(implicit_rng, "balanced", config, True)
        explicit = sim.run_trial(
            explicit_rng,
            "balanced",
            config,
            True,
            rng_streams=sim.RNGStreams(
                explicit_rng,
                explicit_rng,
                explicit_rng,
                explicit_rng,
                sim.CardRNGStreams.shared(explicit_rng),
            ),
        )
        self.assertEqual(implicit, explicit)
        self.assertEqual(implicit_rng.getstate(), explicit_rng.getstate())

    def test_card_substream_consumption_is_isolated(self):
        left = sim.make_split_card_rng_streams(20260828)
        right = sim.make_split_card_rng_streams(20260828)
        for _ in range(100):
            left.hand.random()
            left.reroll.random()
        self.assertEqual(
            [left.rarity.random() for _ in range(20)],
            [right.rarity.random() for _ in range(20)],
        )

    def test_card_counterfactual_fixed_stream_uses_replicate_zero(self):
        capture = {"trial": 4, "wave": 1250}
        baseline_zero = card_diagnosis.card_streams_for(
            capture, "A_all_card_variable", 0, 20260828
        )
        rarity_fixed = card_diagnosis.card_streams_for(
            capture, "B_rarity_fixed", 5, 20260828
        )
        baseline_five = card_diagnosis.card_streams_for(
            capture, "A_all_card_variable", 5, 20260828
        )
        self.assertEqual(baseline_zero.rarity.getstate(), rarity_fixed.rarity.getstate())
        self.assertEqual(baseline_five.hand.getstate(), rarity_fixed.hand.getstate())
        self.assertEqual(baseline_five.reroll.getstate(), rarity_fixed.reroll.getstate())

    def test_boss_devourer_growth_intervention_preserves_checkpoint_power(self):
        config = profile.build_config(max_attempts=2)
        frozen = dataclasses.replace(
            config, diagnostic_boss_devourer_growth_multiplier=0.0
        )
        run = sim.RunState()
        run.counts["boss_devourer"] = 2
        run.boss_devourer_units = 120
        permanent = sim.PermanentState()
        self.assertEqual(
            sim.compute_snapshot(run, permanent, True, config),
            sim.compute_snapshot(run, permanent, True, frozen),
        )

    def test_diagnostic_fixed_wave_power_milestones_are_opt_in_and_cumulative(self):
        run = sim.RunState(kills=1249)
        permanent = sim.PermanentState()
        base = sim.SimConfig()
        diagnostic = dataclasses.replace(
            base,
            diagnostic_fixed_wave_power_milestones=((1250, 4.0), (1500, 4.0), (1750, 4.0)),
        )
        self.assertEqual(
            sim.compute_snapshot(run, permanent, False, diagnostic).log_dps,
            sim.compute_snapshot(run, permanent, False, base).log_dps,
        )
        run.kills = 1250
        self.assertAlmostEqual(
            sim.compute_snapshot(run, permanent, False, diagnostic).log_dps
            - sim.compute_snapshot(run, permanent, False, base).log_dps,
            4.0,
        )
        run.kills = 1750
        self.assertAlmostEqual(
            sim.compute_snapshot(run, permanent, False, diagnostic).log_dps
            - sim.compute_snapshot(run, permanent, False, base).log_dps,
            12.0,
        )

    def test_boss_devourer_base_power_is_internal_to_card_ownership(self):
        permanent = sim.PermanentState()
        base = sim.SimConfig()
        diagnostic = dataclasses.replace(base, diagnostic_boss_devourer_base_power=6.0)
        run = sim.RunState()
        self.assertEqual(
            sim.compute_snapshot(run, permanent, False, diagnostic).log_dps,
            sim.compute_snapshot(run, permanent, False, base).log_dps,
        )
        run.counts["boss_devourer"] = 1
        self.assertAlmostEqual(
            sim.compute_snapshot(run, permanent, False, diagnostic).log_dps
            - sim.compute_snapshot(run, permanent, False, base).log_dps,
            6.0,
        )


if __name__ == "__main__":
    unittest.main()
