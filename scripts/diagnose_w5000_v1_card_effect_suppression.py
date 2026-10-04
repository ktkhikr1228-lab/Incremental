#!/usr/bin/env python3
"""Paired post-W2500 card-effect suppression diagnosis for w5000_v1."""

from __future__ import annotations

import argparse
import collections
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
REQUESTED_LEGENDARIES = {
    "Infinite Barrage": "infinite_barrage",
    "Critical Singularity": "critical_singularity",
    "Critical Overload": "critical_overload",
    "Recursive FU": "recursive_follow_up",
    "Endless Action": "endless_action",
    "Fractal Barrage": "fractal_barrage",
    "Supplemental Singularity": "supplemental_singularity",
    "Knowledge Collapse": "knowledge_collapse",
}


def make_config(capture: dict, suppressed: frozenset[str]) -> sim.SimConfig:
    baseline = tuple(
        (key, int(capture["permanent"].dp_v01_levels[key]))
        for key in sim.DP_V01_ITEMS
    )
    return dataclasses.replace(
        replay.base_config(140),
        diagnostic_checkpoints=(2500,) + CHECKPOINTS,
        diagnostic_dp_baseline_levels=baseline,
        diagnostic_late_dp_effect_scale=0.10,
        diagnostic_suppressed_card_keys=suppressed,
    )


def boss_devourer_power(run: sim.RunState, config: sim.SimConfig) -> tuple[float, float]:
    if not sim.n(run.counts, "boss_devourer"):
        return 0.0, 0.0
    growth = run.boss_devourer_units * math.log10(
        1 + 0.15 * sim.positive_amp(run, "boss_devourer")
    )
    return config.diagnostic_boss_devourer_base_power, growth


def replay_one(capture: dict, label: str, suppressed: frozenset[str]) -> dict:
    config = make_config(capture, suppressed)
    permanent = copy.deepcopy(capture["permanent"])
    streams = replay.restore_streams(capture)
    run = copy.deepcopy(capture["run"])
    if not hasattr(run, "legendary_growth_by_key"):
        run.legendary_growth_by_key = {}
    remaining_runs = config.max_attempts - int(capture["attempt"]) + 1
    rows = []
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
        base_dev, growth_dev = boss_devourer_power(
            # result.end_state intentionally exposes acquisition, while the
            # live run retains growth counters needed for attribution.
            run if run_index == 0 and result.reached == run.kills else sim.RunState(),
            config,
        )
        # Reconstruct Devourer potential from the observational end state.
        if state["cards"].get("boss_devourer", 0):
            base_dev = config.diagnostic_boss_devourer_base_power
            growth_dev = float(state["boss_devourer_units"]) * math.log10(1.15)
        else:
            base_dev = growth_dev = 0.0
        row = {
            "run_index": run_index + 1,
            "max_wave": int(result.reached),
            "failure_wave": result.failure_wave,
            "reaches": {str(w): result.reached >= w for w in CHECKPOINTS},
            "rarity": state["rarity_composition"],
            "cards": state["cards"],
            "first_acquired_wave": state["card_first_acquired_wave"],
            "acquisition_log": state["card_acquisition_log"],
            "card_count": int(state["card_count"]),
            "player_power": float(state["normal_power"]),
            "boss_power": float(state["boss_power"]),
            "boss_devourer_base_power": base_dev,
            "boss_devourer_growth_power": growth_dev,
            "boss_devourer_units": float(state["boss_devourer_units"]),
        }
        rows.append(row)
        if result.reached >= 5000:
            success = True
            break
        sim.store_memory_candidates(result, permanent)
        sim.award_and_spend_dp_v01(permanent, result.reached, config)
        sim.purchase_game_speed(permanent, config)
        sim.convert_surplus_material(permanent, config)
        sim.forge_relics(streams.relic, permanent, config)
        run = None

    values = [row["player_power"] for row in rows]
    nonfinite = [value for value in values if not math.isfinite(value)]
    return {
        "trial": int(capture["trial"]),
        "condition": label,
        "suppressed_keys": sorted(suppressed),
        "success": success,
        "best_wave": max(row["max_wave"] for row in rows),
        "runs": len(rows),
        "terminal_power": rows[-1]["player_power"],
        "w5000_margin": (
            float(checkpoints["5000"]["margin_power"])
            if "5000" in checkpoints else None
        ),
        "checkpoints": checkpoints,
        "run_rows": rows,
        "nonfinite": nonfinite,
    }


