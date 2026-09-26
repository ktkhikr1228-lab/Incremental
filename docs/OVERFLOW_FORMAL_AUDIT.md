# formal v1 `overflow` 実装調査（2026-09-26）

対象は**旧formal第一転生 W10000** の [`scripts/simulate_first_prestige_v1.py`](../scripts/simulate_first_prestige_v1.py)。新W5000候補プローブとは区別する。`overflow`の戦闘効果をコードから一意に復元できないため、**CardValue化は要仕様確認・未実装**。

## 定義とキー固有の参照

formal v1本体で`overflow`を文字列キーとして参照する箇所は次の2箇所だけ。

1. `sim.CARDS`（227行）: `card("overflow", "Overflow", "R", "crit", "rule", unique=True)`。Rare、Crit/Ruleタグ、固有、解禁Wave指定なし（既定0）。
2. `POTENTIAL`（1167–1184行）: `"overflow": 0.05`。これは`card_score`（1187–1262行）が加点する**選択ヒューリスティック**であり、実際のCrit率や戦闘Damageではない。タグにも汎用の評価ウェイトがある。例: 初期状態のBalanced旧scoreは`0.81325`で、PEや戦闘効果を表さない。

`first_prestige_v1_spec.md`、`card_value_evaluation_spec.md`、`card_value_v01_implementation_plan.md`に`Overflow`/`overflow`の個別効果・期待式は見つからなかった。

## 取得時に実際に起こる共通処理

- `available_cards`（1011–1030行）はRareプールから未所持の固有カードとして提示可能にし、取得後は固有条件で除外する。取得は`acquire_card`（1080–1089行）を通り、`run.counts["overflow"]`、`run.tag_counts["crit"]`/`["rule"]`、card_count、choices、effect_versionを更新。Growth Engine / Accelerated Learningが既所持なら、**どのカード取得でも**発生する取得イベントの成長も発生する。`overflow`固有の成長ではない。
- `"rule"`タグにより`enhanceable`（592–593行）で強化対象外。`card_score`のCrit/Rule/POTENTIAL加点と`tag_counts`更新は、将来の旧scoreによる選択やSynergy、Multi-Critを既所持してW2500に到達した場合の`matching_legendary`（1535–1547行）のCrit系対応カードの投資タグ数に**間接的に**影響し得る。これらは「Crit上限解除」という戦闘効果の実装ではない。

## 戦闘・Crit計算における不在

`compute_snapshot`（664–834行）のCrit率は各数値カード等から計算し、`overflow`所持を参照しない。`Snapshot.crit_chance`は100%超でも生値であり、既存のCrit閾値連動効果にもこの値を使う。`crit_log_multiplier`（621–642行）はMulti-Critなしなら`min(1.0, chance)`でダメージ寄与を100%に制限する。Multi-Critありなら生Crit率からTierを計算するが、この分岐も`overflow`とは無関係。`time_to_kill`や撃破後成長にも`overflow`固有分岐は見当たらない。

**読み取り専用の挙動確認**（`PYTHONPATH=scripts python3`からformalモジュールを読み込み、コピーへの`acquire_card`前後の`compute_snapshot`を比較）:

| 取得前の所持例 | Crit率 | Overflow取得後のlog DPS差 | Crit率差 | Multi-Crit Tier差 |
|---|---:|---:|---:|---:|
| なし | 0.01 | 0.0 | 0.0 | 0 |
| Critical Eye 12枚 | 1.21 | 0.0 | 0.0 | 0 |
| Critical Eye 12枚 + Multi-Crit 1枚 | 1.21 | 0.0 | 0.0 | 0 |

同じ確認で取得前はRareプールに存在、取得後はunique条件で消え、`enhanceable=False`、`crit`タグ数は+1。これは**上記の限定状態とコード参照調査**の結果であって、効果が0であることを意図した正式仕様の証明ではない。

## テストと他系列の扱い

`scripts/test_*.py`の4ファイルに`overflow`/`Overflow`への参照はなく、formalの取得前後のCrit上限やCombat/PEを検証する専用テストもない。`first-prestige-playtest/sim_server.py:65`には「Crit率100%上限を撤廃（超過Tierはまだ無効）」との**表示説明**があるが、同サーバーの戦闘計算はformalモジュールを利用するため、説明文だけでは対応するformal効果の実装を示せない。別系列の`scripts/simulate_new_w5000_common_uncommon_rare.py`は`overflow`を表示Crit・シナジー用Critの上限処理に使い、Epic版でも別の`overcap_enabled`がある。**新W5000候補のルールをformal v1へ転用しない。**

## 判定: 要仕様確認

現行formalコードでの**直接の戦闘効果は確認できない**。一方、カード名・ruleタグ、playtest説明、新W5000の別実装から意図を一意に確定することもできない。特に100%超のCrit率について、表示/閾値シナジー/実ダメージのどれを変えるのか、Multi-Critと併用したTierをどう扱うのか、そもそもformal v1では効果なしを意図したのかの決定が必要。`overflow`のCardValue実装やformal戦闘式・specは変更せず、正式な効果仕様が決まるまで**要仕様確認**とする。新fallback仕様の10組では合法候補に`overflow`が2手札、単独原因は0手札だった（[`output/card_value_take_eligible_unsupported_10.md`](../output/card_value_take_eligible_unsupported_10.md)）。
