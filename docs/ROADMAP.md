# ROADMAP — W5000 Godot Development

最終更新: 2026-10-11

この文書は実装順と短期目標を管理する。
仕様の正本は `GAME_SPEC.md`。
完了状況は `CURRENT_STATE.md` に反映する。

---

## 0. 現在

目的: **Godotで最小のゲームループを完成させる**

現在:
- Manual Attack
- Weapon選択
- Auto Attack
- XP
- Level Up
- Card Pick
- Card Effect

次:
- Pending Picks

---

## 1. Core Loop

### 1-1. Pending Picks

- Level UpごとにCard Pick権を+1
- 未選択権を蓄積
- 選択中も戦闘継続
- 1枚選ぶごとにPendingを-1
- 0になったらCard UIを閉じる
- 死亡時に未使用Pickを破棄

### 1-2. Card Draft

- Card Poolからランダム3択
- 同一3択内の重複を避ける
- null / pool不足時の安全処理
- Card ResourceへID等を追加するか検討

### 1-3. XP

- 余剰XPを持ち越す
- 一度に複数Level Upできる構造
- 正式XP curveは後でBalance調整

**Core Loop完了条件**

```text
Enemy defeat
→ XP
→ Level Up
→ Pending Pick
→ 3-card Draft
→ Build growth
→ Combat continues
```

---

## 2. W1–100 Vertical Slice

目的: **短時間でもゲームとして説明・試遊できる状態**

- Enemy HP curveの初版
- Boss
- Wave 10 Weapon Choice
- Weapon Resource整理
- Weapon取得でAuto Attack解禁
- Card Poolを数枚から拡張
- Crit等の基礎戦闘要素を段階導入
- Death → Retry
- UIを最低限整理
- Debug表示とPlayer表示を分離

この段階でスクリーンショット / GIFをポートフォリオへ反映する。

---

## 3. Permanent Progression / Equipment

目的: **死亡と再挑戦に意味を持たせる**

- DP獲得
- DP強化
- Weapon Drop
- Inventory / Storage
- Weapon強化
- Relic 3装備枠
- Relic保持
- Death Reset Policyを実装
- 一部素材の保持
- Save / Loadの最小版

旧Web試作の仕様は参考にするが、
`GAME_SPEC.md` に採用した項目だけGodotへ入れる。

---

## 4. W500–2500

目的: **中盤の成長とビルド分岐を成立させる**

- Card rarity
- Rare / Epic / Legendaryの役割整理
- Weapon固有効果
- Relic固有効果
- Luck / Find / Quality等のDP
- Backpack / Equipment UI
- 操作量が増えすぎないようAutomation候補を検討
- W2500までの成長曲線をプレイテスト

---

## 5. W2500–5000 / First Prestige

目的: **第一転生まで完成**

確定:
- First Prestige = Wave 5000
- Wave 5000 Boss HP = 1e308
- 実プレイ時間中央値12時間以下

実装・検証:
- 後半成長構造
- W5000到達に必要な指数成長
- First Prestige処理
- Prestige時Reset
- Prestige後への最低限の導線

12時間を超える方向へBalanceを悪化させない。

---

## 6. Portfolio / Early Selection

提出期限: **2026-10-30 10:00**

### 10/11–10/18

- Core Loop完成
- W1–100 Vertical Sliceを進める
- GitHub docsを現行Godot基準へ整理
- 開発中スクリーンショットを保存

### 10/19–10/25

- DP / Equipment等を可能な範囲で接続
- README更新
- PortfolioのIncrementalページ更新
- Before / Afterや設計判断の図を作る

### 10/26–10/28

- 安定化
- clone → 起動確認
- スクリーンショット / GIF最終化
- GitHubを初見の人が追える状態にする
- 応募文面と作品説明を仕上げる

### 10/29

**提出可能状態を固定する日。**

新しい大型機能の追加を原則止め、
URL・文章・起動・公開範囲・誤字を確認する。

10/30朝の修正を前提にしない。

---

## 7. 優先順位

### Must

1. Core Loopが壊れず遊べる
2. Godot版がGitHubに反映されている
3. 何を作っているかREADMEから分かる
4. 設計判断を説明できる
5. PortfolioからGitHubへ辿れる

### Should

- W1–100のまとまった試遊
- Card / Weaponのビルド差
- DPによるRetry成長
- Screenshot / GIF

### Nice to have

- W5000まで完全に実時間で遊べる完成版
- 全Card / Weapon / Relic
- 完成UI
- Prestige後コンテンツ

早期選考では「未完成を隠す」より、
現状・判断・次の課題を明確に説明できることを優先する。
