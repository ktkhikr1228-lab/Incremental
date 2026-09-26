# Shadow CardValue v0.1: Encounter-based Conditional PE 修正設計

状態: **正式v1のshadow評価にExecution/Time Collapseのみ実装済み**。Take/Reroll/Refineの選択は旧scoreのまま。根拠は [`output/card_value_v01_validity_diagnostic.md`](output/card_value_v01_validity_diagnostic.md) の人工状態比較。以下の未対応候補・新W5000系のadapter案は今後の設計事項。

## 1. 問題と適用範囲

現行 `scripts/card_value_v01.py` は条件カードの価値を `temporal_integral(T,T,snapshot)`、つまり制限時間全体で発揮できる総Damageの差として測る。同じWaveで敵HPだけを変えても、候補前後の `enemy_hp_power` は差分で相殺される。したがって Time Collapse は `1.23→1.23秒` と `9.82→6.14秒` の双方で Conditional 約 `0.4150 PE`、Executionも余裕戦闘と壁で約 `0.0862 PE` になった。さらに連続余裕が正でも、必要攻撃回数の切り上げにより時間切れが起こる。

**修正対象:** 条件付き/時間依存カードの Conditional Combat Value のみ。通常の Power Up / Rapid Fire / Critical Eye 等は現行の `compute_snapshot` 前後差による Immediate PE を維持し、Conditional=0とする。既存のbaselineから決まるH、Combat/Growth/XPの帰属と `0.60/0.25/0.15`、候補コピーと本体RNG不変、terminal PE非加算は維持する。

## 2. 現行戦闘モデルに沿う Encounter Outcome

評価はH内の各敵 `e=(wave, enemy_kind, enemy_power, limit)` について、**同じ敵・同じ制限時間**のbaseline戦闘と候補仮適用後の戦闘を比較する。`boss = wave % 10 == 0` を各Snapshotへ与える。敵HP、Big Boss、`enemy_time_limit`、Glass Cannon、既存時間倍率、Defense有効時のHP/Armor Breakを、その設定の実行経路で解決する。

```pseudo
S0 = compute_snapshot(baseline_state_at_e, permanent_at_e, e.is_boss, config)
S1 = compute_snapshot(candidate_copy_at_e_without_future_growth,
                      permanent_at_e, e.is_boss, config)

T0 = time_to_kill_with_defense(e.wave, e.enemy_power, e.limit,
                               S0, S0.log_dps, config)
T1 = time_to_kill_with_defense(e.wave, e.enemy_power, e.limit,
                               S1, S1.log_dps, config)
win_i = T_i is not None
```

`T_i=None` はタイムアウト。単純な`log_dps - HP Power`を勝敗判定に使わない。候補の効果によってQuick Learner等の3秒判定が変わる場合は、XP軸の既存イベント予測で**同一H上の新TTK**から判定し、Conditionalに追加XPを重ねない。

### 現実にモデル化されている離散性の範囲

- 正式v1の非時間依存経路は `required_ratio=0.70+0.30/execution_mult` と `required=10^(HPpower+log10(required_ratio)-log_dps)` を用い、`ceil(required * attack_speed)` 攻撃を `1/attack_speed` 刻みで行う。`T0/T1` は**必要Hit数を切り上げた結果**で比較する。実際の演出用の個別Hit RNGを新たに作らない。
- 時間効果の経路は現行 `temporal_lookup` で必要Damageに到達する連続時刻を求め、その時刻を `ceil(time * attack_speed)/attack_speed` に丸める。Time Collapse/First Strike/Last Standはこの関数が使う区間積分を通す。これは現行本体の近似であり、各攻撃時刻にDamage倍率を再サンプリングする別エンジンとは同一ではない。診断には連続到達時刻、攻撃回数、離散TTKを区別して残す（現行関数が前二者を返さないため、同式から診断専用に再構成する場合は結果照合が必須）。
- Crit / Multi-Crit は `crit_log_multiplier` による現在ビルドの期待DamageとTierを含めたSnapshotを使う。Follow-Upも現在の追撃率・追撃Damage・Echo/再帰上限を織り込んだ期待Damageを使う。Critや追撃の確率で攻撃ごとのランダムHit列を生成しない。Defense有効時はSnapshot中のAS/Crit/追撃率がArmor Breakへ渡る経路も維持する。
- **Hit Count / Re-Action は正式v1のカードプールにない。** 新W5000側の `multi_hit` / `re_action` を対象に広げる場合のみ、その系統の `action_factor` による期待Hit数・Reaction action・Follow-Up段数をSnapshot側の戦闘adapterで扱う。Re-ActionはFollow-Upから発火せず、Re-Actionの通常行動からはFollow-Upが出るという既存ルールを保持する。新W5000のTime Collapseは正式v1と時間曲線も異なるので、モデル間で積分関数を流用しない。実カードのHit CountやReaction発動を「毎攻撃で必ず起きる」離散イベントとして捏造しない。

