# Incremental Roguelite - Current Game Specification

> 最終更新: 2026-11-29
>
> この文書を **現在開発しているGodot版 Incremental Roguelite の仕様正本** とする。
> 旧formal Wave 10000、過去のWeb試作、各種simulationは履歴・比較・検証資料であり、この文書より優先しない。
>
> 仕様は以下の4段階で区別する。
>
> - **CONFIRMED**: 確定。勝手に変更しない
> - **DIRECTION**: 現在採用して進める方向。数値・細部は未確定
> - **CANDIDATE**: 候補。実装前に再確認する
> - **UNDECIDED**: 未決定

---

## 1. Game Concept

### ジャンル

**Incremental × Roguelite**

### 企画の原点

ローグライクでは、強いビルドが完成した頃にRunが終わってしまうことがある。
このゲームでは「ビルド完成」を終点ではなく、その先の超インフレへ入る起点として扱う。

### コンセプト

**「完成したビルドの、その先を遊ぶ。」**

プレイヤー体験としては、

**「壊れたビルドを、壊せるところまで壊す。」**

を目指す。

単に無限に数字が増えるだけではなく、
Run中のカード・武器・遺物・恒久成長などの組み合わせによって、
プレイヤーが自分のビルドを作り、そのビルドが指数的に壊れていく過程を遊ぶ。

**Status: CONFIRMED**

---

## 2. First Prestige / 第一転生

第一段階の明確な到達目標を第一転生とする。

- First Prestige: **Wave 5000**
- Wave 5000 Boss HP: **1e308**
- Wave 5000撃破で第一転生
- 第一転生までの標準的な実プレイ時間: **中央値12時間以下**
- 12時間より短くなる調整は許容
- 12時間を明確に超える方向への調整は不可

第一転生後のコンテンツは未決定。

**Status: CONFIRMED**

---

## 3. Core Game Loop

基本構造は次の通り。

```text
Run開始
↓
Manual Attack
↓
Enemy Defeat / XP / Coin等のRun内報酬
↓
Level / Card / Weapon / Shop等でBuild Growth
↓
Auto Attack解禁・Build拡張
↓
より高いWaveへ
↓
Death
↓
DP / Relic / 一部素材などのRun外成長
↓
Retry
↓
さらに高いWaveへ
↓
Wave 5000
↓
First Prestige
```

重要なのは、

- RunごとにBuildを作る
- Deathしても一部の成長が残る
- 再挑戦で前Runより強くなる
- Build完成後も指数成長が続く

という4点。

**Status: CONFIRMED / DIRECTION**

---

## 4. Combat

### 4.1 Manual Attack

Run開始時は **Manual Attackのみ**。

プレイヤー操作で敵へDamageを与える。

最初のWeaponを入手した後もManual Attackは残す。

目的:

- 序盤にプレイヤー自身が戦闘へ参加する
- Auto Attack解禁後も追加Damageを入れられる
- ギリギリの敵をクリックで押し切れる
- Manual特化Buildを成立させられる

**Status: CONFIRMED**

### 4.2 Auto Attack

最初のWeapon取得でAuto Attackを解禁する。

Weaponの基本パラメータ:

- Damage
- Attack Interval

Attack Speed系の効果によって攻撃間隔を変化させる。

**Status: CONFIRMED**

### 4.3 Active Action / Skill

Manual Attackとは別レイヤーの能動操作として扱う。

方向性:

- Cooldownあり
- Manual Attackより強力
- 常時連打ではなく、使うタイミングを選ぶ

効果・個数・解禁時期は未決定。

**Status: DIRECTION**

### 4.4 Enemy / Time Limit

通常敵は一定時間以内に倒す。

Godot初期Prototypeでは **10秒** をテスト値として使用している。

Bossは通常敵より長い制限時間を持たせる方向だが、正式値は未確定。

Enemy HP curveも正式値は未確定。

**Status: DIRECTION / CANDIDATE**

---

## 5. XP / Level

Enemy撃破でXPを得る。

Level UpはRun中の成長トリガーとして残す。

Godot動作確認用の現在値:

- 初期Level: 1
- 初期XP: 0
- 必要XP: 3
- Enemy defeat: +1 XP

これらはPrototype値でありBalance確定値ではない。

正式版では、

- XP余剰持ち越し
- 1回の処理で複数Level Up
- XP curve

を扱える構造にする。

### Level Upで何を得るか

従来案は **Level UpごとにCard Pick**。

ただし、Card選択頻度を減らすためShop / Coinを導入する方向が出ており、
Level UpとCard取得の最終関係は未確定。

候補:

- Level UpごとにCard Pickを維持
- 一定LevelごとだけCard Pick
- Level Upは小さなStat成長、CardはShop中心
- Level Up Pick + Shop強化の併用

**Status: XP/Level自体はCONFIRMED、報酬構造はUNDECIDED**

---

## 6. Card System

CardはRun内Build形成の主要要素。

### 6.1 Draft

