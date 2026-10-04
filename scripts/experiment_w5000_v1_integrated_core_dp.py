#!/usr/bin/env python3
"""Paired W2500+ integration comparison for late DP and medium Core."""

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
import replay_w5000_v1_micro_core_profiles as core
import simulate_first_prestige_v1 as sim


CHECKPOINTS = tuple(range(2750, 5001, 250))
BARRAGE_STRENGTH = 0.375
PROFILES = {
    "A_dp10_core_off": (0.10, 0.0),
    "B_dp10_core_medium20": (0.10, 0.20),
    "C_dp25_core_off": (0.25, 0.0),
    "D_dp25_core_medium20": (0.25, 0.20),
}


def make_config(
    capture: dict,
    dp_scale: float,
    core_scale: float,
    core_stage_scales: tuple[float, float, float] | None = None,
) -> sim.SimConfig:
    baseline = tuple(
        (key, int(capture["permanent"].dp_v01_levels[key]))
        for key in sim.DP_V01_ITEMS
    )
    base = dataclasses.replace(
        core.base_config(140),
        diagnostic_checkpoints=(2500,) + CHECKPOINTS,
        diagnostic_dp_baseline_levels=baseline,
        diagnostic_late_dp_effect_scale=dp_scale,
        diagnostic_infinite_barrage_strength=BARRAGE_STRENGTH,
    )
    if core_stage_scales is None:
        return core.profile_config(base, core_scale)
    if len(core_stage_scales) != len(core.WEAK_STAGES):
        raise ValueError("core_stage_scales must match the existing three Core stages")
    return dataclasses.replace(
        base,
        exponential_core_guaranteed_wave=2500,
        exponential_core_growth_stages=tuple(
            (start, end, increment * scale)
            for (start, end, increment), scale in zip(core.WEAK_STAGES, core_stage_scales)
        ),
    )


def snapshot_without_core(
    run: sim.RunState,
    permanent: sim.PermanentState,
    boss: bool,
    config: sim.SimConfig,
) -> sim.Snapshot:
    no_core_run = copy.deepcopy(run)
    no_core_run.counts.pop("exponential_core", None)
    no_core_config = dataclasses.replace(
        config,
        exponential_core_guaranteed_wave=None,
        exponential_core_growth_stages=(),
    )
    return sim.compute_snapshot(no_core_run, permanent, boss, no_core_config)


def direct_contributions(
    run: sim.RunState,
    permanent: sim.PermanentState,
    boss: bool,
    config: sim.SimConfig,
) -> tuple[sim.Snapshot, float, float, float, float]:
    actual = sim.compute_snapshot(run, permanent, boss, config)
    zero_dp = sim.compute_snapshot(
        run,
        permanent,
        boss,
        dataclasses.replace(config, diagnostic_late_dp_effect_scale=0.0),
    )
    no_core = snapshot_without_core(run, permanent, boss, config)
    no_boost = sim.compute_snapshot(
        run,
        permanent,
        boss,
        dataclasses.replace(
            config,
            unlimited_boost=dataclasses.replace(config.unlimited_boost, enabled=False),
        ),
    )
    no_barrage = sim.compute_snapshot(
        run,
        permanent,
        boss,
        dataclasses.replace(
            config,
            diagnostic_suppressed_card_keys=(
                config.diagnostic_suppressed_card_keys | frozenset({"infinite_barrage"})
            ),
        ),
    )
    return (
        actual,
        actual.log_dps - zero_dp.log_dps,
        actual.log_dps - no_core.log_dps,
        actual.log_dps - no_boost.log_dps,
        actual.log_dps - no_barrage.log_dps,
    )


def terminal_power(state: dict, wave: int) -> float:
    return float(state["boss_power"] if wave % 10 == 0 else state["normal_power"])


