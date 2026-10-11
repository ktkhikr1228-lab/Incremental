# Incremental Roguelite - Current Game Specification

> この文書を「現在開発しているゲーム」の仕様入口とする。
>
> 現在の実装対象は **Godot版 / 第一転生 Wave 5000**。
> 旧formal Wave 10000仕様や過去のWeb試作は履歴・比較資料であり、
> この文書より優先しない。

---

## 1. ゲーム概要

**ジャンル**  
Incremental Roguelite / インクリメンタル・ローグライト

**コンセプト**  
「壊れたビルドを、壊せるところまで壊す」

敵を倒して成長し、カード・武器・遺物・恒久強化などを組み合わせながら、
指数的に火力を伸ばしていく。

第一段階では **Wave 5000 の突破と第一転生** を目標とする。

### 第一転生

- Target: **Wave 5000**
- Wave 5000 Boss HP: **1e308**
- Wave 5000撃破で第一転生
- 第一転生後の詳細システムは未確定
- 第一転生までの実プレイ時間は **中央値12時間以下** を目標とする
- 12時間より短くなる調整は許容する
- 12時間を明確に超える調整は不可とする

---

## 2. 基本ゲームループ

```text
Run開始
↓
手動攻撃で敵を倒す
↓
XP獲得
↓
Level Up
↓
Card Pick
↓
武器・カード・遺物等でビルド成長
↓
より高いWaveへ進む
↓
死亡
↓
DPなどの恒久成長
↓
Retry
↓
Wave 5000
↓
First Prestige
```

戦闘と成長を繰り返し、
同じRunの中でもビルドが大きく変化することを重視する。

---

## 3. 戦闘

### 3.1 Manual Attack / 手動攻撃

Run開始時は手動クリック攻撃のみ使用可能。

プレイヤーがAttack操作を行うことで敵へDamageを与える。

最初の武器を取得した後もManual Attackは使用可能とする。

これにより、

- Auto Attackを眺める
- Manual Attackで追加Damageを入れる
- ギリギリの敵をクリックで押し切る

というプレイヤー介入を残す。

### 3.2 Auto Attack / 自動攻撃

最初の武器を取得するとAuto Attackが解禁される。

武器は主に、

- Damage
- Attack Interval

を持つ。

Attack Speed系の効果によって攻撃間隔を短縮できる。

### 3.3 Active

Active Skill / Active ActionはManual Attackとは別レイヤーとして扱う。

将来的にはCooldownを持つ強力な操作として実装する。
詳細は未決定。

### 3.4 Enemy

基本方針：

- 通常敵：制限時間10秒
- Boss：通常敵より長い制限時間を持つ
- 敵撃破後、次Waveへ進む

現在のGodotプロトタイプでは敵HP・Wave・制限時間を簡易値で検証している。

正式なEnemy HP curveは未確定。

---

## 4. XP / Level

敵撃破によってXPを獲得する。

必要XPへ到達するとLevel Upし、
Card Pickを1回得る。

余剰XPを持ち越せる構造を前提とする。

### Godot動作確認用の現在値

- 初期Level: 1
- 初期XP: 0
- テスト用必要XP: 3
- 敵撃破: +1 XP

これらは動作確認用であり正式Balanceではない。

---

## 5. Card System

カードはRun中の主要なビルド形成要素。

### 5.1 Card Pick

通常は3枚の候補から1枚を取得する。

Card Pick中も戦闘は停止しない。

カード選択によって戦闘時間・画面・注意を過度に奪わないことを
重要なUX方針とする。

### 5.2 Pending Picks

Level Up時にカードをすぐ選ばなくてもよい。

未使用のCard Pickは **Pending Picks / 未選択カード取得権**
としてRun内に蓄積する。

```text
Pending Picks = 2
↓
1枚取得
↓
Pending Picks = 1
↓
次の3択
↓
もう1枚取得
↓
Pending Picks = 0
↓
選択UIを閉じる
```

戦闘はこの間も継続する。

死亡時の未選択Card Pickは破棄する。

### 5.3 現在のGodotテストカード

システム確認用として以下を実装している。

- Manual Attack倍率
- Auto Attack倍率
- Attack Speed倍率

これは正式なCard Poolではない。

### 5.4 将来のCard Pool

現行W5000候補では以下の5段階を想定する。

- Common
- Uncommon
- Rare
- Epic
- Legendary

既存Web試作には多数の候補カードが存在するが、
Godot版へそのまま全採用するとは限らない。

カード内容・数値は別途整理する。

---

## 6. Weapon System

### 6.1 初武器

現在のGodotプロトタイプではWave 10到達時に初武器候補を提示する。

現在は2択による動作確認。

武器選択後、

- Auto Attack解禁
- Weapon Damage適用
- Attack Interval適用

となる。

### 6.2 Equipment Slot

- **武器装備：1枠**
- 武器保管：5枠を初期候補とする

装備1枠は確定。
保管枠拡張は将来要素。

### 6.3 将来の武器取得

W5000候補では個体武器Dropを採用候補としている。

候補値：

- Normal Drop率 1%
- Boss Drop率 10%
- Soft Pity
- Wave 10初回武器保証

Drop率等は正式Balanceではない。

### 6.4 Weapon Type

候補：

