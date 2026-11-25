# Balanced Standard CardValue B案 v0.1 実装計画

状態: 実装前の計画。`card_value_evaluation_spec.md` と `predict_run_end_spec.md` の v0.1 限定プロファイル。コード変更は含まない。

## 1. v0.1 の境界と出力

対象は `scripts/simulate_first_prestige_v1.py` の Balanced Standard。火力型・シナジー型、および別系列の `simulate_new_w5000_*.py` へは適用しない。正式v1カード全種を同じ評価経路へ通し、以下5群を先行検証する: Power Up、Rapid Fire、Execution、Time Collapse、XP系（Experience / Quick Learner / Scholar / Accelerated Learning / Knowledge Conversion）。

- 評価期間Hは候補適用前のbaseline stateから予測する現在Runの残り期間。**同じ手札・Reroll・Refine/Upgrade内で固定**。固定100Waveを使わない。
- 将来の通常Draftは、レベルアップ期待件数・取得期待件数・カード1枚の期待価値で近似。未取得の具体的カード系列や架空の所持カードを生成しない。
- 将来のWeapon/Relicのランダムdrop・品質、探索で得るランダム資源は原則予測しない。現在装備・既取得遺物は反映する。決定的な解禁・固定報酬だけを対応する条件で反映する。対象外の影響が大きい期間はforecastを`uncertain`とする。v0.1では`compute_snapshot`と`dynamic_damage_log`内の遺物平均Powerが`permanent.max_wave`に応じて暗黙増加しないよう、予測戦闘用の`max_wave`を現在値に固定したコピーを使い、将来到達Wave（報酬/rarity判定用）は別フィールドで追跡する。未解禁でW100に到達した場合だけ、固定遺物の確定寄与として戦闘用`max_wave=100`と`relic_unlocked=True`を反映する。
- terminal突破確率は計算・ログ・事後照合できるようにするが、継続機会のPE換算未校正につき **`total_pe`にも選択判断にも加算しない**。フィールドは`terminal_pe=None`、`terminal_included=False`（ゼロ価値だと誤認させない）。
- Combat/Growth/XPの未加重値を同じ固定Hの**遭遇1回あたり期待余裕差**で表し、`total_pe = 0.60 * combat_net + 0.25 * growth_net + 0.15 * xp_net`を一度だけ実行。Riskは各軸の前後差に含め、別加算はしない。Synergyも重複加算しない。旧scoreの1.10/0.55を使わない。

## 2. Baseline予測 v0.1

`predict_run_end_spec.md` の全機能を一度に実装しない。選択中のXP cost支払済み・`xp_level_count`増分前という呼出し位相を明示し、現在の選択を「候補なしno-op」として決済したコピーから開始する。将来カード抽選・取得はしない。ただし既取得のGrowth Engine / Accelerated Learningには**期待カード取得イベント数**を与える。現在保有のBoss Devourer、Escalation、Perfect Overdrive、Legendary撃破成長等は既存の戦闘後更新順序に従う。

```pseudo
baseline = normalize_choice_phase_copy(run, permanent, phase)
for w in next_wave .. config.target_wave:
    snapshot_before = snapshot_with_existing_growth(baseline, w)
    ttk = time_to_kill_with_defense(w, configured_enemy_power(w),
                                    enemy_time_limit(w), snapshot_before)
    if cannot_kill_and_not_reward_skipped: stop_at_failed_wave(w)
    if killed: update_owned_growth_then_expected_xp_then_expected_draft_events(w)
    if w == target_wave: stop_at_prestige(w)
```

XPは現在残高と`CARD_COSTS`を逐次更新する。将来通常Draftで実際にTakeする期待確率は、正式v1の診断ログからWave帯別に校正した表を使う。表がなければ保守的な上下界（取得率0～1）と`uncertain`を返す。確定3択は獲得イベント数のみ記録し、将来カードの固有効果は仮所持しない。XP増加による追加DraftはXP軸へ帰属し、Growthが使う既存baseline Draftイベントと分ける。

将来のランダム装備を固定Powerで代用しない。`permanent.max_wave`だけを更新して遺物平均Powerが増える隠れた予測も禁止する。装備不確実性で遠方の失敗地点を特定できない場合はlow/high終了Waveを診断し、全候補で共通の次の検証可能な戦闘を暫定Hに使う。将来Growth/XPは`unknown`として別途記録し、推測で0点確定にはしない。稼働上の暫定選択は`predict_run_end_spec.md` §6の保守的方針に従う。

