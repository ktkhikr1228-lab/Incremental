# 確定した設計判断と適用範囲

**対象は旧formal W10000のBalanced Standard/CardValue v0.1。** 新W5000候補群・formal Variant D/Eへこの判断を無断で適用しない。根拠: [`card_value_evaluation_spec.md`](../card_value_evaluation_spec.md)、[`card_value_take_experiment_design.md`](../card_value_take_experiment_design.md)、[`scripts/card_value_v01.py`](../scripts/card_value_v01.py)、[`scripts/simulate_first_prestige_v1.py`](../scripts/simulate_first_prestige_v1.py)。将来構想と現行実装は区別する。

| 論点 | 現在の判断 |
|---|---|
| 単位・比率 | 各軸を共通H内の遭遇1回あたりの未加重PEとして比較。`total_pe = 0.60 * (Immediate + Conditional) + 0.25 * Growth + 0.15 * XP`。Combat/Growth/XPは**60/25/15**、軸間で二重加算しない。既存のriskは対応する軸の差分で扱う。 |
| baseline H | 候補取得前のbaseline状態のコピーを、現在の選択位相（XP支払済み/確定カード）に合わせて正規化し、次のWaveからbaseline予測終端まで。予測失敗した最後の敵を含み、撃破していない敵にXP/成長を与えない。**同一判断の全候補に共通**。候補ごとに期間を延長せず、固定100 Waveにも戻さない。予測の将来装備や取得率は未校正。 |
| Conditional | Execution / Time Collapseは現行の遭遇ごとの戦闘結果・TTKを用いる（[`card_value_encounter_conditional_design.md`](../card_value_encounter_conditional_design.md)）。他のカードへ無条件に広げない。 |
| XP追加Draft | XP系候補では同じLv `j` のcandidate/baseline取得Wave `t_c(j)`/`t_b(j)`を対応付け、各Wave時点の状態・合法プールから**共通Hの残期間**で`V_c(t_c(j)) - V_b(t_b(j))`を計算してXP軸へ帰属。H外は0、具体的な未来カード系列を引かない。取得Waveが同じでも状態/プール差を許す（[`card_value_xp_draft_h_design.md`](../card_value_xp_draft_h_design.md)）。 |
| terminal PE | `terminal_break_probability_delta`は**未校正の診断値**。`terminal_pe=None`、`terminal_included=False`で`total_pe`/Take順位に足さない。継続価値と確率ゲートの校正は未実装（[`predict_run_end_spec.md`](../predict_run_end_spec.md) §5は将来案）。 |
| Take限定の切替 | `take_mode=legacy`が**既定**。formal Balancedの`pe`は最終手札の**Takeカード順位のみ**をPEに変更。Reroll停止/除外は旧score、Refine判定は旧最良候補のscore、Upgradeは取得後のstateで従来の`spend_card_points`。Damage/SynergyにPEを適用せず、CLIのVariant D/EではPE指定を拒否。 |
| fallback | **2026-09-26決定:** 最終手札の**合法Take候補のみ**を検査・PE評価し、1枚でも未対応/無効`total_pe`なら合法候補全体の順位をlegacyへ戻し理由を記録。Take不能カードは評価せずfallbackにも含めない。`hand_keys`は全提示カードを保持し、`eligible_keys`/`ineligible_keys`/`evaluated_pe_keys`を分離する。旧scoreとPEを候補単位で混用しない。`prediction_confidence=low`は有効な有限値なら排除しない。全件有効なら最大PEを選び、同値は手札順で決定。 |
| 比較・解釈 | 同初期seed/試行ID/設定でlegacyとpeを別RNGで対実行。最初の選択差以降のstate/RNG一致は要求しない。初回10組は探索的診断で、成功率や強さの優劣を結論にしない。 |

**採用を決めていない案:** 未対応keyをgreedy集計順に追加実装する方針。[`output/card_value_take_eligible_greedy_audit.md`](../output/card_value_take_eligible_greedy_audit.md) は**旧仕様のJSONLからの反実仮想上限**であり、新仕様での実測値ではない。共通CardValueをReroll/Refine/Upgradeへ広げるのも将来仕様で、現在の確定実装ではない。

**履歴:** 旧10組パイロットは全提示カード判定で実施した。2026-09-26にユーザーが合法候補限定へ変更を決定した。旧出力はそのまま保持し、変更後の実験は別ファイルへ保存する。
