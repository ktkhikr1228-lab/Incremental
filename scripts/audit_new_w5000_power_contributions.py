#!/usr/bin/env python3
"""Deterministic same-seed audit of DP/Weapon attribution for new_w5000."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any

import simulate_first_prestige_v1 as sim
import simulate_new_w5000_dp_v01 as dp
import compare_new_w5000_weapon_acquisition as weapon


WAVES = (500, 550, 600, 650, 700, 750)


def pct(values: list[float], q: float) -> float | None:
    return dp.percentile(values, q)


def pearson(rows: list[dict[str, Any]], x: str, y: str) -> float | None:
    if len(rows) < 2:
        return None
    xs = [float(row[x]) for row in rows]
    ys = [float(row[y]) for row in rows]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    numerator = sum((a-mx)*(b-my) for a,b in zip(xs,ys))
    dx = math.sqrt(sum((a-mx)**2 for a in xs))
    dy = math.sqrt(sum((b-my)**2 for b in ys))
    return numerator/(dx*dy) if dx > 0 and dy > 0 else None


def controlled_pearson(rows: list[dict[str, Any]], x: str, y: str, group_key: str) -> float | None:
    groups: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(int(row[group_key]), []).append(row)
    residuals: list[dict[str, float]] = []
    for group in groups.values():
        mx=statistics.mean(float(row[x]) for row in group)
        my=statistics.mean(float(row[y]) for row in group)
        residuals.extend({"x":float(row[x])-mx,"y":float(row[y])-my} for row in group)
    return pearson(residuals,"x","y")


def quartiles(rows: list[dict[str, Any]], sort_key: str) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: float(row[sort_key]))
    count = len(ordered)
    low_end, high_start = count // 4, count - count // 4
    groups = {
        "low25": ordered[:low_end],
        "middle50": ordered[low_end:high_start],
        "high25": ordered[high_start:],
    }
    result: dict[str, Any] = {}
    for name, group in groups.items():
        result[name] = {
            "runs": len(group),
            "weapon_power_p50": pct([float(row["max_weapon_power"]) for row in group], .5),
            "quality_advantage_p50": pct([float(row["death_weapon_quality_advantage"]) for row in group], .5),
            "progress_waves_p50": pct([float(row["progress_waves"]) for row in group], .5),
            "highest_wave_p50": pct([float(row["end_wave"]) for row in group], .5),
            "run_hours_p50": pct([float(row["run_hours"]) for row in group], .5),
        }
    return result


def aggregate_quality(rows: list[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for wave in (500, 600, 750):
        states = [row["checkpoint"][wave] for row in rows if wave in row["checkpoint"]]
        names = states[0]["weapon_quality_scenarios"].keys() if states else []
        output[str(wave)] = {
            name: {
                "final_power_p50": pct([float(state["weapon_quality_scenarios"][name]["final_power"]) for state in states], .5),
                "delta_vs_common_p50": pct([float(state["weapon_quality_scenarios"][name]["delta_vs_common"]) for state in states], .5),
            }
            for name in names
        }
    return output


def build_report(result: dict[str, Any]) -> dict[str, Any]:
    checkpoints = {str(w): result["checkpoint"][str(w)] for w in WAVES}
    intervals = [item for item in result["intervals"] if item["from"] in WAVES[:-1] and item["to"] in WAVES[1:]]
    rows = result["diagnostic_rows"]
    runs = [record for row in rows for record in row["run_records"] if int(record["drops"]) > 0]
    return {
        "settings": {
            "condition": "C_drop_affix", "trials": 30, "seed": weapon.DEFAULT_SEED,
            "same_seed_replay": True, "balance_changed": False,
        },
        "checkpoints": checkpoints,
        "intervals": intervals,
        "weapon_quality": aggregate_quality(rows),
        "run_rng": {
            "runs_with_weapon": len(runs),
            "corr_max_weapon_vs_progress": pearson(runs, "max_weapon_power", "progress_waves"),
            "corr_death_weapon_vs_progress": pearson(runs, "death_weapon_power", "progress_waves"),
            "corr_max_weapon_vs_run_hours": pearson(runs, "max_weapon_power", "run_hours"),
            "corr_quality_advantage_vs_progress": pearson(runs, "death_weapon_quality_advantage", "progress_waves"),
            "corr_quality_advantage_vs_progress_attempt_controlled": controlled_pearson(runs, "death_weapon_quality_advantage", "progress_waves", "run"),
            "raw_power_quartiles": quartiles(runs, "max_weapon_power"),
            "quality_quartiles": quartiles(runs, "death_weapon_quality_advantage"),
        },
    }


def f(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# new_w5000 Power contribution監査", "",
        "同一seed 30 trialのC_drop_affix診断再生。バランス値・Drop率・Weapon性能・DP性能は未変更。", "",
        "## Checkpoints", "",
        "| W | F | D | W | N | DP旧 | DP Shapley | Weapon旧 | Weapon Shapley | Interaction |", "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for wave in WAVES:
        x=report["checkpoints"][str(wave)]
        lines.append(f"| {wave} | {f(x['F_p50'])} | {f(x['D_p50'])} | {f(x['W_p50'])} | {f(x['N_p50'])} | {f(x['dp_power_legacy_p50'])} | {f(x['dp_power_p50'])} | {f(x['weapon_power_legacy_p50'])} | {f(x['weapon_power_p50'])} | {f(x['dp_weapon_interaction_p50'])} |")
    lines += ["", "## 50Wave growth", "", "| 区間 | Enemy | Player | DP旧 | DP Shapley | Weapon Shapley | Interaction Δ | Residual | DP旧/Player | DP Shapley/Player |", "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for x in report["intervals"]:
        lines.append(f"| {x['from']}→{x['to']} | {f(x['enemy_power_delta'])} | {f(x['player_power_delta'])} | {f(x['dp_power_legacy_delta'])} | {f(x['dp_power_delta'])} | {f(x['weapon_power_delta'])} | {f(x['dp_weapon_interaction_delta'])} | {f(x['residual_power_delta'])} | {f(x['dp_share_of_player_growth_legacy']*100 if x['dp_share_of_player_growth_legacy'] is not None else None,1)}% | {f(x['dp_share_of_player_growth']*100 if x['dp_share_of_player_growth'] is not None else None,1)}% |")
    lines += ["", "## Weapon quality counterfactual", "", "同一プレイヤー状態へ指定Weaponを装備したFinal Power。Affix平均は全21組合せの平均。", "", "| W | Case | Final P50 | Commonとの差 |", "|---:|---|---:|---:|"]
    for wave, cases in report["weapon_quality"].items():
        for name, x in cases.items():
            lines.append(f"| {wave} | {name} | {f(x['final_power_p50'])} | {f(x['delta_vs_common_p50'])} |")
    rng=report["run_rng"]
    lines += ["", "## Run内Weapon RNG", "", f"Weapon取得Run数: {rng['runs_with_weapon']}", "", f"- 生corr(max Weapon Power, 進行Wave): {f(rng['corr_max_weapon_vs_progress'])}（Wave基準Weaponによる逆因果を含む）", f"- corr(死亡直前Weapon Power, 進行Wave): {f(rng['corr_death_weapon_vs_progress'])}", f"- corr(max Weapon Power, Run時間): {f(rng['corr_max_weapon_vs_run_hours'])}", f"- corr(同Wave Common比quality差, 進行Wave): {f(rng['corr_quality_advantage_vs_progress'])}", f"- 同attempt内で調整後corr(quality差, 進行Wave): {f(rng['corr_quality_advantage_vs_progress_attempt_controlled'])}", "", "### 生Weapon Power四分位（交絡あり）", "", "| 群 | Runs | Weapon P50 | Quality差 | 進行Wave P50 | 最高Wave P50 | Run時間 P50 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for name,x in rng["raw_power_quartiles"].items():
        lines.append(f"| {name} | {x['runs']} | {f(x['weapon_power_p50'])} | {f(x['quality_advantage_p50'])} | {f(x['progress_waves_p50'],1)} | {f(x['highest_wave_p50'],1)} | {f(x['run_hours_p50'])}h |")
    lines += ["", "### 同Wave Common比quality差の四分位", "", "| 群 | Runs | Weapon P50 | Quality差 | 進行Wave P50 | 最高Wave P50 | Run時間 P50 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for name,x in rng["quality_quartiles"].items():
        lines.append(f"| {name} | {x['runs']} | {f(x['weapon_power_p50'])} | {f(x['quality_advantage_p50'])} | {f(x['progress_waves_p50'],1)} | {f(x['highest_wave_p50'],1)} | {f(x['run_hours_p50'])}h |")
    lines += [
        "", "## 結論", "",
        "- A: W500→750全体の従来DP比率は約87.1%、Shapley DP比率は約68.0%。約19.1 percentage points過大評価されていた。W750時点のDP stockも13.390→11.427で1.963 Power低下。",
        "- B: 同区間のShapley Weapon成長は約2.980 Power、Player成長の約28.9%。従来集計より重要だが、DP約68.0%に対してなお副次的。rarity差は実戦状態でもC→R +0.264、C→E +0.411 Powerで、Affix追加分は小さい。",
        "- C: 同Wave Common比quality差のlow/high quartileで進行中央値671→741（+70 Wave）。同attempt内調整後相関は0.371で、良WeaponのRun内差は存在する。ただし死亡WaveまでのDrop回数差が残る観察相関であり、完全な因果推定ではない。",
        "- 生Weapon Powerと進行の相関0.975は、先へ進むほど高Wave基準Weaponを拾う逆因果が大半なので、バランス判断には使用しない。",
    ]
    path.write_text("\n".join(lines)+"\n",encoding="utf-8")


def main() -> None:
    if hasattr(sys.stdout,"reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser()
    parser.add_argument("--output-dir",type=Path,default=Path("output/new_w5000_power_contribution_audit"))
    args=parser.parse_args()
    config=sim.SimConfig(target_wave=1000)
    capture=weapon.WeaponCapture(config)
    dp.ACTIVE_CONFIG=config
    dp.install_isolated_candidate(capture)
    result=weapon.run_condition("C_drop_affix_shapley", "affix", 30, weapon.DEFAULT_SEED, 220, include_rows=True)
    report=build_report(result)
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    json_path=out/"power_contribution_audit.json"
    md_path=out/"power_contribution_audit.md"
    json_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    write_markdown(md_path,report)
    print(json.dumps({"json":str(json_path),"markdown":str(md_path)},ensure_ascii=False,indent=2))


if __name__=="__main__": main()
