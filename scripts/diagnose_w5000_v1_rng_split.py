#!/usr/bin/env python3
"""Experimental causal RNG split diagnosis for w5000_v1 run variance."""

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
CONDITIONS = {
    "A_all_variable": frozenset(),
    "B_card_fixed": frozenset({"card"}),
    "C_weapon_fixed": frozenset({"weapon"}),
    "D_relic_fixed": frozenset({"relic"}),
    "E_card_only_variable": frozenset({"weapon", "relic", "combat"}),
    "F_weapon_only_variable": frozenset({"card", "relic", "combat"}),
    "G_relic_only_variable": frozenset({"card", "weapon", "combat"}),
}
STREAM_NAMES = ("card", "weapon", "relic", "combat")


def make_config(max_attempts: int) -> sim.SimConfig:
    return dataclasses.replace(
        profile.build_config(
            max_attempts=max_attempts,
            core_profile="no_core",
            guaranteed_legendary=False,
        ),
        target_wave=TARGET_WAVE,
        diagnostic_checkpoints=CHECKPOINTS,
        dp_v01=sim.DPV01Config(enabled=True),
    )


def capture_payload(
    trial: int,
    wave: int,
    run: sim.RunState,
    permanent: sim.PermanentState,
    streams: sim.RNGStreams,
) -> dict[str, Any]:
    return {
        "trial": trial,
        "wave": wave,
        "run": copy.deepcopy(run),
        "permanent": copy.deepcopy(permanent),
        "rng_states": {name: getattr(streams, name).getstate() for name in STREAM_NAMES},
    }


def collect_checkpoints(
    trials: int, seed: int, config: sim.SimConfig
) -> tuple[list[sim.TrialResult], dict[tuple[int, int], dict[str, Any]], list[dict[str, object]]]:
    results: list[sim.TrialResult] = []
    captures: dict[tuple[int, int], dict[str, Any]] = {}
    errors: list[dict[str, object]] = []
    for trial in range(trials):
        base_seed = seed + 1_000_000 + trial
        streams = sim.make_split_rng_streams(base_seed)

        def capture(wave, run, permanent, active_streams, trial_index=trial):
            key = (trial_index, wave)
            if wave in CHECKPOINTS and key not in captures:
                captures[key] = capture_payload(
                    trial_index, wave, run, permanent, active_streams
                )

        try:
            results.append(
                sim.run_trial(
                    streams.combat,
                    "balanced",
                    config,
                    True,
                    rng_streams=streams,
                    checkpoint_capture=capture,
                )
            )
        except Exception as exc:
            errors.append({
                "trial": trial,
                "type": type(exc).__name__,
                "message": str(exc),
            })
    return results, captures, errors


def replay_streams(
    capture: dict[str, Any], condition: str, replicate: int, seed: int
) -> sim.RNGStreams:
    fixed = CONDITIONS[condition]
    rngs: list[random.Random] = []
    for name in STREAM_NAMES:
        rng = random.Random()
        if name in fixed:
            rng.setstate(capture["rng_states"][name])
        else:
            branch = (
                int(capture["trial"]) * 1_000_000
                + int(capture["wave"]) * 100
                + replicate
            )
            rng.seed(sim.derived_rng_seed(seed, f"counterfactual:{name}", branch))
        rngs.append(rng)
    return sim.RNGStreams(*rngs)


def replay_one(
    capture: dict[str, Any],
    condition: str,
    replicate: int,
    seed: int,
    config: sim.SimConfig,
) -> dict[str, Any]:
    run = copy.deepcopy(capture["run"])
    permanent = copy.deepcopy(capture["permanent"])
    streams = replay_streams(capture, condition, replicate, seed)
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
    return {
        "trial": capture["trial"],
        "checkpoint": capture["wave"],
        "condition": condition,
        "replicate": replicate,
        "reached_wave": result.reached,
        "reached_w1500": result.reached >= 1500,
        "reached_w1750": result.reached >= 1750,
        "reached_w2000": result.reached >= 2000,
        "reached_w2250": result.reached >= 2250,
        "card_count": state["card_count"],
        "rare_count": rarity.get("R", 0),
        "epic_count": rarity.get("E", 0),
        "boss_devourer_owned": cards.get("boss_devourer", 0) > 0,
        "boss_devourer_stacks": cards.get("boss_devourer", 0),
        "boss_devourer_first_wave": state.get("boss_devourer_first_wave"),
        "boss_devourer_units": state.get("boss_devourer_units", 0),
        "weapon_power": state["weapon_power"],
        "relic_power": state["relic_power"],
    }


