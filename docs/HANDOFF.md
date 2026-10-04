# HANDOFF — 次回セッションの開始点（2026-09-27）

## 最新（2026-10-04: 試遊テンポ・操作改善）

- 新W5000手動EquipmentSessionのみnon-blocking化。旧formal/D/E/CardValue/旧PlaySession、XP量・カード数値は今回変更なし。
- カード選択権はRun内で蓄積、開く時に手札抽選、閉じても保持、死亡時破棄。途中の取得/装備/分解は経過時間・残HP・攻撃位相を保持したsegment計算で適用。既存期待値モデルを借用。
- 武器取得時は新規＋装備＋保管を一覧比較して装備/保管/分解。鞄の装備/保管/炉へdrag/drop、炉は即分解・確認なし。カードはrarity色＋名称とクリック説明。死亡後は手動再挑戦、開いた画面にも死亡表示。
- API操作直列化、fight IDでstale resolve無視、操作例外でsession復元。未処理武器も死亡50%回収、未処理遺物は保持。
- 158 scripts tests / TypeScript / vinext production build成功。追加non-blocking 9件。ブラウザseed20260828の短い手動Runで選択中進行/一覧装備/drag保管/炉即分解/カード説明を確認。balance Monte Carloなし。
- 検証画像: output/play_ux_nonblocking_20261004.png。localhost:4173(API8765)起動。保存はまだ未実装。
- GitHub保存対象はゲームsource/依存scripts/docs。playtest内のnested Git metadataは削除せず、親repoには通常ファイルとして収録。生成物・生ログ・無関係な文書生成scriptは除外。
- 次: 実プレイ確認後にスマホ専用UI。カード必要XP/カード強化は別実験で未採用。Core/UB/Finale等未接続も維持。
- 再現: rootで`python -m unittest discover -s scripts -p 'test_*.py' -q`、playtestで`npx tsc --noEmit`/`npm run build`/`npm run dev -- --port 4173`。

## 現在の開始点（2026-10-04: 新W5000手動候補・死亡修正済み）

- 現行Figma Mainは新カード47枚（Apotheosis保留）/ BC DP v0.1 / 個体Drop装備。旧formal/D/E・w5000_v1 scaffold・CardValueは別途保存。
- 以下のLuna重大不具合は修正済み。149 tests/TypeScript成功。接続済み・未接続の正確な境界と再現方法は`NEW_W5000_PLAY_CANDIDATE.md`および末尾の今回更新を参照。
- 新UIで新カード・DP9項目・装備報酬を確認。画像:`output/new_w5000_play_candidate_20261004.png`。計算サーバー再起動済み、http://localhost:4173/。

## 最新確認（2026-10-04: Luna動作チェック／死亡処理に重大不具合）

- ユーザー指定でgpt-6-luna・lowを起動し、コード編集なしで装備基盤/PlaySessionを再確認。全scriptsテスト131件成功、親でTypeScript成功。ただし実際の死亡処理は現テストで未カバー。
- メモリ上のEquipmentSessionでW13失敗を再現すると、`sim_server.py`死亡分岐のRunResultに必須`reach_elapsed`/`end_state`/`w2500_state`がなくTypeError。DP/戦闘時間を先に加算するため、例外後もcombatのまま。2回resolveでDP776→778→780、時間3974.8→3984.8→3994.8。武器死亡回収へも進まない。
- 親のread-only画面確認でもW13/Failed to fetch/HP0%を観測。page.tsxは失敗後もresolving/busyを解除し、終端elapsedの戦闘を再resolveするため部分更新が反復する。HP表示は残HPでなく経過時間比率で、敗北時も0%になる別の表示問題。
- 未修正。コード/spec/balance変更なし、ライブSESSIONの初期化・停止なし。この状態を正常な死亡/再挑戦プレイ可能と扱わない。
- 次の最優先: RunResult呼び出し整合、死亡処理の例外時原子性/二重resolve防止、フロントの通信失敗時自動反復停止。実際の死亡→DP1回支給→武器50%回収→遺物保持→retryの統合テストを追加してから再検証する。
- 再現は既存131テストとは別に、インメモリEquipmentSessionのrun.kills=12、fight.timeToKill=None、wave=13でaction(type=resolve)を2回実行。ライブAPIには送信しないこと。

## 最新更新（2026-10-04: Figma Main / 個体装備UI接続候補）

- `first-prestige-playtest/components/game-ui/figma-main.tsx` と `app/figma-main.css` を追加。MainBattle_v0.1（Figma 18:2）を既存React UIへ移植。Figma本体は変更していない。元の02/03表示は残す。
- Mainの鞄ボタンは左下、Backpack内の閉じるは左上。遺物3装備枠、Mainカード横スクロール、Backpackの3×2、個体詳細・装備/保管・強化・分解プレビュー/確定・同名吸収/交換を接続。
- `/api/start` の `equipmentMode:true` のみ独立 `EquipmentSession`。通常PlaySessionはW500を維持。scaffold W5000敵曲線を使用し、Core/Final Equation/Defense/Reward Skipなし。新W5000 balance完成版ではない。
- 初回W10 Common剣（Base1×1.10）とW100 Common学習レンズを個体として受け取り。保管満杯時は取得候補を保持。装備武器とXPレンズを計算に接続し、旧Weapon/Relic共通Powerを無効化。レンズは借用中の旧XP→Damage式にも反映。
- 重要な未接続: 新Common～Legendary・DP v0.1、正式Weapon曲線/rarity/affix/固有効果、遺物全種類とW500以降報酬、保管拡張・ディスク保存・UB。武器曲線は旧値の仮接続、Bossのみ仮取得モデル。生成は延期表示。これらを新仕様実装済みと扱わない。
- 既存playtestで `draw_hand` のconfig引数欠落をブラウザ検証中に発見。API呼び出しを現署名へ合わせ、preview/取得/scoreへconfigを渡す。formal本体/specは未変更。
- 全scriptsテスト131件成功、TypeScript `tsc --noEmit`成功。ブラウザでW10取得→保管→詳細→装備、Main反映と鞄開閉を確認。全表示画像ロード成功。バランスMonte Carloは未実行。
- 検証画像: `output/equipment_backpack_ui_v01.jpg`。開発サーバー `http://localhost:4173/`（API8765）。状態はメモリのみ、プロセス再起動/初期化で消える。
- 再現: playtestディレクトリで `npm run dev -- --port 4173`。テスト: `python -m unittest discover -s scripts -p 'test_*.py' -q`。次は仮接続と確定新仕様の計算境界を整理してからカード/DP/各遺物の接続へ進む。UIの見た目だけでbalance統合済みと判定しない。

## 最新更新（2026-10-03: 新W5000個体装備基盤）

- 会話の決定・仮値・延期項目を `W5000_EQUIPMENT_V01.md` へ整理。formal specや既存profileの値は変更なし。
- `scripts/w5000_equipment_v01.py` を独立追加。個体ID、装備武器1/遺物3、保管各5、満杯拒否、交換、強化4/9/16、分解返還、同名吸収、死亡/Prestige処理、JSON互換状態往復を実装。
- 個体の戦闘値適用・報酬抽選・UI・ディスク保存・保管拡張購入は未接続。装備基盤完成をゲーム完成と解釈しない。武器種固有効果・遺物16種確定も未実装。
- 単体10件成功、全scriptsテスト123件成功。Monte Carlo未実行。既存出力・formal/D/E・playtestコードは未変更。
- 次: 独立したnew W5000状態への接続と遺物報酬。未取得候補はUI側で保持し、満杯拒否で失わせないこと。旧Relic共通Powerとの二重適用禁止。
- 再現: `python -m unittest discover -s scripts -p 'test_w5000_equipment_v01.py' -v` / `python -m unittest discover -s scripts -p 'test_*.py' -q`。

## 最新更新（2026-09-27: v2 Barrage後半baseline診断）

- Infinite Barrage v2 fixed-ratioを診断baseline（未採用）として固定し、Core flat15% / late-DP10% / Boss Devourer base-heavy B / W2500確定Legendary OFFの保存済みW2500 10状態でFinale OFF/ON × Boost OFF/v0.2をpaired比較。
- W4000到達は全条件1/10。Finale OFFはBoost OFF/v0.2ともその1件が同一RunでW5000到達（全体10%）。Marginは+13.47/+26.21で、Boost直接寄与+12.74 Powerは到達率を増やさず余裕だけを増加。
- Finale ONはBoost OFFでW4585、Boost v0.2でW4697が最高。W5000はともに0/10。BoostはFinale壁を約112 Wave延長したが突破不能。W4500 Marginは+7.69/+20.81、W4600はBoost ONだけ到達して+12.61。
- 成功したFinale OFFの1件はInfinite Barrage非取得。v2取得群は全条件0成功で、今回の後半到達をBarrageが支配していない。W4000 sampleが1件だけなので率の一般化は禁止。
- profile差でW4000後のRun履歴が分岐し、2 trialの最初のBarrage取得signatureは不一致。W2500開始state/RNGはpairedだが、分岐後一致は要求しない。error/nonfinite/overflow 0、全110テストOK。
- 結果: [`../output/w5000_v1_v2_late_baseline_10_states_final/v2_late_baseline_report.md`](../output/w5000_v1_v2_late_baseline_10_states_final/v2_late_baseline_report.md)。数値変更・正式採用なし。

