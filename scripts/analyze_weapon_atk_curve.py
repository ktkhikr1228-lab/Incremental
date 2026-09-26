#!/usr/bin/env python3
"""Analyze additive Weapon ATK curves without modifying the formal simulator.

The formal simulator models weapons as direct log10 Base ATK power.  This tool
imports that simulator, records its actual formal-v1 combat state, reconstructs
pre-weapon Base ATK, derives additive weapon curves, and compares those curves
through runtime-only monkey patches in worker processes.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import dataclasses
import importlib
import json
import math
import random
import statistics
import sys
from pathlib import Path
from typing import Any


CHECKPOINTS = (10, 25, 100, 500, 1000, 2500, 5000, 7500, 10000)
CURVE_ANCHOR_WAVES = (10, 100, 500, 1000, 2500, 5000, 7500, 10000)
PHASE4_REPORT_WAVES = (100, 500, 1000, 2500)
SHARES = {"A": 0.30, "B": 0.40, "C": 0.50}
COMMON_WEAPON_MULTIPLIER = 1.10
REFERENCE_A_1000_SUCCESS_RATE = 0.718


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    position = (len(ordered) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def quantiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"p25": None, "p50": None, "p75": None, "mean": None}
    return {
        "p25": percentile(values, 0.25),
        "p50": percentile(values, 0.50),
        "p75": percentile(values, 0.75),
        "mean": statistics.fmean(values),
    }


def log10_add(left: float, right: float) -> float:
    high = max(left, right)
    low = min(left, right)
    if high - low > 40:
        return high
    return high + math.log10(1 + 10 ** (low - high))


def interpolate_log(wave: int, anchors: tuple[tuple[int, float], ...]) -> float:
    if wave <= anchors[0][0]:
        return anchors[0][1]
    for (left_wave, left), (right_wave, right) in zip(anchors, anchors[1:]):
        if wave <= right_wave:
            ratio = (wave - left_wave) / (right_wave - left_wave)
            return left + (right - left) * ratio
    return anchors[-1][1]


def scientific_from_log(log_value: float) -> str:
    if not math.isfinite(log_value):
        return "unknown"
    exponent = math.floor(log_value)
    mantissa = 10 ** (log_value - exponent)
    if -3 <= exponent <= 5:
        return f"{10 ** log_value:,.4g}"
    return f"{mantissa:.4g}e{exponent:+d}"


def _formal_config(sim: Any, max_attempts: int) -> Any:
    return sim.SimConfig(max_attempts=max_attempts)


def _install_runtime_mode(
    sim: Any,
    mode: str,
    curve_anchors: tuple[tuple[int, float], ...],
) -> tuple[dict[int, dict[str, float]], dict[int, dict[str, Any]]]:
    """Install process-local diagnostics and optional additive weapon behavior."""
    sim.CHECKPOINTS = CHECKPOINTS
    sim.REACH_WAVES = CHECKPOINTS

    current_capture: dict[int, dict[str, float]] = {}
    snapshot_meta: dict[int, dict[str, Any]] = {}
    original_compute = sim.compute_snapshot
    original_ttk = sim.time_to_kill_with_defense

    if mode in SHARES:
        def common_curve_roll_weapon(
            rng: random.Random,
            permanent: Any,
            run: Any,
            wave: int,
            config: Any,
            minimum_rarity: str = "C",
            generated: bool = False,
        ) -> None:
            # Preserve the formal drop/material economy, but remove rarity and
            # quality from combat strength.  Combat uses the Common curve only.
            reward_wave = sim.progression_wave(wave, config)
            distribution = sim.weapon_rarity_distribution(reward_wave)
            allowed = [
                (rarity, chance)
                for rarity, chance in distribution
                if sim.RARITY_ORDER.index(rarity)
                >= sim.RARITY_ORDER.index(minimum_rarity)
            ]
            total = sum(chance for _, chance in allowed)
            normalized = tuple((rarity, chance / total) for rarity, chance in allowed)
            rarity = sim.draw_from_distribution(rng, normalized)
            effective_weapon_log = interpolate_log(reward_wave, curve_anchors)
            sim.equip_or_smelt_weapon(
                permanent,
                run,
                effective_weapon_log,
                rarity,
                reward_wave,
            )
            if generated:
                permanent.weapon_generations += 1
                if not permanent.one_tap_workshop_enabled:
                    permanent.interaction_seconds += sim.FORGE_OPERATION_SECONDS
                    permanent.forge_seconds += sim.FORGE_OPERATION_SECONDS

        sim.roll_weapon = common_curve_roll_weapon

    def diagnostic_compute_snapshot(
        run: Any,
        permanent: Any,
        boss: bool,
        config: Any,
    ) -> Any:
        snapshot = original_compute(run, permanent, boss, config)
        exponent = (
            config.exponential_core_multiplier
            if sim.n(run.counts, "exponential_core")
            else 1.0
        )
        weapon_term = run.weapon_power if run.weapon else 0.0
        pre_exponent_with_old_weapon = snapshot.base_attack_power / exponent
        raw_base_log = pre_exponent_with_old_weapon - weapon_term

        if mode == "none":
            new_base_log = raw_base_log * exponent
            delta = new_base_log - snapshot.base_attack_power
            snapshot = dataclasses.replace(
                snapshot,
                log_dps=snapshot.log_dps + delta,
                base_attack_power=new_base_log,
                weapon_power=0.0,
            )
            effective_weapon_log: float | None = None
        elif mode in SHARES:
            if run.weapon:
                pre_exponent_total = log10_add(raw_base_log, weapon_term)
                effective_weapon_log = weapon_term
            else:
                pre_exponent_total = raw_base_log
                effective_weapon_log = None
            new_base_log = pre_exponent_total * exponent
            delta = new_base_log - snapshot.base_attack_power
            weapon_contribution = new_base_log - raw_base_log * exponent
            snapshot = dataclasses.replace(
                snapshot,
                log_dps=snapshot.log_dps + delta,
                base_attack_power=new_base_log,
                weapon_power=weapon_contribution,
            )
        else:
            effective_weapon_log = None

        crit_power = sim.crit_log_multiplier(
            snapshot.crit_chance,
            snapshot.crit_multiplier,
            run.counts,
        )
        snapshot_meta[id(snapshot)] = {
            "raw_base_log10": raw_base_log,
            "base_exponent": exponent,
            "old_weapon_power": weapon_term if mode == "baseline" and run.weapon else 0.0,
            "effective_weapon_log10": effective_weapon_log,
            "crit_expected_power": crit_power,
        }
        return snapshot

    sim.compute_snapshot = diagnostic_compute_snapshot

    def diagnostic_ttk(
        wave: int,
        total_power: float,
        limit: float,
        snapshot: Any,
        effective_log_dps: float,
        config: Any,
    ) -> float | None:
        if wave == 1:
            snapshot_meta.clear()
        result = original_ttk(
            wave,
            total_power,
            limit,
            snapshot,
            effective_log_dps,
            config,
        )
        if wave in CHECKPOINTS and result is not None and wave not in current_capture:
            meta = snapshot_meta.get(id(snapshot), {})
            raw_base_log = float(meta.get("raw_base_log10", math.nan))
            effective_weapon_log = meta.get("effective_weapon_log10")
            if effective_weapon_log is None or not math.isfinite(raw_base_log):
                weapon_share = 0.0
            else:
                difference = raw_base_log - float(effective_weapon_log)
                if difference >= 300:
                    weapon_share = 0.0
                elif difference <= -300:
                    weapon_share = 1.0
                else:
                    weapon_share = 1.0 / (1.0 + 10.0**difference)
            crit_power = float(meta.get("crit_expected_power", 0.0))
            all_damage_power = math.log10(max(1e-300, snapshot.all_damage))
            attack_speed_power = math.log10(max(1e-300, snapshot.attack_speed))
            other_power = (
                effective_log_dps
                - snapshot.base_attack_power
                - attack_speed_power
                - crit_power
                - all_damage_power
            )
            current_capture[wave] = {
                "raw_base_log10": raw_base_log,
                "base_atk_log10": snapshot.base_attack_power,
                "base_exponent": float(meta.get("base_exponent", 1.0)),
                "old_weapon_power": float(meta.get("old_weapon_power", 0.0)),
                "all_damage": snapshot.all_damage,
                "attack_speed": snapshot.attack_speed,
                "crit_rate": snapshot.crit_chance,
                "crit_multiplier": snapshot.crit_multiplier,
                "crit_expected_multiplier_log10": crit_power,
                "follow_up_rate": snapshot.follow_rate,
                "weapon_share": weapon_share,
                "other_damage_power": other_power,
                "dps_log10": effective_log_dps,
                "enemy_hp_log10": total_power,
                "kill_time_seconds": result if result is not None else math.nan,
            }
        return result

    sim.time_to_kill_with_defense = diagnostic_ttk
    return current_capture, snapshot_meta


def _worker_batch(
    mode: str,
    curve_anchors: tuple[tuple[int, float], ...],
    start: int,
    count: int,
    seed: int,
    max_attempts: int,
) -> list[dict[str, Any]]:
    import simulate_first_prestige_v1 as sim

    sim = importlib.reload(sim)
    capture, _ = _install_runtime_mode(sim, mode, curve_anchors)
    config = _formal_config(sim, max_attempts)
    rows: list[dict[str, Any]] = []
    for trial_index in range(start, start + count):
        capture.clear()
        rng = random.Random(seed + 1_000_000 + trial_index)
        result = sim.run_trial(rng, "balanced", config, allow_overdrive=True)
        checkpoint_copy = {
            int(wave): dict(values) for wave, values in capture.items()
        }
        for wave, elapsed in result.reach_seconds.items():
            if wave in checkpoint_copy:
                checkpoint_copy[wave]["arrival_hours"] = elapsed / 3600
        rows.append(
            {
                "trial": trial_index,
                "success": result.success,
                "play_hours": (
                    result.total_combat_seconds + result.total_interaction_seconds
                ) / 3600,
                "combat_hours": result.total_combat_seconds / 3600,
                "operation_hours": result.total_interaction_seconds / 3600,
                "deaths": result.deaths,
                "best_wave": max(result.run_reaches),
                "checkpoints": checkpoint_copy if result.success else {},
                "reach_hours": {
                    int(wave): elapsed / 3600
                    for wave, elapsed in result.reach_seconds.items()
                    if wave in CHECKPOINTS
                },
            }
        )
    return rows


def run_parallel(
    mode: str,
    curve_anchors: tuple[tuple[int, float], ...],
    trials: int,
    seed: int,
    max_attempts: int,
    workers: int,
) -> list[dict[str, Any]]:
    chunk = max(1, math.ceil(trials / workers))
    jobs = [
        (mode, curve_anchors, start, min(chunk, trials - start), seed, max_attempts)
        for start in range(0, trials, chunk)
    ]
    rows: list[dict[str, Any]] = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_worker_batch, *job) for job in jobs]
        for future in concurrent.futures.as_completed(futures):
            rows.extend(future.result())
    rows.sort(key=lambda row: row["trial"])
    return rows


def summarize_phase1(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    successes = [row for row in rows if row["success"]]
    metrics = (
        "raw_base_log10",
        "base_atk_log10",
        "base_exponent",
        "old_weapon_power",
        "all_damage",
        "attack_speed",
        "crit_rate",
        "crit_multiplier",
        "crit_expected_multiplier_log10",
        "follow_up_rate",
        "other_damage_power",
        "dps_log10",
        "enemy_hp_log10",
        "kill_time_seconds",
        "arrival_hours",
    )
    output: dict[int, dict[str, Any]] = {}
    for wave in CHECKPOINTS:
        entries = [
            row["checkpoints"][wave]
            for row in successes
            if wave in row["checkpoints"]
        ]
        output[wave] = {
            "samples": len(entries),
            **{
                metric: quantiles(
                    [float(entry[metric]) for entry in entries if math.isfinite(float(entry[metric]))]
                )
                for metric in metrics
            },
        }
    return output


def derive_curves(
    phase1: dict[int, dict[str, Any]],
) -> tuple[dict[str, tuple[tuple[int, float], ...]], list[dict[str, Any]]]:
    curves: dict[str, list[tuple[int, float]]] = {name: [] for name in SHARES}
    rows: list[dict[str, Any]] = []
    for wave in CHECKPOINTS:
        raw_log = phase1[wave]["raw_base_log10"]["p50"]
        if raw_log is None:
            for name in SHARES:
                rows.append(
                    {
                        "wave": wave,
                        "curve": name,
                        "target_share": SHARES[name],
                        "raw_base_log10": None,
                        "required_effective_weapon_log10": None,
                        "curve_effective_weapon_log10": None,
                        "weapon_base_log10": None,
                    }
                )
            continue
        for name, share in SHARES.items():
            required_log = raw_log + math.log10(share / (1 - share))
            if wave in CURVE_ANCHOR_WAVES:
                curve_log = math.log10(1.10) if wave == 10 else required_log
                curves[name].append((wave, curve_log))
            rows.append(
                {
                    "wave": wave,
                    "curve": name,
                    "target_share": share,
                    "raw_base_log10": raw_log,
                    "required_effective_weapon_log10": required_log,
                    "curve_effective_weapon_log10": None,
                    "weapon_base_log10": None,
                }
            )
    final_curves = {name: tuple(values) for name, values in curves.items()}
    for row in rows:
        if row["raw_base_log10"] is None:
            continue
        curve_log = interpolate_log(int(row["wave"]), final_curves[str(row["curve"])])
        row["curve_effective_weapon_log10"] = curve_log
        row["weapon_base_log10"] = curve_log - math.log10(COMMON_WEAPON_MULTIPLIER)
    return final_curves, rows


def summarize_phase4(rows: list[dict[str, Any]]) -> dict[str, Any]:
    successes = [row for row in rows if row["success"]]
    basis = successes if successes else rows

    def percentiles(key: str, source: list[dict[str, Any]] = successes) -> dict[str, float | None]:
        values = [float(row[key]) for row in source]
        if not values:
            return {"p10": None, "p25": None, "p50": None, "p75": None, "p90": None}
        return {
            "p10": percentile(values, 0.10),
            "p25": percentile(values, 0.25),
            "p50": percentile(values, 0.50),
            "p75": percentile(values, 0.75),
            "p90": percentile(values, 0.90),
        }

    reach = {}
    for wave in CHECKPOINTS:
        values = [
            float(row["reach_hours"][wave])
            for row in successes
            if wave in row["reach_hours"]
        ]
        reach[str(wave)] = percentile(values, 0.50) if values else None
    weapon_share = {}
    for wave in PHASE4_REPORT_WAVES:
        values = [
            float(row["checkpoints"][wave]["weapon_share"])
            for row in successes
            if wave in row["checkpoints"]
        ]
        weapon_share[str(wave)] = percentile(values, 0.50) if values else None
    return {
        "trials": len(rows),
        "success_rate": len(successes) / len(rows),
        "play_hours": percentiles("play_hours"),
        "combat_hours_p50": (
            percentile([float(row["combat_hours"]) for row in successes], 0.50)
            if successes else None
        ),
        "operation_hours_p50": (
            percentile([float(row["operation_hours"]) for row in successes], 0.50)
            if successes else None
        ),
        "deaths_p50": percentile([float(row["deaths"]) for row in basis], 0.50),
        "best_wave_p50": percentile([float(row["best_wave"]) for row in rows], 0.50),
        "reach_hours_p50": reach,
        "weapon_share_p50": weapon_share,
    }


def write_phase4_progress_csv(path: Path, phase4: dict[str, dict[str, Any]]) -> None:
    fields = [
        "condition",
        "trials",
        "success_rate",
        "play_time_p25",
        "play_time_p50",
        "play_time_p75",
        "deaths_p50",
    ]
    for wave in PHASE4_REPORT_WAVES:
        fields.extend((f"reach_w{wave}_p50", f"weapon_share_w{wave}_p50"))
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for condition in ("A", "B", "C"):
            if condition not in phase4:
                continue
            result = phase4[condition]
            row: dict[str, Any] = {
                "condition": condition,
                "trials": result["trials"],
                "success_rate": result["success_rate"],
                "play_time_p25": result["play_hours"]["p25"],
                "play_time_p50": result["play_hours"]["p50"],
                "play_time_p75": result["play_hours"]["p75"],
                "deaths_p50": result["deaths_p50"],
            }
            for wave in PHASE4_REPORT_WAVES:
                row[f"reach_w{wave}_p50"] = result["reach_hours_p50"][str(wave)]
                row[f"weapon_share_w{wave}_p50"] = result["weapon_share_p50"][str(wave)]
            writer.writerow(row)


def save_staged_progress(
    output_dir: Path,
    trials: int,
    seed: int,
    max_attempts: int,
    phase1_success_rate: float,
    phase1: dict[int, dict[str, Any]],
    curves: dict[str, tuple[tuple[int, float], ...]],
    phase4: dict[str, dict[str, Any]],
) -> None:
    payload = {
        "conditions": {
            "trials_per_weapon_curve": trials,
            "seed": seed,
            "max_attempts": max_attempts,
            "formal_variant": True,
            "defense": False,
            "common_weapon_multiplier": COMMON_WEAPON_MULTIPLIER,
        },
        "references": {
            "prior_A_1000_success_rate": REFERENCE_A_1000_SUCCESS_RATE,
            "note": "参考値。今回の段階検証とは別実行。",
        },
        "phase1_success_rate": phase1_success_rate,
        "phase1": phase1,
        "curves_effective_weapon_log10": {
            name: list(values) for name, values in curves.items()
        },
        "phase4": phase4,
        "completed_conditions": [name for name in ("A", "B", "C") if name in phase4],
    }
    (output_dir / "weapon_curve_200_progress.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_phase4_progress_csv(output_dir / "weapon_curve_200_progress.csv", phase4)


def write_phase1_csv(path: Path, phase1: dict[int, dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["wave", "metric", "samples", "p25", "p50", "p75", "mean"])
        for wave, values in phase1.items():
            for metric, stats in values.items():
                if metric == "samples":
                    continue
                writer.writerow(
                    [wave, metric, values["samples"], stats["p25"], stats["p50"], stats["p75"], stats["mean"]]
                )


def write_curve_csv(path: Path, curve_rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        fields = (
            "wave",
            "curve",
            "target_share",
            "raw_base_log10",
            "required_effective_weapon_log10",
            "curve_effective_weapon_log10",
            "weapon_base_log10",
        )
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(curve_rows)


def _range_text(stats: dict[str, float | None], digits: int = 2) -> str:
    if stats["p50"] is None:
        return "不明"
    return f"{stats['p25']:.{digits}f} / {stats['p50']:.{digits}f} / {stats['p75']:.{digits}f}"


def build_report(
    trials: int,
    max_attempts: int,
    seed: int,
    phase1_success_rate: float,
    phase1: dict[int, dict[str, Any]],
    curves: dict[str, tuple[tuple[int, float], ...]],
    curve_rows: list[dict[str, Any]],
    phase4: dict[str, dict[str, Any]],
) -> str:
    lines = [
        "# 正式v1 Weapon ATK成長曲線分析",
        "",
        "## 検証条件",
        "",
        f"- Standard bot、各条件{trials:,}試行、seed={seed}、最大{max_attempts}ラン。",
        "- 正式v1（W10,000、Defenseなし、精錬+3、遺物厳選あり）を使用。D/Eは不使用。",
        "- `first_prestige_v1_spec.md`と本体シミュレーターは未変更。独立スクリプトの実行時パッチだけで比較。",
        "- 現行Weaponは加算ATKではなく、Base ATKのlog10 Powerへ直接加算される。",
        "- `Raw Base ATK`という独立フィールドは現行コードに存在しない。ここでは、Base ATK計算から現行Weapon Powerだけを除いた値を再構成値として使用。",
        "- 新曲線ではCommonのWeapon multiplierを全地点×1.10として正規化。W10以外の倍率は既存仕様から抽出不能なため、曲線比較用の明示的な設計条件。",
        f"- Phase 1正式v1成功率: {phase1_success_rate:.1%}",
        "",
        "## Phase 1：正式v1の実測状態（P25 / P50 / P75）",
        "",
        "DPS・Raw Base ATKは桁が大きいためlog10 Powerで表示。Enemy HP Powerはlog10(HP)。",
        "",
        "| Wave | Raw Base ATK Power | 現Base ATK Power | 旧Weapon Power | All Damage | AS | Crit率 | Crit倍率 | その他Damage Power | DPS Power | Enemy HP Power | Kill秒 | 到達h |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for wave in CHECKPOINTS:
        row = phase1[wave]
        lines.append(
            f"| {wave:,} | {_range_text(row['raw_base_log10'])} | {_range_text(row['base_atk_log10'])} | "
            f"{_range_text(row['old_weapon_power'])} | {_range_text(row['all_damage'])} | "
            f"{_range_text(row['attack_speed'])} | {_range_text(row['crit_rate'], 3)} | "
            f"{_range_text(row['crit_multiplier'])} | {_range_text(row['other_damage_power'])} | "
            f"{_range_text(row['dps_log10'])} | {row['enemy_hp_log10']['p50']:.2f} | "
            f"{_range_text(row['kill_time_seconds'], 3)} | {_range_text(row['arrival_hours'])} |"
        )

    lines.extend([
        "",
        "### Phase 1の読み方",
        "",
        "- `旧Weapon Power=4.78`なら、旧武器はBase ATKを約`10^4.78`倍する実装。新式のWeapon share 40%（Base ATK×約1.67）とは単位も強度も異なる。",
        "- 初期Raw Base ATKは1なので、この再構成Raw Base ATKの数値は、Weaponを除いたBase ATK倍率と同値。Raw値と倍率を別々に保持するフィールドは現行コードにない。",
        "- `その他Damage Power`には成長スタック、マイルストーン、追撃、Boss補正、遺物平均Powerなど、Base ATK/AS/Crit/All Damage以外の残差を含む。",
        "- 到達時間・戦闘ステータス・Kill秒はいずれも、そのtrialで各Waveを初めて撃破した戦闘の値。最終成功ラン基準ではない。",
        "",
        "## Phase 2：必要Effective Weapon ATKの逆算",
        "",
        "| Wave | Raw Base ATK(P50) | 30%必要ATK | 40%必要ATK | 50%必要ATK |",
        "|---:|---:|---:|---:|---:|",
    ])
    by_wave: dict[int, dict[str, dict[str, Any]]] = {}
    for row in curve_rows:
        by_wave.setdefault(int(row["wave"]), {})[str(row["curve"])] = row
    for wave in CHECKPOINTS:
        raw_log = phase1[wave]["raw_base_log10"]["p50"]
        if raw_log is None:
            lines.append(f"| {wave:,} | 不明 | 不明 | 不明 | 不明 |")
            continue
        cells = []
        for name in ("A", "B", "C"):
            cells.append(scientific_from_log(by_wave[wave][name]["required_effective_weapon_log10"]))
        lines.append(
            f"| {wave:,} | {scientific_from_log(raw_log)} | {cells[0]} | {cells[1]} | {cells[2]} |"
        )
    w10_raw = phase1[10]["raw_base_log10"]["p50"]
    if w10_raw is not None:
        fixed_share = 1 / (1 + 10 ** (w10_raw - math.log10(1.10)))
        lines.extend([
            "",
            f"W10固定武器はEffective ATK 1.10。初回W10戦闘時のRaw中央値に対する参考シェアは{fixed_share:.4%}。ただし武器はW10撃破後に取得する。",
            "ユーザー指定のRaw=1で取得直後を評価するとシェアは52.38%。W10曲線はチュートリアル固定値を優先し、30/40/50%目標には合わせていない。",
        ])

    lines.extend([
        "",
        "## Phase 3：Common Weapon Base ATK曲線",
        "",
        "W10/W100/W500/W1000/W2500/W5000/W7500/W10000をアンカーとし、間は`log10(Weapon Base ATK)`をWaveで線形補間する。Effective Weapon ATKはWeapon Base ATK×1.10。W25の逆算値は曲線アンカーに使わない。",
        "",
        "| Wave | A 控えめ30% | B 標準40% | C 武器重視50% |",
        "|---:|---:|---:|---:|",
    ])
    for wave in CURVE_ANCHOR_WAVES:
        cells = [
            scientific_from_log(by_wave[wave][name]["weapon_base_log10"])
            for name in ("A", "B", "C")
        ]
        lines.append(f"| {wave:,} | {cells[0]} | {cells[1]} | {cells[2]} |")
    lines.extend([
        "",
        "説明用の式：隣接アンカー`(W1,A1)`と`(W2,A2)`の間では、"
        "`WeaponBaseATK = 10^(log10(A1)+(log10(A2)-log10(A1))×(Wave-W1)/(W2-W1))`。",
        "",
        "## Phase 4：正式v1への影響（Standard bot）",
        "",
        "時間P10/P50/P90は成功trialのみ。成功率とBest Wave中央値を必ず併記する。",
        "",
        "| 条件 | 成功率 | 実時間 P10/P50/P90 | 戦闘P50 | 操作P50 | 死亡P50 | Best Wave P50 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    names = {
        "none": "Weaponなし",
        "A": "A 控えめ30%",
        "B": "B 標準40%",
        "C": "C 武器重視50%",
    }
    for mode in ("none", "A", "B", "C"):
        row = phase4[mode]
        play = row["play_hours"]
        play_text = (
            f"{play['p10']:.2f}/{play['p50']:.2f}/{play['p90']:.2f}h"
            if play["p50"] is not None else "成功なし"
        )
        lines.append(
            f"| {names[mode]} | {row['success_rate']:.1%} | {play_text} | "
            f"{row['combat_hours_p50']:.2f}h" if row["combat_hours_p50"] is not None else f"| {names[mode]} | {row['success_rate']:.1%} | {play_text} | —"
        )
        # Complete the row separately to keep None formatting explicit.
        if lines[-1].count("|") < 7:
            pass
        combat = f"{row['combat_hours_p50']:.2f}h" if row["combat_hours_p50"] is not None else "—"
        operation = f"{row['operation_hours_p50']:.2f}h" if row["operation_hours_p50"] is not None else "—"
        deaths = f"{row['deaths_p50']:.0f}"
        best = f"{row['best_wave_p50']:.0f}"
        lines[-1] = (
            f"| {names[mode]} | {row['success_rate']:.1%} | {play_text} | {combat} | "
            f"{operation} | {deaths} | {best} |"
        )

    lines.extend([
        "",
        "### 判定",
        "",
    ])
    best_mode = max(("A", "B", "C"), key=lambda key: phase4[key]["success_rate"])
    candidate_success = [phase4[key]["success_rate"] for key in ("A", "B", "C")]
    candidate_p50 = [phase4[key]["play_hours"]["p50"] for key in ("A", "B", "C")]
    candidate_deaths = [phase4[key]["deaths_p50"] for key in ("A", "B", "C")]
    candidate_w100 = [phase4[key]["reach_hours_p50"]["100"] for key in ("A", "B", "C")]
    candidate_w2500 = [phase4[key]["reach_hours_p50"]["2500"] for key in ("A", "B", "C")]
    no_weapon_p50 = phase4["none"]["play_hours"]["p50"]
    old_weapon_w10000 = phase1[10000]["old_weapon_power"]["p50"]
    if phase4[best_mode]["success_rate"] == 0:
        lines.extend([
            "- A～CはいずれもW10,000へ到達しなかった。30～50%シェア曲線は、旧Weapon Powerを置換するには弱すぎる。",
            "- これは曲線の補間不良ではなく、旧武器が最大35 Power超を直接与えていたのに対し、新式は50%シェアでもBase ATKを最大×2にするだけという構造差による。",
            "- 正式敵曲線を維持するなら、Weapon share設計だけで旧Weapon Powerを代替できない。敵曲線または他成長源を別途再設計する必要があるが、本分析では変更していない。",
        ])
    else:
        lines.append(
            f"- 成功率最大は{names[best_mode]}の{phase4[best_mode]['success_rate']:.1%}。時間だけでなく成功率・停滞Waveを基準に比較する必要がある。"
        )
    lines.extend([
        f"- 過去formal Standard 1,000試行は成功94.7%、P50 13.44h、死亡195。A/B/Cは成功{min(candidate_success):.1%}～{max(candidate_success):.1%}、P50 {min(candidate_p50):.2f}～{max(candidate_p50):.2f}h、死亡{min(candidate_deaths):.0f}～{max(candidate_deaths):.0f}。",
        f"- WeaponなしP50 {no_weapon_p50:.2f}hに対し、A/B/Cは{no_weapon_p50-max(candidate_p50):.2f}～{no_weapon_p50-min(candidate_p50):.2f}h短縮する。30%→50%の差は成功率・時間・死亡を合わせて判断する必要がある。",
        f"- W100到達はformal 1.09hに対してA/B/Cで{min(candidate_w100):.2f}～{max(candidate_w100):.2f}h、W2,500到達は{min(candidate_w2500):.2f}～{max(candidate_w2500):.2f}h。",
        f"- formal W10,000の旧Weapon中央値は{old_weapon_w10000:.2f} Power。新50%シェアの直接寄与は指数前でlog10(2)=0.301 Powerなので、同じ敵曲線を保ったままの置換にはならない。",
        "- A/B/Cは比較用の逆算曲線であり、そのまま採用・Freezeするかは成功率と時間分布を見て判断する。敵曲線や別成長源は本分析では変更していない。",
    ])
    lines.extend([
        "- W10倍率×1.10以外のCommon Weapon multiplierは正式仕様に存在しないため、Phase 3–4では比較用に×1.10固定とした。",
        "- Rarity/Affix/Unique Affixは戦闘Powerへ加えていない。正式v1の素材供給と加速炉への影響を隔離するため、レアリティ抽選自体は素材経済だけに残した。",
        "- 自動バランス調整および正式仕様への書き戻しは行っていない。",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260828)
    parser.add_argument("--max-attempts", type=int, default=450)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument(
        "--scenarios",
        default="none,A,B,C",
        help="comma-separated subset of none,A,B,C",
    )
    parser.add_argument(
        "--reuse-phase1",
        type=Path,
        help="reuse phase1 and its success rate from a previous analysis JSON",
    )
    parser.add_argument(
        "--reuse-none",
        action="store_true",
        help="with --reuse-phase1, also reuse the unchanged no-weapon phase4 result",
    )
    parser.add_argument(
        "--reuse-none-from",
        type=Path,
        help="reuse the curve-independent no-weapon result from an analysis JSON",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/weapon_atk_analysis"),
    )
    args = parser.parse_args()
    if args.trials <= 0 or args.workers <= 0 or args.max_attempts <= 0:
        parser.error("trials, workers, and max-attempts must be positive")
    scenarios = tuple(part.strip() for part in args.scenarios.split(",") if part.strip())
    invalid_scenarios = [name for name in scenarios if name not in {"none", "A", "B", "C"}]
    if not scenarios or invalid_scenarios:
        parser.error("--scenarios must be a comma-separated subset of none,A,B,C")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    previous: dict[str, Any] | None = None
    if args.reuse_phase1:
        previous = json.loads(args.reuse_phase1.read_text(encoding="utf-8"))
        phase1 = {int(wave): values for wave, values in previous["phase1"].items()}
        phase1_success_rate = float(previous["phase1_success_rate"])
        print(f"Phase 1: reused from {args.reuse_phase1}", flush=True)
    else:
        print(f"Phase 1: formal baseline ({args.trials} trials)", flush=True)
        phase1_rows = run_parallel(
            "baseline", (), args.trials, args.seed, args.max_attempts, args.workers
        )
        phase1 = summarize_phase1(phase1_rows)
        phase1_success_rate = sum(row["success"] for row in phase1_rows) / len(phase1_rows)
    curves, curve_rows = derive_curves(phase1)

    # Save Phase 1 before any comparison run so an interruption never loses it.
    write_phase1_csv(output_dir / "formal_phase1_checkpoints.csv", phase1)
    write_curve_csv(output_dir / "weapon_curve_candidates.csv", curve_rows)

    phase4: dict[str, dict[str, Any]] = {}
    save_staged_progress(
        output_dir,
        args.trials,
        args.seed,
        args.max_attempts,
        phase1_success_rate,
        phase1,
        curves,
        phase4,
    )
    for mode in scenarios:
        if mode == "none" and args.reuse_none_from:
            source = json.loads(args.reuse_none_from.read_text(encoding="utf-8"))
            phase4[mode] = source["phase4"]["none"]
            print(f"Phase 4: none reused from {args.reuse_none_from}", flush=True)
            continue
        if mode == "none" and args.reuse_none:
            if previous is None:
                parser.error("--reuse-none requires --reuse-phase1")
            phase4[mode] = previous["phase4"]["none"]
            print("Phase 4: none reused (curve-independent)", flush=True)
            continue
        print(f"Phase 4: {mode} ({args.trials} trials)", flush=True)
        anchors = curves.get(mode, ())
        rows = run_parallel(
            mode, anchors, args.trials, args.seed, args.max_attempts, args.workers
        )
        phase4[mode] = summarize_phase4(rows)
        # Persist after every condition; later conditions are never required
        # for earlier results to survive.
        save_staged_progress(
            output_dir,
            args.trials,
            args.seed,
            args.max_attempts,
            phase1_success_rate,
            phase1,
            curves,
            phase4,
        )
        print(
            f"  success={phase4[mode]['success_rate']:.1%} "
            f"best_wave_p50={phase4[mode]['best_wave_p50']:.0f}",
            flush=True,
        )

    if set(("none", "A", "B", "C")).issubset(phase4):
        write_phase1_csv(output_dir / "formal_phase1_checkpoints.csv", phase1)
        write_curve_csv(output_dir / "weapon_curve_candidates.csv", curve_rows)
        payload = {
            "conditions": {
                "trials": args.trials,
                "seed": args.seed,
                "max_attempts": args.max_attempts,
                "formal_variant": True,
                "defense": False,
                "common_weapon_multiplier": COMMON_WEAPON_MULTIPLIER,
            },
            "phase1_success_rate": phase1_success_rate,
            "phase1": phase1,
            "curves_effective_weapon_log10": {
                name: list(values) for name, values in curves.items()
            },
            "phase4": phase4,
        }
        (output_dir / "weapon_atk_analysis.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        report = build_report(
            args.trials,
            args.max_attempts,
            args.seed,
            phase1_success_rate,
            phase1,
            curves,
            curve_rows,
            phase4,
        )
        (output_dir / "weapon_atk_analysis.md").write_text(report, encoding="utf-8")
        print(f"report={output_dir / 'weapon_atk_analysis.md'}", flush=True)
    else:
        print(f"progress={output_dir / 'weapon_curve_200_progress.json'}", flush=True)


if __name__ == "__main__":
    main()
