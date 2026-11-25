# scripts/ 索引

検証・シミュレーション用スクリプト置き場（84ファイル）。
ファイル同士の相互importを壊さないため、**フォルダ分け・改名は行わない**。この索引で系列と入口を示す。

最終更新: 2026-11-26（repo整理PRで作成）

## 接頭辞の意味

| 接頭辞 | 役割 |
|---|---|
| `simulate_*` | 本体シミュレーション |
| `compare_*` | 条件・系列同士の比較 |
| `diagnose_*` | 問題の切り分け診断 |
| `experiment_*` | 仮説検証の実験 |
| `replay_*` | 固定条件での再再生検証 |
| `analyze_*` / `audit_*` | 分析・監査 |
| `repair_*` | 出力の修復 |
| `test_*` | テスト（repo rootから `python -m unittest discover -s scripts -p 'test_*.py' -q`） |

## 系列

### 旧formal v1 系列（Legacy）
- `simulate_first_prestige_v1.py` — 旧formal W10000 の本体シム（CardValue v0.1 の対象）
- `w5000_v1_profile.py` / `test_w5000_v1_profile.py`
- `*_w5000_v1_*`（diagnose / experiment / replay / compare 系）
- `first_prestige_defense_model.py`

仕様側の対応: `../docs/archive/first_prestige_v1_spec.md`

### CardValue 系列（実験）
- `card_value_v01.py` — CardValue v0.1 本体（DECISIONS.md が根拠として参照）
- `run_card_value_take_experiment.py`
- `test_card_value_*.py`、`diagnose_standard_card_score_scale.py`、`stress_test_card_softcaps.py`

仕様側の対応: `../docs/experiments/card_value_*.md` / `predict_run_end_spec.md`、出力は `../output/card_value_*`

### new_w5000 系列（現行候補の検証）
- `simulate_new_w5000_*.py` — レアリティ段階別の本体シム（common/uncommon → rare → epic → legendary）
- `compare_new_w5000_*.py`、`analyze_new_w5000_*.py`、`audit_new_w5000_*.py`、`repair_new_w5000_*.py`
- `test_new_w5000_play_session.py`、`test_play_*.py`、`test_equipment_play_session.py`

仕様側の対応: `../docs/NEW_W5000_PLAY_CANDIDATE.md`、試遊本体は `../first-prestige-playtest/`（`new_w5000_rules.py` / `new_w5000_session.py`）

### 装備
- `w5000_equipment_v01.py` / `test_w5000_equipment_v01.py`

仕様側の対応: `../docs/W5000_EQUIPMENT_V01.md`

### その他
- `simulate_early_game.py` — 序盤シム（Godot版 W1–100 調整への流用可否は未確認）
- `simulate_first_prestige.py` — 初期の転生シム
- `runaway_inflation.js` / `runaway_inflation.README.md` — インフレ挙動の単独実験

## 注意
- Godot版の実数値（`../godot/*.gd` / `*.tres`）に直接対応するシムはこの中には無い。パラメータ調整に使う正本シムは、調整を始める前に決めること
