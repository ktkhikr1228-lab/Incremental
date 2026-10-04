# 現在の状態（2026-09-27: CardValue 9-key freeze / w5000_v1 scaffold）

## 最新（2026-10-04: 新W5000試遊操作改善）

カード選択・鞄・設定は戦闘を停止しない。選択権蓄積、武器全品比較、装備/保管/即分解、鞄drag/drop、カードrarity色とクリック説明を接続。死亡後のみ手動再挑戦待ち。今回balance値は変更なし。
158 scripts tests / TypeScript / production build成功、短いブラウザ操作検証済み。詳細はHANDOFF最新節。スマホ専用UI・保存・未接続後半システムは未実装。

## 最新（2026-10-04: 新W5000手動候補へ切替）

- Mainは新カード47枚/BC DP v0.1/個体Drop武器の独立候補。旧カード・旧DP巨大倍率の仮接続は解消。旧formal/D/E・CardValueは変更なし。
- 149 tests・TypeScript成功、死亡多重加算修正、画面/APIを確認。全遺物・武器固有・Core/UB/Finale・Refine UI・保存/拡張は未接続。12hバランスの結論なし。
- 詳細は`NEW_W5000_PLAY_CANDIDATE.md`。下の旧接続記述は履歴。

## 2026-10-04: Figma Main / 個体装備UI候補

- playtestに独立equipmentModeを追加。鞄・装備3遺物枠・個体保管/詳細/強化/炉/同名処理、Mainカード横スクロールを接続。Figmaは変更なし。
- W10武器とW100学習レンズのみ初期報酬接続。旧Weapon/Relic Powerとの二重適用なし。新カード/DP/武器成長/全遺物/保存/拡張/UBは未統合。カード・DPと武器曲線は明示的な旧値仮接続。
- scriptsテスト131件・TypeScript成功、W10受取/装備をブラウザ確認。balanceシミュレーションなし。詳細はHANDOFF最新項目。

## 2026-10-03: 新W5000個体装備基盤（未接続）

- `scripts/w5000_equipment_v01.py` と10単体テストを追加。個体・装備・保管・強化・分解・同名処理・死亡/転生・シリアライズ対応。
- 全123テスト成功。既存formal/D/E/w5000/playtestには未接続、戦闘効果とディスク保存も未実装。候補仕様は `W5000_EQUIPMENT_V01.md`。

## 2026-09-27: v2 Barrage後半baseline 4条件診断

- v2 fixed-ratio / Core15% / late-DP10% / base-heavy Bで、Finale OFF/ON × Boost OFF/v0.2を保存済み10状態から比較。全条件W4000到達1/10。
- Finale OFFはBoost有無ともW5000 1/10。Boost v0.2は成功Marginを+13.47→+26.21へ増やしたが成功集合は不変。
- Finale ONはW5000 0/10。最高WaveはBoost OFF W4585、Boost v0.2 W4697。Finale追加Powerにより段階壁が成立し、Boostだけでは突破不能。
- 唯一のW5000成功はBarrage非取得。v2取得群は0成功。小標本につき一般化・採用なし。結果: [`../output/w5000_v1_v2_late_baseline_10_states_final/v2_late_baseline_report.md`](../output/w5000_v1_v2_late_baseline_10_states_final/v2_late_baseline_report.md)。

## 2026-09-27: Infinite Barrage v2 experimental implementation

- 診断専用`v2_fixed_ratio`を追加。既定`legacy`とformal値は不変。N=20、Barrage=通常攻撃5発分で、AS 100～20000でもBarrage/normal=25%、追加Power=+0.096910一定。
- 既存kill-growthを使うCは成長寄与だけ0.25 Power漸近softcap。Run終端のBarrage寄与はB +0.0969、C 約+0.1597でAS帯に依存せず、A currentは+73.77～+743.58。
- 保存済みW2500 10状態のpaired replayではW5000到達A/B/C=7/0/0、W4500=7/1/1。構造的暴走は解消したが進行力不足。正式採用なし。結果: [`../output/w5000_v1_infinite_barrage_v2_10_states_final/infinite_barrage_v2_report.md`](../output/w5000_v1_infinite_barrage_v2_10_states_final/infinite_barrage_v2_report.md)。

この文書は状態のスナップショット。確定判断は [`DECISIONS.md`](DECISIONS.md)、次の作業は [`HANDOFF.md`](HANDOFF.md) を参照。数値は該当ファイルの時点・条件付きであり、再試行や他系列へ外挿しない。

## 2026-09-27: Infinite Barrage 37.5%下のlate DP診断

- W2500後DP combat contribution 10/25/50%でW5000成功率50/60/80%、Barrage取得trial成功5/7、6/7、8/8。
- W5000でのlate-DP直接寄与P50は+27.87/+54.14/+121.91 Power。50%はBarrage取得が再び突破保証となり、Core主成長の余地を奪うため過剰。
- 10～25%を候補帯として残す。10%はCore余地最大、25%は上限寄り。正式採用・Core ON・他調整は未実施。
- 結果: [`../output/w5000_v1_late_dp_barrage375_10_states_final/late_dp_barrage375_report.md`](../output/w5000_v1_late_dp_barrage375_10_states_final/late_dp_barrage375_report.md)。

