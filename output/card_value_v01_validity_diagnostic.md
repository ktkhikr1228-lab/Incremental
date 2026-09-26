# shadow CardValue v0.1 人工代表状態の妥当性診断

既存の`card_value_v01.py`と正式v1の戦闘関数を読み込み、評価ロジック・ゲーム本体の選択経路は変更せずに診断した。全状態は人工的な制御例であり、Weapon Powerは各Waveの戦闘余裕を調整するための入力値（実際のドロップ分布ではない）。Power Up/Rapid FireはW50でstackだけを変更。ExecutionはW500 Boss（15秒）、Time CollapseはW501通常敵（10秒）の同一Waveで装備Powerを変えた。XPはW15/501/7501で各21遭遇を固定し、次Level-upのXP Costに近い/遠い状態を比較した。

共通の列：Immediate/Conditional/Growth/XP/TotalはPE。terminal Δpは未校正の突破確率プロキシで、Totalに含まない。予測終端・信頼度は候補適用前のbaseline rollout。

| 群 | 状態 | Wave | 候補 | legacy_score | Immediate | Conditional | Growth | XP | Total | terminal Δp | confidence |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| Power Up stacks | 0 stack | 50 | power_up | 0.6000 | +0.0969 | +0.0000 | +0.0000 | +0.0000 | +0.0581 | +0.2256 | low |
| Power Up stacks | 5 stack | 50 | power_up | 0.6300 | +0.0458 | +0.0000 | +0.0000 | +0.0000 | +0.0275 | — | low |
| Power Up stacks | 20 stack | 50 | power_up | 0.7000 | +0.0177 | +0.0000 | +0.0000 | +0.0000 | +0.0106 | — | low |
| Rapid Fire stacks | 0 stack | 50 | rapid_fire | 0.6000 | +0.0792 | +0.0000 | +0.0000 | +0.0000 | +0.0475 | +0.1695 | low |
| Rapid Fire stacks | 5 stack | 50 | rapid_fire | 0.6300 | +0.0414 | +0.0000 | +0.0000 | +0.0000 | +0.0248 | — | low |
| Rapid Fire stacks | 20 stack | 50 | rapid_fire | 0.7000 | +0.0170 | +0.0000 | +0.0000 | +0.0000 | +0.0102 | — | low |
| Execution wall | 余裕あり | 500 | execution | 1.1962 | +0.0000 | +0.0862 | +0.0000 | +0.0000 | +0.0517 | — | low |
| Execution wall | 制限時間直前・成功 | 500 | execution | 1.1962 | +0.0000 | +0.0862 | +0.0000 | +0.0000 | +0.0517 | — | low |
| Execution wall | 壁・時間切れ | 500 | execution | 1.1962 | +0.0000 | +0.0862 | +0.0000 | +0.0000 | +0.0517 | +0.2005 | medium |
| Time Collapse wall | 余裕あり | 501 | time_collapse | 1.3200 | +0.0000 | +0.4150 | +0.0000 | +0.0000 | +0.2490 | — | low |
| Time Collapse wall | 制限時間直前・成功 | 501 | time_collapse | 1.3200 | +0.0000 | +0.4150 | +0.0000 | +0.0000 | +0.2490 | — | low |
| Time Collapse wall | 壁・時間切れ | 501 | time_collapse | 1.3200 | +0.0000 | +0.4150 | +0.0000 | +0.0000 | +0.2490 | +0.5046 | medium |
| XP 序盤 | 閾値直前 | 15 | experience | 0.1500 | +0.0000 | +0.0000 | +0.0000 | +0.0425 | +0.0064 | — | low |
| XP 序盤 | 閾値遠方 | 15 | experience | 0.1500 | +0.0000 | +0.0000 | +0.0000 | +0.0386 | +0.0058 | — | low |
| XP 中盤 | 閾値直前 | 501 | experience | 0.1500 | +0.0000 | +0.0000 | +0.0000 | +0.0045 | +0.0007 | — | low |
| XP 中盤 | 閾値遠方 | 501 | experience | 0.1500 | +0.0000 | +0.0000 | +0.0000 | +0.0000 | +0.0000 | — | low |
| XP 終盤 | 閾値直前 | 7501 | experience | 0.1500 | +0.0000 | +0.0000 | +0.0000 | +0.0136 | +0.0020 | — | low |
| XP 終盤 | 閾値遠方 | 7501 | experience | 0.1500 | +0.0000 | +0.0000 | +0.0000 | +0.0000 | +0.0000 | — | low |

