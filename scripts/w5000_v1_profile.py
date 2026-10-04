"""Independent scaffold configuration for the future W5000 v1 profile.

Only migration decisions that are already explicit live here.  Undecided
balance systems continue to use legacy placeholders, and Exponential Core is
disabled until its final formula is approved.
"""

from __future__ import annotations

from dataclasses import dataclass

import simulate_first_prestige_v1 as sim


PROFILE_NAME = "w5000_v1"
TARGET_WAVE = 5_000
ENEMY_PROGRESSION_ANCHORS: tuple[tuple[int, float], ...] = (
    (1, 1.0),
    (2_500, 2_500.0),
    (5_000, 10_000.0),
)
UNRESOLVED_DISABLED_CARDS = frozenset({"exponential_core", "final_equation"})
CORE_CHECKPOINTS = (2500, 3000, 3500, 4000, 4500, 5000)


@dataclass(frozen=True)
class CoreProfile:
    name: str
    stages: tuple[tuple[int, int, float], ...]

    @property
    def enabled(self) -> bool:
        return bool(self.stages)


CORE_PROFILES: dict[str, CoreProfile] = {
    "no_core": CoreProfile("no_core", ()),
    "three_stage_candidate": CoreProfile(
        "three_stage_candidate",
        ((1, 6, 0.90), (7, 16, 0.80), (17, 26, 0.65)),
    ),
    "three_stage_weaker": CoreProfile(
        "three_stage_weaker",
        ((1, 6, 0.85), (7, 16, 0.75), (17, 26, 0.60)),
    ),
    "three_stage_stronger": CoreProfile(
        "three_stage_stronger",
        ((1, 6, 0.95), (7, 16, 0.85), (17, 26, 0.70)),
    ),
}


@dataclass(frozen=True)
class ProfileMetadata:
    name: str = PROFILE_NAME
    status: str = "scaffold"
    enemy_curve: str = "legacy W1-2500; legacy W2500-10000 compressed 3x into W2500-5000"
    exponential_core: str = "unresolved; temporarily disabled"
    dp: str = "legacy placeholder; DP v0.1 not adopted"
    weapon: str = "legacy placeholder; new Weapon values not adopted"
    relic: str = "legacy placeholder; new Relic specification not adopted"
    card_value: str = "not integrated"


METADATA = ProfileMetadata()


def build_config(
    *,
    max_attempts: int = 140,
    core_profile: str = "no_core",
    guaranteed_legendary: bool = True,
) -> sim.SimConfig:
    """Return an isolated W5000 profile without changing formal/D/E defaults."""
    core = CORE_PROFILES[core_profile]
    return sim.SimConfig(
        max_attempts=max_attempts,
        target_wave=TARGET_WAVE,
        enemy_progression_anchors=ENEMY_PROGRESSION_ANCHORS,
        # Do not inherit D/E's separate 2.20x player-growth experiment merely
        # because this profile also ends at W5000.
        progression_after_2500_scale=1.0,
        reward_skip_enabled=False,
        defense=sim.DefenseConfig(enabled=False),
        card_upgrade_cap=1,
        exponential_core_multiplier=1.0,
        exponential_core_unlock_wave=2500,
        exponential_core_guaranteed_wave=2500 if core.enabled else None,
        exponential_core_growth_stages=core.stages,
        diagnostic_checkpoints=CORE_CHECKPOINTS,
        disabled_card_keys=UNRESOLVED_DISABLED_CARDS,
        disabled_guaranteed_choice_waves=(
            frozenset() if guaranteed_legendary else frozenset({2500})
        ),
        take_mode="legacy",
    )


def source_wave(wave: int) -> int:
    """Map a W5000 profile wave onto the legacy formal enemy curve."""
    config = build_config()
    return sim.enemy_progression_wave(wave, config)


def enemy_power(wave: int) -> float:
    return sim.configured_enemy_power(wave, build_config())
