# Balanced Take-only PE: 同seed 10組の探索的診断（合法Take候補限定）

seed=20260828、各trialの初期RNG seed=`20260828+1,000,000+trial_index`、max_attempts=10、POあり、workers=1。

## PE適用とfallback

- Take判断 1477件中、PE適用 180件（12.19%）
- fallback 1297件（87.81%）
- 理由別: {'unsupported_card': 1297}
- 未対応カード別: {'battle_focus': 30, 'boss_devourer': 3, 'brutal_critical': 6, 'brutal_force': 40, 'critical_conversion': 9, 'critical_engine': 10, 'critical_eye': 233, 'critical_momentum': 56, 'critical_power': 208, 'critical_training': 41, 'double_strike': 4, 'escalation': 32, 'first_strike': 54, 'follow_up_strike': 2, 'glass_cannon': 223, 'growth_engine': 5, 'heavy_blow': 221, 'heavy_critical': 218, 'last_stand': 33, 'light_attack': 214, 'momentum': 7, 'overclock': 34, 'overflow': 2, 'precise_strike': 236, 'sharpened_edge': 220, 'steady_force': 269}

## trial別の最初の選択分岐

| trial | 初分岐 | PE適用/Take | fallback/Take |
|---:|---|---:|---:|
| 0 | attempt 7 / W67 / decision 15: take quick_learner → take scholar | 21/141 | 120/141 |
| 1 | attempt 4 / W8 / decision 2: take rapid_fire → take power_up | 20/148 | 128/148 |
| 2 | attempt 8 / W80 / decision 16: take scholar → take rapid_fire | 18/152 | 134/152 |
| 3 | attempt 1 / W14 / decision 4: take power_up → take rapid_fire | 21/153 | 132/153 |
| 4 | 分岐なし | 14/143 | 129/143 |
| 5 | attempt 1 / W8 / decision 2: take power_up → take rapid_fire | 15/143 | 128/143 |
| 6 | attempt 2 / W28 / decision 9: take accelerated_learning → take experience | 23/146 | 123/146 |
| 7 | attempt 8 / W81 / decision 17: take accelerated_learning → take fast_learner | 15/167 | 152/167 |
| 8 | attempt 2 / W8 / decision 2: take rapid_fire → take power_up | 15/144 | 129/144 |
| 9 | attempt 1 / W44 / decision 12: take knowledge_conversion → take rapid_fire | 18/140 | 122/140 |

## 最初の分岐手札: 全提示カード（Take不能はPE未評価）

### trial 0 / attempt 7 / W67

legacy=quick_learner、PE mode=scholar、source=pe、fallback=None、H=74。
手札: scholar, quick_learner, study_break。Reroll: 1回、Refine gate: False。

| 候補 | Take可 | legacy | Immediate | Conditional | Combat PE | Growth PE | XP PE | Total PE | confidence | terminal Δp (非加算) | PE状態 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---|
| scholar | yes | +0.15000 | +0.00000 | +0.00000 | +0.00000 | +0.00000 | +0.00000 | +0.00000 | low | +0.00000 | ok |
| quick_learner | yes | +0.18750 | +0.00000 | +0.00000 | +0.00000 | +0.00000 | +0.00000 | +0.00000 | low | +0.00000 | ok |
| study_break | yes | -0.07500 | -0.00877 | +0.00000 | -0.00877 | +0.00000 | +0.00000 | -0.00526 | low | -0.01039 | ok |

### trial 1 / attempt 4 / W8

legacy=rapid_fire、PE mode=power_up、source=pe、fallback=None、H=31。
手札: power_up, battle_focus, rapid_fire。Reroll: 1回、Refine gate: False。

| 候補 | Take可 | legacy | Immediate | Conditional | Combat PE | Growth PE | XP PE | Total PE | confidence | terminal Δp (非加算) | PE状態 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---|
| power_up | yes | +0.60000 | +0.09691 | +0.00000 | +0.09691 | +0.00000 | +0.00000 | +0.05815 | low | +0.15814 | ok |
| battle_focus | no | +0.46875 | — | — | — | — | — | — | — | — | ineligible_take |
| rapid_fire | yes | +0.60600 | +0.06695 | -0.00000 | +0.06695 | +0.00000 | +0.00000 | +0.04017 | low | +0.08392 | ok |

