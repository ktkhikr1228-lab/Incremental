#!/usr/bin/env python3
"""Paired A/B/C test-only Weapon Base ATK scale probe for new W5000 candidate."""

from __future__ import annotations

import argparse
import collections
import copy
import csv
from dataclasses import replace
import json
import math
import random
import sys
from pathlib import Path
from typing import Any

import simulate_first_prestige_v1 as sim
import simulate_new_w5000_common_uncommon as base
import simulate_new_w5000_common_uncommon_rare_epic as epic


CHECKPOINTS = (500, 750, 800, 900, 1000, 1250, 1500, 2000, 2500)
DEFAULT_SEED = 20260828
CURVES = {
    "A_weak": ((10,1.0),(100,10.0),(500,300.0),(750,3000.0),(800,6000.0),(1000,30000.0),(1500,3e5),(2000,3e6),(2500,3e7)),
    "B_medium": ((10,1.0),(100,15.0),(500,500.0),(750,5000.0),(800,10000.0),(1000,50000.0),(1500,5e5),(2000,5e6),(2500,5e7)),
    "C_strong": ((10,1.0),(100,20.0),(500,800.0),(750,8000.0),(800,15000.0),(1000,80000.0),(1500,8e5),(2000,8e6),(2500,8e7)),
}

ACTIVE_CURVE: tuple[tuple[int,float], ...] = CURVES["A_weak"]


def weapon_base_atk(wave: int) -> float:
    if wave < 10:
        return 0.0
    if wave >= ACTIVE_CURVE[-1][0]:
        return ACTIVE_CURVE[-1][1]
    for (left_wave,left_value),(right_wave,right_value) in zip(ACTIVE_CURVE,ACTIVE_CURVE[1:]):
        if left_wave <= wave <= right_wave:
            fraction=(wave-left_wave)/(right_wave-left_wave)
            return 10**(math.log10(left_value)+(math.log10(right_value)-math.log10(left_value))*fraction)
    return ACTIVE_CURVE[0][1]


def weapon_terms(run: sim.RunState, raw_base_atk: float) -> tuple[float,float,float,float]:
    if run.kills < 10:
        return 0.0, 0.0, raw_base_atk, 0.0
    c_amp,u_amp,_=epic.amps(run.counts)
    additive=(0.25*c_amp*run.counts.get("weapon_training",0)+0.10*u_amp*run.counts.get("overclock",0))
    effective=weapon_base_atk(run.kills)*(1.0+additive)*1.10
    total=raw_base_atk+effective
    return weapon_base_atk(run.kills),effective,total,effective/total


def weapon_snapshot(run: sim.RunState, permanent: sim.PermanentState, boss: bool, config: sim.SimConfig) -> sim.Snapshot:
    snapshot=epic.candidate_snapshot(run,permanent,boss,config)
    raw=10**snapshot.base_attack_power
    _,effective,total,_=weapon_terms(run,raw)
    delta=math.log10(total)-snapshot.base_attack_power
    return replace(snapshot,log_dps=snapshot.log_dps+delta,base_attack_power=math.log10(total),weapon_power=delta)


WEAPON_CARDS=tuple(
    sim.card("weapon_training","Weapon Training","C","damage") if item.key=="weapon_training" else item
    for item in epic.ALL_CARDS
)
CARD_BY_KEY={item.key:item for item in WEAPON_CARDS}


class WeaponCapture(epic.EpicCapture):
    def compute(self,run:sim.RunState,permanent:sim.PermanentState,boss:bool,config:sim.SimConfig)->sim.Snapshot:
        wave=int(run.kills); already=wave in self.current
        snapshot=super().compute(run,permanent,boss,config)
        if not already and wave in self.current:
            _,effective,total,share=weapon_terms(run,10**(snapshot.base_attack_power-snapshot.weapon_power))
            self.current[wave].update({
                "raw_base_atk": total-effective,
                "effective_weapon_atk": effective,
                "weapon_share": share,
            })
        return snapshot


def percentile(values:list[float],q:float)->float|None:
    return base.percentile(values,q)


def stats(values:list[float])->dict[str,float|None]:
    return {"p25":percentile(values,.25),"p50":percentile(values,.50),"p75":percentile(values,.75)}