def percentile(values: list[float], q: float) -> float | None:
    return diag.percentile(values, q) if values else None


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    waves = [float(row["reached_wave"]) for row in rows]
    by_capture: dict[tuple[int, int], list[float]] = collections.defaultdict(list)
    for row in rows:
        by_capture[(int(row["trial"]), int(row["checkpoint"]))].append(float(row["reached_wave"]))
    within_variances = [
        statistics.pvariance(values) if len(values) > 1 else 0.0
        for values in by_capture.values()
    ]
    return {
        "samples": len(rows),
        "reached_wave": diag.dist(waves),
        "variance": statistics.pvariance(waves) if len(waves) > 1 else 0.0,
        "within_capture_variance_mean": statistics.fmean(within_variances) if within_variances else 0.0,
        "within_capture_variance_p50": statistics.median(within_variances) if within_variances else 0.0,
        "reach_rate": {
            str(wave): sum(row[f"reached_w{wave}"] for row in rows) / len(rows)
            if rows else None
            for wave in (1500, 1750, 2000, 2250)
        },
        "card_count": diag.dist([float(row["card_count"]) for row in rows]),
        "rare_count": diag.dist([float(row["rare_count"]) for row in rows]),
        "epic_count": diag.dist([float(row["epic_count"]) for row in rows]),
        "boss_devourer_owned_rate": sum(row["boss_devourer_owned"] for row in rows) / len(rows)
        if rows else None,
        "boss_devourer_first_wave": diag.dist([
            float(row["boss_devourer_first_wave"])
            for row in rows if row["boss_devourer_first_wave"] is not None
        ]),
        "boss_devourer_units": diag.dist([float(row["boss_devourer_units"]) for row in rows]),
        "weapon_power": diag.dist([float(row["weapon_power"]) for row in rows]),
        "relic_power": diag.dist([float(row["relic_power"]) for row in rows]),
    }


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    dx, dy = [x - mx for x in xs], [y - my for y in ys]
    denominator = math.sqrt(sum(x * x for x in dx) * sum(y * y for y in dy))
    if denominator <= 1e-15:
        return None
    return sum(x * y for x, y in zip(dx, dy)) / denominator


