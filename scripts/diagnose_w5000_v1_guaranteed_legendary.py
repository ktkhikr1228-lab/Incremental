#!/usr/bin/env python3
"""Diagnose W2500 guaranteed Legendary and post-W1500 run variance."""

from __future__ import annotations

import argparse
import collections
import dataclasses
import json
import math
import random
import statistics
from pathlib import Path
from typing import Any

import diagnose_w5000_v1_precore as diag
import simulate_first_prestige_v1 as sim
import w5000_v1_profile as profile


CHECKPOINTS = (1500, 1750, 2000, 2250, 2500, 2750, 3000, 5000)
CONDITIONS = ("guaranteed_on", "guaranteed_off")
CARD_RARITY = {item.key: item.rarity for item in sim.CARDS}


def make_configs(max_attempts: int) -> dict[str, sim.SimConfig]:
    common = {
        "max_attempts": max_attempts,
        "core_profile": "no_core",
    }
    return {
        name: dataclasses.replace(
            profile.build_config(
                **common,
                guaranteed_legendary=(name == "guaranteed_on"),
            ),
            diagnostic_checkpoints=CHECKPOINTS,
            dp_v01=sim.DPV01Config(enabled=True),
        )
        for name in CONDITIONS
    }


def execute(
    name: str, config: sim.SimConfig, trials: int, seed: int
) -> tuple[list[tuple[int, sim.TrialResult]], list[dict[str, object]]]:
    rows: list[tuple[int, sim.TrialResult]] = []
    errors: list[dict[str, object]] = []
    for trial in range(trials):
        try:
            rng = random.Random(seed + 1_000_000 + trial)
            rows.append((trial, sim.run_trial(rng, "balanced", config, allow_overdrive=True)))
        except Exception as exc:
            errors.append({"condition": name, "trial": trial, "type": type(exc).__name__, "message": str(exc)})
    return rows, errors


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    dx, dy = [x - mx for x in xs], [y - my for y in ys]
    denominator = math.sqrt(sum(value * value for value in dx) * sum(value * value for value in dy))
    if denominator <= 1e-15:
        return None
    return sum(a * b for a, b in zip(dx, dy)) / denominator


