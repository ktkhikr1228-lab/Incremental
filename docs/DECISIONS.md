# 確定した設計判断と適用範囲

## 最新の操作判断（2026-10-04）

- ユーザー指定で新W5000手動候補のカード選択・バックパック・設定をnon-blockingにする。カード未選択はRun内蓄積、死亡時破棄。死亡後は手動再挑戦、自動再挑戦は延期。
- 武器取得はバックパックを開かず、新規/装備/保管品の一覧で装備・保管・分解を選ぶ。炉は即分解で確認なし。所持カードはrarity色/名称とクリック説明。
- XP必要量・カード性能の1.5倍案は未採用。今回は操作改善だけを実装・検証してGitHubへ保存。スマホ専用対応は次の作業。
- 以前の「戦闘中は装備編集禁止」は旧接続制約の履歴。新手動候補では残HP/経過時間/攻撃位相を保持して途中変更する。formal/specを変更する判断ではない。

## 最新の接続判断（2026-10-04）

ユーザー選択によりMainを新カード・新DP・個体装備の候補版へ切替。正式balance採用ではない。旧formal/D/E/scaffold/CardValueは保持し、未接続効果を旧効果で代用しない。詳細は末尾の今回決定と`NEW_W5000_PLAY_CANDIDATE.md`。

## 2026-10-04: UI接続時の扱い

- Mainの鞄は左下、Backpack内は左上。Figmaの「遺物2個＋空欄」は3装備枠の表示例、「カード」ラベルは横スクロールの省略表示であり仕様変更ではない。
- Figmaを変更するのではなく既存ゲームUIへ移植。新装備接続候補を通常旧プレイテストと分離する。仮接続を新W5000正式balanceと扱わない。
- 戦闘APIは1戦を原子的に解決するため、現接続版の装備変更はカード選択・装備報酬・死亡中のみ。戦闘中は詳細確認のみ。これは接続版の制約で、将来の戦闘中交換仕様の確定ではない。

## 2026-10-03: 初版装備の境界

- 新W5000用候補として進める。旧formal/D/Eを変更しない。
- 遺物分解C1/U3/R6＋実消費強化素材50%返還（切り捨て）。強化倍率1.08/1.16/1.24、コスト4/9/16は初版候補。
- 遺物固定品質1.00。同名は交換/重複/分解。重複は固有正数値の基準+2%/回、10回まで、Affix・整数・特殊ルール対象外。
- W100初回Common学習レンズ、W500..4500各500Wave初回報酬。遺物・素材は死亡で保持、Prestigeで個体・素材・保管拡張リセット、各5枠。報酬抽選は未実装。
- rarityは既存Wave段階ドラフト、補間/Luckなし。Legendary武器第2固有・槍・遺物生成/振り直しは延期。
- 参照: `W5000_EQUIPMENT_V01.md`。仕様候補の整理は正式balance採用やゲーム統合を意味しない。

## v2 Barrage後半baseline診断の判断材料（2026-09-27）

- Barrage数値探索は停止し、v2 fixed-ratioを後半診断baselineとして使用するがformal採用しない。
- Finale OFFではW4000へ届いた唯一のtrialがBoostなしでもW5000へ到達。Boost v0.2は同trialのMarginを約+12.74 Power増やすが到達率を変えない。
- Finale ONではBoostなしW4585、BoostありW4697で停止しW5000 0/10。現sampleではFinaleがW4500以降へ明確な壁を作り、Boost v0.2は壁を延長するが突破させない。
- W4000到達1件のためFinale/Boost強度を変更する根拠には不足。追加候補や係数変更は行わない。

## Infinite Barrage v2構造診断の判断材料（2026-09-27）

- raw integer ASを直接Power化しない`v2_fixed_ratio`をexperimental経路に追加したが、formal/default legacyは変更しない。
- N=20・通常攻撃5発分はAS 100～20000で常にnormal DPSの25%となり、ASによる寄与暴走を解消。既存kill-growth併用候補も0.25 Power漸近softcapでAS帯別寄与が一定になった。
- 保存済み10状態ではfixed/softcapともW5000 0/10のため数値採用根拠はない。構造は目的を満たすが、強度・成長の扱いは未決定として追加調整を自動で行わない。

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

## w5000_v1 W2500後診断の固定条件（2026-09-26）

