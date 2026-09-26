# 現在の状態（2026-09-26: 合法候補限定の10組実施済み）

この文書は状態のスナップショット。確定判断は [`DECISIONS.md`](DECISIONS.md)、次の作業は [`HANDOFF.md`](HANDOFF.md) を参照。数値は該当ファイルの時点・条件付きであり、再試行や他系列へ外挿しない。

## 実装済みの系列

- **旧formal第一転生 / W10000:** [`first_prestige_v1_spec.md`](../first_prestige_v1_spec.md)、[`scripts/simulate_first_prestige_v1.py`](../scripts/simulate_first_prestige_v1.py)。Wave/敵・カードプール・XP/DP・武器/遺物・Refine/Upgrade、各profileの旧選択経路を持つ。`SimConfig.target_wave=10000`、`take_mode="legacy"`が既定。同ファイルの`--variant D|E`はtarget W5000の実験設定で、下記の新W5000候補群とは別。
- **新W5000候補の独立プローブ:** [`scripts/simulate_new_w5000_common_uncommon.py`](../scripts/simulate_new_w5000_common_uncommon.py)、同`_rare.py`、`_rare_epic.py`、[`scripts/simulate_new_w5000_dp_v01.py`](../scripts/simulate_new_w5000_dp_v01.py)、[`scripts/simulate_new_w5000_legendary_v01.py`](../scripts/simulate_new_w5000_legendary_v01.py)、武器関連の比較スクリプト。formalをメカニクスとしてimportするが、候補カード/経済/装備等の設定は別。例: [`output/new_w5000_legendary_v01_8card_30/new_w5000_legendary_v01.md`](../output/new_w5000_legendary_v01_8card_30/new_w5000_legendary_v01.md) は30 trial、**target W1000**の途中診断（W5000達成実験ではない）、正式採用の宣言ではない。新W5000へ旧formalのCardValue PEを流用していない。

## CardValue v0.1 とTake実験

- [`scripts/card_value_v01.py`](../scripts/card_value_v01.py) は旧formal Balancedの部分実装。`TARGET_KEYS`は16 key（formalのカードプールは55枚）。baseline `predict_run_end`が**候補取得前**の現在Run残期間Hを決定し、同じ手札の候補は共通Hで比較。将来のランダム装備と具体的な未来カード列は予測しない。Draft取得を上限寄りに扱う未校正の近似があり、confidenceは低くなりやすい。Combat（Immediate + Conditional）/Growth/XPを60/25/15で一度だけ加重する。Execution/Time Collapseは遭遇の離散勝敗・TTKに基づくConditional、XP系候補はLvごとのcandidate/baseline Draft Waveと状態別プールに基づくH内XP価値。`terminal_break_probability_delta`は診断用、`terminal_pe=None`で合計へ非加算。
- [`scripts/simulate_first_prestige_v1.py`](../scripts/simulate_first_prestige_v1.py) の`--take-mode legacy|pe`は既定`legacy`。Balanced `pe`時のみ、旧Reroll/Refine後の**最終Take候補順位**をPEへ変更する。Upgradeも旧経路。**最終手札の合法Take候補だけ**をPE評価・fallback判定し、Take不能カードは評価しない。合法候補が1枚でも未対応・無効PEなら合法候補全体の順位をlegacyへ戻す。`hand_keys`は全提示カードを維持し、`eligible_keys`、`ineligible_keys`、`evaluated_pe_keys`を分離。PE同値は手札順。診断shadow CSVと選択JSONLは別フック。`--take-branch-output`は`--workers 1`が必要。ペア実験は[`scripts/run_card_value_take_experiment.py`](../scripts/run_card_value_take_experiment.py)（新既定prefix `output/card_value_take_eligible_pilot_10`）。
- 未実装: CardValueの全55カード対応、Reroll/Refine/Upgradeの共通PE化、校正済み将来Draft取得率/ランダム装備・未来取得カードを考慮した終端予測、`terminal_pe`の継続価値への換算、新W5000候補へのCardValue adapter。`predict_run_end_spec.md`のフル仕様が完成したわけではない。

## 検証と最新の数値

