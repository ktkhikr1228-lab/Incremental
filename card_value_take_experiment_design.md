# Balanced Standard CardValue v0.1: Take-only PE実験モード設計

状態: **Take-only PEモードと対比較runnerを実装済み**。`scripts/simulate_first_prestige_v1.py`のBalanced Standardに限る。既定は`legacy`。現行の戦闘・CardValue PE算出・Game RNG・Take以外の行動価値は変更しない。10組の初回診断は [`output/card_value_take_pilot_10.md`](output/card_value_take_pilot_10.md)。

## 1. モードと判断境界

- `--take-mode {legacy,pe}`（既定`legacy`）。`legacy`は現行のカード選択と同一。`pe`は**Takeが選ばれた後の最終手札内のカード順位だけ**`scripts/card_value_v01.py`の`total_pe`で置換する。正式版の一括実行ではBalanced行だけPE対象とし、Damage/Synergy行はどちらのモードでも旧ロジック。Variant D/Eで`pe`指定は起動時に拒否し、暗黙の部分適用をしない。
- Rerollの回数・除外集合・停止閾値`1.10`と最良候補の判定は従来の`card_score`のまま。PEはRerollを止めるかどうかに使用しない。
- Refine（溶解）は最終手札の**legacy最良候補のlegacy score**と現行`0.55`閾値で判定する。Refineなら従来どおり手札から溶解カードを選び、PE Takeを実行しない。PEで選ばれたカードのlegacy scoreでRefine判定をやり直さない。
- `spend_card_points`のUpgrade対象・購入可否・Point消費は従来の`card_score * owned_count`。PE選択の結果所持カードやPoint残高が変わった**後**は、同じ旧関数を現在stateに対して実行する。PEでUpgrade先を選ばない。
- starterの安全候補集合、forced rarity/cardを含む手札生成、Reroll禁止、Refine禁止、既存の自動化・操作時間・所持数・uniqueのルールは現行のまま。PE評価・fallback判定・順位付けの対象はその最終手札の`eligible`のみ。Take不能カードは評価しない。

```text
draw/reroll exactly as legacy, retaining the final hand and eligible candidates
legacy_winner = first argmax card_score over final eligible (hand order tie-break)
if legacy_refine_condition(legacy_winner):
    dissolve exactly as legacy; run legacy spend_card_points; log Refine
else:
    if take_mode == pe and every eligible card has valid comparable total_pe:
        take_winner = first argmax total_pe over final eligible
        decision_source = pe
    else:
        take_winner = legacy_winner
        decision_source = legacy or fallback_legacy
    record_card_decision / acquire_card / legacy spend_card_points
```

`legacy`モードでも、分岐ログを要求した場合のみ合法Take候補のPEを診断として計算してよい。その計算結果は判断に用いない。PEモードはshadow CSVの有無・候補件数上限から独立して最終手札の**全合法Take候補**を評価する。同一判断につきbaseline `predict_run_end`を一度だけ作り、対象候補に同じH・phaseを渡す。既存shadow CSVが有効なら結果を再利用して重複計算を避けるが、CSV行数制限でTakeの候補評価を打ち切らない。

## 2. 未対応・評価不能時の明示的なフォールバック

現在の`TARGET_KEYS`は55カード全種をカバーしない。**一部だけPE、残りをlegacy scoreで順位付けしない**。最終手札の**合法Take候補`eligible`**に1枚でもv0.1対象外があれば、その手札のTake順位全体をlegacyへ戻し、`fallback_reason=unsupported_card`と対象keyを残す。同様に合法候補の予測失敗、評価例外、`total_pe=None`（例:Encounter換算不能）、NaN/∞、共通H不成立なら、**合法候補の順位全体**をlegacyへ戻し、理由とカードkeyを記録する。starter制約等でTake不能なカードは未対応・無効値でもfallback原因にせず、PE評価関数を呼ばない。PEの`prediction_confidence=low`は数値が有効なら判断対象に含め、低信頼であることをログへ残す（lowを禁止するとv0.1の有効比較がほぼ成立しない）。この判定範囲は2026-09-26に変更を決定。過去の10組のJSONLは**全提示カード判定**の結果として保存する。

`total_pe`は`0.60*(Immediate+Conditional)+0.25*Growth+0.15*XP`の既存値をそのまま使う。未校正の`terminal_break_probability_delta`や`terminal_pe`は順位に入れない。未知カードを暗黙に0 PE、旧scoreをPEへ擬似換算、常にレアリティを優先、といった混合尺度を採用しない。PE Takeの適用率（全Take判断に対する`decision_source=pe`割合）とfallback内訳を集計して、結果が全カードへ一般化できないことを測定可能にする。

## 3. 同seedの対比較

