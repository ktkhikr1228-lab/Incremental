#!/usr/bin/env python3
"""Diagnose W1500-W2000 card/reroll divergence without balance changes."""

from __future__ import annotations

import argparse
import collections
import copy
import csv
import dataclasses
import json
import math
import random
import statistics
from pathlib import Path
from typing import Any

import diagnose_w5000_v1_old_vs_v2_midgame as previous
import diagnose_w5000_v1_precore as diag
import simulate_first_prestige_v1 as sim


CHECKPOINTS = (1000, 1250, 1500, 1750, 2000)
CARD_KEYS = (
    "escalation", "boss_devourer", "steady_force", "rapid_fire",
    "power_up", "critical_momentum",
)
RARITY_RANK = {key: index for index, key in enumerate(sim.RARITY_ORDER)}


def rarity_counts(run: sim.RunState) -> dict[str, int]:
    result = collections.Counter()
    for key, count in run.counts.items():
        card = sim.CARD_BY_KEY.get(key)
        if card is not None and count > 0:
            result[card.rarity] += count
    return {rarity: int(result[rarity]) for rarity in sim.RARITY_ORDER}


def hand_rarity(keys: list[str]) -> str:
    values = [sim.CARD_BY_KEY[key].rarity for key in keys if key in sim.CARD_BY_KEY]
    return max(values, key=lambda rarity: RARITY_RANK[rarity]) if values else "?"


def checkpoint_row(trial: int, success: bool, wave: int, capture: dict[str, Any],
                   config: sim.SimConfig, decisions: list[dict[str, Any]]) -> dict[str, Any]:
    run, permanent = capture["run"], capture["permanent"]
    snapshot = sim.compute_snapshot(run, permanent, wave % 10 == 0, config)
    attempt = int(capture["attempt"])
    draft_rows = sorted(
        (
            row for row in decisions
            if int(row.get("attempt", -1)) == attempt
            and row.get("phase") == "xp"
            and int(row.get("next_wave", 0)) <= wave
        ),
        key=lambda row: int(row.get("decision_index", 0)),
    )
    longest, streak = 0, 0
    for row in draft_rows:
        traces = row.get("reroll_trace") or []
        saw_rare_plus = any(
            RARITY_RANK.get(hand_rarity(list(trace.get("hand", []))), -1)
            >= RARITY_RANK["R"]
            for trace in traces
        )
        if saw_rare_plus:
            streak = 0
        else:
            streak += 1
            longest = max(longest, streak)
    rarity = rarity_counts(run)
    rare_first = [
        acquire_wave for key, acquire_wave in run.card_first_acquired_wave.items()
        if key in sim.CARD_BY_KEY and RARITY_RANK[sim.CARD_BY_KEY[key].rarity] >= RARITY_RANK["R"]
    ]
    epic_first = [
        acquire_wave for key, acquire_wave in run.card_first_acquired_wave.items()
        if key in sim.CARD_BY_KEY and RARITY_RANK[sim.CARD_BY_KEY[key].rarity] >= RARITY_RANK["E"]
    ]
    row: dict[str, Any] = {
        "trial": trial, "group": "success10" if success else "failure20",
        "wave": wave, "attempt": attempt,
        "rare_plus_drought": longest,
        "rare_plus_count": sum(rarity[key] for key in ("R", "E", "L")),
        "rare_first_wave": min(rare_first) if rare_first else None,
        "epic_first_wave": min(epic_first) if epic_first else None,
        "dp_power": snapshot.dp_power,
        "base_attack_power": snapshot.base_attack_power,
        "attack_speed": snapshot.attack_speed,
        "weapon_power": snapshot.weapon_power,
        "relic_power": snapshot.relic_power,
        "card_count": run.card_count,
        "player_power": snapshot.log_dps,
        "enemy_power": sim.configured_enemy_power(wave, config),
        "margin": snapshot.log_dps - sim.configured_enemy_power(wave, config),
        "dp_levels": copy.deepcopy(permanent.dp_v01_levels),
        "rarity": rarity,
    }
    for key in CARD_KEYS:
        row[f"{key}_stack"] = int(run.counts.get(key, 0))
        row[f"{key}_first"] = run.card_first_acquired_wave.get(key)
    return row