### trial 2 / attempt 8 / W80

legacy=scholar、PE mode=rapid_fire、source=pe、fallback=None、H=91。
手札: scholar, fast_learner, rapid_fire。Reroll: 2回、Refine gate: False。

| 候補 | Take可 | legacy | Immediate | Conditional | Combat PE | Growth PE | XP PE | Total PE | confidence | terminal Δp (非加算) | PE状態 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---|
| scholar | yes | +0.92500 | +0.00000 | +0.00000 | +0.00000 | +0.00000 | +0.00433 | +0.00065 | low | +0.00000 | ok |
| fast_learner | yes | -0.07500 | -0.00877 | +0.00000 | -0.00877 | +0.00000 | +0.00433 | -0.00462 | low | -0.00427 | ok |
| rapid_fire | yes | +0.61200 | +0.05799 | +0.00000 | +0.05799 | +0.00000 | +0.00000 | +0.03480 | low | +0.06361 | ok |

### trial 3 / attempt 1 / W14

legacy=power_up、PE mode=rapid_fire、source=pe、fallback=None、H=23。
手札: rapid_fire, power_up, experience。Reroll: 1回、Refine gate: False。

| 候補 | Take可 | legacy | Immediate | Conditional | Combat PE | Growth PE | XP PE | Total PE | confidence | terminal Δp (非加算) | PE状態 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---|
| rapid_fire | yes | +0.60600 | +0.06695 | -0.00000 | +0.06695 | +0.00000 | +0.00000 | +0.04017 | low | +0.05557 | ok |
| power_up | yes | +0.61200 | +0.06695 | -0.00000 | +0.06695 | +0.00000 | +0.00000 | +0.04017 | low | +0.05557 | ok |
| experience | yes | +0.15000 | +0.00000 | +0.00000 | +0.00000 | +0.00000 | +0.01807 | +0.00271 | low | +0.00000 | ok |

### trial 5 / attempt 1 / W8

legacy=power_up、PE mode=rapid_fire、source=pe、fallback=None、H=9。
手札: rapid_fire, scholar, power_up。Reroll: 1回、Refine gate: False。

| 候補 | Take可 | legacy | Immediate | Conditional | Combat PE | Growth PE | XP PE | Total PE | confidence | terminal Δp (非加算) | PE状態 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---|
| rapid_fire | yes | +0.60000 | +0.07918 | -0.00000 | +0.07918 | +0.00000 | +0.00000 | +0.04751 | low | +0.22299 | ok |
| scholar | no | +0.15000 | — | — | — | — | — | — | — | — | ineligible_take |
| power_up | yes | +0.60600 | +0.07918 | -0.00000 | +0.07918 | +0.00000 | +0.00000 | +0.04751 | low | +0.22299 | ok |

### trial 6 / attempt 2 / W28

legacy=accelerated_learning、PE mode=experience、source=pe、fallback=None、H=34。
手札: experience, scholar, accelerated_learning。Reroll: 1回、Refine gate: False。

| 候補 | Take可 | legacy | Immediate | Conditional | Combat PE | Growth PE | XP PE | Total PE | confidence | terminal Δp (非加算) | PE状態 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---|
| experience | yes | +0.15600 | +0.00860 | +0.00000 | +0.00860 | +0.00000 | -0.00017 | +0.00514 | low | +0.01483 | ok |
| scholar | yes | +0.15600 | +0.00000 | +0.00000 | +0.00000 | +0.00000 | +0.00705 | +0.00106 | low | +0.00000 | ok |
| accelerated_learning | yes | +1.00585 | +0.00204 | +0.00000 | +0.00204 | +0.00000 | +0.00065 | +0.00132 | low | +0.00379 | ok |

### trial 7 / attempt 8 / W81

legacy=accelerated_learning、PE mode=fast_learner、source=pe、fallback=None、H=98。
手札: accelerated_learning, fast_learner, scholar。Reroll: 2回、Refine gate: False。

