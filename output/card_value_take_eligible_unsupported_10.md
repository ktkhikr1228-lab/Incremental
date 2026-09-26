# 合法Take候補の未対応key集計 — 新fallback仕様・10組

入力: [`card_value_take_eligible_pilot_10_branches.jsonl`](card_value_take_eligible_pilot_10_branches.jsonl)。旧formal W10000 / Balanced・POあり、seed `20260828`、trial ID `0..9`、各最大10 attempts。`take_mode=pe`かつ`action=take`の**1,477手札**を対象にした、保存済みログの読み取り専用集計。`hand_keys`内でも`eligible_keys`に属さないカードは数えない。各手札の未対応集合は、合法候補のうち`pe_status=unsupported_card`である**異なるkeyの集合**。同じ集合の並び順は無視し、1手札につき各keyを1回数える。

PE実測適用は **180/1,477 = 12.19%**、fallbackは **1,297/1,477 = 87.81%**（すべて`unsupported_card`）。未対応集合のサイズ別: 0 key 180手札、**1 key 433**、**2 key 615**、**3 key 249**。この3択ログでは4 key以上は存在しない。keyの出現を全部合算すると2,410件で、手札数ではない。

## 各key: 出現・単独原因・CardValue化の暫定分類

「単独原因」は、その手札の**合法候補**に含まれる未対応keyが当該keyだけだった数。そのkeyだけを対応したときの**構造上の限界増加手札数**に相当する（他の合法候補のPE有効性は未検証）。分類は[`../scripts/simulate_first_prestige_v1.py`](../scripts/simulate_first_prestige_v1.py)のカード定義、`compute_snapshot`、`dynamic_damage_log`、`enemy_time_limit`、`time_to_kill`、戦闘後の成長処理から主な実装障壁を1群に割り当てた概算で、工数やPEの精度を保証しない。

| key | 出現手札 | 単独原因（単独対応の増分上限） | 分類 | 根拠・難所 |
|---|---:|---:|---|---|
| steady_force | 269 | 95 | simple snapshot | 静的な全Damage加算 |
| precise_strike | 236 | 37 | simple snapshot | Crit率増、AS減を同時に反映 |
| critical_eye | 233 | 46 | simple snapshot | Crit率加算 |
| glass_cannon | 223 | 37 | conditional encounter | ATK増に加え敵の制限時間が短縮される |
| heavy_blow | 221 | 49 | simple snapshot | ATK増、AS減の差分 |
| sharpened_edge | 220 | 31 | simple snapshot | Crit率とCrit倍率の加算 |
| heavy_critical | 218 | 33 | simple snapshot | Crit倍率/率とAS減を同時に反映 |
| light_attack | 214 | 27 | simple snapshot | AS増とATK減の差分 |
| critical_power | 208 | 32 | simple snapshot | Crit率とCrit倍率の加算 |
| critical_momentum | 56 | 8 | simple snapshot | Crit率の段階閾値からASを増加 |
| first_strike | 54 | 8 | conditional encounter | 戦闘の初め3秒に限定した倍率 |
| critical_training | 41 | 3 | simple snapshot | Crit率とCrit倍率の加算 |
| brutal_force | 40 | 4 | simple snapshot | ATK増、AS減の差分 |
| overclock | 34 | 7 | simple snapshot | AS増、ATK減の差分 |
| last_stand | 33 | 2 | conditional encounter | 戦闘の最後3秒に限定した倍率 |
| escalation | 32 | 3 | growth/XP | 撃破Wave数に応じたDamage成長 |
| battle_focus | 30 | 3 | growth/XP | Damage増とXP倍率低下を共通H内のDraft機会まで追う |
| critical_engine | 10 | 2 | simple snapshot | Crit率の段階閾値からASを増加 |
| critical_conversion | 9 | 1 | simple snapshot | Crit率の段階閾値から全Damageを増加 |
| momentum | 7 | 0 | conditional encounter | 3秒以内撃破による次戦闘の発動状態 |
| brutal_critical | 6 | 1 | simple snapshot | Crit率減とCrit倍率増の差分 |
| growth_engine | 5 | 1 | growth/XP | 以後のカード取得イベントによる成長 |
| double_strike | 4 | 2 | special/rule-changing | Follow-Up Strike所持が効果の前提、追撃率/威力を変更 |
| boss_devourer | 3 | 1 | growth/XP | Boss撃破後にスタックを増やし次戦闘へ反映 |
| follow_up_strike | 2 | 0 | special/rule-changing | 追撃の発動、Echo/再帰などとの相互作用 |
| overflow | 2 | 0 | special/rule-changing | `rule`タグのunique。formal戦闘式に独立した効果の参照が見当たらず**要確認** |

`simple snapshot`でも段階閾値や相互作用の検算は必要。`conditional encounter`には勝敗・制限時間・次戦闘の状態を伴うものを含む。`growth/XP`は候補取得後の予測イベントやXP Draft機会まで追う分類。`special/rule-changing`は既存ルールとの相互作用、または効果仕様の確認が必要な群。`overflow`の効果はカード定義とlegacy score以外に明示的な適用箇所を確認できず、効果を推測してCardValue化しない。

## 未対応keyが2個・3個の組合せ頻度