## 最新更新（2026-09-27: Infinite Barrage v2構造診断）

- formal/defaultのlegacy式を維持したまま、診断専用`v2_fixed_ratio`を追加。20通常攻撃ごとに通常攻撃5発分を発生させるため、Barrage/normal DPSはAS 100/1000/5000/20000の全てで25%、追加Powerは+0.096910で一定。
- v2は通常攻撃成分を基準に加算し、Follow-Up部分を複製しない。追加Barrage、Follow-Up、Re-Action、Supplemental、Hit Countは発生させず、Crit/Multi-Crit/Coreは元通常攻撃damageを通じて反映される集約モデル。
- A=current 37.5%、B=v2固定比率、C=v2+既存kill-growthの0.25 Power漸近softcapを、Finale ON / Unlimited Boost v0.2 / Core flat15% / late-DP10%の保存済みW2500 10状態でpaired replay。W5000率は70%/0%/0%、W4500率は70%/10%/10%。
- Barrage所持Run終端の寄与はAがAS帯により+73.77～+743.58 Power、Bは全AS帯+0.0969、Cは全AS帯約+0.1597。高ASからの無制限Power生成は解消したが、現baselineではv2単独の進行力は不足。正式採用・数値調整なし。
- 結果: [`../output/w5000_v1_infinite_barrage_v2_10_states_final/infinite_barrage_v2_report.md`](../output/w5000_v1_infinite_barrage_v2_10_states_final/infinite_barrage_v2_report.md)。error/nonfinite/overflow 0、全110テストOK。

## 最新更新（2026-09-27: Infinite Barrage 37.5%下のlate DP再評価）

- Infinite Barrage 37.5%を後半診断candidateとして固定（未採用）、Core OFFのまま、W2500後に新規取得したDP Lvのcombat contributionだけを10/25/50%で比較。W2500以前のDP効果・保存state・他システムは同一。
- W5000到達率は50/60/80%。Best Wave P50は4559/5000/5000。Infinite Barrage取得trialでは5/7、6/7、8/8がW5000へ到達し、50%は再び「取得＝突破」になった。
- W5000 checkpointのlate-DP Power P50は+27.87/+54.14/+121.91。成功時Margin P50は+139.18/+80.21/+157.03だが成功者集合が異なるため強度比較には直接DP寄与を優先する。
- Coreを後半主成長にする目的ではlate_dp_50は過剰。候補帯は10～25%で、10%がCore余地最大、25%が上限寄り。結果が近く小標本なので追加候補は作らず、正式採用もしない。
- 結果: [`../output/w5000_v1_late_dp_barrage375_10_states_final/late_dp_barrage375_report.md`](../output/w5000_v1_late_dp_barrage375_10_states_final/late_dp_barrage375_report.md)。error/nonfinite/overflow 0、全96テストOK。

## 最新更新（2026-09-27: Infinite Barrage 37.5% bracket）

- 前回と同一のW2500保存10状態・RNG・late_dp_10/Core OFF/Boss Devourer base-heavy B/W2500確定Legendary OFFで、Infinite Barrage 37.5%だけを追加paired replay。31.25%/43.75%は実行していない。
- 到達率はW3000 70%、W3500 70%、W4000 60%、W4500 50%、W5000 50%。Best Wave P25/P50/P75=3068/4559/5000、variance=999,493。
- Infinite Barrage取得trialは7/10で、そのうちW5000成功5/7=71%。取得＝突破保証ではない。最初の取得時ΔPower P25/P50/P75=+61.53/+103.46/+148.87、取得後追加Wave=3478/4290/4904。
- terminal margin P25/P50/P75=-1.34/+4.17/+136.00。W5000成功時Margin P50=+139.18。後半checkpointに段階的脱落を残しつつ強いLegendaryとして機能したため、37.5%は狙いの位置に入った。ただし正式採用ではない。
- 初回取得Run/Wave signature一致、error/nonfinite/overflow 0。結果: [`../output/w5000_v1_infinite_barrage_strength_37_5_10_states_final/infinite_barrage_strength_report.md`](../output/w5000_v1_infinite_barrage_strength_37_5_10_states_final/infinite_barrage_strength_report.md)。全96テストOK。

## 最新更新（2026-09-27: Infinite Barrage strength experiment）

- late_dp_10（診断baseline・未採用）/ Core OFF / DP v0.1 / Boss Devourer base-heavy B / W2500確定Legendary OFFの既存W2500到達10状態から、Infinite Barrage効果強度0/25/50/75/100%をpaired replay。rarity・取得確率・pool・選択処理は変更していない。
- strengthは直接効果（AS余剰段数×log10(1.25)）と同カード由来Legendary growth logの両方へ線形適用。各trialの最初の取得Run/Waveは全5条件で完全一致し、即時ΔPower P50も0/+68.98/+137.95/+206.93/+275.90と線形。
- 全trial W5000到達率は0/30/60/70/70%。Infinite Barrage取得trial（7件）に限ると0/43/86/100/100%。75%以上は依然「取得＝W5000」を再現し、50%は非常に強いが1/7脱落、25%は3/7成功。
- 25%はW3000/3500/4000/4500/5000到達率60/60/60/40/30%で後半に段階的脱落。次回の詳細候補帯は25～50%だが、正式値は未採用。DP/Core/他カードは未調整。
- 結果: [`../output/w5000_v1_infinite_barrage_strength_10_states_final/infinite_barrage_strength_report.md`](../output/w5000_v1_infinite_barrage_strength_10_states_final/infinite_barrage_strength_report.md)。runner: [`../scripts/experiment_w5000_v1_infinite_barrage_strength.py`](../scripts/experiment_w5000_v1_infinite_barrage_strength.py)。error/nonfinite/overflow 0、全96テストOK。

## 最新更新（2026-09-26: W2500後Card effect suppression）

- late-DP係数探索を停止し、`late_dp_10`を診断baseline（未採用）、Core OFFとして既存W2500到達10状態を後続Run込みでpaired replay。カードは通常どおり取得・記録し、draw pool/RNG列から削除せず、診断対象のcombat/growth効果だけを抑止した。
- baseline W5000到達7/10。Legendary全効果抑止は0/10、Epic全抑止6/10、Rare全抑止7/10、Epic+Legendary全抑止0/10。Best Wave P50は5000/2591/5000/5000/2511。
- baselineの成功Run 7件は全件`Infinite Barrage`所持、非成功Runは0件。`Infinite Barrage`単独抑止もW5000 7/10→0/10、paired ΔBest Wave P50 -2195、Δterminal Power P50 -406.23。他の自然取得済みLegendary単独抑止では成功率変化なし。この10状態では「当たりRun→W5000」の因果分岐は`Infinite Barrage`。
- `Critical Overload` / `Endless Action` / `Fractal Barrage` / `Supplemental Singularity`は別のLegendary v0.1 probeにのみ存在し、現行`w5000_v1` active poolには不在。混入させず未評価とした。
- 効果抑止は診断専用`SimConfig.diagnostic_suppressed_card_keys`。所持・unique・取得履歴・選択候補は維持。Legendary成長logをkey別に記録し、個別抑止できる。既定空集合のためformal/D/E/w5000通常経路は不変。結果: [`../output/w5000_v1_card_effect_suppression_10_states_final/card_effect_suppression_report.md`](../output/w5000_v1_card_effect_suppression_10_states_final/card_effect_suppression_report.md)。error/nonfinite/overflow 0、全95テストOK。

## 最新更新（2026-09-26: W2500後DP combat contribution scaling）

- 既存W2500到達10状態を使い、W2500時点のDP Lv効果を完全維持したまま、その後購入したLvのcombat contributionだけを100%/50%/25%/10%へ縮小。DP獲得量・コスト・購入順、Core以外の全システムは共通。CoreはOFF。
- W5000到達率は80%/80%/70%/70%。成功時Margin P50は+944.92/+685.92/+418.13/+273.35。追加Run P50は12.5/12.5/21/14。
- 最終late DP Lv P50は21.5/20.5/26.5/25.5で、購入量は縮小していない。W5000到達者における直接late-DP寄与P50は+265.18/+102.67/+141.47/+22.92 Power。25%が50%より大きいのは成功者集合・到達経路・獲得Lv数が異なるsurvivorship/interactionで、尺度の逆転ではない。
- 50%は到達率を維持しながら余裕を約259 Power圧縮。10%は余裕を約672 Power圧縮してCore余地が最大だが、Best Wave分散は686k→1,077kへ増え、Best−直近10Run中央値も約3,556 Wave。late DP縮小だけではCard RNG由来のRun再現性を改善しない。
- 正式値・Core・カードは未変更。medium 20% Coreは暫定候補のままOFF。結果: [`../output/w5000_v1_late_dp_scaling_10_states_final/late_dp_scaling_report.md`](../output/w5000_v1_late_dp_scaling_10_states_final/late_dp_scaling_report.md)。error/nonfinite/overflow 0、全92テストOK。