2モードを**同じ整数seed、同じSimConfig、同じtrial_index、同じBalanced/PO条件**から別々の`random.Random`インスタンスで開始する。現行のBalanced seed導出（`seed + 1_000_000 + trial_index`）を両モードで維持する。比較対象のtrialは順番にIDで対応付け、成功試行のみへの条件付けで組を落とさない。`--workers 1`をログ付き実験の初期条件とし、複数worker由来のグローバル診断行の混線を防ぐ。

CLI:

```text
--take-mode legacy|pe             # 既定legacy。既存コマンドの結果は不変
--take-branch-output PATH         # 選択分岐のJSONL。ログONでも判断/RNG不変
python3 scripts/run_card_value_take_experiment.py --trials 10 --max-attempts 10 --seed 20260828
                                  # paired balancedを両モードで同seed実行
```

比較runnerはtrialごとに独立したRNGを2個生成して各モードを順に走らせ、両ログとtrialペア集計を別ファイルへ保存する。代わりに上記`--take-mode`で同じ`--seed`/`--trials`を2回実行したログも、後から`(seed, trial_index, allow_overdrive)`で結合できる。PE選択が初めて異なった後は、Run state、手札、乱数の**消費回数と到達位置がずれ得る**。同seed比較は共通の初期条件による対比較であって、分岐後のRNG状態や手札の一致を要求するものではない。一致すべきなのは、両モードで同じ判断が続く**最初の分岐まで**と、モードを`legacy→legacy`とした再現実行である。

ペア集計: 試行ID、両modeの成功/死亡/到達Wave/プレイ時間/RunResult・TrialResult、最初の異なるTake（attempt、wave、phase、choice ordinal）、PE適用件数、fallback率と理由、Reroll/Refine/Upgrade件数。進行経路が分岐した後の同じ`wave`だけで異なる手札を「PE判断差」として直結せず、最初の因果的分岐を切り出す。

## 4. 選択分岐ログ（1 decision = 1 JSONL行）

- 識別: `run_id`（seed / trial_index / Balanced / PO / attempt）、`decision_index`（そのRun内の単調増加番号）、`next_wave`、`phase=xp|guaranteed`、`take_mode`、`forced_rarity`、`forced_card`、`starter`。Runや再試行を跨いだ同Waveの混同を防ぐ。
- 選択入力: 最終提示手札全体の`hand_keys`（順序あり）、`eligible_keys`（合法Take候補）、`ineligible_keys`（Take不能）、`evaluated_pe_keys`（Take順位付け用に実際にPE評価関数を呼んだ候補。shadow診断での呼出しは含めない）、`reroll_trace`（各手札、legacy最大score、停止理由、消費回数）、`pre_decision_rng_digest`（`rng.getstate()`の安定ハッシュ）、必要なら比較用のstate digest。Take不能カードは`pe_status=ineligible_take`としてログに残し、PE値は未評価。診断はRNGを抽選に使わない。
- 分岐: `legacy_winner`と全eligibleの`legacy_score`、各候補の`total_pe`/4軸値/予測H/信頼度/評価status（取得できた場合）、`legacy_refine_gate`と実際の`action=take|refine`、`selected_card`、`decision_source=legacy|pe|fallback_legacy`、`fallback_reason`、PE候補がlegacyと異なったか。Reroll/Refine/UpgradeでPEを使用したかの真偽値は常にFalse。
- 出力: 取得/溶解card、旧ロジックのUpgrade支出・強化対象、処理後RNG digest。既存shadow診断CSVとはファイルを分け、実際にTakeした候補と反実仮想スコアを明確に区別する。`--take-branch-output`指定時以外はログを蓄積しない。

評価が遅い場合でも「最終手札の一部だけをPE採点して残りを旧scoreで選ぶ」方式へ暗黙に退避しない。ログには評価所要時間を載せ、実行時間の上限を設ける場合は候補全件不能として明示的fallbackにする。

## 5. 実装後に必要な受け入れテスト

| ケース | 判定 |
|---|---|
| 既定/明示`legacy`、ログOFF/ON、shadow OFF/ON | 既存34テストを含め、旧選択列・RunResult/TrialResult・本体state・RNGが一致 |
| PE対象カードだけからなる同一最終手札、旧1位とPE1位が異なる | `pe`でPE1位をTake、`legacy`で旧1位をTake。PEのtieは手札順。Combat/Growth/XP重みは既存値、terminal非加算 |
| 合法Take候補に対象外1枚、または評価不能/非有限の候補1枚 | 合法候補全体のTake順位を旧順位に戻す。fallback理由と対象keyがログに残る。異尺度を混合しない |
| starter制約でTake不能な提示カードが未対応、または仮に評価すれば無効 | そのカードのPE評価関数を呼ばず、合法候補が全件有効ならPEを適用。`hand_keys`は全提示カード、`ineligible_keys`にはそのカード、`evaluated_pe_keys`には評価した合法候補だけを記録 |
| Reroll可能でlegacy scoreが閾値未満、PEは非常に高い | Rerollの回数・対象外集合・停止タイミングはlegacyと一致（カード取得が分岐する前の同一stateで比較） |
| 最終手札にlegacy Refine条件成立、PEで高いカードがある | 旧Refineが起きる。逆に旧Refine条件が不成立ならPE選択カードのlegacy scoreが低くてもRefineしない |
| Card Pointがある状態でPE Takeにより所持カードが変わる | Upgradeは新しい所持stateに対する**従来の**`card_score * owned_count`、Cost・操作時間も従来式 |
| starter/guaranteed/forced choice、POあり/なし | 従来のeligibleと手札制約に従い、同じ共通H/正しいphaseでPE評価 |
| 同seedで`legacy`を2回、`pe`を2回、および両モードのペア | 各モード内では全結果・分岐ログ・RNGが再現。モード間は最初のTake差まで同一入力/RNG、差後のRun・RNG一致は要求しない |
| PEモードでshadow診断上限0・小・大 | Takeの評価候補集合と実選択が同一（shadowの行数制限は選択に影響しない）。PE評価そのものは状態とゲームRNGを変更しない |