## 戦闘境界の実測（同じ人工状態の現行戦闘式）

| 候補 | 状態 | 制限 | 候補前TTK | 候補後TTK | baseline終端 | H遭遇数 |
|---|---|---:|---:|---:|---:|---:|
| execution | 余裕あり | 15.0s | 1.23s | 1.23s | 500 | 1 |
| execution | 制限時間直前・成功 | 15.0s | 14.12s | 11.66s | 500 | 1 |
| execution | 壁・時間切れ | 15.0s | 時間切れ | 12.28s | 500 | 1 |
| time_collapse | 余裕あり | 10.0s | 1.23s | 1.23s | 501 | 1 |
| time_collapse | 制限時間直前・成功 | 10.0s | 9.82s | 6.14s | 501 | 1 |
| time_collapse | 壁・時間切れ | 10.0s | 時間切れ | 6.75s | 501 | 1 |

## 期待関係の判定

| 関係 | 判定 | 根拠・解釈 |
|---|---|---|
| Power Upの限界Immediate/Totalは0>5>20 | 成立 | legacyは逆にstackに伴い上昇する。 |
| Rapid Fireの限界Immediate/Totalは0>5>20 | 成立 | 加算ASの逓減を反映。 |
| Executionの余裕あり/壁付近でConditionalが高まる | 不成立／尺度上の制約 | 全制限時間の積分余裕差なので、敵HPの違いは前後差で相殺される。 |
| Execution壁でterminal Δpは正 | 成立 | 壁時のみ突破確率プロキシが正。余裕ありではbaselineに失敗frontierがなく値はなし。 |
| Time Collapseの余裕あり/時間切れ寸前でConditionalが高まる | 不成立／尺度上の制約 | 全制限時間積分の比が同じなら、実際の撃破時間が違っても同じPEとなる。 |
| Time Collapse壁でterminal Δpは正 | 成立 | ただしterminal PEはTotalに加算しない。 |
| XPは各段階で閾値直前>遠方 | 成立 | 追加Draftの発生時期に敏感。 |
| XP追加DraftはXP軸だけでGrowth 0 | 成立 | 重み0.15は最終合成で一度だけ。 |
| XP序盤>中盤>終盤が必ず成り立つ | 不成立／段階間の単調性は非要件 | 異なるCost/レアリティプールなので単調性を要求できない。この人工状態では終盤が中盤を上回る。 |

## 監査上の結論

- Power UpとRapid Fireの現在状態での限界逓減は期待どおり。旧scoreのstack連動加点とは逆方向である。
- Execution/Time Collapseは即時Power差0でも正のConditional PEを返す。一方、同Waveで敵HPだけを調整した余裕戦闘と壁戦闘のConditional/Totalはほぼ同一。実際のTTK・勝敗差はTotalに反映されず、terminal Δpのみが一部区別する。terminalは未校正で非加算のため、**v0.1の判断scoreとしては時間・壁感度が不足**。
- Executionの「壁・時間切れ」はfull-time marginが約+0.0058 PEでも実際は離散Hitの切り上げにより失敗する。continuous marginだけでは境界を正しく判定できず、terminal Δp（シグモイド近似）もそのまま実際の突破確率としては解釈できない。
- XPは閾値直前が遠方より大きく、XP軸へ限定される。ただし序盤・中盤・終盤を同じ絶対値で単調比較する根拠はない。終盤のWeapon Powerはテスト用調整値であり、実Runの到達予測と混同しない。
- 全例のconfidenceは、将来ランダム装備・未取得カード系列を予測しないためlow（直近失敗ケースのみmedium）。terminal Δp自体も温度未校正のプロキシである。

詳細値・入力Weapon Power・TTK: [`card_value_v01_validity_diagnostic.csv`](card_value_v01_validity_diagnostic.csv)。
