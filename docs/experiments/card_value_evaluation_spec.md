# Balanced Standard CardValue 評価システム詳細仕様

状態: 共通CardValueの将来設計仕様。正式v1ではBalancedのshadow評価だけ部分実装済みで、ゲーム本体の選択は旧scoreのまま。

baseline現在Run残り期間の予測とH外のRun延長価値の設計案は [`predict_run_end_spec.md`](predict_run_end_spec.md) に記載する。`baseline_predicted_run_end_wave` の未決事項は同文書の校正項目に従う。

§5.2および§6の全制限時間積分による条件付きカードのPE式は初期案の記録。正式v1のshadow評価で **Execution / Time CollapseだけはEncounter-based Conditional PEに置換済み**。現行の計算式と合格ゲートは [`card_value_encounter_conditional_design.md`](card_value_encounter_conditional_design.md) を優先する。

§5.4のXP追加Draft価値は、XP系候補のshadow評価でLvごとのDraft発生Waveとその後の共通Hを使う方式へ更新済み。candidate/baseline別の状態と合法プール、未来Draft非依存の前提は [`card_value_xp_draft_h_design.md`](card_value_xp_draft_h_design.md) を優先する。

## 1. 目的と適用範囲

正式v1（`scripts/simulate_first_prestige_v1.py`）のBalanced Standard評価を、タグ固定scoreから現在状態に対する限界効果へ移行する。Take、Reroll、Refine（提示カードの溶解）、取得済みカードの強化先が同じCardValue評価関数と単位を使う。Legendaryに別の係数や尺度を設けない。

別系統の `simulate_new_w5000_*.py` はカードプール・効果式が異なるため、本仕様の対象に含めない。

## 2. 共通単位と標準型ウェイト

すべての評価軸の生値をPE（Power-equivalent）で返す。1 PEは、敵HP Powerとの差を測る `log10` 戦闘余裕の1.0差に相当する。正値が有利、負値が不利。

Balanced Standardの方針ウェイトは仕様書§11のCombat 60% / Growth 25% / XP 15%とする。軸別PEはすべて**同一のbaseline stateから固定した現在Run残り期間**における、遭遇1回あたりの期待戦闘余裕差に正規化する。候補によって評価期間・分母を変えない。

```text
CombatNet = Immediate + Conditional - CombatRisk
GrowthNet = FutureGrowth + Economy - GrowthRisk
XPNet     = XPValue - XPRisk

total_pe = 0.60 * CombatNet
         + 0.25 * GrowthNet
         + 0.15 * XPNet
```

- **Combat 60%** はImmediateとConditionalの合計に一度だけ適用する。
- **Growth 25%** は時間経過・撃破・後続カード取得による成長と、資源・時間の効率価値を含む。
- **XP 15%** は追加XPによるカード取得機会の価値。XPが直接Damageへ変換される分はCombat側に帰属する。
- XPが増やす追加Draftの価値は**100% XP軸**に帰属する。そのDraftで得るカードが後続戦闘・成長に与える価値もXP軸の内部で評価し、Combat/Growth軸には再計上しない。追加Draftの期待価値は未加重PEで計算し、最後にXP軸へ0.15を一度だけ掛ける。`CardValue.total_pe`を追加Draft価値へ代入しない。
- Synergyは既に各軸へ反映した値を再加算しない。未帰属の相互作用はdiagnosticとして返すが、v1 online scoreでは加算しない。
- Riskは該当軸から差し引く。不利益が前後差分へ既に含まれる場合、同じ不利益を再度減点しない。

## 3. 戦闘価値と評価期間

### 3.1 Encounter余裕

敵条件`e`に対する候補取得前後の戦闘余裕を次で定義する。

```text
required_ratio(S) = 0.70 + 0.30 / S.execution_mult

S(e) = compute_snapshot(state_at_e, permanent, boss=e.is_boss, config)
margin(S(e), e) = S(e).log_dps
             + log10(temporal_integral(T_e, T_e, S(e)))
             - enemy_hp_power(e)
             - log10(required_ratio(S(e)))
```

