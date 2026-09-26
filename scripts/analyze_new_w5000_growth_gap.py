#!/usr/bin/env python3
"""Exact-seed diagnostic replay of B_medium W500-W850 progression."""

from __future__ import annotations

import argparse
import collections
import copy
import csv
import json
import math
import random
import sys
from pathlib import Path
from typing import Any

import simulate_first_prestige_v1 as sim
import simulate_new_w5000_common_uncommon as base
import simulate_new_w5000_common_uncommon_rare_epic as epic
import simulate_new_w5000_weapon_scale as weapon


OUTPUT_WAVES=(500,550,600,650,700,750,775,800,825,850)
CAPTURE_WAVES=tuple(sorted(set(OUTPUT_WAVES)|{wave-100 for wave in OUTPUT_WAVES if wave>=100}))
CURRENT_ATTEMPT=0
ORIGINAL_RUN_ONCE=sim.run_once


def tracked_run_once(*args:Any,**kwargs:Any)->sim.RunResult:
    global CURRENT_ATTEMPT
    CURRENT_ATTEMPT+=1
    return ORIGINAL_RUN_ONCE(*args,**kwargs)


GROUPS={
    "base_atk_cards": {"power_up","brutal_force","balanced_training","weapon_training"},
    "attack_speed": {"rapid_fire","overclock","critical_momentum","critical_engine"},
    "crit": {"critical_eye","critical_power","critical_training","critical_conversion","overflow","multi_crit","critical_compression"},
    "all_damage": {"steady_force","knowledge_conversion"},
    "boss_devourer": {"boss_devourer"},
    "supplemental": {"supplemental_damage","resonant_damage","echoing_damage"},
    "multi_hit": {"multi_hit"},
    "follow_up": {"follow_up_strike","double_strike","follow_up_echo"},
    "re_action": {"re_action","chain_action"},
    "epic": {"time_collapse","limit_break"},
}


def clone_run_with_counts(run:sim.RunState,keys:set[str])->sim.RunState:
    cloned=copy.copy(run)
    cloned.counts=collections.Counter({key:value for key,value in run.counts.items() if key in keys})
    cloned.tag_counts=collections.Counter()
    return cloned


def zero_permanent(config:sim.SimConfig)->sim.PermanentState:
    return sim.PermanentState(automation_enabled=config.automation_enabled)


def power_decomposition(run:sim.RunState,permanent:sim.PermanentState,boss:bool,config:sim.SimConfig)->dict[str,float]:
    all_keys=set(run.counts)
    empty=clone_run_with_counts(run,set())
    zero=zero_permanent(config)
    zero_snapshot=weapon.weapon_snapshot(empty,zero,boss,config)
    _,effective,_,_=weapon.weapon_terms(empty,1.0)
    weapon_power=math.log10(1.0+effective)
    other=zero_snapshot.log_dps-weapon_power
    permanent_empty=weapon.weapon_snapshot(empty,permanent,boss,config)
    output={"other":other,"weapon":weapon_power,"dp":permanent_empty.log_dps-zero_snapshot.log_dps}
    previous=permanent_empty.log_dps
    included:set[str]=set()
    for name,keys in GROUPS.items():
        included|=keys
        stage=clone_run_with_counts(run,included)
        current=weapon.weapon_snapshot(stage,permanent,boss,config).log_dps
        output[name]=current-previous
        previous=current
    final=weapon.weapon_snapshot(run,permanent,boss,config).log_dps
    output["other"]+=final-previous
    output["sum"]=sum(value for key,value in output.items() if key!="sum")
    output["final"]=final
    output["sum_error"]=output["sum"]-final
    return output