- 2026-09-26に `python3 -m unittest discover -s scripts -p 'test_*.py' -q` を実行: **48件、OK**（CardValue/遭遇/XP Draft/Takeと実験レポートのテスト）。この4ファイル以外の全スクリプトが試験された意味ではない。以前のshadow実Runスモークは12候補でエラー0（[`output/card_value_v01_shadow_smoke.md`](../output/card_value_v01_shadow_smoke.md)）。
- **旧・全提示カードfallback仕様の履歴:** [`output/card_value_take_pilot_10.md`](../output/card_value_take_pilot_10.md)、[集計JSON](../output/card_value_take_pilot_10.json)、[全判断JSONL](../output/card_value_take_pilot_10_branches.jsonl): seed `20260828`、Balanced / POあり、同seed `trial_index=0..9` × legacy/pe、各trial最大10 attempts、合計20 trial、workers=1。PEモードのTake **1,477件中54件（3.66%）適用**、**1,423件（96.34%）fallback**。理由はすべて`unsupported_card`。最初の選択分岐は8/10組、PE同値のTakeが4件、レポートの機械的な違法/非最大PE検出は0。**これは旧仕様の数値**。成功率の優劣は判断しない。
- **新・合法Take候補限定の実測:** [`output/card_value_take_eligible_pilot_10.md`](../output/card_value_take_eligible_pilot_10.md)、[集計JSON](../output/card_value_take_eligible_pilot_10.json)、[JSONL](../output/card_value_take_eligible_pilot_10_branches.jsonl)。同seed `20260828`、同trial ID 0..9、POあり、legacy/PE各10、最大10 attempts。PE適用 **180/1,477（12.19%）**、fallback **1,297/1,477（87.81%）**で理由はすべて`unsupported_card`。初選択分岐9/10組。zero-PE tie 1件、positive tie 3件（上位2候補差≤1e-10、今回いずれも厳密同値）。機械的な違法Take・非最大PEの選択0件。旧仕様比+126件・+8.53ポイント、fallback -126件。旧出力は未変更。少数実験から到達Waveや成功率の優劣は言えない。
- 旧仕様のfallback未対応key別出現手札は[`output/card_value_take_pilot_10.json`](../output/card_value_take_pilot_10.json)に保存。上位は`precise_strike`274、`steady_force`269、`critical_eye`264、`glass_cannon`264、`heavy_blow`255。1手札内に複数keyがあり、出現数を合算してもfallback件数にはならない。旧仕様で未対応keyが唯一の障害だった手札は436（1 key対応時の**構造的な増分上限**）。
- [`output/card_value_take_eligible_greedy_audit.md`](../output/card_value_take_eligible_greedy_audit.md): **旧ログからの反実仮想**。合法Take候補だけをfallback対象にした構造上の適用可能数は180/1,477（12.19%）で、新実測と数値が一致したが、分岐後の状態まで予測したものではない。greedyに10 keyを追加した場合の **1,252/1,477 = 84.77%** は依然として構造上限で、新規カードのPE有効性は未検証。順序と各段階の限界増分はレポート参照。
- [`output/card_value_take_eligible_unsupported_10.md`](../output/card_value_take_eligible_unsupported_10.md): **新10組JSONLから**合法Take候補内の未対応keyを再集計。単独433手札、2 key 615、3 key 249。単独keyの増分、262種類の2/3 key exact組合せ、全26 keyのgreedy構造上限、30/50/70/80%到達prefix、および暫定CardValue化分類を保存。PE実測180/1,477とは区別する。
- `overflow`はformal Rare unique/crit/ruleとして定義され、旧選択scoreの`POTENTIAL`に登録されているが、formal戦闘計算にはキー固有の適用箇所が見つからない。取得時のタグ等の共通効果と、意図されたCrit上限解除を混同しない。専用テストなし、**効果仕様は要仕様確認・CardValue化保留**。調査: [`docs/OVERFLOW_FORMAL_AUDIT.md`](OVERFLOW_FORMAL_AUDIT.md)。

## 要確認（原文・実装はこの引き継ぎでは変更しない）

1. **解消済み（履歴）:** [`card_value_take_experiment_design.md`](../card_value_take_experiment_design.md) の擬似コードと§2は合法候補限定で統一。旧10組レポートとJSONLは全提示カード判定の結果として残し、再解釈や上書きをしない。
2. [`card_value_evaluation_spec.md`](../card_value_evaluation_spec.md) 冒頭や [`card_value_encounter_conditional_design.md`](../card_value_encounter_conditional_design.md) は「本体の選択は旧scoreのみ」「Takeは旧score」と記す。現在は既定legacyだが、任意の`pe` Takeモードが実装済み。これらは当時の設計段階の記述で、オンラインの全行動共通PE化が済んだ意味ではない。
3. [`predict_run_end_spec.md`](../predict_run_end_spec.md) および [`card_value_v01_implementation_plan.md`](../card_value_v01_implementation_plan.md) の「実装前」「未決」はフル構想や当時の計画を指す。実際には部分的な予測器が実装済みで、将来取得率やterminal換算は未校正。計画と実装の境界を確認すること。
4. [`output/card_value_v01_validity_diagnostic.md`](../output/card_value_v01_validity_diagnostic.md) はEncounter-based Conditional導入の**前**の人工状態診断（余裕/壁の値が同じとの旧結果）。現行のExecution/Time CollapseのPE値として引用しない。同様に [`output/card_value_v01_shadow_smoke.md`](../output/card_value_v01_shadow_smoke.md) は過去のshadow結果で現行のPE Takeパイロット値ではない。
