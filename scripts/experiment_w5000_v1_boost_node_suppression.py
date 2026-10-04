#!/usr/bin/env python3
"""Matched effect-suppression audit for Unlimited Boost v0.1 nodes."""

from __future__ import annotations

import argparse
import collections
import gzip
import json
import pickle
from pathlib import Path

import diagnose_w5000_v1_precore as diag
import experiment_w5000_v1_integrated_core_dp as integrated
import simulate_first_prestige_v1 as sim


DP_SCALE = 0.10
CORE_SCALE = 0.15
CHECKPOINTS = (4000, 4500, 4600, 4700, 4800, 4900, 5000)
PROFILES = {
    "A_full_boost": (),
    "B_base_atk_off": ("base_atk",),
    "C_weapon_atk_off": ("weapon_atk",),
    "D_attack_speed_off": ("attack_speed",),
    "E_crit_multiplier_off": ("crit_multiplier",),
    "F_all_damage_off": ("all_damage",),
    "G_boss_damage_off": ("boss_damage",),
}


def fmt(value, digits=2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def augment_w4000(row: dict) -> None:
    first_index = next(
        (index for index, run in enumerate(row["run_rows"]) if run["max_wave"] >= 4000),
        None,
    )
    success_index = next(
        (index for index, run in enumerate(row["run_rows"]) if run["max_wave"] >= 5000),
        None,
    )
    row["first_w4000_run_index"] = first_index
    row["success_run_index"] = success_index
    row["w4000_to_w5000_runs"] = (
        None if first_index is None or success_index is None else success_index - first_index
    )
    row["w4000_same_run_w5000"] = (
        first_index is not None and success_index == first_index
    )


def checkpoint_items(rows: list[dict], wave: int) -> list[dict]:
    return [row["checkpoints"][str(wave)] for row in rows if str(wave) in row["checkpoints"]]


def subgroup(rows: list[dict], acquired: bool) -> dict:
    chosen = [row for row in rows if row["infinite_barrage_acquired"] is acquired]
    return {
        "samples": len(chosen),
        "successes": sum(row["success"] for row in chosen),
        "success_rate": (
            sum(row["success"] for row in chosen) / len(chosen) if chosen else None
        ),
        "same_run_w5000_rate": (
            sum(row["w4000_same_run_w5000"] for row in chosen) / len(chosen)
            if chosen else None
        ),
    }


def summarize(rows: list[dict]) -> dict:
    successes = [row for row in rows if row["success"]]
    reached_w4000 = [row for row in rows if row["first_w4000_run_index"] is not None]
    result = {
        "samples": len(rows),
        "checkpoints": {},
        "w4000_to_w5000_runs": diag.dist([
            row["w4000_to_w5000_runs"] for row in successes
            if row["w4000_to_w5000_runs"] is not None
        ]),
        "w4000_same_run_w5000_rate": (
            sum(row["w4000_same_run_w5000"] for row in reached_w4000)
            / len(reached_w4000) if reached_w4000 else None
        ),
        "w5000_margin": diag.dist([
            row["w5000_margin"] for row in successes if row["w5000_margin"] is not None
        ]),
        "death_wave_4500_plus": dict(sorted(collections.Counter(
            str(run["failure_wave"])
            for row in rows for run in row["run_rows"]
            if run["failure_wave"] is not None and run["failure_wave"] >= 4500
        ).items(), key=lambda item: int(item[0]))),
        "boost_levels": {
            key: diag.dist([row["unlimited_boost_levels"][key] for row in rows])
            for key in sim.UNLIMITED_BOOST_NODES
        },
        "weapon_spent": diag.dist([row["unlimited_boost_weapon_spent"] for row in rows]),
        "relic_spent": diag.dist([row["unlimited_boost_relic_spent"] for row in rows]),
        "barrage_acquired": subgroup(rows, True),
        "barrage_not_acquired": subgroup(rows, False),
        "rows": rows,
    }
    for wave in CHECKPOINTS:
        states = checkpoint_items(rows, wave)
        result["checkpoints"][str(wave)] = {
            "reached": len(states),
            "reach_rate": len(states) / len(rows) if rows else None,
            "margin": diag.dist([float(item["margin_power"]) for item in states]),
            "boost_power": diag.dist([float(item.get("boost_power", 0.0)) for item in states]),
            "core_power": diag.dist([float(item.get("core_power", 0.0)) for item in states]),
            "barrage_power": diag.dist([float(item.get("barrage_power", 0.0)) for item in states]),
            "attack_speed": diag.dist([float(item.get("attack_speed", 0.0)) for item in states]),
            "attack_capacity": diag.dist([float(item.get("attack_capacity", 0.0)) for item in states]),
            "suppressed_node_direct_power": diag.dist([
                float(item.get("suppressed_node_direct_power", 0.0)) for item in states
            ]),
            "suppressed_node_attack_speed": diag.dist([
                float(item.get("suppressed_node_attack_speed", 0.0)) for item in states
            ]),
            "suppressed_node_attack_capacity": diag.dist([
                float(item.get("suppressed_node_attack_capacity", 0.0)) for item in states
            ]),
            "suppressed_node_barrage_power": diag.dist([
                float(item.get("suppressed_node_barrage_power", 0.0)) for item in states
            ]),
            "suppressed_node_core_power": diag.dist([
                float(item.get("suppressed_node_core_power", 0.0)) for item in states
            ]),
        }
    return result


def paired_as_analysis(grouped: dict[str, list[dict]]) -> dict:
    full_by_trial = {row["trial"]: row for row in grouped["A_full_boost"]}
    off_by_trial = {row["trial"]: row for row in grouped["D_attack_speed_off"]}
    shared = sorted(set(full_by_trial) & set(off_by_trial))
    acquired = [trial for trial in shared if full_by_trial[trial]["infinite_barrage_acquired"]]

    def differences(trials: list[int], field: str, wave: int = 5000) -> dict:
        values = []
        for trial in trials:
            full_state = full_by_trial[trial]["checkpoints"].get(str(wave))
            off_state = off_by_trial[trial]["checkpoints"].get(str(wave))
            if full_state is not None and off_state is not None:
                values.append(float(full_state.get(field, 0.0)) - float(off_state.get(field, 0.0)))
        return diag.dist(values)

    return {
        "paired_trials": len(shared),
        "full_barrage_acquired_trials": acquired,
        "w5000_full_minus_as_off": {
            "samples_at_w5000": sum(
                str(5000) in full_by_trial[t]["checkpoints"]
                and str(5000) in off_by_trial[t]["checkpoints"] for t in shared
            ),
            "attack_speed": differences(shared, "attack_speed"),
            "attack_capacity": differences(shared, "attack_capacity"),
            "infinite_barrage_power": differences(shared, "barrage_power"),
            "core_power": differences(shared, "core_power"),
            "margin": differences(shared, "margin_power"),
        },
        "barrage_acquired_matched_w5000": {
            "samples_at_w5000": sum(
                str(5000) in full_by_trial[t]["checkpoints"]
                and str(5000) in off_by_trial[t]["checkpoints"] for t in acquired
            ),
            "attack_speed": differences(acquired, "attack_speed"),
            "attack_capacity": differences(acquired, "attack_capacity"),
            "infinite_barrage_power": differences(acquired, "barrage_power"),
            "core_power": differences(acquired, "core_power"),
            "margin": differences(acquired, "margin_power"),
        },
    }


def markdown(payload: dict) -> str:
    lines = [
        "# w5000_v1 Unlimited Boost node causal audit", "",
        "Diagnostic only. Finale ON, Core flat 15%, late DP 10%, Infinite Barrage 37.5%, Boss Devourer base-heavy B.", "",
        "## Reach", "",
        "| Profile | W4500 | W4600 | W4700 | W4800 | W4900 | W5000 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label, item in payload["profiles"].items():
        lines.append(
            f"| {label} | " + " | ".join(
                f"{item['checkpoints'][str(wave)]['reach_rate']:.0%}"
                for wave in CHECKPOINTS[1:]
            ) + " |"
        )
    lines += [
        "", "## Runs, power, and margin", "",
        "| Profile | W4000→5000 Runs P25/P50/P75 | Same-run W5000 | Boost Power W5000 P50 | W5000 Margin P50 |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, item in payload["profiles"].items():
        runs = item["w4000_to_w5000_runs"]
        lines.append(
            f"| {label} | {fmt(runs['p25'],1)}/{fmt(runs['p50'],1)}/{fmt(runs['p75'],1)}"
            f" | {fmt(100 * item['w4000_same_run_w5000_rate'],0) if item['w4000_same_run_w5000_rate'] is not None else '—'}%"
            f" | {fmt(item['checkpoints']['5000']['boost_power']['p50'])}"
            f" | {fmt(item['w5000_margin']['p50'])} |"
        )
    lines += ["", "## Direct node effect on the same state", "", "| Profile | W4500 Power | W5000 Power | W5000 Barrage interaction | W5000 Core interaction |", "|---|---:|---:|---:|---:|"]
    for label, item in payload["profiles"].items():
        c45 = item["checkpoints"]["4500"]
        c50 = item["checkpoints"]["5000"]
        lines.append(
            f"| {label} | {fmt(c45['suppressed_node_direct_power']['p50'])}"
            f" | {fmt(c50['suppressed_node_direct_power']['p50'])}"
            f" | {fmt(c50['suppressed_node_barrage_power']['p50'])}"
            f" | {fmt(c50['suppressed_node_core_power']['p50'])} |"
        )
    lines += ["", "## Infinite Barrage split", "", "| Profile | Group | N | W5000 | Same-run W5000 |", "|---|---|---:|---:|---:|"]
    for label, item in payload["profiles"].items():
        for key, title in (("barrage_acquired", "acquired"), ("barrage_not_acquired", "not acquired")):
            group = item[key]
            lines.append(
                f"| {label} | {title} | {group['samples']}"
                f" | {fmt(100 * group['success_rate'],0) if group['success_rate'] is not None else '—'}%"
                f" | {fmt(100 * group['same_run_w5000_rate'],0) if group['same_run_w5000_rate'] is not None else '—'}% |"
            )
    lines += ["", "## Attack Speed matched effect at W5000", "", "| Group | N | ΔAS | Δattack capacity | ΔBarrage Power | ΔCore Power | ΔMargin |", "|---|---:|---:|---:|---:|---:|---:|"]
    all_as = payload["attack_speed_matched"]["w5000_full_minus_as_off"]
    barr_as = payload["attack_speed_matched"]["barrage_acquired_matched_w5000"]
    lines.append(
        f"| all paired successes | {all_as['samples_at_w5000']} | {fmt(all_as['attack_speed']['p50'])}"
        f" | {fmt(all_as['attack_capacity']['p50'],0)} | {fmt(all_as['infinite_barrage_power']['p50'])}"
        f" | {fmt(all_as['core_power']['p50'])} | {fmt(all_as['margin']['p50'])} |"
    )
    lines.append(
        f"| Full-Barrage acquired | {barr_as['samples_at_w5000']} | {fmt(barr_as['attack_speed']['p50'])}"
        f" | {fmt(barr_as['attack_capacity']['p50'],0)} | {fmt(barr_as['infinite_barrage_power']['p50'])}"
        f" | {fmt(barr_as['core_power']['p50'])} | {fmt(barr_as['margin']['p50'])} |"
    )
    lines += ["", "## W4500+ deaths", ""]
    for label, item in payload["profiles"].items():
        lines.append(f"- {label}: `{json.dumps(item['death_wave_4500_plus'])}`")
    lines += [
        "", "## Validation", "",
        f"- paired checkpoint states: {payload['state_count']}",
        "- Suppressed nodes remain purchasable and consume their normal material cost; only combat effect lookup is zeroed.",
        f"- errors/nonfinite/overflow: {payload['error_count']}/{payload['nonfinite_count']}/{payload['overflow_count']}",
        "- No Finale, Boost, Core, DP, card, enemy, Weapon, or Relic balance value was changed.", "",
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
        default=Path("output/w5000_v1_boost_node_suppression_10_states"),
    )
    args = parser.parse_args()
    with gzip.open(args.states, "rb") as handle:
        captures = pickle.load(handle)
    if len(captures) != 10:
        raise ValueError(f"expected 10 W2500 states, found {len(captures)}")

    grouped = {label: [] for label in PROFILES}
    errors = []
    for label, suppressed in PROFILES.items():
        for capture in captures.values():
            try:
                row = integrated.replay_one(
                    capture,
                    label,
                    DP_SCALE,
                    CORE_SCALE,
                    unlimited_boost_config=sim.UnlimitedBoostConfig(
                        enabled=True, suppressed_nodes=suppressed
                    ),
                    finale_config=sim.FinaleConfig(enabled=True),
                    diagnostic_checkpoints=CHECKPOINTS,
                )
                augment_w4000(row)
                grouped[label].append(row)
            except Exception as exc:
                errors.append({
                    "profile": label,
                    "trial": capture["trial"],
                    "type": type(exc).__name__,
                    "message": str(exc),
                })

    profiles = {label: summarize(rows) for label, rows in grouped.items()}
    nonfinite = sum(len(row["nonfinite"]) for rows in grouped.values() for row in rows)
    payload = {
        "state_count": len(captures),
        "trial_ids": sorted(captures),
        "profiles": profiles,
        "attack_speed_matched": paired_as_analysis(grouped),
        "error_count": len(errors),
        "nonfinite_count": nonfinite,
        "overflow_count": sum(error["type"] == "OverflowError" for error in errors),
        "errors": errors,
        "formal_changed": False,
        "balance_adopted": False,
    }
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = output / "boost_node_suppression_report.md"
    summary = output / "boost_node_suppression_summary.json"
    report.write_text(markdown(payload), encoding="utf-8")
    summary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "report": str(report),
        "json": str(summary),
        "states": len(captures),
        "errors": len(errors),
        "nonfinite": nonfinite,
        "overflow": payload["overflow_count"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
