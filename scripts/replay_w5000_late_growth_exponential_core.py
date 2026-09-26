#!/usr/bin/env python3
"""Paired replay comparing late Exponential Core growth after a fixed +0.90 opening."""

from pathlib import Path

import replay_w5000_growing_exponential_core as replay


RATE_PAIRS = {
    0.74: (0.90, 0.74),
    0.77: (0.90, 0.77),
    0.90: (0.90, 0.80),
    0.80: (0.80, 0.80),
}

replay.CONDITIONS = (
    ("A_front_0.90_late_0.74", 0.74),
    ("B_front_0.90_late_0.77", 0.77),
    ("C_front_0.90_late_0.80", 0.90),
    ("D_constant_0.80", 0.80),
)
replay.CHECKPOINTS = (2500, 2600, 2700, 2800, 3000, 3500, 4000, 4500, 5000)
replay.REQUIRED_REACH_WAVES = (2600, 2700, 2800, 3000, 3500, 4000, 4500, 5000)
replay.REPORT_TITLE = "Exponential Core後半成長量 paired replay"
replay.DEFAULT_OUTPUT_DIR = Path("output/w5000_late_growth_exponential_core")
replay.OUTPUT_STEM = "w5000_late_growth_exponential_core"
replay.FORMULA_DESCRIPTION = (
    "BaseATK_after = BaseATK_before ^ CoreExponent; "
    "CoreExponent = 1 + early*min(N, 6) + late*max(N-6, 0)"
)
replay.N_DESCRIPTION = (
    "W2500 defeat is N=1; each subsequent 100-wave Big Boss increments N"
)


def big_boss_count(kills: int) -> int:
    if kills < 2500:
        return 0
    return 1 + (kills - 2500) // 100


def late_growth_core_exponent(kills: int, rate_key: float | None) -> float:
    if rate_key is None:
        return 1.0
    early, late = RATE_PAIRS[rate_key]
    n = big_boss_count(kills)
    return 1.0 + early * min(n, 6) + late * max(n - 6, 0)


replay.big_bosses_after_w2500 = big_boss_count
replay.core_exponent = late_growth_core_exponent


if __name__ == "__main__":
    replay.main()
