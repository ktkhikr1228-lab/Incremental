#!/usr/bin/env python3
"""Monte Carlo check for the proposed first-prestige HP and DP curves.

This is intentionally an economy/progression-envelope simulation. The concrete
card pool, XP thresholds, weapon rolls, and relic rolls are not specified yet,
so the model samples runs around explicit target-wave checkpoints instead of
inventing those systems and presenting the result as settled combat balance.
"""

from __future__ import annotations

import argparse
import math
import random
import statistics
from dataclasses import dataclass
from pathlib import Path


TRIALS = 20_000
SEED = 20260826
PRESTIGE_WAVE = 1_000
P50 = 2.5
HP_EXPONENT = 1.65
DP_BASE_COST = 5.0
DP_COST_GROWTH = 1.025

# Attempt number -> median target wave before build/player variance.
# Attempt 1 is the first run. A failed attempt awards DP and adds one death.
WAVE_CHECKPOINTS = (
    (1, 34),
    (5, 60),
    (10, 110),
    (20, 270),
    (30, 600),
    (35, 800),
    (40, 950),
    (45, 1_120),
    (55, 1_500),
)


@dataclass(frozen=True)
class TrialResult:
    first_wave: int
    first_dp: int
    deaths: int
    attempts: int
    total_kills: int
    total_dp: int
    permanent_levels: int
    unspent_dp: int
    noncombat_seconds: float
    required_seconds_per_kill_for_12h: float


def lerp_checkpoint(attempt: int) -> float:
    for (a0, w0), (a1, w1) in zip(WAVE_CHECKPOINTS, WAVE_CHECKPOINTS[1:]):
        if a0 <= attempt <= a1:
            t = (attempt - a0) / (a1 - a0)
            return w0 + (w1 - w0) * t
    a0, w0 = WAVE_CHECKPOINTS[-2]
    a1, w1 = WAVE_CHECKPOINTS[-1]
    slope = (w1 - w0) / (a1 - a0)
    return w1 + slope * (attempt - a1)


def enemy_power(wave: int, p50: float = P50, exponent: float = HP_EXPONENT) -> float:
    """log10(HP) for the post-Wave-50 proposal.

    Wave 1-50 remains the separately tuned early-game table. Only its Wave 50
    endpoint is needed here.
    """
    if wave <= 50:
        # Placeholder interpolation for reporting only; combat is not simulated.
        p1 = math.log10(5)
        return p1 + (p50 - p1) * (wave - 1) / 49
    x = (wave - 50) / (PRESTIGE_WAVE - 50)
    x = min(max(x, 0.0), 1.0)
    return p50 + (308.0 - p50) * x**exponent


def buy_all_levels(dp: int, growth: float = DP_COST_GROWTH) -> tuple[int, int]:
    levels = 0
    remaining = dp
    while True:
        cost = math.ceil(DP_BASE_COST * growth**levels)
        if remaining < cost:
            return levels, remaining
        remaining -= cost
        levels += 1


def estimated_choice_seconds(wave: int, attempt: int) -> float:
    # 1.7*sqrt(wave) gives about 10 cards at Wave 34 and about 54 at Wave 1000.
    cards = max(1, round(1.7 * math.sqrt(wave)))
    if attempt <= 5:
        seconds_per_card = 6.0
    elif attempt <= 15:
        seconds_per_card = 4.0
    elif attempt <= 25:
        seconds_per_card = 2.0
    elif attempt <= 30:
        seconds_per_card = 0.75
    else:
        seconds_per_card = 0.10
    return cards * seconds_per_card


def run_trial(rng: random.Random) -> TrialResult:
    # Persistent player/build quality plus independent per-run card luck.
    player_factor = math.exp(rng.gauss(-0.5 * 0.07**2, 0.07))
    total_kills = 0
    total_dp = 0
    choice_seconds = 0.0
    wall_seconds = 0.0
    first_wave = 0

    for attempt in range(1, 81):
        run_factor = math.exp(rng.gauss(-0.5 * 0.09**2, 0.09))
        reached = max(1, round(lerp_checkpoint(attempt) * player_factor * run_factor))
        reached = min(reached, PRESTIGE_WAVE)
        if attempt == 1:
            first_wave = reached
        total_kills += reached
        choice_seconds += estimated_choice_seconds(reached, attempt)

        if reached >= PRESTIGE_WAVE:
            levels, unspent = buy_all_levels(total_dp)
            noncombat_seconds = choice_seconds + wall_seconds
            required = max(0.0, 12 * 3600 - noncombat_seconds) / total_kills
            return TrialResult(
                first_wave=first_wave,
                first_dp=first_wave // 5,
                deaths=attempt - 1,
                attempts=attempt,
                total_kills=total_kills,
                total_dp=total_dp,
                permanent_levels=levels,
                unspent_dp=unspent,
                noncombat_seconds=noncombat_seconds,
                required_seconds_per_kill_for_12h=required,
            )

        # DP is awarded only after a failed run/death. The successful prestige
        # run ends immediately and therefore does not grant death points.
        total_dp += reached // 5
        wall_seconds += 15.0 if (reached + 1) % 10 == 0 else 10.0

    raise RuntimeError("A trial did not reach the prestige wave within 80 attempts")