## 2026-09-27: Infinite Barrage 37.5%追加診断

- 同一W2500保存10状態で37.5%だけを追加。W3000/3500/4000/4500/5000到達率=70/70/60/50/50%、Best Wave P50=4559。
- Infinite Barrage取得trial限定のW5000成功は5/7=71%。25%の3/7と50%の6/7の中間に入り、「非常に強いが単独突破保証ではない」挙動を確認。
- 初回取得ΔPower P50=+103.46、取得後追加Wave P50=4290、terminal margin P50=+4.17。正式採用・他値調整なし。
- 結果: [`../output/w5000_v1_infinite_barrage_strength_37_5_10_states_final/infinite_barrage_strength_report.md`](../output/w5000_v1_infinite_barrage_strength_37_5_10_states_final/infinite_barrage_strength_report.md)。

## 2026-09-27: Infinite Barrage strength診断

- 既存W2500到達10状態から効果強度0/25/50/75/100%を比較。初回取得signatureは全条件一致し、取得確率・rarity・履歴処理は維持。
- W5000成功率は全trialで0/30/60/70/70%、Infinite Barrage取得trial限定で0/43/86/100/100%。75%以上は取得が突破保証になり、50%は強いが非確定、25%は後半checkpointで段階的脱落。
- 最初の取得時ΔPower P50は0/+68.98/+137.95/+206.93/+275.90。線形strength実装を確認。
- 25～50%を次の詳細候補帯として記録するが正式採用しない。結果: [`../output/w5000_v1_infinite_barrage_strength_10_states_final/infinite_barrage_strength_report.md`](../output/w5000_v1_infinite_barrage_strength_10_states_final/infinite_barrage_strength_report.md)。

## 2026-09-26: W2500後Card effect suppression診断

- `late_dp_10`（診断baseline、未採用）/ Core OFF / DP v0.1 / Boss Devourer base-heavy B / W2500確定Legendary OFFで、保存済みW2500到達10状態を使用。
- W5000成功率はcurrent 70%、Legendary効果抑止0%、Epic抑止60%、Rare抑止70%、Epic+Legendary抑止0%。カード取得・記録・poolは変えず効果のみ抑止。
- `Infinite Barrage`は成功Run取得率100%、失敗Run0%。単独効果抑止で成功率70%→0%、ΔBest Wave P50 -2195、Δterminal Power P50 -406.23。現サンプルの当たりRun分岐はこのカードへ集中。
- 指定Legendaryのうち`Critical Overload` / `Endless Action` / `Fractal Barrage` / `Supplemental Singularity`は現行pool未実装。別probeから混ぜていない。
- 診断runner: [`../scripts/diagnose_w5000_v1_card_effect_suppression.py`](../scripts/diagnose_w5000_v1_card_effect_suppression.py)。結果: [`../output/w5000_v1_card_effect_suppression_10_states_final/card_effect_suppression_report.md`](../output/w5000_v1_card_effect_suppression_10_states_final/card_effect_suppression_report.md)。formal/balance値は未変更、error/nonfinite/overflow 0、全95テストOK。

## 2026-09-26: W2500後DP寄与率の診断

- W2500以前の取得済みDP効果を維持し、以後の新規DP Lv効果だけを100/50/25/10%へscale。DP economyと購入Lv数は変更していない。
- W5000到達率80/80/70/70%、成功時Margin P50 +944.9/+685.9/+418.1/+273.4。50%は成功率を維持して余裕を縮小し、10%はCore余地を最大化したが、いずれも正式採用していない。
- Best Wave分散はscale低下で改善せず、100% 686,185に対し10% 1,077,002。Best−直近10Run P50も全条件約3,400～3,570 Waveで、late DP寄与縮小だけではCard RNG閾値とRun再現性を解消しない。
- CoreはOFF、medium 20%は暫定候補・未採用のまま。結果: [`../output/w5000_v1_late_dp_scaling_10_states_final/late_dp_scaling_report.md`](../output/w5000_v1_late_dp_scaling_10_states_final/late_dp_scaling_report.md)。error/nonfinite/overflow 0、全92テストOK。

## 2026-09-26: W2500後Power爆発の成長源

- no_coreの既存W2500到達10状態から後続Runを含めて診断。現状W5000到達8/10・成功時Margin P50 +944.9に対し、DP停止6/10・+283.6、Weapon恒久進行停止8/10・+912.4、Relic進行停止8/10・+786.1、全恒久進行停止7/10・+208.1。
- 成功者集合差を含むためMargin差は厳密な加法分解ではないが、+600～+1300 Power余裕の最大要因はDP累積、次点はRelic進行。Weapon素材/生成/品質のW2500後進行だけを止めた影響は小さい。
- Card RNGを後続Runごとに固定するとW5000到達は1/10へ低下。Card再抽選は成功確率を支配するが、成功した固定列のMarginは+1178 Powerで、余裕量を抑制しない。
- Core探索は停止。weak increment 20%版は暫定候補として記録しただけで未採用。結果: [`../output/w5000_v1_post2500_growth_10_states_final/post2500_growth_report.md`](../output/w5000_v1_post2500_growth_10_states_final/post2500_growth_report.md)。error/nonfinite/overflow 0、全90テストOK。