`T_e`は`enemy_time_limit`で求めた敵の制限時間。`temporal_integral`の実際の引数は`(time, limit, snapshot)`。時間積分は現行のTime Collapse式とFirst Strike / Last Stand等の時間区間を含む。Boss判定ごとにSnapshotを作る。Enemy HPは`configured_enemy_power`によるPower表現（`HP=10^Power`）。積分の単位は秒で、DPSとの積がDamageになる。Defense有効構成ではHPとDefense/Armor Breakをこの単純marginへ直結できないため、別途対応式が決まるまで同式を適用しない。

候補がTime CollapseやExecutionを持つ場合、`margin`は即時`log_dps`だけでは見えない時間・要求ダメージ条件の差を反映する。離散Hit数・最小攻撃時間による実際の撃破可否と時間は、既存`time_to_kill`でも確認する。

### 3.2 予測期間H：baselineから見た現在Run残り期間

各判断の開始時に、**候補をまだ仮適用していないbaseline state**から、現在Runの終了（次の失敗または第一転生到達）までを予測する。この期間をHとして固定し、手札内の全候補、Reroll期待値の全仮想手札、Refineと強化比較で共通使用する。

```text
H = [next_wave, baseline_predicted_run_end_wave]
baseline_predicted_run_end_wave = min(config.target_wave,
                                     baselineから予測した現在Runの終了Wave)
```

予測関数は本体RNGを消費しない決定的なbaseline近似を使い、候補ごとの予測到達WaveでHを延長・短縮しない。H内の通常敵・10 Wave Boss・100 Wave Big Bossを実際の出現数で重み付けし、**全軸共通の遭遇総数**を分母とする。予測失敗Waveは戦闘評価には含めるが、撃破XP・撃破成長イベントには含めない。baselineで次の敵を突破できない予測なら、診断用に次の敵1体をHとして用いる。候補がHの後まで生存することによる利益はこの近似では含めず、オフライン校正で取りこぼしを確認する。Hは予測であってゲーム本体のRun状態を進めない。

`baseline_predicted_run_end_wave` を決める近似の詳細（敵Power、将来カード・XP、成長イベント、時間制限をどの粒度で予測するか）は実装前の未決事項。これを決めずに旧100-wave固定Hへ戻してはならない。

## 4. 共通戻り値

```text
CardValue {
  candidate_id: str
  action: take | reroll_probe | refine_probe | upgrade_probe
  immediate_pe: float
  conditional_pe: float
  growth_pe: float
  xp_pe: float
  economy_pe: float
  synergy_pe: float          # 帰属・監査値。totalへ独立加算しない
  risk_penalty_pe: float     # 軸別に配分した減点の説明値
  combat_net_pe: float
  growth_net_pe: float
  xp_net_pe: float
  total_pe: float
  diagnostics: dict
}
```

`diagnostics`にはbaselineから固定したHとその遭遇数、前後Snapshot、各Encounterの余裕・撃破時間差、予測追加カード数、Riskの帰属先、予測乱数seed、キャッシュ情報を含める。全レアリティが同じ`total_pe`尺度を使い、判断主体は常にこの値を比較する。

## 5. 評価軸

### 5.1 Immediate Combat Value

候補カードをコピー状態へ仮適用し、現在の参照敵に対する`log_dps`差を取る。

```pseudo
for encounter e in fixed H:
    S0(e) = compute_snapshot(baseline_state_at_e, permanent, e.is_boss, config)
    S1(e) = compute_snapshot(candidate_state_at_e_without_future_growth,
                             permanent, e.is_boss, config)
Immediate = sum_e(weight(e) * (S1(e).log_dps - S0(e).log_dps))
            / sum_e(weight(e))
```

現在のDP、Crit率・倍率、AS、XP余剰、所持カード、カード強化、Limit効果などはそのまま使う。候補取得後に新規発生する将来成長イベントはこの差分から除きGrowthへ送る。Boss専用効果があればEncounterのBoss比率に応じてImmediateに反映する。候補後のSnapshot差に直接出ないExecution・Time Collapse等はここに含めずConditionalで評価する。§6.1の「現在差分」はPower Upの検算用で、正式なImmediateはこの共通H平均値。

### 5.2 Conditional Combat Value

H内Encounterの余裕差を出現数で加重平均し、Immediate分を除く。

```text
combat_delta_H = sum_e(count_H(e) * (margin(S1(e),e) - margin(S0(e),e)))
                 / sum_e(count_H(e))
Conditional = combat_delta_H - Immediate
```

