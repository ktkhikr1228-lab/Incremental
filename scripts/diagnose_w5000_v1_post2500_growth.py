#!/usr/bin/env python3
"""Diagnose post-W2500 permanent growth from ten paired saved states."""

from __future__ import annotations

import argparse
import copy
import dataclasses
import gzip
import json
import math
import pickle
import random
from pathlib import Path

import diagnose_w5000_v1_precore as diag
import replay_w5000_v1_micro_core_profiles as replay
import simulate_first_prestige_v1 as sim


CHECKPOINTS = (3000, 3500, 4000, 4500, 5000)
CONDITIONS = {
    "A_current": {"freeze_dp": False, "freeze_weapon": False, "freeze_relic": False, "fixed_card": False},
    "B_freeze_DP_after_W2500": {"freeze_dp": True, "freeze_weapon": False, "freeze_relic": False, "fixed_card": False},
    "C_freeze_weapon_progression": {"freeze_dp": False, "freeze_weapon": True, "freeze_relic": False, "fixed_card": False},
    "D_freeze_relic_progression": {"freeze_dp": False, "freeze_weapon": False, "freeze_relic": True, "fixed_card": False},
    "E_freeze_permanent_progression": {"freeze_dp": True, "freeze_weapon": True, "freeze_relic": True, "fixed_card": False},
    "F_fixed_card_rng": {"freeze_dp": False, "freeze_weapon": False, "freeze_relic": False, "fixed_card": True},
    "G_freeze_DP_fixed_card_rng": {"freeze_dp": True, "freeze_weapon": False, "freeze_relic": False, "fixed_card": True},
}
WEAPON_FIELDS = (
    "weapon_material", "weapon_acquisitions", "weapon_generations",
    "game_speed_level", "game_speed_material_spent",
)
RELIC_FIELDS = (
    "relic_material", "relic_drops", "relic_generations", "relic_duplicates",
    "relic_types", "relic_quality",
)


def copy_fields(state, names):
    return {name: copy.deepcopy(getattr(state, name)) for name in names}


def restore_fields(state, values):
    for name, value in values.items():
        setattr(state, name, copy.deepcopy(value))


def blank_power(permanent: sim.PermanentState, config: sim.SimConfig) -> float:
    return sim.compute_snapshot(sim.RunState(), permanent, False, config).log_dps


def config_for(capture: dict, flags: dict) -> sim.SimConfig:
    config = replay.base_config(140)
    dp_caps = ()
    if flags["freeze_weapon"]:
        dp_caps = tuple(
            (key, int(capture["permanent"].dp_v01_levels[key]))
            for key in ("weapon_atk", "weapon_find", "weapon_quality")
        )
    return dataclasses.replace(
        config,
        diagnostic_checkpoints=(2500,) + CHECKPOINTS,
        relic_selection_enabled=not flags["freeze_relic"],
        diagnostic_relic_power_wave_cap=2500 if flags["freeze_relic"] else None,
        diagnostic_freeze_weapon_permanent_progression=flags["freeze_weapon"],
        diagnostic_dp_level_caps=dp_caps,
    )


def fresh_streams(capture: dict) -> sim.RNGStreams:
    return replay.restore_streams(capture)