## 2026-09-26: Core first-run-only寄与分離

- 同一W2500到達10状態から、死亡後成長を一切行わない1 Run限定replayを実施。Core以外の開始state/RNG/configは共通。
- max Wave P50はno_core 2582、micro 2602.5、low 2623、medium 2690、existing weak 5000。W5000直行は0/10、0/10、0/10、1/10、10/10。
- mediumは複数checkpointで段階的脱落が見える唯一の低係数候補だが、W3000到達3/10、W5000 1/10。existing weakは全件直行し、直接Core寄与もW5000 +495 Powerで過剰。
- low以下の延長は中央値+20.5～41 Wave、mediumは+108 Wave。正式値の採用や新係数追加はしていない。結果: [`../output/w5000_v1_core_first_run_10_states_final/core_first_run_report.md`](../output/w5000_v1_core_first_run_10_states_final/core_first_run_report.md)。error/nonfinite/overflow 0、全88テストOK。

## 2026-09-26: weak未満Core帯のpaired replay

- 保存・再現した同一W2500到達10状態から、既存weakのincrementのみを0/5/10/20%へscaleして比較。正式値、段階構造、Big Boss timing、DP、Boss Devourer、敵、Weapon、Relic、他カードは変更していない。
- W5000到達は8/10、7/10、7/10、8/10。同一Run直行は0/10、0/10、0/10、1/10。最初の停止は大半がW2500～2999で、複数の後半壁を形成しなかった。
- no_coreでも8/10が残りRun内にW5000へ到達し、成功時W5000 Margin P50は全条件+638～+1374 Power。Coreの小係数差より、後続Runで生じる他成長の方が支配的な状態である。今回の4候補から正式値や次の探索帯は採用していない。
- 結果: [`../output/w5000_v1_micro_core_10_states_final/micro_core_report.md`](../output/w5000_v1_micro_core_10_states_final/micro_core_report.md)。元trialの残りRun上限を維持し、error/nonfinite/overflow 0、全88テストOK。

## 実装済みの系列

- **旧formal第一転生 / W10000:** [`first_prestige_v1_spec.md`](../first_prestige_v1_spec.md)、[`scripts/simulate_first_prestige_v1.py`](../scripts/simulate_first_prestige_v1.py)。Wave/敵・カードプール・XP/DP・武器/遺物・Refine/Upgrade、各profileの旧選択経路を持つ。`SimConfig.target_wave=10000`、`take_mode="legacy"`が既定。同ファイルの`--variant D|E`はtarget W5000の実験設定で、下記の新W5000候補群とは別。
- **新W5000候補の独立プローブ:** [`scripts/simulate_new_w5000_common_uncommon.py`](../scripts/simulate_new_w5000_common_uncommon.py)、同`_rare.py`、`_rare_epic.py`、[`scripts/simulate_new_w5000_dp_v01.py`](../scripts/simulate_new_w5000_dp_v01.py)、[`scripts/simulate_new_w5000_legendary_v01.py`](../scripts/simulate_new_w5000_legendary_v01.py)、武器関連の比較スクリプト。formalをメカニクスとしてimportするが、候補カード/経済/装備等の設定は別。例: [`output/new_w5000_legendary_v01_8card_30/new_w5000_legendary_v01.md`](../output/new_w5000_legendary_v01_8card_30/new_w5000_legendary_v01.md) は30 trial、**target W1000**の途中診断（W5000達成実験ではない）、正式採用の宣言ではない。新W5000へ旧formalのCardValue PEを流用していない。
- **`w5000_v1` scaffold:** [`scripts/w5000_v1_profile.py`](../scripts/w5000_v1_profile.py) と [`scripts/simulate_w5000_v1.py`](../scripts/simulate_w5000_v1.py)。legacy formal/D/Eを変更せず、target W5000、W5000 Enemy Power 308、W2500以降3倍圧縮、Final Equation/Defense/Reward Skip無効、Refinement最大+1を独立設定として持つ。scaffold既定のCoreは無効。Coreだけを交換する4実験profileと10-pair runnerは追加済みだが、係数は未採用。DP/Weapon/Relicはlegacy placeholderであり、新候補値の正式採用ではない。CardValueは未統合。

## CardValue v0.1 とTake実験

- [`scripts/card_value_v01.py`](../scripts/card_value_v01.py) は旧formal Balancedの部分実装。`TARGET_KEYS`は25 key（formalのカードプールは55枚）。baseline `predict_run_end`が**候補取得前**の現在Run残期間Hを決定し、同じ手札の候補は共通Hで比較。将来のランダム装備と具体的な未来カード列は予測しない。Draft取得を上限寄りに扱う未校正の近似があり、confidenceは低くなりやすい。Combat（Immediate + Conditional）/Growth/XPを60/25/15で一度だけ加重する。Execution/Time Collapse/Glass Cannonは遭遇の離散勝敗・TTKに基づくConditional、XP系候補は明示的な12-key集合でLvごとのcandidate/baseline Draft Waveと状態別プールに基づくH内XP価値。`terminal_break_probability_delta`は診断用、`terminal_pe=None`で合計へ非加算。
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