`RunEndForecast`に少なくとも`predicted_end_wave`、`end_reason`、`remaining_encounters`、通常/Boss/Big Boss件数、`remaining_xp_gross`、`remaining_xp_balance`、通常Draft期待件数、既存成長イベント件数、`status/confidence/assumptions`を返す。失敗した敵は遭遇数に含み、XP・撃破成長から除外する。

## 3. 共通CardValue の v0.1 計算

候補をコピーへ適用し、baseline予測した同じ遭遇列・同じ装備仮定を参照する。前後`compute_snapshot(..., boss=w % 10 == 0)`の差をH内で平均してImmediateとする。Growthの将来イベントは別のコピーに適用し、候補由来増分だけをH内平均差として足す。時間・Execution等のConditionalは次式で計算する。

```text
M(S,w) = S.log_dps + log10(temporal_integral(T_w,T_w,S))
         - configured_enemy_power(w) - log10(0.70 + 0.30/S.execution_mult)
Immediate = mean_H(S_candidate_frozen.log_dps - S_baseline.log_dps)
Conditional = mean_H(M(S_candidate_frozen,w) - M(S_baseline,w)) - Immediate
CombatNet = Immediate + Conditional
```

`S_candidate_frozen`は候補の現在効果だけを含み、候補獲得後の成長イベントを含めない。候補自身の成長を載せたtrajectoryとの差はGrowthへ。`time_to_kill`の離散Hit/撃破時間・勝敗はConditionalの診断に保存し、未校正の秒→PE加点はしない。Defense有効時にはこの単純HP marginを用いず、Armor Breakを含む専用経路の設計・テストが整うまで診断のみとする。

### 代表ケース

| カード | v0.1で使う値 | 検証上の注意 |
|---|---|---|
| Power Up | `compute_snapshot`前後差。`attack_bonus`の`log10(1+A+0.25*amp)-log10(1+A)`は検算用 | 他のATK加算、カード強化、Limit倍率、Exponential Core、Final EquationをSnapshot経由で反映 |
| Rapid Fire | AS増加をSnapshotのDPS差へ。`time_to_kill`のHit数端数、Infinite BarrageのAS Tierは診断/実差分 | Bossと通常敵の比率、Defense時のArmor Break価値を混同しない |
| Execution | `execution_mult`により要求Damage比`0.70+0.30/execution_mult`の変化を全Encounterへ。Immediate=0でもConditionalに正値 | 勝敗/時間の閾値は診断。uniqueで2枚目を評価しない |
| Time Collapse | `temporal_integral(T,T,S)`の前後比でConditionalを計算。通常10秒/Boss15秒を別評価 | First Strike/Last Stand、Glass Cannonによる制限時間を反映 |
| XP系 | 現在XP倍率/Quick Learnerの条件付きXPを既存処理式から予測。追加Draftとその後続価値はXP軸のみ | Accelerated Learningの取得後成長はXP軸、Knowledge Conversionの既存XPからの直接火力はCombat。追加DraftのGrowthを別計上しない |

### XP追加Draftの期待価値

候補あり/なしで固定HのXP獲得・閾値通過を比較し、追加Draftの期待時刻と期待件数を求める。獲得時点のレアリティ分布、解禁、uniqueを使って3択の**最良カードの未加重PE**を決定的近似で計算する（レアリティ×利用可能カードの離散分布から順序統計を求める。重複禁止の誤差はオフラインで検証）。3択の期待値は本体`draw_hand`を呼ばず、ゲームRNGを消費しない。

```text
XPValue = Σ_{追加Draft d} E[最良カードがd以降の固定Hにもたらす
                          未加重Combat+GrowthのPE差] / N_H
total_pe = 0.60*CombatNet + 0.25*GrowthNet + 0.15*XPValue
```

Draft内のXP再帰価値を同じ期待値へ入れず、再帰で発生する追加DraftはXP forecast側で一度だけ処理する。全候補に同じH・分母を使用し、`CardValue.total_pe`を`E[最良カード]`の中へ戻さない。短いHでは追加Draftがあっても、その効果が発揮される残り遭遇数が短くなる。

## 4. terminal計測（scoreから分離）

baseline予測が失敗するWave Fを記録。候補適用後の固定H上の同じFについて、先行障害への到達率`r_c`とF突破率`q_c`を測れるようにする。v0.1では事前に凍結した閾値・温度による決定的な確率近似を**診断値**として計算し、真の成功率ではないことを記録する。

