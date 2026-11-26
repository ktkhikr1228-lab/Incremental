# 現在の状態

最終更新: 2026-11-26

この文書は「いま何を作っていて、どこまで進んでいるか」だけを短く示すスナップショット。
詳細な過去ログは `HANDOFF.md`、仕様は `GAME_SPEC.md`、判断理由は `DECISIONS.md` を参照する。

---

## 1. 現在の開発対象

- Engine: **Godot 4**
- Current target: **First Prestige at Wave 5000**
- Wave 5000 Boss HP: **1e308**
- 第一転生までの標準的な実プレイ時間: **中央値12時間以下**
- 旧formal Wave 10000やWeb試作はLegacy / Referenceとして保持する

現在の正本:
1. `GAME_SPEC.md` — 現行ゲーム仕様
2. `CURRENT_STATE.md` — 現在の実装状況
3. `DECISIONS.md` — 設計判断と理由
4. `ROADMAP.md` — 次の実装順
5. `HANDOFF.md` — 詳細な作業履歴・引き継ぎ倉庫

---

## 2. Godot版の現在地

### GitHub origin/main に反映済み

最新Godotプロトタイプは **2026-10-12 時点で origin/main と同期済み**。

主な実装:

- Manual Attack
- Enemy HP
- Wave進行
- Enemy Timer
- Death / Retry
- `WeaponData` Resource
- Wave 10での初武器2択
  - Old Sword
  - Fast Dagger
- Weapon選択後のAuto Attack
- Weapon取得後もManual Attackを継続可能
- `CardData` Resource
- Card Choice Panel / 3択UI
- テストカード3種
  - Manual Attack倍率
  - Auto Attack倍率
  - Attack Speed倍率
- カード品質（試作実装、PR #2ブランチ）
  - 選択肢の生成時に品質を抽選し、選択前に表示する
  - 並 70%（係数1.0） / 良 22%（係数1.2） / 特上 8%（係数1.45）
  - 実効倍率 = 1 +（基礎倍率 − 1）× 品質係数
  - 特上はおまけ効果として、主軸と違う軸に ×1.10 が付く
  - 抽選結果は専用変数に保持し、共有CardDataは書き換えない
- 試作用パラメータ調整（PR #2ブランチ、正式Balanceではない）
  - Old Sword: Damage 3 / Interval 1.0s（明示）
  - Fast Dagger: Damage 2（明示） / Interval 0.7s
  - Power Training ×1.40 / Strong Training ×1.35 / Quick Hands ×1.30
- 敵HP曲線（試作、本PRブランチ、正式Balanceではない）
  - HP = roundi(10 × 1.06^(Wave-1))（W1=10 / W50≈174 / W100≈3,190）
  - XP必要量は一律3のまま。Level Up時の余剰XPは持ち越しに変更（現状は+1/撃破のため挙動は不変、GAME_SPECの前提への整合）
  - 実ゲーム自動プレイ測定（クリック5回/秒・剣）: W100到達 約119秒、死亡0、TTK 1.0〜1.3秒。複数シードおよびクリック2回/秒でも死亡0を確認
- EnemyTimer / RetryButton のシグナル接続を修正（従来は未接続で、10秒制限によるDeath / Retryが実際には発生しなかった）
- XP
- Level
- Enemy撃破 → XP獲得
- Level Up → Card Pick
- Card取得 → 効果反映
- Card取得後にPanelを閉じる流れ
- Pending Picks（本PRブランチ）
  - Level Upが重なってもCard Pick回数を失わず蓄積する。Panel表示中は現在の選択肢を再抽選しない（品質は生成時に固定）
  - 戦闘は止まらない。死亡時に未処理の選択権は破棄される
  - 残りの選択権数はLevel表示に併記する

最新のGodot更新コミット:

```text
3b2d946 feat: add card and weapon progression prototype
```

### 現在の次タスク

**Card候補ランダム3択**

その次:
1. 必要XP curve（余剰処理は実装済み）
2. W1〜100のBoss進行（HP曲線v1は試作実装済み）
3. Card Pool拡張

---

## 3. 現在の確定ルール

- Run開始時はManual Attackのみ
- 最初のWeapon取得でAuto Attack解禁
- Auto Attack解禁後もManual Attackを使用可能
- Weapon装備は1枠
- Relic装備は3枠
- Card Pick中も戦闘を停止しない
- 未使用Card PickはPending PicksとしてRun内に蓄積
- Player-facing UIにDPS / TTK / 勝敗予測を表示しない
- Enemy HPとRemaining Timeは表示する
- First Prestige = Wave 5000
- Wave 5000 Boss HP = 1e308
- 第一転生まで12時間を明確に超える方向への調整は行わない

死亡時Resetはほぼ確定:
- 失う: Run内Card / Weapon / 未使用Card Pick
- 保持: DP / Relic / 一部素材
- 細部は今後調整

---

## 4. 未実装の主要システム

- Pending Picks
- Card候補ランダム化
- 正式Card Pool
- Weapon Drop / rarity / affix
- Relic
- DP / Permanent Progression
- Inventory / Storage
- Weapon / Relic強化
- Boss / Big Bossの正式進行
- 正式Enemy HP curve
- 正式XP curve
- Save / Load
- First Prestige処理
- Prestige後システム
- Active Skill
- Automation

---

## 5. Legacy / Reference

以下は削除せず比較・検証資料として保持する。

- `docs/archive/first_prestige_v1_spec.md`
  - 旧formal Wave 10000
- `first-prestige-playtest/`
  - WebベースのW5000試作
- `NEW_W5000_PLAY_CANDIDATE.md`
  - 新W5000候補の重要な参照資料
- `W5000_EQUIPMENT_V01.md`
  - Equipment初版候補
- `HANDOFF.md`
  - 過去の詳細作業ログ

Legacyの仕様を現行Godotへ自動的に採用しない。
必要な項目は `GAME_SPEC.md` へ明示的に昇格してから実装する。

---

## 6. Git同期状態

2026-10-12 時点:

```text
main == origin/main
working tree clean
```

Godotの正式な開発先は次とする。

```text
C:\Users\katao\Incremental\godot
```

旧作業フォルダ `C:\Users\katao\Dev` は参照用として扱い、
今後の開発はGit管理下の `Incremental\godot` で行う。