## 2026-09-26: CardValue Take対応を9 keyまで拡張

- XP Draft分類をTARGET_KEYSからの差集合ではなく、意味が明示された12-key集合に固定。4/7/9-key各段階の10-pair診断と、比較上の注意は[`../output/card_value_take_stages_1-3_comparison.md`](../output/card_value_take_stages_1-3_comparison.md)。
- Stage 1はPE 497/1,521 (32.68%)、Stage 2は900/1,584 (56.82%)、Stage 3は1,343/1,655 (81.15%)。全fallbackは未対応カード。全段階でfinite/state-RNG/illegal/non-max gate合格。pilotは探索的で、成績比較の根拠にしない。
- 対応keyは既存16に加え、Steady Force / Heavy Blow / Critical Eye / Precise Strike / Glass Cannon / Heavy Critical / Light Attack / Sharpened Edge / Critical Power。`overflow`を含む残30 keyは未対応で、Overflowはblocked_specのまま。
- 最終全体テスト: 59件OK。Stage固有テスト: 11件。
- ユーザー判断によりCardValue Take v0.1はこの9-key追加状態でfreeze。これ以上対応keyを増やさない。

## 2026-09-26: w5000_v1 scaffold

- `w5000_v1`専用profile/configとentry pointを追加。D/Eの`target_wave == 5000`分岐を暗黙継承しないよう、敵curve mappingとW2500以降のplayer progression指定をconfigへ明示できる。
- 新規profileテスト7件を含む全66件OK。1 trial / 最大2 attemptsのsmokeはentry point接続確認として完了し、best Wave 53、成功0。これはバランス評価ではない。出力は[`../output/w5000_v1_scaffold_smoke_1.json`](../output/w5000_v1_scaffold_smoke_1.json)。

## 2026-09-26: w5000_v1 Exponential Core比較基盤

- W2500非Draft取得、Base ATK指数、Big Bossごとの3段階加算、死亡時Run成長リセットをprofile化。`no_core`、候補`0.90/0.80/0.65`、各段階±0.05の弱/強版を同一seedで比較可能。旧formal/D/Eの固定指数経路は回帰テストで維持を確認。
- 10 paired trialsではW2500到達が1件のみ。到達した同一状態からno_coreはW3000未到達、Core 3種はW5000到達。profile間の非Core configとW2500までの到達可否/時刻は一致、nonfinite 0。少数かつ前半到達率10%のためCore係数の採用判断は不可。
- 結果: [`../output/w5000_v1_core_profiles_10/w5000_v1_core_profiles.md`](../output/w5000_v1_core_profiles_10/w5000_v1_core_profiles.md)。全72テストOK。

## 2026-09-26: w5000_v1 W2500前ボトルネック診断

- `no_core` 30 trialsではW1250まで全trial到達後、W1500 66.7%、W1750 40.0%、W2000 23.3%、W2250/W2500 13.3%へ低下。最高Wave中央値1705、最終死亡Wave中央値1120。
- 全trialが最大140 attemptsまで失敗を継続。最終死亡は900～1199へ20/30が集中。W2500以降のCore以前に、W1250～1750帯と後続Runの再現性が主要な停止要因。
- checkpoint初回到達時のDP/主要戦闘値/Weapon/Relic状態を診断用に保存可能にした。既存の最終Run checkpoint項目は維持。Core・DP・Weapon・Relic・敵曲線の値は変更していない。
- レポート: [`../output/w5000_v1_precore_bottleneck_30/w5000_v1_precore_bottleneck.md`](../output/w5000_v1_precore_bottleneck_30/w5000_v1_precore_bottleneck.md)。nonfinite/error 0、全72テストOK。

## 2026-09-26: w5000_v1 DP paired診断

- 既存DP v0.1 BCを`SimConfig.dp_v01`のopt-inとして比較可能にした。既定OFFなのでlegacy formal/D/E/w5000_v1既定は変更なし。個別コスト、死亡/Record/Big Boss DP、Reroll、個別Lv効果、Luck/Weapon Find/Qualityを既存候補値で使用。
- 30 pairedでは新DPがW1500～2500到達率を改善しW5000成功10/30を出したが、W1500後の後続Run単位再到達率は5.0%→5.3%でほぼ不変。恒久進行の底上げはあるがRun再現性崩壊は解消していない。
- W2500確定Legendaryと高ASの相互作用により新DP到達者のMargin P50が+546 Powerへ跳ねる。DP単体の効果として解釈しない。正式採用・値調整は未実施。
- レポート: [`../output/w5000_v1_dp_paired_30/w5000_v1_dp_paired.md`](../output/w5000_v1_dp_paired_30/w5000_v1_dp_paired.md)。nonfinite/error 0、全75テストOK。

## 2026-09-26: W2500確定Legendary分離診断