def replay_one(
    capture: dict,
    label: str,
    dp_scale: float,
    core_scale: float,
    core_stage_scales: tuple[float, float, float] | None = None,
    unlimited_boost_config: sim.UnlimitedBoostConfig | None = None,
    finale_config: sim.FinaleConfig | None = None,
    diagnostic_checkpoints: tuple[int, ...] | None = None,
    barrage_strength: float | None = None,
    barrage_power_cap: float | None = None,
    barrage_mode: str | None = None,
    barrage_v2_growth_power_cap: float | None = None,
) -> dict:
    config = make_config(capture, dp_scale, core_scale, core_stage_scales)
    if unlimited_boost_config is not None:
        config = dataclasses.replace(config, unlimited_boost=unlimited_boost_config)
    if finale_config is not None:
        config = dataclasses.replace(config, finale=finale_config)
    if diagnostic_checkpoints is not None:
        config = dataclasses.replace(
            config,
            diagnostic_checkpoints=tuple(sorted(set((2500,) + diagnostic_checkpoints))),
        )
    if barrage_strength is not None or barrage_power_cap is not None:
        config = dataclasses.replace(
            config,
            diagnostic_infinite_barrage_strength=(
                config.diagnostic_infinite_barrage_strength
                if barrage_strength is None else barrage_strength
            ),
            diagnostic_infinite_barrage_power_cap=barrage_power_cap,
        )
    if barrage_mode is not None:
        config = dataclasses.replace(
            config,
            diagnostic_infinite_barrage_mode=barrage_mode,
            diagnostic_infinite_barrage_v2_growth_power_cap=(
                barrage_v2_growth_power_cap
            ),
        )
    recorded_checkpoints = set(config.diagnostic_checkpoints)
    run = copy.deepcopy(capture["run"])
    permanent = copy.deepcopy(capture["permanent"])
    streams = core.restore_streams(capture)
    core_enabled = bool(core_scale or core_stage_scales)
    if core_enabled:
        run.counts["exponential_core"] = 1
        run.effect_version += 1

    baseline_levels = dict(config.diagnostic_dp_baseline_levels)
    initial_interaction = permanent.interaction_seconds
    remaining_runs = config.max_attempts - int(capture["attempt"]) + 1
    checkpoints: dict[str, dict] = {}
    first_run_checkpoints: dict[str, dict] = {}
    run_rows = []
    combat_seconds = 0.0
    success = False

    for run_index in range(remaining_runs):
        interaction_before_run = permanent.interaction_seconds
        start: dict[str, float] = {}
        end: dict[str, float] = {}
        diagnostics: dict[int, dict] = {}

        def capture_start(live_run, live_permanent, live_streams):
            snap, late_dp_power, core_power, boost_power, barrage_power = direct_contributions(
                live_run, live_permanent, False, config
            )
            start.update({
                "power": snap.log_dps,
                "attack_speed": snap.attack_speed,
                "late_dp_power": late_dp_power,
                "core_power": core_power,
                "boost_power": boost_power,
                "barrage_power": barrage_power,
            })

        def capture_checkpoint(wave, live_run, live_permanent, live_streams):
            snap, late_dp_power, core_power, boost_power, barrage_power = direct_contributions(
                live_run, live_permanent, wave % 10 == 0, config
            )
            restored_config = dataclasses.replace(
                config,
                unlimited_boost=dataclasses.replace(
                    config.unlimited_boost, suppressed_nodes=()
                ),
            )
            restored, _, restored_core, _, restored_barrage = direct_contributions(
                live_run, live_permanent, wave % 10 == 0, restored_config
            )
            limit = sim.enemy_time_limit(wave, sim.n(live_run.counts, "glass_cannon"))
            node_power = {}
            for node in config.unlimited_boost.node_order:
                node_off_config = dataclasses.replace(
                    config,
                    unlimited_boost=dataclasses.replace(
                        config.unlimited_boost,
                        suppressed_nodes=tuple(sorted(
                            set(config.unlimited_boost.suppressed_nodes) | {node}
                        )),
                    ),
                )
                node_off = sim.compute_snapshot(
                    live_run, live_permanent, wave % 10 == 0, node_off_config
                )
                node_power[node] = snap.log_dps - node_off.log_dps
            diagnostics[wave] = {
                "late_dp_power": late_dp_power,
                "core_power": core_power,
                "boost_power": boost_power,
                "barrage_power": barrage_power,
                "attack_speed": snap.attack_speed,
                "attack_capacity": math.floor(
                    snap.attack_speed * limit + 1e-12
                ),
                "suppressed_node_direct_power": restored.log_dps - snap.log_dps,
                "suppressed_node_attack_speed": restored.attack_speed - snap.attack_speed,
                "suppressed_node_attack_capacity": (
                    math.floor(restored.attack_speed * limit + 1e-12)
                    - math.floor(snap.attack_speed * limit + 1e-12)
                ),
                "suppressed_node_barrage_power": restored_barrage - barrage_power,
                "suppressed_node_core_power": restored_core - core_power,
                "boost_node_power": node_power,
                "core_exponent": sim.exponential_core_exponent(live_run, config),
                "infinite_barrage_owned": live_run.counts.get("infinite_barrage", 0) > 0,
                "finale_added_power": sim.finale_added_power(wave, config),
            }

        def capture_end(live_run, live_permanent, live_streams, failure_wave):
            snap, late_dp_power, core_power, boost_power, barrage_power = direct_contributions(
                live_run, live_permanent, False, config
            )
            end.update({
                "power": snap.log_dps,
                "attack_speed": snap.attack_speed,
                "late_dp_power": late_dp_power,
                "core_power": core_power,
                "boost_power": boost_power,
                "barrage_power": barrage_power,
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
            checkpoint_capture=capture_checkpoint,
            run_end_capture=capture_end,
        )
        combat_seconds += result.combat_seconds
        run_game_seconds = (
            result.combat_seconds + permanent.interaction_seconds - interaction_before_run
        )
        for wave, state in result.checkpoint_states.items():
            if wave == 2500 or wave not in recorded_checkpoints or str(wave) in checkpoints:
                continue
            extra = diagnostics.get(wave, {})
            checkpoints[str(wave)] = {**copy.deepcopy(state), **extra}

        levels_gained = {
            key: max(0, int(permanent.dp_v01_levels[key]) - baseline_levels[key])
            for key in sim.DP_V01_ITEMS
        }
        terminal_wave = int(result.failure_wave or result.reached)
        state = result.end_state
        run_rows.append({
            "run_index": run_index + 1,
            "max_wave": int(result.reached),
            "failure_wave": result.failure_wave,
            "start_power": float(start["power"]),
            "end_power": float(end["power"]),
            "start_attack_speed": float(start["attack_speed"]),
            "end_attack_speed": float(end["attack_speed"]),
            "start_late_dp_power": float(start["late_dp_power"]),
            "end_late_dp_power": float(end["late_dp_power"]),
            "start_core_power": float(start["core_power"]),
            "end_core_power": float(end["core_power"]),
            "start_boost_power": float(start["boost_power"]),
            "end_boost_power": float(end["boost_power"]),
            "start_barrage_power": float(start["barrage_power"]),
            "end_barrage_power": float(end["barrage_power"]),
            "late_dp_levels": levels_gained,
            "late_dp_total_levels": sum(levels_gained.values()),
            "infinite_barrage_owned": state["cards"].get("infinite_barrage", 0) > 0,
            "infinite_barrage_first_wave": state["card_first_acquired_wave"].get(
                "infinite_barrage"
            ),
            "terminal_margin": terminal_power(state, terminal_wave)
            - sim.configured_enemy_power(terminal_wave, config),
            "game_seconds": run_game_seconds,
            "reach_w4000_seconds": (
                sum(result.reach_elapsed[4000]) if 4000 in result.reach_elapsed else None
            ),
            "reach_w4500_seconds": (
                sum(result.reach_elapsed[4500]) if 4500 in result.reach_elapsed else None
            ),
        })
        if run_index == 0:
            first_run_checkpoints = copy.deepcopy(checkpoints)
        if result.reached >= 5000:
            success = True
            break
        sim.store_memory_candidates(result, permanent)
        sim.award_and_spend_dp_v01(permanent, result.reached, config)
        sim.purchase_game_speed(permanent, config)
        sim.convert_surplus_material(permanent, config)
        sim.forge_relics(streams.relic, permanent, config)
        sim.purchase_unlimited_boost(permanent, config)
        run = None

    waves = [item["max_wave"] for item in run_rows]
    first = run_rows[0]
    successes = [item for item in run_rows if item["max_wave"] >= 5000]
    game_seconds = combat_seconds + permanent.interaction_seconds - initial_interaction
    nonfinite = []
    for item in run_rows:
        for key in (
            "start_power", "end_power", "start_late_dp_power", "end_late_dp_power",
            "start_core_power", "end_core_power", "terminal_margin",
            "start_boost_power", "end_boost_power",
            "start_barrage_power", "end_barrage_power",
            "start_attack_speed", "end_attack_speed",
        ):
            if not math.isfinite(item[key]):
                nonfinite.append({"run": item["run_index"], "key": key, "value": item[key]})
    return {
        "trial": int(capture["trial"]),
        "profile": label,
        "success": success,
        "checkpoints": checkpoints,
        "first_run_checkpoints": first_run_checkpoints,
        "first_run_max_wave": first["max_wave"],
        "first_run_stop_wave": first["failure_wave"],
        "first_run_w5000": first["max_wave"] >= 5000,
        "best_wave": max(waves),
        "additional_runs": max(0, len(run_rows) - 1),
        "game_hours_from_w2500": game_seconds / 3600.0,
        "w5000_margin": (
            float(checkpoints["5000"]["margin_power"])
            if success and "5000" in checkpoints else None
        ),
        "terminal_margin": run_rows[-1]["terminal_margin"],
        "best_minus_recent10_median": max(waves) - statistics.median(waves[-10:]),
        "final_late_dp_power": run_rows[-1]["end_late_dp_power"],
        "final_core_power": run_rows[-1]["end_core_power"],
        "final_boost_power": run_rows[-1]["end_boost_power"],
        "final_barrage_power": run_rows[-1]["end_barrage_power"],
        "unlimited_boost_levels": permanent.unlimited_boost_levels.copy(),
        "unlimited_boost_weapon_spent": permanent.unlimited_boost_weapon_spent,
        "unlimited_boost_relic_spent": permanent.unlimited_boost_relic_spent,
        "infinite_barrage_acquired": any(
            item["infinite_barrage_owned"] for item in run_rows
        ),
        "run_rows": run_rows,
        "nonfinite": nonfinite,
    }


def summarize_rows(rows: list[dict], include_rows: bool = True) -> dict:
    successes = [row for row in rows if row["success"]]
    result = {
        "samples": len(rows),
        "successes": len(successes),
        "success_rate": len(successes) / len(rows) if rows else None,
        "checkpoints": {},
        "first_run_checkpoints": {},
        "first_run_max_wave": diag.dist([row["first_run_max_wave"] for row in rows]),
        "first_run_w5000_rate": (
            sum(row["first_run_w5000"] for row in rows) / len(rows) if rows else None
        ),
        "first_run_stop_wave": dict(sorted(collections.Counter(
            str(row["first_run_stop_wave"] or 5000) for row in rows
        ).items(), key=lambda pair: int(pair[0]))),
        "best_wave": diag.dist([row["best_wave"] for row in rows]),
        "additional_runs_to_w5000": diag.dist([
            row["additional_runs"] for row in successes
        ]),
        "game_hours_to_w5000": diag.dist([
            row["game_hours_from_w2500"] for row in successes
        ]),
        "w5000_margin": diag.dist([
            row["w5000_margin"] for row in successes if row["w5000_margin"] is not None
        ]),
        "terminal_margin": diag.dist([row["terminal_margin"] for row in rows]),
        "best_minus_recent10_median": diag.dist([
            row["best_minus_recent10_median"] for row in rows
        ]),
        "late_dp_power": diag.dist([row["final_late_dp_power"] for row in rows]),
        "core_power": diag.dist([row["final_core_power"] for row in rows]),
        "boost_power": diag.dist([row["final_boost_power"] for row in rows]),
        "boost_levels": {
            key: diag.dist([row["unlimited_boost_levels"][key] for row in rows])
            for key in sim.UNLIMITED_BOOST_NODES
        },
        "boost_weapon_spent": diag.dist([
            row["unlimited_boost_weapon_spent"] for row in rows
        ]),
        "boost_relic_spent": diag.dist([
            row["unlimited_boost_relic_spent"] for row in rows
        ]),
    }
    for wave in CHECKPOINTS:
        states = [row["checkpoints"][str(wave)] for row in rows if str(wave) in row["checkpoints"]]
        result["checkpoints"][str(wave)] = {
            "reached": len(states),
            "reach_rate": len(states) / len(rows) if rows else None,
            "margin": diag.dist([float(item["margin_power"]) for item in states]),
            "core_exponent": diag.dist([float(item.get("core_exponent", 1.0)) for item in states]),
            "late_dp_power": diag.dist([float(item.get("late_dp_power", 0.0)) for item in states]),
            "core_power": diag.dist([float(item.get("core_power", 0.0)) for item in states]),
            "boost_power": diag.dist([float(item.get("boost_power", 0.0)) for item in states]),
            "finale_added_power": diag.dist([
                float(item.get("finale_added_power", 0.0)) for item in states
            ]),
        }
        first_states = [
            row["first_run_checkpoints"][str(wave)]
            for row in rows if str(wave) in row["first_run_checkpoints"]
        ]
        result["first_run_checkpoints"][str(wave)] = {
            "reached": len(first_states),
            "reach_rate": len(first_states) / len(rows) if rows else None,
            "margin": diag.dist([float(item["margin_power"]) for item in first_states]),
            "core_exponent": diag.dist([
                float(item.get("core_exponent", 1.0)) for item in first_states
            ]),
            "late_dp_power": diag.dist([
                float(item.get("late_dp_power", 0.0)) for item in first_states
            ]),
            "core_power": diag.dist([
                float(item.get("core_power", 0.0)) for item in first_states
            ]),
            "boost_power": diag.dist([
                float(item.get("boost_power", 0.0)) for item in first_states
            ]),
            "finale_added_power": diag.dist([
                float(item.get("finale_added_power", 0.0)) for item in first_states
            ]),
        }
    if include_rows:
        result["rows"] = rows
    return result


def subgroup(rows: list[dict], acquired: bool) -> dict:
    return summarize_rows(
        [row for row in rows if row["infinite_barrage_acquired"] is acquired],
        include_rows=False,
    )


def fmt(value, digits=2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def markdown(payload: dict) -> str:
    lines = [
        "# w5000_v1 W2500+ integrated Core / late-DP comparison", "",
        "Diagnostic only. Infinite Barrage 37.5%, Boss Devourer base-heavy B, W2500 guaranteed Legendary OFF.", "",
        "| Profile | W2750 | W3000 | W3250 | W3500 | W3750 | W4000 | W4250 | W4500 | W4750 | W5000 |",
        "|---|" + "---:|" * 10,
    ]
    for label, item in payload["profiles"].items():
        lines.append(
            f"| {label} | " + " | ".join(
                f"{item['checkpoints'][str(w)]['reach_rate']:.0%}" for w in CHECKPOINTS
            ) + " |"
        )
    lines += [
        "", "## First run", "",
        "| Profile | Max Wave P25/P50/P75 | Same-run W5000 | First stop waves | W5000 Core exp P50 |",
        "|---|---:|---:|---|---:|",
    ]
    for label, item in payload["profiles"].items():
        wave = item["first_run_max_wave"]
        lines.append(
            f"| {label} | {fmt(wave['p25'],0)}/{fmt(wave['p50'],0)}/{fmt(wave['p75'],0)}"
            f" | {item['first_run_w5000_rate']:.0%} | `{json.dumps(item['first_run_stop_wave'])}`"
            f" | {fmt(item['first_run_checkpoints']['5000']['core_exponent']['p50'],3)} |"
        )
    lines += ["", "### First-run checkpoint margins", ""]
    for label, item in payload["profiles"].items():
        lines += [
            f"#### {label}", "",
            "| W | Reach | Margin P25/P50/P75 | Core exponent P50 | Core Power P50 |",
            "|---:|---:|---:|---:|---:|",
        ]
        for wave in CHECKPOINTS:
            cp = item["first_run_checkpoints"][str(wave)]
            margin = cp["margin"]
            lines.append(
                f"| {wave} | {cp['reach_rate']:.0%}"
                f" | {fmt(margin['p25'])}/{fmt(margin['p50'])}/{fmt(margin['p75'])}"
                f" | {fmt(cp['core_exponent']['p50'],3)} | {fmt(cp['core_power']['p50'])} |"
            )
        lines.append("")
    lines += [
        "", "## Long run", "",
        "| Profile | Best P25/P50/P75 | W5000 | Add Runs P25/P50/P75 | Hours P50 | Success Margin P50 | Terminal Margin P50 | Best-recent10 P50 | Late DP Power P50 | Core Power P50 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, item in payload["profiles"].items():
        best = item["best_wave"]
        runs = item["additional_runs_to_w5000"]
        lines.append(
            f"| {label} | {fmt(best['p25'],0)}/{fmt(best['p50'],0)}/{fmt(best['p75'],0)}"
            f" | {item['success_rate']:.0%}"
            f" | {fmt(runs['p25'],1)}/{fmt(runs['p50'],1)}/{fmt(runs['p75'],1)}"
            f" | {fmt(item['game_hours_to_w5000']['p50'],3)}"
            f" | {fmt(item['w5000_margin']['p50'])} | {fmt(item['terminal_margin']['p50'])}"
            f" | {fmt(item['best_minus_recent10_median']['p50'],0)}"
            f" | {fmt(item['late_dp_power']['p50'])} | {fmt(item['core_power']['p50'])} |"
        )
    lines += [
        "", "## Infinite Barrage dependency", "",
        "| Profile | Group | N | W5000 | Best P50 | Success Margin P50 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for label, item in payload["profiles"].items():
        for key, name in (("barrage_acquired", "acquired"), ("barrage_not_acquired", "not acquired")):
            group = item[key]
            if not group["samples"]:
                continue
            lines.append(
                f"| {label} | {name} | {group['samples']} | {group['success_rate']:.0%}"
                f" | {fmt(group['best_wave']['p50'],0)} | {fmt(group['w5000_margin']['p50'])} |"
            )
    lines += ["", "## Checkpoint margin / direct contributions (P50)", ""]
    for label, item in payload["profiles"].items():
        lines += [
            f"### {label}", "",
            "| W | Margin | Core exponent | late-DP Power | Core Power |",
            "|---:|---:|---:|---:|---:|",
        ]
        for wave in CHECKPOINTS:
            cp = item["checkpoints"][str(wave)]
            lines.append(
                f"| {wave} | {fmt(cp['margin']['p50'])} | {fmt(cp['core_exponent']['p50'],3)}"
                f" | {fmt(cp['late_dp_power']['p50'])} | {fmt(cp['core_power']['p50'])} |"
            )
        lines.append("")
    lines += [
        "## Validation", "",
        f"- Paired W2500 states: {payload['state_count']}",
        "- All profiles use the same saved state and RNG state per trial.",
        "- Pre-W2500 DP baseline levels are identical; only post-W2500 contribution scale differs.",
        "- Core medium is the existing weak-increment ×20% profile; coefficients are unchanged.",
        f"- errors/nonfinite/overflow: {payload['error_count']}/{payload['nonfinite_count']}/{payload['overflow_count']}",
        "- No formal adoption or balance mutation.", "",
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
        default=Path("output/w5000_v1_integrated_core_dp_10_states"),
    )
    args = parser.parse_args()
    with gzip.open(args.states, "rb") as handle:
        captures = pickle.load(handle)
    if len(captures) != 10:
        raise ValueError(f"expected 10 W2500 states, found {len(captures)}")

    grouped = {label: [] for label in PROFILES}
    errors = []
    for label, (dp_scale, core_scale) in PROFILES.items():
        for capture in captures.values():
            try:
                grouped[label].append(replay_one(capture, label, dp_scale, core_scale))
            except Exception as exc:
                errors.append({
                    "profile": label,
                    "trial": capture["trial"],
                    "type": type(exc).__name__,
                    "message": str(exc),
                })

    profiles = {}
    for label, rows in grouped.items():
        summary = summarize_rows(rows)
        summary["barrage_acquired"] = subgroup(rows, True)
        summary["barrage_not_acquired"] = subgroup(rows, False)
        profiles[label] = summary
    nonfinite_count = sum(len(row["nonfinite"]) for rows in grouped.values() for row in rows)
    payload = {
        "state_count": len(captures),
        "trial_ids": sorted(captures),
        "profiles_definition": PROFILES,
        "infinite_barrage_strength": BARRAGE_STRENGTH,
        "profiles": profiles,
        "error_count": len(errors),
        "nonfinite_count": nonfinite_count,
        "overflow_count": sum(error["type"] == "OverflowError" for error in errors),
        "errors": errors,
        "formal_changed": False,
        "balance_adopted": False,
    }
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = output / "integrated_core_dp_report.md"
    summary = output / "integrated_core_dp_summary.json"
    report.write_text(markdown(payload), encoding="utf-8")
    summary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "report": str(report), "json": str(summary), "states": len(captures),
        "errors": len(errors), "nonfinite": nonfinite_count,
        "overflow": payload["overflow_count"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
