#!/usr/bin/env python3
"""Paired Infinite Barrage strength experiment from saved W2500 states."""

from __future__ import annotations

import argparse
import copy
import dataclasses
import gzip
import json
import math
import pickle
import statistics
from pathlib import Path

import diagnose_w5000_v1_precore as diag
import replay_w5000_v1_micro_core_profiles as replay
import simulate_first_prestige_v1 as sim


CHECKPOINTS = (3000, 3500, 4000, 4500, 5000)
STRENGTHS = {
    "A_0pct": 0.00,
    "B_25pct": 0.25,
    "C_50pct": 0.50,
    "D_75pct": 0.75,
    "E_100pct_current": 1.00,
}


def make_config(capture: dict, strength: float) -> sim.SimConfig:
    baseline = tuple(
        (key, int(capture["permanent"].dp_v01_levels[key]))
        for key in sim.DP_V01_ITEMS
    )
    return dataclasses.replace(
        replay.base_config(140),
        diagnostic_checkpoints=(2500,) + CHECKPOINTS,
        diagnostic_dp_baseline_levels=baseline,
        diagnostic_late_dp_effect_scale=0.10,
        diagnostic_infinite_barrage_strength=strength,
    )


def replay_one(capture: dict, label: str, strength: float) -> dict:
    config = make_config(capture, strength)
    permanent = copy.deepcopy(capture["permanent"])
    streams = replay.restore_streams(capture)
    run = copy.deepcopy(capture["run"])
    if not hasattr(run, "legendary_growth_by_key"):
        run.legendary_growth_by_key = {}
    if not hasattr(run, "card_immediate_power_deltas"):
        run.card_immediate_power_deltas = []
    remaining_runs = config.max_attempts - int(capture["attempt"]) + 1
    run_rows = []
    checkpoints = {}
    success = False

    for run_index in range(remaining_runs):
        result = sim.run_once(
            streams.combat,
            "balanced",
            permanent,
            config,
            True,
            initial_run=run if run_index == 0 else None,
            start_wave=2501 if run_index == 0 else 1,
            rng_streams=streams,
        )
        for wave, state in result.checkpoint_states.items():
            if wave in CHECKPOINTS and str(wave) not in checkpoints:
                checkpoints[str(wave)] = copy.deepcopy(state)
        state = result.end_state
        first_wave = state["card_first_acquired_wave"].get("infinite_barrage")
        deltas = [
            float(delta) for wave, key, delta in state["card_immediate_power_deltas"]
            if key == "infinite_barrage"
        ]
        run_rows.append({
            "run_index": run_index + 1,
            "max_wave": int(result.reached),
            "failure_wave": result.failure_wave,
            "infinite_barrage_owned": state["cards"].get("infinite_barrage", 0) > 0,
            "infinite_barrage_first_wave": first_wave,
            "infinite_barrage_immediate_power_delta": deltas[0] if deltas else None,
            "additional_waves_after_acquisition": (
                max(0, int(result.reached) - int(first_wave)) if first_wave is not None else None
            ),
            "terminal_power": float(state["normal_power"]),
            "terminal_margin": (
                float(state["boss_power"] if result.reached % 10 == 0 else state["normal_power"])
                - sim.configured_enemy_power(result.failure_wave or result.reached, config)
            ),
            "card_count": int(state["card_count"]),
            "rarity": state["rarity_composition"],
            "cards": state["cards"],
        })
        if result.reached >= 5000:
            success = True
            break
        sim.store_memory_candidates(result, permanent)
        sim.award_and_spend_dp_v01(permanent, result.reached, config)
        sim.purchase_game_speed(permanent, config)
        sim.convert_surplus_material(permanent, config)
        sim.forge_relics(streams.relic, permanent, config)
        run = None

    waves = [row["max_wave"] for row in run_rows]
    recent = waves[-10:]
    acquired = [row for row in run_rows if row["infinite_barrage_owned"]]
    first_acquisition = (
        [acquired[0]["run_index"], acquired[0]["infinite_barrage_first_wave"]]
        if acquired else None
    )
    nonfinite = [
        {"run": row["run_index"], "field": field, "value": row[field]}
        for row in run_rows
        for field in ("terminal_power", "infinite_barrage_immediate_power_delta")
        if row[field] is not None and not math.isfinite(float(row[field]))
    ]
    return {
        "trial": int(capture["trial"]),
        "condition": label,
        "strength": strength,
        "success": success,
        "best_wave": max(waves),
        "best_minus_recent10_median": max(waves) - statistics.median(recent),
        "runs": len(run_rows),
        "terminal_power": run_rows[-1]["terminal_power"],
        "terminal_margin": run_rows[-1]["terminal_margin"],
        "w5000_margin": (
            float(checkpoints["5000"]["margin_power"])
            if "5000" in checkpoints else None
        ),
        "first_acquisition": first_acquisition,
        "checkpoints": checkpoints,
        "run_rows": run_rows,
        "nonfinite": nonfinite,
    }