- `w5000_v1`の診断用profile引数でW2500確定Legendaryだけを無効化できる。既定は有効のままで、他系列・バランス値に変更なし。
- DP v0.1 BC / no Core / seed 20260828 / 30 pairedでは、W2500到達10/30はON/OFF同一。ONは全10件が`Infinite Barrage`を取得し即時+538.35 Power（P50）、W5000へ10/10到達。OFFは即時差0、W5000へ7/10到達。W2500巨大jumpは保証カード由来。
- W2250以前は全ペア一致するため、W1250～2000のRun再現性崩壊はW2500保証では説明できない。W1500～2499の到達Wave関連はBoss Devourer、カード総数、Relic/Weapon/Base ATK Power、Rare枚数が上位。ただし終了状態相関には逆因果があり、個別因果の確定ではない。
- 結果: [`../output/w5000_v1_guaranteed_legendary_30_final/w5000_v1_guaranteed_legendary.md`](../output/w5000_v1_guaranteed_legendary_30_final/w5000_v1_guaranteed_legendary.md)。nonfinite/error 0、全77テストOK。

## 2026-09-26: w5000_v1 experimental RNG split診断

- 診断専用でCard/Weapon/Relic/Combat RNGを独立stream化。既定は従来shared RNGで、legacy/formal/D/E/w5000_v1通常結果は変更しない。分離streamはbase seed・stream名・branchからSHA-256で決定論的に派生。
- W1000/1250/1500の保存状態から各7条件×6回、計3,738 replay。同一保存状態内の分散はCard固定で96.2～97.5%低下。Weapon固定は明確な低下なし、Relic固定は0%。Cardだけ可変で全可変と同程度の分散を再現したため、W1250～2000の後半Run分散はCard RNGが主因。
- Boss Devourerは全保存状態で既取得。取得Waveと成長unitを記録し、現在効果のみ抑止する89 matched pairsでは到達Wave差P50 +116。ただし過去の取得時に生じた他engine stackは維持する限定介入。
- 相関表は介入表と分離。Weapon/Relic Powerの高相関は到達Waveによる成長を含み、因果寄与とはしない。結果: [`../output/w5000_v1_rng_split_30_final/rng_split_report.md`](../output/w5000_v1_rng_split_30_final/rng_split_report.md)。全81テストOK、error/nonfinite 0。

## 2026-09-26: Card RNG内部split診断

- 診断replay限定でCard RNGをRarity/Hand-key/Rerollへ分離。通常・formal・w5000_v1の既定shared RNGは維持。
- W1000ではReroll固定が分散を61.8%削減、W1250ではRarity固定87.5%、W1500ではRarity固定32.8%が最大。Hand固定の削減は18.0%/16.0%/5.2%。抽選段階の主因は進行段階で変わる。
- 大差pairの最初のカード分岐はEscalationが突出。ただし相関/最初の分岐と単体カード効果は区別する。Boss Devourerだけは効果ON/OFFのmatched介入を実施し、平均Waveを+268～410押し上げる一方、OFFではcheckpoint直後に停止して分散0となる強い依存を確認。
- 結果: [`../output/w5000_v1_card_rng_split_30_final/card_rng_report.md`](../output/w5000_v1_card_rng_split_30_final/card_rng_report.md)。3,738 replay + 534 Boss pairs、error/nonfinite 0、全84テストOK。バランス変更なし。

## 2026-09-26: Boss Devourer checkpoint後成長のmatched介入

- 保存済みW1000/1250/1500 checkpointから、同一state・同一Card RNGで現行成長、以後freeze、以後50%、全効果OFFを比較。freeze/50%はcheckpoint時点の累積効果を保持するため、基礎寄与とその後の成長を分離している。
- 累積基礎寄与Power P50はW1000 +12.635、W1250 +19.566、W1500 +26.597。checkpoint後成長をfreezeするとCard RNGの同一state内分散は91.5%/94.3%/64.6%減少し、50%成長でも73.8%/84.2%/60.2%減少。
- W1500起点のW1750/W2000/W2250到達率はcurrent 62.1%/38.5%/23.0%、freeze 24.7%/8.6%/3.4%、50% 40.8%/18.4%/11.5%。現行Boss Devourerの後続成長は平均進行だけでなくCard RNG差の増幅にも大きく寄与する。
- 診断専用介入のみでformal値・通常profileは未変更。結果: [`../output/w5000_v1_boss_devourer_growth_30_final/boss_devourer_growth_report.md`](../output/w5000_v1_boss_devourer_growth_30_final/boss_devourer_growth_report.md)。2,136 replay、error/nonfinite 0、全85テストOK。

## 2026-09-26: Boss Devourer balance experiment

- 同seed 30 pairedで成長100%/75%/50%/50%+固定補償を比較。Dの補償はW1250/1500/1750後に各+4 Powerの単純な診断候補で、正式仕様ではない。
- Highest Wave meanは3068.8/1846.8/1324.9/1793.5、W2500到達率は50.0%/13.3%/0%/10.0%。補償は50%単独より進行を戻すが現行を維持できない。
- 非Card RNGを固定したCard-only分散は現行比で75%成長-66.9%、50%成長-96.1%、補償-35.0%。固定補償の受給Wave自体が閾値となり、分散が50%単独より再拡大した。
- W1500後のRun再到達率は9.0%/4.0%/0%/6.5%。今回の補償1案では「平均進行維持」と「Card RNG分散低減」を同時達成していないため採用判断不可。
- 結果: [`../output/w5000_v1_boss_devourer_balance_30_final/boss_devourer_balance_report.md`](../output/w5000_v1_boss_devourer_balance_30_final/boss_devourer_balance_report.md)。error/nonfinite 0、全86テストOK。formal値・通常profile未変更。