def replay_condition(capture: dict, label: str, flags: dict) -> dict:
    config = config_for(capture, flags)
    permanent = copy.deepcopy(capture["permanent"])
    streams = fresh_streams(capture)
    run = copy.deepcopy(capture["run"])
    fixed_card_state = copy.deepcopy(capture["rng_states"]["card"])
    frozen_weapon = copy_fields(permanent, WEAPON_FIELDS)
    frozen_relic = copy_fields(permanent, RELIC_FIELDS)
    remaining_runs = config.max_attempts - int(capture["attempt"]) + 1
    run_rows = []
    checkpoint_states = {}
    errors = []
    success = False

    for run_index in range(remaining_runs):
        if flags["fixed_card"] and run_index > 0:
            streams.card.setstate(fixed_card_state)
        start = {}

        def capture_start(live_run, live_permanent, live_streams):
            snapshot = sim.compute_snapshot(live_run, live_permanent, False, config)
            start.update({
                "power": snapshot.log_dps,
                "weapon_power": snapshot.weapon_power,
                "relic_power": snapshot.relic_power,
                "card_count": live_run.card_count,
            })

        result = sim.run_once(
            streams.combat,
            "balanced",
            permanent,
            config,
            True,
            initial_run=run if run_index == 0 else None,
            start_wave=2501 if run_index == 0 else 1,
            rng_streams=streams,
            run_start_capture=capture_start,
        )
        for wave, state in result.checkpoint_states.items():
            checkpoint_states.setdefault(str(wave), copy.deepcopy(state))
        end = result.end_state
        before_death = blank_power(permanent, config)

        if flags["freeze_weapon"]:
            restore_fields(permanent, frozen_weapon)
        if flags["freeze_relic"]:
            restore_fields(permanent, frozen_relic)

        if result.reached < 5000:
            sim.store_memory_candidates(result, permanent)
            if not flags["freeze_dp"]:
                sim.award_and_spend_dp_v01(permanent, result.reached, config)
            sim.purchase_game_speed(permanent, config)
            if not flags["freeze_weapon"]:
                sim.convert_surplus_material(permanent, config)
            if not flags["freeze_relic"]:
                sim.forge_relics(streams.relic, permanent, config)
        after_death = blank_power(permanent, config)
        rarity = end["rarity_composition"]
        run_rows.append({
            "run_index": run_index + 1,
            "start_wave": 2501 if run_index == 0 else 1,
            "max_wave": int(result.reached),
            "failure_wave": result.failure_wave,
            "start_power": float(start["power"]),
            "end_power": float(end["normal_power"]),
            "start_to_end_power": float(end["normal_power"] - start["power"]),
            "death_permanent_power_delta": float(after_death - before_death),
            "dp_levels": permanent.dp_v01_levels.copy(),
            "dp_total_level": sum(permanent.dp_v01_levels.values()),
            "dp_balance": permanent.banked_dp,
            "weapon_power": float(end["weapon_power"]),
            "relic_power": float(end["relic_power"]),
            "weapon_material": permanent.weapon_material,
            "relic_material": permanent.relic_material,
            "card_count": int(end["card_count"]),
            "rarity": rarity,
            "boss_devourer_units": float(end["boss_devourer_units"]),
            "boss_devourer_owned": end["cards"].get("boss_devourer", 0) > 0,
            "game_hours": result.combat_seconds / 3600.0,
        })
        if result.reached >= 5000:
            success = True
            break
        run = None

    nonfinite = []
    for row in run_rows:
        for key in ("start_power", "end_power", "death_permanent_power_delta", "weapon_power", "relic_power"):
            if not math.isfinite(float(row[key])):
                nonfinite.append({"run": row["run_index"], "key": key, "value": row[key]})
    return {
        "trial": int(capture["trial"]),
        "condition": label,
        "success": success,
        "runs": len(run_rows),
        "additional_runs": max(0, len(run_rows) - 1),
        "game_hours": sum(row["game_hours"] for row in run_rows),
        "final_wave": max(row["max_wave"] for row in run_rows),
        "checkpoints": checkpoint_states,
        "run_rows": run_rows,
        "nonfinite": nonfinite,
        "errors": errors,
    }


def summarize(rows: list[dict]) -> dict:
    successes = [row for row in rows if row["success"]]
    checkpoints = {}
    for wave in CHECKPOINTS:
        reached = [row["checkpoints"][str(wave)] for row in rows if str(wave) in row["checkpoints"]]
        checkpoints[str(wave)] = {
            "reached": len(reached),
            "reach_rate": len(reached) / len(rows),
            "margin": diag.dist([float(item["margin_power"]) for item in reached]),
            "player_power": diag.dist([float(item["player_power"]) for item in reached]),
        }
    all_runs = [run for row in rows for run in row["run_rows"]]
    final_runs = [row["run_rows"][-1] for row in rows]
    return {
        "samples": len(rows),
        "successes": len(successes),
        "checkpoints": checkpoints,
        "additional_runs_to_w5000": diag.dist([row["additional_runs"] for row in successes]),
        "game_hours_to_w5000": diag.dist([row["game_hours"] for row in successes]),
        "w5000_margin": diag.dist([
            float(row["checkpoints"]["5000"]["margin_power"])
            for row in successes if "5000" in row["checkpoints"]
        ]),
        "final_wave": diag.dist([row["final_wave"] for row in rows]),
        "death_permanent_power_delta": diag.dist([
            run["death_permanent_power_delta"] for run in all_runs if run["failure_wave"] is not None
        ]),
        "run_start_power": diag.dist([run["start_power"] for run in all_runs]),
        "run_end_power": diag.dist([run["end_power"] for run in all_runs]),
        "final_dp_total_level": diag.dist([run["dp_total_level"] for run in final_runs]),
        "final_dp_levels": {
            key: diag.dist([run["dp_levels"][key] for run in final_runs])
            for key in sim.DP_V01_ITEMS
        },
        "final_weapon_power": diag.dist([run["weapon_power"] for run in final_runs]),
        "final_relic_power": diag.dist([run["relic_power"] for run in final_runs]),
        "final_card_count": diag.dist([run["card_count"] for run in final_runs]),
        "final_rarity": {
            rarity: diag.dist([float(run["rarity"].get(rarity, 0)) for run in final_runs])
            for rarity in sim.RARITY_ORDER
        },
        "final_boss_devourer_units": diag.dist([run["boss_devourer_units"] for run in final_runs]),
        "rows": rows,
    }