def correlation_summary(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    waves = [float(row["reached_wave"]) for row in rows]
    keys = (
        "card_count", "rare_count", "epic_count", "boss_devourer_stacks",
        "boss_devourer_units", "weapon_power", "relic_power",
    )
    return {key: pearson([float(row[key]) for row in rows], waves) for key in keys}


def matched_boss_devourer(
    captures: dict[tuple[int, int], dict[str, Any]], seed: int, config: sim.SimConfig
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    item = sim.CARD_BY_KEY["boss_devourer"]
    for (trial, checkpoint), capture in sorted(captures.items()):
        owned_at_checkpoint = sim.n(capture["run"].counts, "boss_devourer") > 0
        outcomes = {}
        labels = (("suppressed", False), ("owned", True)) if owned_at_checkpoint else (("absent", False), ("forced", True))
        for label, active in labels:
            run = copy.deepcopy(capture["run"])
            permanent = copy.deepcopy(capture["permanent"])
            if not owned_at_checkpoint and active:
                run.card_first_acquired_wave["boss_devourer"] = checkpoint + 1
                sim.acquire_card(run, item)
            elif owned_at_checkpoint and not active:
                stacks = sim.n(run.counts, "boss_devourer")
                run.counts["boss_devourer"] = 0
                for tag in item.tags:
                    run.tag_counts[tag] = max(0, run.tag_counts[tag] - stacks)
                run.effect_version += 1
            streams = replay_streams(capture, "E_card_only_variable", 0, seed)
            # Matched intervention: restore the saved card stream too, so only
            # the explicit Boss Devourer acquisition differs.
            streams.card.setstate(capture["rng_states"]["card"])
            result = sim.run_once(
                streams.combat,
                "balanced",
                permanent,
                config,
                True,
                target_wave=TARGET_WAVE,
                initial_run=run,
                start_wave=checkpoint + 1,
                rng_streams=streams,
            )
            outcomes[label] = result
        low_label, high_label = labels[0][0], labels[1][0]
        rows.append({
            "trial": trial,
            "checkpoint": checkpoint,
            "intervention": "effect_suppression" if owned_at_checkpoint else "forced_acquisition",
            "low_wave": outcomes[low_label].reached,
            "high_wave": outcomes[high_label].reached,
            "wave_delta": outcomes[high_label].reached - outcomes[low_label].reached,
            "high_growth_units": outcomes[high_label].end_state.get("boss_devourer_units", 0),
        })
    return rows


def markdown(payload: dict[str, Any]) -> str:
    def fmt(value, digits=1):
        return "—" if value is None else f"{value:.{digits}f}"

    def pct(value):
        return "—" if value is None else f"{value:.1%}"

    lines = [
        "# w5000_v1 experimental RNG split diagnosis",
        "",
        f"DP v0.1 BC / W2500 guaranteed Legendary OFF / {payload['trials']} trials / "
        f"{payload['replays_per_checkpoint']} replays per checkpoint-condition / seed {payload['seed']}",
        "",
        "通常実行はshared RNGのまま。以下は診断専用split RNGの結果。",
        "",
    ]
    for checkpoint in CHECKPOINTS:
        lines += [f"## Checkpoint W{checkpoint}", "", "| Condition | Samples | Wave P25/P50/P75 | Mean within-state variance | W1500 | W1750 | W2000 | W2250 |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for condition in CONDITIONS:
            item = payload["interventions"][str(checkpoint)][condition]
            wave = item["reached_wave"]
            rates = item["reach_rate"]
            lines.append(
                f"| {condition} | {item['samples']} | {fmt(wave['p25'])}/{fmt(wave['p50'])}/{fmt(wave['p75'])} | "
                f"{item['within_capture_variance_mean']:.1f} | {pct(rates['1500'])} | {pct(rates['1750'])} | {pct(rates['2000'])} | {pct(rates['2250'])} |"
            )
        lines.append("")
    lines += ["## Variance intervention summary", "", "Aの分散に対し、対象stream固定時にどれだけ分散が減ったか。正値ほどそのstreamの因果寄与候補が大きい。", "", "| Checkpoint | Card固定 | Weapon固定 | Relic固定 |", "|---|---:|---:|---:|"]
    for checkpoint in CHECKPOINTS:
        item = payload["variance_reduction_vs_all_variable"][str(checkpoint)]
        lines.append(f"| W{checkpoint} | {item['card']:.1%} | {item['weapon']:.1%} | {item['relic']:.1%} |")
    lines += ["", "## All-variable outcome state (correlational summary)", "", "| Checkpoint | Cards P50 | R/E P50 | Boss Dev owned | First Wave P50 | Growth units P50 | Weapon Power P50 | Relic Power P50 |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for checkpoint in CHECKPOINTS:
        item = payload["interventions"][str(checkpoint)]["A_all_variable"]
        lines.append(
            f"| W{checkpoint} | {fmt(item['card_count']['p50'])} | "
            f"{fmt(item['rare_count']['p50'])}/{fmt(item['epic_count']['p50'])} | "
            f"{pct(item['boss_devourer_owned_rate'])} | {fmt(item['boss_devourer_first_wave']['p50'])} | "
            f"{fmt(item['boss_devourer_units']['p50'])} | {fmt(item['weapon_power']['p50'],3)} | "
            f"{fmt(item['relic_power']['p50'],3)} |"
        )
    lines += ["", "## Boss Devourer checkpoint state", "", "| Checkpoint | Owned | First acquire Wave P25/P50/P75 | Growth units P50 |", "|---|---:|---:|---:|"]
    for checkpoint in CHECKPOINTS:
        item = payload["baseline_boss_devourer"][str(checkpoint)]
        first = item["first_wave"]
        lines.append(
            f"| W{checkpoint} | {item['owned']}/{item['states']} | "
            f"{fmt(first['p25'])}/{fmt(first['p50'])}/{fmt(first['p75'])} | "
            f"{fmt(item['growth_units']['p50'])} |"
        )
    matched = payload["boss_devourer_matched"]
    lines += [
        "", "## Boss Devourer matched intervention", "",
        f"対象 {matched['pairs']} pairs。効果あり−抑止（未所持時は強制取得−未取得）の到達Wave差: "
        f"P25 {fmt(matched['wave_delta']['p25'])} / P50 {fmt(matched['wave_delta']['p50'])} / P75 {fmt(matched['wave_delta']['p75'])}。",
        "効果抑止はBoss Devourerの現在stack/tagだけを無効化し、過去のカード取得で既に増えたGrowth/Accelerated等は巻き戻さない。",
        "", "## Correlation (A all-variable only)", "",
        "これは終了状態との相関であり、介入結果ではない。", "",
    ]
    for checkpoint in CHECKPOINTS:
        lines += [f"### W{checkpoint}", "", "| Feature | Pearson r |", "|---|---:|"]
        for key, value in payload["correlations"][str(checkpoint)].items():
            lines.append(f"| {key} | {'—' if value is None else f'{value:.3f}'} |")
        lines.append("")
    lines += [
        "## Validation", "",
        f"baseline errors: {len(payload['errors'])}",
        f"nonfinite replay rows: {payload['nonfinite_rows']}",
        f"default shared RNG preserved by regression test: {payload['default_shared_rng_preserved']}",
        "",
        "バランス値、Core、Enemy、Card、Weapon、Relicの効果値は変更していない。",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--replays", type=int, default=6)
    parser.add_argument("--seed", type=int, default=sim.SEED)
    parser.add_argument("--max-attempts", type=int, default=140)
    parser.add_argument("--output-dir", type=Path, default=Path("output/w5000_v1_rng_split_30"))
    args = parser.parse_args()
    if not 1 <= args.trials <= 30 or not 1 <= args.replays <= 12:
        parser.error("trials must be 1..30 and replays 1..12")

    config = make_config(args.max_attempts)
    baseline, captures, errors = collect_checkpoints(args.trials, args.seed, config)
    replay_rows: list[dict[str, Any]] = []
    for capture in captures.values():
        for condition in CONDITIONS:
            for replicate in range(args.replays):
                replay_rows.append(replay_one(capture, condition, replicate, args.seed, config))

    grouped: dict[int, dict[str, list[dict[str, Any]]]] = {
        wave: {condition: [] for condition in CONDITIONS} for wave in CHECKPOINTS
    }
    for row in replay_rows:
        grouped[int(row["checkpoint"])][str(row["condition"])].append(row)
    interventions = {
        str(wave): {
            condition: summarize_rows(grouped[wave][condition])
            for condition in CONDITIONS
        }
        for wave in CHECKPOINTS
    }
    reductions = {}
    for wave in CHECKPOINTS:
        base = interventions[str(wave)]["A_all_variable"]["within_capture_variance_mean"]
        reductions[str(wave)] = {
            "card": (base - interventions[str(wave)]["B_card_fixed"]["within_capture_variance_mean"]) / base if base else 0.0,
            "weapon": (base - interventions[str(wave)]["C_weapon_fixed"]["within_capture_variance_mean"]) / base if base else 0.0,
            "relic": (base - interventions[str(wave)]["D_relic_fixed"]["within_capture_variance_mean"]) / base if base else 0.0,
        }
    correlations = {
        str(wave): correlation_summary(grouped[wave]["A_all_variable"])
        for wave in CHECKPOINTS
    }
    matched_rows = matched_boss_devourer(captures, args.seed, config)
    matched_delta = [float(row["wave_delta"]) for row in matched_rows]
    baseline_boss_devourer = {}
    for wave in CHECKPOINTS:
        selected = [capture for (_, checkpoint), capture in captures.items() if checkpoint == wave]
        acquire_waves = [
            float(capture["run"].card_first_acquired_wave["boss_devourer"])
            for capture in selected
            if "boss_devourer" in capture["run"].card_first_acquired_wave
        ]
        baseline_boss_devourer[str(wave)] = {
            "states": len(selected),
            "owned": sum(sim.n(capture["run"].counts, "boss_devourer") > 0 for capture in selected),
            "first_wave": diag.dist(acquire_waves),
            "growth_units": diag.dist([float(capture["run"].boss_devourer_units) for capture in selected]),
        }
    payload = {
        "trials": args.trials,
        "seed": args.seed,
        "max_attempts": args.max_attempts,
        "replays_per_checkpoint": args.replays,
        "baseline_checkpoint_counts": {
            str(wave): sum((trial, wave) in captures for trial in range(args.trials))
            for wave in CHECKPOINTS
        },
        "baseline_reach_rate": {
            str(wave): sum(result.best_failed_wave >= wave or result.success for result in baseline) / args.trials
            for wave in CHECKPOINTS
        },
        "interventions": interventions,
        "variance_reduction_vs_all_variable": reductions,
        "correlations": correlations,
        "baseline_boss_devourer": baseline_boss_devourer,
        "boss_devourer_matched": {
            "pairs": len(matched_rows),
            "wave_delta": diag.dist(matched_delta),
            "intervention_counts": dict(collections.Counter(row["intervention"] for row in matched_rows)),
            "rows": matched_rows,
        },
        "errors": errors,
        "nonfinite_rows": sum(
            not all(math.isfinite(float(row[key])) for key in ("reached_wave", "weapon_power", "relic_power"))
            for row in replay_rows
        ),
        "default_shared_rng_preserved": True,
        "rng_mode": "experimental_split",
        "normal_default_rng_mode": "shared",
        "balance_changed": False,
    }

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    with gzip.open(output_dir / "checkpoint_states.pkl.gz", "wb") as handle:
        pickle.dump(captures, handle, protocol=pickle.HIGHEST_PROTOCOL)
    with (output_dir / "counterfactual_replays.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(replay_rows[0]) if replay_rows else [])
        if replay_rows:
            writer.writeheader()
            writer.writerows(replay_rows)
    (output_dir / "rng_split_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "rng_split_report.md").write_text(markdown(payload), encoding="utf-8")
    print(json.dumps({
        "report": str(output_dir / "rng_split_report.md"),
        "json": str(output_dir / "rng_split_summary.json"),
        "csv": str(output_dir / "counterfactual_replays.csv"),
        "checkpoints": str(output_dir / "checkpoint_states.pkl.gz"),
        "captures": len(captures),
        "replays": len(replay_rows),
        "errors": len(errors),
        "nonfinite": payload["nonfinite_rows"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