## 最新更新（2026-09-26: W2500後Power爆発の成長源分離）

- Core係数探索を停止し、weak increment 20%版を「暫定Core候補・未採用」として記録。scaffold既定やformal値は変更していない。
- 既存W2500到達10状態 / no_core / DP v0.1 / Boss Devourer base-heavy B / W2500確定Legendary OFFから、後続Runを含む7条件をpaired replay。各trialは元の140 Run上限の残数だけ使用。
- 現状はW5000 8/10、追加Run P50 12.5、成功時Margin P50 +944.92。DP停止は6/10、16 Run、+283.56。武器恒久進行停止は8/10、12.5 Run、+912.45。遺物進行停止は8/10、9 Run、+786.14。全恒久進行停止は7/10、12 Run、+208.10。
- 成功時Marginの低下幅はDP停止約-661 Power、遺物停止約-159、武器停止約-32、全恒久停止約-737。ただし成功者集合が異なるため単純加算しない。余裕Powerの主因はDP、次点が遺物、武器恒久進行は小さい。
- Card RNGを各後続RunでW2500保存状態へ固定するとW5000到達は1/10へ低下。DPも同時停止しても1/10。再抽選は爆発そのものの大きさより「強いRunを引く機会」を作っている。成功した1件のMarginは依然+1178/+1200 Powerで、固定Card列でも当たり列は過剰。
- 全条件の各Run最高Wave、開始/終了Power、死亡時恒久Power差、DP内訳、Weapon/Relic/Card/rarity/Boss DevourerはJSONへ保存。error/nonfinite/overflow 0、全90テストOK。結果: [`../output/w5000_v1_post2500_growth_10_states_final/post2500_growth_report.md`](../output/w5000_v1_post2500_growth_10_states_final/post2500_growth_report.md)。

## 最新更新（2026-09-26: Core first-run-only分離）

- 既存の同一W2500到達10状態を使い、no_core / weak increment 5% / 10% / 20% / existing weakを、W2500後の最初のRunだけpaired replay。死亡時点で終了し、後続Run、死亡DP、再抽選、再挑戦を完全に除外した。
- first-run max Wave P25/P50/P75はno_core 2522.5/2582/2721、micro 2533.5/2602.5/2759.8、low 2545.8/2623/2828、medium 2567.3/2690/3052.8、existing weak 5000/5000/5000。
- W5000直行率は0%/0%/0%/10%/100%。mediumはW2750 50%、W3000 30%、W3250～3750 20%、W4000～5000 10%と段階的に脱落。existing weakは全checkpoint 100%で明確に過剰。
- 同一checkpoint stateからCoreだけを除去した直接寄与は、mediumでW2750 +8.57、W3000 +19.61、W3500 +38.26、W4000 +57.23、W5000 +99.56 Power。existing weakはW2750 +45.75、W3000 +96.14、W5000 +495.23 Power。
- low以下は中央値をno_core比+20.5～41 Wave、mediumは+108 Wave延長するが、10状態では大半がW3000前に停止。正式採用・新係数追加なし。
- 結果: [`../output/w5000_v1_core_first_run_10_states_final/core_first_run_report.md`](../output/w5000_v1_core_first_run_10_states_final/core_first_run_report.md)。Core以外のconfig/state/RNG共通、error/nonfinite/overflow 0、全88テストOK。

## 最新更新（2026-09-26: weak increment 0/5/10/20% Core replay）

- DP v0.1、Boss Devourer base-heavy B（growth75%+固定6 Power）、W2500確定Legendary OFFを共通にし、既存weakの段階別incrementだけを0%/5%/10%/20%へ縮小。weakの段階構造と100WaveごとのBig Boss timingは維持し、正式Core値は変更していない。
- 前回と同じseed 20260828のW2500到達10状態を再現し、trial ID、開始state、Card/Weapon/Relic/Combat RNGを共通化。元trialの140 Run上限からW2500到達時点までに消費したRunを差し引いてpaired replayした。
- 条件付きW5000到達率はno_core 80%、micro 70%、low 70%、medium 80%。取得RunのままW5000へ直行した率は0%/0%/0%/10%。同一Run到達Wave P50は2582/2602.5/2623/2690。
- 成功例の追加Run P50は12.5/14/14/9、W2500後時間P50は0.776h/0.758h/0.769h/0.518h。W5000 Margin P50は+944.9/+1347.2/+1374.3/+638.2 Powerと全条件で過剰に大きい。
- 最初の停止は主にW2500～2999へ集中し、W3000/W3500/W4000/W4500で段階的に脱落する望ましい形は得られなかった。no_core自体が8/10成功するため、今回の0～20%帯からCore係数の境界は判定不能。10状態で差が明瞭でないため、指示どおりtrial追加・新候補追加はしていない。
- 結果: [`../output/w5000_v1_micro_core_10_states_final/micro_core_report.md`](../output/w5000_v1_micro_core_10_states_final/micro_core_report.md)。error/nonfinite/overflow 0、Core以外のconfig差なし、全88テストOK。

## 最新更新（2026-09-26: 現行候補上のExponential Core 30-pair）

- 共通条件をDP v0.1、Boss Devourer base-heavy B（growth75%+固定6 Power）、W2500確定Legendary OFFへ更新し、既存Core profile `no_core` / weak / baseline / strongを係数無変更で30 paired比較。Enemy/Weapon/Relic/他カードは同一。
- 各profileのW2500到達sampleは同じ10/30。全10件でW2500報酬前state・到達時刻・Card/Weapon/Relic/Combat RNG stateが一致し、Core以外のconfig差0。
- 条件付きW5000到達率はno_core 80%、weak/baseline/strong 100%。no_coreはW2500後Runs P50=13、同一Run到達P50=W2582。Core 3種は全10件が取得RunのままW5000へ到達し、Runs P50=1、死亡0。
- W2500取得直後のexponentはweak 1.85、baseline 1.90、strong 1.95。W5000は19.60/20.90/22.20。W5000 Margin P50は+376/+412/+447 Powerで、weakでも大幅な余剰。既存3候補は到達曲線上すべて強すぎ、係数差の識別不能。
- W2500到達sample 10のため精密率には不足。指示どおり100+ trialへ拡張していない。次の詳細調整帯は既存weakより下が妥当だが、新係数は未作成・未採用。
- 結果: [`../output/w5000_v1_core_profiles_current_30_final/w5000_v1_core_profiles_current_30.md`](../output/w5000_v1_core_profiles_current_30_final/w5000_v1_core_profiles_current_30.md)。error/nonfinite/overflow 0、全87テストOK。

## 最新更新（2026-09-26: Boss Devourer base-heavy experiment）

- 外部Wave milestone補償の探索を終了し、Boss Devourer内部の固定基礎寄与と可変成長の配分だけを比較。A現行、B=成長75%+所持中固定6 Power、C=成長50%+所持中固定12 Power。固定値は保存済みW1500寄与中央値26.60の減少分を切り下げた単純候補で、正式採用なし。
- w5000_v1 / DP v0.1 BC / Coreなし / W2500確定Legendary OFF / 30 paired。Highest Wave mean/P50はA 3068.8/2511.5、B 2826.9/2051.5、C 2591.3/2051.0。W2500到達率50.0%/33.3%/23.3%、W5000成功33.3%/26.7%/16.7%。
- 非Card RNG固定のCard-only Highest Wave分散はBが現行比47.5%減、Cが34.1%減。Bは平均進行を現行の約92%維持しつつ分散を約半減し、今回候補中では最も目的に近い。ただしP50とW2500到達は低下しており採用判断はしていない。
- W1500後の再到達率は9.0%/11.0%/19.2%、Best−直近10Run P50は1215.8/829.8/749.5。Cは再現性指標を改善するが、固定12 Powerの早期閾値効果でCard-only分散はBより大きい。
- 固定寄与はBoss Devourer所持時のみ有効。通常既定は0 Power、growth既定1.0。Enemy/Core/DP/Weapon/Relic/他カードは変更なし。結果: [`../output/w5000_v1_boss_devourer_base_heavy_30_final/boss_devourer_base_heavy_report.md`](../output/w5000_v1_boss_devourer_base_heavy_30_final/boss_devourer_base_heavy_report.md)。error/nonfinite 0、全87テストOK。

## 最新更新（2026-09-26: Boss Devourer balance experiment）

