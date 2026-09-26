# AI共通の開発ルール（OpenCode / Codex / ChatGPT）

作業開始時は [`docs/HANDOFF.md`](docs/HANDOFF.md) → [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) → [`docs/DECISIONS.md`](docs/DECISIONS.md) を読み、対象のspec・実装・直近の出力で再確認する。この文書は実装や仕様の代用品ではない。

1. **系列を混同しない。** 旧formal第一転生は [`first_prestige_v1_spec.md`](first_prestige_v1_spec.md) と `scripts/simulate_first_prestige_v1.py` の **W10000**。同ファイルのVariant D/Eは別設定のW5000。`scripts/simulate_new_w5000_*.py` は**別の新W5000候補プローブ**で、既存formalのメカニクスを借用するものがあってもカード・DP・武器等の設定を同一視しない。新W5000の個別レポートはW1000等の途中checkpoint実験も含み、W5000達成結果と解釈しない。結果を記すときは系列、設定、target/checkpoint、trial数、seedを明記する。
2. **specを勝手に変更しない。** 設計案・実装計画・現行コード・診断出力を区別する。矛盾や古い記述を見つけたら、根拠のパスとともに「要確認」としてHANDOFFへ記録し、ユーザーの決定なしに仕様を上書きしたり、既存の結果を新仕様に読み替えたりしない。
3. **small trial first。** 実装依頼がある場合も関連単体・回帰テスト → 少数seed/trialのスモーク → 指示された規模の対比較の順で進める。比較は同じ初期seed/条件でペア化し、分岐後のRNGや手札の一致を要求しない。10組のPE Takeパイロットから強さや成功率の優劣を結論にしない。
4. **candidate評価は本体のRNG/stateを汚染しない。** baselineは候補取得前のコピーから決定的に予測し、同じ判断の候補へ共通Hを使う。評価中に本体の`RunState`/`PermanentState`、本体`random.Random`、グローバルRNGを変更しない。候補ごとの仮適用もコピー上で行い、状態・RNG不変の既存テストで検証する。
5. **変更境界を守る。** CardValue v0.1は旧formal Balanced向け。`legacy`が既定、`pe`は最終Take順位限定。Reroll・Refine・UpgradeへPEを広げない。fallbackとPE評価の対象は**最終手札の合法Take候補のみ**（2026-09-26決定）。旧10組は全提示カード判定の履歴、合法候補限定のログ再集計は反実仮想であり、新仕様の実測値と混同しない。未対応/無効PEと旧scoreを混ぜない。未校正`terminal_pe`を`total_pe`へ足さない。変更は依頼された範囲に限定する。
6. 作業後は **[`docs/HANDOFF.md`](docs/HANDOFF.md)を更新**し、変更点、最新の検証結果、残課題、次の一手、再現コマンドを記す。関連するCURRENT_STATE/DECISIONSも事実が変わった場合だけ更新する。生成済み出力や他者の作業を無断で消したり上書きしたりしない。

共通テスト: `python3 -m unittest discover -s scripts -p 'test_*.py' -q`。必要なシミュレーションは小規模から開始し、出力先を明示する。リポジトリは現時点で大半がuntrackedのため、`git status --short`の`??`を不要ファイルとみなさない。