同じ手札の**未対応key集合そのもの**の出現回数（ペアが3 key手札に含まれる回数ではない）。2 key手札は615件・異なる組合せ122種類、3 key手札は249件・異なる組合せ140種類。**全262組合せと各頻度**は [`card_value_take_eligible_unsupported_10_combinations.csv`](card_value_take_eligible_unsupported_10_combinations.csv)（`unsupported_key_count,key_1,key_2,key_3,hands`）および[集計JSON](card_value_take_eligible_unsupported_10.json)に保存。上位例:

| 未対応key数 | exact key集合 | 手札数 |
|---:|---|---:|
| 2 | glass_cannon, light_attack | 21 |
| 2 | glass_cannon, heavy_critical | 20 |
| 2 | glass_cannon, precise_strike | 20 |
| 2 | critical_power, sharpened_edge | 19 |
| 2 | critical_eye, precise_strike | 18 |
| 2 | light_attack, precise_strike | 18 |
| 2 | precise_strike, steady_force | 18 |
| 2 | critical_eye, steady_force | 17 |
| 3 | critical_eye, glass_cannon, sharpened_edge | 7 |
| 3 | critical_eye, critical_power, light_attack | 6 |
| 3 | critical_eye, critical_power, sharpened_edge | 5 |
| 3 | critical_eye, heavy_critical, steady_force | 5 |
| 3 | critical_power, precise_strike, steady_force | 5 |
| 3 | glass_cannon, heavy_blow, precise_strike | 5 |
| 3 | heavy_critical, sharpened_edge, steady_force | 5 |

## Greedyによる構造適用可能数

集合`S(hand)`を上記の未対応key集合、追加対応済み集合を`A`とする。構造適用可能数は `#{hand | S(hand) ⊆ A}`。各段階で**今回追加する1 keyにより新しく集合全体をカバーする手札**が最多になるkeyを選ぶ。同数ならkeyの辞書順。対応済み候補のPEが実際に有効か、追加keyのPEを計算できるかは評価していない。従って以下は**この固定JSONL上の構造上限**であり、カード追加後にゲームを再実行した際のPE適用率ではない。0 key時点は実測済み180手札。

| 段階 | 追加key | その段階の限界増加 | 累積手札 | 累積率 |
|---:|---|---:|---:|---:|
| 0 | — | — | 180 | 12.19% |
| 1 | steady_force | 95 | 275 | 18.62% |
| 2 | heavy_blow | 64 | 339 | 22.95% |
| 3 | critical_eye | 78 | 417 | 28.23% |
| 4 | precise_strike | 92 | 509 | 34.46% |
| 5 | glass_cannon | 100 | 609 | 41.23% |
| 6 | heavy_critical | 120 | 729 | 49.36% |
| 7 | light_attack | 138 | 867 | 58.70% |
| 8 | sharpened_edge | 166 | 1,033 | 69.94% |
| 9 | critical_power | 191 | 1,224 | 82.87% |
| 10 | critical_momentum | 28 | 1,252 | 84.77% |
| 11 | first_strike | 28 | 1,280 | 86.66% |
| 12 | overclock | 22 | 1,302 | 88.15% |
| 13 | critical_training | 23 | 1,325 | 89.71% |
| 14 | brutal_force | 27 | 1,352 | 91.54% |
| 15 | last_stand | 25 | 1,377 | 93.23% |
| 16 | escalation | 27 | 1,404 | 95.06% |
| 17 | battle_focus | 30 | 1,434 | 97.09% |
| 18 | critical_engine | 10 | 1,444 | 97.77% |
| 19 | critical_conversion | 7 | 1,451 | 98.24% |
| 20 | growth_engine | 5 | 1,456 | 98.58% |
| 21 | momentum | 5 | 1,461 | 98.92% |
| 22 | brutal_critical | 5 | 1,466 | 99.26% |
| 23 | double_strike | 4 | 1,470 | 99.53% |
| 24 | boss_devourer | 3 | 1,473 | 99.73% |
| 25 | follow_up_strike | 2 | 1,475 | 99.86% |
| 26 | overflow | 2 | 1,477 | 100.00% |

後段の限界増加は前段の対応keyと組合せで2・3 key手札を解放するので、最初の「単独原因」より増え得る。全26 key対応時の100%はあくまで`unsupported_card`を無視した構造計数であり、実装の完了・PEの有効性を意味しない。

### 目標率に到達するgreedy prefix

| 目標 | このgreedy順で初めて到達する段階・率 | 必要なkey集合（この順序でのprefix） |
|---:|---|---|
| 30% | 4 key、509/1,477 = 34.46% | steady_force, heavy_blow, critical_eye, precise_strike |
| 50% | 7 key、867/1,477 = 58.70% | 上記4 + glass_cannon, heavy_critical, light_attack |
| 70% | 9 key、1,224/1,477 = 82.87% | 上記7 + sharpened_edge, critical_power |
| 80% | 9 key、1,224/1,477 = 82.87% | 70%と同じ9 key |

8 key時点は1,033/1,477 = **69.94%**で、70%にはわずかに届かない。これらは**greedy経路上**で必要なkey集合であり、全組合せを探索した最小個数の証明ではない。将来のPE有効性・CardValue化の難易度は対象に入れない。到達Waveや成功率の優劣もこの集計から判断しない。