- w5000_v1 / DP v0.1 BC / Coreなし / W2500確定Legendary OFFで、Boss Devourer成長100%・75%・50%・50%+固定補償を同seed 30 paired比較。補償はW1250/1500/1750撃破後に各+4 Power（累積+4/+8/+12）の1案のみ。正式採用なし。
- Highest Wave meanは100% 3068.8、75% 1846.8、50% 1324.9、補償1793.5。W2500到達率は50.0% / 13.3% / 0% / 10.0%。Boss Devourer成長率低下だけでは平均進行が大きく落ち、補償案も現行平均を維持できなかった。
- Weapon/Relic/Combat RNGを固定しCard RNGだけ30通り変えたHighest Wave分散は、100%比で75%が66.9%減、50%が96.1%減、補償が35.0%減。補償はW1250等の到達可否を新たな閾値にするため、50%単独より分散が再拡大した。
- W1500到達後のRun単位再到達率は9.0% / 4.0% / 0% / 6.5%。補償は一部回復するが、平均進行維持と分散低減を同時達成していない。
- 診断用固定Power milestone fieldは既定空、Boss成長倍率は既定1.0。formal・通常profileは変更なし。結果: [`../output/w5000_v1_boss_devourer_balance_30_final/boss_devourer_balance_report.md`](../output/w5000_v1_boss_devourer_balance_30_final/boss_devourer_balance_report.md)。error/nonfinite 0、全86テストOK。

## 最新更新（2026-09-26: Boss Devourer進行依存性）

- 保存済みW1000/1250/1500の89 checkpointを使い、各stateにつき同一Card RNG 6 replayで`current` / `checkpoint後freeze` / `checkpoint後50%成長` / `全効果OFF`をmatched比較。計2,136 replay、error/nonfinite 0。
- checkpoint時点で既に蓄積したBoss Devourerの基礎寄与はPower P50でW1000 +12.635、W1250 +19.566、W1500 +26.597。freeze/50%条件ではこの寄与を維持し、以後のBoss撃破成長だけを介入した。
- currentの平均到達WaveはW1000/1250/1500起点で1296/1518/1910。freezeは1129/1359/1704、50%成長は1175/1405/1777。W1500起点のW2000到達率は38.5%→8.6%/18.4%。
- 同一checkpoint state内のCard RNG分散は、成長freezeでW1000 91.5%、W1250 94.3%、W1500 64.6%減少。50%成長でも73.8%/84.2%/60.2%減少。Boss Devourerのcheckpoint後成長がCard RNG差を強く増幅している。
- `added stacks`はuniqueカードの追加取得数なのでP50=0。実際の進行成長は`added growth units`で、current P50は36/37/81、50%条件は14/13.2/24、freezeは0。
- 診断用growth multiplierの既定は1.0、suppress既定はfalse。formal・通常profileの値は未変更。結果: [`../output/w5000_v1_boss_devourer_growth_30_final/boss_devourer_growth_report.md`](../output/w5000_v1_boss_devourer_growth_30_final/boss_devourer_growth_report.md)。全85テストOK。

## 最新更新（2026-09-26: Card RNG内部split診断）

- 既定shared Card RNGを維持し、diagnostic replayだけ`rarity` / `hand-card-key` / `reroll`へ分離。明示shared substreamと従来経路のTrialResult/RNG state一致をテスト。
- 既存W1000/1250/1500の89 checkpointを再利用し、7条件×6回=3,738 replay、Boss Devourer ON/OFF 534 matched pairs。error/nonfinite 0、全84テストOK。
- 同一状態内分散の固定介入: W1000はReroll固定-61.8%、Rarity固定-27.9%、Hand固定-18.0%。W1250はRarity固定-87.5%が突出。W1500はRarity固定-32.8%、Reroll固定-13.9%、Hand固定-5.2%。寄与は相互作用するため合計100%にはならない。
- 単独可変でもW1000はReroll、W1250/W1500はRarityが最大。Run段階によってCard RNGの主因が変化する。
- |ΔWave|≥100のpaired replayで最初に分岐したカードは`Escalation`が43件・|ΔWave|合計11,113で突出。次いで`Steady Force`12件/3,526、`Rapid Fire`7件/1,865、`Power Up`7件/1,536、`Critical Momentum`5件/1,533。これは最初の分岐頻度でありカード単体因果効果とは断定しない。
- Boss Devourerはカード取得/stack/手札RNGを保ったままDamage寄与と以後のBoss成長だけをOFF。OFFは各checkpoint直後で停止し、ON平均到達はW1000 1296、W1250 1518、W1500 1910。平均押上げ+296/+268/+410に加え、ON側だけ分散が発生しており、現状態はBoss Devourerへ進行とCard RNG分散を強く依存。
- 結果: [`../output/w5000_v1_card_rng_split_30_final/card_rng_report.md`](../output/w5000_v1_card_rng_split_30_final/card_rng_report.md)、JSON、全replay CSV、Boss matched CSV。バランス値は未変更。

## 最新更新（2026-09-26: w5000_v1 experimental RNG split）

- 通常のshared RNGを既定のまま維持し、診断呼び出し時だけCard/Weapon/Relic/Combatを決定論的な独立streamへ分ける`RNGStreams`を追加。明示shared呼び出しと従来呼び出しの`TrialResult`/最終RNG state一致を回帰テスト済み。
- DP v0.1 BC / W2500確定Legendary OFF / no Core / seed 20260828 / 30 trial。W1000/1250各30状態、W1500 29状態を保存し、各状態から7条件×6 counterfactual（3,738 replay）。error/nonfinite 0。
- 同一状態内の再生分散に対しCard stream固定でW1000 97.5%、W1250 97.5%、W1500 96.2%減少。Weapon固定は-0.4%/+1.2%/-2.5%、Relic固定は全て0%。Cardだけ可変でall-variable相当、Weaponだけ可変は小分散、Relicだけ可変は0。W1250～2000のRun variance主因はcheckpoint後のCard RNG。
- Weapon/Relic Powerと到達Waveの相関は高いが、Wave進行で装備Power自体が上がる逆因果を含む。介入ではWeaponの追加分散は小さくRelicは0なので、相関を因果と解釈しない。
- Boss Devourerは保存状態すべてで所持済み（W1000取得Wave P25/P50/P75=2/16/40）。所持有無は分散要因ではないが、同一状態・同一RNGで現在効果だけを抑止した89 matched pairsでは効果あり側が到達Wave P25/P50/P75で+33/+116/+257。過去の取得に伴うGrowth/Accelerated増加は巻き戻していないため、これは現在効果の限定的介入。
- runner: [`../scripts/diagnose_w5000_v1_rng_split.py`](../scripts/diagnose_w5000_v1_rng_split.py)。結果: [`../output/w5000_v1_rng_split_30_final/rng_split_report.md`](../output/w5000_v1_rng_split_30_final/rng_split_report.md)、raw CSV、JSON、checkpoint pickle。同条件の再利用が可能。全81テストOK。バランス値は未変更。

## 最新更新（2026-09-26: W2500確定Legendary分離診断）

- `w5000_v1`へ診断専用のW2500確定Legendary ON/OFF切替を追加。既定ONを維持し、legacy formal/D/E、Core、敵、カード、Weapon、Relic、DP v0.1 BCの数値は変更していない。
- seed 20260828 / 30 paired / max 140 Run / Coreなし。W2250まで全trialの到達可否・時刻が一致し、ON/OFF以外のconfigも一致。nonfinite/error 0。
- W2500到達は両条件10/30。ONでは10件すべて`Infinite Barrage`、即時ΔPower P50 +538.35、Margin P50 +546.07で10/10がW5000到達。OFFは即時Δ0、Margin P50 +8.10、7/10がW5000到達。全trial成功率は33.3%対23.3%。W2500の巨大jumpは確定`Infinite Barrage`が原因。
- W1500以上・W2500未満のRunでは、到達Waveとの関連が大きいのは`Boss Devourer` stack r=0.773、card count r=0.422、Relic Power r=0.369、Base ATK Power r=0.329、Weapon Power r=0.305、Rare枚数 r=0.332。単独要因ではなくRun内カード/装備の再抽選差が大きい。
- W1500初到達後の後続RunでW1350以上を再現した率はON 11.0%、OFF 15.6%。ただしW2500以前は条件が同一なので、確定LegendaryはW1250～2000の再現性崩壊の原因ではない。要素別の仮想再生はCard/Weaponが同じRNG streamを共有するため未実施。
- 診断runner: [`../scripts/diagnose_w5000_v1_guaranteed_legendary.py`](../scripts/diagnose_w5000_v1_guaranteed_legendary.py)。結果: [`../output/w5000_v1_guaranteed_legendary_30_final/w5000_v1_guaranteed_legendary.md`](../output/w5000_v1_guaranteed_legendary_30_final/w5000_v1_guaranteed_legendary.md)。全77テストOK。

## 最新更新（2026-09-26: w5000_v1 legacy DP vs DP v0.1 BC）

