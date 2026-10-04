#!/usr/bin/env python3
"""Paired legacy-DP versus existing W5000 DP v0.1 comparison."""

from __future__ import annotations

import argparse
import collections
import dataclasses
import json
import math
import random
from pathlib import Path
from typing import Any

import diagnose_w5000_v1_precore as diag
import simulate_first_prestige_v1 as sim
import w5000_v1_profile as profile


CHECKPOINTS = (500, 750, 1000, 1250, 1500, 1750, 2000, 2250, 2500)
CONDITIONS = ("legacy_dp", "dp_v01_bc")


def configs(max_attempts: int) -> dict[str, sim.SimConfig]:
    base = dataclasses.replace(
        profile.build_config(max_attempts=max_attempts, core_profile="no_core"),
        diagnostic_checkpoints=CHECKPOINTS,
    )
    return {
        "legacy_dp": base,
        "dp_v01_bc": dataclasses.replace(base, dp_v01=sim.DPV01Config(enabled=True)),
    }


def run_condition(
    name: str, config: sim.SimConfig, trials: int, seed: int
) -> tuple[list[tuple[int, sim.TrialResult]], list[dict[str, object]]]:
    completed: list[tuple[int, sim.TrialResult]] = []
    errors: list[dict[str, object]] = []
    for trial in range(trials):
        try:
            rng = random.Random(seed + 1_000_000 + trial)
            completed.append((trial, sim.run_trial(rng, "balanced", config, allow_overdrive=True)))
        except Exception as exc:
            errors.append({"condition": name, "trial": trial, "type": type(exc).__name__, "message": str(exc)})
    return completed, errors


def record_events(reaches: tuple[int, ...]) -> list[dict[str, int]]:
    events: list[dict[str, int]] = []
    best = -1
    previous_attempt = 0
    for index, wave in enumerate(reaches, start=1):
        if wave > best:
            events.append({
                "attempt": index,
                "wave": wave,
                "attempts_since_record": index - previous_attempt,
            })
            best = wave
            previous_attempt = index
    return events


def recurrence(reaches: tuple[int, ...]) -> dict[str, object] | None:
    first_index = next((index for index, wave in enumerate(reaches) if wave >= 1500), None)
    if first_index is None:
        return None
    first_wave = reaches[first_index]
    later = reaches[first_index + 1:]
    threshold = first_wave - 100
    return {
        "first_attempt": first_index + 1,
        "first_wave": first_wave,
        "later_runs": len(later),
        "later_max_wave": max(later) if later else None,
        "later_reach_1500_count": sum(wave >= 1500 for wave in later),
        "later_within_100_count": sum(wave >= threshold for wave in later),
        "any_later_reach_1500": any(wave >= 1500 for wave in later),
        "any_later_within_100": any(wave >= threshold for wave in later),
    }