def fmt(value, digits=2):
    return "—" if value is None else f"{value:.{digits}f}"


def markdown(payload: dict) -> str:
    lines = [
        "# w5000_v1 post-W2500 growth-source diagnosis", "",
        "10 paired saved W2500 states / no Core / post-death runs enabled.", "",
        "Interventions preserve the W2500 checkpoint values. Weapon freeze blocks later material/generation/Game Speed purchases and caps Weapon ATK/Find/Quality DP effects at their checkpoint levels. Relic freeze retains owned relic effects but freezes later relic acquisition/quality and average-power wave growth. Fixed Card RNG restores the saved card stream before every later Run.", "",
        "| Condition | W3000 | W3500 | W4000 | W4500 | W5000 | Add Runs P25/P50/P75 | W5000 Margin P50 | Death ΔPower P50/P75 | Final DP Lv P50 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label in CONDITIONS:
        item = payload["conditions"][label]
        runs = item["additional_runs_to_w5000"]
        lines.append(
            f"| {label} | "
            + " | ".join(f"{item['checkpoints'][str(w)]['reach_rate']:.0%}" for w in CHECKPOINTS)
            + f" | {fmt(runs['p25'],1)}/{fmt(runs['p50'],1)}/{fmt(runs['p75'],1)} | "
            f"{fmt(item['w5000_margin']['p50'],2)} | {fmt(item['death_permanent_power_delta']['p50'],3)}/{fmt(item['death_permanent_power_delta']['p75'],3)} | "
            f"{fmt(item['final_dp_total_level']['p50'],1)} |"
        )
    lines += ["", "## Final-state diagnostics", "", "| Condition | Final Wave P50 | Start Power P50 | End Power P50 | Weapon Power P50 | Relic Power P50 | Cards P50 | Devourer units P50 |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for label in CONDITIONS:
        item = payload["conditions"][label]
        lines.append(
            f"| {label} | {fmt(item['final_wave']['p50'],1)} | {fmt(item['run_start_power']['p50'],2)} | "
            f"{fmt(item['run_end_power']['p50'],2)} | {fmt(item['final_weapon_power']['p50'],2)} | "
            f"{fmt(item['final_relic_power']['p50'],2)} | {fmt(item['final_card_count']['p50'],1)} | "
            f"{fmt(item['final_boss_devourer_units']['p50'],1)} |"
        )
    lines += ["", "## Validation", "", f"- states: {payload['state_count']}", f"- error/nonfinite/overflow: {payload['error_count']}/{payload['nonfinite_count']}/{payload['overflow_count']}", "- Core profiles/coefficients unchanged; no new Core candidate.", "- Formal balance values unchanged; interventions are diagnostic-only.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260828)
    parser.add_argument("--states", type=Path, default=Path("output/w5000_v1_micro_core_10_states_final/w2500_checkpoint_states.pkl.gz"))
    parser.add_argument("--output-dir", type=Path, default=Path("output/w5000_v1_post2500_growth_10_states"))
    args = parser.parse_args()
    with gzip.open(args.states, "rb") as handle:
        captures = pickle.load(handle)
    if len(captures) != 10:
        raise ValueError(f"expected 10 states, found {len(captures)}")
    grouped = {label: [] for label in CONDITIONS}
    errors = []
    for label, flags in CONDITIONS.items():
        for capture in captures.values():
            try:
                grouped[label].append(replay_condition(capture, label, flags))
            except Exception as exc:
                errors.append({"condition": label, "trial": capture["trial"], "type": type(exc).__name__, "message": str(exc)})
    conditions = {label: summarize(grouped[label]) for label in CONDITIONS}
    nonfinite_count = sum(len(row["nonfinite"]) for rows in grouped.values() for row in rows)
    overflow_count = sum(error["type"] == "OverflowError" for error in errors)
    payload = {
        "seed": args.seed,
        "state_count": len(captures),
        "trial_ids": sorted(captures),
        "conditions_definition": CONDITIONS,
        "conditions": conditions,
        "error_count": len(errors),
        "nonfinite_count": nonfinite_count,
        "overflow_count": overflow_count,
        "errors": errors,
        "formal_changed": False,
        "core_candidate_recorded": "medium 20% (provisional, not adopted)",
    }
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = output / "post2500_growth_report.md"
    summary = output / "post2500_growth_summary.json"
    report.write_text(markdown(payload), encoding="utf-8")
    summary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report), "json": str(summary), "states": len(captures), "errors": len(errors), "nonfinite": nonfinite_count, "overflow": overflow_count}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