通常のDamage効果だけならConditionalは概ね0。制限時間、敵種別、Boss条件、時間依存効果で変わる部分がConditionalに残る。撃破可否の0/1だけでscore化せず、PE連続余裕差を主値とする。`time_to_kill`の撃破可否と時間差はdiagnosticとして記録する。

### 5.3 Future Growth Value

H内で候補取得後に発生すると予測されるイベントだけを数え、全候補共通のH内遭遇数で割って将来戦闘余裕の増分を計算する。

```text
Growth = sum_over_H_encounters(
    margin(state + candidate, after_candidate_growth_events)
  - margin(state + candidate, before_those_events)
  - value already assigned to Immediate or XP
) / count(H_encounters)
```

対象例: Growth Engineの後続カード取得数、Escalationの10体区切り、Boss Devourer / Boss Assimilationの候補取得後Boss数、Perfect Overdriveの条件成立撃破数、Legendary撃破エンジンのTier成長。既に`run.*_units`へ記録された過去分は新規候補価値に含めない。**追加XP由来の追加Draftとその後続効果はすべてXP軸**に帰属し、Growth側の予測イベントから除外する。

### 5.4 XP Value

XP量自体でなく、固定H内に生まれる追加カード選択機会を評価する。追加DraftがH内の戦闘余裕を何PE改善するかを、全候補共通のH内遭遇数で割る。Hを越える効果は評価しない。

```pseudo
baseline_drafts = forecast_normal_drafts(baseline, H)
candidate_drafts = forecast_normal_drafts(baseline + candidate, H)
extra_drafts = candidate_drafts - baseline_drafts
V_pick_raw(draft_time) = E[best unweighted PE contribution across the
                            remaining encounters in H of one extra draft]
XPValue = sum_{d in extra_drafts} V_pick_raw(d)
# 追加DraftによるGrowth等もこのraw値へ含める。total_peの0.15適用は§2で一度だけ。
```

`simulate_xp_levels`は現行`CARD_COSTS`、現在XP、XP倍率、Boss/Big Boss倍率、H内の敵を使う。レベルアップ閾値をまたぐ確率は期待イベント数または固定サンプルで算出する。追加ドラフトの価値は現行解禁・レアリティ分布・unique条件から推定する。`V_pick_raw`は追加取得後からH終了までの遭遇で生じる即時・条件・成長の**未加重PE差を、H全体の遭遇数で割った値**。追加Draft数の差は整数とは限らないため、時間帯別の期待取得数を使う。

追加DraftがさらにXPを生む効果は`V_pick_raw`に含めず、その再帰で生まれるDraftはH内のXP予測側で一度だけ処理する。追加Draft由来のCombat/Growth効果はXP軸から他軸へ移さない。**候補カード自体**のXP倍率が既存Knowledge Conversion等で直接Damageへ変わる分はCombatに帰属し、追加Draft由来の効果とは分離する。`CardValue.total_pe`を`V_pick_raw`へ入力してはならない。

### 5.5 Utility / Economy Value

素材、Card Point、操作時間等の差を、状態依存のシャドープライスでPEへ換算する。

```text
Economy = Δweapon_material * shadow_weapon_material
        + Δrelic_material * shadow_relic_material
        + Δcard_points * shadow_card_point
        - Δmanual_seconds * shadow_seconds
```

シャドープライスは在庫・解禁・次に可能な生成/強化行動から見積もる。確度のある換算値がない資源は0として理由を記録し、恣意的な固定加点をしない。効果が経済・時間を変えないカードでは0。

### 5.6 Synergy Value

候補を仮適用した完全差分に含まれる相互作用は、Immediate/Conditional/Growth/XPへ一度だけ計上する。

```text
synergy_residual = full_candidate_delta - sum(attributed_axis_deltas)
```

残差は診断値で、オンラインtotalには独立加点しない。これによりStandardに60/25/15以外の暗黙ウェイトを加えない。

### 5.7 Risk Penalty

不利益をPEに換算し、その効果が属する軸から一度差し引く。

```text
CombatNet = Immediate + Conditional - CombatRisk
GrowthNet = Growth + Economy - GrowthRisk
XPNet = XPValue - XPRisk
```

例: Heavy BlowのAS低下はCombat、Risky StudyのDamage低下はCombat・XP利得はXP、Glass Cannonの制限時間短縮はConditional Combat。前後Snapshot差に既に含まれた不利益は二度減点しない。