- late-DP係数探索はいったん停止。`late_dp_10`はCard分岐診断のbaselineとしてのみ使用し、正式採用しない。
- Exponential CoreはOFFのまま。DP/Core/Enemy/Weapon/Relic/Card数値をCard効果抑止診断から変更しない。
- Card因果診断ではdraw poolからカードを削除せず、通常取得・所持・履歴を維持したままeffectだけを抑止する。相関表とmatched intervention結果を分ける。
- 現行`w5000_v1` poolにないLegendary v0.1 probe専用カードを診断のために移植しない。
- Infinite Barrageの0/25/50/75/100%比較は診断のみ。75%以上は取得trial全件W5000、50%は6/7、25%は3/7。次の候補帯を25～50%として記録するが、正式値やカード式はまだ採用変更しない。
- 37.5%追加診断は取得trial 5/7がW5000、全体checkpoint到達率70/70/60/50/50%。意図した「非常に強いが取得だけでは突破保証しない」位置に入ったと記録する。正式採用はせず、31.25%/43.75%も未実行。
- Infinite Barrage 37.5%固定下ではlate-DP 50%は取得trial 8/8がW5000となり過剰。late-DP候補帯は10～25%として記録し、Coreを主成長にするなら10%が余地最大、25%は上限寄り。どちらも未採用で、追加候補は作らない。

## CardValue v0.1 対応範囲更新（2026-09-26）

- formal v1のコードで効果が一意に確認でき、既存Snapshot経路で表せる9 keyを段階的にTake評価対象へ追加した。Glass Cannonのみ、制限時間短縮があるため既存Encounter Conditional（実TTK）経路を使う。カード値・legacy score・formal仕様値は変更していない。
- XP Draft対象は明示的な意味集合で管理する。Combat keyの追加によってXP側へ誤分類されない。
- 段階別の10-pair pilotとgate結果は[`../output/card_value_take_stages_1-3_comparison.md`](../output/card_value_take_stages_1-3_comparison.md)。これは適用範囲の診断であり、各10ペアからバランス優劣を判断しない。
- 9 key以外は未対応のため、合法手札に未対応keyが含まれる場合は従来規則どおり手札全体をlegacyへfallbackする。`overflow`は仕様未確定のため引き続きblocked_spec。
- CardValue Take v0.1はこの9-key追加状態でfreezeする。今後のW5000統合でも対応keyを増やさず、CardValue自体を自動移植しない。

## w5000_v1 migration scaffold（2026-09-26）

- legacy formal W10000とVariant D/Eは保存し、`w5000_v1`を独立profile/entry pointとして追加する。
- 確定設定はtarget W5000、W5000 Enemy Power 308、W1～2500はlegacy curve、W2500～5000はlegacy W2500～10000の3倍圧縮、Final Equation/Defense/Reward Skip無効、Refinement最大+1。
- Exponential Core最終係数、DP v0.1、新Weapon、新Relic、CardValue統合は未決。scaffoldではCoreを暫定無効化し、他の未決システムを正式採用したとは扱わない。

## w5000_v1 Exponential Core実験境界（2026-09-26）

- scaffold既定の`no_core`は維持し、Core係数は独立profileでのみ切り替える。比較profile間で変えてよいのはW2500保証取得と3段階の指数増分だけ。
- 基準候補は`N=1..6: +0.90`、`N=7..16: +0.80`、`N=17..26: +0.65`。弱/強比較は各段階を一律`-0.05`/`+0.05`しただけの診断値で、いずれも正式採用ではない。
- CoreはW2500撃破時の非Draft報酬として扱い、カード枚数・選択回数・Growth/Accelerated等を発火させない。Run内Big Boss進行でBase ATK指数が増え、死亡後は指数1へ戻る。Final Equationは引き続きOFF。
- 10-pairは交換経路・paired条件・finite性の確認に限定する。W2500到達が1/10だったため、Core形状の優劣や正式係数は未決のまま。
- single-run診断後、既存weak incrementの20%版（段階構造は同一）を**暫定Core候補**として記録する。ただし正式採用ではなく、Core係数探索はいったん停止する。scaffold既定`no_core`も変更しない。

## W2500後 Core / late-DP統合比較の判断材料（2026-09-27）

