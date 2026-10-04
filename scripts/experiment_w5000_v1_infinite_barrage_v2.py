#!/usr/bin/env python3
"""Experimental Infinite Barrage v2 structure check and paired replay."""

from __future__ import annotations

import argparse
import gzip
import json
import math
import pickle
from pathlib import Path

import diagnose_w5000_v1_precore as diag
import experiment_w5000_v1_integrated_core_dp as integrated
import experiment_w5000_v1_unlimited_boost_v02 as boost_v02
import simulate_first_prestige_v1 as sim


DP_SCALE = 0.10
CORE_SCALE = 0.15
CURRENT_STRENGTH = 0.375
V2_TRIGGER_ATTACKS = 20
V2_DAMAGE_ATTACKS = 5.0
V2_GROWTH_POWER_CAP = 0.25
CHECKPOINTS = (4500, 4750, 5000)
FIXED_ATTACK_SPEEDS = (100.0, 1000.0, 5000.0, 20000.0)

PROFILES = {
    "A_current": {
        "mode": "legacy",
        "strength": CURRENT_STRENGTH,
        "growth_cap": None,
    },
    "B_v2_fixed_ratio": {
        "mode": "v2_fixed_ratio",
        "strength": CURRENT_STRENGTH,
        "growth_cap": None,
    },
    "C_v2_fixed_ratio_growth_softcap": {
        "mode": "v2_fixed_ratio",
        "strength": CURRENT_STRENGTH,
        "growth_cap": V2_GROWTH_POWER_CAP,
    },
}


def fixed_attack_speed_check() -> list[dict[str, float]]:
    rows = []
    v2_ratio = V2_DAMAGE_ATTACKS / V2_TRIGGER_ATTACKS
    for attack_speed in FIXED_ATTACK_SPEEDS:
        normal_dps = attack_speed
        barrage_dps = attack_speed / V2_TRIGGER_ATTACKS * V2_DAMAGE_ATTACKS
        rows.append({
            "attack_speed": attack_speed,
            "normal_dps": normal_dps,
            "barrage_dps": barrage_dps,
            "barrage_normal_ratio": barrage_dps / normal_dps,
            "total_power_increase": math.log10(1.0 + v2_ratio),
        })
    return rows


def as_band(value: float) -> str:
    if value < 5000:
        return "AS<5000"
    if value < 10000:
        return "AS5000-9999"
    if value < 20000:
        return "AS10000-19999"
    return "AS>=20000"


def augment(row: dict) -> None:
    acquisition = next(
        (
            (run["run_index"], run["infinite_barrage_first_wave"])
            for run in row["run_rows"]
            if run["infinite_barrage_first_wave"] is not None
        ),
        None,
    )
    row["first_barrage_acquisition"] = acquisition


def summarize(rows: list[dict]) -> dict:
    successes = [row for row in rows if row["success"]]
    acquired = [row for row in rows if row["infinite_barrage_acquired"]]
    not_acquired = [row for row in rows if not row["infinite_barrage_acquired"]]
    w5000_states = [
        row["checkpoints"]["5000"] for row in rows if "5000" in row["checkpoints"]
    ]
    terminal_owned = [
        run
        for row in rows
        for run in row["run_rows"]
        if run["infinite_barrage_owned"]
    ]
    by_as: dict[str, list[dict]] = {}
    for run in terminal_owned:
        by_as.setdefault(as_band(float(run["end_attack_speed"])), []).append(run)
    return {
        "samples": len(rows),
        "reach_rates": {
            str(wave): sum(str(wave) in row["checkpoints"] for row in rows) / len(rows)
            for wave in CHECKPOINTS
        },
        "successes": len(successes),
        "success_rate": len(successes) / len(rows),
        "acquired_trials": len(acquired),
        "acquired_successes": sum(row["success"] for row in acquired),
        "acquired_success_rate": (
            sum(row["success"] for row in acquired) / len(acquired) if acquired else None
        ),
        "not_acquired_trials": len(not_acquired),
        "not_acquired_successes": sum(row["success"] for row in not_acquired),
        "not_acquired_success_rate": (
            sum(row["success"] for row in not_acquired) / len(not_acquired)
            if not_acquired else None
        ),
        "barrage_power_w5000": diag.dist([
            float(state.get("barrage_power", 0.0)) for state in w5000_states
        ]),
        "w5000_margin": diag.dist([
            row["w5000_margin"] for row in successes if row["w5000_margin"] is not None
        ]),
        "terminal_barrage_by_attack_speed": {
            band: {
                "samples": len(items),
                "attack_speed": diag.dist([
                    float(item["end_attack_speed"]) for item in items
                ]),
                "barrage_power": diag.dist([
                    float(item["end_barrage_power"]) for item in items
                ]),
            }
            for band, items in sorted(by_as.items())
        },
        "rows": rows,
    }


