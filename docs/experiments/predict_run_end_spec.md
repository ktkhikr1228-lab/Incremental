# `predict_run_end(baseline_state)` 仕様案

状態: 実装前の設計案。対象は `scripts/simulate_first_prestige_v1.py` の Balanced Standard。コード・既存仕様は変更しない。

## 1. 契約と出力

入力はカード選択開始時点の `RunState`、`PermanentState`、`SimConfig`、`next_wave`、選択時点のフェーズ情報。候補カード、Reroll結果、Refine結果は入力しない。**一判断につき一度だけ**baselineの予測を作り、すべての候補へ同じ予測期間を配る。入力状態とゲームRNGを変更せず、乱数抽選を行わない。

```text
RunEndForecast {
  status: ok | uncertain | invalid
  predicted_end_wave: int                  # 最後に試みるWave。失敗なら失敗Wave
  end_reason: failed_battle | prestige | fallback_next_encounter
  last_killed_wave: int                    # 失敗時はpredicted_end_wave - 1
  remaining_encounters: int                # next_wave..predicted_end_wave（両端含む）
  remaining_normal_encounters: int
  remaining_boss_encounters: int           # 10の倍数。ただしBig Bossを除く
  remaining_big_boss_encounters: int       # 100の倍数。Boss合計は両者の和
  remaining_xp_gross: float                # 成功撃破からH末までに得る期待XP
  remaining_xp_balance: float              # 現在の未消費XP + gross - 将来支払うXP
  remaining_xp_levelups: float             # 期待追加通常Draft数（将来の保証取得は除外）
  remaining_guaranteed_cards: dict         # 未到達の25/100/500/2500の期待取得
  remaining_card_acquisitions: float       # 通常Draft + 確定取得の期待数
  remaining_growth_events: dict           # 10kill、Boss、quick kill、Tier等
  expected_combat_seconds: float
  frontier: {wave, time_limit, enemy_power, margin, ttk, reason}
  checkpoints: list                       # 固定順序の少数の診断状態
  confidence: high | medium | low
  assumptions: list[str]
}
```

`remaining_encounters`は**撃破しなかった最終敵も1体の戦闘遭遇に含む**。XP・ドロップ・撃破時成長イベントは撃破したWaveだけを数える。`remaining_xp_balance`は終了時の残XPであり、`remaining_xp_gross`とは別。即時のカード選択に使われたXPを再び支払わない。

## 2. 入力境界とbaselineの意味

`run_once` はWave撃破後にマイルストーン確定選択を行い、その後にXPを得てLevel-up選択を行う（`simulate_first_prestige_v1.py:1805–1822`）。通常選択はXP Costを差し引いた後、`run.xp_level_count += 1` より**前**に `choose_card` が呼ばれる。評価入口で「現在の選択が完了した後」の正規化baselineを作り、既払いコストの再控除や同じ報酬の再発火を避ける。

- 現在の選択はカードを取得しない仮想no-opとして決済する。候補カードを加えず、`run.xp_level_count` の未反映増分だけを反映する。確定選択では対応する処理済み印を反映する。phaseは明示引数とし、推測しない。
- baselineのカード数・タグ数・強化段階・素材・装備・XP・既存スタックは実状態からコピーし、過去に獲得した成長効果を初期値に含める。
- 予測区間は戦闘直前の `next_wave` から開始。候補の取得・強化・溶解をbaselineに混入させない。
- 終了Waveは`config.target_wave`を超えない。現在既に最終戦闘後なら残遭遇0としてprestige完了を返す。

将来のドラフトを特定カードとして確定所持にしない。後続の**カード取得イベント数**は期待値でモデル化し、現在所持しているGrowth Engine / Accelerated Learning等を進める。将来選ぶカードの新規効果を表現するなら、別途校正済みの「候補とは独立した期待ドラフトモデル」を適用する。未校正時は0と明記し、成長イベントのカード取得件数だけを入れる。これによる生存期間の過小予測はconfidence/校正で検出する。

