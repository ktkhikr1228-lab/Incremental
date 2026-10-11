# 現在の状態

最終更新: 2026-10-11

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

現時点でGitHubにpush済みのGodotコードは初期プロトタイプ段階。

- Manual Attack
- Enemy HP
- Wave進行
- Enemy Timer
- Death
- Retry
- Wave 10以降の簡易Weapon取得
- 簡易Auto Attack

### ローカルで進行中 / 会話で動作確認済み

GitHubへまだ反映されていない最新Godot作業を含む。

- `WeaponData` Resource
- 初武器2択
  - Old Sword
  - Fast Dagger
- Weapon選択後にAuto Attack解禁
- Manual AttackはWeapon取得後も使用可能
- `CardData` Resource
- Card Choice Panel / 3択
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

### 現在の次タスク

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

## 6. Git同期上の注意

現在、会話で確認できているGodotのローカル進捗が
GitHub origin/mainの `godot/` より先行している。

PCへ戻ったら、まず以下を行う。

```text
git status
git diff
```

Godotの最新ローカル変更を確認し、
意図しないファイルを含めずcommit / pushする。

push後、この文書の「GitHub origin/main に反映済み」を更新する。
