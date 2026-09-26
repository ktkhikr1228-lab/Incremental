"""Optional Defense / Armor Break layer for the first-prestige simulator.

This module deliberately contains only the proposed v1.1 mechanics.  The
frozen v1 simulator leaves ``DefenseConfig.enabled`` set to False, so importing
this module does not alter any existing result.  All numbers below are tuning
anchors, not card effects: they can be calibrated by running the simulator.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


PRESTIGE_WAVE = 10_000

# Enemy hardness is split into HP Power and Defense Power.  Defense begins
# visibly before Wave 2,500, while the final boss keeps HP itself at 1e308.
DEFENSE_POWER_ANCHORS: tuple[tuple[int, float], ...] = (
    (1, 0.00),
    (100, 0.10),
    (500, 0.35),
    (1_000, 0.75),
    (2_500, 1.75),
    (5_000, 3.00),
    (7_500, 4.75),
    (9_000, 5.40),
    (10_000, 5.80),
)

# This optional curve lowers the reset-heavy middle and reserves more room for
# the Legendary -> wall -> Exponential -> wall -> Final sequence.  It is never
# selected by default; calibrate these anchors after the Defense layer is on.
FUTURE_TOTAL_POWER_ANCHORS: tuple[tuple[int, float], ...] = (
    (1, math.log10(5)),
    (10, math.log10(15)),
    (25, 1.325),
    (100, 2.97),
    (500, 9.50),
    (2_500, 91.00),
    (5_000, 215.00),
    (7_500, 304.00),
    (9_000, 307.00),
    (10_000, 308.00),
)


@dataclass(frozen=True)
class DefenseConfig:
    """Tuning inputs for the proposed pre-prestige Defense system.

    ``post_prestige_penetration`` is intentionally 0.0 in this simulator.
    It exists only to make the first-prestige / post-prestige boundary explicit
    in the shared formula.
    """

    enabled: bool = False
    start_wave: int = 1
    power_anchors: tuple[tuple[int, float], ...] = DEFENSE_POWER_ANCHORS
    use_future_power_curve: bool = False
    armor_break_base: float = 2.00
    crit_break_weight: float = 0.35
    followup_break_weight: float = 0.20
    average_break_time_ratio: float = 0.20
    final_boss_requires_full_break: bool = True
    post_prestige_penetration: float = 0.0


def interpolate_anchors(wave: int, anchors: tuple[tuple[int, float], ...]) -> float:
    if wave <= anchors[0][0]:
        return anchors[0][1]
    for (left_wave, left_value), (right_wave, right_value) in zip(anchors, anchors[1:]):
        if wave <= right_wave:
            ratio = (wave - left_wave) / (right_wave - left_wave)
            return left_value + (right_value - left_value) * ratio
    return anchors[-1][1]


def defense_power(wave: int, config: DefenseConfig) -> float:
    """Return the unbroken Defense Power of this enemy."""
    if not config.enabled or wave < config.start_wave:
        return 0.0
    raw = interpolate_anchors(wave, config.power_anchors)
    # Penetration remains zero before the first prestige.  Keeping this term
    # here prevents a later post-prestige implementation from changing the
    # meaning of the formula.
    return raw * max(0.0, 1.0 - config.post_prestige_penetration)


def hp_power(total_power: float, wave: int, config: DefenseConfig) -> float:
    """Split total hardness into HP and Defense, preserving final HP = 1e308."""
    if not config.enabled or wave >= PRESTIGE_WAVE:
        return total_power
    return max(0.0, total_power - defense_power(wave, config))


def armor_break_power(
    *,
    attack_speed: float,
    crit_chance: float,
    crit_multiplier: float,
    follow_rate: float,
    seconds: float,
    config: DefenseConfig,
) -> float:
    """Defense removed during one fight, expressed in Power.

    The hit term is logarithmic, so doubling an already high Attack Speed does
    not double armor removal.  Crit and Follow-Up change the *kind* of Break:
    high-quality critical strikes and extra hit events contribute independent,
    capped modifiers instead of simple linear hit-count scaling.
    """
    if not config.enabled or seconds <= 0.0:
        return 0.0
    expected_hits = max(0.0, attack_speed) * seconds * (1.0 + max(0.0, follow_rate))
    hit_term = math.log10(1.0 + expected_hits)
    crit_quality = math.log10(1.0 + max(0.0, crit_chance) * max(0.0, crit_multiplier - 1.0))
    follow_quality = math.log10(1.0 + max(0.0, follow_rate))
    build_multiplier = (
        1.0
        + config.crit_break_weight * min(3.0, crit_quality)
        + config.followup_break_weight * min(2.0, follow_quality)
    )
    return config.armor_break_base * hit_term * build_multiplier


def remaining_defense_power(
    *,
    wave: int,
    attack_speed: float,
    crit_chance: float,
    crit_multiplier: float,
    follow_rate: float,
    seconds: float,
    config: DefenseConfig,
) -> float:
    return max(
        0.0,
        defense_power(wave, config)
        - armor_break_power(
            attack_speed=attack_speed,
            crit_chance=crit_chance,
            crit_multiplier=crit_multiplier,
            follow_rate=follow_rate,
            seconds=seconds,
            config=config,
        ),
    )


def armor_break_time(
    *,
    wave: int,
    attack_speed: float,
    crit_chance: float,
    crit_multiplier: float,
    follow_rate: float,
    limit: float,
    config: DefenseConfig,
) -> float | None:
    """Return time to fully break Defense, or None when the timer is lost."""
    target = defense_power(wave, config)
    if target <= 0.0:
        return 0.0
    if armor_break_power(
        attack_speed=attack_speed,
        crit_chance=crit_chance,
        crit_multiplier=crit_multiplier,
        follow_rate=follow_rate,
        seconds=limit,
        config=config,
    ) + 1e-12 < target:
        return None
    low, high = 0.0, limit
    for _ in range(28):
        middle = (low + high) / 2.0
        broken = armor_break_power(
            attack_speed=attack_speed,
            crit_chance=crit_chance,
            crit_multiplier=crit_multiplier,
            follow_rate=follow_rate,
            seconds=middle,
            config=config,
        )
        if broken >= target:
            high = middle
        else:
            low = middle
    return high