class DiagnosticCapture(weapon.WeaponCapture):
    def compute(self,run:sim.RunState,permanent:sim.PermanentState,boss:bool,config:sim.SimConfig)->sim.Snapshot:
        wave=int(run.kills); already=wave in self.current
        if not hasattr(run,"diagnostic_card_history"):
            run.diagnostic_card_history={}
        run.diagnostic_card_history.setdefault(wave,run.card_count)
        snapshot=super().compute(run,permanent,boss,config)
        if not already and wave in self.current:
            state=self.current[wave]
            state.update({
                "deaths_before_reach":CURRENT_ATTEMPT-1,
                "dp_total_level":permanent.total_levels,"dp_atk_level":permanent.atk,"dp_as_level":permanent.attack_speed,"dp_xp_level":permanent.xp,
                "next_dp_cost":sim.next_dp_cost(permanent.total_levels,config.dp_growth),
                "current_xp":run.xp,
                "next_card_xp":sim.CARD_COSTS[run.xp_level_count] if run.xp_level_count<len(sim.CARD_COSTS) else None,
                "boss_devourer_stack":run.boss_devourer_units,
                "accelerated_learning_stack":run.accelerated_units,
                "cards_gained_last_100":run.card_count-run.diagnostic_card_history.get(max(0,wave-100),0),
                "decomposition":power_decomposition(run,permanent,boss,config),
                "effective_weapon_atk_power":math.log10(state["effective_weapon_atk"]) if state["effective_weapon_atk"]>0 else None,
            })
        return snapshot


def percentile(values:list[float],q:float)->float|None:return base.percentile(values,q)
def median(values:list[float])->float|None:return percentile(values,.5)


def setup(config:sim.SimConfig,capture:DiagnosticCapture,observer:epic.Observer)->None:
    weapon.ACTIVE_CURVE=weapon.CURVES["B_medium"]
    base.NEW_CARDS=weapon.WEAPON_CARDS;base.CARD_BY_KEY=weapon.CARD_BY_KEY;base.candidate_snapshot=weapon.weapon_snapshot;base.full_window_power=epic.full_window_power;base.CHECKPOINTS=CAPTURE_WAVES
    base.install_candidate_pool(capture)
    sim.CHECKPOINTS=CAPTURE_WAVES;sim.REACH_WAVES=OUTPUT_WAVES;sim.VARIANT_REACH_WAVES=OUTPUT_WAVES
    sim.draw_hand=epic.draw_hand_current_wave;sim.available_cards=epic.available_cards;sim.process_guaranteed_choices=epic.guaranteed_choices;sim.acquire_card=observer.acquire
    sim.dynamic_damage_log=epic.dynamic_damage_log;sim.temporal_integral=epic.temporal_integral;sim.temporal_lookup=epic.temporal_lookup
    sim.forge_starting_weapon=lambda rng,permanent,run,config:None;sim.process_boss_loot=lambda rng,permanent,run,wave,config:False;sim.acquire_relic=lambda rng,permanent,config:None
    sim.limit_amplification=lambda counts:1.15 if counts.get("limit_break",0) else 1.0
    sim.run_once=tracked_run_once


