# Index — ファイル分類と対応表

このリポジトリの全ファイルを「現行 / 参照 / 実験 / Legacy / 履歴」に分類した索引。
仕様の正本は [GAME_SPEC.md](GAME_SPEC.md)。ここは入口と対応表だけを持ち、仕様そのものは書かない。

最終更新: 2026-11-26（repo整理PRで作成）

---

## 1. 現行（Godot版 W5000 の開発基準）

| ファイル | 役割 |
|---|---|
| [GAME_SPEC.md](GAME_SPEC.md) | 現在仕様の正本 |
| [CURRENT_STATE.md](CURRENT_STATE.md) | 現在の実装状況 |
| [DECISIONS.md](DECISIONS.md) | 設計判断と理由 |
| [ROADMAP.md](ROADMAP.md) | 今後の実装順 |
| `../AGENTS.md` | AI共通の開発ルール |
| `../godot/` | 現在のゲーム本体（Godot 4 / GDScript） |
| `../README.md` | プロジェクト概要 |

## 2. 現行の参照資料（docs/ 直下）

| ファイル | 役割 |
|---|---|
| [NEW_W5000_PLAY_CANDIDATE.md](NEW_W5000_PLAY_CANDIDATE.md) | 新W5000候補の重要参照資料 |
| [W5000_EQUIPMENT_V01.md](W5000_EQUIPMENT_V01.md) | Equipment初版候補 |
| [OVERFLOW_FORMAL_AUDIT.md](OVERFLOW_FORMAL_AUDIT.md) | Overflow効果の監査記録（時点の記録として保持） |

## 3. 実験仕様（docs/experiments/）

旧formal W10000 / CardValue v0.1 系列の実験・検証仕様。現行Godot仕様ではない。
採用する場合は、先に GAME_SPEC.md へ明示的に反映する（AGENTS.md のルール）。

| ファイル | 対応するスクリプト | 対応する出力 |
|---|---|---|
| [experiments/card_value_evaluation_spec.md](experiments/card_value_evaluation_spec.md) | `../scripts/card_value_v01.py` | `../output/card_value_v01_*.md` |
| [experiments/card_value_v01_implementation_plan.md](experiments/card_value_v01_implementation_plan.md) | `../scripts/card_value_v01.py` | — |
| [experiments/card_value_take_experiment_design.md](experiments/card_value_take_experiment_design.md) | `../scripts/run_card_value_take_experiment.py`, `../scripts/simulate_first_prestige_v1.py` | `../output/card_value_take_*.md` / `.json` |
| [experiments/card_value_encounter_conditional_design.md](experiments/card_value_encounter_conditional_design.md) | `../scripts/test_card_value_encounter_conditional.py` | `../output/card_value_v01_validity_diagnostic.md` |
| [experiments/card_value_xp_draft_h_design.md](experiments/card_value_xp_draft_h_design.md) | `../scripts/test_card_value_xp_drafts.py` | — |
| [experiments/predict_run_end_spec.md](experiments/predict_run_end_spec.md) | （CardValue評価から参照される将来案） | — |

## 4. Legacy（docs/archive/ と旧系列）

| 場所 | 内容 |
|---|---|
| [archive/first_prestige_v1_spec.md](archive/first_prestige_v1_spec.md) | 旧formal Wave 10000 仕様 |
| `../first-prestige-playtest/` | WebベースのW5000手動試作（新W5000手動プレイ候補） |
| `../scripts/` の `*_v1_*` / `simulate_first_prestige_v1.py` 等 | 旧formal系列のシム・診断（索引は `../scripts/README.md`） |
| formal Variant D/E | 別実験系列 |

## 5. 履歴

| ファイル | 役割 |
|---|---|
| [HANDOFF.md](HANDOFF.md) | 詳細な作業履歴・引き継ぎ倉庫。当時のパス表記は履歴としてそのまま残す |

## 6. 出力

| 場所 | 方針 |
|---|---|
| `../output/` | 実験出力。人間可読な要約（md / json）のみ保持する（`.gitignore` の方針通り） |

---

## 既知の不整合（2026-11-26 棚卸し時点）

- DECISIONS.md が参照する `../output/card_value_take_stages_1-3_comparison.md` が `output/` に存在しない（リンク切れ。要確認）
- Godot版の実数値（`godot/*.gd` / `*.tres`）に直接対応するシミュレーションは scripts/ に見当たらない。現行シム群は主にWeb候補・旧formal系列のバランス検証用。パラメータ調整では、どのシムを正本にするかを先に決める必要がある
