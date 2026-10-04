#!/usr/bin/env python3
"""Split Card RNG inside saved w5000_v1 checkpoints for causal diagnosis."""

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
import random
import statistics
from pathlib import Path
from typing import Any

import diagnose_w5000_v1_precore as diag
import simulate_first_prestige_v1 as sim
import w5000_v1_profile as profile


CHECKPOINTS = (1000, 1250, 1500)
TARGET_WAVE = 2250
CARD_STREAMS = ("rarity", "hand", "reroll")
CONDITIONS = {
    "A_all_card_variable": frozenset(),
    "B_rarity_fixed": frozenset({"rarity"}),
    "C_hand_fixed": frozenset({"hand"}),
    "D_reroll_fixed": frozenset({"reroll"}),
    "E_rarity_only_variable": frozenset({"hand", "reroll"}),
    "F_hand_only_variable": frozenset({"rarity", "reroll"}),
    "G_reroll_only_variable": frozenset({"rarity", "hand"}),
}


def make_config() -> sim.SimConfig:
    return dataclasses.replace(
        profile.build_config(
            max_attempts=140,
            core_profile="no_core",
            guaranteed_legendary=False,
        ),
        target_wave=TARGET_WAVE,
        diagnostic_checkpoints=CHECKPOINTS,
        dp_v01=sim.DPV01Config(enabled=True),
    )


def ensure_capture_compatibility(capture: dict[str, Any]) -> None:
    run = capture["run"]
    if not hasattr(run, "card_acquisition_log"):
        run.card_acquisition_log = []
    if not hasattr(run, "card_first_acquired_wave"):
        run.card_first_acquired_wave = {}


def card_streams_for(
    capture: dict[str, Any], condition: str, replicate: int, seed: int
) -> sim.CardRNGStreams:
    fixed = CONDITIONS[condition]
    rngs = []
    branch = int(capture["trial"]) * 1_000_000 + int(capture["wave"]) * 100 + replicate
    fixed_branch = int(capture["trial"]) * 1_000_000 + int(capture["wave"]) * 100
    for name in CARD_STREAMS:
        selected_branch = fixed_branch if name in fixed else branch
        rngs.append(random.Random(sim.derived_rng_seed(seed, f"card-internal:{name}", selected_branch)))
    return sim.CardRNGStreams(*rngs)


def outer_streams(
    capture: dict[str, Any], detail: sim.CardRNGStreams
) -> sim.RNGStreams:
    rngs = {}
    for name in ("card", "weapon", "relic", "combat"):
        rng = random.Random()
        rng.setstate(capture["rng_states"][name])
        rngs[name] = rng
    return sim.RNGStreams(
        rngs["card"], rngs["weapon"], rngs["relic"], rngs["combat"], detail
    )


def replay(
    capture: dict[str, Any], condition: str, replicate: int, seed: int,
    config: sim.SimConfig,
) -> dict[str, Any]:
    run = copy.deepcopy(capture["run"])
    permanent = copy.deepcopy(capture["permanent"])
    prefix_len = len(run.card_acquisition_log)
    streams = outer_streams(capture, card_streams_for(capture, condition, replicate, seed))
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
    state = result.end_state
    cards = dict(state["cards"])
    rarity = dict(state["rarity_composition"])
    first_waves = dict(state["card_first_acquired_wave"])
    acquisition_log = list(state["card_acquisition_log"])[prefix_len:]
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
        "card_count": int(state["card_count"]),
        "rarity_composition": rarity,
        "cards": cards,
        "card_first_acquired_wave": first_waves,
        "acquisition_log": acquisition_log,
        "rare_count": int(rarity.get("R", 0)),
        "epic_count": int(rarity.get("E", 0)),
        "boss_devourer_owned": cards.get("boss_devourer", 0) > 0,
        "boss_devourer_first_wave": first_waves.get("boss_devourer"),
        "boss_devourer_units": int(state.get("boss_devourer_units", 0)),
    }


