#!/usr/bin/env python3
"""Decompose Core-off W2500->W5000 power using saved paired states only."""

from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import pickle
import random
import sys
from pathlib import Path
from typing import Any

import simulate_first_prestige_v1 as sim


CHECKPOINTS = (2500, 3000, 3500, 4000, 4500, 5000)
CATEGORIES = (
    "raw_base_atk",
    "weapon",
    "relic",
    "dp",
    "base_atk_cards",
    "all_damage",
    "attack_speed",
    "crit",
    "follow_up",
    "xp_to_damage",
    "boss_kill_growth",
    "other_growth_cards",
    "epic_legendary_direct",
    "other_multipliers",
)
LABELS = {
    "raw_base_atk": "Raw/Base ATK由来",
    "weapon": "Weapon由来",
    "relic": "Relic由来",
    "dp": "DP由来",
    "base_atk_cards": "Base ATKカード由来",
    "all_damage": "All Damage由来",
    "attack_speed": "Attack Speed由来",
    "crit": "Crit/Crit Multiplier由来",
    "follow_up": "Follow-Up由来",
    "xp_to_damage": "XP→Damage変換由来",
    "boss_kill_growth": "Boss撃破成長カード由来",
    "other_growth_cards": "その他成長カード由来",
    "epic_legendary_direct": "Epic/Legendary直接効果",
    "other_multipliers": "その他の倍率",
}
PLANNED = {
    "raw_base_atk": "維持（新Weapon ATK加算先）",
    "weapon": "旧Weapon Powerは新Weapon Base ATK式へ置換予定",
    "relic": "平均Power近似は実Relic/OP成長へ置換予定",
    "dp": "廃止予定の明示なし",
    "base_atk_cards": "廃止予定の明示なし",
    "all_damage": "廃止予定の明示なし",
    "attack_speed": "廃止予定の明示なし",
    "crit": "廃止予定の明示なし",
    "follow_up": "廃止予定の明示なし",
    "xp_to_damage": "廃止予定の明示なし",
    "boss_kill_growth": "廃止予定の明示なし",
    "other_growth_cards": "廃止予定の明示なし",
    "epic_legendary_direct": "カード群は維持候補、Core/Final Equationは本分析OFF",
    "other_multipliers": "廃止予定の明示なし",
}


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return float(ordered[low])
    return float(ordered[low] + (ordered[high] - ordered[low]) * (position - low))


def make_config() -> Any:
    return sim.SimConfig(
        max_attempts=1,
        reward_skip_enabled=True,
        defense=sim.DefenseConfig(enabled=False),
        target_wave=5000,
        enemy_curve_scale=1.0,
        card_upgrade_cap=1,
        relic_selection_enabled=False,
        exponential_core_multiplier=1.0,
        exponential_core_unlock_wave=2500,
        disabled_card_keys=frozenset({"exponential_core", "final_equation"}),
    )


def proportional_log(total_log: float, parts: dict[str, float]) -> dict[str, float]:
    total = sum(parts.values())
    if total <= 0.0 or abs(total_log) <= 1e-15:
        return {key: 0.0 for key in parts}
    return {key: total_log * value / total for key, value in parts.items()}