- Core/Enemy/Weapon/Relic/Card/140 Run上限を共通にし、legacy DPと既存DP v0.1候補BC（Economy B + Power C）をseed 20260828で30 paired trials比較。DP値は無調整、`w5000_v1`既定はlegacyのまま。
- 新DPはW1500到達率66.7%→96.7%、W1750 40.0%→73.3%、W2000 23.3%→60.0%、W2500 13.3%→33.3%。Highest Wave P50は1705→2177。最大140 Run到達は30→20、W5000成功は0→10。
- ただしW1500初到達後の後続Run単位の再到達はlegacy 37/737=5.0%、新DP 55/1033=5.3%。初回到達Wave-100以内も23/737=3.1%、32/1033=3.1%。新DPは到達trial数を増やすがRun再現性そのものはほぼ改善していない。
- 記録更新間隔P25/P50/P75は両方1/3/7 attempts。新DP最終Lv P50は合計314（Base42/AS41/XP44/Crit35/CritMult31/WeaponATK38/Luck30/Find28/Quality26）。
- W2500到達時、新DPのAS中央値5556とW2500確定Legendaryの`Infinite Barrage`系効果が組み合わさり、Margin中央値+546 Powerへ急増。これはDPの滑らかな恒久成長ではなくDP×Legendary相互作用で、10到達trialがそのままW5000成功。採用判断では分離が必要。
- non-DP config一致=True、nonfinite/error 0。全75テストOK。結果: [`../output/w5000_v1_dp_paired_30/w5000_v1_dp_paired.md`](../output/w5000_v1_dp_paired_30/w5000_v1_dp_paired.md)。

## 最新更新（2026-09-26: w5000_v1 W2500前ボトルネック）

- Core係数・バランス値を変更せず、`no_core` / Standard / 30 trials / seed 20260828 / max attempts 140で前半診断を実施。runner: [`../scripts/diagnose_w5000_v1_precore.py`](../scripts/diagnose_w5000_v1_precore.py)。
- 到達率はW100～1250が100%、W1500 66.7%、W1750 40.0%、W2000 23.3%、W2250/W2500 13.3%。最高Wave P25/P50/P75は1468/1705/1863、最終死亡Waveは1047/1120/1228。
- 全30 trialが140 attempts上限へ到達。Deaths P25/P50/P75も全て140。最終死亡は900～1199に20/30が集中し、過去最高Waveより後続Runが低い状態で打ち切られる。
- 最終恒久値P50: DP total 155（ATK/AS/XP=62/62/31）、Weapon material 42.25、Relic material 535.5、Weapon生成137、Relic生成7、Relic drop 10。Game Speed/Memoryは0。
- nonfinite 0、error 0。全72テストOK。結果: [`../output/w5000_v1_precore_bottleneck_30/w5000_v1_precore_bottleneck.md`](../output/w5000_v1_precore_bottleneck_30/w5000_v1_precore_bottleneck.md)。これは停止地点の診断で、調整案の採用ではない。

## 最新更新（2026-09-26: w5000_v1 Core比較基盤）

- `w5000_v1` scaffoldを維持したまま、Coreだけを交換する4 profileを追加: `no_core`、3段階候補`+0.90/+0.80/+0.65`、機械的弱版`-0.05/段階`、強版`+0.05/段階`。いずれも正式採用値ではない。
- CoreはW2500撃破時の非Draft報酬、Base ATK指数、100WaveごとのBig Boss数でRun内成長。死亡後の新Runでは指数1へ戻る。Final EquationはOFFのまま。legacy formalの固定`^1.05`とD/Eの`^1.02`は維持。
- 比較runner: [`../scripts/compare_w5000_v1_core_profiles.py`](../scripts/compare_w5000_v1_core_profiles.py)。同一seedをprofile間で使用し、Core以外のconfig一致とW2500までの到達可否/時刻一致を検査する。初回到達checkpointをtrial全体で保持する診断項目を追加したが、既存の最終Run checkpoint出力は維持。
- 10 paired trials / seed 20260828 / max attempts 140: W2500到達は1/10。no_coreはW3000未到達、Core 3種はその1 trialでW5000到達。Core以外のconfig一致=True、W2500 prefix一致=True、nonfinite=0。サンプル不足のため係数の強弱・採用は判断しない。結果: [`../output/w5000_v1_core_profiles_10/w5000_v1_core_profiles.md`](../output/w5000_v1_core_profiles_10/w5000_v1_core_profiles.md)。
- Core/scaffold専用13件を含む全72テストOK。次の判断では、W2500以前の低到達率をCore係数評価と混同しない。

## 最新更新（2026-09-26: w5000_v1 scaffold）

- CardValue Take v0.1は9-key追加状態でfreeze。これ以上対応keyを増やさない。
- [`../scripts/w5000_v1_profile.py`](../scripts/w5000_v1_profile.py) と [`../scripts/simulate_w5000_v1.py`](../scripts/simulate_w5000_v1.py) を追加。legacy formal/D/Eの既定挙動は維持。
- `w5000_v1`: target W5000、W5000 Enemy Power 308、W1～2500 legacy curve、W2500～5000は旧W2500～10000を3倍圧縮、Final Equation/Defense/Reward Skip無効、Refinement最大+1。
- Exponential Coreはscaffold既定では無効。交換可能な実験profileは追加済みだが最終係数は未決。DP v0.1、新Weapon、新Relic、CardValueは未採用・未統合。
- [`../scripts/test_w5000_v1_profile.py`](../scripts/test_w5000_v1_profile.py) のscaffold/Coreテスト13件を含め全72件OK。1 trial / 最大2 attempts smokeはbest Wave 53、成功0で、接続確認のみ。出力: [`../output/w5000_v1_scaffold_smoke_1.json`](../output/w5000_v1_scaffold_smoke_1.json)。
- 次の一手は未決項目を一つずつ選定すること。長時間試行やバランス結論はまだ行わない。

## 最新更新（2026-09-26: CardValue Take v0.1 9 key）

依頼されたStage 1～3を順に完了し、各gate後のみ次段階へ進んだ。実装差分は`scripts/card_value_v01.py`のTARGET/XP分類とGlass CannonのEncounter Conditional登録、関連テスト。formal本体・仕様値・legacy score・新W5000系は変更なし。

- 対応keyは25/55。追加9 key: `steady_force`, `heavy_blow`, `critical_eye`, `precise_strike`, `glass_cannon`, `heavy_critical`, `light_attack`, `sharpened_edge`, `critical_power`。残る30 keyは未対応。`overflow`は依然blocked_spec。
- XP Draft keyは意味的に明示した12 key。新規Combat keyはXP Draftとして分類されない。
- Stage 1 10-pair: PE 497/1,521 (32.68%)、fallback1,024 (全件unsupported)。Stage 2: 900/1,584 (56.82%)、fallback684 (全件unsupported)。Stage 3: 1,343/1,655 (81.15%)、fallback312 (全件unsupported)。各stageで10/10組が最初の分岐を持つ。
- 各Stage gateでfinite PE、入力state/RNG、候補合法性、最大PE選択、fallback理由を確認。違反/非最大0、internal-error fallback 0。Stage固有テストは最終11件、全体59件OK。
- Stage report: [`../output/card_value_take_stage1_4key_10.md`](../output/card_value_take_stage1_4key_10.md)、[`../output/card_value_take_stage2_7key_10.md`](../output/card_value_take_stage2_7key_10.md)、[`../output/card_value_take_stage3_9key_10.md`](../output/card_value_take_stage3_9key_10.md)。3段階比較と過去eligible-only基準との差: [`../output/card_value_take_stages_1-3_comparison.md`](../output/card_value_take_stages_1-3_comparison.md)。既存pilotは上書きしていない。
- 過去eligible-only baseline 180/1,477 (12.19%)比の適用率差はStage 1 +20.49pp、Stage 2 +44.63pp、Stage 3 +68.96pp。ただし判断候補数/分岐後stateが異なる探索指標であり、性能比較ではない。個別runnerレポートの旧比較欄は過去のfull-hand 54/1,477を参照する場合があるため、eligible-only比較は比較表を正とする。
- CardValue v0.1は9-key追加状態でfreeze済み。`overflow`を含む追加key、Reroll/Refine/Upgrade/terminal PEへの拡張は行わない。

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

**Claude共有パッケージ:** `output/claude_formal_v1_pe_take_bundle.zip`にformal W10000の仕様・実装・PE Take実験runner・4テスト・要約レポート・このHANDOFF等を相対パス付きでまとめた。約5 MBの判断JSONLと新W5000候補コードは含まない。ZIP内`README_FOR_CLAUDE.md`に読順とテスト・少数試行の再現コマンドを記載。ZIPを`/tmp/opencode/claude_formal_v1_pe_take_bundle_check`へ展開して`python3 -m unittest discover -s scripts -p 'test_*.py' -q`を実行し**48件OK**。次の一手はZIPをClaudeへ渡し、必要に応じて固定10組の判断JSONLを別途提供すること。CardValueやゲーム本体はパッケージングのためには変更していない。

## ファイル案内（推奨読順）

