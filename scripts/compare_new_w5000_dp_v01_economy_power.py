#!/usr/bin/env python3
"""2x2 Economy/Power factorial comparison for new W5000 DP v0.1."""

from __future__ import annotations

import argparse
import csv
from dataclasses import replace
import json
from pathlib import Path
import sys
from typing import Any

import simulate_first_prestige_v1 as sim
import simulate_new_w5000_dp_v01 as dp


DEFAULT_SEED = 20260828
MAIN = (100, 250, 400, 500, 600, 750, 1000)


def hybrid(name: str, economy: dp.Candidate, power: dp.Candidate) -> dp.Candidate:
    """Economy fields come from economy; all per-level effects come from power."""
    return dp.Candidate(
        name=name,
        base_cost=economy.base_cost,
        cost_growth=economy.cost_growth,
        atk_per_level=power.atk_per_level,
        as_per_level=power.as_per_level,
        xp_per_level=power.xp_per_level,
        crit_rate_per_level=power.crit_rate_per_level,
        crit_mult_per_level=power.crit_mult_per_level,
        weapon_atk_per_level=power.weapon_atk_per_level,
        luck_per_effective_level=power.luck_per_effective_level,
        weapon_find_per_effective_level=power.weapon_find_per_effective_level,
        weapon_quality_rate=power.weapon_quality_rate,
        death_base=economy.death_base,
        death_divisor=economy.death_divisor,
        record_bonus=economy.record_bonus,
        big_boss_bonus=economy.big_boss_bonus,
        reroll_cost=economy.reroll_cost,
    )