## 6. 指定カードの具体計算

### 6.1 Power Upの限界価値

現行式はPower UpをBase ATK加算へ入れるため、その加算項の前後差が限界価値になる。

```text
A0 = 現在の全Base ATKカード加算（Power Upを含む）
amp = limit_amplification(counts) * card_enhancement(state, "power_up")
A1 = A0 + 0.25 * amp

通常:
  Δbase_attack = log10(1 + A1) - log10(1 + A0)
Exponential Core所持時:
  Δbase_attack = config.exponential_core_multiplier
               * (log10(1 + A1) - log10(1 + A0))

Immediate(Power Up) = compute_snapshot(state + PowerUp).log_dps
                    - compute_snapshot(state).log_dps
```

`A0`はPower Up以外のBase ATK加算も含む。候補の枚数、強化段階、Limit Break/Shatter、Exponential Coreを仮適用したSnapshot差を正式値とし、式は検算用。従ってPower Upの価値は一定でなく、現加算量・強化状態・相互作用に応じた限界効果となる。

### 6.2 Execution

現行`execution_mult`を使い、要求Damage比の変化をH内Encounterごとに計算する。

```text
R0 = 0.70 + 0.30 / S0.execution_mult
R1 = 0.70 + 0.30 / S1.execution_mult

M0(e) = S0.log_dps + log10(I0(T_e)) - enemy_hp_power(e) - log10(R0)
M1(e) = S1.log_dps + log10(I1(T_e)) - enemy_hp_power(e) - log10(R1)
Conditional(Execution) = weighted_mean_e(M1(e) - M0(e)) - Immediate
```

`I(T)`はTime Collapse等も含む制限時間全体の時間積分。Execution単独なら`I0=I1`で、要求比率の改善がConditionalへ表れる。敵条件・制限時間に応じた`time_to_kill`差と撃破可否も診断に残す。

### 6.3 Time Collapse

候補前後の時間積分の比を比較する。

```text
I0(T) = temporal_integral(T, T, snapshot_without_card)
I1(T) = temporal_integral(T, T, snapshot_with_card)
Δmargin(e) = log10(I1(T_e)) - log10(I0(T_e))
           + その他の候補差
Conditional = weighted_mean_e(Δmargin(e)) - Immediate
```

通常敵10秒、Boss15秒、Glass Cannon等による制限時間変化を個別に評価する。`snapshot.log_dps`が変わらなくても積分が増えれば正のConditionalを返す。

### 6.4 XP・成長カード

- Experience / Fast Learner / Quick Learner / Scholar等: 直接XP倍率差は既存Snapshotで得る。追加Level-upによる選択機会をXPValueへ計上。
- Accelerated Learning: H内の後続カード取得数でXP倍率が伸びる分を予測し、そのLevel-up価値をXPValueへ。
- Growth Engine: H内の後続カード取得数で増えるDamageをGrowthへ。
- Boss Devourer: 候補取得後に倒すBoss分だけをGrowthへ。
- Knowledge Conversion: 現在XP余剰からの直接Damage差はCombat、後続XP取得による将来差はGrowth。XPの追加選択機会はXPValue。

同じ将来XPがKnowledge Conversion、追加カード取得、Growth Engineに波及する場合、イベント予測を一度作り、軸帰属表で重複分を除く。

## 7. Take / Reroll / Refineでの利用

`CardValue` は状態差の評価だけを担う。Take/Reroll/Refine/Upgradeの合法性、Card Point台帳、選択機会費用は行動選択側で比較する。旧scoreのBalancedしきい値1.10（Reroll）/0.55（溶解）はPEと単位が異なるため使用しない。

### 7.1 Take

```pseudo
context = build_evaluation_context(state, permanent, next_wave, config)
values = [evaluate_card_value(state, c, context, "take") for c in hand]
take(argmax(values.total_pe))
```

取得後に限り実状態を更新する。強制マイルストーンカードは現行仕様どおりReroll/Refine対象外。

### 7.2 Reroll

```pseudo
current_best = max(CardValue(c).total_pe for c in hand)
reroll_best_ev = E[max(CardValue(c).total_pe for c in next_hand_distribution)]
reroll_cost = reroll_seconds * shadow_seconds

reroll iff reroll_best_ev - reroll_cost > current_best
```