```text
predicted_frontier_pass_prob(c) = r_c * q_c
predicted_frontier_pass_delta = r_c*q_c - r_0*q_0
terminal_pe = None          # uncalibrated
selection_total_pe = CardValue.total_pe
```

実試行では各決定の`decision_id`、baseline/candidate状態識別子、F、選択候補、予測確率、実際のF到達/撃破/死亡、進行結果を照合可能なログへ保存する。観測は**実際に選択された候補のみ**得られるため、非選択候補の反実仮想を実測扱いしない。独立した同seedの候補介入比較が必要なら後段のオフライン校正で行う。Fが予測不能な場合は確率を`None/status=unknown`として残す。PE係数もprestige報酬価値も校正されるまでterminalを選択に加算しない。

## 5. 既存再利用・新規関数・変更箇所

| 区分 | 対象 | 目的 |
|---|---|---|
| 再利用 | `compute_snapshot`, `dynamic_damage_log`, `temporal_integral`, `time_to_kill`, `time_to_kill_with_defense` | 実戦と同じDamage・条件効果・撃破判定 |
| 再利用 | `enemy_time_limit`, `configured_enemy_power`, `progression_wave`, `progression_units`, `reward_preserving_skip_end` | 次敵・Boss・報酬スキップの時系列 |
| 再利用 | `CARD_COSTS`, `rarity_chances`, `available_cards`, `CARDS`, `enhanceable`, `CARD_POINT_VALUE`, `CARD_UPGRADE_COSTS` | XP・期待Draft・Refine/Upgradeの合法性 |
| 再利用 | `RunState`, `PermanentState`, `SimConfig`, `acquire_card` | コピー状態への候補仮適用。乱数系を呼ばない |
| 新規 | `normalize_choice_phase_copy`, `predict_run_end_v01`, `forecast_existing_growth`, `forecast_xp_and_drafts`, `snapshot_without_future_random_loot` | 候補非依存のHと期待イベント、遺物平均曲線の暗黙予測を防ぐ戦闘用Snapshot |
| 新規 | `build_evaluation_context`, `evaluate_state_delta`, `evaluate_card_value`, `evaluate_raw_draft_pick` | 共通PEと軸別帰属、未加重XP Draft価値 |
| 新規 | `expected_next_hand_value`, `incremental_refine_value`, `best_upgrade_plan` | 共通CardValueを用いる行動価値比較 |
| 新規 | `frontier_pass_probability`, `record_card_value_diagnostic` | terminal突破診断。scoreへの加算なし |
| 変更予定 | `choose_card`, `carry_memory_card`, `spend_card_points` | Balanced分岐だけ新評価へ。starter/forced・解禁・既存操作時間ルールを維持 |
| 変更予定 | `run_once` のカード選択呼出し箇所と実結果記録 | 位相情報を評価入口へ渡し、Fの実到達/突破と選択を対応付ける |
| 変更予定 | CLI/設定、レポートの診断導線 | 既定OFFの明示フラグ、実行条件とdiagnosticの出力先を分ける |

`draw_hand`は**実際の選択**にだけ使う。将来/仮想手札の期待値近似からは呼ばない。CardValue内部の予測に`card_score`のタグ点数を流用しない。

## 6. Take / Reroll / Refine / Upgradeの接続

1. **Take:** 同一contextの`CardValue.total_pe`最大を選ぶ。starter/forced制約は既存ルール。
2. **Reroll:** 現在手札の最良Takeと、次手札の期待最大Take（必要ならRefine価値も含む）の差を比較。現行の除外集合・残回数・強制報酬の禁止を守る。v0.1は1段先の期待値近似と明記し、複数回の最適停止はオフラインで誤差確認。旧1.10は使用しない。
3. **Refine:** 全手札の最良Takeと、各提示カード溶解で増えるPointの`best_upgrade_plan(current+gain)-best_upgrade_plan(current)`を比較。既投入Pointはサンクコスト。既存未使用Pointが失効するときだけ失効価値を一度差し引く。将来Pointオプションが未校正なら`unknown`と記録し、安全側ではRefineを強制しない。旧0.55は使用しない。
4. **Upgrade:** 所持カードの次の1段階の`evaluate_state_delta`を比較し、今回消費Pointの機会費用だけを引く。購入後に残高・状態を更新して再評価。単純な`card_score * count`を使わない。

予測で未解決軸がある状態を暫定判断した場合は`forecast_status=uncertain`を決定ログに残し、formalの評価結果と分けて集計する。

## 7. 実装順と確認ゲート

