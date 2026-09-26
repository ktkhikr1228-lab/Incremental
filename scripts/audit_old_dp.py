#!/usr/bin/env python3
"""Generate a read-only audit of the legacy Death Point implementation."""

from __future__ import annotations

import csv
import math
from pathlib import Path

import simulate_first_prestige_v1 as sim


GROWTH=sim.DP_GROWTH
BALANCED=("atk","attack_speed","atk","xp","attack_speed")
MILESTONE_POWER={50:1.0,75:2.0,100:3.0,125:4.0,150:5.0}


def stat_effect(stat:str)->tuple[float,float]:
    multiplier={"atk":1.10,"attack_speed":1.05,"xp":1.0}[stat]
    return multiplier,math.log10(multiplier)


def transition(level:int)->dict[str,object]:
    new=level+1;stat=BALANCED[level%len(BALANCED)]
    direct,direct_power=stat_effect(stat)
    milestone_power=MILESTONE_POWER.get(new,0.0)
    milestone_multiplier=10**milestone_power
    return {"from":level,"to":new,"stat":stat,"direct_multiplier":direct,"milestone_multiplier":milestone_multiplier,"total_multiplier":direct*milestone_multiplier,"power":direct_power+milestone_power,"milestone":f"+{milestone_power:g} Power" if milestone_power else "-"}


