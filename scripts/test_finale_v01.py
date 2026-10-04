from __future__ import annotations

import dataclasses
import unittest

import simulate_first_prestige_v1 as sim


class FinaleV01Tests(unittest.TestCase):
    def test_default_is_disabled_and_enemy_curve_is_unchanged(self) -> None:
        config = sim.SimConfig(target_wave=5000)
        self.assertFalse(config.finale.enabled)
        for wave in (4000, 4500, 4750, 5000):
            self.assertEqual(sim.finale_added_power(wave, config), 0.0)

    def test_anchor_values(self) -> None:
        config = dataclasses.replace(
            sim.SimConfig(target_wave=5000),
            finale=sim.FinaleConfig(enabled=True),
        )
        expected = {4500: 0, 4600: 10, 4700: 20, 4800: 30, 4900: 40, 5000: 50}
        for wave, power in expected.items():
            self.assertEqual(sim.finale_added_power(wave, config), power)

    def test_linear_interpolation_and_independent_addition(self) -> None:
        base = sim.SimConfig(target_wave=5000)
        finale = dataclasses.replace(base, finale=sim.FinaleConfig(enabled=True))
        self.assertEqual(sim.finale_added_power(4550, finale), 5.0)
        self.assertEqual(sim.finale_added_power(4750, finale), 25.0)
        self.assertAlmostEqual(
            sim.configured_enemy_power(4750, finale)
            - sim.configured_enemy_power(4750, base),
            25.0,
        )


if __name__ == "__main__":
    unittest.main()