## 3. 決定的なbaseline rollout

Waveは1から走り直さず、現在状態から順に予測する。各Waveの処理順は本体 `run_once`（同`:1717–1822`）に合わせる。浮動小数点の期待値で実カード枚数・Tierを直接表現するとfloor・unique・thresholdが壊れるため、**カード所持は離散値のまま**、期待カード取得数・成長カウンターのみ別の小数予測値として管理する。Snapshotに小数の`run.counts`を渡さない。

```pseudo
predict_run_end(baseline, phase, config):
    s = normalize_after_current_decision(copy(baseline), phase)
    forecast = empty_forecast(next_wave)
    for w in next_wave .. config.target_wave:
        pre = forecast_snapshot(s, boss=(w % 10 == 0), w, config)
        T = enemy_time_limit(w, s.counts["glass_cannon"])
        P = configured_enemy_power(w, config)
        ttk = time_to_kill_with_defense(w, P, T, pre.snapshot,
                                        pre.effective_log_dps, config)
        if reward_preserving_skip_applies(w) and ttk is None:
            ttk = T             # 本体と同じ「保証突破、quick扱いなし」
        record_encounter(w, ttk, pre)
        if ttk is None:
            return finalize(failed_battle, w, last_killed=w-1)

        quick = (ttk <= 3.0)
        s.kills = w
        apply_expected_boss_and_equipment_events(s, w)
        apply_existing_card_growth(s, w, pre.snapshot, quick)
        apply_expected_relic_events(s, w)
        apply_guaranteed_reward_event(s, w)   # 固有カードは勝手に選ばない
        xp_gain = expected_xp_from_pre_fight_snapshot(s, w, pre.snapshot, quick)
        record_xp(xp_gain)
        advance_expected_normal_drafts_and_existing_engines(s)
        record_checkpoint_if_relevant(s, w)
        if w == config.target_wave:
            return finalize(prestige, w, last_killed=w)
```

### 3.1 反映する現在保有カードの成長

- `escalation`: 現行`compute_snapshot`が`progression_wave(run.kills)//10 * 現在枚数`で計算するため、その式どおり現Wave時点の全累積撃破数を反映する。カード取得時点以前の撃破数も式上は寄与するので、予測側で勝手に「取得後のみ」へ変更しない。
- `growth_engine`: 後続カード取得イベントで`growth_units`を進める。取得自身の成長は現在のRunStateに既に記録済みなら再加算しない。
- `accelerated_learning`: 後続カード取得イベントで`accelerated_units`を進め、以後のXP倍率を更新。今回選択をno-opとするbaselineでは今回の取得イベントを発生させない。
- `boss_devourer` / `boss_assimilation`: 10の倍数の**成功撃破後だけ**スタック/Power加算。Boss戦自身の判定には使わない。
- `perfect_overdrive` / `momentum`: 戦闘前の所持状態と`ttk <= 3`で更新。Momentumは次戦闘への状態として更新。
- `critical_singularity` / `recursive_follow_up` / `infinite_barrage` / `knowledge_collapse`: 戦闘前Snapshotの対応Tierで撃破成長ログを進める。floorは**離散Snapshot値に対してのみ**使う。
- `limit_break` / `limit_shatter` / `exponential_core` / `final_equation`等の既取得カード効果は`compute_snapshot`の通常経路で適用。候補未取得のLegendaryは入れない。

本体の`compute_snapshot`は`permanent.max_wave`や武器・遺物状態を参照する。baselineの将来状態コピー上で到達Waveを進め、装備・品質の期待更新方針を固定する。`snapshot_cache`の使用時は`run.effect_version`だけでなく予測成長ログ・XP・装備・`permanent.max_wave`の変化で正しく無効化する。まずは毎イベント境界で再計算する仕様とし、キャッシュは測定後に最適化する。

### 3.2 XP / Draftの期待値

