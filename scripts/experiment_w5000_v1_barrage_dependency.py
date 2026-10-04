#!/usr/bin/env python3
"""Matched Infinite Barrage dependency diagnostic with Boost v0.2 fixed."""

from __future__ import annotations

import argparse
import gzip
import json
import pickle
from pathlib import Path

import diagnose_w5000_v1_precore as diag
import experiment_w5000_v1_integrated_core_dp as integrated
import experiment_w5000_v1_unlimited_boost_v02 as boost_v02
import simulate_first_prestige_v1 as sim


DP_SCALE = 0.10
CORE_SCALE = 0.15
CHECKPOINTS = (4000, 4500, 4750, 5000)
CURRENT_STRENGTH = 0.375
PROFILES = {
    "A_current": (CURRENT_STRENGTH, None),
    "B_effect_off": (0.0, None),
    "C_half_effect": (CURRENT_STRENGTH * 0.50, None),
    "D_softcap_20_power": (CURRENT_STRENGTH, 20.0),
}


def fmt(value, digits=2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def augment(row: dict) -> None:
    first_w4000 = next(
        (i for i, run in enumerate(row["run_rows"]) if run["max_wave"] >= 4000), None
    )
    success_run = next(
        (i for i, run in enumerate(row["run_rows"]) if run["max_wave"] >= 5000), None
    )
    row["w4000_to_w5000_runs"] = (
        None if first_w4000 is None or success_run is None else success_run - first_w4000
    )
    row["w4000_same_run_w5000"] = (
        first_w4000 is not None and success_run == first_w4000
    )
    acquisition = next(
        (
            (run["run_index"], run["infinite_barrage_first_wave"])
            for run in row["run_rows"]
            if run["infinite_barrage_first_wave"] is not None
        ),
        None,
    )
    row["first_barrage_acquisition"] = acquisition


def as_band(value: float) -> str:
    if value < 5000:
        return "AS<5000"
    if value < 10000:
        return "AS5000-9999"
    if value < 20000:
        return "AS10000-19999"
    return "AS>=20000"


def summarize(rows: list[dict]) -> dict:
    successes = [row for row in rows if row["success"]]
    reached_w4000 = [row for row in rows if "4000" in row["checkpoints"]]
    acquired = [row for row in rows if row["infinite_barrage_acquired"]]
    not_acquired = [row for row in rows if not row["infinite_barrage_acquired"]]
    w5000_states = [
        (row["trial"], row["checkpoints"]["5000"])
        for row in rows if "5000" in row["checkpoints"]
    ]
    by_as: dict[str, list[dict]] = {}
    for _, state in w5000_states:
        by_as.setdefault(as_band(float(state["attack_speed"])), []).append(state)
    terminal_by_as: dict[str, list[dict]] = {}
    for row in rows:
        for run in row["run_rows"]:
            if run["infinite_barrage_owned"]:
                terminal_by_as.setdefault(
                    as_band(float(run["end_attack_speed"])), []
                ).append(run)
    return {
        "samples": len(rows),
        "successes": len(successes),
        "success_rate": len(successes) / len(rows) if rows else None,
        "reach_rates": {
            str(wave): sum(str(wave) in row["checkpoints"] for row in rows) / len(rows)
            for wave in (4500, 4750, 5000)
        },
        "w5000_margin": diag.dist([
            row["w5000_margin"] for row in successes if row["w5000_margin"] is not None
        ]),
        "barrage_power_w5000": diag.dist([
            float(state.get("barrage_power", 0.0)) for _, state in w5000_states
        ]),
        "boost_power_w5000": diag.dist([
            float(state.get("boost_power", 0.0)) for _, state in w5000_states
        ]),
        "checkpoint_power": {
            str(wave): {
                "reached": sum(str(wave) in row["checkpoints"] for row in rows),
                "barrage_power": diag.dist([
                    float(row["checkpoints"][str(wave)].get("barrage_power", 0.0))
                    for row in rows if str(wave) in row["checkpoints"]
                ]),
                "boost_power": diag.dist([
                    float(row["checkpoints"][str(wave)].get("boost_power", 0.0))
                    for row in rows if str(wave) in row["checkpoints"]
                ]),
            }
            for wave in (4500, 4750, 5000)
        },
        "w4000_to_w5000_runs": diag.dist([
            row["w4000_to_w5000_runs"] for row in successes
            if row["w4000_to_w5000_runs"] is not None
        ]),
        "same_run_w5000_rate": (
            sum(row["w4000_same_run_w5000"] for row in reached_w4000)
            / len(reached_w4000) if reached_w4000 else None
        ),
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
        "first_acquisition_wave": diag.dist([
            row["first_barrage_acquisition"][1]
            for row in acquired if row["first_barrage_acquisition"] is not None
        ]),
        "barrage_by_attack_speed": {
            band: {
                "samples": len(states),
                "attack_speed": diag.dist([float(state["attack_speed"]) for state in states]),
                "barrage_power": diag.dist([
                    float(state.get("barrage_power", 0.0)) for state in states
                ]),
            }
            for band, states in sorted(by_as.items())
        },
        "terminal_barrage_by_attack_speed": {
            band: {
                "samples": len(runs),
                "attack_speed": diag.dist([
                    float(run["end_attack_speed"]) for run in runs
                ]),
                "barrage_power": diag.dist([
                    float(run["end_barrage_power"]) for run in runs
                ]),
                "max_wave": diag.dist([float(run["max_wave"]) for run in runs]),
            }
            for band, runs in sorted(terminal_by_as.items())
        },
        "w5000_as_power_pairs": [
            {
                "trial": trial,
                "attack_speed": float(state["attack_speed"]),
                "barrage_power": float(state.get("barrage_power", 0.0)),
            }
            for trial, state in w5000_states
        ],
        "rows": rows,
    }


def markdown(payload: dict) -> str:
    lines = [
        "# w5000_v1 Infinite Barrage dependency diagnostic", "",
        "Unlimited Boost v0.2 fixed. Finale v0.1 ON; Core flat 15%, late DP 10%, Boss Devourer base-heavy B.", "",
        "C means 50% of the current 37.5% effect (effective strength 18.75%). D applies `20 * (1 - exp(-raw / 20))` to total Barrage Power.", "",
        "| Profile | W4500 | W4750 | W5000 | Margin P50 | Barrage Power P50 | Boost Power P50 | Same-run | Extra Runs P25/P50/P75 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, item in payload["profiles"].items():
        runs = item["w4000_to_w5000_runs"]
        lines.append(
            f"| {label} | {item['reach_rates']['4500']:.0%} | {item['reach_rates']['4750']:.0%} | {item['reach_rates']['5000']:.0%}"
            f" | {fmt(item['w5000_margin']['p50'])} | {fmt(item['barrage_power_w5000']['p50'])}"
            f" | {fmt(item['boost_power_w5000']['p50'])}"
            f" | {fmt(100 * item['same_run_w5000_rate'],0) if item['same_run_w5000_rate'] is not None else '—'}%"
            f" | {fmt(runs['p25'],1)}/{fmt(runs['p50'],1)}/{fmt(runs['p75'],1)} |"
        )
    lines += ["", "## Acquisition split", "", "| Profile | Acquired success | No-acquisition success | First acquire Wave P50 |", "|---|---:|---:|---:|"]
    for label, item in payload["profiles"].items():
        lines.append(
            f"| {label} | {item['acquired_successes']}/{item['acquired_trials']}"
            f" | {item['not_acquired_successes']}/{item['not_acquired_trials']}"
            f" | {fmt(item['first_acquisition_wave']['p50'],0)} |"
        )
    lines += ["", "## Barrage contribution by W5000 Attack Speed", "", "| Profile | AS band | N | AS P50 | Barrage Power P50 |", "|---|---|---:|---:|---:|"]
    for label, item in payload["profiles"].items():
        for band, values in item["barrage_by_attack_speed"].items():
            lines.append(
                f"| {label} | {band} | {values['samples']}"
                f" | {fmt(values['attack_speed']['p50'])}"
                f" | {fmt(values['barrage_power']['p50'])} |"
            )
    lines += ["", "## Barrage-owned Run endings by Attack Speed", "", "| Profile | AS band | N | AS P50 | Barrage Power P50 | Max Wave P50 |", "|---|---|---:|---:|---:|---:|"]
    for label, item in payload["profiles"].items():
        for band, values in item["terminal_barrage_by_attack_speed"].items():
            lines.append(
                f"| {label} | {band} | {values['samples']}"
                f" | {fmt(values['attack_speed']['p50'])}"
                f" | {fmt(values['barrage_power']['p50'])}"
                f" | {fmt(values['max_wave']['p50'],0)} |"
            )
    lines += [
        "", "## Validation", "",
        f"- paired states: {payload['state_count']}",
        f"- first acquisition signature identical through the common prefix: {payload['first_acquisition_signatures_identical']}",
        f"- errors/nonfinite/overflow: {payload['error_count']}/{payload['nonfinite_count']}/{payload['overflow_count']}",
        "- Boost v0.2 values and every non-Barrage balance value are unchanged.",
        "- No Barrage profile is formally adopted.", "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--states", type=Path,
        default=Path("output/w5000_v1_micro_core_10_states_final/w2500_checkpoint_states.pkl.gz"),
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("output/w5000_v1_barrage_dependency_10_states"),
    )
    args = parser.parse_args()
    with gzip.open(args.states, "rb") as handle:
        captures = pickle.load(handle)
    if len(captures) != 10:
        raise ValueError(f"expected 10 W2500 states, found {len(captures)}")

    grouped = {label: [] for label in PROFILES}
    errors = []
    for label, (strength, cap) in PROFILES.items():
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
                    barrage_strength=strength,
                    barrage_power_cap=cap,
                )
                augment(row)
                grouped[label].append(row)
            except Exception as exc:
                errors.append({
                    "profile": label, "trial": capture["trial"],
                    "type": type(exc).__name__, "message": str(exc),
                })

    profiles = {label: summarize(rows) for label, rows in grouped.items()}
    signatures = {
        label: {row["trial"]: row["first_barrage_acquisition"] for row in rows}
        for label, rows in grouped.items()
    }
    reference = signatures["A_current"]
    mismatches = [
        {"profile": label, "trial": trial, "expected": reference[trial], "actual": sig}
        for label, values in signatures.items()
        for trial, sig in values.items()
        if sig != reference[trial]
    ]
    nonfinite = sum(len(row["nonfinite"]) for rows in grouped.values() for row in rows)
    payload = {
        "state_count": len(captures), "trial_ids": sorted(captures),
        "profiles": profiles,
        "first_acquisition_signatures_identical": not mismatches,
        "first_acquisition_signature_mismatches": mismatches,
        "error_count": len(errors), "nonfinite_count": nonfinite,
        "overflow_count": sum(error["type"] == "OverflowError" for error in errors),
        "errors": errors, "formal_changed": False, "balance_adopted": False,
    }
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = output / "barrage_dependency_report.md"
    summary = output / "barrage_dependency_summary.json"
    report.write_text(markdown(payload), encoding="utf-8")
    summary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "report": str(report), "json": str(summary), "states": len(captures),
        "errors": len(errors), "nonfinite": nonfinite,
        "overflow": payload["overflow_count"],
        "first_acquisition_signatures_identical": not mismatches,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
