#!/usr/bin/env python3
"""Independent deterministic stress test for card softcaps.

This script does not import or modify the formal first-prestige simulator.
It only evaluates the formulas supplied for this stress test.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


CRIT_CHECKPOINTS = (0, 100, 200, 300, 400, 600, 1000, 2000, 5000)
XP_MULTIPLIERS = (1, 1.5, 2, 3, 4, 5, 10, 20, 50)
CARD_COUNTS = (0, 10, 30, 50, 100, 250, 500, 1000, 2500)
BOSS_COUNTS = (0, 10, 30, 50, 100, 250, 500, 1000)
CRIT_MULTIPLIERS = (1.5, 2.0, 2.5, 3.0, 4.0, 5.0)
SINGULARITY_TIERS = tuple(range(1, 21)) + (30, 50, 100)
SINGULARITY_SUMMARY_TIERS = (1, 2, 3, 4, 5, 8, 10, 20, 30, 50, 100)
THRESHOLDS = (10.0, 100.0, 1e3, 1e6, 1e12)

CSV_FIELDS = (
    "system",
    "variant",
    "input_name",
    "input_value",
    "secondary_input_name",
    "secondary_input_value",
    "effective_tier",
    "increase_pct",
    "final_multiplier",
    "threshold",
    "first_tier_reaching_threshold",
)


def piecewise_steps(value: float, bands: tuple[tuple[float, float], ...]) -> int:
    steps = 0
    lower = 0.0
    for upper, step_size in bands:
        segment = max(0.0, min(value, upper) - lower)
        steps += math.floor((segment + 1e-12) / step_size)
        lower = upper
        if value <= upper:
            break
    return steps


def critical_steps(crit_rate_pct: float, variant: str) -> int:
    if variant == "current":
        bands = ((200.0, 25.0), (400.0, 50.0), (math.inf, 100.0))
    elif variant == "no_softcap":
        bands = ((math.inf, 25.0),)
    elif variant == "relaxed":
        bands = ((300.0, 25.0), (600.0, 50.0), (math.inf, 100.0))
    else:
        raise ValueError(f"unknown variant: {variant}")
    return piecewise_steps(crit_rate_pct, bands)


def critical_increase_pct(crit_rate_pct: float, variant: str) -> float:
    return critical_steps(crit_rate_pct, variant) * 5.0


def knowledge_conversion_increase(xp_multiplier: float) -> float:
    first = max(0.0, min(xp_multiplier, 2.0) - 1.0) * 0.25
    second = max(0.0, min(xp_multiplier, 4.0) - 2.0) * 0.125
    third = max(0.0, xp_multiplier - 4.0) * 0.05
    return first + second + third


def accelerated_learning_increase(cards_after: int) -> float:
    first = min(cards_after, 10) * 0.03
    second = max(0, min(cards_after, 30) - 10) * 0.015
    third = max(0, cards_after - 30) * 0.005
    return first + second + third


def boss_devourer_increase(bosses_after: int) -> float:
    first = min(bosses_after, 10) * 0.05
    second = max(0, min(bosses_after, 30) - 10) * 0.025
    third = max(0, bosses_after - 30) * 0.01
    return first + second + third


def effective_tier(tier: int) -> float:
    return (
        min(tier, 4)
        + max(min(tier - 4, 4), 0) * 0.5
        + max(tier - 8, 0) * 0.25
    )


def singularity_multiplier(crit_multiplier: float, tier: int, variant: str) -> tuple[float, float]:
    if variant == "normal":
        return 1.0 + tier * (crit_multiplier - 1.0), float(tier)
    if variant == "singularity_uncapped":
        return crit_multiplier**tier, float(tier)
    if variant == "singularity_softcap":
        tier_effective = effective_tier(tier)
        return crit_multiplier**tier_effective, tier_effective
    raise ValueError(f"unknown singularity variant: {variant}")


def first_tier_for_threshold(crit_multiplier: float, threshold: float, variant: str) -> int:
    if variant == "normal":
        return max(1, math.ceil((threshold - 1.0) / (crit_multiplier - 1.0) - 1e-12))
    if variant == "singularity_uncapped":
        return max(1, math.ceil(math.log(threshold) / math.log(crit_multiplier) - 1e-12))
    tier = 1
    log_threshold = math.log(threshold)
    log_crit = math.log(crit_multiplier)
    while effective_tier(tier) * log_crit + 1e-12 < log_threshold:
        tier += 1
    return tier


def crit_rate_grid() -> list[int]:
    values = list(range(0, 2001, 25))
    values.extend(range(2100, 5001, 100))
    return values


def make_row(
    system: str,
    variant: str,
    input_name: str,
    input_value: float | int,
    *,
    secondary_input_name: str = "",
    secondary_input_value: float | int | str = "",
    effective: float | str = "",
    increase_pct: float | str = "",
    multiplier: float | str = "",
    threshold: float | str = "",
    first_tier: int | str = "",
) -> dict[str, object]:
    return {
        "system": system,
        "variant": variant,
        "input_name": input_name,
        "input_value": input_value,
        "secondary_input_name": secondary_input_name,
        "secondary_input_value": secondary_input_value,
        "effective_tier": effective,
        "increase_pct": increase_pct,
        "final_multiplier": multiplier,
        "threshold": threshold,
        "first_tier_reaching_threshold": first_tier,
    }


def build_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for system in ("Critical Engine", "Critical Conversion"):
        for variant in ("current", "no_softcap", "relaxed"):
            for crit_rate in crit_rate_grid():
                increase = critical_increase_pct(crit_rate, variant)
                rows.append(
                    make_row(
                        system,
                        variant,
                        "crit_rate_pct",
                        crit_rate,
                        increase_pct=increase,
                        multiplier=1.0 + increase / 100.0,
                    )
                )

    for xp_multiplier in XP_MULTIPLIERS:
        increase = knowledge_conversion_increase(xp_multiplier)
        rows.append(
            make_row(
                "Knowledge Conversion",
                "current",
                "xp_multiplier",
                xp_multiplier,
                increase_pct=increase * 100.0,
                multiplier=1.0 + increase,
            )
        )

    for cards in CARD_COUNTS:
        increase = accelerated_learning_increase(cards)
        rows.append(
            make_row(
                "Accelerated Learning",
                "current",
                "cards_after_acquisition",
                cards,
                increase_pct=increase * 100.0,
                multiplier=1.0 + increase,
            )
        )

    for bosses in BOSS_COUNTS:
        increase = boss_devourer_increase(bosses)
        rows.append(
            make_row(
                "Boss Devourer",
                "current",
                "bosses_after_acquisition",
                bosses,
                increase_pct=increase * 100.0,
                multiplier=1.0 + increase,
            )
        )

    for crit_multiplier in CRIT_MULTIPLIERS:
        for variant in ("normal", "singularity_uncapped", "singularity_softcap"):
            for tier in SINGULARITY_TIERS:
                multiplier, tier_effective = singularity_multiplier(crit_multiplier, tier, variant)
                rows.append(
                    make_row(
                        "Critical Singularity",
                        variant,
                        "tier",
                        tier,
                        secondary_input_name="crit_multiplier",
                        secondary_input_value=crit_multiplier,
                        effective=round(tier_effective, 6),
                        multiplier=multiplier,
                    )
                )
            for threshold in THRESHOLDS:
                rows.append(
                    make_row(
                        "Critical Singularity Threshold",
                        variant,
                        "crit_multiplier",
                        crit_multiplier,
                        threshold=threshold,
                        first_tier=first_tier_for_threshold(
                            crit_multiplier, threshold, variant
                        ),
                    )
                )
    return rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def fmt_multiplier(value: float) -> str:
    if value >= 1e6:
        return f"{value:.3e}"
    if value >= 1000:
        return f"{value:,.1f}"
    return f"{value:.3f}".rstrip("0").rstrip(".")


def markdown_table(headers: list[str], rows: list[list[object]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return lines


def build_report(csv_name: str) -> str:
    lines = [
        "# カードSoftcap / Diminishing Returns ストレステスト",
        "",
        "## 前提",
        "",
        "- formal仕様と本体シミュレーターから独立した数式評価。ゲーム数値は変更していない。",
        "- `増加率`は同カテゴリ内の加算値、`最終倍率`は基礎1.0へ増加率を加えた表示。",
        "- Critical Singularityの閾値Tierは、その倍率へ初めて到達する（`>=`）整数Tier。",
        "",
        "## 1–2. Critical Engine / Critical Conversion",
        "",
        "両カードは変換先だけが異なり、増加曲線は同一。EngineはAS、ConversionはAll Damageへ加算する。",
        "",
    ]
    lines.extend(
        markdown_table(
            ["Crit Rate", "現仕様", "Softcapなし", "緩和案"],
            [
                [
                    f"{crit}%",
                    f"+{critical_increase_pct(crit, 'current'):.0f}%",
                    f"+{critical_increase_pct(crit, 'no_softcap'):.0f}%",
                    f"+{critical_increase_pct(crit, 'relaxed'):.0f}%",
                ]
                for crit in CRIT_CHECKPOINTS
            ],
        )
    )
    lines.extend(
        [
            "",
            "- 現仕様はCrit 200%で+40%、400%で+60%、2,000%でも+140%。Softcapなしの+400%を大きく抑える。",
            "- 400%以降も100ptごと+5%で線形に伸びるため無限Runでは無限だが、5,000%でも+290%に留まる。",
            "- 緩和案との差は2,000%で20pt、5,000%で20ptだけで、極端域の傾きは同じ。",
            "- 第一転生前を概ね0～400%帯と見るなら現仕様は十分機能。Hard Capを急いで追加する必要は薄い。",
            "",
            "## 3. Knowledge Conversion",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            ["XP倍率", "All Damage増加", "最終倍率"],
            [
                [
                    xp,
                    f"+{knowledge_conversion_increase(xp) * 100:.1f}%",
                    f"×{1 + knowledge_conversion_increase(xp):.3f}",
                ]
                for xp in XP_MULTIPLIERS
            ],
        )
    )
    lines.extend(
        [
            "",
            "- XP×4までにAll Damage+50%、以後はXP倍率+1ごとに+5%。段階Softcapは明確に機能する。",
            "- XP×10で+80%、×20で+130%、×50で+280%。極端域では無限線形だが、指数的な暴走ではない。",
            "- 第一転生前にXP×10前後なら現状維持で問題は小さい。将来XP×50超が常態化する段階で再Softcap候補。",
            "",
            "## 4. Accelerated Learning",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            ["取得後カード", "XP増加", "最終XP倍率"],
            [
                [
                    cards,
                    f"+{accelerated_learning_increase(cards) * 100:.1f}%",
                    f"×{1 + accelerated_learning_increase(cards):.3f}",
                ]
                for cards in CARD_COUNTS
            ],
        )
    )
    lines.extend(
        [
            "",
            "- 30枚で+60%、100枚で+95%、250枚で+170%。この範囲では強い成長カードだが急激な折れはない。",
            "- 31枚以降の+0.5%が線形継続するため、500枚で+295%、1,000枚で+545%、2,500枚で+1,295%。",
            "- 長期Runでは確実に支配的になる。第一転生前の実カード取得数が数百を超えるなら、Hard Capまたは第4帯が必要になる可能性が高い。",
            "",
            "## 5. Boss Devourer",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            ["取得後Boss撃破", "All Damage増加", "最終倍率"],
            [
                [
                    bosses,
                    f"+{boss_devourer_increase(bosses) * 100:.1f}%",
                    f"×{1 + boss_devourer_increase(bosses):.3f}",
                ]
                for bosses in BOSS_COUNTS
            ],
        )
    )
    lines.extend(
        [
            "",
            "- 30体で+100%、100体で+170%、500体で+570%。",
            "- Wave10,000までBossが1,000体いるため、最速取得の最悪ケースは+1,070%（×11.7）。",
            "- 31体以降+1%は長期Runで支配的になり得る。取得時期の分散が大きいほどカード運による格差も大きい。",
            "- 第一転生内の意図的なラン成長エンジンなら成立するが、早期取得が可能ならHard CapまたはBoss数帯の追加検証が必要。",
            "",
            "## 6. Critical Singularity",
            "",
            "### 指定Tierでの倍率",
            "",
        ]
    )
    singularity_rows: list[list[object]] = []
    for crit_multiplier in CRIT_MULTIPLIERS:
        for tier in SINGULARITY_SUMMARY_TIERS:
            normal, _ = singularity_multiplier(crit_multiplier, tier, "normal")
            uncapped, _ = singularity_multiplier(
                crit_multiplier, tier, "singularity_uncapped"
            )
            capped, tier_effective = singularity_multiplier(
                crit_multiplier, tier, "singularity_softcap"
            )
            singularity_rows.append(
                [
                    crit_multiplier,
                    tier,
                    f"{tier_effective:g}",
                    fmt_multiplier(normal),
                    fmt_multiplier(uncapped),
                    fmt_multiplier(capped),
                ]
            )
    lines.extend(
        markdown_table(
            ["Crit倍率", "Tier", "EffectiveTier", "通常", "Singularity無制限", "Softcapあり"],
            singularity_rows,
        )
    )
    lines.extend(["", "### 倍率閾値へ初めて到達するTier", ""])
    threshold_rows: list[list[object]] = []
    for crit_multiplier in CRIT_MULTIPLIERS:
        for threshold in THRESHOLDS:
            threshold_rows.append(
                [
                    crit_multiplier,
                    f"×{threshold:g}",
                    first_tier_for_threshold(crit_multiplier, threshold, "normal"),
                    first_tier_for_threshold(
                        crit_multiplier, threshold, "singularity_uncapped"
                    ),
                    first_tier_for_threshold(
                        crit_multiplier, threshold, "singularity_softcap"
                    ),
                ]
            )
    lines.extend(
        markdown_table(
            ["Crit倍率", "閾値", "通常", "無制限", "Softcapあり"],
            threshold_rows,
        )
    )
    lines.extend(
        [
            "",
            "- 無制限SingularityはTierが指数そのものになり、Crit倍率3ならTier13で×1e6、Tier26で×1e12へ到達する。",
            "- Softcap案はTier5～8を半減、Tier9以降を4分の1にし、急増点を大幅に後ろへ移す。",
            "- それでもTier9以降が無限に+0.25されるため、Tier50～100ではCrit倍率次第で巨大になる。",
            "- 第一転生前にTierが20以下ならSoftcap案は有効。Tier50以上が現実的なら、EffectiveTierのHard Capまたはさらに弱い第4帯が必要。",
            "",
            "## 7. 総合判定",
            "",
            "| カード | 第一転生前 | 極端条件 | 判定 |",
            "| --- | --- | --- | --- |",
            "| Critical Engine | 0～400%で+0～60% | Crit5,000%で+290% | 現Softcapは十分。Hard Cap優先度は低い |",
            "| Critical Conversion | Engineと同曲線 | Crit5,000%で+290% | 現Softcapは十分。All Damage枠全体との合算確認は必要 |",
            "| Knowledge Conversion | XP×4～10で+50～80% | XP×50で+280% | 現状維持可能。超長期のみ再Softcap候補 |",
            "| Accelerated Learning | ～250枚で最大+170% | 2,500枚で+1,295% | 長期線形尾部が弱い。将来Hard Cap/第4帯候補 |",
            "| Boss Devourer | 取得時期で大きく変動 | 最速取得で+1,070% | 長期支配・取得運格差に注意。追加帯候補 |",
            "| Critical Singularity無制限 | Tier上昇で即指数化 | Tier50～100で極端 | Softcapなしは危険 |",
            "| Critical Singularity Softcap | Tier20以下なら抑制有効 | Tier50以上で再び巨大 | 第一転生前Tier上限次第。Hard Cap検討価値あり |",
            "",
            f"全数値は `{csv_name}` に保存。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir", type=Path, default=Path("output/card_softcaps")
    )
    args = parser.parse_args()
    rows = build_rows()
    csv_path = args.output_dir / "card_softcap_stress_test.csv"
    report_path = args.output_dir / "card_softcap_stress_test.md"
    write_csv(csv_path, rows)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(build_report(csv_path.name), encoding="utf-8")
    print(f"rows={len(rows)}")
    print(f"csv={csv_path.resolve()}")
    print(f"report={report_path.resolve()}")


if __name__ == "__main__":
    main()
