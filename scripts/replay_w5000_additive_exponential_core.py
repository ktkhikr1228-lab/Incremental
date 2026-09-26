#!/usr/bin/env python3
"""Run the paired W5000 replay with additive Exponential Core growth."""

from pathlib import Path

import replay_w5000_growing_exponential_core as replay


replay.CONDITIONS = (
    ("A_no_core", None),
    ("B_additive_0.60", 0.60),
    ("C_additive_0.70", 0.70),
    ("D_additive_0.80", 0.80),
)
replay.REPORT_TITLE = "加算指数成長Exponential Core paired replay"
replay.DEFAULT_OUTPUT_DIR = Path("output/w5000_additive_exponential_core")
replay.OUTPUT_STEM = "w5000_additive_exponential_core"
replay.FORMULA_DESCRIPTION = (
    "BaseATK_after = BaseATK_before ^ CoreExponent; "
    "CoreExponent = 1 + growth_per_big_boss * N"
)
replay.N_DESCRIPTION = (
    "W2500 defeat is N=1; each subsequent 100-wave Big Boss increments N"
)


def additive_big_boss_count(kills: int) -> int:
    if kills < 2500:
        return 0
    return 1 + (kills - 2500) // 100


def additive_core_exponent(kills: int, growth: float | None) -> float:
    if growth is None:
        return 1.0
    return 1.0 + growth * additive_big_boss_count(kills)


replay.big_bosses_after_w2500 = additive_big_boss_count
replay.core_exponent = additive_core_exponent


if __name__ == "__main__":
    replay.main()
