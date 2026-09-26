# Balanced Take-only PE: 同seed 10組の探索的診断

seed=20260828、各trialの初期RNG seed=`20260828+1,000,000+trial_index`、max_attempts=10、POあり、workers=1。

## PE適用とfallback

- Take判断 1477件中、PE適用 54件（3.7%）
- fallback 1423件（96.3%）
- 理由別: {'unsupported_card': 1423}
- 未対応カード別: {'battle_focus': 32, 'boss_devourer': 3, 'brutal_critical': 7, 'brutal_force': 42, 'critical_conversion': 10, 'critical_engine': 10, 'critical_eye': 264, 'critical_momentum': 60, 'critical_power': 240, 'critical_training': 45, 'double_strike': 5, 'escalation': 33, 'first_strike': 59, 'follow_up_strike': 3, 'glass_cannon': 264, 'growth_engine': 5, 'heavy_blow': 255, 'heavy_critical': 246, 'last_stand': 33, 'light_attack': 239, 'momentum': 7, 'overclock': 34, 'overflow': 3, 'precise_strike': 274, 'sharpened_edge': 247, 'steady_force': 269}

## trial別の最初の選択分岐

| trial | legacy (到達/attempts) | PE (到達/attempts) | 初分岐 | PE適用/Take | fallback/Take |
|---:|---|---|---|---:|---:|
| 0 | 48/10 | 48/10 | attempt 7 / W67 / decision 15: take quick_learner → take scholar | 6/141 | 135/141 |
| 1 | 56/10 | 56/10 | attempt 9 / W61 / decision 15: take boss_research → take experience | 7/148 | 141/148 |
| 2 | 51/10 | 51/10 | attempt 8 / W80 / decision 16: take scholar → take rapid_fire | 7/152 | 145/152 |
| 3 | 52/10 | 52/10 | attempt 1 / W14 / decision 4: take power_up → take rapid_fire | 8/153 | 145/153 |
| 4 | 32/10 | 32/10 | 分岐なし | 2/143 | 141/143 |
| 5 | 44/10 | 46/10 | attempt 1 / W8 / decision 2: take power_up → take rapid_fire | 2/143 | 141/143 |
| 6 | 47/10 | 47/10 | attempt 2 / W28 / decision 9: take accelerated_learning → take experience | 7/146 | 139/146 |
| 7 | 51/10 | 51/10 | attempt 8 / W81 / decision 17: take accelerated_learning → take fast_learner | 2/167 | 165/167 |
| 8 | 38/10 | 38/10 | 分岐なし | 5/144 | 139/144 |
| 9 | 44/10 | 47/10 | attempt 1 / W44 / decision 12: take knowledge_conversion → take rapid_fire | 8/140 | 132/140 |

## 最初の分岐手札: 全提示カードのPE内訳

### trial 0 / attempt 7 / W67

legacy=quick_learner、PE mode=scholar、source=pe、fallback=None、H=74。
手札: scholar, quick_learner, study_break。Reroll: 1回、Refine gate: False。

| 候補 | Take可 | legacy | Immediate | Conditional | Growth | XP | Total | confidence | terminal Δp (非加算) | PE状態 |
|---|---|---:|---:|---:|---:|---:|---:|---|---:|---|
| scholar | yes | +0.15000 | +0.00000 | +0.00000 | +0.00000 | +0.00000 | +0.00000 | low | +0.00000 | ok |
| quick_learner | yes | +0.18750 | +0.00000 | +0.00000 | +0.00000 | +0.00000 | +0.00000 | low | +0.00000 | ok |
| study_break | yes | -0.07500 | -0.00877 | +0.00000 | +0.00000 | +0.00000 | -0.00526 | low | -0.01039 | ok |

### trial 1 / attempt 9 / W61

legacy=boss_research、PE mode=experience、source=pe、fallback=None、H=71。
手札: experience, boss_research, study_break。Reroll: 2回、Refine gate: False。