基本形は **3枚から1枚を選択**。

Card選択中も戦闘は停止しない。

一度に大量の候補を表示せず、3択を1セットずつ処理する。

**Status: DIRECTION**

### 6.2 Pending Picks

Level Up等で得た未使用Card Pickを蓄積できる仕組み。

```text
PICK ×2
↓
3択から1枚取得
↓
PICK ×1
↓
次の3択
↓
1枚取得
↓
PICK ×0
```

戦闘は継続する。

死亡時、未使用Pickは失う。

この仕組みの目的は、
「カード選択を急かされる」「戦闘中にUIが何度も割り込む」問題を減らすこと。

ただしShop中心のCard取得へ寄せる場合は、Pending Picksの役割を縮小する可能性がある。

**Status: DIRECTION**

### 6.3 Prototype Card

Godot Prototypeには以下の3系統がある。

- Manual Attack倍率
- Auto Attack倍率
- Attack Speed倍率

正式Card Poolではない。

### 6.4 Rarity

候補:

- Common
- Uncommon
- Rare
- Epic
- Legendary

正式な出現率・効果・枚数は未確定。

**Status: CANDIDATE**

---

## 7. Coin / Shop

Card選択の頻度を抑えつつBuildを自分で伸ばすため、
**Coin + Shopを成長軸として採用する方向**。

### Coinの用途候補

- Card強化
- Relic購入
- Shop更新
- 将来のその他Run内成長

### Shop更新候補

- Coinを支払って更新
- 一定Wave到達で更新
- Boss撃破で更新
- 上記の組み合わせ

### Cardとの関係

弱いCardを引いて終わりではなく、
取得後のCardを強化できる余地を作る方向。

ただし以下は未決定:

- Card購入そのものをShopへ移すか
- Level Up Draftをどの程度残すか
- Shop更新頻度
- Coin獲得量
- Card強化Cost
- Relic購入Cost
- Boss時の更新ルール

**Status: DIRECTION、数値・統合方法はUNDECIDED**

---

## 8. Weapon System

### 8.1 Equipment

- Weapon装備: **1枠**

**Status: CONFIRMED**

### 8.2 First Weapon

Godot PrototypeではWave 10で最初のWeapon 2択を出している。

最初のWeaponを取得するとAuto Attack解禁。

Wave 10保証は有力な方向だが、正式BalanceとしてのWave値は再調整可能。

**Status: DIRECTION**

### 8.3 Storage

初期候補:

- Weapon保管: 5枠

保管拡張を将来成長にする案あり。

**Status: CANDIDATE**

### 8.4 Weapon Drop / Individualization

将来候補:

- Weapon Drop
- Rarity
- 個体差
- Affix
- 強化
- Quality / Find / Luckとの連動

過去候補値のDrop率は正式採用しない。

**Status: CANDIDATE**

### 8.5 Weapon Type

候補:

- Great Sword
- Sword
- Dagger
- Bow
- Spear

SpearはManual / Click Attack系の固有効果を持たせる方向。

**Status: CANDIDATE**

---

## 9. Relic System

RelicはWeaponとは別のBuild / Meta成長要素。

### Equipment

- Relic装備: **3枠**

**Status: CONFIRMED**

### Death / Prestige

方向性:

- Deathでは保持
- First Prestigeではリセット

### Storage

初期候補:

- Relic保管: 5枠

Relicの取得源・固有効果・強化・重複処理は未確定。

**Status: 装備3枠はCONFIRMED、その他はDIRECTION / CANDIDATE**

---

## 10. Death / Retry

Enemyを時間内に倒せない等でRun終了。

死亡後は自動再挑戦せず、プレイヤーがRetryを押す。

### Deathで失う

- Run内Card
- Weapon
- 未使用Card Pick
- その他Run限定Stack / Buff

### Death後も保持

- DP
- Relic
- 一部素材

素材・強化・Storageの細部は未確定。

### New Runの基準

Retry後は新しいRunとして、

- Wave 1
- Level 1
- XP 0
- Weaponなし
- Run Cardなし
- Run限定倍率 / Stackを初期化
- Pending Picks 0

へ戻す方向。

**Status: Reset方針はNEAR-CONFIRMED / DIRECTION**

---

## 11. DP / Permanent Progression

Death Point / DPをRunを跨ぐ恒久成長に使う。

候補項目:

- Base Attack
- Attack Speed
- XP Gain
- Crit Rate
- Crit Multiplier
- Weapon Attack
- Luck
- Weapon Find
- Weapon Quality
- Storage expansion

DPの獲得式・Cost curve・上限は未確定。

DPの役割は、

**Deathを失敗だけにせず、次Runの前進へ変えること。**

**Status: システム自体はDIRECTION、数値はUNDECIDED**

---

## 12. Backpack / Equipment UI

Backpackは装備・成長システムへアクセスするHubとして扱う。

現在の6分割ラフ方向:

