# Incremental Roguelite

> **「完成したビルドの、その先を遊ぶ。」**
>
> **「壊れたビルドを、壊せるところまで壊す。」**

超インフレする数値とRunごとのBuild形成を組み合わせた
**Incremental × Roguelite** の個人制作ゲームです。

現在は **Godot 4 / GDScript** でPrototypeを開発しています。

---

## Concept

ローグライクでは、強いBuildが完成した頃にRunが終わってしまうことがあります。

このゲームではBuild完成を終点ではなく、
その先の指数的な成長へ入る起点として扱います。

第一段階の目標:

- **First Prestige: Wave 5000**
- **Wave 5000 Boss HP: 1e308**
- 第一転生までの標準的な実プレイ時間: **中央値12時間以下**

---

## Core Direction

```text
Manual Attack
↓
Enemy Defeat / XP
↓
Card / Weapon / Shop
↓
Build Growth
↓
Death
↓
DP / Relic等のPermanent Growth
↓
Retry
↓
Wave 5000 / First Prestige
```

設計上の重要ルール:

- Run開始時はManual Attack
- First WeaponでAuto Attack解禁
- Auto後もManual Attack可能
- Weapon装備1枠
- Relic装備3枠
- Card / Backpack操作でCombatをなるべく止めない
- Player-facing UIにDPS / TTK / 勝敗予測を表示しない
- Enemy HP / Remaining Timeは表示する
- Coin / ShopをCard強化・Relic購入等の成長軸として検討中

---

## Current Development Status

現在のGodot mainには、

- Manual Attack
- Enemy HP / Wave / Timer
- Weapon Resource / First Weapon Choice
- Auto Attack
- Card Resource / 3-choice UI
- XP / Level
- Card Effect

が存在します。

一方で、Death / RetryのSignal接続とPending Picksは最新mainで未完成です。

過去の `codex/run-reset-fixes` Branchには修正案がありますが、
現在のmainとはdivergeしているため、そのままmergeせず再統合・人間確認を行います。

---

## Current Design Topics

現在特に整理中:

- Level UpとCard Pickの関係
- Pending Picks
- Coin / Shop
- Card Upgrade
- Backpack UI
- DP / Permanent Progression
- Weapon / Relic
- W1–100 Vertical Slice

詳細は現行仕様を参照してください。

---

## Documentation

- [Current Game Specification](docs/GAME_SPEC.md) — **現行仕様の正本**
- [Current State](docs/CURRENT_STATE.md) — 現在の実装状態・既知問題
- [Roadmap](docs/ROADMAP.md) — 次の作業順
- [Decisions](docs/DECISIONS.md) — 設計判断と履歴
- [Index](docs/INDEX.md) — 現行 / 実験 / Legacyの分類
- [AI / Contributor Rules](AGENTS.md) — AI共通ルール

詳細な過去ログは `docs/HANDOFF.md`。
実験は `docs/experiments/`、旧仕様は `docs/archive/` に保存しています。

---

## Tech Stack

- Godot 4
- GDScript
- Python
- Git / GitHub

AIは企画壁打ち、実装補助、レビュー、テスト、ドキュメント整理に利用しています。
仕様の採否、Godot上の動作確認、プレイテスト上の判断は人間が行う方針です。

---

## Repository Structure

```text
Incremental/
├─ godot/                   # 現在のゲーム本体
├─ docs/                    # 現行仕様・判断・Roadmap
│  ├─ experiments/          # Balance / CardValue等の実験
│  └─ archive/              # 旧formal仕様
├─ first-prestige-playtest/ # 過去のWeb試作
├─ scripts/                 # 検証・補助Script
├─ output/                  # 実験結果
└─ AGENTS.md                # AI共通ルール
```

---

## Status

**Work in progress / 開発中**

現在の最優先:

```text
Core Loop Repair
→ Death / Retry
→ Pending Picks
→ Card / Shop仕様確定
→ Random Draft / XP
→ W1–100 Vertical Slice
→ DP / Equipment
→ W5000 / First Prestige
```
