# Incremental Roguelite

> **「その選択で、強さの桁が跳ね上がる。」**

超インフレする数値と、Runごとのビルド形成を組み合わせた
**Incremental × Roguelite** の個人制作ゲームです。

現在は **Godot / GDScript** でプロトタイプを開発しています。

---

## Game Concept

敵を倒してXPを獲得し、Level UpでCardを選び、
Weapon・Relic・恒久強化を組み合わせながら
Damageを指数的に伸ばしていきます。

第一段階の目標は:

- **First Prestige: Wave 5000**
- **Wave 5000 Boss HP: 1e308**
- 第一転生までの標準的な実プレイ時間: **中央値12時間以下**

```text
Manual Attack
    ↓
Enemy Defeat / XP
    ↓
Level Up
    ↓
Card Pick
    ↓
Weapon / Build Growth
    ↓
Death / Permanent Progression
    ↓
Retry
    ↓
Wave 5000 / First Prestige
```

---

## Current Godot Prototype

現在GitHubに反映済みの主な機能:

- Manual Attack
- Enemy HP / Wave / Time Limit
- Death / Retry
- WeaponData Resource
- Wave 10での初Weapon 2択
- Weapon取得後のAuto Attack
- CardData Resource
- Card 3択UI
- Manual Attack / Auto Attack / Attack Speed系Card
- XP / Level
- Level Up → Card Pick
- Card効果の反映

現在の次タスクは **Pending Picks** です。

Level Upが連続してもCard Pick権を失わず、
戦闘を止めずに後から処理できる形を目指しています。

---

## Design Principles

このゲームでは、単純に情報量を増やすのではなく
「成長を見て、必要な瞬間だけ介入する」感覚を重視しています。

特に現在は次の方針で設計しています。

- Run開始時はManual Attackのみ
- 最初のWeapon取得でAuto Attack解禁
- Auto Attack解禁後もManual Attack可能
- Card Pick中も戦闘を停止しない
- 未処理Card PickはPending Picksとして蓄積
- Weapon装備は1枠
- Relic装備は3枠
- Player-facing UIに **DPS / TTK / 勝敗予測を表示しない**
- Enemy HPとRemaining Timeを見て判断できるようにする

---

## Development Approach

企画 → 試作 → 問題発見 → 再設計 → 実装確認、
という小さなサイクルで進めています。

過去にはWebベースのシミュレーター / プレイテストも作成しましたが、
現在は **Godot版をゲーム本体として再構築**しています。

旧Wave 10000仕様や過去の実験結果は削除せず、
現行仕様と混同しない形でLegacy / Referenceとして保存しています。

---

## Tech Stack

- Godot 4
- GDScript
- Python
- Git / GitHub

AIは企画壁打ち・実装補助・レビュー・ドキュメント整理に利用していますが、
ゲーム仕様の採否、実装確認、プレイテスト上の判断は自分で行う方針です。

---

## Documentation

現行の開発情報は以下を基準に管理しています。

- [Game Specification](docs/GAME_SPEC.md) — 現在採用しているゲーム仕様
- [Current State](docs/CURRENT_STATE.md) — 現在の実装状況
- [Decisions](docs/DECISIONS.md) — 設計判断と理由
- [Roadmap](docs/ROADMAP.md) — 今後の実装順
- [AI / Contributor Rules](AGENTS.md) — AI共通の開発ルール

詳細な過去ログは `docs/HANDOFF.md` に保存しています。

---

## Repository Structure

```text
Incremental/
├─ godot/                  # 現在のゲーム本体
├─ docs/                   # 仕様・判断・ロードマップ
├─ first-prestige-playtest/ # 過去のWeb試作
├─ scripts/                # 検証・補助スクリプト
└─ AGENTS.md               # AI共通ルール
```

---

## Status

**Work in progress / 開発中**

現在はコアループをGodot上で成立させる段階です。

次の短期目標:

```text
Pending Picks
→ Random 3-card Draft
→ XP / Enemy Growth
→ W1–100 Vertical Slice
→ DP / Equipment
→ W5000 / First Prestige
```