def percentile(values: list[float] | list[int], q: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * q
    lo = math.floor(index)
    hi = math.ceil(index)
    if lo == hi:
        return float(ordered[lo])
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (index - lo)


def summary_row(values: list[float] | list[int], digits: int = 1) -> str:
    mean = statistics.fmean(values)
    return " | ".join(
        f"{value:.{digits}f}"
        for value in (
            mean,
            percentile(values, 0.10),
            percentile(values, 0.50),
            percentile(values, 0.90),
        )
    )


def levels_for_growth(dp_values: list[int], growth: float) -> list[int]:
    return [buy_all_levels(dp, growth)[0] for dp in dp_values]


def build_report(results: list[TrialResult]) -> str:
    first_waves = [r.first_wave for r in results]
    first_dps = [r.first_dp for r in results]
    deaths = [r.deaths for r in results]
    kills = [r.total_kills for r in results]
    dps = [r.total_dp for r in results]
    levels = [r.permanent_levels for r in results]
    required_spe = [r.required_seconds_per_kill_for_12h for r in results]

    within_death_target = sum(35 <= value <= 45 for value in deaths) / len(results)
    within_level_target = sum(100 <= value <= 150 for value in levels) / len(results)
    first_costs = [math.ceil(DP_BASE_COST * DP_COST_GROWTH**n) for n in range(15)]

    lines = [
        "# 第一転生・基準曲線シミュレーション",
        "",
        "## 前提",
        "",
        f"- モンテカルロ試行: {len(results):,}人（seed={SEED}）",
        f"- 第一転生: Wave {PRESTIGE_WAVE}、敵HP `1e308`",
        f"- Wave 51以降: `P=P50+(308-P50)*x^{HP_EXPONENT}`（例示用P50={P50}）",
        "- DP獲得: 失敗ラン終了時に `floor(撃退数/5)`",
        f"- 次Lvコスト: `ceil({DP_BASE_COST:g}*{DP_COST_GROWTH}^合計Lv)`",
        "- 成功ランは即転生するため、そのランのDPは獲得しない",
        "- カード・XP・装備数値が未確定のため、到達Waveは設計目標チェックポイント周辺で変動させた",
        "",
        "## 結果",
        "",
        "| 指標 | 平均 | P10 | 中央値 | P90 |",
        "|---|---:|---:|---:|---:|",
        f"| 初ラン撃退数 | {summary_row(first_waves, 1)} |",
        f"| 初ランDP | {summary_row(first_dps, 1)} |",
        f"| 転生までの死亡回数 | {summary_row(deaths, 1)} |",
        f"| 累計撃破数 | {summary_row(kills, 0)} |",
        f"| 累計DP | {summary_row(dps, 0)} |",
        f"| 恒久強化合計Lv | {summary_row(levels, 0)} |",
        f"| 12時間に必要な平均戦闘秒/体 | {summary_row(required_spe, 2)} |",
        "",
        f"- 死亡35〜45回に収まった割合: **{within_death_target:.1%}**",
        f"- 合計Lv100〜150に収まった割合: **{within_level_target:.1%}**",
        "",
        "## 敵Powerチェックポイント",
        "",
        "| Wave | Power=log10(HP) | HP概算 |",
        "|---:|---:|---:|",
    ]
    for wave in (50, 100, 250, 500, 750, 900, 1000):
        power = enemy_power(wave)
        lines.append(f"| {wave} | {power:.2f} | `1e{power:.2f}` |")

    lines.extend(
        [
            "",
            "## 区間ごとに要求される火力成長",
            "",
            "| 区間 | Power増加 | 1Waveあたり平均倍率 |",
            "|---|---:|---:|",
        ]
    )
    for start, end in ((50, 100), (100, 250), (250, 500), (500, 750), (750, 1000)):
        delta = enemy_power(end) - enemy_power(start)
        multiplier = 10 ** (delta / (end - start))
        lines.append(f"| {start}→{end} | +{delta:.2f}桁 | ×{multiplier:.2f}/Wave |")

    lines.extend(
        [
            "",
            "## DP価格上昇率の感度",
            "",
            "同じDP収入で価格上昇率だけを変えた場合です。",
            "",
            "| 価格上昇率 | 合計Lv平均 | P10 | 中央値 | P90 |",
            "|---:|---:|---:|---:|---:|",
        ]
    )
    for growth in (1.020, 1.021, 1.0225, 1.025, 1.0275, 1.030):
        alternate = levels_for_growth(dps, growth)
        lines.append(f"| {100*(growth-1):.2f}% | {summary_row(alternate, 0)} |")

    lines.extend(
        [
            "",
            "## プレイ時間の感度",
            "",
            "カード選択時間は初期ほど長く、後半は自動化される仮定です。下表の戦闘秒/体には攻撃演出や敵切替時間も含みます。",
            "",
            "| 全期間の平均戦闘秒/体 | 総プレイ時間平均 | P10 | 中央値 | P90 |",
            "|---:|---:|---:|---:|---:|",
        ]
    )
    for seconds_per_enemy in (1.5, 2.0, 2.5, 2.75, 3.0):
        hours = [
            (r.noncombat_seconds + seconds_per_enemy * r.total_kills) / 3600
            for r in results
        ]
        lines.append(f"| {seconds_per_enemy:.2f}秒 | {summary_row(hours, 1)} |")

    lines.extend(
        [
            "",
            "## 読み方",
            "",
            "`12時間に必要な平均戦闘秒/体`は、カード選択時間と各失敗時の制限時間を差し引いた残りを累計撃破数で割った値です。実装後の平均がこれより短ければ第一転生は12時間未満、長ければ12時間超になります。",
            "",
            "初期15レベルの価格: `" + ", ".join(map(str, first_costs)) + "`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=TRIALS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    rng = random.Random(SEED)
    results = [run_trial(rng) for _ in range(args.trials)]
    report = build_report(results)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
