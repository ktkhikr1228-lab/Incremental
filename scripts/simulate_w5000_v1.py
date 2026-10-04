#!/usr/bin/env python3
"""Entry point for the independent W5000 v1 scaffold profile."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import simulate_first_prestige_v1 as sim
import w5000_v1_profile as profile


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--seed", type=int, default=sim.SEED)
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--core-profile", choices=tuple(profile.CORE_PROFILES), default="no_core")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.trials <= 3:
        parser.error("w5000_v1 scaffold currently permits only 1-3 smoke trials")
    if args.max_attempts <= 0:
        parser.error("--max-attempts must be greater than zero")

    config = profile.build_config(max_attempts=args.max_attempts, core_profile=args.core_profile)
    rows = sim.simulate_standard(args.trials, config, args.seed, workers=1)
    payload = sim.build_json_result(profile.PROFILE_NAME, rows, config)
    payload["profile_status"] = profile.METADATA.status
    payload["profile_metadata"] = {
        "enemy_curve": profile.METADATA.enemy_curve,
        "exponential_core": profile.METADATA.exponential_core,
        "dp": profile.METADATA.dp,
        "weapon": profile.METADATA.weapon,
        "relic": profile.METADATA.relic,
        "card_value": profile.METADATA.card_value,
    }
    payload["target_wave"] = config.target_wave
    payload["core_profile"] = args.core_profile
    payload["w5000_enemy_power"] = sim.configured_enemy_power(5000, config)
    payload["defense_enabled"] = config.defense.enabled
    payload["refinement_max"] = config.card_upgrade_cap
    payload["disabled_card_keys"] = sorted(config.disabled_card_keys)

    output_text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_text, encoding="utf-8")
    terminal = {key: value for key, value in payload.items() if key != "w2500_trials"}
    print(json.dumps(terminal, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