def decompose(run: Any, permanent: Any, boss: bool, config: Any) -> dict[str, float]:
    counts = run.counts
    amp = sim.limit_amplification(counts)
    out = {key: 0.0 for key in CATEGORIES}
    details: dict[str, float] = {}

    # Raw Base ATK is 1, therefore log10(1) = 0 Power.
    out["raw_base_atk"] = 0.0

    crit_chance = (
        0.01
        + 0.10 * amp * sim.enhanced_count(run, "critical_eye")
        + 0.03 * amp * sim.enhanced_count(run, "critical_power")
        + 0.06 * amp * sim.enhanced_count(run, "sharpened_edge")
        + 0.15 * amp * sim.enhanced_count(run, "precise_strike")
        + 0.03 * amp * sim.enhanced_count(run, "heavy_critical")
        + 0.10 * amp * sim.enhanced_count(run, "critical_training")
        - 0.10 * sim.n(counts, "brutal_critical")
    )
    crit_chance = max(0.0, crit_chance)
    crit_multiplier = (
        2.0
        + 0.50 * amp * sim.enhanced_count(run, "critical_power")
        + 0.20 * amp * sim.enhanced_count(run, "sharpened_edge")
        + 0.20 * amp * sim.enhanced_count(run, "critical_training")
    )
    crit_multiplier *= (1 + 0.50 * sim.positive_amp(run, "heavy_critical")) ** sim.n(counts, "heavy_critical")
    crit_multiplier *= (1 + 0.50 * sim.positive_amp(run, "brutal_critical")) ** sim.n(counts, "brutal_critical")

    as_bonus = (
        0.20 * amp * sim.enhanced_count(run, "rapid_fire")
        + 0.30 * amp * sim.enhanced_count(run, "light_attack")
        + 0.35 * amp * sim.enhanced_count(run, "overclock")
        + 0.05 * amp * (crit_chance // 0.25) * sim.enhanced_count(run, "critical_momentum")
        + 0.05 * amp * (crit_chance // 0.20) * sim.enhanced_count(run, "critical_engine")
    )
    base_interval = max(0.1, 1.0 - 0.1 * permanent.interval_level)
    attack_speed = (1.0 / base_interval) * 1.05**permanent.attack_speed * (1 + as_bonus)
    attack_speed *= 0.90 ** (sim.n(counts, "heavy_blow") + sim.n(counts, "brutal_force"))
    attack_speed *= 0.95 ** sim.n(counts, "precise_strike")
    attack_speed *= 0.97 ** sim.n(counts, "heavy_critical")
    attack_speed *= 0.98 ** sim.n(counts, "study_break")

    xp_bonus = (
        0.20 * amp * sim.enhanced_count(run, "experience")
        + 0.25 * amp * sim.enhanced_count(run, "fast_learner")
        + 0.30 * amp * sim.enhanced_count(run, "study_break")
        + 0.35 * amp * sim.enhanced_count(run, "risky_study")
        + 0.03 * sim.positive_amp(run, "accelerated_learning") * run.accelerated_units
    )
    general_xp = 1.05**permanent.xp * (1 + xp_bonus)
    general_xp *= 0.90 ** sim.n(counts, "battle_focus")
    if permanent.relic_unlocked:
        general_xp *= 1.02

    # Base ATK terms.
    out["dp"] += permanent.atk * math.log10(1.10)
    attack_bonus = (
        0.25 * amp * sim.enhanced_count(run, "power_up")
        + 0.40 * amp * sim.enhanced_count(run, "heavy_blow")
        + 0.50 * amp * sim.enhanced_count(run, "glass_cannon")
        + 0.50 * amp * sim.enhanced_count(run, "brutal_force")
    )
    out["base_atk_cards"] += math.log10(1 + attack_bonus)
    out["base_atk_cards"] += sim.n(counts, "light_attack") * math.log10(0.90)
    out["base_atk_cards"] += sim.n(counts, "fast_learner") * math.log10(0.98)
    out["base_atk_cards"] += sim.n(counts, "overclock") * math.log10(0.90)
    if run.weapon:
        out["weapon"] += run.weapon_power
        details["Weapon Power"] = run.weapon_power
    if permanent.relic_unlocked:
        relic_base = math.log10(1.02)
        out["relic"] += relic_base
        details["Relic fixed Base ATK"] = relic_base
    if sim.n(counts, "double_scaling"):
        double_scaling = math.log10(1 + 0.25 * max(0.0, attack_speed - 1))
        out["epic_legendary_direct"] += double_scaling
        details["Double Scaling"] = double_scaling

    # Attack Speed terms: permanent levels/interval are DP, cards stay in AS.
    out["dp"] += permanent.attack_speed * math.log10(1.05) + math.log10(1.0 / base_interval)
    out["attack_speed"] += math.log10(1 + as_bonus)
    out["attack_speed"] += (sim.n(counts, "heavy_blow") + sim.n(counts, "brutal_force")) * math.log10(0.90)
    out["attack_speed"] += sim.n(counts, "precise_strike") * math.log10(0.95)
    out["attack_speed"] += sim.n(counts, "heavy_critical") * math.log10(0.97)
    out["attack_speed"] += sim.n(counts, "study_break") * math.log10(0.98)

    # Crit expected multiplier, including Multi-Crit/Geometry/Singularity.
    out["crit"] += sim.crit_log_multiplier(crit_chance, crit_multiplier, counts)

    # Shared additive All Damage pool, allocated proportionally before log10.
    xp_excess = max(0.0, general_xp - 1.0)
    shared_parts = {
        "all_damage": (
            0.15 * amp * sim.enhanced_count(run, "steady_force")
            + 0.20 * amp * sim.enhanced_count(run, "battle_focus")
        ),
        "xp_to_damage": (
            0.10 * amp * xp_excess * sim.enhanced_count(run, "battle_scholar")
            + 0.25 * amp * xp_excess * sim.enhanced_count(run, "knowledge_conversion")
            + 0.50 * xp_excess * sim.n(counts, "perfect_learning")
        ),
        "crit": 0.03 * amp * (crit_chance // 0.10) * sim.enhanced_count(run, "critical_conversion"),
    }
    shared_log = math.log10(1 + sum(shared_parts.values()))
    for key, value in proportional_log(shared_log, shared_parts).items():
        out[key] += value

    effective_kills = sim.progression_wave(run.kills, config)
    escalation = (
        (effective_kills // 10)
        * sim.n(counts, "escalation")
        * math.log10(1 + 0.05 * sim.positive_amp(run, "escalation"))
    )
    out["other_growth_cards"] += escalation
    details["Escalation"] = escalation
    growth_engine = run.growth_units * math.log10(
        1 + 0.05 * sim.positive_amp(run, "growth_engine")
    )
    out["other_growth_cards"] += growth_engine
    details["Growth Engine"] = growth_engine
    boss_devourer = run.boss_devourer_units * math.log10(
        1 + 0.15 * sim.positive_amp(run, "boss_devourer")
    )
    out["boss_kill_growth"] += boss_devourer
    details["Boss Devourer"] = boss_devourer
    out["dp"] += sim.milestone_damage_log(permanent.total_levels, config.milestone_power_scale)
    out["boss_kill_growth"] += run.assimilation_power
    details["Boss Assimilation"] = run.assimilation_power
    out["epic_legendary_direct"] += run.legendary_growth_log
    details["Legendary Growth Log"] = run.legendary_growth_log

    out["other_multipliers"] += sim.n(counts, "risky_study") * math.log10(0.90)
    if boss:
        out["all_damage"] += math.log10(
            1 + 0.40 * amp * sim.enhanced_count(run, "boss_research")
        )
    else:
        out["other_multipliers"] += sim.n(counts, "boss_research") * math.log10(0.95)

    if sim.n(counts, "follow_up_strike"):
        follow_rate = 0.10 * amp + 0.15 * amp * sim.enhanced_count(run, "double_strike")
        follow_damage = 0.50 * amp + 0.25 * amp * sim.enhanced_count(run, "double_strike")
        q = min(0.50, 0.25 * follow_rate)
        chain = 1.0
        if sim.n(counts, "recursive_follow_up"):
            chain = 1 / (1 - q)
        elif sim.n(counts, "follow_up_echo"):
            chain = 1 + q
        out["follow_up"] += math.log10(1 + follow_rate * chain * follow_damage)

    if sim.n(counts, "infinite_barrage"):
        excess_steps = math.floor(max(0.0, attack_speed - 1.0) + 1e-12)
        infinite_barrage = excess_steps * math.log10(1.25)
        out["epic_legendary_direct"] += infinite_barrage
        details["Infinite Barrage"] = infinite_barrage
    if sim.n(counts, "knowledge_collapse"):
        excess_steps = math.floor(xp_excess + 1e-12)
        out["xp_to_damage"] += excess_steps * math.log10(1.30)
    if run.momentum_ready and sim.n(counts, "momentum"):
        momentum = sim.n(counts, "momentum") * math.log10(
            1 + 0.50 * sim.positive_amp(run, "momentum")
        )
        out["other_growth_cards"] += momentum
        details["Momentum"] = momentum
    if permanent.relic_unlocked:
        relic_kill = math.log10(1 + 0.01 * (effective_kills // 10))
        out["relic"] += relic_kill
        details["Relic kill scaling"] = relic_kill
    relic_average = (
        sim.relic_average_power(sim.progression_wave(permanent.max_wave, config), config.relic_scale)
        * permanent.relic_quality
    )
    out["relic"] += relic_average
    details["Relic average Power"] = relic_average
    perfect_overdrive = run.perfect_overdrive_stacks * math.log10(1.01)
    out["epic_legendary_direct"] += perfect_overdrive
    details["Perfect Overdrive"] = perfect_overdrive

    # Exponential Core and Final Equation are deliberately absent.
    expected = sim.compute_snapshot(run, permanent, boss, config).log_dps
    out["_sum"] = sum(out[key] for key in CATEGORIES)
    out["_final_damage_power"] = expected
    out["_residual"] = expected - out["_sum"]
    out["_details"] = details
    return out


def replay_saved_state(path: Path, config: Any) -> dict[str, Any]:
    with path.open("rb") as handle:
        captured = pickle.load(handle)
    run = copy.deepcopy(captured["run"])
    permanent = copy.deepcopy(captured["permanent"])
    run.counts.pop("exponential_core", None)
    run.counts.pop("final_equation", None)
    rng = random.Random()
    rng.setstate(captured["rng_state"])
    states: dict[int, tuple[Any, Any]] = {
        2500: (copy.deepcopy(run), copy.deepcopy(permanent))
    }
    original_compute = sim.compute_snapshot

    def capture_compute(run_state: Any, permanent_state: Any, boss: bool, current_config: Any) -> Any:
        snapshot = original_compute(run_state, permanent_state, boss, current_config)
        wave = int(run_state.kills)
        if wave in CHECKPOINTS and wave not in states:
            states[wave] = (copy.deepcopy(run_state), copy.deepcopy(permanent_state))
        return snapshot

    sim.compute_snapshot = capture_compute
    try:
        sim.run_once(
            rng,
            "balanced",
            permanent,
            config,
            True,
            target_wave=5000,
            initial_run=run,
            start_wave=2501,
        )
    finally:
        sim.compute_snapshot = original_compute

    return {
        "trial": int(captured["trial"]),
        "attempt_at_capture": int(captured["attempt"]),
        "checkpoint_decomposition": {
            wave: decompose(run_state, permanent_state, wave % 10 == 0, config)
            for wave, (run_state, permanent_state) in sorted(states.items())
        },
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_wave: dict[str, Any] = {}
    for wave in CHECKPOINTS:
        entries = [row["checkpoint_decomposition"][wave] for row in rows if wave in row["checkpoint_decomposition"]]
        by_wave[str(wave)] = {
            "states": len(entries),
            "final_damage_power_p50": percentile([entry["_final_damage_power"] for entry in entries], 0.50),
            "sum_components_p50": percentile([entry["_sum"] for entry in entries], 0.50),
            "max_abs_residual": max((abs(entry["_residual"]) for entry in entries), default=0.0),
            "components_p50": {
                category: percentile([entry[category] for entry in entries], 0.50)
                for category in CATEGORIES
            },
        }

    paired = [
        row for row in rows
        if 2500 in row["checkpoint_decomposition"] and 5000 in row["checkpoint_decomposition"]
    ]
    growth = []
    for category in CATEGORIES:
        deltas = [
            row["checkpoint_decomposition"][5000][category]
            - row["checkpoint_decomposition"][2500][category]
            for row in paired
        ]
        growth.append({
            "category": category,
            "label": LABELS[category],
            "w2500_power_p50": by_wave["2500"]["components_p50"][category],
            "w5000_power_p50": by_wave["5000"]["components_p50"][category],
            "paired_growth_p50": percentile(deltas, 0.50),
            "paired_growth_p25": percentile(deltas, 0.25),
            "paired_growth_p75": percentile(deltas, 0.75),
            "paired_growth_mean": sum(deltas) / len(deltas),
            "new_w5000_plan": PLANNED[category],
        })
    # Means are used for the ranking because additive means sum exactly to the
    # mean total Power growth; independent medians do not generally add.
    growth.sort(key=lambda item: item["paired_growth_mean"], reverse=True)
    total_deltas = [
        row["checkpoint_decomposition"][5000]["_final_damage_power"]
        - row["checkpoint_decomposition"][2500]["_final_damage_power"]
        for row in paired
    ]
    detail_names = sorted({
        name
        for row in rows
        for entry in row["checkpoint_decomposition"].values()
        for name in entry["_details"]
    })
    detail_growth = []
    for name in detail_names:
        at_2500 = [
            row["checkpoint_decomposition"][2500]["_details"].get(name, 0.0)
            for row in paired
        ]
        at_5000 = [
            row["checkpoint_decomposition"][5000]["_details"].get(name, 0.0)
            for row in paired
        ]
        detail_growth.append({
            "effect": name,
            "w2500_power_p50": percentile(at_2500, 0.50),
            "w5000_power_p50": percentile(at_5000, 0.50),
            "paired_growth_p50": percentile(
                [end - start for start, end in zip(at_2500, at_5000)], 0.50
            ),
            "paired_growth_mean": sum(end - start for start, end in zip(at_2500, at_5000)) / len(paired),
            "active_rate_w5000": sum(abs(value) > 1e-15 for value in at_5000) / len(at_5000),
        })
    detail_growth.sort(key=lambda item: item["paired_growth_mean"], reverse=True)
    return {
        "saved_states_loaded": len(rows),
        "paired_states_reaching_w5000": len(paired),
        "core": False,
        "final_equation": False,
        "checkpoint_power": by_wave,
        "w2500_to_w5000_final_damage_growth_p50": percentile(total_deltas, 0.50),
        "w2500_to_w5000_final_damage_growth_mean": sum(total_deltas) / len(total_deltas),
        "growth_ranking": growth,
        "direct_effect_detail_ranking": detail_growth,
        "notes": [
            "Shared additive All Damage log is allocated proportionally to its raw bonus terms.",
            "Limit Break/Shatter amplification is attributed to the affected category, not double-counted as rarity power.",
            "Epic/Legendary direct contains only residual direct engines such as Double Scaling, Legendary growth, Infinite Barrage and Perfect Overdrive.",
            "First Strike, Last Stand, Execution and Time Collapse affect time-to-kill phases but are not included in Snapshot.log_dps.",
            "This is an exact state-formula decomposition, not a counterfactual history attribution.",
        ],
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["trial", "wave", "final_damage_power", "sum_components", "residual", *CATEGORIES]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            for wave, entry in sorted(row["checkpoint_decomposition"].items()):
                writer.writerow({
                    "trial": row["trial"],
                    "wave": wave,
                    "final_damage_power": entry["_final_damage_power"],
                    "sum_components": entry["_sum"],
                    "residual": entry["_residual"],
                    **{category: entry[category] for category in CATEGORIES},
                })


def fmt(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def write_markdown(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Coreなし W2500→W5000 Final Damage Power分解",
        "",
        f"保存済みW2500状態: {summary['saved_states_loaded']}件  ",
        f"W5000まで同一Runで到達: {summary['paired_states_reaching_w5000']}件  ",
        "Exponential Core: OFF / Final Equation: OFF",
        "",
        "## Final Damage Power",
        "",
        "| Wave | 状態数 | Final Damage Power P50 | 成分合計 P50 | 最大絶対残差 |",
        "|---:|---:|---:|---:|---:|",
    ]
    for wave in CHECKPOINTS:
        item = summary["checkpoint_power"][str(wave)]
        lines.append(
            f"| {wave} | {item['states']} | {fmt(item['final_damage_power_p50'])} | "
            f"{fmt(item['sum_components_p50'])} | {item['max_abs_residual']:.3e} |"
        )
    lines += [
        "",
        f"W2500→W5000のpaired増加中央値: **+{fmt(summary['w2500_to_w5000_final_damage_growth_p50'])} Power**",
        f"W2500→W5000のpaired増加平均: **+{fmt(summary['w2500_to_w5000_final_damage_growth_mean'])} Power**",
        "",
        "## 増加寄与ランキング",
        "",
        "平均増加は各項目を合計すると全体平均と一致するため、順位はpaired増加平均で決定。",
        "",
        "| 順位 | システム | W2500 P50 | W5000 P50 | 増加P50 | 増加平均 | 新W5000設計 |",
        "|---:|---|---:|---:|---:|---:|---|",
    ]
    for index, item in enumerate(summary["growth_ranking"], 1):
        lines.append(
            f"| {index} | {item['label']} | {fmt(item['w2500_power_p50'])} | "
            f"{fmt(item['w5000_power_p50'])} | {fmt(item['paired_growth_p50'])} | "
            f"{fmt(item['paired_growth_mean'])} | "
            f"{item['new_w5000_plan']} |"
        )
    lines += ["", "## Checkpoint別成分P50", ""]
    header = "| システム | " + " | ".join(f"W{wave}" for wave in CHECKPOINTS) + " |"
    lines += [header, "|---|" + "---:|" * len(CHECKPOINTS)]
    for category in CATEGORIES:
        values = [
            summary["checkpoint_power"][str(wave)]["components_p50"][category]
            for wave in CHECKPOINTS
        ]
        lines.append(
            f"| {LABELS[category]} | " + " | ".join(fmt(value) for value in values) + " |"
        )
    lines += [
        "",
        "## 主要直接効果の内訳",
        "",
        "| 順位 | 効果 | W2500 P50 | W5000 P50 | 増加P50 | 増加平均 | W5000有効率 |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for index, item in enumerate(summary["direct_effect_detail_ranking"], 1):
        lines.append(
            f"| {index} | {item['effect']} | {fmt(item['w2500_power_p50'])} | "
            f"{fmt(item['w5000_power_p50'])} | {fmt(item['paired_growth_p50'])} | "
            f"{fmt(item['paired_growth_mean'])} | {item['active_rate_w5000']:.1%} |"
        )
    lines += [
        "",
        "## 解釈上の注意",
        "",
        "- 同枠加算のAll Damageは、log化前の各ボーナス比率でPowerを按分した。",
        "- Limit Break/Shatterの増幅分は増幅対象カテゴリへ含め、Epic/Legendaryへ重複計上していない。",
        "- Epic/Legendary直接効果はDouble Scaling、Legendary成長、Infinite Barrage、Perfect Overdriveなどの残余直接効果。",
        "- First Strike、Last Stand、Execution、Time Collapseは戦闘中のTTKへ作用するが、Snapshot.log_dpsには含まれない。",
        "- これは保存状態における数式の厳密分解であり、カードを取らなかった場合を再試行する因果推定ではない。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=Path("output/w5000_exponential_core_paired_50/w2500_states"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/w5000_core_off_power_decomposition"),
    )
    args = parser.parse_args()
    state_paths = sorted(args.state_dir.resolve().glob("trial_*_w2500.pkl"))
    if not state_paths:
        parser.error(f"No saved W2500 states found in {args.state_dir}")

    sim.CHECKPOINTS = CHECKPOINTS
    sim.REACH_WAVES = CHECKPOINTS
    sim.VARIANT_REACH_WAVES = CHECKPOINTS
    config = make_config()
    rows = [replay_saved_state(path, config) for path in state_paths]
    summary = summarize(rows)

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "w5000_core_off_power_decomposition.json"
    csv_path = output_dir / "w5000_core_off_power_decomposition.csv"
    md_path = output_dir / "w5000_core_off_power_decomposition.md"
    json_path.write_text(
        json.dumps({"summary": summary, "trials": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_csv(csv_path, rows)
    write_markdown(md_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"json={json_path}")
    print(f"csv={csv_path}")
    print(f"markdown={md_path}")


if __name__ == "__main__":
    main()
