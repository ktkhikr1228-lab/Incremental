#!/usr/bin/env python3
"""Small paired direction check for Unlimited Boost v0.2 candidate."""

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


def v02_config() -> sim.UnlimitedBoostConfig:
    """One deliberately simple direction candidate, not an adopted balance."""
    return sim.UnlimitedBoostConfig(
        enabled=True,
        version="v0.2-candidate",
        node_order=sim.UNLIMITED_BOOST_V02_NODES,
        base_atk_per_level=0.0,
        weapon_atk_per_level=0.0,
        attack_speed_per_level=0.0,
        crit_multiplier_per_level=0.0,
        all_damage_per_level=0.0,
        boss_damage_per_level=0.0,
        base_atk_power_per_level=0.35,
        weapon_atk_power_per_level=0.35,
        crit_multiplier_log10_per_level=0.50,
        all_damage_power_per_level=1.25,
        boss_damage_power_per_level=1.25,
        finale_mastery_power_per_level=1.25,
    )


PROFILES = {
    "A_boost_off": sim.UnlimitedBoostConfig(enabled=False),
    "B_boost_v01": sim.UnlimitedBoostConfig(enabled=True),
    "C_boost_v02": v02_config(),
}


def fmt(value, digits=2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def augment_w4000(row: dict) -> None:
    first_index = next(
        (i for i, run in enumerate(row["run_rows"]) if run["max_wave"] >= 4000), None
    )
    success_index = next(
        (i for i, run in enumerate(row["run_rows"]) if run["max_wave"] >= 5000), None
    )
    row["w4000_to_w5000_runs"] = (
        None if first_index is None or success_index is None else success_index - first_index
    )
    row["w4000_same_run_w5000"] = (
        first_index is not None and success_index == first_index
    )


def subgroup(rows: list[dict], acquired: bool) -> dict:
    selected = [row for row in rows if row["infinite_barrage_acquired"] is acquired]
    return {
        "samples": len(selected),
        "successes": sum(row["success"] for row in selected),
        "success_rate": (
            sum(row["success"] for row in selected) / len(selected) if selected else None
        ),
    }


def summarize(rows: list[dict], boost: sim.UnlimitedBoostConfig) -> dict:
    successes = [row for row in rows if row["success"]]
    reached_w4000 = [row for row in rows if "4000" in row["checkpoints"]]
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
            key: diag.dist([row["unlimited_boost_levels"].get(key, 0) for row in rows])
            for key in boost.node_order
        },
        "weapon_spent": diag.dist([row["unlimited_boost_weapon_spent"] for row in rows]),
        "relic_spent": diag.dist([row["unlimited_boost_relic_spent"] for row in rows]),
        "barrage_acquired": subgroup(rows, True),
        "barrage_not_acquired": subgroup(rows, False),
        "rows": rows,
    }
    for wave in CHECKPOINTS:
        states = [
            row["checkpoints"][str(wave)]
            for row in rows if str(wave) in row["checkpoints"]
        ]
        node_values = {
            key: diag.dist([
                float(state.get("boost_node_power", {}).get(key, 0.0))
                for state in states
            ])
            for key in boost.node_order
        }
        median_sum = sum(
            value["p50"] or 0.0 for value in node_values.values()
        )
        max_node = max(
            ((key, value["p50"] or 0.0) for key, value in node_values.items()),
            key=lambda pair: pair[1],
            default=(None, 0.0),
        )
        result["checkpoints"][str(wave)] = {
            "reached": len(states),
            "reach_rate": len(states) / len(rows) if rows else None,
            "margin": diag.dist([float(state["margin_power"]) for state in states]),
            "boost_power": diag.dist([float(state.get("boost_power", 0.0)) for state in states]),
            "node_power": node_values,
            "node_median_sum": median_sum,
            "largest_node": max_node[0],
            "largest_node_share": max_node[1] / median_sum if median_sum > 0 else None,
        }
    return result