## 2026-09-26: Boss Devourer base-heavy experiment

- 外部Wave補償は使わず、カード所持中の固定基礎寄与へ成長の一部を移す診断profileを追加。B=75%成長+6 Power、C=50%成長+12 Power。通常既定は100%+0 Power。
- 30 pairedのHighest Wave meanは現行3068.8、B 2826.9、C 2591.3。Card-only分散はBが47.5%減、Cが34.1%減。Bは平均進行を約92%維持して分散を約半減し、比較内では最も目的に近い。
- W2500到達は50.0%/33.3%/23.3%、W5000成功は33.3%/26.7%/16.7%。平均維持だけでなく到達率低下もあるため正式採用は未判断。
- W1500後の再到達率は9.0%/11.0%/19.2%。Cは再現性が上がる一方、早期固定Powerによる閾値差でCard-only分散がBより再拡大。固定量を増やせば単調に分散が下がるわけではない。
- 結果: [`../output/w5000_v1_boss_devourer_base_heavy_30_final/boss_devourer_base_heavy_report.md`](../output/w5000_v1_boss_devourer_base_heavy_30_final/boss_devourer_base_heavy_report.md)。formal値未変更、error/nonfinite 0、全87テストOK。

## 2026-09-26: 現行候補上のExponential Core比較

- DP v0.1 + Boss Devourer base-heavy B + W2500確定Legendary OFFを共通条件に、既存Core 4 profileを30 paired比較。W2500到達は全profile同一の10/30で、報酬前state/time/RNGも完全一致。
- no_coreはW2500到達者10件中8件が最終的にW5000へ到達するが、W2500後Runs P50=13、同一RunはP50 W2582で停止。weak/baseline/strongは10/10が取得RunのままW5000へ直行。
- weakでもExponentはW2500 1.85→W5000 19.60、W5000 Margin P50 +376 Power。baseline/strongはさらに余剰が増え、3候補の到達率・Run数・死亡数は同一。既存weak以上は比較帯として強すぎる。
- W2500 sampleは10のみ。方向性診断には十分だが精密な率比較には不足し、100+へは拡張していない。Core係数は変更・採用していない。
- 結果: [`../output/w5000_v1_core_profiles_current_30_final/w5000_v1_core_profiles_current_30.md`](../output/w5000_v1_core_profiles_current_30_final/w5000_v1_core_profiles_current_30.md)。error/nonfinite/overflow 0、全87テストOK。

## 最新更新（2026-09-27: W2500後 Core / late-DP統合比較）

- 保存済みW2500到達10状態を使い、Infinite Barrage 37.5%、Boss Devourer base-heavy B、確定Legendary OFFの固定条件でlate-DP 10%/25% × Core OFF/medium20%をpaired replay。
- W5000成功率は10%/OFF=50%、10%/Core=90%、25%/OFF=60%、25%/Core=90%。Coreありの初回Run直行は両DP条件で10%だけだが、後続Run込みではW2750到達者がそのままW5000へ到達し、中間checkpointで追加脱落しなかった。
- Core ON時のW5000成功Margin P50はlate-DP10で+107.12、25で+134.99。直接Core寄与は約+99 Power。Barrage非取得群もCore ONなら2/3成功し必須性は低下したが、取得群7/7成功との相互作用は強い。
- late-DP10は25よりCoreの役割余地を残すが、medium20% Coreはlong-runでまだ強く、複数壁を残す目的には未達。正式採用なし。結果: [`../output/w5000_v1_integrated_core_dp_10_states_final/integrated_core_dp_report.md`](../output/w5000_v1_integrated_core_dp_10_states_final/integrated_core_dp_report.md)。全96テストOK、error/nonfinite/overflow 0。

## 最新更新（2026-09-27: Core re-bracket）

- late-DP10%固定でCore OFF/10/15/20%を保存済み10状態から比較。long-run W5000率は50/70/70/90%、first-run直行率は0/0/10/10%。
- 10%は後半checkpointで90→90→80→80→70→70%と段階的脱落を最も残すが、Barrage非取得群は0/2成功。15%は90→80→70→70→70→70%、Barrage取得6/7・非取得1/3成功で、今回の4条件中は「Barrage必須でも確定勝利でもない」に最も近い。
- 20%は全後半checkpoint 90%、Barrage取得7/7成功で過剰寄り。15%もW3500以降の追加脱落がなく、複数壁という目標を完全には満たさない。正式採用なし。結果: [`../output/w5000_v1_core_rebracket_10_states_final/core_rebracket_report.md`](../output/w5000_v1_core_rebracket_10_states_final/core_rebracket_report.md)。

## 最新更新（2026-09-27: Core shape比較）

- flat10/flat15/tapered15→12.5→10%を同じ10状態で比較。taperedのlong-run到達率はW3000 80%、W3500以降W5000まで70%で、flat15と完全に同じ。成功trial IDも同じ7件。
- taperedは追加Run P50 14（flat15は11）、W2500後時間P50 0.726h（0.591h）へ遅延しただけで、新しい後半脱落を作らなかった。Barrage非取得成功も確認できず、目的に対する改善なし。
- 正式採用なし。結果: [`../output/w5000_v1_core_shape_10_states_final/core_shape_report.md`](../output/w5000_v1_core_shape_10_states_final/core_shape_report.md)。