def summarize(
    completed: list[tuple[int, sim.TrialResult]], errors: list[dict[str, object]], trials: int, max_attempts: int
) -> dict[str, Any]:
    rows = [row for _, row in completed]
    checkpoints: dict[str, object] = {}
    nonfinite: list[dict[str, object]] = []
    for wave in CHECKPOINTS:
        reached = [(trial, row) for trial, row in completed if wave in row.reach_seconds]
        states = [row.first_reach_checkpoint_states[wave] for _, row in reached]
        checkpoints[str(wave)] = {
            "reached": len(reached),
            "reach_rate": len(reached) / trials,
            "state": diag.numeric_state_summary(states),
            "weapon_owned_rate": sum(bool(state["weapon_owned"]) for state in states) / len(states) if states else 0.0,
            "weapon_rarity": dict(collections.Counter(
                str(state["weapon_rarity"]) for state in states if state["weapon_owned"]
            )),
            "relic_unlocked_rate": sum(bool(state["relic_unlocked"]) for state in states) / len(states) if states else 0.0,
        }
    trial_details: list[dict[str, object]] = []
    recurrences: list[dict[str, object]] = []
    for trial, row in completed:
        highest = max(row.run_reaches) if row.run_reaches else 0
        final_wave = None if row.success else (row.run_reaches[-1] if row.run_reaches else 0)
        rec = recurrence(row.run_reaches)
        if rec is not None:
            recurrences.append({"trial": trial, **rec})
        trial_details.append({
            "trial": trial,
            "success": row.success,
            "highest_wave": highest,
            "final_death_wave": final_wave,
            "deaths": row.deaths,
            "attempts": row.attempts,
            "run_reaches": list(row.run_reaches),
            "record_events": record_events(row.run_reaches),
            "recurrence_after_w1500": rec,
            "final_dp_levels": row.dp_v01_levels,
            "final_dp_balance": row.dp_balance,
            "final_dp_earned": row.dp_total_earned,
            "final_dp_spent": row.dp_total_spent,
            "reroll_bought": row.dp_reroll_bought,
        })
        for key, value in {
            "combat_seconds": row.total_combat_seconds,
            "interaction_seconds": row.total_interaction_seconds,
        }.items():
            if not math.isfinite(value):
                nonfinite.append({"trial": trial, "field": key, "value": value})
        for wave, state in row.first_reach_checkpoint_states.items():
            for key, value in state.items():
                if isinstance(value, float) and not math.isfinite(value):
                    nonfinite.append({"trial": trial, "wave": wave, "field": key, "value": value})

    final_waves = [
        int(item["final_death_wave"]) for item in trial_details if item["final_death_wave"] is not None
    ]
    record_gaps = [
        float(event["attempts_since_record"])
        for item in trial_details for event in item["record_events"][1:]
    ]
    eligible = len(recurrences)
    later_runs = sum(int(item["later_runs"]) for item in recurrences)
    return {
        "completed_trials": len(completed),
        "successes": sum(row.success for row in rows),
        "checkpoints": checkpoints,
        "highest_wave": diag.dist([float(item["highest_wave"]) for item in trial_details]),
        "final_death_wave": diag.dist([float(value) for value in final_waves]),
        "final_death_wave_exact": dict(sorted(collections.Counter(final_waves).items())),
        "final_death_wave_bands": dict(sorted(
            collections.Counter(diag.band_label(value) for value in final_waves).items(),
            key=lambda item: int(item[0].split("-")[0]),
        )),
        "deaths": diag.dist([float(row.deaths) for row in rows]),
        "max_attempts_reached": sum(not row.success and row.attempts >= max_attempts for row in rows),
        "w2500_reached": sum(2500 in row.reach_seconds for row in rows),
        "record_update_interval_attempts": diag.dist(record_gaps),
        "w1500_recurrence": {
            "eligible_trials": eligible,
            "any_later_reach_w1500_trials": sum(bool(item["any_later_reach_1500"]) for item in recurrences),
            "any_later_within_100_trials": sum(bool(item["any_later_within_100"]) for item in recurrences),
            "later_runs": later_runs,
            "later_reach_w1500_runs": sum(int(item["later_reach_1500_count"]) for item in recurrences),
            "later_within_100_runs": sum(int(item["later_within_100_count"]) for item in recurrences),
            "definition": "after first W1500+ run; near = at least first W1500+ wave minus 100",
        },
        "final_permanent": {
            "dp_total_level": diag.dist([float(row.permanent_levels) for row in rows]),
            "dp_base_atk_level": diag.dist([float(row.atk_levels) for row in rows]),
            "dp_attack_speed_level": diag.dist([float(row.as_levels) for row in rows]),
            "dp_xp_level": diag.dist([float(row.xp_levels) for row in rows]),
            **{
                f"dp_v01_{key}_level": diag.dist([float(row.dp_v01_levels[key]) for row in rows])
                for key in sim.DP_V01_ITEMS
            },
            "dp_balance": diag.dist([float(row.dp_balance) for row in rows]),
            "dp_earned": diag.dist([float(row.dp_total_earned) for row in rows]),
            "dp_spent": diag.dist([float(row.dp_total_spent) for row in rows]),
            "weapon_material": diag.dist([row.weapon_material for row in rows]),
            "relic_material": diag.dist([row.relic_material for row in rows]),
            "weapon_generations": diag.dist([float(row.weapon_generations) for row in rows]),
            "relic_generations": diag.dist([float(row.relic_generations) for row in rows]),
            "relic_drops": diag.dist([float(row.relic_drops) for row in rows]),
        },
        "trials": trial_details,
        "nonfinite": nonfinite,
        "errors": errors,
    }


def pct(value: float) -> str:
    return f"{value:.1%}"


