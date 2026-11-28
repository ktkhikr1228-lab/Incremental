# ROADMAP — Current Godot / W5000 Development

最終更新: 2026-11-29

仕様正本: `GAME_SPEC.md`
実装状態: `CURRENT_STATE.md`

現在は「機能数を増やす」より、
**最新mainでCore Loopを正しく動かし、その上でCard / Shop構造を確定すること**を優先する。

---

## Phase 0 — Core Loop Repair

### 0-1. Death / Retry

- EnemyTimer timeout Signalを接続
- RetryButton pressed Signalを接続
- RetryButtonへ見えるTextを設定
- StatusLabelを状態表示専用にする
- Death時にBattle / Choice stateを正しく停止・破棄
- Retryを新Runとして初期化

確認項目:

```text
Time 10 → 0
→ Defeated
→ Retry表示
→ Retry
→ Wave 1 / Level 1 / XP 0 / Weaponなし / Run Cardなし
```

### 0-2. Pending Picks

- 最新mainへPending Picksを統合
- Level UpごとにPick権を+1
- 選ばなくてもCombat継続
- 1枚取得ごとに-1
- 0でChoice UIを閉じる
- Death時破棄
- `PICK ×N` をPlayerが確認できるようにする
- Rapid double clickで意図せず複数Pick消費しない

### 0-3. Weapon / Card Collision

- W10等でWeapon ChoiceとCard Choiceが重なる場合はWeapon優先
- Card Pick権は失わない
- Weapon選択後にCard Choiceへ戻る

**Phase 0完了条件:**
Godot上で人間が一連の流れを再現し、既知のCore Loop bugがない。

---

## Phase 1 — Card / Level / Shop Specification

実装前に以下を決める。

- Level UpごとにCard Pickを出すか
- 一定Levelごとにするか
- Shop中心に寄せるか
- Pending Picksをどこまで残すか
- Coinの入手源
- Coinの主な使い道
- Shop更新条件
- Card強化方式
- Relic販売方法

現時点の方向:

```text
Combat
→ XP / Coin
→ Level / Card / Shop
→ Build Growth
→ Weapon / Relic / Upgrade
→ higher Wave
```

Coin用途候補:

- Card強化
- Relic購入
- Shop更新

---

## Phase 2 — Random Card Draft / XP

仕様確定後:

- Card PoolからRandom 3-choice
- 同一3択の重複回避
- Pool不足 / null安全処理
- XP余剰持ち越し
- 複数Level Up
- 初期XP curve

**Phase 2完了条件:**

```text
Enemy Defeat
→ XP
→ Level Up
→ Pending / Draft
→ Card Effect
→ Combat continues
```

が破綻しない。

---

## Phase 3 — W1–100 Vertical Slice

短時間でもゲームの核を説明・試遊できる状態を作る。

- Enemy HP curve初版
- Boss初版
- First Weapon保証
- Card Pool拡張
- Crit等の基礎戦闘要素
- Coin / Shop初版
- Death → Retry → Permanent growth導線
- Main UI整理
- Backpack UIラフ検証

この段階ではBalance完成より、
「Buildが変わる」「強くなって再挑戦できる」を優先する。

---

## Phase 4 — Permanent Progression / Equipment

- DP獲得
- DP Upgrade
- Weapon Drop
- Weapon Inventory / Storage
- Relic 3 slots
- Relic retention
- Furnace / Materials
- Weapon / Relic Upgrade
- Save / Load最小版

旧Web試作の値は自動移植しない。

---

## Phase 5 — Mid Game / W500–2500

- Card rarity
- Weapon固有効果
- Relic固有効果
- Luck / Find / Quality
- Backpack本実装
- Shop拡張
- 操作量削減
- Automation必要性を検証
- W2500までの成長曲線

---

## Phase 6 — W2500–5000 / First Prestige

確定条件:

- First Prestige = **Wave 5000**
- W5000 Boss HP = **1e308**
- 第一転生までの標準プレイ時間 = **中央値12時間以下**

作業:

- 後半の指数成長構造
- 後半Wall / Recovery設計
- First Prestige処理
- Prestige Reset
- Prestige後への最低限の導線

---

## Phase 7 — UI / UX Refinement

UIはGame Systemが固まるまで完全固定しない。

特に検討:

- Compact Card UI
- Pending Pick表示
- Backpack 6分割
- Top-center Shop
- Weapon / Relic access
- Card / Shopの操作量
- 戦闘を隠しすぎない画面構成

原則:

- Card / Backpack操作でCombatを止めない
- Main UIへDPS / TTK / 勝敗予測を出さない
- Enemy HP / Remaining Timeは見せる

---

## Priority

### Must

1. Core Loopを壊さず遊べる
2. 仕様と実装を混同しない
3. Card / Shopの役割を確定する
4. W1–100でBuild形成を体験できる
5. Death / RetryにPermanent growthの意味を持たせる

### Later

- 全Card / Weapon / Relic完成
- Full W5000 Balance
- Offline Progression
- Automation
- Prestige後コンテンツ