1. このファイル → [`CURRENT_STATE.md`](CURRENT_STATE.md) → [`DECISIONS.md`](DECISIONS.md) → [`../AGENTS.md`](../AGENTS.md)。
2. 現行仕様の位置付け: [`../first_prestige_v1_spec.md`](../first_prestige_v1_spec.md)、[`../card_value_evaluation_spec.md`](../card_value_evaluation_spec.md)、[`../card_value_take_experiment_design.md`](../card_value_take_experiment_design.md)、[`../predict_run_end_spec.md`](../predict_run_end_spec.md)、[`../card_value_encounter_conditional_design.md`](../card_value_encounter_conditional_design.md)、[`../card_value_xp_draft_h_design.md`](../card_value_xp_draft_h_design.md)。
3. 現行実装・テスト: [`../scripts/simulate_first_prestige_v1.py`](../scripts/simulate_first_prestige_v1.py)、[`../scripts/card_value_v01.py`](../scripts/card_value_v01.py)、[`../scripts/run_card_value_take_experiment.py`](../scripts/run_card_value_take_experiment.py)、[`../scripts/test_card_value_take_mode.py`](../scripts/test_card_value_take_mode.py)、他の`../scripts/test_card_value_*.py`。
4. 直近の事実: 新仕様の[`../output/card_value_take_eligible_pilot_10.md`](../output/card_value_take_eligible_pilot_10.md)、[集計JSON](../output/card_value_take_eligible_pilot_10.json)、[全判断JSONL](../output/card_value_take_eligible_pilot_10_branches.jsonl)。旧仕様の[`../output/card_value_take_pilot_10.md`](../output/card_value_take_pilot_10.md)、[`../output/card_value_take_pilot_10.json`](../output/card_value_take_pilot_10.json)、[`../output/card_value_take_pilot_10_branches.jsonl`](../output/card_value_take_pilot_10_branches.jsonl)。反実仮想[`../output/card_value_take_eligible_greedy_audit.md`](../output/card_value_take_eligible_greedy_audit.md)。新W5000の結果を見る場合は用途とtargetを先に確認（例: [`../output/new_w5000_legendary_v01_8card_30/new_w5000_legendary_v01.md`](../output/new_w5000_legendary_v01_8card_30/new_w5000_legendary_v01.md)）。

作業後は本ファイルに**何を変更したか・検証結果・次の一手**を追記し、引き継ぎを最新にする。

## 2026-09-27: W2500後 Core / late-DP統合比較

- 保存済みW2500到達10状態を使い、Infinite Barrage 37.5%、Boss Devourer base-heavy B、W2500確定Legendary OFFを固定して4 profileをpaired replayした。A=late-DP10/Core OFF、B=late-DP10/Core medium20%、C=late-DP25/Core OFF、D=late-DP25/Core medium20%。
- W5000成功率はA 50%、B 90%、C 60%、D 90%。Coreありは明確に改善したが、初回Run直行はB/Dとも1/10だけで、Core取得即W5000確定ではない。
- 一方、後続Run込みではB/DともW2750到達90%からW5000到達90%まで脱落がなく、W3000～5000の複数壁は実質残っていない。W5000成功Margin P50はB +107.12、D +134.99、Core直接寄与P50は約+99 Powerで余裕も大きい。
- Barrage非取得3件のW5000成功はCore OFFで0/3、Core ONで2/3。CoreによりBarrage必須性は下がるが、取得群はCore ONで7/7成功しており強い相互作用は残る。
- late-DP10と25はCore ON時の成功率・追加Run中央値が同じ（90%、11 Run）。late-DP10の方がDP直接寄与と成功Marginが小さく、Coreとの役割分担余地は大きい。ただし10状態なので率の精密決定・正式採用はしない。
- runner: [`../scripts/experiment_w5000_v1_integrated_core_dp.py`](../scripts/experiment_w5000_v1_integrated_core_dp.py)。結果: [`../output/w5000_v1_integrated_core_dp_10_states_final/integrated_core_dp_report.md`](../output/w5000_v1_integrated_core_dp_10_states_final/integrated_core_dp_report.md)。error/nonfinite/overflow 0、全96テストOK。formal・候補係数は未変更。

## 2026-09-27: Core 0/10/15/20% re-bracket

- late-DP10%、Infinite Barrage 37.5%、Boss Devourer base-heavy B、W2500確定Legendary OFFを固定し、保存済み10状態でCore scaleのみ0/10/15/20%をpaired replay。
- first-run W5000率は0/0/10/10%。Max Wave P50は2582/2623/2641/2690で、10～20%のいずれも取得即直行が一般化していない。
- long-run W5000率は50/70/70/90%。10%はcheckpoint到達が90/90/80/80/70/70%で後半壁を最も残すが、Barrage非取得2件は0/2成功。15%は90/80/70/70/70/70%、Barrage取得6/7・非取得1/3成功で「必須でも確定勝利でもない」に最も近い。20%は取得7/7・非取得2/3、全checkpoint 90%で過剰寄り。
- 15%のW5000 first-run Core直接寄与は+74.67 Power、成功Margin P50 +44.66。10%の成功Margin +140.59は別の成功trial構成による条件付き中央値で、15%よりCore自体が強い意味ではない。
- 正式採用・追加係数・試行増加なし。runner: [`../scripts/experiment_w5000_v1_core_rebracket.py`](../scripts/experiment_w5000_v1_core_rebracket.py)。結果: [`../output/w5000_v1_core_rebracket_10_states_final/core_rebracket_report.md`](../output/w5000_v1_core_rebracket_10_states_final/core_rebracket_report.md)。error/nonfinite/overflow 0、全96テストOK。

## 2026-09-27: Core後半shape比較

- 固定条件を維持し、flat10%、flat15%、tapered 15%→12.5%→10%を保存済み10状態でpaired replay。既存weak incrementへのstage scaleだけを変え、Big Boss timing/Core構造は不変。
- first-run Max Wave P50は2623/2641/2641、W5000率0/10/0%。long-run W3000/3500/4000/4500/5000はflat10=90/80/80/70/70%、flat15=80/70/70/70/70%、tapered=80/70/70/70/70%。taperedはflat15の70%横ばいを崩さなかった。
- W5000成功trial IDは3条件すべて同じ7件。taperedは追加Run P50を11→14、W2500後時間P50を0.591h→0.726hへ延ばしたが、成功/失敗境界は動かしていない。主効果は新しい壁の形成ではなく到達遅延。
- Barrage非取得成功はflat15で1/3、taperedで0/2。自然取得履歴は進行分岐で変わるため母数は同一でないが、taperedが依存を改善した証拠はない。
- 正式採用なし。runner: [`../scripts/experiment_w5000_v1_core_shape.py`](../scripts/experiment_w5000_v1_core_shape.py)。結果: [`../output/w5000_v1_core_shape_10_states_final/core_shape_report.md`](../output/w5000_v1_core_shape_10_states_final/core_shape_report.md)。error/nonfinite/overflow 0、全96テストOK。

## 2026-09-27: Unlimited Boost v0.1 connectivity probe

- 次の実験baselineを固定（未採用）: Boss Devourer base-heavy B、Infinite Barrage 37.5%、late-DP10%、Core flat15%、W2500確定Legendary OFF。Core shape探索は終了。
- 診断専用`UnlimitedBoostConfig`を追加。通常既定はOFF。W4000撃破後解禁、購入Lvはdeath後も`PermanentState`へ保持しprestige単位で初期化。Finaleは未実装。
- v0.1 nodeはBase ATK/Weapon ATK/AS/Crit Mult/All Damage/Boss Damage。costはWeapon 80/70/90、Relic 35/50/40、各node×1.70。効果は+5%/+5%/+5%/+0.10/+5%/+10%、Lv5超は効果50%。最低Lv優先の決定的購入policy。
- 保存済み10状態のOFF/ON pairedではW4000到達7件、W4250～5000到達率はいずれも70%で完全同一。成功7件はBoostなしでもW4000到達RunのままW5000へ進み、W4000→5000追加Run P50=0。現在baselineではBoostの進行効果を測れるW4000壁が存在しない。
- ONのW4000到達群は最終Lv P50が各node 3、Weapon Pt 1344、Relic Dust 701を消費。Boost直接寄与はW4000 +10.99、W5000 +38.33 Power、成功Margin P50 +44.66→+66.73。到達率を変えないまま余剰Powerだけ増やしており、v0.1数値は正式候補にできない。特にAS×Infinite Barrage/Core相互作用の単Lv限界効果を次回分離確認する余地がある。
- runner: [`../scripts/experiment_w5000_v1_unlimited_boost.py`](../scripts/experiment_w5000_v1_unlimited_boost.py)。結果: [`../output/w5000_v1_unlimited_boost_10_states_final/unlimited_boost_report.md`](../output/w5000_v1_unlimited_boost_10_states_final/unlimited_boost_report.md)。error/nonfinite/overflow 0、全100テストOK。

## 2026-09-27: Finale v0.1 experimental probe

