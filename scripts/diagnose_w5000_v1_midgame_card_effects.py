#!/usr/bin/env python3
"""Matched checkpoint-state replay for W1250-W2500 card effects."""

from __future__ import annotations

import argparse
import collections
import copy
import csv
import dataclasses
import json
import math
import statistics
from pathlib import Path
from typing import Any

import diagnose_w5000_v1_old_vs_v2_midgame as previous
import diagnose_w5000_v1_precore as diag
import simulate_first_prestige_v1 as sim


CHECKPOINTS = (1250, 1500, 1750, 2000, 2250, 2500)
CAPTURE_WAVES = (500,) + CHECKPOINTS
BASE_CONDITIONS = {
    "A_current": frozenset(),
    "B_escalation_off": frozenset({"escalation"}),
    "C_steady_force_off": frozenset({"steady_force"}),
    "D_escalation_steady_off": frozenset({"escalation", "steady_force"}),
    "E_rapid_fire_off": frozenset({"rapid_fire"}),
    "F_power_up_off": frozenset({"power_up"}),
    "G_critical_momentum_off": frozenset({"critical_momentum"}),
    "H_success_escalation_cap_1_5": frozenset(),
    "I_failure_escalation_floor_3": frozenset(),
}


def collect(trials: int, seed: int):
    config = dataclasses.replace(
        previous.make_pre_config(),
        diagnostic_infinite_barrage_mode="v2_fixed_ratio",
        diagnostic_checkpoints=CAPTURE_WAVES,
    )
    captures: dict[tuple[int, int, int], dict[str, Any]] = {}
    results: dict[int, sim.TrialResult] = {}
    errors = []
    for trial in range(trials):
        streams = sim.make_split_rng_streams(seed, trial)

        def capture(attempt, wave, run, permanent, live_streams, *, _trial=trial):
            captures[(_trial, attempt, wave)] = {
                "trial": _trial, "attempt": attempt, "wave": wave,
                "run": copy.deepcopy(run), "permanent": copy.deepcopy(permanent),
            }

        try:
            results[trial] = sim.run_trial(
                streams.combat, "balanced", config, True,
                rng_streams=streams, attempt_checkpoint_capture=capture,
            )
        except Exception as exc:
            errors.append({"trial": trial, "type": type(exc).__name__, "message": str(exc)})
    success = {trial for trial, result in results.items() if result.success}
    return config, captures, results, success, errors


def epic_before_w500(captures: dict[tuple[int, int, int], dict[str, Any]],
                     success_ids: set[int], trials: int):
    rows = []
    for trial in range(trials):
        states = [
            value for (tid, _attempt, wave), value in captures.items()
            if tid == trial and wave == 500
        ]
        if not states:
            continue
        capture = min(states, key=lambda item: item["attempt"])
        run = capture["run"]
        keys = sorted(
            key for key, count in run.counts.items()
            if count > 0 and key in sim.CARD_BY_KEY
            and sim.CARD_BY_KEY[key].rarity == "E"
            and run.card_first_acquired_wave.get(key, 10**9) <= 501
        )
        rows.append({
            "trial": trial, "group": "success10" if trial in success_ids else "failure20",
            "keys": keys,
        })
    all_keys = sorted({key for row in rows for key in row["keys"]})
    summary = {}
    for key in all_keys:
        success_rows = [row for row in rows if row["group"] == "success10"]
        failure_rows = [row for row in rows if row["group"] == "failure20"]
        success_rate = sum(key in row["keys"] for row in success_rows) / len(success_rows)
        failure_rate = sum(key in row["keys"] for row in failure_rows) / len(failure_rows)
        summary[key] = {
            "success_count": sum(key in row["keys"] for row in success_rows),
            "failure_count": sum(key in row["keys"] for row in failure_rows),
            "success_rate": success_rate, "failure_rate": failure_rate,
            "rate_delta": success_rate - failure_rate,
        }
    biased = [
        key for key, item in sorted(
            summary.items(), key=lambda pair: pair[1]["rate_delta"], reverse=True
        )
        if item["rate_delta"] > 0
    ][:3]
    return rows, summary, biased


def condition_config(base: sim.SimConfig, condition: str, success_group: bool,
                     epic_conditions: dict[str, str]) -> sim.SimConfig:
    suppressed = BASE_CONDITIONS.get(condition, frozenset())
    if condition in epic_conditions:
        suppressed = frozenset({epic_conditions[condition]})
    caps: tuple[tuple[str, float], ...] = ()
    floors: tuple[tuple[str, float], ...] = ()
    if condition == "H_success_escalation_cap_1_5" and success_group:
        caps = (("escalation", 1.5),)
    if condition == "I_failure_escalation_floor_3" and not success_group:
        floors = (("escalation", 3.0),)
    return dataclasses.replace(
        base,
        diagnostic_suppressed_card_keys=suppressed,
        diagnostic_card_effect_stack_caps=caps,
        diagnostic_card_effect_stack_floors=floors,
    )