1. **観測・分離:** Balanced専用の明示フラグ（既定OFF）と候補/実結果の診断記録、状態・RNG不変チェックの土台を用意。既定条件が従来出力と同一seedで一致することを確認。
2. **baseline予測:** 位相正規化、装備ランダム未来を除く現在保有効果の決定的rollout、終了Wave/XP/Boss件数・信頼度を実装。予測失敗なら固定100Waveでなく明示的な次敵fallback。保存済みtrial状態と予測を突合。
3. **Combat:** 仮適用・H共通化・Immediate/Conditional分解。Power Up、Rapid Fire、Execution、Time Collapseを単体比較し、入力変更・乱数消費がないことを確認。
4. **XP/Growth:** XP閾値、期待Draft価値、Accelerated Learningや既存成長イベントを連結。XP由来DraftはGrowthへ重ねず、最終ウェイトを一度だけ適用。ここまでshadow評価のみでdecisionは変更しない。
5. **行動:** Take→Reroll→Refine/Upgradeの順でフラグON経路を繋ぐ。各段階で旧フラグOFFとの差と診断を確認。
6. **terminal診断:** 突破確率・実結果の照合ログを追加し、`terminal_included=False`をassert。最後に短いpaired seed比較と評価時間計測。多くの判断が`uncertain`ならバランス比較前に予測モデルを見直す。

## 8. 最低限の単体テスト

| 入力状態 → 候補 | 期待される関係 |
|---|---|
| ATK加算少/多、他条件同一 → Power Up | 低加算の方が限界Immediateが大きい。Snapshotの前後差と一致 |
| Exponential Coreなし/あり、同じ攻撃加算 → Power Up | `compute_snapshot`で得る増分が対応して変化。Final Equation併用も前後差と一致 |
| AS加算少/多 → Rapid Fire | ASの限界価値が現在状態で変化。Hit端数によるTTKはdiagnosticへ出る |
| 通常敵/Boss混在H → Execution | `log_dps`増分0でもConditionalは`-log10(required_ratio)`の改善と一致 |
| First Strikeなし/あり、通常10秒/Boss15秒 → Time Collapse | 両制限時間の`temporal_integral`差分を評価。即時DPS差0でもConditionalが正 |
| XP閾値直前/十分遠い、同一H → Experience | 閾値付近で追加Draft期待数・XP軸が高い。Combat直接効果はない |
| Quick Learnerあり、quick killと非quick kill → XP系候補 | Quick LearnerのXP増分はquick時だけ反映 |
| Accelerated Learningあり/なし、後続Draft期待数>0 → XP候補 | 既存成長のXP効果を予測する。追加Draft由来効果をGrowthへ二重計上しない |
| Knowledge Conversionあり、XP倍率増加 → XP系候補 | 候補自身の直接DamageはCombat、追加DraftはXPへ一度ずつ |
| Boss Devourer所持、次がBoss → 任意候補 | Boss自身の戦闘前には撃破スタックを載せず、次敵以降に載せる |
| Lv-up選択中でCost支払済み → 任意候補 | `xp_level_count`の位相補正を一度だけ行い、Cost再控除/現在Draft再加算なし |
| 装備dropが発生し得る未来 → 任意候補 | 未来のランダムWeapon/Relicを仮所持せず、status/assumptionsに対象外を残す |
| 同一判断で候補順序だけ変更 → Power UpとRapid Fire | H、候補値、ゲームRNG状態、入力RunState/PermanentStateが一致 |
| baselineがFで失敗、候補で突破確率上昇 → 任意候補 | 確率差ログは正、Hは固定、`terminal_pe=None`かつ`selection_total_pe=total_pe` |
| 既存Pointで既に強化可能/Point不足 → Refine候補 | Refine価値は`plan(P+gain)-plan(P)`。既投入Pointを再度引かない |
| フラグOFFの同一seed run → 全候補 | 既存score経路・RNG列・正式結果が変更前と一致 |

各テストは効果を鏡写しにした固定scoreではなく、現行戦闘関数の差分、イベント順序、同一H、不変性、軸の一度だけの帰属を検査する。

## 9. v0.1の事前確定事項

実装前にWave帯別の通常Draft期待取得率、将来ランダム装備除外下の予測信頼度基準、XP Draft最良値近似の許容誤差、Rerollの1段先近似とRefine将来Point価値が不明な場合の方針、1判断あたりの計算予算を決める。terminalの突破確率温度は診断の校正対象とし、PE換算係数が決まるまで選択に利用しない。