実験結果にはPE適用率とfallback率を必ず併記し、全カード共通のPE運用成績と誤読しない。Take以外の旧判定が混在することもモード名・ログに残す。

## 6. 最初のパイロット: 同seed・10 trialペア

実装・受け入れテスト通過後、**Balanced / POあり**の`trial_index=0..9`を固定seedから`legacy`/`pe`の2モードで別々に実行する（10組・合計20 trial）。`workers=1`で全選択分岐ログを採取し、同一seed/設定とtrial IDを記録する。探索的な小規模比較なので、この10組だけで強さやバランスの優劣は判定しない。POなしやVariant D/Eへ結果を外挿しない。

旧仕様の初回実施済み: seed `20260828`、`max_attempts=10`、10組。**提示された全3枚**をフォールバック判定に含めた当時の集計はPE適用54/1477（3.7%）、fallback1423/1477（96.3%、すべて`unsupported_card`）、最初の選択分岐8/10組。詳細は上記レポートと同名の`.json`・`_branches.jsonl`を参照。**新仕様の10組は別prefixの [`output/card_value_take_eligible_pilot_10.md`](output/card_value_take_eligible_pilot_10.md) に実施済み**: 180/1477（12.19%）、fallback1297/1477（87.81%）、最初の分岐9/10組。旧ログからの合法候補限定12.19%の推計と同じ数値になったが、反実仮想が分岐後のRunを正しく再現したと解釈しない。

パイロット結果は次の**5項目を一つの対比較レポート**で確認する。

1. **PE適用率:** `decision_source=pe`のTake件数 / PEモードでRefineにならなかった全Take判断件数。分母は各Run・全attemptの合計を使う。候補が全件対象でも診断エラーになった判断は適用数へ入れない。trial別件数・率も併記する。
2. **fallback率・理由:** `fallback_legacy`のTake件数 / 同じTake判断件数。`unsupported_card`（カードkeyも集計）、forecast失敗、`total_pe=None`、非有限値、その他評価例外を**理由別・trial別**に集計。PEモードのBalanced Takeが`pe`/`fallback_legacy`のどちらにも分類されなければログ不備として調査する。
3. **最初の選択分岐:** 各trialで両modeの`(attempt, decision_index, wave, phase)`を最初から照合し、最初に**実際のaction/選択カード**が異なる行を提示。`legacy_winner`、PE選択、final hand、Reroll経路、legacy Refine判定、RNG/state digestを添える。差がないtrialは「分岐なし」とする。最初の差より後の同Wave行を同じ意思決定として直接比較しない。
4. **分岐時のPE内訳:** 最初の分岐の**全eligible候補**について`legacy_score`、Immediate/Conditional/Growth/XP/Total PE、baseline H/終端・信頼度、`terminal_break_probability_delta`（診断のみ）、評価status・fallback理由を同一表に置く。PE採用候補とlegacy採用候補を明記し、`total_pe`の合成が60/25/15を各1回だけ使っているか検算する。PE適用によらない分岐なら原因を別記する。
5. **明らかに変なTakeの点検:** PE適用の全件を、合法性（starter/unique/排他/forced制約）、有限値・最大`total_pe`の選択、H最終WaveでのXP追加Draft価値0、余裕戦でTime Collapseが不自然に高くないか、壁付近のExecution/Time Collapse、XP候補のLv別Draft Waveとプール、負の効果や未校正terminalの加算漏れで確認する。特に最初の分岐とPE順位差が大きい上位例を手動で読む。`red_flag`はdecision ID・全手札・軸別値・予測理由を付けて列挙し、値が想定どおりでも**モデル未校正による違和感**と**実装上の誤り**を区別する。

完成条件は10組すべてのpaired logと5項目の集計が揃い、理由不明のfallback・不正なTake・shadow/評価によるRNG消費がないこと。PE適用率が低い場合はその事実と対象外カードの内訳を主結果として扱い、少数のPE適用例から全体のRun成績を断定しない。