| 候補 | Take可 | legacy | Immediate | Conditional | Growth | XP | Total | confidence | terminal Δp (非加算) | PE状態 |
|---|---|---:|---:|---:|---:|---:|---:|---|---:|---|
| experience | yes | +0.15600 | +0.00000 | +0.00000 | +0.00000 | +0.00498 | +0.00075 | low | +0.00000 | ok |
| boss_research | yes | +0.19500 | -0.00697 | -0.00000 | +0.00000 | +0.00000 | -0.00418 | low | -0.00697 | ok |
| study_break | yes | -0.06900 | -0.00877 | -0.00000 | +0.00000 | +0.00498 | -0.00452 | low | -0.00415 | ok |

### trial 2 / attempt 8 / W80

legacy=scholar、PE mode=rapid_fire、source=pe、fallback=None、H=91。
手札: scholar, fast_learner, rapid_fire。Reroll: 2回、Refine gate: False。

| 候補 | Take可 | legacy | Immediate | Conditional | Growth | XP | Total | confidence | terminal Δp (非加算) | PE状態 |
|---|---|---:|---:|---:|---:|---:|---:|---|---:|---|
| scholar | yes | +0.92500 | +0.00000 | +0.00000 | +0.00000 | +0.00433 | +0.00065 | low | +0.00000 | ok |
| fast_learner | yes | -0.07500 | -0.00877 | +0.00000 | +0.00000 | +0.00433 | -0.00462 | low | -0.00427 | ok |
| rapid_fire | yes | +0.61200 | +0.05799 | +0.00000 | +0.00000 | +0.00000 | +0.03480 | low | +0.06361 | ok |

### trial 3 / attempt 1 / W14

legacy=power_up、PE mode=rapid_fire、source=pe、fallback=None、H=23。
手札: rapid_fire, power_up, experience。Reroll: 1回、Refine gate: False。

| 候補 | Take可 | legacy | Immediate | Conditional | Growth | XP | Total | confidence | terminal Δp (非加算) | PE状態 |
|---|---|---:|---:|---:|---:|---:|---:|---|---:|---|
| rapid_fire | yes | +0.60600 | +0.06695 | -0.00000 | +0.00000 | +0.00000 | +0.04017 | low | +0.05557 | ok |
| power_up | yes | +0.61200 | +0.06695 | -0.00000 | +0.00000 | +0.00000 | +0.04017 | low | +0.05557 | ok |
| experience | yes | +0.15000 | +0.00000 | +0.00000 | +0.00000 | +0.01807 | +0.00271 | low | +0.00000 | ok |

### trial 5 / attempt 1 / W8

legacy=power_up、PE mode=rapid_fire、source=pe、fallback=None、H=9。
手札: rapid_fire, scholar, power_up。Reroll: 1回、Refine gate: False。

| 候補 | Take可 | legacy | Immediate | Conditional | Growth | XP | Total | confidence | terminal Δp (非加算) | PE状態 |
|---|---|---:|---:|---:|---:|---:|---:|---|---:|---|
| rapid_fire | yes | +0.60000 | +0.07918 | -0.00000 | +0.00000 | +0.00000 | +0.04751 | low | +0.22299 | ok |
| scholar | no | +0.15000 | +0.00000 | +0.00000 | +0.00000 | +0.00000 | +0.00000 | low | +0.00000 | ok |
| power_up | yes | +0.60600 | +0.07918 | -0.00000 | +0.00000 | +0.00000 | +0.04751 | low | +0.22299 | ok |

### trial 6 / attempt 2 / W28

legacy=accelerated_learning、PE mode=experience、source=pe、fallback=None、H=34。
手札: experience, scholar, accelerated_learning。Reroll: 1回、Refine gate: False。