def summarize(rows: list[dict]) -> dict:
    best = [row["best_wave"] for row in rows]
    all_runs = [item for row in rows for item in row["run_rows"]]
    return {
        "samples": len(rows),
        "successes": sum(row["success"] for row in rows),
        "success_rate": sum(row["success"] for row in rows) / len(rows),
        "best_wave": diag.dist(best),
        "best_wave_variance": statistics.pvariance(best),
        "checkpoint_rates": {
            str(wave): sum(row["best_wave"] >= wave for row in rows) / len(rows)
            for wave in CHECKPOINTS
        },
        "w5000_margin": diag.dist([
            row["w5000_margin"] for row in rows if row["w5000_margin"] is not None
        ]),
        "run_count": len(all_runs),
        "nonfinite_count": sum(len(row["nonfinite"]) for row in rows),
        "rows": rows,
    }


def card_associations(rows: list[dict]) -> dict[str, dict]:
    runs = [run for row in rows for run in row["run_rows"]]
    successful = [run for run in runs if run["max_wave"] >= 5000]
    failed = [run for run in runs if run["max_wave"] < 5000]
    output = {}
    for item in sim.CARDS:
        acquired = [run for run in runs if run["cards"].get(item.key, 0) > 0]
        if not acquired:
            continue
        success_owned = [run for run in successful if run["cards"].get(item.key, 0) > 0]
        failed_owned = [run for run in failed if run["cards"].get(item.key, 0) > 0]
        output[item.key] = {
            "rarity": item.rarity,
            "acquired_runs": len(acquired),
            "success_run_acquisition_rate": len(success_owned) / len(successful) if successful else None,
            "failed_run_acquisition_rate": len(failed_owned) / len(failed) if failed else None,
            "first_wave_success": diag.dist([
                run["first_acquired_wave"][item.key] for run in success_owned
            ]),
            "first_wave_failure": diag.dist([
                run["first_acquired_wave"][item.key] for run in failed_owned
            ]),
            "stacks_success": diag.dist([run["cards"][item.key] for run in success_owned]),
            "stacks_failure": diag.dist([run["cards"][item.key] for run in failed_owned]),
            "max_wave_owned": diag.dist([run["max_wave"] for run in acquired]),
            "max_wave_not_owned": diag.dist([
                run["max_wave"] for run in runs if run["cards"].get(item.key, 0) == 0
            ]),
        }
    return output


def association_rank(associations: dict[str, dict], rarity: str) -> list[str]:
    candidates = []
    for key, item in associations.items():
        if item["rarity"] != rarity or item["acquired_runs"] < 2:
            continue
        success_rate = item["success_run_acquisition_rate"] or 0.0
        failure_rate = item["failed_run_acquisition_rate"] or 0.0
        candidates.append((abs(success_rate - failure_rate), item["acquired_runs"], key))
    return [key for _, _, key in sorted(candidates, reverse=True)[:3]]


def paired_effect(baseline: list[dict], suppressed: list[dict]) -> dict:
    by_trial = {row["trial"]: row for row in baseline}
    deltas_wave = []
    deltas_power = []
    for row in suppressed:
        base = by_trial[row["trial"]]
        deltas_wave.append(row["best_wave"] - base["best_wave"])
        deltas_power.append(row["terminal_power"] - base["terminal_power"])
    return {
        "delta_best_wave": diag.dist(deltas_wave),
        "delta_terminal_power": diag.dist(deltas_power),
        "success_rate_delta": (
            sum(row["success"] for row in suppressed) - sum(row["success"] for row in baseline)
        ) / len(baseline),
    }