戦闘前SnapshotのXP倍率で、通常敵は`general_xp`、Bossは`boss_xp`を使う。本体の`base_xp = 1 + (progression_wave(w)-1)//10`、Boss×3 / Big Boss×10、quick時のQuick Learner、および`progression_units`を反映する。XPは成功撃破後に入り、`CARD_COSTS`を超えた分は持ち越す。

通常Draftの取得確率・溶解確率・Reroll方針をどう予測するかは明示する。初期設計案は過去baselineログのWave帯別標準型の`P(take | normal draft, state band)`を固定テーブル化し、想定取得件数を成長イベントへ反映する。確定取得は別イベントとし、候補の効果式は増やさない。強化・溶解Pointの将来消費はこの予測では仮計上しない。追加XP由来の追加DraftイベントはXP軸へ帰属し、Growth軸で同じイベントの価値を二度足さない。

固定テーブルがない場合、通常Draftは「選択機会を1回得たがカード未確定」として**イベント件数の上限1**と下限0を併記し、一本の精度の高い予測だと偽らない。Baselineの成長効果を0とみなしてはならない。

### 3.3 武器・遺物・報酬の期待値

現在装備/既解禁/品質をそのまま開始状態とする。ラン内の将来武器取得、遺物drop、炉利用、確定報酬を乱数抽選・実際の取得カードとして処理しない。固定報酬（初回W100の遺物など）は既取得フラグを参照する。確率報酬は既存Drop率と品質分布から期待Power/品質を**別の予測状態**に加えるか、上下界のシナリオを計算する。期待Powerを直接`weapon_power`や`relic_quality`へ代入する方式は、装備の最大値選択や非線形な強化と整合しない場合があるので、確率×離散結果の期待値で計算する。

v1 formalは平均武器/遺物曲線で後半Powerを表現している。将来`permanent.max_wave`・装備基礎Power・品質の更新を止めると失敗Waveを過度に早める。装備期待モデルを校正できない場合は`status=uncertain`とし、確定値だけで遠方の終了Waveを断定しない。

## 4. `predicted_end_wave`の決め方と不確実性

本体と同じ撃破可否（`time_to_kill_with_defense`）で最初に失敗するWaveを探す。戦闘HP Powerだけの線形閾値で判定しない。`reward_preserving_skip_end`以内は本体同様の保証突破を適用する。リスク評価用に最初の予測失敗Waveの戦闘前Snapshot、敵Power、制限時間、TTK、余裕をfrontierへ保存する。

期待成長や装備の近似で終了Waveが揺れる場合、同じ**決定的**なlow/central/highシナリオで終了Waveの区間 `[end_low, end_high]` を推定する。centralが未校正か、区間幅が広く候補比較の順位が変わるときは`status=uncertain`。重要: 不確実だからという理由で100 Waveへ丸めない。固定の予測期間を用いた候補間比較はcentralを使うなら全候補で同じcentral Hを使用し、信頼度も共通に記録する。

## 5. H外のRun延長: terminal/continuation PE

Hはbaselineから固定する。候補によってH内で戦闘を突破しやすくなり、baseline予測では失敗したfrontier Waveを越える価値だけは、**Hを候補ごとに変更せず**追加の`terminal_pe`で評価する。

```text
F = baseline forecastの最初の失敗Wave
r0 = P(baselineがFへ到達)
r1(c) = P(候補cがFへ到達)
q0 = P(baselineがFを突破 | Fへ到達)
q1(c) = P(候補cがFを突破 | Fへ到達、固定H内イベント予測)
delta_pass(c) = r1(c) * q1(c) - r0 * q0

terminal_pe(c) = delta_pass(c) * continuation_opportunity_pe(F)
```