- Infinite Barrage 37.5%、Boss Devourer base-heavy B、W2500確定Legendary OFFを固定した10状態比較では、medium20% CoreはW5000成功率を90%へ上げた一方、long-runのW2750～5000に段階的脱落が残らず、成功Marginも+107～135 Powerだった。
- Core取得Runの即時W5000直行は1/10なので「取得即クリア」ではないが、後続Run込みではまだ強い。medium20%を正式採用しない。
- late-DP10%と25%はCore ON時の成功率が同じで、10%の方がDP寄与・余裕量が小さい。Coreを後半主成長に置く場合の判断材料としてlate-DP10%が役割分担上は有利。ただし正式採用は未決。
- Infinite Barrage非取得でもCore ONでは2/3が成功したため必須性は下がるが、取得群7/7成功との相互作用は残る。カード・DP・Coreの追加変更はユーザー決定まで行わない。

## Core re-bracket判断材料（2026-09-27）

- late-DP10%固定の0/10/15/20%比較では、20%はlong-run全checkpoint 90%で過剰寄り。10%は複数壁を最も残す一方、少数標本上はInfinite Barrage非取得で成功0/2となり依存を解消できない。
- 15%はBarrage取得6/7、非取得1/3成功で「必須でも確定勝利でもない」に最も近い中間候補。ただしW3500以降の到達率が70%で横ばいのため、複数壁を十分残したとは判断しない。
- 10状態のbracket結果だけでCoreを正式採用しない。追加係数・試行増加も未実施。

## Core shape比較の判断材料（2026-09-27）

- tapered 15%→12.5%→10%はflat15%と同じW3500～5000到達率70%、同じ成功trial 7件となり、後半shape変更で70%横ばいを崩す目的を達成しなかった。
- taperedは追加Runと時間を増やす一方で成功境界を動かさず、Infinite Barrage依存改善も確認できない。今回のtapered案を正式採用しない。
- 指示どおり別shape/係数は追加しない。flat15%も引き続き候補であり正式値ではない。

## 後半実験baseline / Unlimited Boost境界（2026-09-27）

- 次のシステム実験ではBoss Devourer base-heavy B、Infinite Barrage37.5%、late-DP10%、Core flat15%、W2500確定Legendary OFFを暫定baselineとして固定する。いずれもformal採用ではない。
- Core shape探索は終了する。別Core係数・shapeを自動追加しない。
- Unlimited Boost v0.1はW4000解禁の診断専用material sinkとして実装し、通常profileではOFF。Finaleはまだ実装しない。
- 初回数値は到達率を変えずW5000余剰を+38.33 Power増やしたため正式採用しない。現在baselineにW4000後の壁がなく、Boostの進行効果そのものを評価できていない点を次判断で分離する。

## Finale v0.1実験境界（2026-09-27）

- Unlimited Boost単独評価は保留し、Finaleだけを通常Enemy curveと独立した加算Power層で試す。v0.1 anchorsはW4500=0、4600=10、4700=20、4800=30、4900=40、5000=50、区間線形補間。通常既定はOFF。
- 10状態ではFinale ON/Boost OFFがW4500以降の死亡と追加Run中央値15を作り、壁の接続目的を満たした。Boost ONは中央値0まで圧縮したが3/7件は再挑戦を必要とし、自動突破100%ではない。
- 長期W5000到達率は全条件7/10で同じため、Finale v0.1は成功集合を変えるより所要Run/時間を増やす層として働いた。Finale値・Boost値とも正式採用しない。新係数候補は追加しない。

## Unlimited Boost node診断の判断材料（2026-09-27）

- node別比較は購入経済を変えずeffectだけを抑止する。診断用`suppressed_nodes`は正式balance変更ではなく、通常既定は空のまま。
- 現v0.1ではAttack Speed nodeの直接Powerの大半がInfinite Barrageとの相互作用（W5000 P50で総+61.12中+60.82 Power）。他5 nodeは10状態で成功集合を変えず、Boost全体を一律弱体化すべき根拠はない。
- AS OFFでもBarrage取得群6/8、非取得群0/2で、AS nodeとBarrage依存は別問題として扱う。標本10なのでAS値・Barrage式・Finale値の正式変更はまだ決定しない。

## Unlimited Boost v0.2候補の判断材料（2026-09-27）

- v0.2は診断候補としてASを削除し、Finale ONのW4500以降だけ有効なFinale Masteryへ置換する。v0.1・formal・通常既定は変更しない。
- 初期候補はW5000総寄与P50 +22.46 Power、最大node share 19.2%で、探索目標の合計20～30 Power・単node 50%未満を満たした。細かい最適化や正式採用はしない。
- W5000成功集合はOFF/v0.1/v0.2で同じ7/10。v0.2は余剰Marginをv0.1より縮めたが、Barrage非取得群0/2の依存は残る。Boost調整とLegendary依存は分けて判断する。

