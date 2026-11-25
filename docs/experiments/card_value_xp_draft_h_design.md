# Shadow CardValue v0.1: XP追加DraftのH内価値 修正設計

状態: **正式v1のBalanced shadow評価のXP系候補に実装済み**。旧scoreを使うゲーム本体のTake/Reroll/Refine、Encounter Conditional PE、Power Up / Rapid Fireの既存PE、`terminal_pe`非加算は維持する。XP候補以外に由来する間接的なXP増分は従来のshadow経路のまま（この段階で既存Combatカードの値を変えないため）。

## 1. 問題と計算境界

現在の`scripts/card_value_v01.py`は、候補とbaselineのXP残高・Lvを固定H上で追跡する一方、最初に`active_extra`が生じた時点だけ`_draft_value(..., horizon=1.0)`を計算し、以後その同じ値を`active_extra / len(H)`として足している。これでは後から生じるDraftをそのWaveのプールで評価できず、将来解禁や候補取得後の合法性、カード効果が発揮される残り遭遇区間を直接検査しにくい。

Hは現行の`predict_run_end`が**候補取得前のbaseline**から得た`forecast.frames`（失敗した最後の敵を含む）とし、全候補共通に固定する。`N_H = len(frames)`。候補によって終端Waveを延長しない。候補とbaselineのXPは**同じH内で、撃破成功が予測されたWaveだけ**加算する。初期位相`phase="xp"`の既払いCost/未増分Lvは現行`_start`で一度だけ正規化し、今選んでいるDraftを将来Draftに数えない。

## 2. Draft発生Waveの予測と対応付け

本体の順序に合わせ、Wave `w`の戦闘前SnapshotからXP獲得量を求め、撃破後に保証カード取得イベントを記録してからXPを加算し、`CARD_COSTS[level]`を満たす限り連続でLvを進める。現行forecastの未取得カード・ランダム装備を確定取得として適用しない。候補側は現行の`candidate_run/full_snap`に基づくXP増分を使う（Quick Learnerの3秒成否も現行戦闘関数）。Cost配列の上限を越えない。

正規化された開始Lv以降の**Lv番号`j`**について、`t_b(j)` / `t_c(j)`をbaseline / 候補側でそのLvのDraftが発生する撃破Waveとする。H内に発生しなければ`∞`。同じWaveの複数Lvは別の`j`として全件記録し、Lv番号を挟んだ差分を「1 WaveにDraftが1件」と丸めない。失敗WaveにはXP獲得もDraftもない。

```text
V_b(w) / V_c(w) = baseline / 候補側それぞれのWave w時点の予測状態と
                  合法カードプールからDraftを1回得た場合の、
                  H全体で正規化した期待・未加重PE
V_b(∞) = V_c(∞) = 0

xp_pe(c) = Σ_j [ V_c(t_c(j)) - V_b(t_b(j)) ]
```

同じLvが候補で早く、baselineで遅く取得される場合も、**早期取得の残りH価値から後期取得の残りH価値を引く**。両者が同じWaveでも、それぞれの状態・合法プールにより期待価値が違えば差を残す。baselineがH内で追い付かなければ早期取得の価値だけ、候補が遅延させれば負にもなる。これにより`active_extra`の継続期間を二重に数えず、途中の解禁・プール変化も時点ごとに評価する。候補カードが既所持uniqueになるなどの**状態依存のDraft機会価値差もXP軸**へ帰属させる。

診断にはLv番号、candidate/baseline取得Wave、各`V`、両者の差、`N_H`、プール署名/合法カード件数を記録する。`expected_drafts`はbaseline予測の件数として維持し、XPの追加/前倒しDraft数は別の診断値とする。

## 3. Wave w の期待Draft価値 `V(w; c)`

`w`は**取得に至った戦闘後**のWave。したがって、カードが有効なのは`forecast.frames`のうち`wave > w`だけ。最後の撃破WaveでDraftが生じてもH内の戦闘便益は0（H外のterminal価値に転嫁しない）。失敗Waveが後にあればその戦闘は便益の対象だが、失敗Wave自身ではDraftは発生しない。

```text
raw(card, w; c) = Σ_{e∈H, e.wave>w} [
    combat_marginal_of_one_virtual_card(card, e, c)
  + owned_growth_marginal_of_that_card(card, e, c)
]

V(w; c) = E_{legal three-card hand at w}[
    max(0, max_{card in hand} raw(card,w;c))
] / N_H

total_pe = 0.60*(immediate_combat_pe + conditional_combat_pe)
         + 0.25*growth_pe + 0.15*xp_pe
```

`raw`にはCombat/Growthの**未加重**PEを使い、`CardValue.total_pe`や旧`card_score`を入れない。Power Up等の通常カードは既存のSnapshot差、Execution/Time Collapseを仮に引く場合は**現行Encounter Conditional PE関数をそのまま再利用**する。仮取得した1枚の効果だけをWave `w+1`から各遭遇に展開し、現在保有の成長エンジンやその1枚に伴う、既に予測済みの決定的な撃破/取得イベントの寄与が計算できる場合はraw内に含める。その寄与を外側の`growth_pe`に再加算しない。仮のXPカードがさらにDraftを生む再帰、未知の将来カードの相乗効果、将来のランダムWeapon/Relicはrawへ入れない。再帰未評価なら診断と低いconfidenceで明示する。