def run_condition(name:str,curve:tuple[tuple[int,float],...],trials:int,seed:int,max_attempts:int)->dict[str,Any]:
    global ACTIVE_CURVE
    ACTIVE_CURVE=curve
    config=sim.SimConfig(max_attempts=max_attempts,automation_enabled=True,interval_enabled=False,game_speed_enabled=True,initial_card_points_enabled=False,sweep_enabled=True,reward_skip_enabled=True,defense=sim.DefenseConfig(enabled=False),target_wave=2500,card_upgrade_cap=0,relic_selection_enabled=False,exponential_core_multiplier=1.0)
    observer=epic.Observer(); capture=WeaponCapture(config)
    base.NEW_CARDS=WEAPON_CARDS; base.CARD_BY_KEY=CARD_BY_KEY; base.candidate_snapshot=weapon_snapshot; base.full_window_power=epic.full_window_power; base.CHECKPOINTS=CHECKPOINTS
    base.install_candidate_pool(capture)
    sim.CHECKPOINTS=CHECKPOINTS; sim.REACH_WAVES=CHECKPOINTS; sim.VARIANT_REACH_WAVES=CHECKPOINTS
    sim.draw_hand=epic.draw_hand_current_wave; sim.available_cards=epic.available_cards; sim.process_guaranteed_choices=epic.guaranteed_choices; sim.acquire_card=observer.acquire
    sim.dynamic_damage_log=epic.dynamic_damage_log; sim.temporal_integral=epic.temporal_integral; sim.temporal_lookup=epic.temporal_lookup; sim.time_to_kill_with_defense=epic.recording_time_to_kill_with_defense
    sim.forge_starting_weapon=lambda rng,permanent,run,config:None; sim.process_boss_loot=lambda rng,permanent,run,wave,config:False; sim.acquire_relic=lambda rng,permanent,config:None
    sim.limit_amplification=lambda counts:1.15 if counts.get("limit_break",0) else 1.0
    rows=[]
    for trial in range(trials):
        capture.reset(); observer.reset(); epic.FAILURE_SINK.clear(); rng=random.Random(seed+1_000_000+trial)
        result=sim.run_trial(rng,"balanced",config,allow_overdrive=False)
        rows.append({"trial":trial,"result":result,"checkpoint":copy.deepcopy(capture.current),"failures":copy.deepcopy(epic.FAILURE_SINK)})
    checkpoints={}
    for wave in CHECKPOINTS:
        reached=[row for row in rows if wave in row["checkpoint"]]; states=[row["checkpoint"][wave] for row in reached]
        def sv(key:str)->dict[str,float|None]: return stats([float(state[key]) for state in states if state.get(key) is not None])
        checkpoints[str(wave)]={
            "reach_rate":len(states)/trials,
            "arrival_hours":stats([row["result"].reach_seconds[wave]/3600 for row in reached]),
            "final_damage_power":sv("final_damage_power"),
            "enemy_power":sim.configured_enemy_power(wave,config),
            "damage_minus_enemy":stats([float(state["final_damage_power"]-sim.configured_enemy_power(wave,config)) for state in states]),
            "raw_base_atk":sv("raw_base_atk"),"effective_weapon_atk":sv("effective_weapon_atk"),"weapon_share":sv("weapon_share"),
            "common_cards":sv("common_cards"),"uncommon_cards":sv("uncommon_cards"),"rare_cards":sv("rare_cards"),"epic_cards":sv("epic_cards"),
        }
    best=[float(row["result"].best_failed_wave if not row["result"].success else 2500) for row in rows]
    failures=[failure for row in rows for failure in row["failures"]]
    bands=collections.Counter((failure["failure_wave"]//25)*25 for failure in failures if failure["failure_wave"]>=500)
    return {
        "condition":name,"curve":curve,"trials":trials,
        "success_rate":sum(row["result"].success for row in rows)/trials,
        "deaths":stats([float(row["result"].deaths) for row in rows]),
        "final_wave":stats(best),
        "final_wave_distribution":dict(sorted(collections.Counter(int(value) for value in best).items())),
        "first_wall_wave_p50":percentile([float(row["result"].best_failed_wave) for row in rows if not row["result"].success],.50),
        "failure_wave_bands":dict(sorted(bands.items(),key=lambda item:(-item[1],item[0]))[:12]),
        "checkpoint":checkpoints,
    }


def fmt(value:float|None,digits:int=3)->str:
    return "—" if value is None else f"{value:.{digits}f}"


def sci(value:float|None)->str:
    return "—" if value is None else f"{value:.3e}"


def write_markdown(path:Path,payload:dict[str,Any])->None:
    lines=["# 新W5000候補 Weapon Base ATKスケール探索","",f"30 trials / condition / Standard bot / seed {payload['seed']}","","Weapon rarity / affix / drop RNG / pity, Relic, Legendary, refinement: OFF","","※ Final Damage Power - Enemy PowerはDPSとHP Powerの直接差。制限時間分の総Damage余裕ではない。"]
    for name,result in payload["conditions"].items():
        lines += ["",f"## {name}","",f"Success: {result['success_rate']:.1%} / Deaths P50: {fmt(result['deaths']['p50'],1)} / Final Wave P25/P50/P75: {fmt(result['final_wave']['p25'],1)}/{fmt(result['final_wave']['p50'],1)}/{fmt(result['final_wave']['p75'],1)} / First wall P50: {fmt(result['first_wall_wave_p50'],1)}","",f"Failure bands (25 Wave): {result['failure_wave_bands']}","","| W | Reach | Time P25/P50/P75 | Final Power | Enemy | Margin | Raw Base | Effective Weapon | Share | C/U/R/E |","|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for wave in CHECKPOINTS:
            x=result["checkpoint"][str(wave)]; t=x["arrival_hours"]
            lines.append(f"| {wave} | {x['reach_rate']:.1%} | {fmt(t['p25'])}/{fmt(t['p50'])}/{fmt(t['p75'])}h | {fmt(x['final_damage_power']['p50'])} | {fmt(x['enemy_power'])} | {fmt(x['damage_minus_enemy']['p50'])} | {sci(x['raw_base_atk']['p50'])} | {sci(x['effective_weapon_atk']['p50'])} | {fmt(x['weapon_share']['p50']*100 if x['weapon_share']['p50'] is not None else None,1)}% | {fmt(x['common_cards']['p50'],1)}/{fmt(x['uncommon_cards']['p50'],1)}/{fmt(x['rare_cards']['p50'],1)}/{fmt(x['epic_cards']['p50'],1)} |")
        w800=result["checkpoint"]["800"]; w900_enemy=result["checkpoint"]["900"]["enemy_power"]
        simple_factor=10**(w900_enemy-math.log10(10.0)-w800["final_damage_power"]["p50"])
        lines += ["",f"- 最終到達Wave分布: {result['final_wave_distribution']}",f"- W800の中央DPSを固定した単純換算で、W900通常敵を10秒で倒すには約×{simple_factor:.0f}の追加Base ATKが必要。"]
    none=payload.get("weapon_none_reference")
    lines += ["","## Weaponなし条件との差",""]
    if none:
        lines.append(f"- Weaponなし Final Wave P50: {none['p50']:.1f}")
        for name,result in payload["conditions"].items(): lines.append(f"- {name}: {result['final_wave']['p50']-none['p50']:+.1f} Wave")
    else: lines.append("- 参照ファイルなし")
    path.write_text("\n".join(lines)+"\n",encoding="utf-8")


def write_csv(path:Path,payload:dict[str,Any])->None:
    fields=["condition","wave","reach_rate","time_p25","time_p50","time_p75","final_power_p50","enemy_power","margin_p50","raw_base_atk_p50","effective_weapon_atk_p50","weapon_share_p50","common_p50","uncommon_p50","rare_p50","epic_p50"]
    with path.open("w",newline="",encoding="utf-8-sig") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields); writer.writeheader()
        for name,result in payload["conditions"].items():
            for wave in CHECKPOINTS:
                x=result["checkpoint"][str(wave)]; t=x["arrival_hours"]
                writer.writerow({"condition":name,"wave":wave,"reach_rate":x["reach_rate"],"time_p25":t["p25"],"time_p50":t["p50"],"time_p75":t["p75"],"final_power_p50":x["final_damage_power"]["p50"],"enemy_power":x["enemy_power"],"margin_p50":x["damage_minus_enemy"]["p50"],"raw_base_atk_p50":x["raw_base_atk"]["p50"],"effective_weapon_atk_p50":x["effective_weapon_atk"]["p50"],"weapon_share_p50":x["weapon_share"]["p50"],"common_p50":x["common_cards"]["p50"],"uncommon_p50":x["uncommon_cards"]["p50"],"rare_p50":x["rare_cards"]["p50"],"epic_p50":x["epic_cards"]["p50"]})


def main()->None:
    if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(); parser.add_argument("--trials",type=int,default=30); parser.add_argument("--seed",type=int,default=DEFAULT_SEED); parser.add_argument("--max-attempts",type=int,default=220); parser.add_argument("--output-dir",type=Path,default=Path("output/new_w5000_weapon_scale_30")); args=parser.parse_args()
    if not 1<=args.trials<=30:parser.error("--trials must be between 1 and 30")
    conditions={name:run_condition(name,curve,args.trials,args.seed,args.max_attempts) for name,curve in CURVES.items()}
    none_path=Path("output/new_w5000_common_uncommon_rare_epic_wave900_30/new_w5000_common_uncommon_rare_epic_wave900.json")
    none_ref=None
    if none_path.exists(): none_ref=json.loads(none_path.read_text(encoding="utf-8"))["summary"]["best_failed_wave"]
    payload={"seed":args.seed,"trials_per_condition":args.trials,"conditions":conditions,"weapon_none_reference":none_ref,"formal_modified":False,"automatic_balance":False}
    out=args.output_dir.resolve(); out.mkdir(parents=True,exist_ok=True); jp=out/"weapon_scale.json"; cp=out/"weapon_scale_checkpoints.csv"; mp=out/"weapon_scale.md"
    jp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8"); write_csv(cp,payload); write_markdown(mp,payload)
    print(json.dumps({"conditions":{name:{"success_rate":x["success_rate"],"final_wave":x["final_wave"],"first_wall_wave_p50":x["first_wall_wave_p50"],"deaths":x["deaths"]} for name,x in conditions.items()},"weapon_none_reference":none_ref,"files":{"json":str(jp),"csv":str(cp),"markdown":str(mp)}},ensure_ascii=False,indent=2))


if __name__=="__main__":main()