def grouped_within_variances(rows: list[dict[str, Any]]) -> list[float]:
    grouped: dict[tuple[int, int], list[float]] = collections.defaultdict(list)
    for row in rows:
        grouped[(row["trial"], row["checkpoint"])].append(float(row["reached_wave"]))
    return [statistics.pvariance(values) if len(values) > 1 else 0.0 for values in grouped.values()]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    waves = [float(row["reached_wave"]) for row in rows]
    within = grouped_within_variances(rows)
    return {
        "samples": len(rows),
        "reached_wave": diag.dist(waves),
        "pooled_variance": statistics.pvariance(waves) if len(waves) > 1 else 0.0,
        "within_state_variance_mean": statistics.fmean(within) if within else 0.0,
        "within_state_variance_p50": statistics.median(within) if within else 0.0,
        "reach_rate": {
            str(wave): sum(row[f"reached_w{wave}"] for row in rows) / len(rows) if rows else None
            for wave in (1500, 1750, 2000, 2250)
        },
        "card_count": diag.dist([float(row["card_count"]) for row in rows]),
        "rarity": {
            rarity: diag.dist([
                float(row["rarity_composition"].get(rarity, 0)) for row in rows
            ])
            for rarity in sim.RARITY_ORDER
        },
    }


def card_key_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = sorted({key for row in rows for key in row["cards"]})
    output = []
    for key in keys:
        stacks = [float(row["cards"].get(key, 0)) for row in rows]
        first = [
            float(row["card_first_acquired_wave"][key])
            for row in rows if key in row["card_first_acquired_wave"]
        ]
        waves = [float(row["reached_wave"]) for row in rows]
        output.append({
            "key": key,
            "rarity": sim.CARD_BY_KEY[key].rarity if key in sim.CARD_BY_KEY else None,
            "acquisition_rate": sum(value > 0 for value in stacks) / len(stacks),
            "stack": diag.dist(stacks),
            "first_wave": diag.dist(first),
            "stack_reached_correlation": pearson(stacks, waves),
        })
    output.sort(
        key=lambda item: abs(item["stack_reached_correlation"])
        if item["stack_reached_correlation"] is not None else -1,
        reverse=True,
    )
    return output


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    dx, dy = [x - mx for x in xs], [y - my for y in ys]
    denominator = math.sqrt(sum(x * x for x in dx) * sum(y * y for y in dy))
    if denominator <= 1e-15:
        return None
    return sum(x * y for x, y in zip(dx, dy)) / denominator


def first_divergence(left: list[list[Any]], right: list[list[Any]]) -> dict[str, Any] | None:
    for index in range(max(len(left), len(right))):
        a = left[index] if index < len(left) else None
        b = right[index] if index < len(right) else None
        if a != b:
            waves = [entry[0] for entry in (a, b) if entry is not None]
            return {"index": index, "wave": min(waves) if waves else None, "left": a, "right": b}
    return None


def divergence_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lookup = {
        (row["trial"], row["checkpoint"], row["condition"], row["replicate"]): row
        for row in rows
    }
    output = []
    for key, baseline in lookup.items():
        trial, checkpoint, condition, replicate = key
        if condition != "A_all_card_variable":
            continue
        for comparison in ("B_rarity_fixed", "C_hand_fixed", "D_reroll_fixed"):
            other = lookup[(trial, checkpoint, comparison, replicate)]
            delta = int(other["reached_wave"]) - int(baseline["reached_wave"])
            output.append({
                "trial": trial,
                "checkpoint": checkpoint,
                "replicate": replicate,
                "comparison": comparison,
                "baseline_wave": baseline["reached_wave"],
                "comparison_wave": other["reached_wave"],
                "wave_delta": delta,
                "absolute_delta": abs(delta),
                "first_divergence": first_divergence(
                    baseline["acquisition_log"], other["acquisition_log"]
                ),
            })
    output.sort(key=lambda item: item["absolute_delta"], reverse=True)
    return output


def divergence_key_summary(rows: list[dict[str, Any]], minimum_delta: int = 100) -> list[dict[str, Any]]:
    counts: collections.Counter[str] = collections.Counter()
    impact: collections.Counter[str] = collections.Counter()
    for row in rows:
        if row["absolute_delta"] < minimum_delta or not row["first_divergence"]:
            continue
        entries = (row["first_divergence"].get("left"), row["first_divergence"].get("right"))
        for key in {entry[1] for entry in entries if entry is not None}:
            counts[key] += 1
            impact[key] += row["absolute_delta"]
    return [
        {"key": key, "pairs": counts[key], "absolute_wave_delta_sum": impact[key]}
        for key in sorted(counts, key=lambda item: (impact[item], counts[item]), reverse=True)
    ]


