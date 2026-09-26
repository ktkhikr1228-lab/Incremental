# HANDOFF — 次回セッションの開始点（2026-09-26）

## 最重要問題

旧formal BalancedのCardValue v0.1は部分対応。**最終手札の合法Take候補だけ**へfallback判定・PE評価を変更し、同seed10ペアでPE適用 **180/1,477（12.19%）**、fallback **1,297/1,477（87.81%）**、すべて`unsupported_card`。旧・全提示カード判定の10組は54/1,477（3.66%）で、旧出力は保持。予測信頼度は低く、同点/短いHで順位の識別力が不足し得る。到達Waveや成功率の優劣を10組から判断しない。

## 優先順位（次の担当者が判断・着手するとき）

1. **新仕様の実測を確認。** PE評価・fallbackは最終手札の合法Take候補だけ。Take不能カードは未評価のままログに残す。`hand_keys`は全提示カード、`eligible_keys`/`ineligible_keys`/`evaluated_pe_keys`は分離。新レポート [`output/card_value_take_eligible_pilot_10.md`](../output/card_value_take_eligible_pilot_10.md) を読む。旧10組は保持する。
2. **次の追加対応は未決。** 旧ログからの合法候補限定180/1,477という反実仮想と、新実測180/1,477は一致したが同一実験ではない。greedy10 key後の1,252/1,477（84.77%）は新規カード未実装・未評価の**構造上限**のまま。未対応keyのPE有効性や計算コストを検証せず実装優先順位を確定しない。
3. **将来の作業候補（依頼・合意後のみ）:** 予測H、将来Draft取得率/装備・terminalの校正、同値選択や短Hの診断、未対応カード追加の設計とテスト。変更時はRNG/state不変と手札単位fallbackを維持し、単体・回帰テスト後にsmall trial first。新W5000用CardValueは別途設計する。

## 触らない部分・未解決の食い違い

- 今回はPE Takeのfallback判定範囲と関連ログ・テスト・設計文書のみ変更。ゲームバランス/カード効果/CardValue算出式/旧10組の出力は変更しない。旧formal W10000と新W5000実験群を統合しない。`first_prestige_v1_spec.md`を推測で修正しない。`terminal_pe`を加算しない。
- [`CURRENT_STATE.md`](CURRENT_STATE.md) の「要確認・履歴」を読む。fallback判定範囲の不一致は解消済み。旧CardValue specの「本体選択は旧scoreのみ」は任意PE Take実装以前の記述。`output/card_value_v01_validity_diagnostic.md`はEncounter条件値修正前の人工状態であり、現行値の証拠にはしない。
- gitの未追跡ファイルが多い。`git status --short`の`??`を不要物と判断せず、ユーザーの作業を保持する。

## 再現・検証

```bash
python3 -m unittest discover -s scripts -p 'test_*.py' -q
# 既存ログの再読だけなら以下のペア実験は実行不要。新たに依頼された場合に限り、出力先を変えて少数から試す。
python3 scripts/run_card_value_take_experiment.py --trials 1 --max-attempts 10 --seed 20260828 --output-prefix output/card_value_take_smoke_next
```

2026-09-26に `python3 -m unittest discover -s scripts -p 'test_*.py' -q` を実行し、**48件OK**。新パイロットはseed `20260828`、Balanced/POあり、旧と同じtrial ID 0..9、legacy/PE各10（計20 trial）、各trial最大10 attempts、workers=1。PE適用180/1,477（12.19%）、fallback1,297（87.81%、理由すべて未対応カード）、初分岐9/10、zero-PE tie 1、positive tie 3（上位2候補差≤1e-10、いずれも厳密同値）、機械的な違法Take・非最大PE 0。旧パイロット比+126件・+8.53ポイント。新旧出力は別ファイルで、旧3ファイルのSHA-256は実行前後で一致。これらは探索的な数値。

2026-09-26の決定に従い、`scripts/simulate_first_prestige_v1.py`、`scripts/run_card_value_take_experiment.py`、`scripts/test_card_value_take_mode.py`、`card_value_take_experiment_design.md`、`AGENTS.md`、`docs/CURRENT_STATE.md`、`docs/DECISIONS.md`、本ファイルを更新。runnerの新既定prefixは`output/card_value_take_eligible_pilot_10`。本作業ではレポートにCombat合算PE、zero/positive tie内訳、旧仕様との差分を追加し、1ペアのスモーク後に10ペアを実行。次の一手は新レポートの低信頼・同点ケースを点検し、次の変更判断はユーザーの指示を待つこと。

