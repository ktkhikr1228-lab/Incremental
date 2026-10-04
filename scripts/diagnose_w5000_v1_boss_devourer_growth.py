#!/usr/bin/env python3
"""Matched Boss Devourer baseline/growth intervention on saved checkpoints."""

from __future__ import annotations

import argparse
import collections
import copy
import csv
import dataclasses
import gzip
import json
import math
import pickle
import statistics
from pathlib import Path
from typing import Any

import diagnose_w5000_v1_precore as diag
import diagnose_w5000_v1_card_rng_split as card_diag
import simulate_first_prestige_v1 as sim


CHECKPOINTS = (1000, 1250, 1500)
TARGET_WAVE = 2250
CONDITIONS = {
    "A_current": {"growth": 1.0, "suppress": False},
    "B_frozen_after_checkpoint": {"growth": 0.0, "suppress": False},
    "C_reduced_growth_50": {"growth": 0.5, "suppress": False},
    "D_no_effect": {"growth": 0.0, "suppress": True},
}


def condition_config(base: sim.SimConfig, name: str) -> sim.SimConfig:
    values = CONDITIONS[name]
    return dataclasses.replace(
        base,
        diagnostic_boss_devourer_growth_multiplier=values["growth"],
        diagnostic_suppress_boss_devourer=values["suppress"],
    )


def replay_one(
    capture: dict[str, Any], condition: str, replicate: int, seed: int,
    base_config: sim.SimConfig,
) -> dict[str, Any]:
    run = copy.deepcopy(capture["run"])
    permanent = copy.deepcopy(capture["permanent"])
    start_units = float(run.boss_devourer_units)
    start_stacks = sim.n(run.counts, "boss_devourer")
    detail = card_diag.card_streams_for(
        capture, "A_all_card_variable", replicate, seed
    )
    streams = card_diag.outer_streams(capture, detail)
    config = condition_config(base_config, condition)
    result = sim.run_once(
        streams.combat,
        "balanced",
        permanent,
        config,
        True,
        target_wave=TARGET_WAVE,
        initial_run=run,
        start_wave=int(capture["wave"]) + 1,
        rng_streams=streams,
    )
    evaluation_wave = result.failure_wave or TARGET_WAVE
    snapshot = sim.compute_snapshot(run, permanent, evaluation_wave % 10 == 0, config)
    margin = snapshot.log_dps - sim.configured_enemy_power(evaluation_wave, config)
    return {
        "trial": int(capture["trial"]),
        "checkpoint": int(capture["wave"]),
        "condition": condition,
        "replicate": replicate,
        "reached_wave": result.reached,
        "reached_w1500": result.reached >= 1500,
        "reached_w1750": result.reached >= 1750,
        "reached_w2000": result.reached >= 2000,
        "reached_w2250": result.reached >= 2250,
        "boss_devourer_added_card_stacks": sim.n(run.counts, "boss_devourer") - start_stacks,
        "boss_devourer_added_growth_units": float(run.boss_devourer_units) - start_units,
        "player_enemy_margin": margin,
    }


def within_state_variances(rows: list[dict[str, Any]]) -> list[float]:
    grouped: dict[tuple[int, int], list[float]] = collections.defaultdict(list)
    for row in rows:
        grouped[(row["trial"], row["checkpoint"])].append(float(row["reached_wave"]))
    return [statistics.pvariance(values) if len(values) > 1 else 0.0 for values in grouped.values()]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    waves = [float(row["reached_wave"]) for row in rows]
    fixed_rows = [row for row in rows if row["replicate"] == 0]
    fixed_waves = [float(row["reached_wave"]) for row in fixed_rows]
    within = within_state_variances(rows)
    return {
        "samples": len(rows),
        "reached_wave_mean": statistics.fmean(waves) if waves else None,
        "reached_wave": diag.dist(waves),
        "pooled_variance": statistics.pvariance(waves) if len(waves) > 1 else 0.0,
        "card_rng_variable_within_state_variance": statistics.fmean(within) if within else 0.0,
        "card_rng_fixed_across_state_variance": statistics.pvariance(fixed_waves) if len(fixed_waves) > 1 else 0.0,
        "card_rng_fixed_reached_wave": diag.dist(fixed_waves),
        "reach_rate": {
            str(wave): sum(row[f"reached_w{wave}"] for row in rows) / len(rows) if rows else None
            for wave in (1500, 1750, 2000, 2250)
        },
        "added_card_stacks": diag.dist([
            float(row["boss_devourer_added_card_stacks"]) for row in rows
        ]),
        "added_growth_units": diag.dist([
            float(row["boss_devourer_added_growth_units"]) for row in rows
        ]),
        "player_enemy_margin": diag.dist([
            float(row["player_enemy_margin"]) for row in rows
        ]),
    }