def post_w1500_states(rows: list[tuple[int, sim.TrialResult]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for trial, row in rows:
        first = next(
            (index for index, state in enumerate(row.run_end_states) if int(state["reached_wave"]) >= 1500),
            None,
        )
        if first is None:
            continue
        for attempt, state in enumerate(row.run_end_states[first:], start=first + 1):
            output.append({"trial": trial, "attempt": attempt, **state})
    return output


def reproducibility_summary(rows: list[tuple[int, sim.TrialResult]]) -> dict[str, Any]:
    subsequent: list[float] = []
    near_1500: list[float] = []
    reached_trials = 0
    for _, row in rows:
        first = next((i for i, wave in enumerate(row.run_reaches) if wave >= 1500), None)
        if first is None:
            continue
        reached_trials += 1
        later = [float(wave) for wave in row.run_reaches[first + 1:]]
        subsequent.extend(later)
        near_1500.extend(wave for wave in later if wave >= 1350)
    return {
        "trials_reaching_w1500": reached_trials,
        "subsequent_runs": len(subsequent),
        "subsequent_wave": diag.dist(subsequent),
        "subsequent_runs_reaching_w1350": len(near_1500),
        "near_reproduction_rate": len(near_1500) / len(subsequent) if subsequent else None,
    }


def feature_correlations(states: list[dict[str, object]]) -> dict[str, Any]:
    waves = [float(state["reached_wave"]) for state in states]
    numeric_keys = (
        "normal_power", "boss_power", "base_attack_power", "all_damage", "attack_speed",
        "xp_multiplier", "crit_rate", "crit_multiplier", "follow_up_rate", "card_count",
        "weapon_power", "weapon_origin_wave", "relic_power", "relic_quality", "relic_types",
    )
    numeric = {
        key: pearson(
            [float(state[key] or 0.0) for state in states],
            waves,
        )
        for key in numeric_keys
    }
    rarity = {
        rarity: pearson(
            [float(dict(state["rarity_composition"]).get(rarity, 0)) for state in states],
            waves,
        )
        for rarity in sim.RARITY_ORDER
    }
    card_keys = sorted({
        key for state in states for key in dict(state["cards"])
    })
    cards: list[dict[str, object]] = []
    for key in card_keys:
        stacks = [float(dict(state["cards"]).get(key, 0)) for state in states]
        owned = [wave for wave, stack in zip(waves, stacks) if stack > 0]
        absent = [wave for wave, stack in zip(waves, stacks) if stack <= 0]
        cards.append({
            "key": key,
            "rarity": CARD_RARITY.get(key),
            "owned_runs": len(owned),
            "stack_correlation": pearson(stacks, waves),
            "owned_wave_p50": diag.dist(owned)["p50"] if owned else None,
            "absent_wave_p50": diag.dist(absent)["p50"] if absent else None,
            "owned_minus_absent_p50": (
                diag.dist(owned)["p50"] - diag.dist(absent)["p50"] if owned and absent else None
            ),
        })
    cards.sort(
        key=lambda item: abs(float(item["stack_correlation"])) if item["stack_correlation"] is not None else -1,
        reverse=True,
    )
    weapon_groups: dict[str, list[float]] = collections.defaultdict(list)
    for state in states:
        weapon_groups[str(state["weapon_rarity"] or "none")].append(float(state["reached_wave"]))
    return {
        "runs": len(states),
        "numeric_correlations": numeric,
        "rarity_correlations": rarity,
        "top_card_correlations": cards[:20],
        "all_card_correlations": cards,
        "weapon_rarity_wave": {
            key: {"runs": len(values), **diag.dist(values)} for key, values in sorted(weapon_groups.items())
        },
    }


def summarize(
    rows: list[tuple[int, sim.TrialResult]], errors: list[dict[str, object]], trials: int
) -> dict[str, Any]:
    checkpoints: dict[str, Any] = {}
    nonfinite: list[dict[str, object]] = []
    for wave in CHECKPOINTS:
        reached = [(trial, row) for trial, row in rows if wave in row.reach_seconds]
        states = [row.first_reach_checkpoint_states[wave] for _, row in reached]
        checkpoints[str(wave)] = {
            "reached": len(reached),
            "reach_rate": len(reached) / trials,
            "state": diag.numeric_state_summary(states),
        }
    w2500_groups: dict[str, list[dict[str, object]]] = collections.defaultdict(list)
    for trial, row in rows:
        state = row.first_reach_checkpoint_states.get(2500)
        if state is None:
            continue
        card = str(state.get("guaranteed_card") or "none")
        w2500_groups[card].append({
            "trial": trial,
            "immediate_power_delta": state.get("guaranteed_card_immediate_power_delta", 0.0),
            "margin": state.get("margin_power"),
            "w5000_success": row.success,
            "infinite_barrage": card == "infinite_barrage",
        })
    card_results = {}
    for key, values in sorted(w2500_groups.items()):
        card_results[key] = {
            "trials": len(values),
            "immediate_power_delta": diag.dist([float(item["immediate_power_delta"]) for item in values]),
            "w2500_margin": diag.dist([float(item["margin"]) for item in values]),
            "w5000_successes": sum(bool(item["w5000_success"]) for item in values),
            "trial_ids": [int(item["trial"]) for item in values],
        }
    infinite_trials = set()
    infinite_runs = 0
    for trial, row in rows:
        count = sum(bool(dict(state["cards"]).get("infinite_barrage", 0)) for state in row.run_end_states)
        if count:
            infinite_trials.add(trial)
            infinite_runs += count
        for attempt, state in enumerate(row.run_end_states, start=1):
            for key in ("normal_power", "boss_power", "attack_speed", "xp_multiplier", "crit_rate", "crit_multiplier"):
                value = float(state[key])
                if not math.isfinite(value):
                    nonfinite.append({"trial": trial, "attempt": attempt, "field": key, "value": value})
    states = post_w1500_states(rows)
    pre_w2500_states = [state for state in states if int(state["reached_wave"]) < 2500]
    return {
        "completed_trials": len(rows),
        "successes": sum(row.success for _, row in rows),
        "checkpoints": checkpoints,
        "w2500_card_results": card_results,
        "infinite_barrage": {
            "trials_with_any": len(infinite_trials),
            "run_end_states_with_card": infinite_runs,
            "trial_ids": sorted(infinite_trials),
        },
        "post_w1500": feature_correlations(states),
        "post_w1500_pre_w2500": feature_correlations(pre_w2500_states),
        "w1500_reproducibility": reproducibility_summary(rows),
        "trial_run_waves": {
            str(trial): list(row.run_reaches) for trial, row in rows
        },
        "nonfinite": nonfinite,
        "errors": errors,
    }


def f(value: float | None, digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# w5000_v1 W2500 Guaranteed Legendary診断",
        "",
        f"DP v0.1 BC / paired {payload['trials']} trials / seed {payload['seed']} / max 140 runs / Coreなし",
        "",
        "| Condition | W2250 | W2500 | W2750 | W3000 | W5000 | W2500 Margin P50 | W2500 immediate ΔPower P50 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in CONDITIONS:
        x = payload["conditions"][name]
        def cp(wave: int) -> dict[str, Any]:
            return x["checkpoints"][str(wave)]
        margin = cp(2500)["state"].get("margin_power", {}).get("p50")
        delta = cp(2500)["state"].get("guaranteed_card_immediate_power_delta", {}).get("p50")
        lines.append(
            f"| {name} | {cp(2250)['reach_rate']:.1%} | {cp(2500)['reach_rate']:.1%} | "
            f"{cp(2750)['reach_rate']:.1%} | {cp(3000)['reach_rate']:.1%} | {x['successes']/payload['trials']:.1%} | "
            f"{f(margin)} | {f(delta)} |"
        )
    lines += ["", "## W2500取得カード別", ""]
    for name in CONDITIONS:
        lines += [f"### {name}", "", "| Card | trials | immediate ΔPower P50 | Margin P50 | W5000 success |", "|---|---:|---:|---:|---:|"]
        for key, item in payload["conditions"][name]["w2500_card_results"].items():
            lines.append(
                f"| {key} | {item['trials']} | {f(item['immediate_power_delta']['p50'])} | "
                f"{f(item['w2500_margin']['p50'])} | {item['w5000_successes']} |"
            )
        lines.append("")
    lines += ["## W1500以降Run相関（guaranteed_on baseline）", ""]
    analysis = payload["conditions"]["guaranteed_on"]["post_w1500_pre_w2500"]
    lines += ["W2500保証の影響を除くため、W1500以上・W2500未満のRunだけを使用。", ""]
    lines += ["| Feature | Pearson r |", "|---|---:|"]
    for key, value in sorted(
        analysis["numeric_correlations"].items(),
        key=lambda item: abs(item[1]) if item[1] is not None else -1,
        reverse=True,
    ):
        lines.append(f"| {key} | {f(value, 3)} |")
    lines += ["", "### 主要カード", "", "| Card | Rarity | runs | stack r | owned-minus-absent Wave P50 |", "|---|---:|---:|---:|---:|"]
    for item in analysis["top_card_correlations"][:15]:
        lines.append(
            f"| {item['key']} | {item['rarity']} | {item['owned_runs']} | "
            f"{f(item['stack_correlation'],3)} | {f(item['owned_minus_absent_p50'],1)} |"
        )
    lines += ["", "### Run再現性", "", "| Condition | W1500到達trial | 以後のRun数 | 次Run群Wave P50 | W1350以上再現率 |", "|---|---:|---:|---:|---:|"]
    for name in CONDITIONS:
        item = payload["conditions"][name]["w1500_reproducibility"]
        rate = item["near_reproduction_rate"]
        lines.append(
            f"| {name} | {item['trials_reaching_w1500']} | {item['subsequent_runs']} | "
            f"{f(item['subsequent_wave']['p50'], 1)} | {f(rate * 100 if rate is not None else None, 1)}% |"
        )
    lines += ["", "### Rarity相関（同区間）", "", "| Rarity | stack数と到達Waveのr |", "|---|---:|"]
    for rarity, value in analysis["rarity_correlations"].items():
        lines.append(f"| {rarity} | {f(value, 3)} |")
    lines += ["", "### Weapon rarity別到達Wave（同区間）", "", "| Rarity | runs | Wave P25/P50/P75 |", "|---|---:|---:|"]
    for rarity, item in analysis["weapon_rarity_wave"].items():
        lines.append(
            f"| {rarity} | {item['runs']} | {f(item['p25'],1)} / {f(item['p50'],1)} / {f(item['p75'],1)} |"
        )
    lines += [
        "",
        "相関はRun終了時点の状態との関連であり、到達した結果カード枚数が増えた逆因果を含む。因果効果とは扱わない。",
        "独立したCard/Weapon RNG streamが現シミュレーターにないため、同一恒久状態から要素別に固定する仮想再生は今回は未実施。",
        "",
        f"paired prefix W2250一致: {payload['paired_invariants']['w2250_prefix_match']}",
        f"non-guarantee config一致: {payload['paired_invariants']['non_guarantee_config_match']}",
        f"nonfinite/errors: {payload['nonfinite_count']}/{payload['error_count']}",
        "",
        "カード・DP・Core・Enemy・Weapon・Relicの数値変更および正式採用は行っていない。",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--seed", type=int, default=sim.SEED)
    parser.add_argument("--max-attempts", type=int, default=140)
    parser.add_argument("--output-dir", type=Path, default=Path("output/w5000_v1_guaranteed_legendary_30"))
    args = parser.parse_args()
    if not 1 <= args.trials <= 30:
        parser.error("guaranteed Legendary diagnosis is limited to 1-30 trials")
    cfgs = make_configs(args.max_attempts)
    rows: dict[str, list[tuple[int, sim.TrialResult]]] = {}
    errors: dict[str, list[dict[str, object]]] = {}
    for name in CONDITIONS:
        rows[name], errors[name] = execute(name, cfgs[name], args.trials, args.seed)

    normalized = []
    for name in CONDITIONS:
        values = dataclasses.asdict(cfgs[name])
        values.pop("disabled_guaranteed_choice_waves")
        normalized.append(values)
    prefix_mismatch = []
    by_condition = {name: dict(rows[name]) for name in CONDITIONS}
    for trial in range(args.trials):
        if trial not in by_condition["guaranteed_on"] or trial not in by_condition["guaranteed_off"]:
            continue
        a, b = by_condition["guaranteed_on"][trial], by_condition["guaranteed_off"][trial]
        if (2250 in a.reach_seconds) != (2250 in b.reach_seconds) or a.reach_seconds.get(2250) != b.reach_seconds.get(2250):
            prefix_mismatch.append(trial)
    summaries = {
        name: summarize(rows[name], errors[name], args.trials) for name in CONDITIONS
    }
    payload = {
        "trials": args.trials,
        "seed": args.seed,
        "max_attempts": args.max_attempts,
        "conditions": summaries,
        "paired_invariants": {
            "same_seed_formula": "seed + 1_000_000 + trial_index",
            "non_guarantee_config_match": normalized[0] == normalized[1],
            "w2250_prefix_match": not prefix_mismatch,
            "prefix_mismatch_trials": prefix_mismatch,
        },
        "nonfinite_count": sum(len(summaries[name]["nonfinite"]) for name in CONDITIONS),
        "error_count": sum(len(summaries[name]["errors"]) for name in CONDITIONS),
        "virtual_replay": {
            "performed": False,
            "reason": "Card and Weapon currently share one RNG stream; causal component freezing would require a new RNG architecture.",
        },
        "balance_changed": False,
        "automatic_adoption": False,
    }
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "w5000_v1_guaranteed_legendary.json"
    md_path = output_dir / "w5000_v1_guaranteed_legendary.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(markdown(payload), encoding="utf-8")
    print(json.dumps({
        "json": str(json_path), "markdown": str(md_path),
        "paired_invariants": payload["paired_invariants"],
        "nonfinite": payload["nonfinite_count"], "errors": payload["error_count"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