- Great Sword / 大剣
- Sword / 剣
- Dagger / 短剣
- Bow / 弓
- Spear / 槍

SpearはClick Attack系の固有効果を持たせる方向。

各武器種の最終数値・固有効果は未確定。

---

## 7. Relic System

RelicはWeaponとは別の装備成長要素。

### Equipment Slot

- **Relic装備：3枠**
- Relic保管：5枠を初期候補とする

装備3枠は確定。

基本方針：

- Relicは死亡しても保持
- 第一転生でリセット

既存候補にはWave到達報酬によるRelic取得案があるが、
Relic一覧・固有効果・Balanceは未確定。

---

## 8. Death / Retry

敵を時間内に倒せない等の条件でRun終了。

死亡後は即座に自動再挑戦せず、
プレイヤーがRetryを選択する。

### Reset Policy

基本方針はほぼ確定。

**死亡時に失う**

- Run内Card
- Weapon
- 未使用Card Pick

**死亡後も保持**

- DP
- Relic
- 一部素材

素材・装備強化・保管拡張などの細部は今後調整する。

---

## 9. DP / Permanent Progression

死亡時にDeath Point / DPを獲得する。

DPを使用してRunを跨ぐ恒久強化を行う。

現在の候補項目：

- Base Attack
- Attack Speed
- XP Gain
- Crit Rate
- Crit Multiplier
- Weapon Attack
- Luck
- Weapon Find
- Weapon Quality

既存W5000候補の数値は参考値とし、
Godot実装時に再検証する。

---

## 10. First Prestige

第一転生は以下を確定仕様とする。

- **Wave 5000**
- **Wave 5000 Boss HP = 1e308**
- Wave 5000撃破時にFirst Prestige
- 第一転生までの実プレイ時間中央値は **12時間以下**
- 12時間より短くなることは許容
- 12時間を超えて遅くする調整は不可

第一転生後のシステムは現在のGodot初期実装範囲外。

---

## 11. UI / UX Principles

### 11.1 戦闘を止めない

以下の操作では原則として戦闘を停止しない。

- Card Pick
- Backpack
- Equipment確認
- Settings

明示的なPause操作は別途用意可能。

### 11.2 Card UI

大量のカード選択によって
戦闘への注意・画面・操作時間を奪わない。

候補3枚をコンパクトに表示する。

取得権が複数ある場合でも、
同時に大量のカードUIを表示しない。

### 11.3 情報表示

**表示する**

- Enemy HP
- Wave
- Remaining Time
- XP
- Level
- Equipment
- Card Effect

**表示しない**

- DPS
- TTK
- 勝敗予測
- Kill Prediction

内部計算で使用することは可能だが、
プレイヤー向けMain UIには表示しない。

---

## 12. Godot Current Prototype

現在Godot版で実装・検証中。

### 実装済み

- Enemy HP
- Wave進行
- Time Limit
- Manual Attack
- Death
- Retry
- Wave 10 Weapon Choice
- Weapon Resource
- Auto Attack
- Card Resource
- Card Choice UI
- Manual Attack Card
- Auto Attack Card
- Attack Speed Card
- XP
- Level Up
- Level Up → Card Pick

### 作業中

- Pending Picks

### 次

- Card候補ランダム化
- XP必要量
- Enemy HP成長
- Card Pool拡張

### その後

- Weapon Drop
- DP
- Relic
- Equipment
- W5000 progression
- First Prestige

---

## 13. 仕様ステータス

### CURRENT / 現行

- Godotを現在のゲーム本体として開発
- First Prestige = Wave 5000
- Wave 5000 Boss HP = 1e308
- Weapon装備1枠
- Relic装備3枠
- Manual Attackから開始
- 初武器でAuto Attack解禁
- Manual Attackはその後も使用可能
- XP → Level → Card Pick
- Card Pick中も戦闘継続
- Pending Picks
- DPS / TTKをMain UIに表示しない
- 第一転生までの実プレイ時間中央値は12時間以下

### NEAR-FINAL / ほぼ確定

- Death時にCard / Weapon / 未使用Card Pickを失う
- DP / Relic / 一部素材を保持

### CANDIDATE / 暫定

- Card Pool内容
- DP数値
- Weapon Drop率
- Weapon / Relicの個別数値
- Enemy HP curve
- 武器・Relic保管枠の拡張Cost

### UNDECIDED / 未決定

- 第一転生後
- Active Skill詳細
- 正式なEnemy HP curve
- XP curve
- Card取得頻度
- Card Refinement
- 全Weapon固有効果
- 全Relic効果
- 後半Wave 2500～5000の成長構造
- Save仕様
- Automation解禁時期

---

## 14. Legacy / Reference

以下は現在仕様そのものではなく、
履歴・実験・比較用資料として扱う。

- `first_prestige_v1_spec.md`
  - 旧formal Wave 10000

- `first-prestige-playtest/`
  - WebベースのW5000手動試作

- `docs/NEW_W5000_PLAY_CANDIDATE.md`
  - 現行W5000設計の重要な参照元
  - ただし全項目が正式採用済みではない

- `docs/W5000_EQUIPMENT_V01.md`
  - Equipment初版候補

- `docs/HANDOFF.md`
  - 開発履歴・AI引き継ぎ倉庫

設計判断の理由は `docs/DECISIONS.md` を参照する。