def checkpoint_base_contribution(
    captures: dict[tuple[int, int], dict[str, Any]], base_config: sim.SimConfig
) -> dict[str, Any]:
    off_config = dataclasses.replace(base_config, diagnostic_suppress_boss_devourer=True)
    output = {}
    for checkpoint in CHECKPOINTS:
        values = []
        for (_, wave), capture in captures.items():
            if wave != checkpoint:
                continue
            run = capture["run"]
            permanent = capture["permanent"]
            boss = checkpoint % 10 == 0
            current = sim.compute_snapshot(run, permanent, boss, base_config).log_dps
            off = sim.compute_snapshot(run, permanent, boss, off_config).log_dps
            values.append(current - off)
        output[str(checkpoint)] = diag.dist(values)
    return output


def markdown(payload: dict[str, Any]) -> str:
    def fmt(value, digits=1):
        return "—" if value is None else f"{value:.{digits}f}"

    def pct(value):
        return "—" if value is None else f"{value:.1%}"

    lines = [
        "# w5000_v1 Boss Devourer progression dependency", "",
        f"Saved checkpoints {payload['checkpoint_count']} / {payload['replays']} matched Card RNG replays each / seed {payload['seed']}",
        "", "Checkpoint時点の累積効果を保持し、以後の成長倍率だけを介入。Dのみ全効果OFF。", "",
    ]
    for checkpoint in CHECKPOINTS:
        lines += [f"## W{checkpoint}", "", "| Condition | Mean | P25/P50/P75 | Card RNG variance | W1500 | W1750 | W2000 | W2250 | Added stacks P50 | Added units P50 | Margin P50 |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for condition in CONDITIONS:
            item = payload["conditions"][str(checkpoint)][condition]
            wave, rates = item["reached_wave"], item["reach_rate"]
            lines.append(
                f"| {condition} | {fmt(item['reached_wave_mean'])} | "
                f"{fmt(wave['p25'])}/{fmt(wave['p50'])}/{fmt(wave['p75'])} | "
                f"{item['card_rng_variable_within_state_variance']:.1f} | "
                f"{pct(rates['1500'])} | {pct(rates['1750'])} | {pct(rates['2000'])} | {pct(rates['2250'])} | "
                f"{fmt(item['added_card_stacks']['p50'])} | {fmt(item['added_growth_units']['p50'])} | "
                f"{fmt(item['player_enemy_margin']['p50'],3)} |"
            )
        lines.append("")
    lines += ["## Checkpoint base contribution", "", "Current Power − no-effect Power at the saved checkpoint.", "", "| Checkpoint | Power P25/P50/P75 |", "|---|---:|"]
    for checkpoint in CHECKPOINTS:
        item = payload["checkpoint_base_contribution"][str(checkpoint)]
        lines.append(f"| W{checkpoint} | {fmt(item['p25'],3)}/{fmt(item['p50'],3)}/{fmt(item['p75'],3)} |")
    lines += ["", "## Card RNG variance reduction vs current", "", "| Checkpoint | Freeze growth | 50% growth | No effect |", "|---|---:|---:|---:|"]
    for checkpoint in CHECKPOINTS:
        item = payload["variance_reduction"][str(checkpoint)]
        lines.append(f"| W{checkpoint} | {item['frozen']:.1%} | {item['half']:.1%} | {item['off']:.1%} |")
    lines += ["", "## Card RNG fixed versus variable", "", "固定列は各stateのreplicate 0を一度だけ使ったstate間分散。可変列は同一state内6 replayの平均分散。尺度が異なるため直接比率にはしない。", "", "| Checkpoint | Condition | Fixed across-state variance | Variable within-state variance |", "|---|---|---:|---:|"]
    for checkpoint in CHECKPOINTS:
        for condition in CONDITIONS:
            item = payload["conditions"][str(checkpoint)][condition]
            lines.append(
                f"| W{checkpoint} | {condition} | {item['card_rng_fixed_across_state_variance']:.1f} | "
                f"{item['card_rng_variable_within_state_variance']:.1f} |"
            )
    lines += [
        "", "## Validation", "",
        f"matched rows: {payload['row_count']}",
        f"nonfinite/errors: {payload['nonfinite_rows']}/{len(payload['errors'])}",
        "", "相関ではなくgrowth multiplierへの診断専用介入。formal値・通常profileは未変更。",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--checkpoints", type=Path,
        default=Path("output/w5000_v1_rng_split_30_final/checkpoint_states.pkl.gz"),
    )
    parser.add_argument("--replays", type=int, default=6)
    parser.add_argument("--seed", type=int, default=sim.SEED)
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("output/w5000_v1_boss_devourer_growth_30"),
    )
    args = parser.parse_args()
    if not 1 <= args.replays <= 12:
        parser.error("replays must be 1..12")
    with gzip.open(args.checkpoints, "rb") as handle:
        captures = pickle.load(handle)
    for capture in captures.values():
        card_diag.ensure_capture_compatibility(capture)
    base_config = card_diag.make_config()
    rows = []
    errors = []
    for capture in captures.values():
        for replicate in range(args.replays):
            for condition in CONDITIONS:
                try:
                    rows.append(replay_one(
                        capture, condition, replicate, args.seed, base_config
                    ))
                except Exception as exc:
                    errors.append({
                        "trial": capture["trial"], "checkpoint": capture["wave"],
                        "condition": condition, "replicate": replicate,
                        "type": type(exc).__name__, "message": str(exc),
                    })
    summaries = {
        str(checkpoint): {
            condition: summarize([
                row for row in rows
                if row["checkpoint"] == checkpoint and row["condition"] == condition
            ])
            for condition in CONDITIONS
        }
        for checkpoint in CHECKPOINTS
    }
    reductions = {}
    for checkpoint in CHECKPOINTS:
        items = summaries[str(checkpoint)]
        base = items["A_current"]["card_rng_variable_within_state_variance"]
        reductions[str(checkpoint)] = {
            "frozen": (base - items["B_frozen_after_checkpoint"]["card_rng_variable_within_state_variance"]) / base if base else 0.0,
            "half": (base - items["C_reduced_growth_50"]["card_rng_variable_within_state_variance"]) / base if base else 0.0,
            "off": (base - items["D_no_effect"]["card_rng_variable_within_state_variance"]) / base if base else 0.0,
        }
    payload = {
        "seed": args.seed,
        "checkpoint_count": len(captures),
        "replays": args.replays,
        "conditions": summaries,
        "checkpoint_base_contribution": checkpoint_base_contribution(captures, base_config),
        "variance_reduction": reductions,
        "row_count": len(rows),
        "errors": errors,
        "nonfinite_rows": sum(
            not all(math.isfinite(float(row[key])) for key in (
                "reached_wave", "boss_devourer_added_growth_units", "player_enemy_margin"
            ))
            for row in rows
        ),
        "balance_changed": False,
        "normal_growth_multiplier": 1.0,
    }
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "boss_devourer_growth_replays.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)
    (output_dir / "boss_devourer_growth_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "boss_devourer_growth_report.md").write_text(
        markdown(payload), encoding="utf-8"
    )
    print(json.dumps({
        "report": str(output_dir / "boss_devourer_growth_report.md"),
        "json": str(output_dir / "boss_devourer_growth_summary.json"),
        "rows": len(rows), "errors": len(errors),
        "nonfinite": payload["nonfinite_rows"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