次手札の分布は既存rarity、解禁、unique、除外カード、3択ルールを使う。期待値サンプルは専用RNGで計算し、ゲームRNGを進めない。初期実装は未校正の操作時間価値を避け`shadow_seconds=0`とし、後で校正可能にする。Reroll上限では残手札の最良CardValueを取る。

### 7.3 Refine（提示カードを溶解）

溶解は、手札内で最良カードを取得する機会費用と、**今回の溶解による追加Pointの限界価値**を比較する。既に強化へ投入済みのPointはサンクコストであり、再減点しない。既存の未使用Pointは現状態の資産として保持し、Refineする場合だけ失われるなら、その失効分を差し引く。

```pseudo
baseline_options = best_legal_upgrade_plan_value(state, current_points, context)
best_take = max(CardValue(c, "take").total_pe for c in hand)
for c in hand:
    after_points = current_points + CARD_POINT_VALUE[c.rarity]
    with_refine = best_legal_upgrade_plan_value(state, after_points, context)
    incremental_point_value = with_refine - baseline_options
    expiry_loss = value_of_existing_unspent_points_lost_only_if_refine(c)
    refine_value[c] = incremental_point_value - expiry_loss
refine iff max(refine_value[c] for c in hand) > best_take + refine_decision_margin
```

`best_legal_upgrade_plan_value` は今回以降に**新たに**使うPointの機会費用と、H内に実現する増分価値を差し引いた、現在の未使用Point残高からの最適行動価値を返す。過去に強化済みのPointは入れない。`with_refine - baseline_options` により、元々のPointで可能だった強化を重複計上しない。もしRefineによって既存の未使用Pointが失効するルールがある場合は、失効分を`expiry_loss`として追加で引く。ただし`with_refine`の状態モデルに失効を既に反映した場合は再度引かない。現行v1でのRefineの失効は通常0（死亡時リセットの共通制約はHに反映）。

既存仕様の強化可能範囲（C/U/R、ruleタグなし）、費用5/15/40、最大+3を使う。未使用Card Pointの将来オプション価値も残す。比較単位は常に手札全体の最良Take対最良Refineとする。

### 7.4 強化先

強化候補ごとに次の1段階を仮適用し、同じCardValueで限界増分を求める。強化後に再評価し、複数回の投資を逐次決める。

```pseudo
upgrade_gain = evaluate_state_delta(state, state + one_upgrade, context).total_pe
net_gain = upgrade_gain - point_opportunity_cost
buy best affordable upgrade iff net_gain > 0
```

`point_opportunity_cost` は今回追加消費するPointだけに課す。既に投入済みのPointを再減点しない。重複枚数を旧式の`score * count`で乗算しない。強化による正の効果増幅は既存`card_enhancement`/`positive_amp`を使い、デメリットを増幅しない仕様も維持する。

## 8. 再利用する既存コード

| 既存コード | 再利用目的 |
|---|---|
| `compute_snapshot` (`simulate_first_prestige_v1.py:656–826`) | 前後Snapshot、DPS/AS/Crit/XP/Follow-Up等の限界差分 |
| `time_curve_integral`, `temporal_integral`, `time_to_kill` (`:829–925`) | Time Collapse、Execution、時間効果、撃破可否・時間 |
| `time_to_kill_with_defense` (`:928–991`) | Defense有効条件の戦闘評価。呼出しコストを測定する |
| `progression_wave`, `progression_units`, `configured_enemy_power` (`:541–564`) | 予測Wave、進行イベント、敵Power |
| `CARD_COSTS`, `CARD_POINT_VALUE`, `CARD_UPGRADE_COSTS` (`:112–113`, `:271`) | XP閾値、溶解Point、強化費用 |
| `rarity_chances`, `available_cards`, `draw_hand` (`:994–1069`) | 将来ドラフトのrarity・解禁・unique条件 |
| `card_enhancement`, `enhanced_count`, `positive_amp`, `enhanceable`, `limit_amplification` (`:571–594`) | 現行強化・倍率・強化可否 |
| `acquire_card` (`:1072–1081`) | 候補の状態コピーへの仮適用。イベントカウンター意味を確認して用いる |
| `RunState`, `PermanentState`, `Snapshot`, `SimConfig`, `CARDS` | 入力状態、カード定義、シミュレーション設定 |