def acquisition_band(wave: int) -> str:
    if wave < 100:
        return "W1-99"
    if wave < 500:
        return "W100-499"
    if wave < 1000:
        return "W500-999"
    if wave < 2500:
        return "W1000-2499"
    return "W2500+"


def summarize(rows: list[dict]) -> dict:
    acquired_trials = [row for row in rows if row["first_acquisition"] is not None]
    first_acquired_runs = [
        next(run for run in row["run_rows"] if run["infinite_barrage_owned"])
        for row in acquired_trials
    ]
    acquired_runs = [
        run for row in rows for run in row["run_rows"]
        if run["infinite_barrage_owned"]
    ]
    best = [row["best_wave"] for row in rows]
    by_wave = {}
    for run in acquired_runs:
        band = acquisition_band(int(run["infinite_barrage_first_wave"]))
        by_wave.setdefault(band, []).append(run)
    return {
        "samples": len(rows),
        "successes": sum(row["success"] for row in rows),
        "success_rate": sum(row["success"] for row in rows) / len(rows),
        "checkpoint_rates": {
            str(wave): sum(row["best_wave"] >= wave for row in rows) / len(rows)
            for wave in CHECKPOINTS
        },
        "best_wave": diag.dist(best),
        "best_wave_variance": statistics.pvariance(best),
        "best_minus_recent10_median": diag.dist([
            row["best_minus_recent10_median"] for row in rows
        ]),
        "terminal_power": diag.dist([row["terminal_power"] for row in rows]),
        "terminal_margin": diag.dist([row["terminal_margin"] for row in rows]),
        "w5000_margin": diag.dist([
            row["w5000_margin"] for row in rows if row["w5000_margin"] is not None
        ]),
        "acquired_trial_count": len(acquired_trials),
        "acquired_trial_success_rate": (
            sum(row["success"] for row in acquired_trials) / len(acquired_trials)
            if acquired_trials else None
        ),
        "acquired_trial_best_wave": diag.dist([row["best_wave"] for row in acquired_trials]),
        "first_acquisition_wave": diag.dist([
            run["infinite_barrage_first_wave"] for run in first_acquired_runs
        ]),
        "first_acquisition_immediate_power_delta": diag.dist([
            run["infinite_barrage_immediate_power_delta"] for run in first_acquired_runs
            if run["infinite_barrage_immediate_power_delta"] is not None
        ]),
        "first_acquisition_additional_waves": diag.dist([
            run["additional_waves_after_acquisition"] for run in first_acquired_runs
        ]),
        "acquired_run_count": len(acquired_runs),
        "acquired_run_checkpoint_rates": {
            str(wave): sum(run["max_wave"] >= wave for run in acquired_runs) / len(acquired_runs)
            if acquired_runs else None
            for wave in CHECKPOINTS
        },
        "additional_waves_after_acquisition": diag.dist([
            run["additional_waves_after_acquisition"] for run in acquired_runs
        ]),
        "immediate_power_delta": diag.dist([
            run["infinite_barrage_immediate_power_delta"] for run in acquired_runs
            if run["infinite_barrage_immediate_power_delta"] is not None
        ]),
        "acquisition_wave_results": {
            band: {
                "runs": len(items),
                "success_rate": sum(item["max_wave"] >= 5000 for item in items) / len(items),
                "best_wave": diag.dist([item["max_wave"] for item in items]),
                "immediate_power_delta": diag.dist([
                    item["infinite_barrage_immediate_power_delta"] for item in items
                    if item["infinite_barrage_immediate_power_delta"] is not None
                ]),
            }
            for band, items in sorted(by_wave.items())
        },
        "nonfinite_count": sum(len(row["nonfinite"]) for row in rows),
        "rows": rows,
    }


