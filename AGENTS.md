# AI共通の開発ルール

このファイルは Codex / ChatGPT / Antigravity / その他AIの共通入口。
詳細仕様や履歴そのものはここへ詰め込まない。

## 作業開始時に読む順番

1. [docs/GAME_SPEC.md](docs/GAME_SPEC.md)
2. [docs/CURRENT_STATE.md](docs/CURRENT_STATE.md)
3. [docs/DECISIONS.md](docs/DECISIONS.md)
4. [docs/ROADMAP.md](docs/ROADMAP.md)

過去の細かい経緯が必要な場合だけ
[docs/HANDOFF.md](docs/HANDOFF.md) を参照する。

---

## 現在の系列

現在のゲーム本体として開発している対象:

- **Godot版**
- **First Prestige = Wave 5000**
- **Wave 5000 Boss HP = 1e308**

以下を現行仕様と混同しない。

- `first_prestige_v1_spec.md` — 旧formal Wave 10000
- formal Variant D/E — 別実験系列
- `first-prestige-playtest/` — Webベース試作
- 過去のW5000診断 / CardValue実験 — 検証資料

Legacyから仕様を採用する場合は、
先に `GAME_SPEC.md` へ明示的に反映する。

---

## 仕様変更ルール

- `GAME_SPEC.md` を現在仕様の正本とする
- AIが仕様を勝手に変更しない
- 未確定事項を推測で確定しない
- 矛盾を見つけた場合は、根拠を示して確認する
- 実装だけ変えて仕様書を置き去りにしない

更新先:

- 仕様が変わった → `GAME_SPEC.md`
- 実装状況が変わった → `CURRENT_STATE.md`
- 設計判断を確定した → `DECISIONS.md`
- 次の実装順が変わった → `ROADMAP.md`
- 詳細な作業ログ → 必要な場合だけ `HANDOFF.md`

---

## 現行Godotの重要ルール

- Run開始時はManual Attackのみ
- 初Weapon取得でAuto Attack解禁
- Auto Attack解禁後もManual Attack可能
- Weapon装備1枠
- Relic装備3枠
- Card Pick中も戦闘を止めない
- Pending Picksを蓄積する
- Player-facing UIにDPS / TTK / 勝敗予測を表示しない
- Enemy HP / Remaining Timeは表示する
- 第一転生までの実プレイ時間は中央値12時間以下を目標とし、明確に遅くする調整をしない

---

## 実装ルール

- 小さい変更から進める
- 関連箇所を確認してから編集する
- 既存挙動を壊す大規模変更を一度に行わない
- Resource / Scene / Signal等のGodot構造を尊重する
- null / 未設定Resourceに対する安全処理を入れる
- Debug用情報とPlayer-facing UIを区別する

ゲームBalanceやシミュレーションでは:

1. Unit / regression test
2. Small smoke test
3. Small trial / seed
4. 必要な場合のみ大規模試行

の順で確認する。

---

## Git安全ルール

- `git status --short` の `??` を不要ファイルと決めつけない
- ユーザーの未保存・未追跡作業を勝手に削除しない
- unrelatedな変更を勝手にcommitへ混ぜない
- force pushしない
- 変更前後でdiffを確認する
- 生成物・save・一時ファイルを無断で追加しない

---

## 作業終了時

最低限、

- 何を変更したか
- 何を確認したか
- 残っている問題
- 次の一手

を `CURRENT_STATE.md` または必要な文書へ反映する。

詳細な履歴を残す必要がある作業だけ `HANDOFF.md` に追記する。