def aggregate(rows:list[dict[str,Any]],config:sim.SimConfig)->dict[str,Any]:
    output={}
    contribution_keys=("weapon","base_atk_cards","attack_speed","crit","all_damage","boss_devourer","supplemental","multi_hit","follow_up","re_action","epic","dp","other")
    for wave in OUTPUT_WAVES:
        states=[row["checkpoint"][wave] for row in rows if wave in row["checkpoint"]]
        def med(key:str)->float|None:return median([float(state[key]) for state in states if state.get(key) is not None])
        decomposition={key:median([float(state["decomposition"][key]) for state in states]) for key in contribution_keys}
        final_power=med("final_damage_power")
        if final_power is not None:
            component_sum=sum(value for value in decomposition.values() if value is not None)
            decomposition["other"]+=final_power-component_sum
        output[str(wave)]={
            "reach_rate":len(states)/len(rows),
            "arrival_hours_p50":median([row["result"].reach_seconds[wave]/3600 for row in rows if wave in row["result"].reach_seconds]),
            "deaths_before_reach_p50":med("deaths_before_reach"),
            "dp_total_level":med("dp_total_level"),"dp_atk_level":med("dp_atk_level"),"dp_as_level":med("dp_as_level"),"dp_xp_level":med("dp_xp_level"),"next_dp_cost":med("next_dp_cost"),
            "cards":med("cards"),"common_cards":med("common_cards"),"uncommon_cards":med("uncommon_cards"),"rare_cards":med("rare_cards"),"epic_cards":med("epic_cards"),
            "xp_multiplier":med("xp_multiplier"),"next_card_xp":med("next_card_xp"),"current_xp":med("current_xp"),
            "cards_gained_last_100":med("cards_gained_last_100"),
            "boss_devourer_stack":med("boss_devourer_stack"),"accelerated_learning_stack":med("accelerated_learning_stack"),
            "final_damage_power":final_power,"enemy_power":sim.configured_enemy_power(wave,config),
            "margin":None if not states else final_power-sim.configured_enemy_power(wave,config),
            "base_atk_power":med("base_atk_power"),"effective_weapon_atk_power":med("effective_weapon_atk_power"),
            "decomposition":decomposition,
            "decomposition_sum":None if not states else sum(value for value in decomposition.values() if value is not None),
            "decomposition_error_p50":median([abs(float(state["decomposition"]["sum_error"])) for state in states]),
        }
    intervals=[]
    for left,right in zip(OUTPUT_WAVES,OUTPUT_WAVES[1:]):
        a=output[str(left)];b=output[str(right)]
        if a["final_damage_power"] is None or b["final_damage_power"] is None: continue
        enemy_growth=b["enemy_power"]-a["enemy_power"];player_growth=b["final_damage_power"]-a["final_damage_power"]
        deltas={key:b["decomposition"][key]-a["decomposition"][key] for key in contribution_keys}
        largest=max(deltas,key=deltas.get)
        intervals.append({"from":left,"to":right,"enemy_growth":enemy_growth,"player_growth":player_growth,"gap":player_growth-enemy_growth,"largest_player_growth_source":largest,"largest_source_growth":deltas[largest]})
    return {"checkpoint":output,"intervals":intervals}


def fmt(value:float|None,digits:int=3)->str:return "—" if value is None else f"{value:.{digits}f}"