## 3. Encounter結果をPEへ写す規則

**単位を揃える:** 1 PEを「最終 `log10 DPS` を1.0加えたのと同程度の戦闘時間/突破結果の改善」として定義する。時間短縮の秒数を任意係数で直接PEに足さず、**同じ敵、baselineのその他の戦闘パラメータを固定して、実TTK関数を同じ結果まで改善するのに必要な最小 `log10 DPS` 増分**へ逆算する。

```text
T(S, d, e) = time_to_kill_with_defense(e.wave, e.power, e.limit,
                                      S, S.log_dps + d, config)

need(S, target_time, e) = inf{d >= 0 | T(S,d,e) != None
                                         and T(S,d,e) <= target_time}
need_win(S,e) = need(S,e.limit,e)
```

攻撃間隔が決める最短TTK未満の`target_time`はスカラーDamage増分で到達不能なので、`unreachable_by_damage`として返し、PEを無理に生成しない。逆算は単調な最小到達点をブラケット探索＋二分法で求め、`ceil`と`1e-12`等、本体の境界許容値に合わせる。`T(S,0)`が対象時刻以下なら`need=0`。解が数値範囲内にない場合、固定の巨大PEを与えず`unresolved`と記録する。

| baseline → 候補 | Encounter PE `E(e)` |
|---|---|
| 成功 `T0` → 成功 `T1<T0` | `+need(S0,T1,e)` |
| 成功 `T0` → 成功 `T1=T0`（許容誤差内） | `0` |
| 成功 `T0` → 成功 `T1>T0` | `-need(S1,T0,e)` |
| 時間切れ → 成功 `T1` | `+need(S0,T1,e)`。baselineの離散Hit不足を埋めて候補TTKまで到達させるDamage増分 |
| 成功 `T0` → 時間切れ | `-need(S1,T0,e)` |
| 時間切れ → 時間切れ | `need_win(S0,e) - need_win(S1,e)`。まだ勝てないが必要火力が減る分だけ正 |

成功同士で同TTKなら、全制限時間積分が増えてもその敵の時間価値は0。`T0=1.23s,T1=1.23s` のTime Collapseは `E(e)=0`。`T0=9.82s,T1=6.14s` は `E(e)>0`、その逆算PEは余裕戦闘を上回る。baselineが連続DPS上は勝てそうでも、切り上げ後 `T0=None` なら必ず「時間切れ→成功/時間切れ」の枝へ入り、連続marginの符号で成功扱いしない。

両者失敗時の `need_win` は現行エンジンの**離散**勝利条件を満たすための最小増分。Defenseの完全BreakがAS等の制約で不可能なら `need_win` が存在しない場合がある。その敵は `unresolved_by_damage` とし、必要に応じて別のAS/Armor Break換算を設計する。近似の都合で「敗北=0点」にしない。

### Immediateとの接続・集計

```text
Immediate(e) = S1.log_dps - S0.log_dps

if card uses encounter conditional path:
    Conditional(e) = E(e) - Immediate(e)
else:
    Conditional(e) = 0                    # 既存snapshot marginalを維持

Immediate PE   = sum_e weight(e)*Immediate(e) / sum_e weight(e)
Conditional PE = sum_e weight(e)*Conditional(e) / sum_e weight(e)
CombatNet PE   = Immediate PE + Conditional PE
total_pe       = 0.60*CombatNet PE + 0.25*GrowthNet PE + 0.15*XPNet PE
```

条件付きカードは `Immediate + Conditional = 平均 E(e)` となり、同じ火力を二重計上しない。純粋なTime Collapse/ExecutionではImmediateが0のため、Encounter PEがそのままConditionalになる。複数効果のカードも1つの仮適用後状態で比較し、Snapshot寄与をImmediateへ、差額をConditionalへ置く。条件カードの当該敵で `E(e)=0` なら負のConditionalがあり得るが、これはImmediateの相殺であり独立のRisk再減点ではない。