`q`は決定的な連続余裕・離散TTKから校正した滑らかなゲート関数を使う（例: `sigmoid(margin / tau)`）。これは追加RNGを使わず、境界付近で0/1に跳ばないための近似であり、`tau`は既存同一seed試行で校正する。`r`はFより前のボトルネック遭遇の生存ゲートを使って近似し、候補による早期失敗を無視しない。Defense/Armor Break有効時は単純HP marginではなく、戦闘可否を反映した専用ゲートを使う。途中の敵に候補だけが失敗する場合は`r1 < r0`となり負のterminal値を許す。

```text
continuation_opportunity_pe(F) =
    {0.60 * combat_opportunity_raw(F..J)
   + 0.25 * growth_opportunity_raw(F..J)
   + 0.15 * xp_opportunity_raw(F..J)} / N_H
```

ここで`J`は**次の実在の構造的な区切り**（次Boss、次の確定カード報酬、targetのうち最初）で、固定Wave幅ではない。各raw値は「Fで終了した場合」対「Fを突破してJまで進めた場合」の、候補に依存しないbaseline継続状態で得る追加機会の未加重PE総量。戦闘は敵Powerの増分・到達余裕、Growthは現在保有エンジンの増分、XPは新たなDraft機会を同じPEへ換算し、既にHで計上したイベントを含めない。`N_H = remaining_encounters`は全候補で共通。XPの追加Draftはこの式のXP rawへ**一度だけ**帰属する。`CardValue.total_pe`をraw値に代入しない。

`terminal_pe`は**ウェイト適用済みPE**として返し、`selection_total_pe = CardValue.total_pe + terminal_pe`で比較する。`CardValue`自体のCombat/Growth/XPを伸長分で再評価しない。継続機会は候補と独立で、候補のFまでの効果による到達確率の変化だけがcandidate dependent。次の構造区切りの先の長期価値は中規模近似では数えず、過大な複利を避ける。

Fがtargetで、baselineが失敗する場合はJ=targetで通常継続区間は0となる。このときのみ、第一転生達成の機会価値`prestige_completion_pe`を別途校正し、`delta_pass * prestige_completion_pe`をterminalに使う。値が未校正なら0と診断付きで返し、勝手な定数を置かない。baselineがtargetまで成功する予測ならRun延長のterminalは0。

**重要な尺度条件:** `continuation_opportunity_pe`の各raw値はH内のCombat/Growth/XPと同じ「遭遇1回あたりの期待余裕差」に正規化し、H内利益の再計上をしない。追加遭遇の存在自体には自然なdamage差がないため、継続による進行をPEへ変える係数（`combat_opportunity_raw`等）は**未決の校正量**。これを定められない間はterminalを0/uncalibratedとし、任意のWave数をPEへ変換しない。単純な`predicted_end_wave(candidate)-predicted_end_wave(baseline)`をPEへ足さない。

## 6. 予測不能時の安全な代替（100 Wave固定は禁止）

予測が非有限、装備期待モデル未校正、必要なカード取得モデル欠落、計算予算超過などで終了Waveが確定しない場合:

1. **局所的に検証できる範囲だけ**で`next_wave`の戦闘前状態・敵条件を評価する。これさえ計算不能ならCardValueを無効扱いにし、旧scoreへ無言で切り替えない。
2. 既知の次戦闘を`fallback_next_encounter`（H=1）として全候補へ同じ期間を設定。将来Growth/XPに関する値は0とするのでなく`unknown`と診断に記録する。利用可能なlow/highシナリオがあれば候補ごとの値の区間を示し、最良候補の下限が他候補の上限を超える場合だけ確定順位とする。
3. `terminal_pe`は校正可能な場合だけ使う。frontierが不明なら0/unknownとしておき、過大な継続価値を捏造しない。
4. 区間が重なり順位を決められない場合のonline暫定方針案: 検証済みの次戦闘の限界価値だけで選択し、同値ならカードkeyの辞書順で決定する。Reroll・Refineは将来機会価値を確定できない限り実行せず、現手札の取得を優先する。これは低信頼の保守的な行動であり、正式なBalance判断として集計する際は別群に分ける。
5. 使用したstatus、理由、失われた評価軸、low/highの範囲を必ずログへ出す。この代替の適用率が高ければ正式校正を止めて予測モデルを修正する。