`V_b`/`V_c`計算の仮カードは**各時点の局所コピー**にだけ適用し、元のbaseline/candidate trajectoryに残さない。Lv `j`が同Waveに複数回起こる場合も、それぞれ独立したDraft機会として評価する。**未来Draft同士の依存はB案では追わない**。先の仮カードが次のプールから消えるという具体的な系列は予測しない。未知のunique取得による後続プールの縮小は上振れ要因として明記し、必要なら後で非系列の占有率校正を行う。既所持のuniqueは確実に除外する。

### プールと3択

- Wave `w`の撃破後に、カードプール専用の状態コピーで`kills=w`、解禁判定用の到達Waveを`w`まで進める。`rarity_chances`と`available_cards`を使用し、既所持unique、`disabled_card_keys`、`allow_overdrive=False`、unlock_waveを反映する。**戦闘Snapshot用の`permanent.max_wave`は凍結したまま**にし、プール用コピーの進行を通じて将来遺物Powerを増やさない。W100の既存の確定遺物だけは現行forecastの扱いを維持する。
- `draw_hand`・`choose_card`・本体RNGは呼ばない。本体の3択で同一カードが手札内に重複しないこと、指定レアリティが空ならR→U→Cへフォールバックすること、starter時の安全カード制約を決定的な期待値演算に反映する。厳密列挙または同等の有限DPを使い、レアリティ→残カードからの一様抽選→3択の最大rawを計算する（手札順は結果に影響しない）。空プールや有効カード不足時は存在しない候補を補充せず、診断statusに記録する。
- 正式v1に一般的な「カードAを所持するとBが排他」となるルールは`available_cards`にはない。ここでいう排他は**既所持unique、設定によるdisabled、Overdrive条件、手札内の重複除外**を指す。未知の相互排他ルールを追加しない。予測済みの保証報酬は取得イベント数だけを記録し、どのuniqueを取得したかは仮定しない。

## 4. 変更境界と受け入れテスト（確認後に実装）

変更箇所は`scripts/card_value_v01.py`のXP系候補のXP軸に限定した。`predict_run_end`の固定H/装備予測、候補のImmediate/Conditional/Growth、本体`scripts/simulate_first_prestige_v1.py`の選択分岐・RNGは変更していない。XP用の局所ヘルパー、Lv別診断、`scripts/test_card_value_xp_drafts.py`を追加した。XP系候補では従来の初回Draft値キャッシュと`active_extra / N_H`を上記イベント式へ置換した。

| # | 検査状態 | 合格条件 |
|---:|---|---|
| 1 | XP Cost閾値の直前/直後（`phase="xp"`既払い状態も含む） | 追加/前倒しDraftのLv番号・発生Waveが正しい。両経路が同WaveにLv-upしても各々の状態・合法プールから計算した差を用いる。現在選択中のDraftを再計上しない |
| 2 | 1回の撃破XPで複数Lv | Waveは同じでも各LvのDraftを別件記録し、対応するcostを順番に控除。`Σ_j`と診断件数が一致 |
| 3 | `CARD_COSTS`配列末尾 | 最終LvのDraftは最大1件。上限到達済みなら追加価値0で、配列外参照/無限ループなし |
| 4 | 同一合法カードプール・同じ仮カード効果・固定Hの序盤/終盤イベント | 序盤`V` > 終盤`V`。`w=end`なら0。プール変化がある一般状態に**無条件の序盤優位は要求しない** |
| 5 | 既所持unique、disabled、Overdrive不可、手札内の重複禁止、unlock境界 | 非合法候補の期待値寄与が0。`w`で解禁するカードはその時点のプールに入り、以前は入らない。具体的な未取得カードを所持扱いにしない |
| 6 | 同一baseline forecast、評価候補順のみ変更 | `xp_pe`・各Lvの取得Wave・診断・`total_pe`が候補keyごとに一致。入力stateとglobal RNGが不変 |
| 7 | 同一seedでshadow OFF/ON、XP候補が実際にshadow評価されるRun・複数attempt・強制選択 | 全カード選択列（Reroll/Refineを含む）、RunResult/TrialResultの全フィールド、変更可能なRun/Permanent state、開始/終了時のゲームRNGとglobal RNGが完全一致。診断だけ増える |
| 相殺 | 同じLv、同じ取得Wave、同じ予測state・合法プール | baselineとcandidateのDraft期待値が完全一致し、当該Lvの`xp_pe`寄与は厳密に0 |
| 前倒し統合 | 候補のLv20 DraftがW600、baselineの同Lv DraftがW700、共通Hの末尾がW900 | `xp_pe=V_c(W600→900)-V_b(W700→900)`。合法3択だけを使う独立した全後続EncounterのSnapshot差分計算と照合 |
| 回帰 | Execution / Time Collapse、Power Up / Rapid Fire | 前回の合格ゲートのConditional/Immediate値と順位は変わらず、terminal PEはTotalに入らない。XP追加Draftは`growth_pe`へ重複しない。全テスト通過 |

**判定の補助検算:** 追加Draftが1回だけWave `w`で起き、比較側がH内では起きない人工ケースで、`xp_pe`は `Σ_{e.wave>w} raw_per_encounter / N_H` の3択期待値と一致することを、実装とは独立した小さい手札の手計算で検証する。異なるWaveに複数Lvが出るケースでは初回のDraft値の再利用がないことを確認する。
