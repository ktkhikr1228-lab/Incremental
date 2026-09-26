#!/usr/bin/env python3
"""Monte Carlo probe for Re-Action / Follow-Up / Hit Count chains.

This is deliberately independent from the first-prestige simulator.  It
measures processing volume only; damage and critical damage are out of scope.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


HIT_COUNTS = (1.0, 1.5, 2.0, 3.0, 5.0, 10.0)
FOLLOW_RATES = (0.0, 0.10, 0.25, 0.50)
REACTION_RATES = (0.10, 0.15, 0.25, 0.50, 0.75, 0.80, 0.90)


@dataclass(frozen=True)
class Mode:
    key: str
    label: str
    reaction_depth: int
    follow_depth: int


MODES = (
    Mode("A", "Rare Re-Action", 1, 1),
    Mode("B", "Epic Re-Action", 2, 1),
    Mode("C", "Legendary Re-Action", -1, 1),
    Mode("D", "Legendary Re-Action + recursive Follow-Up", -1, -1),
)


CSV_FIELDS = (
    "mode",
    "mode_label",
    "reaction_depth",
    "follow_depth",
    "reaction_sources",
    "trials",
    "hit_count",
    "follow_up_rate",
    "reaction_rate",
    "avg_actions",
    "avg_normal_attacks",
    "avg_follow_ups",
    "p50_actions",
    "p90_actions",
    "p95_actions",
    "p99_actions",
    "max_actions",
    "avg_total_hits",
    "p95_total_hits",
    "p99_total_hits",
    "max_total_hits",
    "cap_reached_rate",
    "hits_ge_100_rate",
    "hits_ge_500_rate",
    "hits_ge_1000_rate",
    "theory_avg_actions_unbounded",
    "theory_avg_actions_capped",
    "theory_mc_error",
)


def percentile_nearest(values: list[int], probability: float) -> int:
    """Nearest-rank percentile for discrete processing counts."""
    if not values:
        raise ValueError("percentile requires at least one value")
    index = max(0, math.ceil(probability * len(values)) - 1)
    return sorted(values)[index]


def can_spawn(depth_used: int, maximum_depth: int) -> bool:
    return maximum_depth < 0 or depth_used < maximum_depth


def simulate_action_count(
    rng: random.Random,
    mode: Mode,
    reaction_rate: float,
    follow_rate: float,
    max_actions: int,
    reaction_sources: str,
) -> tuple[int, int, int, bool]:
    """Simulate one initial normal attack and all descendant actions.

    Stack entries are (Re-Action depth, Follow-Up depth, is_normal_attack).
    A Re-Action child is a fresh normal attack, so its Follow-Up depth resets.
    A Follow-Up child preserves Re-Action depth and advances Follow-Up depth.
    """
    stack: list[tuple[int, int, bool]] = [(0, 0, True)]
    actions = 0
    normal_attacks = 0
    follow_ups = 0
    while stack:
        reaction_depth, follow_depth, is_normal = stack.pop()
        actions += 1
        if is_normal:
            normal_attacks += 1
        else:
            follow_ups += 1
        if actions >= max_actions:
            return max_actions, normal_attacks, follow_ups, True

        reaction_allowed = reaction_sources == "all" or is_normal
        reaction_depth_allowed = can_spawn(reaction_depth, mode.reaction_depth)
        reaction_roll = rng.random() if reaction_depth_allowed else 1.0
        if reaction_allowed and reaction_depth_allowed and reaction_roll < reaction_rate:
            stack.append((reaction_depth + 1, 0, True))

        if can_spawn(follow_depth, mode.follow_depth) and rng.random() < follow_rate:
            stack.append((reaction_depth, follow_depth + 1, False))

    return actions, normal_attacks, follow_ups, False


def sample_fractional_hits(rng: random.Random, actions: int, probability: float) -> int:
    if probability <= 0.0:
        return 0
    if hasattr(rng, "binomialvariate"):
        return rng.binomialvariate(actions, probability)
    return sum(rng.random() < probability for _ in range(actions))


def stable_group_seed(
    seed: int,
    mode_index: int,
    follow_index: int,
    reaction_index: int,
) -> int:
    return (
        seed
        + (mode_index + 1) * 1_000_003
        + (follow_index + 1) * 10_007
        + (reaction_index + 1) * 101
    )


def theory_values(mode: Mode, follow_rate: float, reaction_rate: float, cap: int) -> tuple[float | None, float | None]:
    if mode.key != "C" or follow_rate != 0.0:
        return None, None
    unbounded = 1.0 / (1.0 - reaction_rate)
    capped = (1.0 - reaction_rate**cap) / (1.0 - reaction_rate)
    return unbounded, capped


def simulate_matrix(
    trials: int,
    seed: int,
    max_actions: int,
    reaction_sources: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for mode_index, mode in enumerate(MODES):
        for follow_index, follow_rate in enumerate(FOLLOW_RATES):
            for reaction_index, reaction_rate in enumerate(REACTION_RATES):
                group_seed = stable_group_seed(seed, mode_index, follow_index, reaction_index)
                action_rng = random.Random(group_seed)
                action_counts: list[int] = []
                normal_counts: list[int] = []
                follow_counts: list[int] = []
                cap_flags: list[bool] = []
                for _ in range(trials):
                    count, normal_count, follow_count, capped = simulate_action_count(
                        action_rng,
                        mode,
                        reaction_rate,
                        follow_rate,
                        max_actions,
                        reaction_sources,
                    )
                    action_counts.append(count)
                    normal_counts.append(normal_count)
                    follow_counts.append(follow_count)
                    cap_flags.append(capped)

                action_counts_sorted = sorted(action_counts)
                cap_rate = sum(cap_flags) / trials
                avg_actions = sum(action_counts) / trials
                theory_unbounded, theory_capped = theory_values(
                    mode, follow_rate, reaction_rate, max_actions
                )

                for hit_index, hit_count in enumerate(HIT_COUNTS):
                    base_hits = math.floor(hit_count)
                    fractional = hit_count - base_hits
                    if fractional:
                        hit_rng = random.Random(group_seed + (hit_index + 1) * 10_000_019)
                        total_hits = [
                            base_hits * count
                            + sample_fractional_hits(hit_rng, count, fractional)
                            for count in action_counts
                        ]
                    else:
                        total_hits = [base_hits * count for count in action_counts]
                    total_hits_sorted = sorted(total_hits)

                    row = {
                        "mode": mode.key,
                        "mode_label": mode.label,
                        "reaction_depth": mode.reaction_depth,
                        "follow_depth": mode.follow_depth,
                        "reaction_sources": reaction_sources,
                        "trials": trials,
                        "hit_count": hit_count,
                        "follow_up_rate": follow_rate,
                        "reaction_rate": reaction_rate,
                        "avg_actions": round(avg_actions, 6),
                        "avg_normal_attacks": round(sum(normal_counts) / trials, 6),
                        "avg_follow_ups": round(sum(follow_counts) / trials, 6),
                        "p50_actions": percentile_nearest(action_counts_sorted, 0.50),
                        "p90_actions": percentile_nearest(action_counts_sorted, 0.90),
                        "p95_actions": percentile_nearest(action_counts_sorted, 0.95),
                        "p99_actions": percentile_nearest(action_counts_sorted, 0.99),
                        "max_actions": max(action_counts),
                        "avg_total_hits": round(sum(total_hits) / trials, 6),
                        "p95_total_hits": percentile_nearest(total_hits_sorted, 0.95),
                        "p99_total_hits": percentile_nearest(total_hits_sorted, 0.99),
                        "max_total_hits": max(total_hits),
                        "cap_reached_rate": round(cap_rate, 8),
                        "hits_ge_100_rate": round(sum(value >= 100 for value in total_hits) / trials, 8),
                        "hits_ge_500_rate": round(sum(value >= 500 for value in total_hits) / trials, 8),
                        "hits_ge_1000_rate": round(sum(value >= 1000 for value in total_hits) / trials, 8),
                        "theory_avg_actions_unbounded": (
                            round(theory_unbounded, 6) if theory_unbounded is not None else ""
                        ),
                        "theory_avg_actions_capped": (
                            round(theory_capped, 6) if theory_capped is not None else ""
                        ),
                        "theory_mc_error": (
                            round(avg_actions - theory_capped, 6)
                            if theory_capped is not None
                            else ""
                        ),
                    }
                    rows.append(row)
    return rows


def write_csv(path: Path, rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def percent(value: object) -> str:
    return f"{100 * float(value):.3f}%"


def markdown_table(headers: list[str], rows: list[list[object]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return lines


def one_row_per_chain(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [row for row in rows if float(row["hit_count"]) == 1.0]


def build_summary(
    rows: list[dict[str, object]],
    trials: int,
    seed: int,
    max_actions: int,
    reaction_sources: str,
    csv_name: str,
) -> str:
    chain_rows = one_row_per_chain(rows)
    lines = [
        "# Re-Action / Follow-Up / Hit Count 連鎖シミュレーション",
        "",
        "## 実行条件",
        "",
        f"- 各条件 `{trials:,}` 試行、seed `{seed}`、総攻撃行動数上限 `{max_actions}`。",
        f"- Re-Action抽選元: `{reaction_sources}`（`all`は通常攻撃と追撃の両方）。",
        "- A/B/CのFollow-Up深度は1、DのみFollow-Up再帰。",
        "- Re-Action子は新しい通常攻撃としてFollow-Up深度0から開始。",
        "- Hit Countの小数部分は攻撃行動ごとに独立抽選。CritとDamageは計算しない。",
        "- CSVの確率は0～1、Markdownでは百分率表記。分位点は離散値のnearest-rank。",
        "",
        "## 結論",
        "",
    ]

    recursive_d = [row for row in chain_rows if row["mode"] == "D"]
    first_cap_1: list[str] = []
    for follow_rate in FOLLOW_RATES:
        candidates = [
            row
            for row in recursive_d
            if float(row["follow_up_rate"]) == follow_rate
            and float(row["cap_reached_rate"]) >= 0.01
        ]
        if candidates:
            first = min(candidates, key=lambda row: float(row["reaction_rate"]))
            first_cap_1.append(
                f"Follow-Up {follow_rate:.0%}: Re-Action {float(first['reaction_rate']):.0%}"
            )
        else:
            first_cap_1.append(f"Follow-Up {follow_rate:.0%}: 検証範囲では1%未満")

    lines.extend(
        [
            "- 再帰Re-Action単独の危険度は幾何分布どおりで、平均は `1/(1-r)` に一致する。",
            "- Re-Actionと再帰Follow-Upを両方の攻撃行動から発生させるDでは、概ね `r + f = 1` 付近が急増境界になる。",
            "- 100行動上限到達率が1%以上になる最初の検証点: " + "; ".join(first_cap_1) + "。",
            "- 80%上限の安全性はFollow-Up率に依存する。再帰Follow-Up 25%以上との併用は単独80%とは別物として扱う必要がある。",
            "",
            "## 再帰Re-Action単独: 理論値との比較",
            "",
        ]
    )

    theory_rows = [
        row
        for row in chain_rows
        if row["mode"] == "C" and float(row["follow_up_rate"]) == 0.0
    ]
    lines.extend(
        markdown_table(
            ["Re-Action", "理論平均", "上限100理論", "MC平均", "誤差", "P99", "上限到達"],
            [
                [
                    f"{float(row['reaction_rate']):.0%}",
                    row["theory_avg_actions_unbounded"],
                    row["theory_avg_actions_capped"],
                    row["avg_actions"],
                    row["theory_mc_error"],
                    row["p99_actions"],
                    percent(row["cap_reached_rate"]),
                ]
                for row in theory_rows
            ],
        )
    )

    lines.extend(["", "## D: 再帰Re-Action + 再帰Follow-Up", ""])
    lines.extend(
        markdown_table(
            ["Follow-Up", "Re-Action", "r+f", "平均行動", "P95", "P99", "最大", "上限到達"],
            [
                [
                    f"{float(row['follow_up_rate']):.0%}",
                    f"{float(row['reaction_rate']):.0%}",
                    f"{float(row['follow_up_rate']) + float(row['reaction_rate']):.2f}",
                    row["avg_actions"],
                    row["p95_actions"],
                    row["p99_actions"],
                    row["max_actions"],
                    percent(row["cap_reached_rate"]),
                ]
                for row in recursive_d
            ],
        )
    )

    lines.extend(["", "## Re-Action 80%の詳細", ""])
    eighty_action_rows = [
        row
        for row in recursive_d
        if float(row["reaction_rate"]) == 0.80
    ]
    eighty_hit_rows = [
        row
        for row in rows
        if row["mode"] == "D"
        and float(row["reaction_rate"]) == 0.80
        and float(row["hit_count"]) == 10.0
    ]
    hit_lookup = {float(row["follow_up_rate"]): row for row in eighty_hit_rows}
    lines.extend(
        markdown_table(
            ["Follow-Up", "平均行動", "P95", "P99", "上限到達", "HC10: ≥100Hit", "≥500Hit", "≥1000Hit"],
            [
                [
                    f"{float(row['follow_up_rate']):.0%}",
                    row["avg_actions"],
                    row["p95_actions"],
                    row["p99_actions"],
                    percent(row["cap_reached_rate"]),
                    percent(hit_lookup[float(row["follow_up_rate"])]["hits_ge_100_rate"]),
                    percent(hit_lookup[float(row["follow_up_rate"])]["hits_ge_500_rate"]),
                    percent(hit_lookup[float(row["follow_up_rate"])]["hits_ge_1000_rate"]),
                ]
                for row in eighty_action_rows
            ],
        )
    )

    lines.extend(
        [
            "",
            "## 読み方",
            "",
            "- `上限到達`は連鎖が総攻撃行動数100へ達し、内部打ち切りになった割合。",
            "- `100/500/1000Hit以上`は1回の初期攻撃から生じた総Hit数。",
            "- Hit Countが整数の場合、総Hit数は攻撃行動数×Hit Count。1.5だけ追加Hitを独立抽選する。",
            f"- 全672条件の数値は `{csv_name}` を参照。",
            "",
        ]
    )
    return "\n".join(lines)


def build_comparison_summary(
    rows: list[dict[str, object]],
    trials: int,
    seed: int,
    max_actions: int,
    csv_name: str,
) -> str:
    focus_reactions = {0.50, 0.75, 0.80, 0.90}
    focus_follows = {0.10, 0.25, 0.50}
    focus = [
        row
        for row in rows
        if row["mode"] == "D"
        and float(row["reaction_rate"]) in focus_reactions
        and float(row["follow_up_rate"]) in focus_follows
    ]

    def lookup(source: str, reaction: float, follow: float, hit_count: float) -> dict[str, object]:
        return next(
            row
            for row in focus
            if row["reaction_sources"] == source
            and float(row["reaction_rate"]) == reaction
            and float(row["follow_up_rate"]) == follow
            and float(row["hit_count"]) == hit_count
        )

    lines = [
        "# Re-Action判定元の比較",
        "",
        "## 実行条件",
        "",
        f"- 各条件 `{trials:,}` 試行、seed `{seed}`、総連鎖上限 `{max_actions}`。",
        "- 旧方式 `all`: 通常攻撃とFollow-Upの両方がRe-Actionを抽選。",
        "- 新方式 `normal-only`: 初期通常攻撃とRe-Action通常攻撃だけがRe-Actionを抽選。",
        "- 両方式ともFollow-Up自身の再帰、Hit Count独立抽選、総連鎖上限は同一。",
        "- `平均通常攻撃`と`平均Follow-Up`を分離し、その合計を平均総イベント数として併記。",
        "",
        "## 連鎖量比較（D: Re-Action再帰 + Follow-Up再帰）",
        "",
    ]

    structure_rows: list[list[object]] = []
    for follow in sorted(focus_follows):
        for reaction in sorted(focus_reactions):
            old = lookup("all", reaction, follow, 1.0)
            new = lookup("normal-only", reaction, follow, 1.0)
            structure_rows.append(
                [
                    f"{reaction:.0%}",
                    f"{follow:.0%}",
                    old["avg_normal_attacks"],
                    old["avg_follow_ups"],
                    old["avg_actions"],
                    percent(old["cap_reached_rate"]),
                    new["avg_normal_attacks"],
                    new["avg_follow_ups"],
                    new["avg_actions"],
                    percent(new["cap_reached_rate"]),
                ]
            )
    lines.extend(
        markdown_table(
            [
                "Re-Action",
                "Follow-Up",
                "旧:平均通常攻撃",
                "旧:平均FU",
                "旧:総イベント",
                "旧:上限",
                "新:平均通常攻撃",
                "新:平均FU",
                "新:総イベント",
                "新:上限",
            ],
            structure_rows,
        )
    )

    lines.extend(["", "## Hit Count 10の比較", ""])
    hit_rows: list[list[object]] = []
    for follow in sorted(focus_follows):
        for reaction in sorted(focus_reactions):
            old = lookup("all", reaction, follow, 10.0)
            new = lookup("normal-only", reaction, follow, 10.0)
            hit_rows.append(
                [
                    f"{reaction:.0%}",
                    f"{follow:.0%}",
                    old["avg_total_hits"],
                    old["p95_total_hits"],
                    old["p99_total_hits"],
                    percent(old["hits_ge_100_rate"]),
                    percent(old["hits_ge_500_rate"]),
                    percent(old["hits_ge_1000_rate"]),
                    new["avg_total_hits"],
                    new["p95_total_hits"],
                    new["p99_total_hits"],
                    percent(new["hits_ge_100_rate"]),
                    percent(new["hits_ge_500_rate"]),
                    percent(new["hits_ge_1000_rate"]),
                ]
            )
    lines.extend(
        markdown_table(
            [
                "Re-Action",
                "Follow-Up",
                "旧:平均Hit",
                "旧:P95",
                "旧:P99",
                "旧:≥100",
                "旧:≥500",
                "旧:≥1000",
                "新:平均Hit",
                "新:P95",
                "新:P99",
                "新:≥100",
                "新:≥500",
                "新:≥1000",
            ],
            hit_rows,
        )
    )

    old_80_25 = lookup("all", 0.80, 0.25, 1.0)
    new_80_25 = lookup("normal-only", 0.80, 0.25, 1.0)
    old_80_50 = lookup("all", 0.80, 0.50, 1.0)
    new_80_50 = lookup("normal-only", 0.80, 0.50, 1.0)
    lines.extend(
        [
            "",
            "## 重要な発見",
            "",
            "- 新方式ではFollow-UpがRe-Action分岐を新しく作らないため、旧方式の `r+f≈1` による分岐爆発が消える。",
            f"- Re-Action 80% / Follow-Up 25%の上限到達率: 旧 `{percent(old_80_25['cap_reached_rate'])}` → 新 `{percent(new_80_25['cap_reached_rate'])}`。",
            f"- Re-Action 80% / Follow-Up 50%の上限到達率: 旧 `{percent(old_80_50['cap_reached_rate'])}` → 新 `{percent(new_80_50['cap_reached_rate'])}`。",
            "- 新方式でもRe-Action 90%と高Follow-Upの組み合わせは裾が長くなるため、P99と100上限到達率は確認が必要。",
            f"- 全Hit Count・全A～Dモードを含む比較数値は `{csv_name}` を参照。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260920)
    parser.add_argument("--max-actions", type=int, default=100)
    parser.add_argument(
        "--reaction-sources",
        choices=("all", "normal-only"),
        default="all",
        help="Whether Follow-Up actions can also proc Re-Action.",
    )
    parser.add_argument(
        "--compare-reaction-sources",
        action="store_true",
        help="Run both all and normal-only policies and write a side-by-side report.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/reaction_chain"),
    )
    args = parser.parse_args()
    if args.trials <= 0:
        parser.error("--trials must be greater than zero")
    if args.max_actions <= 0:
        parser.error("--max-actions must be greater than zero")

    if args.compare_reaction_sources:
        rows = []
        for source in ("all", "normal-only"):
            rows.extend(
                simulate_matrix(
                    trials=args.trials,
                    seed=args.seed,
                    max_actions=args.max_actions,
                    reaction_sources=source,
                )
            )
        suffix = f"comparison_{args.trials}"
    else:
        rows = simulate_matrix(
            trials=args.trials,
            seed=args.seed,
            max_actions=args.max_actions,
            reaction_sources=args.reaction_sources,
        )
        suffix = f"{args.reaction_sources}_{args.trials}"
    csv_path = args.output_dir / f"reaction_followup_{suffix}.csv"
    report_path = args.output_dir / f"reaction_followup_{suffix}.md"
    write_csv(csv_path, rows)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if args.compare_reaction_sources:
        report = build_comparison_summary(
            rows, args.trials, args.seed, args.max_actions, csv_path.name
        )
    else:
        report = build_summary(
            rows,
            args.trials,
            args.seed,
            args.max_actions,
            args.reaction_sources,
            csv_path.name,
        )
    report_path.write_text(report, encoding="utf-8")
    print(f"rows={len(rows)}")
    print(f"csv={csv_path.resolve()}")
    print(f"report={report_path.resolve()}")


if __name__ == "__main__":
    main()