| 候補 | Take可 | legacy | Immediate | Conditional | Combat PE | Growth PE | XP PE | Total PE | confidence | terminal Δp (非加算) | PE状態 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---|
| accelerated_learning | yes | +1.08505 | +0.00484 | +0.00000 | +0.00484 | +0.00000 | +0.00046 | +0.00297 | low | +0.00309 | ok |
| fast_learner | yes | -0.05700 | +0.02627 | +0.00000 | +0.02627 | +0.00000 | +0.01367 | +0.01781 | low | +0.01959 | ok |
| scholar | yes | +0.16800 | +0.00000 | +0.00000 | +0.00000 | +0.00000 | +0.00690 | +0.00104 | low | +0.00000 | ok |

### trial 8 / attempt 2 / W8

legacy=rapid_fire、PE mode=power_up、source=pe、fallback=None、H=11。
手札: heavy_critical, rapid_fire, power_up。Reroll: 1回、Refine gate: False。

| 候補 | Take可 | legacy | Immediate | Conditional | Combat PE | Growth PE | XP PE | Total PE | confidence | terminal Δp (非加算) | PE状態 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---|
| heavy_critical | no | +0.10500 | — | — | — | — | — | — | — | — | ineligible_take |
| rapid_fire | yes | +0.60600 | +0.06695 | +0.00000 | +0.06695 | +0.00000 | +0.00000 | +0.04017 | low | +0.16375 | ok |
| power_up | yes | +0.60000 | +0.09691 | +0.00000 | +0.09691 | +0.00000 | +0.00000 | +0.05815 | low | +0.25652 | ok |

### trial 9 / attempt 1 / W44

legacy=knowledge_conversion、PE mode=rapid_fire、source=pe、fallback=None、H=45。
手札: knowledge_conversion, fast_learner, rapid_fire。Reroll: 1回、Refine gate: False。

| 候補 | Take可 | legacy | Immediate | Conditional | Combat PE | Growth PE | XP PE | Total PE | confidence | terminal Δp (非加算) | PE状態 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---|
| knowledge_conversion | yes | +1.76385 | +0.00000 | +0.00000 | +0.00000 | +0.00000 | +0.00000 | +0.00000 | low | +0.00000 | ok |
| fast_learner | yes | -0.07500 | -0.00877 | +0.00000 | -0.00877 | +0.00000 | +0.00000 | -0.00526 | low | -0.02415 | ok |
| rapid_fire | yes | +0.61200 | +0.05799 | -0.00000 | +0.05799 | +0.00000 | +0.00000 | +0.03480 | low | +0.16912 | ok |

## 明らかに不自然なTakeの機械的点検

- 不正な候補/非最大PEの選択: 0件 []
- PE同値・近同値（上位2候補の差≤1e-10）: zero-PE tie 1件、positive tie 3件、negative tie 0件。zeroは最高PEの絶対値≤1e-10、positiveは最高PE>1e-10。
- うち厳密な同値（手札順tie-break適用）: {'zero_pe': 1, 'positive': 3, 'negative': 0}。近同値でも数値が異なれば最大PEで選択する。
- 同値の識別子（trial,attempt,decision）: [(0, 7, 15), (3, 1, 4), (3, 2, 5), (5, 1, 2)]
- 合法Take候補に未対応カードがないか、Take不能カードが評価されていないか、最初の分岐の軸別値・H・低信頼予測を上表とJSONLで確認する。
- この10組は探索的診断であり、成功率やビルド強度の優劣は結論にしない。

## 旧・全提示カード判定との比較

- 旧仕様: 54/1477（3.66%）、fallback 1423件。
- 新仕様: 180/1477（12.19%）、fallback 1297件。
- 適用件数 +126、Take判断数 +0、適用率 +8.53ポイント、fallback -126件。
- 同じ初期seed・trial IDの探索的比較。選択分岐後は手札/Run/RNGがずれ得るため、旧ログの反実仮想12.19%や成功率の優劣と同一視しない。