def fmt(value, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def markdown(payload: dict) -> str:
    lines = [
        "# Infinite Barrage v2 experimental diagnostic",
        "",
        "Diagnostic only. Formal/default Infinite Barrage remains legacy.",
        "",
        "## Fixed Attack Speed structure check",
        "",
        "| AS | Normal DPS | Barrage DPS | Barrage / Normal | Total Power increase |",
        "|---:|---:|---:|---:|---:|",
    ]
    for row in payload["fixed_attack_speed_check"]:
        lines.append(
            f"| {row['attack_speed']:.0f} | {row['normal_dps']:.0f}"
            f" | {row['barrage_dps']:.0f} | {row['barrage_normal_ratio']:.1%}"
            f" | {row['total_power_increase']:.6f} |"
        )
    lines += [
        "",
        "## W2500 checkpoint paired replay",
        "",
        "| Profile | W4500 | W4750 | W5000 | Barrage acquired success | No Barrage success | Barrage Power W5000 P50 | Margin P50 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, item in payload["profiles"].items():
        acquired = f"{item['acquired_successes']}/{item['acquired_trials']}"
        not_acquired = f"{item['not_acquired_successes']}/{item['not_acquired_trials']}"
        lines.append(
            f"| {label} | {item['reach_rates']['4500']:.0%}"
            f" | {item['reach_rates']['4750']:.0%} | {item['reach_rates']['5000']:.0%}"
            f" | {acquired} | {not_acquired}"
            f" | {fmt(item['barrage_power_w5000']['p50'])}"
            f" | {fmt(item['w5000_margin']['p50'])} |"
        )
    lines += [
        "",
        "## Barrage-owned Run endings by AS",
        "",
        "| Profile | AS band | N | AS P50 | Barrage Power P50 |",
        "|---|---|---:|---:|---:|",
    ]
    for label, item in payload["profiles"].items():
        for band, values in item["terminal_barrage_by_attack_speed"].items():
            lines.append(
                f"| {label} | {band} | {values['samples']}"
                f" | {fmt(values['attack_speed']['p50'], 1)}"
                f" | {fmt(values['barrage_power']['p50'])} |"
            )
    lines += [
        "",
        "## Validation",
        "",
        f"- paired checkpoint states: {payload['state_count']}",
        f"- first Barrage acquisition signatures identical: {payload['first_acquisition_signatures_identical']}",
        f"- errors/nonfinite/overflow: {payload['error_count']}/{payload['nonfinite_count']}/{payload['overflow_count']}",
        "- v2: one Barrage every 20 normal attacks, each worth 5 normal attacks.",
        "- v2 Barrage triggers no Follow-Up, Re-Action, Supplemental, Hit Count, or further Barrage in this aggregate model.",
        "- C applies only the existing stored kill-growth through a 0.25 Power asymptotic softcap.",
        "- No profile is formally adopted.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--states",
        type=Path,
        default=Path("output/w5000_v1_micro_core_10_states_final/w2500_checkpoint_states.pkl.gz"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/w5000_v1_infinite_barrage_v2_10_states"),
    )
    args = parser.parse_args()
    with gzip.open(args.states, "rb") as handle:
        captures = pickle.load(handle)
    if len(captures) != 10:
        raise ValueError(f"expected 10 W2500 states, found {len(captures)}")

    grouped = {label: [] for label in PROFILES}
    errors = []
    for label, profile in PROFILES.items():
        for capture in captures.values():
            try:
                row = integrated.replay_one(
                    capture,
                    label,
                    DP_SCALE,
                    CORE_SCALE,
                    unlimited_boost_config=boost_v02.v02_config(),
                    finale_config=sim.FinaleConfig(enabled=True),
                    diagnostic_checkpoints=CHECKPOINTS,
                    barrage_strength=profile["strength"],
                    barrage_mode=profile["mode"],
                    barrage_v2_growth_power_cap=profile["growth_cap"],
                )
                augment(row)
                grouped[label].append(row)
            except Exception as exc:
                errors.append({
                    "profile": label,
                    "trial": capture["trial"],
                    "type": type(exc).__name__,
                    "message": str(exc),
                })

    profiles = {label: summarize(rows) for label, rows in grouped.items()}
    signatures = {
        label: {
            row["trial"]: row["first_barrage_acquisition"] for row in rows
        }
        for label, rows in grouped.items()
    }
    reference = signatures["A_current"]
    signature_mismatches = [
        {
            "profile": label,
            "trial": trial,
            "expected": reference[trial],
            "actual": signature,
        }
        for label, values in signatures.items()
        for trial, signature in values.items()
        if signature != reference[trial]
    ]
    nonfinite = sum(len(row["nonfinite"]) for rows in grouped.values() for row in rows)
    payload = {
        "state_count": len(captures),
        "trial_ids": sorted(captures),
        "definitions": {
            "v2_trigger_attacks": V2_TRIGGER_ATTACKS,
            "v2_damage_attacks": V2_DAMAGE_ATTACKS,
            "v2_growth_power_cap": V2_GROWTH_POWER_CAP,
            "current_legacy_strength": CURRENT_STRENGTH,
        },
        "fixed_attack_speed_check": fixed_attack_speed_check(),
        "profiles": profiles,
        "first_acquisition_signatures_identical": not signature_mismatches,
        "first_acquisition_signature_mismatches": signature_mismatches,
        "error_count": len(errors),
        "nonfinite_count": nonfinite,
        "overflow_count": sum(item["type"] == "OverflowError" for item in errors),
        "errors": errors,
        "formal_changed": False,
        "balance_adopted": False,
    }
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "infinite_barrage_v2_summary.json"
    report_path = output / "infinite_barrage_v2_report.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(markdown(payload), encoding="utf-8")
    print(json.dumps({
        "report": str(report_path),
        "json": str(json_path),
        "states": len(captures),
        "errors": len(errors),
        "nonfinite": nonfinite,
        "overflow": payload["overflow_count"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