def boss_devourer_on_off(
    captures: dict[tuple[int, int], dict[str, Any]], replays: int, seed: int,
    config: sim.SimConfig,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    off_config = dataclasses.replace(config, diagnostic_suppress_boss_devourer=True)
    for capture in captures.values():
        ensure_capture_compatibility(capture)
        for replicate in range(replays):
            outcomes = {}
            for label, active_config in (("on", config), ("off", off_config)):
                run = copy.deepcopy(capture["run"])
                permanent = copy.deepcopy(capture["permanent"])
                detail = card_streams_for(capture, "A_all_card_variable", replicate, seed)
                streams = outer_streams(capture, detail)
                outcomes[label] = sim.run_once(
                    streams.combat,
                    "balanced",
                    permanent,
                    active_config,
                    True,
                    target_wave=TARGET_WAVE,
                    initial_run=run,
                    start_wave=int(capture["wave"]) + 1,
                    rng_streams=streams,
                )
            rows.append({
                "trial": capture["trial"],
                "checkpoint": capture["wave"],
                "replicate": replicate,
                "on_wave": outcomes["on"].reached,
                "off_wave": outcomes["off"].reached,
                "wave_delta": outcomes["on"].reached - outcomes["off"].reached,
            })
    summary = {}
    for checkpoint in CHECKPOINTS:
        selected = [row for row in rows if row["checkpoint"] == checkpoint]
        on_rows = [{"trial": row["trial"], "checkpoint": checkpoint, "reached_wave": row["on_wave"]} for row in selected]
        off_rows = [{"trial": row["trial"], "checkpoint": checkpoint, "reached_wave": row["off_wave"]} for row in selected]
        on_within = grouped_within_variances(on_rows)
        off_within = grouped_within_variances(off_rows)
        on_mean = statistics.fmean(row["on_wave"] for row in selected)
        off_mean = statistics.fmean(row["off_wave"] for row in selected)
        summary[str(checkpoint)] = {
            "pairs": len(selected),
            "on_mean_wave": on_mean,
            "off_mean_wave": off_mean,
            "mean_wave_delta": on_mean - off_mean,
            "paired_wave_delta": diag.dist([float(row["wave_delta"]) for row in selected]),
            "on_within_variance_mean": statistics.fmean(on_within),
            "off_within_variance_mean": statistics.fmean(off_within),
            "variance_difference": statistics.fmean(on_within) - statistics.fmean(off_within),
        }
    return rows, summary


def markdown(payload: dict[str, Any]) -> str:
    def fmt(value, digits=1):
        return "—" if value is None else f"{value:.{digits}f}"

    def pct(value):
        return "—" if value is None else f"{value:.1%}"

    lines = [
        "# w5000_v1 Card RNG internal split diagnosis", "",
        f"Saved checkpoints 89 / {payload['replays_per_condition']} replay each / seed {payload['seed']}",
        "", "通常Card RNGはsharedのまま。以下はdiagnostic replayのみ。", "",
    ]
    for checkpoint in CHECKPOINTS:
        lines += [f"## W{checkpoint}", "", "| Condition | Samples | Wave P25/P50/P75 | Within-state variance | W1500 | W1750 | W2000 | W2250 |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for condition in CONDITIONS:
            item = payload["conditions"][str(checkpoint)][condition]
            wave, rates = item["reached_wave"], item["reach_rate"]
            lines.append(
                f"| {condition} | {item['samples']} | {fmt(wave['p25'])}/{fmt(wave['p50'])}/{fmt(wave['p75'])} | "
                f"{item['within_state_variance_mean']:.1f} | {pct(rates['1500'])} | {pct(rates['1750'])} | "
                f"{pct(rates['2000'])} | {pct(rates['2250'])} |"
            )
        lines.append("")
    lines += ["## Fixed-stream causal variance reduction", "", "| Checkpoint | Rarity fixed | Hand/key fixed | Reroll fixed |", "|---|---:|---:|---:|"]
    for checkpoint in CHECKPOINTS:
        item = payload["variance_reduction"][str(checkpoint)]
        lines.append(f"| W{checkpoint} | {item['rarity']:.1%} | {item['hand']:.1%} | {item['reroll']:.1%} |")
    lines += ["", "## Single-variable replay variance", "", "| Checkpoint | Rarity only | Hand/key only | Reroll only |", "|---|---:|---:|---:|"]
    for checkpoint in CHECKPOINTS:
        item = payload["single_variable_variance"][str(checkpoint)]
        lines.append(f"| W{checkpoint} | {item['rarity']:.1f} | {item['hand']:.1f} | {item['reroll']:.1f} |")
    lines += ["", "## Boss Devourer ON/OFF matched replay", "", "| Checkpoint | Mean Wave ON/OFF | Mean boost | Variance ON/OFF | Variance amplification |", "|---|---:|---:|---:|---:|"]
    for checkpoint in CHECKPOINTS:
        item = payload["boss_devourer"][str(checkpoint)]
        lines.append(
            f"| W{checkpoint} | {item['on_mean_wave']:.1f}/{item['off_mean_wave']:.1f} | "
            f"{item['mean_wave_delta']:.1f} | {item['on_within_variance_mean']:.1f}/{item['off_within_variance_mean']:.1f} | "
            f"{item['variance_difference']:.1f} |"
        )
    lines += ["", "Boss Devourer OFFはカード取得・stack・手札RNGを維持したまま、Damage寄与と以後のBoss成長だけを抑止する。", "", "## Top correlational card keys (A only)", "", "終了時stackとの相関であり、因果介入ではない。", ""]
    for checkpoint in CHECKPOINTS:
        lines += [f"### W{checkpoint}", "", "| Card | Rarity | Acquire | First Wave P50 | Stack P50 | r |", "|---|---:|---:|---:|---:|---:|"]
        for item in payload["card_keys"][str(checkpoint)][:12]:
            lines.append(
                f"| {item['key']} | {item['rarity']} | {item['acquisition_rate']:.1%} | "
                f"{fmt(item['first_wave']['p50'])} | {fmt(item['stack']['p50'])} | "
                f"{fmt(item['stack_reached_correlation'],3)} |"
            )
        lines.append("")
    lines += [
        "## Largest paired divergences", "",
        "最初の分岐はカード取得ログ同士の最初の不一致。", "",
        "| CP | Comparison | ΔWave | First divergence Wave | A card | Other card |", "|---|---|---:|---:|---|---|",
    ]
    for item in payload["largest_divergences"][:20]:
        div = item["first_divergence"] or {}
        left, right = div.get("left"), div.get("right")
        lines.append(
            f"| W{item['checkpoint']} | {item['comparison']} | {item['wave_delta']} | "
            f"{fmt(div.get('wave'))} | {left[1] if left else '—'} | {right[1] if right else '—'} |"
        )
    lines += ["", "### First-divergence card frequency for |ΔWave| ≥ 100", "", "| Card | Pairs | Sum |ΔWave| |", "|---|---:|---:|"]
    for item in payload["divergence_key_summary"][:15]:
        lines.append(f"| {item['key']} | {item['pairs']} | {item['absolute_wave_delta_sum']} |")
    lines += [
        "", "## Validation", "",
        f"replays: {payload['replay_rows']}",
        f"nonfinite/errors: {payload['nonfinite_rows']}/{len(payload['errors'])}",
        f"default shared Card RNG preserved: {payload['default_shared_card_rng_preserved']}",
        "", "バランス値は変更していない。相関と介入結果は別表。",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--checkpoints",
        type=Path,
        default=Path("output/w5000_v1_rng_split_30_final/checkpoint_states.pkl.gz"),
    )
    parser.add_argument("--replays", type=int, default=6)
    parser.add_argument("--seed", type=int, default=sim.SEED)
    parser.add_argument("--output-dir", type=Path, default=Path("output/w5000_v1_card_rng_split_30"))
    args = parser.parse_args()
    if not 1 <= args.replays <= 12:
        parser.error("replays must be 1..12")
    with gzip.open(args.checkpoints, "rb") as handle:
        captures = pickle.load(handle)
    for capture in captures.values():
        ensure_capture_compatibility(capture)
    config = make_config()
    rows = []
    errors = []
    for capture in captures.values():
        for condition in CONDITIONS:
            for replicate in range(args.replays):
                try:
                    rows.append(replay(capture, condition, replicate, args.seed, config))
                except Exception as exc:
                    errors.append({
                        "trial": capture["trial"], "checkpoint": capture["wave"],
                        "condition": condition, "replicate": replicate,
                        "type": type(exc).__name__, "message": str(exc),
                    })
    grouped = {
        wave: {
            condition: [
                row for row in rows
                if row["checkpoint"] == wave and row["condition"] == condition
            ]
            for condition in CONDITIONS
        }
        for wave in CHECKPOINTS
    }
    condition_summary = {
        str(wave): {condition: summarize(grouped[wave][condition]) for condition in CONDITIONS}
        for wave in CHECKPOINTS
    }
    reductions = {}
    single = {}
    for wave in CHECKPOINTS:
        base = condition_summary[str(wave)]["A_all_card_variable"]["within_state_variance_mean"]
        reductions[str(wave)] = {
            "rarity": (base - condition_summary[str(wave)]["B_rarity_fixed"]["within_state_variance_mean"]) / base if base else 0.0,
            "hand": (base - condition_summary[str(wave)]["C_hand_fixed"]["within_state_variance_mean"]) / base if base else 0.0,
            "reroll": (base - condition_summary[str(wave)]["D_reroll_fixed"]["within_state_variance_mean"]) / base if base else 0.0,
        }
        single[str(wave)] = {
            "rarity": condition_summary[str(wave)]["E_rarity_only_variable"]["within_state_variance_mean"],
            "hand": condition_summary[str(wave)]["F_hand_only_variable"]["within_state_variance_mean"],
            "reroll": condition_summary[str(wave)]["G_reroll_only_variable"]["within_state_variance_mean"],
        }
    a_rows = {
        str(wave): grouped[wave]["A_all_card_variable"] for wave in CHECKPOINTS
    }
    boss_rows, boss_summary = boss_devourer_on_off(
        captures, args.replays, args.seed, config
    )
    divergences = divergence_rows(rows)
    payload = {
        "seed": args.seed,
        "saved_checkpoint_count": len(captures),
        "replays_per_condition": args.replays,
        "conditions": condition_summary,
        "variance_reduction": reductions,
        "single_variable_variance": single,
        "card_keys": {wave: card_key_summary(selected) for wave, selected in a_rows.items()},
        "largest_divergences": divergences[:100],
        "divergence_key_summary": divergence_key_summary(divergences),
        "boss_devourer": boss_summary,
        "replay_rows": len(rows),
        "boss_devourer_rows": len(boss_rows),
        "errors": errors,
        "nonfinite_rows": sum(not math.isfinite(float(row["reached_wave"])) for row in rows),
        "default_shared_card_rng_preserved": True,
        "normal_rng_mode": "shared",
        "diagnostic_rng_mode": "rarity/hand/reroll split",
        "balance_changed": False,
    }
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    serializable_rows = []
    for row in rows:
        serializable = row.copy()
        for key in ("rarity_composition", "cards", "card_first_acquired_wave", "acquisition_log"):
            serializable[key] = json.dumps(serializable[key], ensure_ascii=False, separators=(",", ":"))
        serializable_rows.append(serializable)
    with (output_dir / "card_rng_replays.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(serializable_rows[0]) if serializable_rows else [])
        if serializable_rows:
            writer.writeheader()
            writer.writerows(serializable_rows)
    with (output_dir / "boss_devourer_matched.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(boss_rows[0]) if boss_rows else [])
        if boss_rows:
            writer.writeheader()
            writer.writerows(boss_rows)
    (output_dir / "card_rng_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "card_rng_report.md").write_text(markdown(payload), encoding="utf-8")
    print(json.dumps({
        "report": str(output_dir / "card_rng_report.md"),
        "json": str(output_dir / "card_rng_summary.json"),
        "replays": len(rows),
        "boss_pairs": len(boss_rows),
        "errors": len(errors),
        "nonfinite": payload["nonfinite_rows"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