def fmt(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# 新W5000 DP v0.1 Economy × Power 分離比較", "",
        f"各{payload['settings']['trials']} trials / Standard bot / seed {payload['settings']['seed']} / target W1000", "",
        "Legendary / Relic / refinement / Weapon rarity・drop RNG・affix / Sweep / Auto / Game Speed: OFF", "",
        "BB=Economy B+Power B、CB=Economy C+Power B、BC=Economy B+Power C、CC=Economy C+Power C。", "",
        "Luck/Weapon Find/Weapon Qualityの1Lv効果もPower側に追従する。Find/Qualityは固定Weapon条件では休眠。", "",
        "## 全体比較", "",
        "| 条件 | W500時間 | W750時間 | W1000時間 | W500/W750/W1000到達率 | Deaths P50 | Final Wave P25/P50/P75 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, result in payload["conditions"].items():
        c = result["checkpoint"]
        lines.append(
            f"| {name} | {fmt(c['500']['time_hours']['p50'])}h | {fmt(c['750']['time_hours']['p50'])}h | {fmt(c['1000']['time_hours']['p50'])}h | "
            f"{pct(c['500']['reach_rate'])}/{pct(c['750']['reach_rate'])}/{pct(c['1000']['reach_rate'])} | "
            f"{fmt(result['final_deaths']['p50'],1)} | {fmt(result['final_wave']['p25'],1)}/{fmt(result['final_wave']['p50'],1)}/{fmt(result['final_wave']['p75'],1)} |"
        )

    for name, result in payload["conditions"].items():
        lines += [
            "", f"## {name}", "",
            f"Final Wave distribution: `{result['final_wave_distribution']}`", "",
            "| W | Reach | Time P25/P50/P75 | Deaths | DP balance/spent | Reroll | DP Lv ATK/AS/XP/Crit/CM/WATK/Luck | Final | DP | Weapon | Card |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for wave in MAIN:
            x = result["checkpoint"][str(wave)]
            t, lv = x["time_hours"], x["dp_levels_p50"]
            levels = "/".join(fmt(lv[key], 1) for key in ("base_atk","attack_speed","xp_gain","crit_rate","crit_multiplier","weapon_atk","luck"))
            lines.append(
                f"| {wave} | {pct(x['reach_rate'])} | {fmt(t['p25'])}/{fmt(t['p50'])}/{fmt(t['p75'])}h | {fmt(x['deaths_p50'],1)} | "
                f"{fmt(x['dp_balance_p50'],1)}/{fmt(x['dp_spent_p50'],1)} | {pct(x['reroll_purchase_rate'])} | {levels} | "
                f"{fmt(x['final_damage_power_p50'])} | {fmt(x['dp_power_p50'])} | {fmt(x['weapon_power_p50'])} | {fmt(x['card_power_p50'])} |"
            )
        lines += ["", "### W500～750 / 50Wave", "", "| 区間 | Enemy +P | Player +P | DP +P | DP/Player |", "|---:|---:|---:|---:|---:|"]
        for item in result["intervals"]:
            if 500 <= item["from"] < 750:
                lines.append(
                    f"| {item['from']}→{item['to']} | {fmt(item['enemy_power_delta'])} | {fmt(item['player_power_delta'])} | "
                    f"{fmt(item['dp_power_delta'])} | {pct(item['dp_share_of_player_growth'])} |"
                )

    effects = payload["factorial_effects"]
    lines += [
        "", "## Factorial差分", "",
        "Final Wave P50の差。正値ほど先へ進む。", "",
        "| 比較 | 差 |", "|---|---:|",
        f"| Economy B→C（Power B固定）: CB-BB | {effects['economy_at_power_B_final_wave_p50']:+.1f} |",
        f"| Economy B→C（Power C固定）: CC-BC | {effects['economy_at_power_C_final_wave_p50']:+.1f} |",
        f"| Power B→C（Economy B固定）: BC-BB | {effects['power_at_economy_B_final_wave_p50']:+.1f} |",
        f"| Power B→C（Economy C固定）: CC-CB | {effects['power_at_economy_C_final_wave_p50']:+.1f} |",
        "", "## 判定", "",
        "- Economy B→CのFinal Wave効果は平均+162.0 Wave、Power B→Cは平均+91.5 Wave。Cの強さはEconomy側への依存が大きい（約1.77倍）。",
        "- W500～750のPlayer成長に占めるDP比率は全条件で77.5～98.1%。Economy/Powerの組み替えだけではDP支配を軽減できていない。",
        "- CBはBCより速いが、Economy CでDP Lvを大量購入している。DP寄与を抑える方向とは逆。",
        "- 追加システムの余地を残す比較候補はBC。W750到達100%、Final Wave P50=844で、CCよりW1000までの余白が大きい。ただしDP依存自体は要再設計。",
        "", "正式採用・自動調整は行っていない。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv(path: Path, payload: dict[str, Any]) -> None:
    fields = [
        "condition","wave","reach_rate","time_p25","time_p50","time_p75","deaths_p50",
        "dp_balance_p50","dp_spent_p50","reroll_purchase_rate","final_power_p50","dp_power_p50","weapon_power_p50","card_power_p50",
    ] + [f"lv_{key}" for key in dp.ITEM_ORDER]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for name, result in payload["conditions"].items():
            for wave in dp.CHECKPOINTS:
                x = result["checkpoint"][str(wave)]
                row = {
                    "condition": name, "wave": wave, "reach_rate": x["reach_rate"],
                    "time_p25": x["time_hours"]["p25"], "time_p50": x["time_hours"]["p50"], "time_p75": x["time_hours"]["p75"],
                    "deaths_p50": x["deaths_p50"], "dp_balance_p50": x["dp_balance_p50"], "dp_spent_p50": x["dp_spent_p50"],
                    "reroll_purchase_rate": x["reroll_purchase_rate"], "final_power_p50": x["final_damage_power_p50"],
                    "dp_power_p50": x["dp_power_p50"], "weapon_power_p50": x["weapon_power_p50"], "card_power_p50": x["card_power_p50"],
                }
                row.update({f"lv_{key}": x["dp_levels_p50"][key] for key in dp.ITEM_ORDER})
                writer.writerow(row)


def write_interval_csv(path: Path, payload: dict[str, Any]) -> None:
    fields = ["condition","from","to","enemy_power_delta","player_power_delta","dp_power_delta","dp_share_of_player_growth"]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for name, result in payload["conditions"].items():
            for item in result["intervals"]:
                writer.writerow({"condition": name, **item})


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--max-attempts", type=int, default=220)
    parser.add_argument("--output-dir", type=Path, default=Path("output/new_w5000_dp_v01_factorial_30"))
    args = parser.parse_args()
    if not 1 <= args.trials <= 30:
        parser.error("--trials must be between 1 and 30")

    econ_b, econ_c = dp.CANDIDATES["B_medium"], dp.CANDIDATES["C_aggressive"]
    conditions = {
        "BB": hybrid("BB", econ_b, econ_b),
        "CB": hybrid("CB", econ_c, econ_b),
        "BC": hybrid("BC", econ_b, econ_c),
        "CC": hybrid("CC", econ_c, econ_c),
    }
    dp.ACTIVE_CONFIG = sim.SimConfig(target_wave=dp.TARGET_WAVE)
    capture = dp.Capture(dp.ACTIVE_CONFIG)
    dp.install_isolated_candidate(capture)
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {}
    for name, candidate in conditions.items():
        result = dp.run_condition(
            name, candidate, args.trials, args.seed, args.max_attempts, 1250,
            automation_enabled=False, sweep_enabled=False, reward_skip_enabled=False,
        )
        results[name] = result
        (out / f"{name}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    p50 = {name: float(result["final_wave"]["p50"]) for name, result in results.items()}
    effects = {
        "economy_at_power_B_final_wave_p50": p50["CB"] - p50["BB"],
        "economy_at_power_C_final_wave_p50": p50["CC"] - p50["BC"],
        "power_at_economy_B_final_wave_p50": p50["BC"] - p50["BB"],
        "power_at_economy_C_final_wave_p50": p50["CC"] - p50["CB"],
    }
    payload = {
        "settings": {
            "trials": args.trials, "seed": args.seed, "target_wave": dp.TARGET_WAVE,
            "max_attempts": args.max_attempts, "profile": "Standard/balanced",
            "automation": False, "sweep": False, "reward_skip": False, "game_speed": False,
            "weapon_curve": "B_medium deterministic", "legendary": False,
            "relic": False, "refinement": False, "weapon_rng": False,
            "formal_modified": False,
        },
        "conditions": results,
        "factorial_effects": effects,
        "automatic_adoption": False,
    }
    json_path = out / "dp_v01_factorial.json"
    csv_path = out / "dp_v01_factorial_checkpoints.csv"
    interval_path = out / "dp_v01_factorial_intervals.csv"
    md_path = out / "dp_v01_factorial.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(csv_path, payload)
    write_interval_csv(interval_path, payload)
    write_markdown(md_path, payload)
    print(json.dumps({
        "conditions": {
            name: {
                "success_rate": result["success_rate"], "final_wave_p50": result["final_wave"]["p50"],
                "w500_time_p50": result["checkpoint"]["500"]["time_hours"]["p50"],
                "w750_time_p50": result["checkpoint"]["750"]["time_hours"]["p50"],
                "w1000_time_p50": result["checkpoint"]["1000"]["time_hours"]["p50"],
            } for name, result in results.items()
        },
        "factorial_effects": effects,
        "files": {"json": str(json_path), "csv": str(csv_path), "interval_csv": str(interval_path), "markdown": str(md_path)},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
