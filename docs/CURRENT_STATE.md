# 現在の状態

最終更新: 2026-10-12

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
- XP
- Level
- Enemy撃破 → XP獲得
- Level Up → Card Pick
- Card取得 → 効果反映
- Card取得後にPanelを閉じる流れ

最新のGodot更新コミット:

```text
3b2d946 feat: add card and weapon progression prototype
```

### 現在の次タスク

`codex/run-reset-fixes` でPending Picksを基点にDeath / Retry / Choice修正を追加。
Godot 4.7.2 headless import・構文チェック・実Scene signalスモークは成功。
死亡時破棄、新Run初期化、Weapon優先とPending復帰、同時二重入力拒否を自動確認。
Codex側でGodot画面の操作・表示は未確認。mainへの反映・mergeはしていない。

**Pending Picks / 未処理Card Pick**

Card選択中も戦闘を止めないため、
Level Upが重なった場合のCard Pick回数を失わず蓄積する。

その次:
1. Card候補ランダム3択
2. XP余剰処理・必要XP curve
3. W1〜100のEnemy HP / Boss進行
4. Card Pool拡張

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

- `first_prestige_v1_spec.md`
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