def f(value: float | None, digits: int = 1) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# w5000_v1 DP paired comparison",
        "",
        f"legacy DP vs DP v0.1 BC / paired {payload['trials']} trials / seed {payload['seed']} / max 140 runs",
        "",
        "Core=no_core、Enemy/Weapon/Relic/Cardは共通。DP v0.1は既存Economy B + Power C値を無調整で使用。",
        "",
        "| Condition | Highest P25/P50/P75 | Final death P25/P50/P75 | Deaths P25/P50/P75 | cap trials | W2500 | W5000 success |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name in CONDITIONS:
        item = payload["conditions"][name]
        h, d, deaths = item["highest_wave"], item["final_death_wave"], item["deaths"]
        lines.append(
            f"| {name} | {f(h['p25'])}/{f(h['p50'])}/{f(h['p75'])} | "
            f"{f(d['p25'])}/{f(d['p50'])}/{f(d['p75'])} | "
            f"{f(deaths['p25'])}/{f(deaths['p50'])}/{f(deaths['p75'])} | "
            f"{item['max_attempts_reached']} | {item['w2500_reached']} | {item['successes']} |"
        )
    lines += [
        "",
        "## Checkpoints",
        "",
        "| W | legacy reach | v0.1 reach | legacy margin P50 | v0.1 margin P50 | legacy DP Lv | v0.1 DP Lv |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for wave in CHECKPOINTS:
        a = payload["conditions"]["legacy_dp"]["checkpoints"][str(wave)]
        b = payload["conditions"]["dp_v01_bc"]["checkpoints"][str(wave)]
        def p50(item: dict[str, Any], key: str) -> float | None:
            return item["state"].get(key, {}).get("p50")
        lines.append(
            f"| {wave} | {pct(a['reach_rate'])} | {pct(b['reach_rate'])} | "
            f"{f(p50(a, 'margin_power'), 2)} | {f(p50(b, 'margin_power'), 2)} | "
            f"{f(p50(a, 'dp_total_level'))} | {f(p50(b, 'dp_total_level'))} |"
        )
    lines += ["", "## W1500以降の再現性", ""]
    for name in CONDITIONS:
        x = payload["conditions"][name]["w1500_recurrence"]
        run_reach_rate = x["later_reach_w1500_runs"] / x["later_runs"] if x["later_runs"] else 0.0
        run_near_rate = x["later_within_100_runs"] / x["later_runs"] if x["later_runs"] else 0.0
        lines.append(
            f"- {name}: 対象{x['eligible_trials']} trial、後続Runで再びW1500到達 "
            f"{x['any_later_reach_w1500_trials']}/{x['eligible_trials']}、初回到達Wave-100以内を再現 "
            f"{x['any_later_within_100_trials']}/{x['eligible_trials']}。後続Run単位ではW1500到達 "
            f"{x['later_reach_w1500_runs']}/{x['later_runs']} ({run_reach_rate:.1%})、-100以内 "
            f"{x['later_within_100_runs']}/{x['later_runs']} ({run_near_rate:.1%})。"
        )
    lines += [
        "",
        "## 診断上の注意",
        "",
        "- 新DPはW1500以上へ一度到達するtrialを増やすが、到達後の1 Run単位再現率はlegacyとほぼ同じ。",
        "- 新DPのW2500 Margin急増は、高ASとW2500確定Legendary（Infinite Barrage系）の相互作用。DPの連続成長だけの効果ではない。",
        "",
        f"non-Core config一致: {payload['paired_invariants']['non_dp_config_match']}",
        f"nonfinite: {sum(len(payload['conditions'][name]['nonfinite']) for name in CONDITIONS)} / "
        f"errors: {sum(len(payload['conditions'][name]['errors']) for name in CONDITIONS)}",
        "",
        "本比較ではDP値を調整しておらず、候補の正式採用も行っていない。",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--seed", type=int, default=sim.SEED)
    parser.add_argument("--max-attempts", type=int, default=140)
    parser.add_argument("--output-dir", type=Path, default=Path("output/w5000_v1_dp_paired_30"))
    args = parser.parse_args()
    if not 1 <= args.trials <= 30:
        parser.error("DP paired diagnosis is limited to 1-30 trials")
    cfgs = configs(args.max_attempts)
    completed: dict[str, list[tuple[int, sim.TrialResult]]] = {}
    errors: dict[str, list[dict[str, object]]] = {}
    for name in CONDITIONS:
        completed[name], errors[name] = run_condition(name, cfgs[name], args.trials, args.seed)

    normalized = []
    for name in CONDITIONS:
        values = dataclasses.asdict(cfgs[name])
        values.pop("dp_v01")
        normalized.append(values)
    payload = {
        "trials": args.trials,
        "seed": args.seed,
        "max_attempts": args.max_attempts,
        "dp_v01": dataclasses.asdict(cfgs["dp_v01_bc"].dp_v01),
        "paired_invariants": {
            "same_seed_formula": "seed + 1_000_000 + trial_index",
            "non_dp_config_match": normalized[0] == normalized[1],
        },
        "conditions": {
            name: summarize(completed[name], errors[name], args.trials, args.max_attempts)
            for name in CONDITIONS
        },
        "balance_changed": False,
        "automatic_adoption": False,
    }
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "w5000_v1_dp_paired.json"
    md_path = output_dir / "w5000_v1_dp_paired.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(markdown(payload), encoding="utf-8")
    print(json.dumps({
        "json": str(json_path), "markdown": str(md_path),
        "non_dp_config_match": payload["paired_invariants"]["non_dp_config_match"],
        "errors": {name: len(payload["conditions"][name]["errors"]) for name in CONDITIONS},
        "nonfinite": {name: len(payload["conditions"][name]["nonfinite"]) for name in CONDITIONS},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