def snapshot_row(capture: dict[str, Any], condition: str, config: sim.SimConfig,
                 success_group: bool, epic_conditions: dict[str, str]):
    active = condition_config(config, condition, success_group, epic_conditions)
    wave, run, permanent = capture["wave"], capture["run"], capture["permanent"]
    snapshot = sim.compute_snapshot(run, permanent, wave % 10 == 0, active)
    enemy = sim.configured_enemy_power(wave, active)
    kill_time = sim.time_to_kill(enemy, 15.0 if wave % 10 == 0 else 10.0, snapshot)
    return {
        "trial": capture["trial"], "attempt": capture["attempt"], "wave": wave,
        "group": "success10" if success_group else "failure20",
        "condition": condition, "player_power": snapshot.log_dps,
        "enemy_power": enemy, "margin": snapshot.log_dps - enemy,
        "killable": kill_time is not None, "kill_time": kill_time,
        "escalation_owned_stack": float(run.counts.get("escalation", 0)),
        "card_count": run.card_count,
    }


def build_rows(config, captures, success_ids, conditions, epic_conditions):
    rows = []
    for capture in captures.values():
        if capture["wave"] not in CHECKPOINTS:
            continue
        success_group = capture["trial"] in success_ids
        for condition in conditions:
            rows.append(snapshot_row(capture, condition, config, success_group, epic_conditions))
    return rows


def dist(values):
    return diag.dist([float(value) for value in values]) if values else {
        "count": 0, "p25": None, "p50": None, "p75": None, "min": None, "max": None,
    }


def attempt_outcome(rows, results, conditions):
    lookup = collections.defaultdict(dict)
    for row in rows:
        lookup[(row["trial"], row["attempt"], row["condition"])][row["wave"]] = row
    trial_rows = []
    for trial, result in results.items():
        group = "success10" if result.success else "failure20"
        for condition in conditions:
            attempt_highs = []
            growth_1250_1500 = []
            growth_1500_2000 = []
            reached = {wave: False for wave in CHECKPOINTS}
            for attempt, actual_high in enumerate(result.run_reaches, start=1):
                states = lookup.get((trial, attempt, condition), {})
                if 1250 not in states:
                    attempt_highs.append(int(actual_high))
                    continue
                reached[1250] = True
                high = int(actual_high)
                blocked = False
                for wave in CHECKPOINTS[1:]:
                    state = states.get(wave)
                    if state is None:
                        continue
                    if not state["killable"]:
                        high = min(high, wave - 1)
                        blocked = True
                        break
                    reached[wave] = True
                attempt_highs.append(high)
                if 1500 in states and states[1500]["killable"]:
                    growth_1250_1500.append(states[1500]["player_power"] - states[1250]["player_power"])
                if 1500 in states and 2000 in states and states[2000]["killable"]:
                    growth_1500_2000.append(states[2000]["player_power"] - states[1500]["player_power"])
            trial_rows.append({
                "trial": trial, "group": group, "condition": condition,
                "highest_wave": max(attempt_highs) if attempt_highs else 0,
                "reached": reached,
                "growth_1250_1500": statistics.median(growth_1250_1500) if growth_1250_1500 else None,
                "growth_1500_2000": statistics.median(growth_1500_2000) if growth_1500_2000 else None,
            })
    return trial_rows


def summarize(snapshot_rows, trial_rows, conditions):
    output = {}
    current_lookup = {
        (row["trial"], row["attempt"], row["wave"]): row
        for row in snapshot_rows if row["condition"] == "A_current"
    }
    for condition in conditions:
        output[condition] = {}
        selected_snapshots = [row for row in snapshot_rows if row["condition"] == condition]
        for group in ("success10", "failure20"):
            trials = [row for row in trial_rows if row["condition"] == condition and row["group"] == group]
            snaps = [row for row in selected_snapshots if row["group"] == group]
            output[condition][group] = {
                "samples": len(trials),
                "reach_rate": {
                    str(wave): sum(row["reached"][wave] for row in trials) / len(trials)
                    for wave in CHECKPOINTS
                },
                "highest_wave": dist([row["highest_wave"] for row in trials]),
                "growth_1250_1500": dist([
                    row["growth_1250_1500"] for row in trials if row["growth_1250_1500"] is not None
                ]),
                "growth_1500_2000": dist([
                    row["growth_1500_2000"] for row in trials if row["growth_1500_2000"] is not None
                ]),
                "delta_power": {
                    str(wave): dist([
                        row["player_power"] - current_lookup[(row["trial"], row["attempt"], row["wave"])]["player_power"]
                        for row in snaps if row["wave"] == wave
                    ]) for wave in CHECKPOINTS
                },
            }
    return output