## 最新更新（2026-09-27: Unlimited Boost v0.1）

- 後半実験baselineはBoss Devourer base-heavy B / Infinite Barrage37.5% / late-DP10% / Core flat15% / W2500確定Legendary OFFとして固定（formal未採用）。Core shape探索は終了。
- Unlimited Boostを診断configとして追加し、通常既定OFFを維持。W4000解禁、death後Lv保持、6 node、個別指数cost、Lv5後softcapを実装。Finaleは未実装。
- 10 pairedではOFF/ONともW4000到達7、W5000到達7。全成功RunがW4000から同一RunでW5000へ到達したため、material sinkによる突破差は測れなかった。
- ONは最終各node Lv3 P50、Weapon Pt 1344/Relic Dust 701消費、W5000 Boost寄与+38.33 Power、成功Margin+66.73。到達率不変で余剰だけ増えるためv0.1数値は未採用。結果: [`../output/w5000_v1_unlimited_boost_10_states_final/unlimited_boost_report.md`](../output/w5000_v1_unlimited_boost_10_states_final/unlimited_boost_report.md)。全100テストOK。

## 最新更新（2026-09-27: Finale v0.1）

- Finaleを独立configとして追加。W4500～5000へ0→50 Enemy Powerを100Waveごと+10、区間線形補間。通常Enemy curveと既定profileは不変。
- OFF/OFF、ON/OFF、ON/ONの10 pairedではW4000/W5000到達はいずれも7/10。ON/OFFはW4500+に6死亡地点を作りW4000→5000追加Run P50=15。ON/ONはP50=0へ圧縮したが、3/7成功は5～16追加Runを必要とし完全自動突破ではない。
- Boost ONは壁を強く圧縮し、Barrage非取得群はFinale ONの両条件で0/2成功。正式採用なし。結果: [`../output/w5000_v1_finale_10_states_final/finale_report.md`](../output/w5000_v1_finale_10_states_final/finale_report.md)。全103テストOK。

## 最新更新（2026-09-27: Boost node別effect suppression）

- 診断専用`UnlimitedBoostConfig.suppressed_nodes`を追加。購入・素材・Lv・順序を変えず、指定nodeの戦闘効果のみ0にする。通常既定は空で既存profile不変。
- 10 pairedでAttack Speed OFFだけW5000到達が7/10→6/10、W4000→5000追加Run P50が0→2.5。同一state直接差W5000 P50 +61.12 Power中+60.82がInfinite Barrage相互作用。Base/Weapon/Crit/All/Boss各OFFは到達率を変えなかった。
- 結果は[`../output/w5000_v1_boost_node_suppression_10_states_final/boost_node_suppression_report.md`](../output/w5000_v1_boost_node_suppression_10_states_final/boost_node_suppression_report.md)。正式値変更なし、error/nonfinite/overflow 0、全104テストOK。

## 最新更新（2026-09-27: Unlimited Boost v0.2 candidate）

- experimental v0.2はASをFinale Masteryへ置換。W4500未満またはFinale OFFではMastery効果0。購入コスト位置は旧ASと同じで、v0.1は不変。
- 10 pairedのW5000 Boost寄与P50はv0.1 +58.24、v0.2 +22.46 Power。v0.2最大node shareは19.2%、W5000成功率は両者7/10。AS×Barrageの単独支配を除き、20～30 Powerの初期探索帯へ入った。
- Barrage取得/非取得成功はv0.2でも7/8・0/2。方向性確認のみで正式採用なし。結果: [`../output/w5000_v1_unlimited_boost_v02_10_states_final/unlimited_boost_v02_report.md`](../output/w5000_v1_unlimited_boost_v02_10_states_final/unlimited_boost_v02_report.md)。全106テストOK。

## 最新更新（2026-09-27: Infinite Barrage依存診断）

- Boost v0.2を実験baselineとして固定し、Barrage現行/OFF/半減/20 Power soft capを10 paired比較。W5000成功は7/10、0/10、3/10、0/10。取得群では7/8、0/8、3/8、0/8。
- 現行BarrageのW5000寄与P50は+222.44 Powerで、AS帯上昇に応じ+152～744 Powerへ伸びる。20 Power capは全取得trial失敗。現状は実質必須条件に近い。
- 正式値変更なし。結果: [`../output/w5000_v1_barrage_dependency_10_states_final/barrage_dependency_report.md`](../output/w5000_v1_barrage_dependency_10_states_final/barrage_dependency_report.md)。全107テストOK。

## 最新更新（2026-09-27: 旧Barrage / v2 前半診断）

- 30 trialのW1～2500を共通実行し、W2500到達10状態だけを旧37.5% / v2へpaired分岐。W500～2500のBarrage以外の記録は完全一致。
- Infinite BarrageはW2500解禁のため、W500～2250の直接寄与・旧/v2差は全て0 Power。旧BarrageはW1000～1750の進行を支えていなかった。
- W2500到達は両者10/30。W4000到達は旧7/30、v2 1/30で、差はW2500後にのみ発生。結果: [`../output/w5000_v1_old_vs_v2_midgame_30_final/old_vs_v2_midgame_report.md`](../output/w5000_v1_old_vs_v2_midgame_30_final/old_vs_v2_midgame_report.md)。全110テストOK。