代替は**観測済みの次戦闘という構造境界**であり、100 Waveや恣意的な固定幅の安全弁を設けない。

## 7. 再利用・新規関数・性能

既存再利用: `compute_snapshot`, `dynamic_damage_log`, `time_to_kill_with_defense`, `enemy_time_limit`, `configured_enemy_power`, `progression_wave`, `progression_units`, `CARD_COSTS`, `rarity_chances`, `available_cards`, `reward_preserving_skip_end`, `sweep_time_multiplier`。Boss/XP/成長イベントの処理順は`run_once`を参照するが、乱数を消費する`process_boss_loot`、`choose_card`、`acquire_relic`等を予測中に直接呼ばない。

新規: `normalize_after_current_decision`, `forecast_snapshot`, `advance_expected_xp`, `advance_existing_growth`, `expected_acquisitions_by_wave`, `expected_equipment_outcomes`, `predict_baseline_run_end`, `build_frontier_gate`, `continuation_opportunity_pe`, `estimate_terminal_pe`。

最長でも残りWaveまでの線形走査。複数候補ごとにbaselineを再計算せず、判断単位にキャッシュする。遠方のEncounterは成長・XP・Boss・装備が変化しない区間をまとめられるが、敵Powerが変わる区間の最初の失敗を飛ばさないこと。計算予算到達時は`uncertain`を返し、100 Wave固定にフォールバックしない。

## 8. 受け入れテスト（設計上の最低条件）

| 入力baseline状態 | 期待される関係 |
|---|---|
| 次の通常敵に失敗、XP残高あり | endは次Wave、encounters=1、失敗敵のXPはgrossに含めない |
| 次が10の倍数のBoss | Boss件数1、Big Boss件数0、XPは撃破時のみBoss倍率 |
| 次が100の倍数のBig Boss | Boss件数0、Big Boss件数1、XPは撃破時のみBig Boss倍率 |
| Growth Engine所持、後続通常Draftが複数 | 予測カード取得件数に応じ成長。未所持時より将来Damageが小さくならない |
| Boss Devourer所持、Boss撃破後に次へ進む | Boss自身の戦闘にはそのBoss分を乗せず、次の戦闘には乗せる |
| Perfect Overdrive所持、同じ敵を3秒以内/超で撃破 | quick時だけ次戦闘からスタックが増える |
| 選択中でXP Costは支払済み、`xp_level_count`未増分 | 同じCostを再支払せず、今回の選択を将来Draftとして再計上しない |
| 同じbaseline、候補カード順序のみ変更 | predicted_end_wave・出力件数・本体RNG状態が一致 |
| baselineがFで失敗、候補がFを突破しやすくなる | 固定Hは不変、校正済みterminal_peは正で、H内効果を二重加算しない |
| baselineの終了予測が不確実 | status=uncertain、固定100Waveを返さず、次戦闘のみの検証可能な代替を示す |

## 9. 実装前に決定すべきパラメータ

1. 将来ドラフトの取得確率テーブル・保証報酬の期待効果をどの正式v1出力から校正するか。
2. 武器/遺物取得と装備の期待更新モデル、low/highシナリオの幅。
3. XP feedbackを含む期待取得件数の収束条件、Level-up上限到達時の扱い。
4. frontierの確率ゲートの温度`tau`、候補による早期失敗の確率モデル、Defense有効時のゲート。
5. continuationのPE換算係数と第一転生達成時の`prestige_completion_pe`。未校正ならterminal=0/uncalibrated。
6. `status=uncertain`時の暫定選択方針（§6）を正式採用するか、別の決定規則を用いるか。
7. 1判断あたりの最大予測時間と、`end_low/end_high`幅に基づく信頼度判定。
