from __future__ import annotations

import argparse
import dataclasses
import math
import random
import unittest

import simulate_first_prestige_v1 as sim
import w5000_v1_profile as w5000


def cli_args(variant: str) -> argparse.Namespace:
    return argparse.Namespace(
        variant=variant,
        dp_growth=sim.DP_GROWTH,
        weapon_scale=1.0,
        relic_scale=1.0,
        milestone_power_scale=1.0,
        hp_bonus_scale=1.0,
        midgame_relief=0.0,
        max_attempts=140,
        automation=True,
        game_speed=True,
        initial_card_points=True,
        sweep=True,
        reward_skip=None,
        attack_interval=False,
        armor_break_base=2.0,
        crit_break_weight=0.35,
        followup_break_weight=0.20,
        average_break_time_ratio=0.20,
        final_boss_full_break=True,
        future_qol=False,
        future_sweep_multiplier=0.55,
        memory_card=False,
        memory_card_unlock_wave=500,
        take_mode="legacy",
    )


class W5000V1ProfileTests(unittest.TestCase):
    def test_legacy_formal_defaults_are_unchanged(self) -> None:
        config = sim.build_cli_config(cli_args("formal"))
        self.assertEqual(config.target_wave, 10_000)
        self.assertEqual(config.card_upgrade_cap, 3)
        self.assertEqual(config.exponential_core_multiplier, 1.05)
        self.assertEqual(config.exponential_core_unlock_wave, 5_000)
        self.assertEqual(config.disabled_card_keys, frozenset())
        self.assertFalse(config.reward_skip_enabled)
        self.assertFalse(config.defense.enabled)

    def test_d_and_e_settings_are_unchanged(self) -> None:
        d = sim.build_cli_config(cli_args("D"))
        e = sim.build_cli_config(cli_args("E"))
        for config in (d, e):
            self.assertEqual(config.target_wave, 5_000)
            self.assertEqual(config.card_upgrade_cap, 1)
            self.assertEqual(config.exponential_core_multiplier, 1.02)
            self.assertEqual(config.exponential_core_unlock_wave, 2_500)
            self.assertEqual(config.disabled_card_keys, frozenset({"final_equation"}))
            self.assertTrue(config.reward_skip_enabled)
        self.assertFalse(d.defense.enabled)
        self.assertTrue(e.defense.enabled)
        self.assertEqual(e.defense.start_wave, 500)

    def test_w5000_profile_explicit_settings(self) -> None:
        config = w5000.build_config()
        self.assertEqual(config.target_wave, 5_000)
        self.assertFalse(config.defense.enabled)
        self.assertFalse(config.reward_skip_enabled)
        self.assertEqual(config.card_upgrade_cap, 1)
        self.assertEqual(config.take_mode, "legacy")
        self.assertIn("final_equation", config.disabled_card_keys)
        self.assertIn("exponential_core", config.disabled_card_keys)

    def test_enemy_curve_matches_legacy_through_w2500(self) -> None:
        config = w5000.build_config()
        for wave in (1, 10, 25, 100, 500, 1000, 2500):
            self.assertEqual(w5000.source_wave(wave), wave)
            self.assertAlmostEqual(
                sim.configured_enemy_power(wave, config),
                sim.enemy_power(wave, bonus_scale=1.0),
            )

    def test_enemy_curve_compressed_mapping_and_final_power(self) -> None:
        expected = {3000: 4000, 3500: 5500, 4000: 7000, 4500: 8500, 5000: 10000}
        config = w5000.build_config()
        for wave, legacy_wave in expected.items():
            self.assertEqual(w5000.source_wave(wave), legacy_wave)
            self.assertAlmostEqual(
                sim.configured_enemy_power(wave, config),
                sim.enemy_power(legacy_wave, bonus_scale=1.0),
            )
        self.assertAlmostEqual(sim.configured_enemy_power(5000, config), 308.0)

    def test_final_equation_is_not_available(self) -> None:
        config = w5000.build_config()
        run = sim.RunState(kills=5000)
        permanent = sim.PermanentState(max_wave=5000)
        keys = {card.key for card in sim.available_cards("L", run, permanent, config)}
        self.assertNotIn("final_equation", keys)
        self.assertNotIn("exponential_core", keys)

    def test_profiles_do_not_leak_configuration(self) -> None:
        formal_before = sim.build_cli_config(cli_args("formal"))
        _ = w5000.build_config(max_attempts=2)
        formal_after = sim.build_cli_config(cli_args("formal"))
        self.assertEqual(formal_before, formal_after)
        self.assertIsNone(formal_after.enemy_progression_anchors)
        self.assertIsNone(formal_after.progression_after_2500_scale)

    def test_all_core_profiles_preserve_the_eleven_scaffold_conditions(self) -> None:
        expected_mapping = {3000: 4000, 3500: 5500, 4000: 7000, 4500: 8500, 5000: 10000}
        for name in w5000.CORE_PROFILES:
            with self.subTest(core_profile=name):
                config = w5000.build_config(core_profile=name)
                self.assertEqual(config.target_wave, 5000)
                self.assertAlmostEqual(sim.configured_enemy_power(2500, config), sim.enemy_power(2500, 1.0))
                self.assertAlmostEqual(sim.configured_enemy_power(5000, config), 308.0)
                for wave, legacy_wave in expected_mapping.items():
                    self.assertEqual(sim.enemy_progression_wave(wave, config), legacy_wave)
                self.assertIn("final_equation", config.disabled_card_keys)
                self.assertFalse(config.defense.enabled)
                self.assertFalse(config.reward_skip_enabled)
                self.assertEqual(config.card_upgrade_cap, 1)
                self.assertEqual(config.take_mode, "legacy")

    def test_core_profiles_differ_only_in_core_configuration(self) -> None:
        ignored = {
            "exponential_core_guaranteed_wave",
            "exponential_core_growth_stages",
        }
        configs = [dataclasses.asdict(w5000.build_config(core_profile=name)) for name in w5000.CORE_PROFILES]
        normalized = [{key: value for key, value in config.items() if key not in ignored} for config in configs]
        self.assertTrue(all(config == normalized[0] for config in normalized[1:]))

    def test_core_acquisition_is_a_w2500_non_draft_milestone(self) -> None:
        config = w5000.build_config(core_profile="three_stage_candidate")
        run = sim.RunState(kills=2499)
        self.assertFalse(sim.grant_profile_exponential_core(run, config))
        run.kills = 2500
        self.assertTrue(sim.grant_profile_exponential_core(run, config))
        self.assertEqual(run.counts["exponential_core"], 1)
        self.assertEqual(run.card_count, 0)
        self.assertEqual(run.choices, 0)
        self.assertFalse(sim.grant_profile_exponential_core(run, config))

    def test_three_stage_exponents_and_mechanical_weak_strong_variants(self) -> None:
        expected = {
            "no_core": {2500: 1.0, 3000: 1.0, 4000: 1.0, 5000: 1.0},
            "three_stage_weaker": {2500: 1.85, 3000: 6.10, 4000: 13.60, 5000: 19.60},
            "three_stage_candidate": {2500: 1.90, 3000: 6.40, 4000: 14.40, 5000: 20.90},
            "three_stage_stronger": {2500: 1.95, 3000: 6.70, 4000: 15.20, 5000: 22.20},
        }
        for name, checkpoints in expected.items():
            config = w5000.build_config(core_profile=name)
            run = sim.RunState()
            if name != "no_core":
                run.counts["exponential_core"] = 1
            for wave, value in checkpoints.items():
                run.kills = wave
                exponent = sim.exponential_core_exponent(run, config)
                self.assertTrue(math.isfinite(exponent))
                self.assertAlmostEqual(exponent, value)

    def test_core_run_growth_resets_on_death(self) -> None:
        config = w5000.build_config(core_profile="three_stage_candidate")
        old_run = sim.RunState(kills=4000)
        old_run.counts["exponential_core"] = 1
        self.assertGreater(sim.exponential_core_exponent(old_run, config), 1.0)
        new_run = sim.RunState()
        self.assertEqual(sim.exponential_core_exponent(new_run, config), 1.0)

    def test_legacy_fixed_core_exponents_are_unchanged(self) -> None:
        formal = sim.SimConfig()
        variant_d = sim.SimConfig(
            target_wave=5000,
            exponential_core_multiplier=1.02,
        )
        run = sim.RunState(kills=5000)
        run.counts["exponential_core"] = 1

        self.assertEqual(sim.exponential_core_exponent(run, formal), 1.05)
        self.assertEqual(sim.exponential_core_exponent(run, variant_d), 1.02)

    def test_dp_v01_bc_parameters_and_individual_costs(self) -> None:
        config = dataclasses.replace(
            w5000.build_config(core_profile="no_core"),
            dp_v01=sim.DPV01Config(enabled=True),
        )
        permanent = sim.PermanentState()
        self.assertEqual(sim.dp_v01_next_cost(permanent, "base_atk", config), 8)
        self.assertEqual(sim.dp_v01_next_cost(permanent, "attack_speed", config), 9)
        self.assertEqual(config.dp_v01.cost_growth, 1.065)
        self.assertEqual(config.dp_v01.atk_per_level, 0.28)
        self.assertEqual(config.dp_v01.as_per_level, 0.22)
        self.assertEqual(config.dp_v01.xp_per_level, 0.14)
        self.assertEqual(config.dp_v01.crit_rate_per_level, 0.055)
        self.assertEqual(config.dp_v01.crit_mult_per_level, 0.140)
        self.assertEqual(config.dp_v01.weapon_atk_per_level, 0.28)

    def test_dp_v01_record_bonus_is_once_but_same_wall_death_dp_repeats(self) -> None:
        config = dataclasses.replace(
            w5000.build_config(core_profile="no_core"),
            dp_v01=sim.DPV01Config(enabled=True),
        )
        permanent = sim.PermanentState(max_wave=100)
        first = sim.award_and_spend_dp_v01(permanent, 100, config)
        second = sim.award_and_spend_dp_v01(permanent, 100, config)
        self.assertEqual(first, 33)   # 18 death + 12 record + 3 Big Boss
        self.assertEqual(second, 21)  # 18 death + 0 record + 3 Big Boss
        self.assertEqual(permanent.dp_v01_claimed_records, {25, 50, 75, 100})
        self.assertEqual(permanent.atk, 0)
        self.assertEqual(permanent.attack_speed, 0)
        self.assertEqual(permanent.xp, 0)

    def test_dp_v01_snapshot_is_opt_in_and_finite(self) -> None:
        base_config = w5000.build_config(core_profile="no_core")
        new_config = dataclasses.replace(base_config, dp_v01=sim.DPV01Config(enabled=True))
        permanent = sim.PermanentState()
        for key in ("base_atk", "attack_speed", "xp_gain", "crit_rate", "crit_multiplier", "weapon_atk"):
            permanent.dp_v01_levels[key] = 1
        run = sim.RunState(kills=500, weapon=True, weapon_power=1.0)
        legacy = sim.compute_snapshot(run, permanent, True, base_config)
        candidate = sim.compute_snapshot(run, permanent, True, new_config)
        self.assertTrue(math.isfinite(candidate.log_dps))
        self.assertGreater(candidate.log_dps, legacy.log_dps)
        self.assertEqual(legacy.crit_chance, 0.01)
        self.assertAlmostEqual(candidate.crit_chance, 0.065)

    def test_w2500_guaranteed_legendary_can_be_disabled_per_profile(self) -> None:
        enabled = w5000.build_config(core_profile="no_core", guaranteed_legendary=True)
        disabled = w5000.build_config(core_profile="no_core", guaranteed_legendary=False)
        self.assertNotIn(2500, enabled.disabled_guaranteed_choice_waves)
        self.assertIn(2500, disabled.disabled_guaranteed_choice_waves)

        permanent = sim.PermanentState(max_wave=2500)
        run = sim.RunState(kills=2500)
        sim.process_guaranteed_choices(random.Random(1), "balanced", run, permanent, 2501, disabled)
        self.assertIn(2500, run.milestone_choices)
        self.assertNotIn(2500, run.milestone_card_keys)
        self.assertEqual(run.card_count, 0)

    def test_guaranteed_choice_records_selected_card_and_immediate_delta(self) -> None:
        config = w5000.build_config(core_profile="no_core", guaranteed_legendary=True)
        permanent = sim.PermanentState(max_wave=2500)
        run = sim.RunState(kills=2500)
        run.tag_counts["as"] = 5
        sim.process_guaranteed_choices(random.Random(1), "balanced", run, permanent, 2501, config)
        self.assertIn(2500, run.milestone_card_keys)
        self.assertTrue(math.isfinite(run.milestone_power_deltas[2500]))

    def test_attempt_aware_checkpoint_capture_preserves_legacy_callback(self) -> None:
        config = dataclasses.replace(
            w5000.build_config(core_profile="no_core"),
            target_wave=1,
            max_attempts=1,
            diagnostic_checkpoints=(1,),
        )
        legacy_calls = []
        attempt_calls = []

        def legacy_capture(wave, run, permanent, streams):
            legacy_calls.append(wave)

        def attempt_capture(attempt, wave, run, permanent, streams):
            attempt_calls.append((attempt, wave))

        sim.run_trial(
            random.Random(1), "balanced", config, True,
            checkpoint_capture=legacy_capture,
            attempt_checkpoint_capture=attempt_capture,
        )
        self.assertEqual(legacy_calls, [1])
        self.assertEqual(attempt_calls, [(1, 1)])

    def test_post2500_diagnostic_defaults_are_inert(self) -> None:
        config = w5000.build_config(core_profile="no_core")
        self.assertEqual(config.diagnostic_frozen_dp_items, frozenset())
        self.assertEqual(config.diagnostic_dp_level_caps, ())
        self.assertFalse(config.diagnostic_freeze_weapon_permanent_progression)
        self.assertIsNone(config.diagnostic_relic_power_wave_cap)

    def test_relic_wave_cap_and_dp_level_cap_are_diagnostic_only(self) -> None:
        base = dataclasses.replace(
            w5000.build_config(core_profile="no_core"),
            dp_v01=sim.DPV01Config(enabled=True),
        )
        capped = dataclasses.replace(
            base,
            diagnostic_relic_power_wave_cap=2500,
            diagnostic_dp_level_caps=(("weapon_quality", 3),),
        )
        permanent = sim.PermanentState(max_wave=5000, relic_unlocked=True)
        permanent.dp_v01_levels["weapon_quality"] = 10
        run = sim.RunState(kills=100)
        self.assertLess(
            sim.compute_snapshot(run, permanent, False, capped).relic_power,
            sim.compute_snapshot(run, permanent, False, base).relic_power,
        )
        self.assertEqual(sim.diagnostic_dp_level(permanent, "weapon_quality", base), 10)
        self.assertEqual(sim.diagnostic_dp_level(permanent, "weapon_quality", capped), 3)

    def test_late_dp_scale_preserves_checkpoint_levels(self) -> None:
        config = dataclasses.replace(
            w5000.build_config(core_profile="no_core"),
            diagnostic_dp_baseline_levels=(("base_atk", 10),),
            diagnostic_late_dp_effect_scale=0.25,
        )
        permanent = sim.PermanentState()
        permanent.dp_v01_levels["base_atk"] = 18
        self.assertEqual(sim.diagnostic_dp_level(permanent, "base_atk", config), 12.0)
        permanent.dp_v01_levels["base_atk"] = 8
        self.assertEqual(sim.diagnostic_dp_level(permanent, "base_atk", config), 8.0)

    def test_run_end_capture_is_observational(self) -> None:
        config = dataclasses.replace(
            w5000.build_config(core_profile="no_core"), target_wave=1, max_attempts=1,
        )
        calls = []

        def capture(run, permanent, streams, failure_wave):
            calls.append((run.kills, failure_wave))

        result = sim.run_once(
            random.Random(1), "balanced", sim.PermanentState(), config, True,
            run_end_capture=capture,
        )
        self.assertEqual(result.reached, 1)
        self.assertEqual(calls, [(1, None)])

    def test_card_effect_suppression_keeps_ownership_but_removes_effect(self) -> None:
        base = w5000.build_config(core_profile="no_core")
        suppressed = dataclasses.replace(
            base, diagnostic_suppressed_card_keys=frozenset({"power_up"}),
        )
        permanent = sim.PermanentState()
        run = sim.RunState()
        sim.acquire_card(run, sim.CARD_BY_KEY["power_up"], suppressed)
        self.assertEqual(run.counts["power_up"], 1)
        self.assertEqual(run.tag_counts["atk"], 1)
        self.assertGreater(
            sim.compute_snapshot(run, permanent, False, base).log_dps,
            sim.compute_snapshot(run, permanent, False, suppressed).log_dps,
        )
        empty = sim.compute_snapshot(sim.RunState(), permanent, False, base)
        inert = sim.compute_snapshot(run, permanent, False, suppressed)
        self.assertAlmostEqual(inert.log_dps, empty.log_dps)

    def test_card_effect_suppression_does_not_consume_rng(self) -> None:
        rng = random.Random(20260828)
        before = rng.getstate()
        config = dataclasses.replace(
            w5000.build_config(core_profile="no_core"),
            diagnostic_suppressed_card_keys=frozenset({"critical_singularity"}),
        )
        run = sim.RunState()
        run.counts["critical_singularity"] = 1
        sim.compute_snapshot(run, sim.PermanentState(), False, config)
        self.assertEqual(rng.getstate(), before)

    def test_individual_legendary_growth_can_be_suppressed(self) -> None:
        base = w5000.build_config(core_profile="no_core")
        run = sim.RunState(legendary_growth_log=5.0)
        run.counts.update({"infinite_barrage": 1, "knowledge_collapse": 1})
        run.legendary_growth_by_key = {
            "infinite_barrage": 2.0,
            "knowledge_collapse": 3.0,
        }
        suppressed = dataclasses.replace(
            base, diagnostic_suppressed_card_keys=frozenset({"infinite_barrage"}),
        )
        self.assertEqual(sim.diagnostic_legendary_growth_log(run, base), 5.0)
        self.assertEqual(sim.diagnostic_legendary_growth_log(run, suppressed), 3.0)

    def test_infinite_barrage_strength_scales_direct_and_growth_power(self) -> None:
        base = w5000.build_config(core_profile="no_core")
        half = dataclasses.replace(base, diagnostic_infinite_barrage_strength=0.5)
        zero = dataclasses.replace(base, diagnostic_infinite_barrage_strength=0.0)
        permanent = sim.PermanentState()
        run = sim.RunState(legendary_growth_log=4.0)
        run.counts["infinite_barrage"] = 1
        run.legendary_growth_by_key = {"infinite_barrage": 4.0}
        full_power = sim.compute_snapshot(run, permanent, False, base).log_dps
        half_power = sim.compute_snapshot(run, permanent, False, half).log_dps
        zero_power = sim.compute_snapshot(run, permanent, False, zero).log_dps
        self.assertAlmostEqual(half_power - zero_power, (full_power - zero_power) * 0.5)
        self.assertEqual(sim.diagnostic_legendary_growth_log(run, base), 4.0)
        self.assertEqual(sim.diagnostic_legendary_growth_log(run, half), 2.0)
        self.assertEqual(sim.diagnostic_legendary_growth_log(run, zero), 0.0)

    def test_infinite_barrage_soft_cap_applies_to_total_card_power(self) -> None:
        base = dataclasses.replace(
            w5000.build_config(core_profile="no_core"),
            diagnostic_infinite_barrage_strength=0.375,
        )
        capped = dataclasses.replace(base, diagnostic_infinite_barrage_power_cap=20.0)
        suppressed = dataclasses.replace(
            base,
            diagnostic_suppressed_card_keys=frozenset({"infinite_barrage"}),
        )
        capped_suppressed = dataclasses.replace(
            capped,
            diagnostic_suppressed_card_keys=frozenset({"infinite_barrage"}),
        )
        permanent = sim.PermanentState(attack_speed=200)
        run = sim.RunState(legendary_growth_log=4.0)
        run.counts["infinite_barrage"] = 1
        run.legendary_growth_by_key = {"infinite_barrage": 4.0}
        uncapped_delta = (
            sim.compute_snapshot(run, permanent, False, base).log_dps
            - sim.compute_snapshot(run, permanent, False, suppressed).log_dps
        )
        capped_delta = (
            sim.compute_snapshot(run, permanent, False, capped).log_dps
            - sim.compute_snapshot(run, permanent, False, capped_suppressed).log_dps
        )
        self.assertAlmostEqual(
            capped_delta,
            20.0 * (1.0 - math.exp(-uncapped_delta / 20.0)),
        )
        self.assertLess(capped_delta, 20.0)

    def test_infinite_barrage_v2_fixed_ratio_is_independent_of_raw_attack_speed(self) -> None:
        base = dataclasses.replace(
            w5000.build_config(core_profile="no_core"),
            diagnostic_infinite_barrage_mode="v2_fixed_ratio",
        )
        suppressed = dataclasses.replace(
            base,
            diagnostic_suppressed_card_keys=frozenset({"infinite_barrage"}),
        )
        run = sim.RunState()
        run.counts["infinite_barrage"] = 1
        expected = math.log10(1.25)
        for attack_speed_level in (95, 142, 174, 200):
            permanent = sim.PermanentState(attack_speed=attack_speed_level)
            actual = sim.compute_snapshot(run, permanent, False, base).log_dps
            without = sim.compute_snapshot(run, permanent, False, suppressed).log_dps
            self.assertAlmostEqual(actual - without, expected)

    def test_infinite_barrage_v2_growth_is_separate_and_soft_capped(self) -> None:
        base = dataclasses.replace(
            w5000.build_config(core_profile="no_core"),
            diagnostic_infinite_barrage_mode="v2_fixed_ratio",
        )
        capped = dataclasses.replace(
            base,
            diagnostic_infinite_barrage_v2_growth_power_cap=0.25,
        )
        run = sim.RunState(legendary_growth_log=4.0)
        run.counts["infinite_barrage"] = 1
        run.legendary_growth_by_key = {"infinite_barrage": 4.0}
        permanent = sim.PermanentState(attack_speed=200)
        base_power = sim.compute_snapshot(run, permanent, False, base).log_dps
        capped_power = sim.compute_snapshot(run, permanent, False, capped).log_dps
        growth_power = 0.25 * (1.0 - math.exp(-4.0 / 0.25))
        expected_delta = math.log10(1 + 0.25 * 10**growth_power) - math.log10(1.25)
        self.assertAlmostEqual(capped_power - base_power, expected_delta)
        self.assertLess(capped_power - base_power, 0.25)
        self.assertEqual(sim.diagnostic_legendary_growth_log(run, capped), 0.0)

    def test_infinite_barrage_v2_does_not_copy_follow_up_damage(self) -> None:
        base = dataclasses.replace(
            w5000.build_config(core_profile="no_core"),
            diagnostic_infinite_barrage_mode="v2_fixed_ratio",
        )
        suppressed = dataclasses.replace(
            base,
            diagnostic_suppressed_card_keys=frozenset({"infinite_barrage"}),
        )
        run = sim.RunState()
        run.counts.update({"infinite_barrage": 1, "follow_up_strike": 1})
        follow_up_multiplier = 1.0 + 0.10 * 0.50
        expected = math.log10((follow_up_multiplier + 0.25) / follow_up_multiplier)
        actual = sim.compute_snapshot(run, sim.PermanentState(), False, base).log_dps
        without = sim.compute_snapshot(run, sim.PermanentState(), False, suppressed).log_dps
        self.assertAlmostEqual(actual - without, expected)


if __name__ == "__main__":
    unittest.main()