def collect(trials: int, seed: int):
    config = dataclasses.replace(
        previous.make_pre_config(),
        diagnostic_infinite_barrage_mode="v2_fixed_ratio",
        diagnostic_checkpoints=CHECKPOINTS + (2500,),
    )
    results: dict[int, sim.TrialResult] = {}
    captures: dict[tuple[int, int], dict[str, Any]] = {}
    decisions: dict[int, list[dict[str, Any]]] = {}
    errors = []
    old_enabled = sim.TAKE_BRANCH_ENABLED
    old_rows = list(sim.TAKE_BRANCH_ROWS)
    old_context = copy.deepcopy(sim.TAKE_BRANCH_CONTEXT)
    try:
        sim.TAKE_BRANCH_ENABLED = True
        for trial in range(trials):
            sim.TAKE_BRANCH_ROWS.clear()
            sim.TAKE_BRANCH_CONTEXT.clear()
            sim.TAKE_BRANCH_CONTEXT.update({
                "seed": seed, "trial_index": trial, "profile": "balanced",
            })
            streams = sim.make_split_rng_streams(seed, trial)

            def capture(attempt, wave, run, permanent, live_streams, *, _trial=trial):
                captures.setdefault((_trial, wave), {
                    "trial": _trial, "wave": wave, "attempt": attempt,
                    "run": copy.deepcopy(run), "permanent": copy.deepcopy(permanent),
                    "rng_states": {
                        name: copy.deepcopy(getattr(live_streams, name).getstate())
                        for name in ("card", "weapon", "relic", "combat")
                    },
                })

            try:
                results[trial] = sim.run_trial(
                    streams.combat, "balanced", config, True,
                    rng_streams=streams, attempt_checkpoint_capture=capture,
                )
                decisions[trial] = copy.deepcopy(sim.TAKE_BRANCH_ROWS)
            except Exception as exc:
                errors.append({"trial": trial, "type": type(exc).__name__, "message": str(exc)})
    finally:
        sim.TAKE_BRANCH_ENABLED = old_enabled
        sim.TAKE_BRANCH_ROWS[:] = old_rows
        sim.TAKE_BRANCH_CONTEXT.clear()
        sim.TAKE_BRANCH_CONTEXT.update(old_context)
    success_ids = {trial for trial, result in results.items() if result.success}
    checkpoint_rows = []
    for (trial, wave), capture in captures.items():
        if wave in CHECKPOINTS:
            checkpoint_rows.append(checkpoint_row(
                trial, trial in success_ids, wave, capture, config, decisions[trial]
            ))
    return config, results, captures, decisions, checkpoint_rows, success_ids, errors


def dist(values: list[float]) -> dict[str, Any]:
    return diag.dist([float(value) for value in values]) if values else {
        "count": 0, "p25": None, "p50": None, "p75": None, "min": None, "max": None,
    }