| 候補 | Take可 | legacy | Immediate | Conditional | Growth | XP | Total | confidence | terminal Δp (非加算) | PE状態 |
|---|---|---:|---:|---:|---:|---:|---:|---|---:|---|
| experience | yes | +0.15600 | +0.00860 | +0.00000 | +0.00000 | -0.00017 | +0.00514 | low | +0.01483 | ok |
| scholar | yes | +0.15600 | +0.00000 | +0.00000 | +0.00000 | +0.00705 | +0.00106 | low | +0.00000 | ok |
| accelerated_learning | yes | +1.00585 | +0.00204 | +0.00000 | +0.00000 | +0.00065 | +0.00132 | low | +0.00379 | ok |

### trial 7 / attempt 8 / W81

legacy=accelerated_learning、PE mode=fast_learner、source=pe、fallback=None、H=98。
手札: accelerated_learning, fast_learner, scholar。Reroll: 2回、Refine gate: False。

| 候補 | Take可 | legacy | Immediate | Conditional | Growth | XP | Total | confidence | terminal Δp (非加算) | PE状態 |
|---|---|---:|---:|---:|---:|---:|---:|---|---:|---|
| accelerated_learning | yes | +1.08505 | +0.00484 | +0.00000 | +0.00000 | +0.00046 | +0.00297 | low | +0.00309 | ok |
| fast_learner | yes | -0.05700 | +0.02627 | +0.00000 | +0.00000 | +0.01367 | +0.01781 | low | +0.01959 | ok |
| scholar | yes | +0.16800 | +0.00000 | +0.00000 | +0.00000 | +0.00690 | +0.00104 | low | +0.00000 | ok |

### trial 9 / attempt 1 / W44

legacy=knowledge_conversion、PE mode=rapid_fire、source=pe、fallback=None、H=45。
手札: knowledge_conversion, fast_learner, rapid_fire。Reroll: 1回、Refine gate: False。

| 候補 | Take可 | legacy | Immediate | Conditional | Growth | XP | Total | confidence | terminal Δp (非加算) | PE状態 |
|---|---|---:|---:|---:|---:|---:|---:|---|---:|---|
| knowledge_conversion | yes | +1.76385 | +0.00000 | +0.00000 | +0.00000 | +0.00000 | +0.00000 | low | +0.00000 | ok |
| fast_learner | yes | -0.07500 | -0.00877 | +0.00000 | +0.00000 | +0.00000 | -0.00526 | low | -0.02415 | ok |
| rapid_fire | yes | +0.61200 | +0.05799 | -0.00000 | +0.00000 | +0.00000 | +0.03480 | low | +0.16912 | ok |

## 明らかに不自然なTakeの機械的点検

- 不正な候補/非最大PEの選択: 0件 []
- PE同値（差≤1e-10）のTake: 4件。この場合は手札順のtie-breakであり、PEの優劣が識別された選択とは扱わない。
- 同値の識別子（trial,attempt,decision）: [(0, 7, 15), (3, 1, 4), (3, 2, 5), (5, 1, 2)]
- 手動点検: trial 0の最初の分岐は`scholar`/`quick_learner`ともTotal PE 0で、先頭の`scholar`を取ったtie-break。trial 3/5のPower Up対Rapid Fireもほぼ同点で、PEが優劣を識別した結果ではない。
- trial 9の`knowledge_conversion`は旧score 1.76385に対しPE 0、`rapid_fire`はPE 0.03480。予測HがW45まででconfidenceはlowのため、未知の将来効果がHからこぼれている可能性を含む。初分岐8件のconfidenceはいずれもlow。
- 違法なTakeや非最大PEの選択は検出されなかった。同点・短いHは実装上の違反と区別して、**モデルの識別力/予測不確実性**として扱う。未対応カード別件数は同一fallback手札の複数枚を含み、合計はfallback手札数を超え得る。
- PEが未対応カードを含む手札を選んでいないか、最初の分岐の軸別値・H・低信頼予測を上表とJSONLで確認する。
- この10組は探索的診断であり、成功率やビルド強度の優劣は結論にしない。