同じ新10組JSONLの追加集計は[`output/card_value_take_eligible_unsupported_10.md`](../output/card_value_take_eligible_unsupported_10.md)、[JSON](../output/card_value_take_eligible_unsupported_10.json)、[全2/3 key組合せCSV](../output/card_value_take_eligible_unsupported_10_combinations.csv)。Take 1,477中PE適用180、未対応1 key 433手札・2 key 615・3 key 249。greedyは4 keyで34.46%、7 keyで58.70%、8 keyで69.94%、9 keyで82.87%。**PEの実測増分ではなく固定手札の構造上限**。`overflow`はformalのカード定義で`rule`タグを持つが、戦闘処理に個別効果の参照が見当たらず**要確認**。CardValue実装・ゲーム本体・既存JSONLは変更していない。検証はJSONLから独立再集計した出現件数/組合せ合計（615+249）/単独433、全key導入時の累積1,477を照合。次の作業は必要なカード効果仕様（特に`overflow`）の確認後に優先順位を判断すること。

**Overflow formal v1調査:** [`OVERFLOW_FORMAL_AUDIT.md`](OVERFLOW_FORMAL_AUDIT.md)。formalでのキー固有参照はRare unique/crit/ruleの定義と`POTENTIAL=0.05`による旧選択scoreだけ。共通取得処理・タグ数・将来の選択には間接効果があるが、Crit/DPS/TTKへの固有分岐は見つからない。Crit率1%・121%（Multi-Critなし/あり）のコピー前後でもlog DPS差0。`scripts/test_*.py`にOverflow固有テストなし。playtestの説明文や別系列の新W5000には上限に関する記述・実装があるため、formalの意図をコードから一意に復元できず**要仕様確認、CardValue化は保留**。本調査ではformal本体・CardValue・spec・テストを変更していない。次はformalで意図する100%超Critの表示/シナジー/DamageとMulti-Critとの関係をユーザーに確認する。

**blocked_specを反映した固定ログ再集計:** `output/card_value_take_eligible_pilot_10_branches.jsonl`のPE Take 1,477手札を対象に、`overflow`だけを追加対応候補から除いてgreedyを再実行。理論greedyの先頭25 keyと同順。30%は先頭4 keyで509/1,477（34.46%）、50%は7 keyで867/1,477（58.70%）、70%/80%は9 keyで1,224/1,477（82.87%）。各目標のkey集合・累積値は理論greedyと**差0**。全25 key後の構造上限は1,475/1,477（99.86%）で、`overflow`を含む2手札は残る（理論上限100%との差-2手札）。CardValue・戦闘仕様・固定ログは変更していない。次の実装候補を決める際も`overflow`は仕様確定まで除外する。

## ファイル案内（推奨読順）

1. このファイル → [`CURRENT_STATE.md`](CURRENT_STATE.md) → [`DECISIONS.md`](DECISIONS.md) → [`../AGENTS.md`](../AGENTS.md)。
2. 現行仕様の位置付け: [`../first_prestige_v1_spec.md`](../first_prestige_v1_spec.md)、[`../card_value_evaluation_spec.md`](../card_value_evaluation_spec.md)、[`../card_value_take_experiment_design.md`](../card_value_take_experiment_design.md)、[`../predict_run_end_spec.md`](../predict_run_end_spec.md)、[`../card_value_encounter_conditional_design.md`](../card_value_encounter_conditional_design.md)、[`../card_value_xp_draft_h_design.md`](../card_value_xp_draft_h_design.md)。
3. 現行実装・テスト: [`../scripts/simulate_first_prestige_v1.py`](../scripts/simulate_first_prestige_v1.py)、[`../scripts/card_value_v01.py`](../scripts/card_value_v01.py)、[`../scripts/run_card_value_take_experiment.py`](../scripts/run_card_value_take_experiment.py)、[`../scripts/test_card_value_take_mode.py`](../scripts/test_card_value_take_mode.py)、他の`../scripts/test_card_value_*.py`。
4. 直近の事実: 新仕様の[`../output/card_value_take_eligible_pilot_10.md`](../output/card_value_take_eligible_pilot_10.md)、[集計JSON](../output/card_value_take_eligible_pilot_10.json)、[全判断JSONL](../output/card_value_take_eligible_pilot_10_branches.jsonl)。旧仕様の[`../output/card_value_take_pilot_10.md`](../output/card_value_take_pilot_10.md)、[`../output/card_value_take_pilot_10.json`](../output/card_value_take_pilot_10.json)、[`../output/card_value_take_pilot_10_branches.jsonl`](../output/card_value_take_pilot_10_branches.jsonl)。反実仮想[`../output/card_value_take_eligible_greedy_audit.md`](../output/card_value_take_eligible_greedy_audit.md)。新W5000の結果を見る場合は用途とtargetを先に確認（例: [`../output/new_w5000_legendary_v01_8card_30/new_w5000_legendary_v01.md`](../output/new_w5000_legendary_v01_8card_30/new_w5000_legendary_v01.md)）。

作業後は本ファイルに**何を変更したか・検証結果・次の一手**を追記し、引き継ぎを最新にする。