def summarize_checkpoints(rows: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = (
        "rare_plus_drought", "rare_plus_count", "rare_first_wave", "epic_first_wave",
        "dp_power", "base_attack_power", "attack_speed", "weapon_power", "relic_power",
        "card_count", "player_power", "margin",
    )
    summary: dict[str, Any] = {}
    for wave in CHECKPOINTS:
        summary[str(wave)] = {}
        for group in ("success10", "failure20"):
            selected = [row for row in rows if row["wave"] == wave and row["group"] == group]
            item = {"states": len(selected)}
            for metric in metrics:
                values = [row[metric] for row in selected if row[metric] is not None]
                item[metric] = dist(values)
                if metric in {"rare_first_wave", "epic_first_wave"}:
                    item[f"{metric}_owned_rate"] = len(values) / len(selected) if selected else None
            item["rarity"] = {
                rarity: dist([row["rarity"][rarity] for row in selected])
                for rarity in sim.RARITY_ORDER
            }
            dp_keys = sorted({key for row in selected for key in row["dp_levels"]})
            item["dp_levels"] = {
                key: dist([row["dp_levels"].get(key, 0) for row in selected]) for key in dp_keys
            }
            item["cards"] = {}
            for key in CARD_KEYS:
                first_values = [row[f"{key}_first"] for row in selected if row[f"{key}_first"] is not None]
                item["cards"][key] = {
                    "stack": dist([row[f"{key}_stack"] for row in selected]),
                    "owned_rate": sum(row[f"{key}_stack"] > 0 for row in selected) / len(selected)
                    if selected else None,
                    "first_wave": dist(first_values),
                }
            summary[str(wave)][group] = item
    return summary


def reroll_summary(decisions: dict[int, list[dict[str, Any]]], success_ids: set[int]):
    raw = []
    trial_summary = []
    for trial, rows in decisions.items():
        selected = [
            row for row in rows
            if row.get("phase") == "xp" and 1000 <= int(row.get("next_wave", 0)) <= 2000
        ]
        events = []
        for row in selected:
            traces = row.get("reroll_trace") or []
            if int(row.get("rerolls_used", 0)) <= 0 or len(traces) < 2:
                continue
            initial, final = traces[0], traces[-1]
            event = {
                "trial": trial, "group": "success10" if trial in success_ids else "failure20",
                "attempt": int(row.get("attempt", 0)), "wave": int(row.get("next_wave", 0)),
                "rerolls_used": int(row.get("rerolls_used", 0)),
                "initial_rarity": hand_rarity(list(initial.get("hand", []))),
                "final_rarity": hand_rarity(list(final.get("hand", []))),
                "selected_card": row.get("selected_card"),
                "selected_rarity": sim.CARD_BY_KEY[row["selected_card"]].rarity
                if row.get("selected_card") in sim.CARD_BY_KEY else None,
                "exhausted": final.get("stop_reason") == "exhausted",
                "initial_hand": list(initial.get("hand", [])),
                "final_hand": list(final.get("hand", [])),
            }
            event["rare_plus_from_reroll"] = (
                RARITY_RANK.get(event["initial_rarity"], -1) < RARITY_RANK["R"]
                and event["selected_rarity"] is not None
                and RARITY_RANK[event["selected_rarity"]] >= RARITY_RANK["R"]
            )
            raw.append(event)
            events.append(event)
        attempts = {int(row.get("attempt", 0)) for row in selected}
        exhausted_waves = [event["wave"] for event in events if event["exhausted"]]
        trial_summary.append({
            "trial": trial, "group": "success10" if trial in success_ids else "failure20",
            "uses": sum(event["rerolls_used"] for event in events),
            "uses_per_run": sum(event["rerolls_used"] for event in events) / len(attempts) if attempts else 0.0,
            "rare_plus_from_reroll": sum(event["rare_plus_from_reroll"] for event in events),
            "exhausted_events": len(exhausted_waves),
            "first_exhausted_wave": min(exhausted_waves) if exhausted_waves else None,
        })
    summary = {}
    for group in ("success10", "failure20"):
        rows = [row for row in trial_summary if row["group"] == group]
        events = [row for row in raw if row["group"] == group]
        transitions = collections.Counter(
            f"{row['initial_rarity']}→{row['final_rarity']}" for row in events
        )
        summary[group] = {
            metric: dist([row[metric] for row in rows if row[metric] is not None])
            for metric in ("uses", "uses_per_run", "rare_plus_from_reroll", "exhausted_events", "first_exhausted_wave")
        }
        summary[group]["transitions"] = dict(transitions)
        summary[group]["event_count"] = len(events)
    return summary, raw, trial_summary


def standardized_distance(left: dict[str, Any], right: dict[str, Any]) -> float:
    features = (
        ("dp_power", False), ("base_attack_power", False), ("attack_speed", True),
        ("weapon_power", False), ("relic_power", False), ("card_count", False),
    )
    total = 0.0
    for key, use_log in features:
        a, b = float(left[key]), float(right[key])
        if use_log:
            a, b = math.log10(max(a, 1e-12)), math.log10(max(b, 1e-12))
        total += (a - b) ** 2
    return math.sqrt(total)


def closest_pairs(rows: list[dict[str, Any]], wave: int, limit: int = 4):
    success = [row for row in rows if row["wave"] == wave and row["group"] == "success10"]
    failure = [row for row in rows if row["wave"] == wave and row["group"] == "failure20"]
    candidates = sorted(
        (standardized_distance(a, b), a["trial"], b["trial"])
        for a in success for b in failure
    )
    used_a, used_b, output = set(), set(), []
    for distance, a, b in candidates:
        if a in used_a or b in used_b:
            continue
        used_a.add(a); used_b.add(b)
        output.append({"success_trial": a, "failure_trial": b, "distance": distance})
        if len(output) >= limit:
            break
    return output


def replay_streams(capture: dict[str, Any], seed: int, replicate: int,
                   fixed: frozenset[str]) -> sim.RNGStreams:
    branch = int(capture["trial"]) * 100_000 + int(capture["wave"]) * 10 + replicate
    fixed_branch = int(capture["trial"]) * 100_000 + int(capture["wave"]) * 10
    detail = []
    for name in ("rarity", "hand", "reroll"):
        selected = fixed_branch if name in fixed else branch
        detail.append(random.Random(sim.derived_rng_seed(seed, f"midgame:{name}", selected)))
    outer = {}
    for name in ("card", "weapon", "relic", "combat"):
        rng = random.Random(); rng.setstate(capture["rng_states"][name]); outer[name] = rng
    return sim.RNGStreams(
        outer["card"], outer["weapon"], outer["relic"], outer["combat"],
        sim.CardRNGStreams(*detail),
    )


def counterfactual(captures: dict[tuple[int, int], dict[str, Any]], pairs_by_wave: dict[int, list[dict]],
                   config: sim.SimConfig, seed: int, replicates: int = 6):
    conditions = {
        "all_variable": frozenset(),
        "rarity_fixed": frozenset({"rarity"}),
        "reroll_fixed": frozenset({"reroll"}),
    }
    rows, errors = [], []
    selected_ids = {
        (wave, trial)
        for wave, pairs in pairs_by_wave.items()
        for pair in pairs
        for trial in (pair["success_trial"], pair["failure_trial"])
    }
    for wave, trial in sorted(selected_ids):
        capture = captures[(trial, wave)]
        for condition, fixed in conditions.items():
            for replicate in range(replicates):
                try:
                    run = copy.deepcopy(capture["run"])
                    permanent = copy.deepcopy(capture["permanent"])
                    streams = replay_streams(capture, seed, replicate, fixed)
                    result = sim.run_once(
                        streams.combat, "balanced", permanent, config, True,
                        target_wave=2250, initial_run=run, start_wave=wave + 1,
                        rng_streams=streams,
                    )
                    rows.append({
                        "checkpoint": wave, "trial": trial,
                        "source_group": "success10" if any(
                            pair["success_trial"] == trial for pair in pairs_by_wave[wave]
                        ) else "failure20",
                        "condition": condition, "replicate": replicate,
                        "reached_wave": result.reached,
                    })
                except Exception as exc:
                    errors.append({
                        "checkpoint": wave, "trial": trial, "condition": condition,
                        "replicate": replicate, "type": type(exc).__name__, "message": str(exc),
                    })
    summary = {}
    for wave in sorted(pairs_by_wave):
        summary[str(wave)] = {}
        for group in ("success10", "failure20"):
            summary[str(wave)][group] = {}
            for condition in conditions:
                values = [
                    row["reached_wave"] for row in rows
                    if row["checkpoint"] == wave and row["source_group"] == group
                    and row["condition"] == condition
                ]
                by_state = collections.defaultdict(list)
                for row in rows:
                    if row["checkpoint"] == wave and row["source_group"] == group and row["condition"] == condition:
                        by_state[row["trial"]].append(row["reached_wave"])
                within = [statistics.pvariance(value) for value in by_state.values() if len(value) > 1]
                summary[str(wave)][group][condition] = {
                    "reached": dist(values),
                    "within_state_variance_mean": statistics.fmean(within) if within else 0.0,
                    "reach_1750": sum(value >= 1750 for value in values) / len(values) if values else None,
                    "reach_2000": sum(value >= 2000 for value in values) / len(values) if values else None,
                    "reach_2250": sum(value >= 2250 for value in values) / len(values) if values else None,
                }
    return summary, rows, errors


def markdown(payload: dict[str, Any]) -> str:
    def f(value, digits=2): return "—" if value is None else f"{value:.{digits}f}"
    def trip(item): return f"{f(item['p25'])}/{f(item['p50'])}/{f(item['p75'])}"
    lines = [
        "# W1500-2000 card divergence diagnosis", "",
        f"30 trials / seed {payload['seed']} / W2500 reached {payload['success_count']} / not reached {payload['failure_count']}",
        "", "Rare+ droughtは、同一RunのXP draftで初期手札とreroll後手札のどこにもR/E/Lが出ない連続回数。", "",
        "## Rarity and controls", "",
        "| W | Group (N) | Rare+ drought | Rare+ count | Rare first Wave | Epic first Wave | DP Power | Base ATK Power | AS | Weapon | Relic | Cards | Margin |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for wave in CHECKPOINTS:
        for group in ("success10", "failure20"):
            item = payload["checkpoints"][str(wave)][group]
            lines.append(
                f"| {wave} | {group} ({item['states']}) | {trip(item['rare_plus_drought'])} | "
                f"{trip(item['rare_plus_count'])} | {trip(item['rare_first_wave'])} | "
                f"{trip(item['epic_first_wave'])} | {trip(item['dp_power'])} | "
                f"{trip(item['base_attack_power'])} | {trip(item['attack_speed'])} | "
                f"{trip(item['weapon_power'])} | {trip(item['relic_power'])} | "
                f"{trip(item['card_count'])} | {trip(item['margin'])} |"
            )
    lines += ["", "## DP category Lv", "", "| W | Group | ATK | AS | XP | Crit Rate | Crit Mult | Weapon ATK | Luck | Weapon Find |", "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    dp_keys = ("base_atk", "attack_speed", "xp_gain", "crit_rate", "crit_multiplier", "weapon_atk", "luck", "weapon_find")
    for wave in (1000, 1250, 1500):
        for group in ("success10", "failure20"):
            values = payload["checkpoints"][str(wave)][group]["dp_levels"]
            cells = [f(values[key]["p50"]) if key in values else "—" for key in dp_keys]
            lines.append(f"| {wave} | {group} | " + " | ".join(cells) + " |")
    lines += ["", "## Target card stacks", ""]
    for wave in (1500, 1750, 2000):
        lines += [f"### W{wave}", "", "| Card | Success stack | Failure stack | Success first | Failure first |", "|---|---:|---:|---:|---:|"]
        for key in CARD_KEYS:
            a = payload["checkpoints"][str(wave)]["success10"]["cards"][key]
            b = payload["checkpoints"][str(wave)]["failure20"]["cards"][key]
            lines.append(f"| {key} | {trip(a['stack'])} | {trip(b['stack'])} | {trip(a['first_wave'])} | {trip(b['first_wave'])} |")
        lines.append("")
    lines += [
        "## Reroll W1000-2000", "",
        "Rerollは現実装ではRun全体の有限券ではなく、各draftごとに1回（買い切り後2回）再付与される。`exhausted`はそのdraft内の上限消費。", "",
        "| Group | Uses/trial | Uses/run | Rare+ obtained | Exhausted events | First exhausted Wave |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for group in ("success10", "failure20"):
        item = payload["reroll"][group]
        lines.append(
            f"| {group} | {trip(item['uses'])} | {trip(item['uses_per_run'])} | "
            f"{trip(item['rare_plus_from_reroll'])} | {trip(item['exhausted_events'])} | "
            f"{trip(item['first_exhausted_wave'])} |"
        )
    lines += ["", "## Closest-state counterfactual", ""]
    for wave in (1250, 1500):
        lines += [f"### W{wave}", "", "| Group | Condition | Reached P25/P50/P75 | Within-state variance | W1750 | W2000 | W2250 |", "|---|---|---:|---:|---:|---:|---:|"]
        for group in ("success10", "failure20"):
            for condition in ("all_variable", "rarity_fixed", "reroll_fixed"):
                item = payload["counterfactual"][str(wave)][group][condition]
                lines.append(
                    f"| {group} | {condition} | {trip(item['reached'])} | "
                    f"{item['within_state_variance_mean']:.1f} | {item['reach_1750']:.1%} | "
                    f"{item['reach_2000']:.1%} | {item['reach_2250']:.1%} |"
                )
        lines.append("")
    lines += [
        "## Interpretation", "",
        *[f"- {line}" for line in payload["interpretation"]], "",
        "## Validation", "",
        f"errors/nonfinite: {len(payload['errors'])}/{payload['nonfinite']}",
        f"same success IDs as prior 30-trial prefix: {payload['matches_prior_success_ids']}",
        "balance changed: false", "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--seed", type=int, default=sim.SEED)
    parser.add_argument("--replays", type=int, default=6)
    parser.add_argument("--output-dir", type=Path, default=Path("output/w5000_v1_midgame_card_divergence_30"))
    args = parser.parse_args()
    config, results, captures, decisions, rows, success_ids, errors = collect(args.trials, args.seed)
    checkpoint_summary = summarize_checkpoints(rows)
    reroll, reroll_events, reroll_trials = reroll_summary(decisions, success_ids)
    pairs = {wave: closest_pairs(rows, wave) for wave in (1250, 1500)}
    cf_summary, cf_rows, cf_errors = counterfactual(
        captures, pairs, config, args.seed, args.replays
    )
    errors.extend(cf_errors)
    prior_path = Path("output/w5000_v1_old_vs_v2_midgame_30_final/old_vs_v2_midgame_summary.json")
    prior_success = set()
    if prior_path.exists():
        prior = json.loads(prior_path.read_text(encoding="utf-8"))
        prior_success = {
            int(row["trial"]) for row in prior["profiles"]["B_barrage_v2_fixed_ratio"]["trial_rows"]
            if row["w2500"]
        }
    # The labels below are descriptive diagnostics, not causal claims.
    interpretation = [
        "W1000/W1250は両群が全件到達しているため、この時点の差は『遠くまで行った結果』ではない。",
        "W1750/W2000のfailure群集計は到達者だけなので、生存者選別を含み、原因候補としては弱い。",
        "counterfactualは近い恒久/戦闘state上でCard内部RNGだけを分離した小標本。相関表と因果介入を混同しない。",
    ]
    payload = {
        "seed": args.seed, "trials": args.trials,
        "success_count": len(success_ids), "failure_count": len(results) - len(success_ids),
        "success_trial_ids": sorted(success_ids),
        "checkpoints": checkpoint_summary,
        "reroll": reroll,
        "reroll_events": reroll_events,
        "reroll_trial_summary": reroll_trials,
        "matched_pairs": pairs,
        "counterfactual": cf_summary,
        "interpretation": interpretation,
        "errors": errors,
        "nonfinite": sum(
            not math.isfinite(float(row["reached_wave"])) for row in cf_rows
        ),
        "matches_prior_success_ids": success_ids == prior_success,
        "balance_changed": False,
    }
    output = args.output_dir.resolve(); output.mkdir(parents=True, exist_ok=True)
    (output / "midgame_card_divergence.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "midgame_card_divergence.md").write_text(markdown(payload), encoding="utf-8")
    with (output / "checkpoint_rows.csv").open("w", newline="", encoding="utf-8") as handle:
        flat = []
        for row in rows:
            item = row.copy()
            for key in ("dp_levels", "rarity"):
                item[key] = json.dumps(item[key], ensure_ascii=False, separators=(",", ":"))
            flat.append(item)
        writer = csv.DictWriter(handle, fieldnames=list(flat[0]) if flat else [])
        writer.writeheader(); writer.writerows(flat)
    with (output / "reroll_events.csv").open("w", newline="", encoding="utf-8") as handle:
        flat = []
        for row in reroll_events:
            item = row.copy()
            item["initial_hand"] = ",".join(item["initial_hand"])
            item["final_hand"] = ",".join(item["final_hand"])
            flat.append(item)
        writer = csv.DictWriter(handle, fieldnames=list(flat[0]) if flat else [])
        writer.writeheader(); writer.writerows(flat)
    with (output / "counterfactual_rows.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(cf_rows[0]) if cf_rows else [])
        writer.writeheader(); writer.writerows(cf_rows)
    print(json.dumps({
        "report": str(output / "midgame_card_divergence.md"),
        "json": str(output / "midgame_card_divergence.json"),
        "success": len(success_ids), "failure": len(results) - len(success_ids),
        "matches_prior": success_ids == prior_success,
        "errors": len(errors), "nonfinite": payload["nonfinite"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