def markdown(payload: dict) -> str:
    lines = [
        "# w5000_v1 Unlimited Boost v0.2 direction check", "",
        "Experimental only. Finale v0.1 ON; Core flat 15%, late DP 10%, Infinite Barrage 37.5%, Boss Devourer base-heavy B.", "",
        "## Reach", "",
        "| Profile | W4500 | W4600 | W4700 | W4800 | W4900 | W5000 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label, item in payload["profiles"].items():
        lines.append(
            f"| {label} | " + " | ".join(
                f"{item['checkpoints'][str(w)]['reach_rate']:.0%}" for w in CHECKPOINTS[1:]
            ) + " |"
        )
    lines += [
        "", "## Progress and total contribution", "",
        "| Profile | W4000→5000 Runs P25/P50/P75 | Same-run W5000 | Boost Power W5000 P50 | Margin P50 | Weapon Pt | Relic Dust |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label, item in payload["profiles"].items():
        runs = item["w4000_to_w5000_runs"]
        same = item["w4000_same_run_w5000_rate"]
        lines.append(
            f"| {label} | {fmt(runs['p25'],1)}/{fmt(runs['p50'],1)}/{fmt(runs['p75'],1)}"
            f" | {fmt(100 * same,0) if same is not None else '—'}%"
            f" | {fmt(item['checkpoints']['5000']['boost_power']['p50'])}"
            f" | {fmt(item['w5000_margin']['p50'])}"
            f" | {fmt(item['weapon_spent']['p50'],0)} | {fmt(item['relic_spent']['p50'],0)} |"
        )
    lines += ["", "## W5000 node marginal Power", "", "| Profile | Node | Power P50 |", "|---|---|---:|"]
    for label, item in payload["profiles"].items():
        for key, value in item["checkpoints"]["5000"]["node_power"].items():
            lines.append(f"| {label} | {key} | {fmt(value['p50'])} |")
        cp = item["checkpoints"]["5000"]
        lines.append(
            f"| {label} | **largest share** | **{fmt(100 * cp['largest_node_share'],1) if cp['largest_node_share'] is not None else '—'}% ({cp['largest_node'] or '—'})** |"
        )
    lines += ["", "## Infinite Barrage split", "", "| Profile | Group | N | W5000 |", "|---|---|---:|---:|"]
    for label, item in payload["profiles"].items():
        for key, title in (("barrage_acquired", "acquired"), ("barrage_not_acquired", "not acquired")):
            group = item[key]
            lines.append(
                f"| {label} | {title} | {group['samples']}"
                f" | {fmt(100 * group['success_rate'],0) if group['success_rate'] is not None else '—'}% |"
            )
    lines += ["", "## W4500+ deaths", ""]
    for label, item in payload["profiles"].items():
        lines.append(f"- {label}: `{json.dumps(item['death_wave_4500_plus'])}`")
    lines += [
        "", "## Candidate values", "",
        "- Base ATK Power +0.35 / effective Lv (before Core)",
        "- Weapon ATK Power +0.35 / effective Lv (before Core; equipped only)",
        "- Crit Multiplier x10^0.50 / effective Lv",
        "- All Damage +1.25 Power / effective Lv",
        "- Boss Damage +1.25 Power / effective Lv",
        "- Finale Mastery +1.25 Power / effective Lv at W4500+ only",
        "- Cost curve and Lv5 softcap are unchanged from v0.1; Finale Mastery replaces AS at the same 90 Weapon Pt base cost.",
        "", "## Validation", "",
        f"- paired states: {payload['state_count']}",
        f"- errors/nonfinite/overflow: {payload['error_count']}/{payload['nonfinite_count']}/{payload['overflow_count']}",
        "- No formal adoption and no fine optimization.", "",
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
        default=Path("output/w5000_v1_unlimited_boost_v02_10_states"),
    )
    parser.add_argument("--limit-states", type=int, default=10)
    args = parser.parse_args()
    with gzip.open(args.states, "rb") as handle:
        all_captures = pickle.load(handle)
    captures = dict(list(sorted(all_captures.items()))[: args.limit_states])

    grouped = {label: [] for label in PROFILES}
    errors = []
    for label, boost in PROFILES.items():
        for capture in captures.values():
            try:
                row = integrated.replay_one(
                    capture,
                    label,
                    DP_SCALE,
                    CORE_SCALE,
                    unlimited_boost_config=boost,
                    finale_config=sim.FinaleConfig(enabled=True),
                    diagnostic_checkpoints=CHECKPOINTS,
                )
                augment_w4000(row)
                grouped[label].append(row)
            except Exception as exc:
                errors.append({
                    "profile": label, "trial": capture["trial"],
                    "type": type(exc).__name__, "message": str(exc),
                })

    profiles = {
        label: summarize(grouped[label], boost)
        for label, boost in PROFILES.items()
    }
    nonfinite = sum(len(row["nonfinite"]) for rows in grouped.values() for row in rows)
    payload = {
        "state_count": len(captures),
        "trial_ids": sorted(captures),
        "profiles": profiles,
        "error_count": len(errors),
        "nonfinite_count": nonfinite,
        "overflow_count": sum(error["type"] == "OverflowError" for error in errors),
        "errors": errors,
        "formal_changed": False,
        "balance_adopted": False,
    }
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = output / "unlimited_boost_v02_report.md"
    summary = output / "unlimited_boost_v02_summary.json"
    report.write_text(markdown(payload), encoding="utf-8")
    summary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "report": str(report), "json": str(summary), "states": len(captures),
        "errors": len(errors), "nonfinite": nonfinite,
        "overflow": payload["overflow_count"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