- Unlimited Boost単独評価は保留。既存後半baselineを維持し、Finaleを通常Enemy curveとは独立した加算Power層として追加。通常既定OFF。W4500/4600/4700/4800/4900/5000で+0/+10/+20/+30/+40/+50、区間内は線形補間。特殊ルール/Defense/Cap/耐性は追加していない。
- 保存済み10状態でA Finale OFF/Boost OFF、B Finale ON/Boost OFF、C Finale ON/Boost ONをpaired replay。W4000到達は各7/10、長期W5000も各7/10で同じ。Finaleは最終成功率を下げず、成功までの再挑戦を増やした。
- AはW4000→5000追加Run P50=0。BはP25/P50/P75=0/15/20、W4000後0.655h。W4500+ deathは4585/4586/4596/4644/4727/4949に発生し、目的どおり段階的な停止地点を作った。
- Cは追加Run=0/0/9.5、W4000後0.001h。7成功中4件は同Run直行、3件は5/14/16追加Runを要したため自動突破100%ではないが、Boostは壁を大きく圧縮。Boost最終Lv P50はBase/Weapon/AS=3、CritMult=4、All/Boss=3、素材消費Weapon1344/Relic1070。
- Barrage非取得群はB/Cとも0/2成功で、Finale下では依存改善が見られない。成功Marginは試行途中の恒久成長量が異なるためFinale強度の単純比較には使わない。
- runner: [`../scripts/experiment_w5000_v1_finale.py`](../scripts/experiment_w5000_v1_finale.py)。結果: [`../output/w5000_v1_finale_10_states_final/finale_report.md`](../output/w5000_v1_finale_10_states_final/finale_report.md)。error/nonfinite/overflow 0、全103テストOK。正式採用なし。

## 2026-09-27: Unlimited Boost node因果診断

- Finale ON / Boost ON / Core flat15% / late-DP10% / Infinite Barrage37.5% / Boss Devourer base-heavy Bを固定し、保存済み10状態で各Boost nodeの効果だけをOFFにした7条件をmatched replay。購入・素材消費・Lv・購入順は通常どおりで、戦闘効果参照だけを抑止する。
- FullはW5000 7/10。Base ATK / Weapon ATK / Crit Mult / All Damage / Boss Damage OFFはいずれも7/10のまま。Attack Speed OFFだけ6/10、W4800以降70%→60%、W4000→5000追加Run P50は0→2.5、同一Run率57%→43%。
- 同一stateへAS nodeを復元した直接差はW4500 +36.11 Power、W5000 +61.12 Power。このうちW5000 +60.82 PowerがInfinite Barrage相互作用、Core相互作用は+0.08。共通W5000到達6件ではAS +1608.26、制限時間内攻撃可能回数+24,124、Barrage寄与+58.45 Power、Margin+57.80（各P50）。AS nodeが壁圧縮の支配要因。
- Barrage取得群はFull 7/8成功、AS OFF 6/8。非取得群はいずれも0/2。Boost nodeよりBarrage依存自体も残る。標本10のため正式nerf/採用判断はしない。
- `UnlimitedBoostConfig.suppressed_nodes`と専用runner [`../scripts/experiment_w5000_v1_boost_node_suppression.py`](../scripts/experiment_w5000_v1_boost_node_suppression.py) を追加。既定は空で通常挙動不変。結果: [`../output/w5000_v1_boost_node_suppression_10_states_final/boost_node_suppression_report.md`](../output/w5000_v1_boost_node_suppression_10_states_final/boost_node_suppression_report.md)。error/nonfinite/overflow 0、全104テストOK。

## 2026-09-27: Unlimited Boost v0.2 direction candidate

- v0.1と正式profileを維持したまま、experimental v0.2を追加。AS nodeを除き、同じ購入位置/Weapon Pt base cost 90のFinale Masteryへ置換。Finale MasteryはFinale ONかつW4500以降だけ+1.25 Power/effective Lv。
- 他nodeの初期候補はBase/Weapon ATK +0.35 Power/effective Lv（Core前）、Crit Multiplier ×10^0.50/effective Lv、All/Boss Damage +1.25 Power/effective Lv。cost growth、Lv5 softcap、購入policyはv0.1維持。正式値ではない。
- Finale ONの保存済み10状態でOFF/v0.1/v0.2をpaired比較。W5000到達は全て7/10、同一Run率は43/57/57%。W4000→5000追加Run P50は15/0/0。v0.2 P75は5で、v0.1の9.5より小さいが標本10の条件付き値。
- W5000 Boost寄与P50は0/58.24/22.46 Power。v0.2 node限界寄与はBase 3.98、Weapon 3.98、Finale Mastery 3.75、Crit 1.50、All 3.75、Boss 3.75。最大share 19.2%で、目標20～30 Power・単node 50%未満を満たす方向性を確認。
- Barrage取得群の成功は3条件とも7/8、非取得群0/2。v0.2はAS×Barrage爆発を除いたが、カード依存そのものは未解消。W5000 Margin P50はv0.2 +44.04で、v0.1 +138.46よりoverkillを抑えた。正式採用・細部最適化なし。
- runner: [`../scripts/experiment_w5000_v1_unlimited_boost_v02.py`](../scripts/experiment_w5000_v1_unlimited_boost_v02.py)。結果: [`../output/w5000_v1_unlimited_boost_v02_10_states_final/unlimited_boost_v02_report.md`](../output/w5000_v1_unlimited_boost_v02_10_states_final/unlimited_boost_v02_report.md)。error/nonfinite/overflow 0、全106テストOK。

## 2026-09-27: Infinite Barrage依存診断（Boost v0.2固定）

- Unlimited Boost v0.2を次の診断baselineとして固定（formal未採用・値変更なし）。保存済み10状態でA現行37.5%、B効果OFF、C現行の50%=18.75%、D総Barrage Powerへ`20*(1-exp(-raw/20))`を適用するsoft-cap候補をmatched replay。
- W4500/W4750/W5000到達率はA 70/70/70%、B 10/0/0%、C 60/50/30%、D 10/0/0%。取得群成功はA 7/8、B 0/8、C 3/8、D 0/8。非取得群は全条件0/2。
- AのW5000 Barrage寄与P50は+222.44 Power。AS別ではAS<5000で+152.30、5000～9999で+213.75、10000～19999で+513.35、20000以上で+743.58。Cは同AS状態でほぼ正確に半分。DはRun終了時にAS帯を問わず約+20へ収束したがW5000成功0。
- 現行条件ではBarrageは単なる強Legendaryではなく、W5000突破の実質必須条件に近い。半減は一部成功を残すが、soft cap 20 Powerは弱すぎる。CのW5000寄与P50 +291.90がAより大きいのは成功者集合が3件へ絞られた生存者選別で、効果逆転ではない。
- runner: [`../scripts/experiment_w5000_v1_barrage_dependency.py`](../scripts/experiment_w5000_v1_barrage_dependency.py)。結果: [`../output/w5000_v1_barrage_dependency_10_states_final/barrage_dependency_report.md`](../output/w5000_v1_barrage_dependency_10_states_final/barrage_dependency_report.md)。first acquisition signature一致、error/nonfinite/overflow 0、全107テストOK。正式Barrage値は未変更。

## 2026-09-27: 旧Barrage 37.5% / v2の前半～中盤診断

- 現行baselineを固定し、30 trial（seed 20260828）のW1～2500を共通実行後、保存できたW2500到達10状態だけを旧Barrage 37.5% / v2 fixed-ratioへpaired分岐した。Barrage以外のW500～2500 payloadは完全一致。
- Infinite Barrageの解禁はW2500なので、W500/750/1000/1250/1500/1750/2000/2250の旧/v2直接寄与と差はすべて0 Power。W2500 checkpointでも取得前状態のため0。したがって旧BarrageはW1000～1750を肩代わりしておらず、同帯域の再ボトルネック原因をBarrage v2化へ帰属できない。
- 到達率もW500～1500=100%、W1750=83%、W2000=50%、W2250=47%、W2500=33%で両条件共通。Margin P50はW1000 +1.16、W1250 +1.63、W1500 +2.66、W1750 +1.42。
- W2500後は旧式が差を作り、Highest Wave P25/P50/P75は旧1827/2052/3321、v2 1827/2052/2580、W4000到達は旧7/30、v2 1/30。W2500到達は両者10/30。
- runner: [`../scripts/diagnose_w5000_v1_old_vs_v2_midgame.py`](../scripts/diagnose_w5000_v1_old_vs_v2_midgame.py)。結果: [`../output/w5000_v1_old_vs_v2_midgame_30_final/old_vs_v2_midgame_report.md`](../output/w5000_v1_old_vs_v2_midgame_30_final/old_vs_v2_midgame_report.md)。error/nonfinite/overflow 0、全110テストOK。補償・新カード・balance値変更なし。

## 2026-09-27: W2500成功10 / 未到達20の中盤カード分岐診断