def fmt(value, digits=2):
    return "—" if value is None else f"{value:.{digits}f}"


def markdown(payload: dict) -> str:
    current = payload["conditions"]["A_current"]
    legendary = payload["conditions"]["B_legendary_suppressed"]
    epic = payload["conditions"]["C_epic_suppressed"]
    rare = payload["conditions"]["D_rare_suppressed"]
    barrage = payload["individual_cards"].get("infinite_barrage", {})
    barrage_pair = barrage.get("paired", {})
    lines = [
        "# w5000_v1 post-W2500 card effect suppression", "",
        "Diagnostic baseline: late_dp_10, Core OFF, DP v0.1, Boss Devourer base-heavy B, W2500 guaranteed Legendary OFF.", "",
        "## Main finding", "",
        f"- Baseline W5000 success: {current['successes']}/{current['samples']}; Legendary effects suppressed: {legendary['successes']}/{legendary['samples']}; Epic suppressed: {epic['successes']}/{epic['samples']}; Rare suppressed: {rare['successes']}/{rare['samples']}.",
        f"- `infinite_barrage` alone changed success by {fmt(barrage_pair.get('success_rate_delta'),2)}, paired best-Wave P50 by {fmt(barrage_pair.get('delta_best_wave',{}).get('p50'),0)}, and terminal Power P50 by {fmt(barrage_pair.get('delta_terminal_power',{}).get('p50'),2)}.",
        "- `critical_overload`, `endless_action`, `fractal_barrage`, and `supplemental_singularity` are absent from the active pool and were not imported from the separate Legendary v0.1 probe.", "",
        "## Rarity-tier matched suppression", "",
        "| Condition | W3000 | W3500 | W4000 | W4500 | W5000 | Best Wave P25/P50/P75 | Variance | ΔWave P50 | ΔPower P50 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    baseline = payload["conditions"]["A_current"]
    for label, item in payload["conditions"].items():
        paired = item.get("paired", {})
        dist = item["best_wave"]
        lines.append(
            f"| {label} | "
            + " | ".join(f"{item['checkpoint_rates'][str(w)]:.0%}" for w in CHECKPOINTS)
            + f" | {fmt(dist['p25'],0)}/{fmt(dist['p50'],0)}/{fmt(dist['p75'],0)}"
            f" | {fmt(item['best_wave_variance'],1)} | {fmt(paired.get('delta_best_wave', {}).get('p50'),0)}"
            f" | {fmt(paired.get('delta_terminal_power', {}).get('p50'),2)} |"
        )
    lines += ["", "## Individual matched suppression", "", "| Card | Rarity | Active pool | Baseline acquired runs | ΔWave P50 | ΔPower P50 | Success Δ |", "|---|---:|---:|---:|---:|---:|---:|"]
    for key, item in payload["individual_cards"].items():
        paired = item.get("paired", {})
        lines.append(
            f"| {key} | {item.get('rarity','—')} | {'yes' if item['active_pool'] else 'no'} | "
            f"{item.get('baseline_acquired_runs',0)} | {fmt(paired.get('delta_best_wave',{}).get('p50'),0)} | "
            f"{fmt(paired.get('delta_terminal_power',{}).get('p50'),2)} | {fmt(paired.get('success_rate_delta'),2)} |"
        )
    lines += ["", "## Interpretation guards", "", "- Cards remain in the draw pool and acquisition records; only effects are suppressed.", "- Correlation tables are observational. Causal labels are reserved for matched effect-suppression deltas.", "- Downstream hands may diverge naturally after an effect changes XP/progression; the checkpoint state and RNG streams are paired at intervention start.", f"- errors/nonfinite/overflow: {payload['error_count']}/{payload['nonfinite_count']}/{payload['overflow_count']}", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--states", type=Path, default=Path("output/w5000_v1_micro_core_10_states_final/w2500_checkpoint_states.pkl.gz"))
    parser.add_argument("--output-dir", type=Path, default=Path("output/w5000_v1_card_effect_suppression_10_states"))
    args = parser.parse_args()
    with gzip.open(args.states, "rb") as handle:
        captures = pickle.load(handle)
    if len(captures) != 10:
        raise ValueError(f"expected 10 W2500 states, found {len(captures)}")

    rarity_keys = {
        rarity: frozenset(item.key for item in sim.CARDS if item.rarity == rarity)
        for rarity in ("R", "E", "L")
    }
    condition_keys = {
        "A_current": frozenset(),
        "B_legendary_suppressed": rarity_keys["L"],
        "C_epic_suppressed": rarity_keys["E"],
        "D_rare_suppressed": rarity_keys["R"],
        "E_epic_legendary_suppressed": rarity_keys["E"] | rarity_keys["L"],
    }
    grouped: dict[str, list[dict]] = {key: [] for key in condition_keys}
    errors = []
    for label, keys in condition_keys.items():
        for capture in captures.values():
            try:
                grouped[label].append(replay_one(capture, label, keys))
            except Exception as exc:
                errors.append({"condition": label, "trial": capture["trial"], "type": type(exc).__name__, "message": str(exc)})
    baseline = grouped["A_current"]
    associations = card_associations(baseline)
    selected = set(association_rank(associations, "R") + association_rank(associations, "E"))
    selected.update(
        key for key in REQUESTED_LEGENDARIES.values()
        if key in sim.CARD_BY_KEY and associations.get(key, {}).get("acquired_runs", 0) >= 2
    )
    individual_rows = {}
    for key in sorted(selected):
        rows = []
        for capture in captures.values():
            try:
                rows.append(replay_one(capture, f"suppress_{key}", frozenset({key})))
            except Exception as exc:
                errors.append({"condition": f"suppress_{key}", "trial": capture["trial"], "type": type(exc).__name__, "message": str(exc)})
        individual_rows[key] = rows

    conditions = {label: summarize(rows) for label, rows in grouped.items()}
    for label, item in conditions.items():
        if label != "A_current":
            item["paired"] = paired_effect(baseline, grouped[label])
    individual = {}
    requested_keys = set(REQUESTED_LEGENDARIES.values())
    for key in sorted(selected | requested_keys):
        active = key in sim.CARD_BY_KEY
        entry = {
            "active_pool": active,
            "rarity": sim.CARD_BY_KEY[key].rarity if active else None,
            "baseline_acquired_runs": associations.get(key, {}).get("acquired_runs", 0),
            "correlation": associations.get(key),
        }
        if key in individual_rows:
            entry["summary"] = summarize(individual_rows[key])
            entry["paired"] = paired_effect(baseline, individual_rows[key])
        else:
            entry["not_replayed_reason"] = "not in active pool" if not active else "fewer than 2 acquired baseline runs"
        individual[key] = entry

    nonfinite = sum(item["nonfinite_count"] for item in conditions.values())
    nonfinite += sum(
        sum(len(row["nonfinite"]) for row in rows)
        for rows in individual_rows.values()
    )
    payload = {
        "state_count": len(captures),
        "trial_ids": sorted(captures),
        "baseline": "late_dp_10 / no_core / DP v0.1 / Boss Devourer base-heavy B / guaranteed Legendary OFF",
        "conditions": conditions,
        "associations": associations,
        "selected_major_rare_epic": sorted(selected - requested_keys),
        "individual_cards": individual,
        "requested_legendary_name_to_key": REQUESTED_LEGENDARIES,
        "error_count": len(errors),
        "nonfinite_count": nonfinite,
        "overflow_count": sum(item["type"] == "OverflowError" for item in errors),
        "errors": errors,
        "formal_changed": False,
        "balance_changed": False,
    }
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = output / "card_effect_suppression_report.md"
    data = output / "card_effect_suppression_summary.json"
    report.write_text(markdown(payload), encoding="utf-8")
    data.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report), "json": str(data), "states": len(captures), "individual_replays": len(individual_rows), "errors": len(errors), "nonfinite": nonfinite}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