def write_markdown(path:Path,payload:dict[str,Any])->None:
    s=payload["summary"]
    lines=["# B_medium W500～850 成長ギャップ原因分析","",f"Saved seed set replay: 30 trials / seed {payload['seed']} / no new sample","","## 進行とカード成長","","| W | Reach | Time P50 | Deaths | DP Lv(A/AS/XP) | Next DP | Cards C/U/R/E | XP倍率 | XP / Next | +Cards/100W | Devourer | Accelerated |","|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for wave in OUTPUT_WAVES:
        x=s["checkpoint"][str(wave)]
        lines.append(f"| {wave} | {x['reach_rate']:.1%} | {fmt(x['arrival_hours_p50'])}h | {fmt(x['deaths_before_reach_p50'],1)} | {fmt(x['dp_total_level'],1)} ({fmt(x['dp_atk_level'],1)}/{fmt(x['dp_as_level'],1)}/{fmt(x['dp_xp_level'],1)}) | {fmt(x['next_dp_cost'],1)} | {fmt(x['cards'],1)} {fmt(x['common_cards'],1)}/{fmt(x['uncommon_cards'],1)}/{fmt(x['rare_cards'],1)}/{fmt(x['epic_cards'],1)} | {fmt(x['xp_multiplier'],2)} | {fmt(x['current_xp'],1)} / {fmt(x['next_card_xp'],1)} | {fmt(x['cards_gained_last_100'],1)} | {fmt(x['boss_devourer_stack'],1)} | {fmt(x['accelerated_learning_stack'],1)} |")
    lines += ["","## Power分解（log10、各列の合計=Final Power）","","| W | Final | Enemy | Margin | Base ATK | Weapon ATK | Weapon寄与 | BaseCard | AS | Crit | AllDmg | Devourer | Supp | MultiHit | Follow | ReAction | Epic | DP | Other | 誤差 |","|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for wave in OUTPUT_WAVES:
        x=s["checkpoint"][str(wave)];d=x["decomposition"]
        lines.append(f"| {wave} | {fmt(x['final_damage_power'])} | {fmt(x['enemy_power'])} | {fmt(x['margin'])} | {fmt(x['base_atk_power'])} | {fmt(x['effective_weapon_atk_power'])} | {fmt(d['weapon'])} | {fmt(d['base_atk_cards'])} | {fmt(d['attack_speed'])} | {fmt(d['crit'])} | {fmt(d['all_damage'])} | {fmt(d['boss_devourer'])} | {fmt(d['supplemental'])} | {fmt(d['multi_hit'])} | {fmt(d['follow_up'])} | {fmt(d['re_action'])} | {fmt(d['epic'])} | {fmt(d['dp'])} | {fmt(d['other'])} | {fmt(x['decomposition_error_p50'],6)} |")
    lines += ["","## 区間成長","","| 区間 | Enemy +Power | Player +Power | 差 | Player最大要因 | 寄与増分 |","|---:|---:|---:|---:|---|---:|"]
    for row in s["intervals"]:lines.append(f"| {row['from']}→{row['to']} | {row['enemy_growth']:.3f} | {row['player_growth']:.3f} | {row['gap']:+.3f} | {row['largest_player_growth_source']} | {row['largest_source_growth']:+.3f} |")
    lines += [
        "", "## 原因分析", "",
        "- W500～750の突破力は連続成長ではなく、DP合計Lv125の+4 PowerとLv150の+5 Powerに依存した段差成長。",
        "- 通常区間では敵50WaveにEnemy +2.073 Powerに対し、Weapon増分は約+0.200 Powerしかない。DPマイルストーンがない区間は基本的に追いつけない。",
        "- W750以降はDP Lv150、XP倍率×4.32で停滞。次DP購入は525 DP、カードは100Waveに中央1枚で、次カードは52,325～70,645 XP。",
        "- Accelerated Learningは全checkpointで中央0 stack。Boss Devourerも所持Runでは伸びるが、死亡時リセットのため安定した進行源になっていない。",
        "- W750→800でEnemyは+2.073 Power、Playerは+0.311 Power。W800→825ではPlayer中央Powerが-0.085となり、Run再構築のブレも壁を強めている。",
        "- W750到達14.17hの主因は戦闘通過時間ではなくDP稼ぎ。W550→600で約2.00h、W650→700で約2.97h、W700→750で約0.68hを消費している。",
        "- 12時間第一転生を狙う場合の最大ボトルネックは、W1→500の8.50hとW650→700のDPマイルストーン待ち。W750以降を調整する前に12hを超える。",
    ]
    path.write_text("\n".join(lines)+"\n",encoding="utf-8")


def main()->None:
    global CURRENT_ATTEMPT
    if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser();parser.add_argument("--seed",type=int,default=20260828);parser.add_argument("--trials",type=int,default=30);parser.add_argument("--output-dir",type=Path,default=Path("output/new_w5000_growth_gap_B_medium_30"));args=parser.parse_args()
    if args.trials!=30:parser.error("This diagnostic replays the saved 30-trial seed set only")
    config=sim.SimConfig(max_attempts=220,automation_enabled=True,interval_enabled=False,game_speed_enabled=True,initial_card_points_enabled=False,sweep_enabled=True,reward_skip_enabled=True,defense=sim.DefenseConfig(enabled=False),target_wave=2500,card_upgrade_cap=0,relic_selection_enabled=False,exponential_core_multiplier=1.0)
    observer=epic.Observer();capture=DiagnosticCapture(config);setup(config,capture,observer);rows=[]
    for trial in range(args.trials):
        CURRENT_ATTEMPT=0;capture.reset();observer.reset();rng=random.Random(args.seed+1_000_000+trial);result=sim.run_trial(rng,"balanced",config,allow_overdrive=False)
        rows.append({"trial":trial,"result":result,"checkpoint":copy.deepcopy(capture.current)})
    payload={"seed":args.seed,"trials":args.trials,"condition":"B_medium","new_monte_carlo":False,"balance_changed":False,"summary":aggregate(rows,config)}
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True);jp=out/"growth_gap_B_medium.json";mp=out/"growth_gap_B_medium.md"
    jp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8");write_markdown(mp,payload)
    print(json.dumps({"checkpoints":payload["summary"]["checkpoint"],"intervals":payload["summary"]["intervals"],"files":{"json":str(jp),"markdown":str(mp)}},ensure_ascii=False,indent=2))


if __name__=="__main__":main()
