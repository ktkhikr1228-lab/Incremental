# 現在の状態

最終更新: 2026-11-29

この文書は「いま何を作っていて、実装がどこまで動いているか」を示す。
仕様正本は `GAME_SPEC.md`、判断履歴は `DECISIONS.md`、次作業は `ROADMAP.md`。

---

## 1. 現在の開発対象

- Engine: **Godot 4 / GDScript**
- Current game target: **First Prestige at Wave 5000**
- Wave 5000 Boss HP: **1e308**
- 第一転生までの標準的な実プレイ時間: **中央値12時間以下**
- Godot版を現在のゲーム本体として扱う
- 旧formal Wave 10000 / Web試作 / simulationはLegacy / Reference

現行仕様:
- `docs/GAME_SPEC.md`

正式なGodot開発先:
- `C:\Users\katao\Incremental\godot`

---

## 2. origin/main のGodot Prototype

2026-11-29確認時の `main` HEAD:

```text
29e4a54
```

mainの `godot/main_2d.gd` に存在する主な機能:

- Manual Attack
- Enemy HP
- Wave進行
- Enemy Timer
- WeaponData
- Wave 10での初Weapon 2択
- Weapon取得後のAuto Attack
- CardData
- Card 3択Panel
- Manual / Auto / Attack Speed系Card Effect
- XP
- Level
- Level Up → Card Choice

---

## 3. 現在確認できている問題

### Enemy Timer / Retry

mainの `main_2d.tscn` には現時点で、

- `EnemyTimer.timeout -> _on_enemy_timer_timeout`
- `RetryButton.pressed -> _on_retry_button_pressed`

のSignal接続が存在しない。

そのため実機確認では、
Enemy Timerが0になってもDeath処理へ入らず **10秒へ戻って再カウント** する状態を確認した。

またScene上では、

- `RetryButton` 自体のTextが空
- `StatusLabel` 初期Textが `Retry`

となっており、見えている「Retry」と押せるButtonが一致していない。

### Pending Picks

`origin/main` にはPending Picks本体がまだ入っていない。

未処理数を `PICK ×N` として見せるUIもmainには存在しない。

---

## 4. codex/run-reset-fixes Branch

過去に以下を実装したBranchがある。

```text
codex/run-reset-fixes
```

含まれる主な内容:

- Pending Picks
- Death / Retry reset改善
- Timer / Retry Signal接続
- Weapon / Card choice衝突対策
- null guard
- Smoke test
- W10以前のLevel Up regression修正

ただし2026-11-29時点では、

```text
main に対して ahead 3 / behind 12
```

でdivergeしている。

そのままmainへmergeせず、
最新main上で必要変更を再適用またはrebaseし、Godotで人間が確認してから統合する。

---

## 5. Design側の現在地

実装より先に決まっている内容:

- First Prestige = W5000
- W5000 Boss HP = 1e308
- Manual → First Weapon → Auto
- ManualはAuto後も残す
- Weapon装備1枠
- Relic装備3枠
- Card Pick中も原則Combat継続
- DPS / TTK / 勝敗予測をPlayer UIへ出さない
- DeathでCard / Weapon / Pendingを失う方向
- DP / Relic / 一部素材を保持する方向
- Coin / Shopを成長軸として追加する方向
- ShopでCard強化 / Relic購入等を扱う方向

まだ未決定:

- Level UpとCard / Shopの役割分担
- Coin獲得量
- Shop更新条件
- Card強化方式
- Backpack最終UI
- Enemy / XP正式curve
- DP / Weapon / Relic正式Balance

---

## 6. 次にやること

新機能を積み増す前に、最新main上でCore Loopを安定させる。

優先順:

1. EnemyTimer timeoutをDeathへ接続
2. RetryButton pressedをRetry処理へ接続
3. RetryButton / StatusLabelの表示整理
4. Retry時のRun resetを仕様どおりにする
5. Pending Picksを最新mainへ統合
6. `PICK ×N` を画面で確認できるようにする
7. W10前Level Up / W10 Weapon競合 / Death / Retryを人間がGodotで確認
8. その後Card Draft / Shop設計へ進む

---

## 7. ドキュメント運用

1. `GAME_SPEC.md` — 現行仕様の正本
2. `CURRENT_STATE.md` — 実装状態・既知問題
3. `DECISIONS.md` — 判断理由・履歴
4. `ROADMAP.md` — 次の作業順
5. `HANDOFF.md` — 詳細な過去ログ
6. `docs/archive/` — 旧仕様
7. `docs/experiments/` — 実験

Legacyの内容は明示的に `GAME_SPEC.md` へ昇格させない限り現行仕様として扱わない。