```text
┌──────────┬──────────┬──────────┐
│ Relic    │ Shop     │ Future   │
│          │          │ LOCKED   │
├──────────┼──────────┼──────────┤
│ Weapon   │ Furnace  │ Card     │
│          │ Materials│          │
└──────────┴──────────┴──────────┘
```

以前の中央上Battle枠は、Main画面にBattleが存在するため **Shopへ変更する方向**。

ただし、ユーザー操作・カードUI・Backpack画面は現在もラフ検討中であり、
上記レイアウトを完成UIとして固定しない。

### Furnace / Materials

候補用途:

- Weapon / Relic分解
- Material獲得
- Upgrade素材管理

詳細は未確定。

**Status: DIRECTION / UIはUNDECIDED**

---

## 13. UI / UX Principles

### 13.1 Combatを止めない

原則として以下でBattleをPauseしない。

- Card Pick
- Backpack
- Equipment確認
- Settings

明示的なPause機能は別途用意可能。

### 13.2 Card選択負荷を抑える

避ける:

- Level Upのたびに大きな全面UIが何度も割り込む
- 複数Pickを一度に大量表示する
- 戦闘よりCard処理に時間を取られる

目指す:

- Compactな3択
- Pending Picks
- 必要ならShopへ操作を集約
- 戦闘を見ながら後から処理できる

### 13.3 Main UIに表示する

- Enemy HP
- Wave
- Remaining Time
- XP / Levelなど必要な進行情報
- Equipment
- Card / Build情報
- Pending Picksを採用する場合は未処理数

### 13.4 Main UIに表示しない

- DPS
- TTK
- Kill prediction
- Win / Lose prediction

内部計算・Balance検証には使用可能だが、Player-facing UIには出さない。

**Status: CONFIRMED**

---

## 14. Visual Direction

「机の上の紙で戦闘が進む」「主人公が物語を書き進める」等の紙・手描き方向は、
世界観・見た目の候補として検討している。

現時点では、

- 設定
- Game System
- 必須演出
- 最終Art Direction

として確定していない。

**Status: CANDIDATE**

---

## 15. Save / Automation

将来必要になるが未決定。

候補:

- Save / Load
- Offline progression
- Automation
- 自動Card処理
- 自動Shop更新 / 購入
- 高Wave向け操作量削減

Automationは、Buildを考える楽しさを消さない段階で解禁する。

**Status: UNDECIDED**

---

## 16. Current Godot Prototypeとの境界

仕様と実装状態は分けて管理する。

実装の現在地は `CURRENT_STATE.md` を参照。

Prototypeの一時的な値やUI配置は、
この文書でCONFIRMEDと明記されていない限り正式仕様ではない。

特に、

- Enemy HP = 10
- XP必要量 = 3
- Wave 10 Weapon 2択
- 現在のCard 3枚
- 現在のNode配置

は主に動作確認用。

---

## 17. Specification Status Summary

### CONFIRMED

- Incremental × Roguelite
- 「完成したビルドの、その先を遊ぶ」
- First Prestige = Wave 5000
- Wave 5000 Boss HP = 1e308
- 第一転生まで中央値12時間以下
- Manual Attack開始
- First WeaponでAuto Attack解禁
- Auto Attack後もManual Attack可能
- Weapon装備1枠
- Relic装備3枠
- Player-facing UIにDPS / TTK / 勝敗予測を表示しない
- Enemy HP / Remaining Timeは表示する

### DIRECTION

- CardによるRun Build
- Combatを止めないCard Pick
- Pending Picks
- Death後の手動Retry
- DeathでCard / Weapon / Pendingを失う
- DP / Relic / 一部素材を保持
- Coin / Shop
- Card強化
- ShopでRelic等を扱う
- Backpack 6分割Hub
- Active Action

### CANDIDATE

- Card rarity 5段階
- Weapon type 5種
- Weapon / Relic保管各5枠
- Weapon Drop / Affix
- Furnace / Material
- 紙・手描きVisual

### UNDECIDED

- Level UpとCard / Shopの最終関係
- Card取得頻度
- XP curve
- Enemy HP curve
- Coin獲得量
- Shop更新条件
- Card強化方式
- Weapon / Relicの全効果
- DP数値
- Boss構造
- Save / Offline
- Automation解禁
- First Prestige後

---

## 18. Legacy / Reference

以下は現在仕様そのものではない。

- `docs/archive/`
  - 旧formal Wave 10000等
- `first-prestige-playtest/`
  - Webベースの試作
- `docs/NEW_W5000_PLAY_CANDIDATE.md`
  - W5000設計候補の参照資料
- `docs/W5000_EQUIPMENT_V01.md`
  - Equipment候補
- `docs/experiments/`
  - Balance / CardValue等の実験
- `docs/HANDOFF.md`
  - 詳細な履歴・引き継ぎ

Legacy / Experimentの仕様をGodotへ自動採用しない。

新しい仕様を採用するときは、
この `GAME_SPEC.md` へ明示的に反映してから実装する。