## Infinite Barrage依存診断の判断材料（2026-09-27）

- Unlimited Boost v0.2は後続診断baselineとして一旦固定するが、formal採用ではない。今回Boost値は変更していない。
- Barrage効果OFFと20 Power soft capは取得群0/8、半減は3/8、現行は7/8成功。現行baselineではBarrageはW5000の実質必須条件に近い。
- ASとBarrage寄与は強く連動し、現行W5000ではAS約4k/5.7k/13.9k/20.2kに対しBarrage約152/214/513/744 Power。将来の調整では単純な20 Power capは採用根拠がなく、成功者条件付き中央値の生存者選別にも注意する。
- この診断は正式balance変更ではない。新しいBarrage候補値はユーザー決定なしに追加しない。

## 旧Barrage / v2前半診断の判断材料（2026-09-27）

- Infinite Barrageの解禁はW2500。paired 30 trialでW500～2250の旧37.5% / v2寄与差は0 Power、到達状態も同一だった。
- よってW1000～1750の停滞を「旧Barrageが肩代わりしていた分の欠落」と解釈しない。Barrage式の差はW2500以降の後半進行として扱う。
- W2500後は旧式の方が強く、W4000到達7/30対1/30。ただしこの結果から補償値や新カードは作らない。

## W1500～2000カード分岐の判断材料（2026-09-27）

- Rare+ drought、rarity率、reroll強化を直ちに原因扱いしない。成功群はW1500でdroughtが短くなく、W1000ではRare+枚数も失敗群より少ない。
- 最初の大きな観測差はW1250後～W1500のRun内構成で、Escalation/Steady Force寄りとRapid Fire/Power Up/Critical Momentum寄りの差。ただしこれは30 trialの診断であり、個別カード調整の正式根拠にはしない。
- rerollは現在「Runで有限」ではなく各draftごとに再付与される。trial総使用数は再挑戦回数に強く依存するため、原因指標にはRun当たり値を使う。
- rarity/reroll固定counterfactualではW1250/W1500後の結果をほぼ動かさなかった。pity、rarity率、reroll、個別カード値はまだ変更しない。

## 中盤card-effect matched診断の判断材料（2026-09-27）

- W1250～1500の逆転はEscalation effectが主要因。取得率の相関だけでなく、同一stateのeffect OFFで成功群W1500 -9.54 Power・W2500率100%→10%を確認。
- Steady Forceのstack差は同枠飽和により実効差がほぼなく、Rapid Fire/Power Up/Critical Momentumも単独では逆転境界を動かさない。
- Double Scalingは絶対火力に重要だが、W1250→1500の成長差より全区間の基礎Powerを支える。Perfect Learningの将来XP価値は取得履歴固定診断では評価不能。
- この結果はcard nerf/buffの決定ではない。特にEscalation floorの到達改善は未観測未来stateを生成しない設計上、Power差のみを判断材料とする。

## Escalation strengthの判断材料（2026-09-27）

- formal/defaultのEscalationは100%のまま。65% / 50%は診断候補であり、正式採用していない。
- matched 30 trialでは65%がW1500到達97%を保ち、W2500到達を33%→13%、high-stack群を64%→27%へ下げた。強カードとしての差は残るが、実質必須エンジン性は大幅に弱まる。
- 50%はW2500 10%で65%との差が小さい一方、W1500到達90%、Highest P50 1796まで下がるため、現時点では65%より削りすぎの兆候がある。
- これは保存済み250Wave checkpointの下方介入診断であり、弱体化後に新しく生じる細かな停止Waveや長期再構築を完全再現しない。正式判断前には候補を通常30 trialで再実行する必要がある。
## 2026-10-04: プレイ画面を新カード/新DP/個体装備候補へ切替

- ユーザー選択は「新カード・新DP・個体装備の候補版」。旧W10000の仮カード/DPを現行Mainから除く。
- 正式balance採用ではなく、既存newカードプローブとBC DPの手動接続。旧formal・D/E・後半診断baseline・CardValueを上書きしない。
- 未完成機能を旧効果で黙って代用しない。Relic Apotheosisは全遺物計算接続まで自然候補から除外。接続境界は`NEW_W5000_PLAY_CANDIDATE.md`に記録。
