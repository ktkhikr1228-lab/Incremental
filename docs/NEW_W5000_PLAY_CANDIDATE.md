# 新W5000手動プレイ候補 接続状況（2026-10-04）

## 実行系列

Figma Mainの開始は`equipmentMode=true`で`EquipmentSession` → `NewW5000Session`を使用。
旧W1–500手動プレイは`equipmentMode=false`の`PlaySession`として保存。
formal W10000、Variant D/E、既存w5000_v1 scaffoldの既定、CardValue 9-keyは変更なし。

新カードプローブ系列を接続した候補であり、旧formalカードを使うw5000_v1後半診断baselineとは別系列。
後半診断のEscalation / Infinite Barrage / base-heavy Devourerをこの新カード集合に混ぜない。
正式採用・12時間調整完了・W5000成功率確認を意味しない。

## 接続済み

- target W5000、Enemy Power W5000=308。W1–2500旧formal、以降3倍圧縮。
- 新C10 / U10 / R12 / E8 / L8定義。Relic Apotheosisは未接続のため自然候補から除外、残り47枚。
- 既存newカード/DP calculatorのpure数式を明示した依存引数で再利用。実験install/monkeypatchは呼ばない。
- unique・Crit排他、Limit Break、Crit/Multi-Crit、Hit Count、Supplemental、FU、Re-Action。
- Recursive FUは現在FU率（cap90%）、Endless Actionは現在率（最低15%、cap80%）。capは固定確率ではない。
- Overload Burn、Singularity、取得時Weapon Mitosis Offshoot、Knowledge Collapse所持非unique Echo、Supplemental Inversion。
- 通常XP Draft、W25 U / W100 R / W500 E別枠。W2500旧確定Legendaryなし。
- rarityは現在Run Waveを参照。L率W500未満0、W500–2499=0.1%、以降0.5%をCから移す候補。Luckは重みに作用。
- 初期カードは全合法候補を選べる。RerollはRun共通1回、W400買い切りで+1。推薦は即時Power差のみで自動選択しない。CardValue未使用。
- BC DP：各項目cost=`ceil(8 × itemWeight × 1.065^itemLv)`。ATK28% / AS22% / XP14%乗算、Crit+5.5pt、Crit倍率+.140、Weapon ATK28%乗算。
- DP v0.1のunlock / Luck / Find / Quality。既存候補の死亡計算を再利用：`9+floor(kills/11)`＋未取得25Wave checkpoint×3＋そのRunのBig Boss撃破数×3。checkpoint報酬も死亡精算、同じ壁の通常死亡DP減衰なし。
- DP手動購入。旧totalLv戦闘倍率・Rare率・初期カードPt・旧攻撃間隔強化は不使用。
- 個体武器Drop Normal1% / Boss10%＋既存候補Soft Pity、Find・rarity・通常Affix・Quality。W10初回C保証と死亡後次Boss回収保証は別。
- Weapon Base ATKはB_mediumアンカーを使用、Drop時のみ更新。W2500以降の未決曲線は最終5e7に据え置き、旧Weapon Powerを代用しない。
- 装備1＋保管5、遺物装備3＋保管5、強化・炉・同名処理。死亡武器50%回収、遺物・素材・DP保持。
- Salvager / Salvage Expertの分解Pt、DP Qualityの通常Affix最低roll改善。Pityに対するSalvage Expertのslight boostは未接続。
- W100初回学習レンズのXP効果は新Knowledge Conversionにも反映。
- Time Collapse / First Strike / Last Standの候補temporal integral＋攻撃間隔への丸め、Execution閾値は離散攻撃で判定。
- 戦闘表示用HPは同じ計算のサンプル列。失敗戦を単に経過時間100%でHP0にしない。

## 未接続・延期

- 全遺物一覧/固有効果・W500以降ランダム遺物報酬、Relic Apotheosis。
- 武器種別・固有効果。今回Dropは剣、通常Affixのみ。
- Core、Unlimited Boost、Finale、late-DP抑制。後半診断用の旧カード系列と混ぜず別途統合が必要。
- Refinementはconfig上+1だが手動Refine UI/取得経路は未接続。旧カード精錬効果は借用しない。
- Game Speed恒久購入、Storage拡張、生成/振り直し、ディスク保存、転生後システム。
- 戦闘はシミュレーターの期待値モデル。Crit/FU/小数Hitを画面上で個別乱数抽選するゲーム本体ではない。

## 検証

2026-10-04操作改善後: カード選択・装備報酬・鞄・設定で戦闘を止めない。
選択権を蓄積し、open時抽選、閉じても同じ手札、死亡時破棄。カード/装備効果はsegment計算で経過時間・残HP・攻撃位相を保持して適用。
武器一覧比較、装備/保管/分解、鞄drag/drop、炉即分解、rarity色と所持カード説明を接続。
最新158 scripts tests / TypeScript / production build成功。追加9テストとブラウザ手動確認。
XP量/カード値の調整、スマホ専用UI、保存は今回は未実装。

149 scriptsテスト、TypeScript typecheck成功。新接続15件で47枚finite・preview state/RNG不変・DP/死亡/再挑戦・旧仕様隔離・保証・Reroll・Execution・FU cap・HP表示・高AS相対誤差を確認。
少数の手動ループ/合成checkpointのみ。新しい30/1000 trial balance測定なし。

`python -m unittest discover -s scripts -p 'test_*.py' -q`

`cd first-prestige-playtest; npm run dev -- --port 4173`