Hはカード候補と無関係に固定。候補の将来成長は従来どおりGrowth、XPで増える追加DraftはXP軸だけ。**このEncounter PEにterminal/continuation価値を混入しない。** H内の敗北敵を救うことはEncounter価値に含まれるが、H外の追加Waveへの報酬は含めない。`terminal_break_probability_delta`は診断として残し、`terminal_pe=None`、`terminal_included=False`、Totalに加算しない。

## 4. 関数境界とコスト

- `should_use_encounter_conditional(card, ruleset)`：対象カードを明示登録する。まず正式v1の `execution` / `time_collapse`。将来First Strike / Last Stand / Momentum、条件付きBoss効果、追撃等へ広げる際は、その条件が現在の戦闘adapterで表現されていることを確認。Power Up / Rapid Fire / Critical Eyeは登録しない。
- `resolve_encounter(state,e,ruleset)`：敵とSnapshotを固定し、既存の `time_to_kill_with_defense`（Defense無効なら内部で `time_to_kill` を呼ぶ）からTTK/成功を取得。現実装は非時間経路のbaseline必要Hit数/制限内Hit数のみ診断出力する。候補Hit数・時間経路の連続到達時刻/Hit数の診断と、Hit Count / Re-Actionの別adapterは未実装。
- `required_final_dps_delta(snapshot,e,target_time)`：前述の `need` を評価。境界・数値精度・到達不能を明示的な結果型で返す。
- `encounter_equivalent_pe(before,after,e)`：成功/敗北の表でPEを求める。`E(e)`と元TTK、変更後TTK、HP Power、limit、Hit数、逆算回数を診断へ出す。
- Shadowの候補1枚につきH内各Encounterの `S0/S1`・TTKを比較し、同一時刻なら逆算を省略する。現実装は内部TTKのキャッシュとDefense反復の負荷計測を行っていない。Damage増分で到達不能なら `conditional_status=unresolved_by_damage`、`conditional_combat_pe=None`、`total_pe=None`を記録する。旧積分PEへ無言で戻さない。

## 5. 必要なテストケース（入力状態 → 候補 → 期待関係）

### 5.1 最初に確認する合格ゲート

次の7条件は**すべて合格してから**追加の条件付きカードへ対象を広げる。時間・PEの例は [`output/card_value_v01_validity_diagnostic.csv`](output/card_value_v01_validity_diagnostic.csv) の同Wave人工状態を入力fixtureとして使う。「≈0」は `abs(PE) <= 1e-9`、正の改善は数値誤差より十分大きい `PE > 1e-6` とする。snapshot固定の比較では既存結果との差も `abs(delta) <= 1e-9` とする。許容差はテスト環境の浮動小数点再現性を測定してから変更できるが、関係の逆転を許してはならない。

| # | 入力状態 → 候補 | 合格条件 |
|---:|---|---|
| 1 | W501通常敵、baseline 1.23秒 → Time Collapse後も1.23秒 | `conditional_combat_pe≈0`。当該カードのImmediateは0なのでEncounter Combat PE/Totalへの寄与も≈0 |
| 2 | 同じW501、baseline 9.82秒 → Time Collapse後6.14秒 | `conditional_combat_pe > 1e-6`、かつ #1 の余裕戦闘より明確に高い。候補後TTKは本体の `time_to_kill` と一致 |
| 3 | W500 Boss、baselineもExecution後も同じ離散攻撃回数で約1.23秒の瞬殺戦 | Executionの `conditional_combat_pe≈0`。全時間積分から旧値約0.086 PEを与えない |
| 4 | 同じW500 Boss、baseline 14.12秒 → Execution後11.66秒 | `conditional_combat_pe > 1e-6`、かつ #3 より高い |
| 5 | W500 Boss、continuous full-time marginは正だがAttack回数を切り上げるとタイムアウト、Execution後12.28秒で撃破 | baselineの `win=False`、候補の `win=True`。敗北→勝利分岐を通り、正のConditional PEを返す。連続margin正を勝利判定に使わない |
| 6 | W50、Power Up / Rapid Fireをそれぞれ0/5/20 stackとした既存fixture | 両カードのImmediate・Conditional・Growth・XP・Totalは**変更前のshadow値と一致**。具体的に0 stackのImmediateはPower Up約0.0969100130、Rapid Fire約0.0791812460 PE。いずれも0>5>20 stackの限界逓減を維持 |
| 7 | 同一seed、同じ初期状態・設定でshadow OFFとONの実行 | カード選択・Reroll・Refineの決定列、`RunResult`/`TrialResult`の全フィールド、入力/終了時のゲームRNG状態、変更可能な本体stateが完全一致。診断出力だけが増える。単一Runと複数attemptの双方で確認 |