def main()->None:
    out=Path("output/old_dp_audit").resolve();out.mkdir(parents=True,exist_ok=True)
    costs=[(level,sim.next_dp_cost(level,GROWTH)) for level in (0,25,50,75,100,125,150,175,200)]
    marginal=[transition(level) for level in range(90,161)]
    focus=[transition(level) for level in (99,100,124,125,144,149,150)]
    with (out/"old_dp_marginal_lv90_160.csv").open("w",newline="",encoding="utf-8-sig") as handle:
        writer=csv.DictWriter(handle,fieldnames=marginal[0].keys());writer.writeheader();writer.writerows(marginal)
    lines=[
        "# 旧DP（Death Point）実装監査","",
        "対象: `scripts/simulate_first_prestige_v1.py` / formalデフォルト。シミュレーションとバランス変更は行っていない。","",
        "## 1. DP獲得","",
        "- 失敗Run終了後に `gained = floor(result.reached / 5)`。`reached`はそのRun単体の撃退Wave数。",
        "- Boss / Big Boss補正なし。最高Wave補正や初回到達補正もなし。",
        "- 同じWaveで繰り返し死亡するたび、同じDPを再獲得できる。",
        "- 獲得DPは`PermanentState.banked_dp`へ入り、購入可能なLvを即時一括購入。余りは次Runへ保持。",
        "- 成功Run（転生Wave到達Run）はDP獲得処理の前にreturnするため、そのRun自体の到達Wave分DPは得ない。",
        "- `permanent.max_wave`は撃破ごとに更新されるが、DP獲得式はmax_waveではなく現Runの`result.reached`を使う。",
        "- 第一転生後の保持/リセット処理は本シミュレーターに未実装。転生成功時点でTrialResultを返して終了する。","",
        "## 2. DP購入コスト","",
        "`next_cost = ceil(5 × 1.0315 ^ totalLv)`","",
        "| totalLv | 次の1Lvコスト |","|---:|---:|",
    ]
    lines += [f"| {level} | {cost:,} |" for level,cost in costs]
    lines += ["", "コストはATK/AS/XPの個別Lv、Wave、死亡回数、購入先に影響されず、`totalLv`と`config.dp_growth`だけで決まる。formalデフォルトは1.0315。","", "## 3. 通常DP強化","", "| 項目 | 1Lv効果 | 式と計算位置 | 上限 / Softcap |","|---|---:|---|---|","| Base ATK | ×1.10 | `log_attack`へ`atkLv×log10(1.10)`。カードBase ATK枠と乗算。旧formal Weapon Powerともlog加算（乗算） | なし |","| Attack Speed | ×1.05 | `(1/base_interval) × 1.05^asLv × cardAS`。 | なし |","| XP | ×1.05 | `1.05^xpLv × cardXP`。直接Damageではない | なし |","", "別系統として最大Lv9の基礎攻撃間隔DPもコード上に存在するが、`--attack-interval`がないformalデフォルトではOFF。totalLvに含まれない。","", "| 間隔Lv | 基礎間隔 | 個別DP Cost | Wave Gate |","|---:|---:|---:|---:|","| 1 | 0.9s | 100 | 100 |","| 2 | 0.8s | 300 | 250 |","| 3 | 0.7s | 900 | 500 |","| 4 | 0.6s | 2,700 | 1,000 |","| 5 | 0.5s | 8,100 | 2,500 |","| 6 | 0.4s | 24,300 | 5,000 |","| 7 | 0.3s | 72,900 | 7,500 |","| 8 | 0.2s | 218,700 | 10,000 |","| 9 | 0.1s | 656,100 | 第一転生後 |","", "ON時のStandardは獲得DPの25%をこの別口座へ配分する。SoftcapはないがLv9がHard Cap。現formalデフォルトと新W5000候補ではOFF。","", "## 4. totalLvマイルストーン","", "| Lv | 効果 | 計算カテゴリ / 重複 |","|---:|---|---|","| 5 | 全Damage×1.20 | milestone乗算。Lv20と累積 |","| 10 | Reroll 1→2 | ルール変更、Damageなし |","| 20 | 全Damage×1.50 | Lv5と乗算（累計×1.80） |","| 30 | 各Run初期XP +10 | 進行QoL、Damageなし |","| 50 | +1 Power（×10） | Final Damage系のlog加算 |","| 75 | +2 Power（×100）、Boss XP×1.50、初期Card Point+5 | Powerは累積。Card Pointは解禁条件とconfig有効時 |","| 100 | +3 Power（×1,000）、Rare率+1pt | Power累積 |","| 125 | +4 Power（×10,000）、初期Card Point+10（累計+15） | Power累積 |","| 150 | +5 Power（×100,000） | Power累積 |","", "Power報酬はすべて累積。Lv150時点で`+1+2+3+4+5 = +15 Power`（×1e15）。Lv25には実装効果なし。Lv150以降の追加マイルストーンもなし。","", "## 5. 指定Lvの1Lv限界効果（Standard/balanced配分）","", "| 遷移 | 購入先 | 最終Damage倍率 | +Power | 発動マイルストーン |","|---:|---|---:|---:|---|",
    ]
    lines += [f"| {row['from']}→{row['to']} | {row['stat']} | ×{row['total_multiplier']:,.3f} | {row['power']:.6f} | {row['milestone']} |" for row in focus]
    lines += ["", "Lv124→125はStandard配分のAS×1.05に、マイルストーン×1e4が同時発動: `1.05×10^4 = 10,500`、`log10 = 4.021189 Power`。","", "Lv149→150はAS×1.05と×1e5: `1.05×10^5 = 105,000`、`log10 = 5.021189 Power`。","", "直前計測の+4.23 / +5.05 Powerは、この+4 / +5 Power段差に、同期間の通常ATK/AS Lvと、診断分解の順序・加算Weaponとの相互作用が加わった値。根本原因は明確にLv125の+4 PowerとLv150の+5 Power。","", "## 6. Lv90～160 marginal effect","", "全行は`old_dp_marginal_lv90_160.csv`に保存。マイルストーン以外はStandardの5Lv周期でATK/AS/ATK/XP/AS。","", "| 購入先 | 倍率 | +Power |","|---|---:|---:|","| ATK通常Lv | ×1.10 | +0.041393 |","| AS通常Lv | ×1.05 | +0.021189 |","| XP通常Lv | ×1.00（直接Damage） | +0.000000 |","| Lv100到達Lv | 通常Lv×1e3 | +3.0 Powerを追加 |","| Lv125到達Lv | 通常Lv×1e4 | +4.0 Powerを追加 |","| Lv150到達Lv | 通常Lv×1e5 | +5.0 Powerを追加 |","", "## 7. Standard botのDP配分","", "固定5Lv周期: `ATK → AS → ATK → XP → AS`。比率はATK 40% / AS 40% / XP 20%。","", "- 効率評価、最安値選択、現在ビルド参照はない。","- 全3種の次LvコストはtotalLv共通なので、個別コスト比較もない。","- Lv100で正確に40/40/20、Lv125で50/50/25、Lv150で60/60/30になる。Lv145の58.5/57.5/29は30 trialの中央値同士で、単一状態の整数Lvではない。","", "## 8. W500～850での判定","", "- 通常Lvの直接成長は5Lvあたり`1.10^2×1.05^2 = ×1.334025`（+0.125164 Power）。XP 1Lvは即時Damageを増やさない。","- Lv100→125の25Lv通常成長は+0.625821 Power。そこへLv125マイルストーン+4 Powerが乗り、理論合計+4.625821 Power。","- Lv145→150の5Lv通常成長は+0.125164 Power。Lv150マイルストーン+5 Powerと合わせて+5.125164 Power。","- したがって現進行は、通常DP成長で連続的に敵曲線へ追いつく設計ではない。Lv125/Lv150の×1e4/×1e5を待つ「巨大マイルストーン待ち」になっていると判定できる。"]
    (out/"old_dp_audit.md").write_text("\n".join(lines)+"\n",encoding="utf-8")


if __name__=="__main__":main()