## 最新更新（2026-09-27: W1500～2000カード分岐）

- 同じ30 trialでW2500成功10/未到達20を比較。成功IDは直前ログと一致。
- Rare+ droughtやW1000時点のRare枚数は失敗原因を説明しない。明瞭な差はW1500の突破Runで、成功側はEscalation/Steady ForceとMarginが高い。Boss Devourer stackは同じ。
- W1250では失敗側のDP/AS/Weapon/Marginがむしろ高く、恒久値不足が最初の分岐ではない。rarity/reroll固定replayも将来到達をほぼ変えず、W1500時点までに形成されたcard key構成の影響が大きい。
- 結果: [`../output/w5000_v1_midgame_card_divergence_30_final/midgame_card_divergence.md`](../output/w5000_v1_midgame_card_divergence_30_final/midgame_card_divergence.md)。balance変更なし、全110テストOK。

## 最新更新（2026-09-27: 中盤card-effect因果診断）

- 同一取得履歴のcheckpoint stateへeffectだけを抑止した結果、Escalation OFFで成功群W1500 -9.54 Power、W2500到達100%→10%。W1250→1500の成功/失敗成長差も0.87→0.31へ縮み、逆転の主要因と確認。
- Steady Force/Rapid Fire/Power Up/Critical MomentumはW1500で-0.005/-0.31/-0.40/-0.14 Power。単独抑止でW1500率は変わらない。
- W500 EpicではPerfect Learningが成功側に偏るが履歴固定の即時差0。Double ScalingはW1500 -2.58、W2500 100%→60%で絶対進行に寄与。
- 結果: [`../output/w5000_v1_midgame_card_effects_30_final/midgame_card_effects.md`](../output/w5000_v1_midgame_card_effects_30_final/midgame_card_effects.md)。正式変更なし、全112テストOK。

## 最新更新（2026-09-27: Escalation単体balance experiment）

- 同一30 trialの取得履歴・stack・RNGを固定し、Wave依存成長だけ100% / 65% / 50%でmatched比較。W2500到達率33% / 13% / 10%、Highest P50 2052 / 1942 / 1796。
- 65%はW1500到達97%を維持しつつ、Escalation 3枚以上群のW2500率を64%→27%へ縮小。50%はW2500差が小さい一方、W1500到達90%まで低下した。正式値は未決定。
- 結果: [`../output/w5000_v1_escalation_strength_30_final/escalation_strength.md`](../output/w5000_v1_escalation_strength_30_final/escalation_strength.md)。通常既定100%は不変、error/nonfinite 0、全113テストOK。

## 要確認（原文・実装はこの引き継ぎでは変更しない）

1. **解消済み（履歴）:** [`card_value_take_experiment_design.md`](../card_value_take_experiment_design.md) の擬似コードと§2は合法候補限定で統一。旧10組レポートとJSONLは全提示カード判定の結果として残し、再解釈や上書きをしない。
2. [`card_value_evaluation_spec.md`](../card_value_evaluation_spec.md) 冒頭や [`card_value_encounter_conditional_design.md`](../card_value_encounter_conditional_design.md) は「本体の選択は旧scoreのみ」「Takeは旧score」と記す。現在は既定legacyだが、任意の`pe` Takeモードが実装済み。これらは当時の設計段階の記述で、オンラインの全行動共通PE化が済んだ意味ではない。
3. [`predict_run_end_spec.md`](../predict_run_end_spec.md) および [`card_value_v01_implementation_plan.md`](../card_value_v01_implementation_plan.md) の「実装前」「未決」はフル構想や当時の計画を指す。実際には部分的な予測器が実装済みで、将来取得率やterminal換算は未校正。計画と実装の境界を確認すること。
4. [`output/card_value_v01_validity_diagnostic.md`](../output/card_value_v01_validity_diagnostic.md) はEncounter-based Conditional導入の**前**の人工状態診断（余裕/壁の値が同じとの旧結果）。現行のExecution/Time CollapseのPE値として引用しない。同様に [`output/card_value_v01_shadow_smoke.md`](../output/card_value_v01_shadow_smoke.md) は過去のshadow結果で現行のPE Takeパイロット値ではない。
# 2026-10-04: 新W5000手動プレイ候補（旧仮カード/DPから切替）

- Figma Mainは新C/U/R/E/L・BC DP v0.1・個体Drop武器へ切替。旧カード初期選択禁止/DP巨大totalLv倍率/Weapon Powerは不使用。Relic Apotheosis以外47枚を候補化。
- 旧formal W10000・D/E・w5000_v1 scaffold既定・CardValueは保存。後半診断の旧カードbaselineとは別系列。
- 死亡のTypeError/多重DP修正、API失敗時停止。149 tests/TypeScript成功。balance未調整。
- 全遺物/武器固有/Core/UB/Finale/手動Refine/保存/保管拡張は未接続。詳細: `NEW_W5000_PLAY_CANDIDATE.md`。