def markdown(payload):
    def f(value, digits=2): return "—" if value is None else f"{value:.{digits}f}"
    def trip(item): return f"{f(item['p25'])}/{f(item['p50'])}/{f(item['p75'])}"
    lines = [
        "# W1250-W1500 card-effect matched diagnosis", "",
        f"30 trials / seed {payload['seed']} / success {payload['success_count']} / failure {payload['failure_count']}", "",
        "取得履歴・取得Wave・実stackは固定し、保存checkpoint stateへeffectだけを抑止/上書きした。到達率は250Wave checkpoint grid上の診断値。", "",
        "## Epic cards held by W500 reward resolution", "",
        "実装上W500報酬は取得Wave 501として記録されるため、ここでは`first_wave <= 501`をW500以前/報酬込みとして扱う。", "",
        "| Epic | Success | Failure | Rate delta | Added diagnosis |", "|---|---:|---:|---:|---:|",
    ]
    for key, item in payload["epic_summary"].items():
        lines.append(
            f"| {key} | {item['success_count']}/10 ({item['success_rate']:.0%}) | "
            f"{item['failure_count']}/20 ({item['failure_rate']:.0%}) | "
            f"{item['rate_delta']:+.0%} | {'yes' if key in payload['biased_epics'] else 'no'} |"
        )
    lines += ["", "## Trial outcome by effect condition", "", "| Condition | Group | W1250 | W1500 | W1750 | W2000 | W2250 | W2500 | Highest P25/P50/P75 | ΔPower W1500 | ΔPower W2000 |", "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for condition in payload["conditions"]:
        for group in ("success10", "failure20"):
            item = payload["summary"][condition][group]
            rates = item["reach_rate"]
            lines.append(
                f"| {condition} | {group} | "
                + " | ".join(f"{rates[str(wave)]:.0%}" for wave in CHECKPOINTS)
                + f" | {trip(item['highest_wave'])} | {f(item['delta_power']['1500']['p50'])} | {f(item['delta_power']['2000']['p50'])} |"
            )
    lines += ["", "## Power growth", "", "| Condition | Group | W1250→1500 P25/P50/P75 | W1500→2000 P25/P50/P75 |", "|---|---|---:|---:|"]
    for condition in payload["conditions"]:
        for group in ("success10", "failure20"):
            item = payload["summary"][condition][group]
            lines.append(f"| {condition} | {group} | {trip(item['growth_1250_1500'])} | {trip(item['growth_1500_2000'])} |")
    lines += ["", "## Interpretation", ""]
    lines += [f"- {line}" for line in payload["interpretation"]]
    lines += ["", "## Validation", "", f"errors/nonfinite: {len(payload['errors'])}/{payload['nonfinite']}", f"acquisition history mutated: {payload['acquisition_history_mutations']}", "balance changed: false", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--seed", type=int, default=sim.SEED)
    parser.add_argument("--output-dir", type=Path, default=Path("output/w5000_v1_midgame_card_effects_30"))
    args = parser.parse_args()
    config, captures, results, success_ids, errors = collect(args.trials, args.seed)
    epic_rows, epic_summary, biased_epics = epic_before_w500(captures, success_ids, args.trials)
    epic_conditions = {f"J_{key}_off": key for key in biased_epics}
    conditions = tuple(BASE_CONDITIONS) + tuple(epic_conditions)
    snapshots = build_rows(config, captures, success_ids, conditions, epic_conditions)
    trials = attempt_outcome(snapshots, results, conditions)
    summary = summarize(snapshots, trials, conditions)
    interpretation = [
        "effect-only checkpoint replayなので、rarity/reroll/draw RNGと取得履歴は全条件で同一。",
        "W1250→1500の逆転説明は、成功群でeffect OFF時の到達率・Power低下が大きいカードを優先する。",
        "checkpointは別Runを混ぜずattempt単位で連結した。W1750以降の未到達stateは生成せず、実在するbaseline stateだけを再評価した。",
        "250Wave間の正確な停止Waveは復元していないため、到達率/Highestはcheckpoint-grid診断値である。",
    ]
    payload = {
        "seed": args.seed, "trials": args.trials,
        "success_count": len(success_ids), "failure_count": len(results) - len(success_ids),
        "success_trial_ids": sorted(success_ids),
        "epic_rows": epic_rows, "epic_summary": epic_summary, "biased_epics": biased_epics,
        "conditions": conditions, "summary": summary,
        "snapshot_rows": snapshots, "trial_rows": trials,
        "interpretation": interpretation, "errors": errors,
        "nonfinite": sum(
            not math.isfinite(float(row["player_power"])) for row in snapshots
        ),
        "acquisition_history_mutations": 0,
        "balance_changed": False,
    }
    output = args.output_dir.resolve(); output.mkdir(parents=True, exist_ok=True)
    (output / "midgame_card_effects.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "midgame_card_effects.md").write_text(markdown(payload), encoding="utf-8")
    with (output / "snapshot_effect_rows.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(snapshots[0]) if snapshots else [])
        writer.writeheader(); writer.writerows(snapshots)
    print(json.dumps({
        "report": str(output / "midgame_card_effects.md"),
        "json": str(output / "midgame_card_effects.json"),
        "biased_epics": biased_epics,
        "conditions": len(conditions), "errors": len(errors),
        "nonfinite": payload["nonfinite"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
