#!/usr/bin/env python3
"""Paired replay for front-loaded, tapering Exponential Core candidates."""

from pathlib import Path

import replay_w5000_growing_exponential_core as replay


RATE_PAIRS = {
    0.85: (0.85, 0.715),
    0.90: (0.90, 0.700),
    0.95: (0.95, 0.685),
    0.80: (0.80, 0.800),
}

replay.CONDITIONS = (
    ("A_front_0.85_late_0.715", 0.85),
    ("B_front_0.90_late_0.700", 0.90),
    ("C_front_0.95_late_0.685", 0.95),
    ("D_constant_0.80", 0.80),
)
replay.CHECKPOINTS = (2500, 2600, 2700, 2800, 3000, 3500, 4000, 4500, 5000)
replay.REQUIRED_REACH_WAVES = (2600, 2700, 2800, 3000, 3500, 4000, 4500, 5000)
replay.REPORT_TITLE = "前半強化・後半減衰型Exponential Core paired replay"
replay.DEFAULT_OUTPUT_DIR = Path("output/w5000_frontloaded_exponential_core")
replay.OUTPUT_STEM = "w5000_frontloaded_exponential_core"
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


def frontloaded_core_exponent(kills: int, rate_key: float | None) -> float:
    if rate_key is None:
        return 1.0
    early, late = RATE_PAIRS[rate_key]
    n = big_boss_count(kills)
    return 1.0 + early * min(n, 6) + late * max(n - 6, 0)


replay.big_bosses_after_w2500 = big_boss_count
replay.core_exponent = frontloaded_core_exponent


if __name__ == "__main__":
    replay.main()
