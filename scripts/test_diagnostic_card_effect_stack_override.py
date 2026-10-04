import copy
import dataclasses
import unittest

import simulate_first_prestige_v1 as sim


class DiagnosticCardEffectStackOverrideTests(unittest.TestCase):
    def test_escalation_cap_and_floor_change_effect_only(self):
        run = sim.RunState(kills=1500)
        run.counts["escalation"] = 2
        for tag in sim.CARD_BY_KEY["escalation"].tags:
            run.tag_counts[tag] = 2
        original_tags = run.tag_counts.copy()
        permanent = sim.PermanentState()
        baseline = sim.compute_snapshot(run, permanent, True, sim.SimConfig()).log_dps
        capped = sim.compute_snapshot(
            run, permanent, True,
            dataclasses.replace(
                sim.SimConfig(), diagnostic_card_effect_stack_caps=(("escalation", 1.5),),
            ),
        ).log_dps
        floored = sim.compute_snapshot(
            run, permanent, True,
            dataclasses.replace(
                sim.SimConfig(), diagnostic_card_effect_stack_floors=(("escalation", 3.0),),
            ),
        ).log_dps
        self.assertLess(capped, baseline)
        self.assertGreater(floored, baseline)
        self.assertEqual(run.counts["escalation"], 2)
        self.assertEqual(run.tag_counts, original_tags)

    def test_virtual_floor_does_not_acquire_card(self):
        run = sim.RunState(kills=1500)
        permanent = sim.PermanentState()
        config = dataclasses.replace(
            sim.SimConfig(), diagnostic_card_effect_stack_floors=(("escalation", 3.0),),
        )
        self.assertGreater(
            sim.compute_snapshot(run, permanent, True, config).log_dps,
            sim.compute_snapshot(run, permanent, True, sim.SimConfig()).log_dps,
        )
        self.assertEqual(run.counts["escalation"], 0)
        self.assertNotIn("escalation", run.card_first_acquired_wave)

    def test_escalation_growth_scale_is_linear_and_default_unchanged(self):
        run = sim.RunState(kills=1500)
        run.counts["escalation"] = 3
        for tag in sim.CARD_BY_KEY["escalation"].tags:
            run.tag_counts[tag] = 3
        permanent = sim.PermanentState()
        default = sim.compute_snapshot(run, permanent, True, sim.SimConfig()).log_dps
        explicit = sim.compute_snapshot(
            run, permanent, True,
            dataclasses.replace(sim.SimConfig(), diagnostic_escalation_growth_scale=1.0),
        ).log_dps
        half = sim.compute_snapshot(
            run, permanent, True,
            dataclasses.replace(sim.SimConfig(), diagnostic_escalation_growth_scale=0.5),
        ).log_dps
        off = sim.compute_snapshot(
            run, permanent, True,
            dataclasses.replace(
                sim.SimConfig(), diagnostic_suppressed_card_keys=frozenset({"escalation"}),
            ),
        ).log_dps
        self.assertAlmostEqual(default, explicit, places=12)
        self.assertAlmostEqual(half - off, 0.5 * (default - off), places=12)
        self.assertEqual(run.counts["escalation"], 3)


if __name__ == "__main__":
    unittest.main()