ゲート#5では `time_to_kill_with_defense` の戻り値も照合し、攻撃時刻 `ceil(required*attack_speed)/attack_speed > limit` を明示的に検査する。#6は新方式の条件カード以外へ分岐が漏れていない回帰検査。#7のRNGはモジュールのglobal RNGだけでなく、実Runへ渡した `random.Random` インスタンスの `getstate()` を比較する。shadowの評価が例外を起こした場合も、legacyのカード選択を止めたりRNGを動かしたりしない。

### 5.2 追加の境界テスト

| 入力状態 | 候補 | 期待関係 |
|---|---|---|
| W501通常敵、baseline TTK=1.23秒・候補後も1.23秒 | Time Collapse | Encounter PE/Conditional≈0。現行全時間積分の約+0.415 PEを流用しない |
| 同じW501、baseline 9.82秒→候補後6.14秒 | Time Collapse | Conditional>余裕戦闘。Encounter逆算PE>0、Totalも高い |
| W501 baseline時間切れ→候補で撃破（例:6.75秒） | Time Collapse | 勝敗変化を記録、Conditional>0。terminal PEはNone、Totalに加えない |
| W500 Boss、baseline 1.23→1.23秒 | Execution | Conditional≈0 |
| W500 Boss、baseline 14.12→11.66秒 | Execution | Conditional>余裕戦闘、Hit数減少を記録 |
| W500 Boss、連続full-time marginが正、離散Hitでは時間切れ→候補後12.28秒で撃破 | Execution | baselineは敗北として扱う。`need_win(S0)>0`、Conditional>0。連続margin正をもってbaseline勝利としない |
| 同じ敵・同じ状態で攻撃速度だけ変え、候補前後TTKが同一のplateau | 条件付きカード | 撃破時間上のEncounter PE=0。Hit切り上げ境界を跨いだときだけ正/負の変化 |
| 候補で戦闘時間が延びる、または勝利→敗北 | 条件付きカード | Encounter PE<0。Riskを二度引かない |
| baseline/候補とも時間切れだが、候補で`need_win`が減少 | 条件付きカード | Encounter PE>0、勝敗はともに失敗と表示 |
| 同じ状態・敵、Power Upの取得枚数0/5/20 | Power Up | 現行SnapshotのImmediate逓減を維持、Conditional=0 |
| 同じ状態・敵、ASでHit数やTTKが変化 | Rapid Fire | v0.1ではImmediateは現行Snapshot差、Conditional=0（変化は診断可能） |
| Crit上限直前/超、Multi-CritのTier前後 | 正式v1の条件候補 | Snapshotの期待Crit・Tier経路と本体TTKを一致させる。Crit RNGは消費しない |
| Follow-Upなし/あり、追撃率と再帰上限が異なる | Follow-Up系候補 | 実モデルの期待追撃を使い、同じ期待DamageをHit数へ重ねて足さない |
| 正式v1カードプールでRe-Actionの評価を要求 | Re-Action | `unsupported_ruleset`。存在しないカード効果を捏造しない |
| 新W5000カードプールでMulti-Hit/Re-Action/Follow-Upを併用 | 各条件候補 | その系統の `action_factor` と時間曲線を使い、Re-Action×Follow-Upの発火順を守る。正式v1の式とは混用しない |
| Defense無効/有効、最終Bossの完全Armor Breakを含む | 条件候補 | 有効時は既存Armor Break込みTTK。Damage増分で到達不能なら `unresolved_by_damage`、架空のPEを与えない |
| 複数の敵を含む同一H、候補順のみ変更 | 対象の条件カード | 各敵の重みとHは同一。入力state・ゲームRNGは不変、候補順で結果が変わらない |
| 任意の評価成功状態 | 対象の条件カード | `Immediate+Conditional=平均Encounter PE`、`total=0.60*Combat+0.25*Growth+0.15*XP`、terminalは非加算 |

最初の合格ゲートと一部境界条件は `scripts/test_card_value_encounter_conditional.py`、旧評価の回帰は `scripts/test_card_value_v01.py` で確認する。既存診断CSVは**変更前の値**なので、修正後の数値として引用しない。