`card_score` (`:1179–1254`) はBalanced Standardの評価基準として再利用しない。`choose_card`と`spend_card_points`の制御フローは参考にできるが、旧固定しきい値・タグ固定score・`score * count`は置換対象。

## 9. 新規に必要な関数・型

```text
EvaluationContext = build_evaluation_context(state, permanent, next_wave, config)
baseline_predicted_run_end_wave = predict_baseline_run_end(state, permanent, config)
StateCopy = clone_state_for_evaluation(state, permanent)
apply_candidate_to_copy(state_copy, candidate, action)
project_encounters(context) -> Encounter[]
evaluate_encounter_margin(state, encounter, config) -> EncounterValue
forecast_future_events(state, context) -> Forecast
simulate_xp_levels(state, candidate, forecast) -> XPForecast
expected_best_draft_value(state, context, rng_seed) -> float
evaluate_economy_shadow_prices(state, permanent, context) -> ShadowPrices
attribute_delta_to_axes(before, after, forecast, encounters) -> AxisValues
evaluate_card_value(state, candidate, context, action) -> CardValue
evaluate_state_delta(before, after, context) -> CardValue
evaluate_upgrade_value(state, card_key, next_level, context) -> CardValue
expected_reroll_value(state, hand, excluded, context) -> float
best_legal_upgrade_plan_value(state, points, context) -> UpgradePlan
should_refine(state, offered_card, context) -> bool
```

全評価は状態コピーのみを変更し、実RunState/PermanentStateおよびゲーム本体RNGを変更しない。候補間比較の抽選には同じ判断内で共通の乱数列（common random numbers）を使い、候補順に依存させない。候補IDはキャッシュキーに含めるが、共通抽選seedには含めない。

## 10. 性能・キャッシュ

- 判断ごとにEvaluationContext、Encounter集合、基準Snapshotを一度作る。
- baseline残りRunが長い場合は同じ敵条件を集約して重み付けし、Hをカードごとに再予測しない。
- 同じ候補の前後Snapshot、XP予測、候補ドラフト期待値を判断内キャッシュする。
- Reroll期待値のonline既定サンプル数は32、オフライン精度確認は256以上。サンプル数は設定可能。
- Defense無効時は通常のSnapshot/`time_to_kill`経路を優先。Defense有効時の反復計算は必要な候補・Encounterに限る。
- 候補あたり計算時間、判断あたり総時間、キャッシュhit率を記録する。

## 11. 受け入れ条件

1. 同一seed・同一状態でCardValueが再現し、評価呼出しが本体RNGを進めない。
2. 関数呼出し前後で入力状態に差がない。
3. Power Upの限界価値が加算飽和・強化段階・Exponential Core状態で変化する。
4. Crit上限時のCritical Eyeは限界効果に応じて低下する。
5. Executionは`execution_mult`を、Time Collapseは時間積分を通じ、現在DPS差が0でも条件に応じて価値を返す。
6. XPカードの価値がbaselineから固定した残りH、XPコスト境界、Boss比率、追加ドラフト価値で変わる。追加DraftのCombat/Growth影響はXP軸のみに帰属し、0.15を二度適用しない。
7. Accelerated Learning / Growth Engine / Boss Devourerは候補取得後イベントだけを将来価値へ計上する。
8. 同じ状態差分ならカードrarityのみを理由にCardValueが変わらない。
9. Take/Reroll/Refine/Upgradeの診断ログが同じtotal_pe定義を使い、各効果を二重計上しない。Refineは既存未使用Pointのbaseline価値を差し引き、既投入Pointは差し引かず、失効する既存Pointのみ一度差し引く。
10. 既存formal結果との比較はバランス変更を混ぜず、同seed条件で実施できる。

## 12. 中規模案としての近似限界

この仕様はカード選択ごとに第一転生Run全体をMonte Carlo再実行しない。baseline現在Run残り期間の近似予測、将来カード選択の期待値、候補による生存期間延長の評価除外は中規模案の近似である。実装後は既存出力と同一seed比較を行い、baseline終了Wave予測、追加Draftの未加重PE換算、Economy shadow priceを校正する。校正前に旧scoreの1.10/0.55しきい値を新total_peへ流用しない。
