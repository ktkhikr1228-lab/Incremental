#!/usr/bin/env python3
"""Paired replay comparing three-stage Exponential Core growth."""

from pathlib import Path

import replay_w5000_growing_exponential_core as replay


# Float keys only identify conditions for the shared replay/reporting engine.
RATE_PROFILES = {
    0.60: (0.90, 0.80, 0.60),
    0.65: (0.90, 0.80, 0.65),
    0.70: (0.90, 0.80, 0.70),
    0.77: (0.90, 0.77, 0.77),
}

replay.CONDITIONS = (
    ("A_three_stage_final_0.60", 0.60),
    ("B_three_stage_final_0.65", 0.65),
    ("C_three_stage_final_0.70", 0.70),
    ("D_front_0.90_late_0.77", 0.77),
)
replay.CHECKPOINTS = (2500, 3000, 3500, 4000, 4500, 5000)
replay.REQUIRED_REACH_WAVES = (3000, 3500, 4000, 4500, 5000)
replay.REPORT_TITLE = "3段階成長型Exponential Core paired replay"
replay.DEFAULT_OUTPUT_DIR = Path("output/w5000_three_stage_exponential_core")
replay.OUTPUT_STEM = "w5000_three_stage_exponential_core"
replay.FORMULA_DESCRIPTION = (
    "BaseATK_after = BaseATK_before ^ CoreExponent; CoreExponent = 1 + "
    "stage1*min(N,6) + stage2*clamp(N-6,0,10) + stage3*max(N-16,0)"
)
replay.N_DESCRIPTION = (
    "W2500 defeat is N=1; each subsequent 100-wave Big Boss increments N"
)


def big_boss_count(kills: int) -> int:
    if kills < 2500:
        return 0
    return 1 + (kills - 2500) // 100


def three_stage_core_exponent(kills: int, profile_key: float | None) -> float:
    if profile_key is None:
        return 1.0
    first, middle, final = RATE_PROFILES[profile_key]
    n = big_boss_count(kills)
    first_n = min(n, 6)
    middle_n = max(min(n - 6, 10), 0)
    final_n = max(n - 16, 0)
    return 1.0 + first * first_n + middle * middle_n + final * final_n


replay.big_bosses_after_w2500 = big_boss_count
replay.core_exponent = three_stage_core_exponent


if __name__ == "__main__":
    replay.main()