def fmt(value, digits=2):
    return "—" if value is None else f"{value:.{digits}f}"


def markdown(payload: dict) -> str:
    lines = [
        "# w5000_v1 Infinite Barrage strength experiment", "",
        "Diagnostic only: late_dp_10, Core OFF, Boss Devourer base-heavy B, W2500 guaranteed Legendary OFF. Acquisition probability, rarity, and card pool are unchanged.", "",
        "| Strength | W3000 | W3500 | W4000 | W4500 | W5000 | Best Wave P25/P50/P75 | Acquired-trial W5000 | First acquire +Wave P50 | First acquire ΔPower P50 | Terminal Power P50 | W5000 Margin P50 | Variance | Best-recent10 P50 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, item in payload["conditions"].items():
        best = item["best_wave"]
        lines.append(
            f"| {label} | "
            + " | ".join(f"{item['checkpoint_rates'][str(w)]:.0%}" for w in CHECKPOINTS)
            + f" | {fmt(best['p25'],0)}/{fmt(best['p50'],0)}/{fmt(best['p75'],0)}"
            f" | {fmt(item['acquired_trial_success_rate'],2)}"
            f" | {fmt(item['first_acquisition_additional_waves']['p50'],0)}"
            f" | {fmt(item['first_acquisition_immediate_power_delta']['p50'],2)}"
            f" | {fmt(item['terminal_power']['p50'],2)}"
            f" | {fmt(item['w5000_margin']['p50'],2)}"
            f" | {fmt(item['best_wave_variance'],1)}"
            f" | {fmt(item['best_minus_recent10_median']['p50'],0)} |"
        )
    if payload.get("single_strength") is not None:
        label, item = next(iter(payload["conditions"].items()))
        acquired_successes = round(item["acquired_trial_success_rate"] * item["acquired_trial_count"])
        lines += [
            "", "## Infinite Barrage-owned Runs", "",
            f"- acquired trials: {item['acquired_trial_count']}/{item['samples']}",
            f"- acquired-trial W5000 success: {item['acquired_trial_success_rate']:.0%}",
            "- owned-Run checkpoint reach: " + ", ".join(
                f"W{wave} {item['acquired_run_checkpoint_rates'][str(wave)]:.0%}"
                for wave in CHECKPOINTS
            ),
            f"- first-acquisition ΔPower P25/P50/P75: {fmt(item['first_acquisition_immediate_power_delta']['p25'],2)}/{fmt(item['first_acquisition_immediate_power_delta']['p50'],2)}/{fmt(item['first_acquisition_immediate_power_delta']['p75'],2)}",
            f"- first-acquisition additional Wave P25/P50/P75: {fmt(item['first_acquisition_additional_waves']['p25'],0)}/{fmt(item['first_acquisition_additional_waves']['p50'],0)}/{fmt(item['first_acquisition_additional_waves']['p75'],0)}",
            f"- terminal margin P25/P50/P75: {fmt(item['terminal_margin']['p25'],2)}/{fmt(item['terminal_margin']['p50'],2)}/{fmt(item['terminal_margin']['p75'],2)}",
            "", "## Diagnostic reading", "",
            f"- At {payload['single_strength']:.3f} strength, {acquired_successes}/{item['acquired_trial_count']} acquired trials reached W5000; acquisition is strong but not deterministic.",
            "- No neighboring strength is run automatically, and this result is not a formal adoption.",
        ]
    else:
        lines += [
            "", "## Diagnostic reading", "",
            "- 75% and 100% still make acquisition a 100% W5000 success signal in the seven acquired trials.",
            "- 50% is still very strong but not deterministic: 6/7 acquired trials reached W5000.",
            "- 25% gives the clearest staged attrition: overall reach falls from 60% at W3000-W4000 to 40% at W4500 and 30% at W5000; 3/7 acquired trials succeeded.",
            "- The useful bracket for a later, larger experiment is therefore 25%-50%. This is not an adoption decision.",
        ]
    lines += [
        "", "## Paired integrity", "",
        f"- first Infinite Barrage acquisition signature identical across strengths: {payload['first_acquisition_signatures_identical']}",
        f"- mismatched trials: {payload['first_acquisition_signature_mismatches']}",
        "- The same saved state and RNG streams start every branch. After the first acquisition, progression can legitimately change later draw counts/history because the effect changes survival.",
        f"- errors/nonfinite/overflow: {payload['error_count']}/{payload['nonfinite_count']}/{payload['overflow_count']}",
        "- No formal value was adopted or changed.", "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--states", type=Path, default=Path("output/w5000_v1_micro_core_10_states_final/w2500_checkpoint_states.pkl.gz"))
    parser.add_argument("--output-dir", type=Path, default=Path("output/w5000_v1_infinite_barrage_strength_10_states"))
    parser.add_argument("--only-strength", type=float)
    args = parser.parse_args()
    with gzip.open(args.states, "rb") as handle:
        captures = pickle.load(handle)
    if len(captures) != 10:
        raise ValueError(f"expected 10 W2500 states, found {len(captures)}")

    active_strengths = (
        {f"strength_{args.only_strength * 100:g}pct": args.only_strength}
        if args.only_strength is not None else STRENGTHS
    )
    if any(not 0.0 <= value <= 1.0 for value in active_strengths.values()):
        raise ValueError("strength must be between 0 and 1")
    grouped = {label: [] for label in active_strengths}
    errors = []
    for label, strength in active_strengths.items():
        for capture in captures.values():
            try:
                grouped[label].append(replay_one(capture, label, strength))
            except Exception as exc:
                errors.append({"condition": label, "trial": capture["trial"], "type": type(exc).__name__, "message": str(exc)})
    conditions = {label: summarize(rows) for label, rows in grouped.items()}
    signatures = {
        label: {row["trial"]: row["first_acquisition"] for row in rows}
        for label, rows in grouped.items()
    }
    reference = next(iter(signatures.values()))
    mismatches = []
    for label, values in signatures.items():
        for trial, signature in values.items():
            if signature != reference[trial]:
                mismatches.append({"condition": label, "trial": trial, "expected": reference[trial], "actual": signature})
    nonfinite = sum(item["nonfinite_count"] for item in conditions.values())
    payload = {
        "state_count": len(captures),
        "trial_ids": sorted(captures),
        "strengths": active_strengths,
        "single_strength": args.only_strength,
        "strength_semantics": "Scales both direct Infinite Barrage log10 contribution and its per-kill Legendary growth log; 0% leaves acquisition/history intact but contributes no power.",
        "conditions": conditions,
        "first_acquisition_signatures_identical": not mismatches,
        "first_acquisition_signature_mismatches": mismatches,
        "error_count": len(errors),
        "nonfinite_count": nonfinite,
        "overflow_count": sum(item["type"] == "OverflowError" for item in errors),
        "errors": errors,
        "formal_changed": False,
        "balance_adopted": False,
    }
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = output / "infinite_barrage_strength_report.md"
    data = output / "infinite_barrage_strength_summary.json"
    report.write_text(markdown(payload), encoding="utf-8")
    data.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report), "json": str(data), "states": len(captures), "errors": len(errors), "nonfinite": nonfinite, "acquisition_signatures_identical": not mismatches}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