- 直前と同じ30 trial / seed 20260828をTake診断ログ付きで再生し、W2500成功trial ID 10件が完全一致。W1000～2000の最初のcheckpoint到達Runを比較した。
- Rarity droughtは主因ではない。W1500のRare+不提示連続draft P50は成功13.5、失敗11.5で成功側の方が長い。W1000のRare+枚数も成功6、失敗7。W1250は両群7.5。
- 明瞭な分岐はW1250後～W1500の突破Run構成。W1500で成功/失敗はRare+ 10/8、Escalation 3/1.5 stack、Steady Force 7.5/6.5、Margin +5.22/+1.31。Boss Devourerは両群3 stack。失敗側はRapid Fire 5/4、Power Up 6.5/5.5、Critical Momentum 3/2で、単純なカード枚数やRare数より成長/全Damage寄り構成の差が大きい。
- W1250では失敗群の方がDP Power 8.56/8.21、AS 990/735、Weapon 3.12/3.08、Margin +2.20/-0.24とむしろ強く、DP/Weapon不足を早期原因とは判定できない。W1750/W2000失敗群は到達者15/5件だけなので生存者選別あり。
- rerollは実装上各draftごとに再付与。W1000～2000の使用P50はtrial総数69.5/143.5だが、Run当たり3.33/3.38で同等。失敗側の総数増は再挑戦Run数の結果。近いW1250/W1500 state各4組×6 replayでrarityまたはreroll RNGを固定しても到達中央値・率はほぼ不変で、将来抽選よりcheckpoint時点の既存構成が支配的。
- runner: [`../scripts/diagnose_w5000_v1_midgame_card_divergence.py`](../scripts/diagnose_w5000_v1_midgame_card_divergence.py)。結果: [`../output/w5000_v1_midgame_card_divergence_30_final/midgame_card_divergence.md`](../output/w5000_v1_midgame_card_divergence_30_final/midgame_card_divergence.md)。errors/nonfinite 0、全110テストOK。balance変更なし。

## 2026-09-27: W1250～1500 card-effect matched診断

- 同じ30 trialの全attempt checkpoint stateを再収集し、rarity/reroll/draw RNG・取得履歴・取得Wave・実stackを固定したままeffectだけを再計算。250Wave gridの到達判定で、存在しない未来stateは生成していない。
- Escalationが逆転の主因。成功群でOFFにするとW1250/W1500/W2000 Power P50が-5.30/-9.54/-12.71、W2500到達100%→10%、Highest P50 2500→1999。W1250→1500成長差はcurrent成功/失敗5.12/4.25からOFF 4.35/4.04へ縮小。
- 成功群を1.5 effective stackへcapするとW2500 40%、W2000 60%。失敗群を3 stackへfloorするとW1500 +3.18 Power、W1250→1500成長4.25→4.83。ただし改善後の未観測未来stateを作らないため、到達率改善はこの方式では下限評価不能。
- Steady Force OFFはW1500 -0.005、Rapid Fire -0.31、Power Up -0.40、Critical Momentum -0.14 Power。これら単独ではW1500到達率不変。Escalation+Steady OFFはEscalation単独と同じ。
- W500報酬込みEpic偏りはPerfect Learning成功3/10・失敗0/20、Double Scaling 5/10・8/20。Perfect Learningは履歴固定の即時評価で0。Double Scaling OFFは成功W1500 -2.58、W2500 100%→60%で絶対火力に重要だが、区間成長差の主因ではない。
- `SimConfig`へ通常既定空のdiagnostic effect stack cap/floorを追加し、実所持状態を変えない2テストを追加。runner: [`../scripts/diagnose_w5000_v1_midgame_card_effects.py`](../scripts/diagnose_w5000_v1_midgame_card_effects.py)。結果: [`../output/w5000_v1_midgame_card_effects_30_final/midgame_card_effects.md`](../output/w5000_v1_midgame_card_effects_30_final/midgame_card_effects.md)。errors/nonfinite/history mutation 0、全112テストOK。正式balance変更なし。

## 2026-09-27: Escalation growth strength実験

- 同じ30 trial / seed 20260828の全attempt checkpoint stateを使い、取得Wave・実stack・カード履歴・RNGを維持したまま、EscalationのWave依存成長部分だけを100% / 65% / 50%へ縮小した。通常既定は100%で変更なし。
- W1250/W1500/W1750/W2000/W2250/W2500到達率は、100%で100/100/83/50/47/33%、65%で100/97/70/40/20/13%、50%で100/90/60/30/20/10%。Highest P50は2052 / 1942 / 1796。
- W1500のEscalation直接寄与P50は、high stack（3枚以上）で9.54 / 6.20 / 4.77 Power。W2500率は同群64% / 27% / 18%、low stack（0～1枚）は17% / 8% / 8%。65%でも強い成長カードとして差を残すが、取得群の自動突破性は大幅に低下した。
- 50%は65%よりW2500を3pt下げるだけだが、W1500到達を97%→90%、Highest P50を1942→1796へ下げる。小標本・250Wave grid診断では65%が次の候補帯、50%はやや強いnerfの兆候。ただし正式採用なし。
- W1500再到達率P50は9% / 6% / 5%、Best-recent10 gap P50は830 / 689 / 631。Escalation縮小だけではRun再現性問題は解消しない。
- runner: [`../scripts/experiment_w5000_v1_escalation_strength.py`](../scripts/experiment_w5000_v1_escalation_strength.py)。結果: [`../output/w5000_v1_escalation_strength_30_final/escalation_strength.md`](../output/w5000_v1_escalation_strength_30_final/escalation_strength.md)。error/nonfinite 0、全113テストOK。

## 2026-10-02: Backpack等のUI拡張に向けた現行構造調査

- 対象: first-prestige-playtest（旧formal計算を使うW1～500 adapter）。root App.tsxの別incremental demo、新W5000候補と区別。実装・spec・balanceは変更していない。
- 状態の正本は sim_server.py の PlaySession.run / permanent。ReactはSessionStateをAPIから受け取る。サーバーメモリ上のみで、ディスクへのsave/loadなし。
- Weaponは装備1本＋pendingWeapon＋次Run予約のみ。inventory/個体IDなし。RelicはPermanentState.relic_types(set[int])、重複総数、全体qualityで保持し、APIは種類数しか公開しない。
- Card一覧はrun.counts→run.cards(key/name/count)。rarity/tags/description等はCARD_BY_KEYから追加公開できる。Sort UI未実装。
- Furnace相当はadapter _resolve_weapon（旧装備の自動素材化・候補smelt）とformal equip_or_smelt_weapon。独立Furnace画面/任意所持品の分解なし。
- BattleはCombatStage / LastAscentStageを使う。タイマーとAPI actionはpage.tsxにあり再利用可能。縮小にはabsolute配置/min-height 870px等をcompact layoutへ変更する必要あり。
- Active/PrestigeのLocked枠はUI追加で可能。SessionState.statusへUIタブ状態を混ぜない。解禁条件・効果は未決定。
- UBはformal共有エンジンに恒久Lv/解禁/素材消費/config/購入処理あり。通常OFF、W4000解禁の実験候補。playtest API/type/UI/購入actionなし、W500 targetでは解禁に届かない。
- 要確認: sim_server.py:417,582 の acquire_relic 呼び出しはconfig引数を渡していないが、現formal定義はconfig必須。遺物ドロップ/生成経路の接続不整合。今回修正していない。
- 検証: spec・Python・TSX・CSSの静的照合のみ。テスト/シミュレーション未実行（コード変更なし、trial/seed該当なし）。
- 次の一手: 表示専用Backpack/Locked枠と、複数武器保管の仕様追加を区別して実装範囲を決める。遺物一覧にはtype ID公開を追加し、上記config接続を修正・確認する。
- 再現: rg -n 'class PermanentState|class RunState|def acquire_relic|def equip_or_smelt_weapon|unlimited_boost' scripts/simulate_first_prestige_v1.py ; rg -n '_run_payload|_permanent_payload|_resolve_weapon|acquire_relic' first-prestige-playtest/sim_server.py
# 最新更新（2026-10-04: 新カード/BC DPの手動W5000候補へ切替＋死亡修正）

- ユーザーが「新カード・新DP・個体装備の候補版」を選択。Figma Mainを`new_w5000_session.py`/`new_w5000_rules.py`へ接続。旧formal/D/E・w5000_v1既定・CardValueは変更なし。
- 新C/U/R/E/L=48定義、Relic Apotheosis除外で47枚。旧初期Take禁止・旧DP totalLv巨大倍率・旧Weapon/Relic Powerは不使用。BC DP9項目＋Reroll購入を画面へ接続、個体Drop/通常Affix使用。
- 新カードプローブ系列と、旧formalカードを使うw5000_v1後半診断系列は別物。Escalation/Barrage等は新集合に混ぜない。詳しい接続/未接続は`NEW_W5000_PLAY_CANDIDATE.md`。
- 依存注入のoptional引数を既存DP calculator/FU factorへ追加、既定経路は不変。install/monkeypatchはプレイで不使用。
- サブエージェントAmpereが旧PlaySession死亡constructor/atomic準備を修正、UIはAPI失敗で一時停止。新候補の死亡精算も一度だけ、死亡武器50%回収/遺物保持/再挑戦をテスト。
- 149 scriptsテスト・TypeScript成功、新接続15件。合成checkpoint/短い手動ループのみ、balance Monte Carloなし。
- 未接続: 全遺物/W500以降報酬/武器固有/Core/UB/Finale/手動Refine/保存/保管拡張/転生後。12h/W5000成功率の結論なし。
- 次: 未接続システムを新カード系列と整合させて個別接続。候補値を勝手に正式採用しない。
- 再現: `python -m unittest discover -s scripts -p 'test_*.py' -q`; `cd first-prestige-playtest; npm run dev -- --port 4173`。
