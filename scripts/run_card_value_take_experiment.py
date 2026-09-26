#!/usr/bin/env python3
"""Paired Balanced Standard Take-mode diagnostic; exploratory, not a balance claim."""
from __future__ import annotations

import argparse
import collections
import copy
import json
import random
from dataclasses import replace
from pathlib import Path

import simulate_first_prestige_v1 as sim


def first_divergence(legacy, pe):
    for old, new in zip(legacy, pe):
        inputs = ("attempt", "decision_index", "next_wave", "phase",
                  "hand_keys", "pre_decision_rng_digest")
        if any(old.get(field) != new.get(field) for field in inputs):
            return {"kind": "input_divergence", "legacy": old, "pe": new}
        if (old["action"], old["selected_card"]) != (new["action"], new["selected_card"]):
            return {"kind": "selection_divergence", "legacy": old, "pe": new}
    if len(legacy) != len(pe):
        return {"kind": "decision_count_divergence", "legacy_count": len(legacy),
                "pe_count": len(pe)}
    return None


def trial_result_summary(result):
    return {"success": result.success, "attempts": result.attempts,
            "first_reached": result.first_reached, "best_failed_wave": result.best_failed_wave,
            "total_kills": result.total_kills,
            "total_seconds": result.total_combat_seconds + result.total_interaction_seconds,
            "total_choices": result.total_choices,
            "total_cards_dissolved": result.total_cards_dissolved,
            "total_card_upgrades": result.total_card_upgrades}


def build_report(seed, max_attempts, pairs, old_summary=None):
    pe_rows = [row for pair in pairs for row in pair["branches"]["pe"]]
    takes = [row for row in pe_rows if row["action"] == "take"]
    applied = sum(row["decision_source"] == "pe" for row in takes)
    fallback = [row for row in takes if row["decision_source"] == "fallback_legacy"]
    reasons = collections.Counter(row["fallback_reason"].split(":", 1)[0] for row in fallback)
    unsupported = collections.Counter(
        entry["card_id"] for row in fallback for entry in row["candidates"]
        if entry["pe_status"] == "unsupported_card")
    summary = {"seed": seed, "trials": len(pairs), "max_attempts": max_attempts,
               "pe_take_opportunities": len(takes), "pe_applied": applied,
               "pe_application_rate": applied / len(takes) if takes else None,
               "fallback_count": len(fallback),
               "fallback_rate": len(fallback) / len(takes) if takes else None,
               "fallback_reasons": dict(sorted(reasons.items())),
               "unsupported_cards": dict(sorted(unsupported.items())),
               "first_divergences": [pair["first_divergence"] for pair in pairs]}
    lines = [f"# Balanced Take-only PE: 同seed {len(pairs)}組の探索的診断（合法Take候補限定）", "",
             f"seed={seed}、各trialの初期RNG seed=`{seed}+1,000,000+trial_index`、"
             f"max_attempts={max_attempts}、POあり、workers=1。", "",
             "## PE適用とfallback", "",
             f"- Take判断 {len(takes)}件中、PE適用 {applied}件"
             f"（{applied / len(takes):.2%}）" if takes else "- Take判断なし",
             f"- fallback {len(fallback)}件（{len(fallback) / len(takes):.2%}）" if takes else "- fallbackなし",
             f"- 理由別: {dict(sorted(reasons.items()))}",
             f"- 未対応カード別: {dict(sorted(unsupported.items()))}", "",
             "## trial別の最初の選択分岐", "",
             "| trial | 初分岐 | PE適用/Take | fallback/Take |",
             "|---:|---|---:|---:|"]
    for pair in pairs:
        first = pair["first_divergence"]
        if first is None:
            first_text = "分岐なし"
        elif first["kind"] == "selection_divergence":
            old, new = first["legacy"], first["pe"]
            first_text = (f"attempt {old['attempt']} / W{old['next_wave']} / "
                          f"decision {old['decision_index']}: "
                          f"{old['action']} {old['selected_card']} → {new['action']} {new['selected_card']}")
        else:
            first_text = f"{first['kind']}（ログ確認）"
        total = pair["take_opportunities"]
        lines.append(f"| {pair['trial_index']} | {first_text} | "
                     f"{pair['pe_applied']}/{total} | {pair['fallback_count']}/{total} |")
    lines.extend(["", "## 最初の分岐手札: 全提示カード（Take不能はPE未評価）", ""])
    for pair in pairs:
        first = pair["first_divergence"]
        if not first or first["kind"] != "selection_divergence":
            continue
        old, new = first["legacy"], first["pe"]
        lines.extend([f"### trial {pair['trial_index']} / attempt {new['attempt']} / W{new['next_wave']}", "",
                      f"legacy={old['selected_card']}、PE mode={new['selected_card']}、"
                      f"source={new['decision_source']}、fallback={new['fallback_reason']}、"
                      f"H={next((c.get('predicted_run_end_wave') for c in new['candidates'] if c.get('predicted_run_end_wave') is not None), '—')}。",
                      f"手札: {', '.join(new['hand_keys'])}。Reroll: {new['rerolls_used']}回、"
                      f"Refine gate: {new['legacy_refine_gate']}。", "",
                      "| 候補 | Take可 | legacy | Immediate | Conditional | Combat PE | Growth PE | XP PE | Total PE | confidence | terminal Δp (非加算) | PE状態 |",
                      "|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---|"])
        def number(value):
            return f"{value:+.5f}" if isinstance(value, (float, int)) else "—"
        scored = {candidate["card_id"]: candidate for candidate in new["candidates"]}
        for card_id in new["hand_keys"]:
            candidate = scored[card_id]
            immediate = candidate.get("immediate_combat_pe")
            conditional = candidate.get("conditional_combat_pe")
            combat = immediate + conditional if isinstance(immediate, (int, float)) and isinstance(conditional, (int, float)) else None
            lines.append("| " + " | ".join((
                candidate["card_id"], "yes" if candidate["take_eligible"] else "no",
                number(candidate.get("legacy_score")),
                number(candidate.get("immediate_combat_pe")),
                number(candidate.get("conditional_combat_pe")),
                number(combat), number(candidate.get("growth_pe")), number(candidate.get("xp_pe")),
                number(candidate.get("total_pe")),
                str(candidate.get("prediction_confidence") or "—"),
                number(candidate.get("terminal_break_probability_delta")),
                candidate["pe_status"],
            )) + " |")
        lines.append("")
    lines.extend(["## 明らかに不自然なTakeの機械的点検", ""])
    red_flags = []
    ambiguous = []
    tie_counts = {"zero_pe": 0, "positive": 0, "negative": 0}
    exact_ties = {"zero_pe": 0, "positive": 0, "negative": 0}
    for pair in pairs:
        for row in pair["branches"]["pe"]:
            if row["action"] != "take" or row["decision_source"] != "pe":
                continue
            eligible = set(row["eligible_keys"])
            valid = [candidate for candidate in row["candidates"] if candidate["pe_status"] == "ok"]
            eligible_valid = [candidate for candidate in valid if candidate["take_eligible"]]
            if eligible_valid:
                ordered = sorted((candidate["total_pe"] for candidate in eligible_valid), reverse=True)
                if len(ordered) > 1 and ordered[0] - ordered[1] <= 1e-10:
                    ambiguous.append((pair["trial_index"], row["attempt"], row["decision_index"]))
                    category = "zero_pe" if abs(ordered[0]) <= 1e-10 else "positive" if ordered[0] > 0 else "negative"
                    tie_counts[category] += 1
                    if ordered[0] == ordered[1]:
                        exact_ties[category] += 1
            if (row["selected_card"] not in eligible or len(eligible_valid) != len(eligible)
                    or set(row["evaluated_pe_keys"]) != eligible
                    or any(candidate["pe_status"] != "ineligible_take"
                           for candidate in row["candidates"] if not candidate["take_eligible"])
                    or not eligible_valid or any(candidate["total_pe"] > next(
                        chosen["total_pe"] for chosen in eligible_valid
                        if chosen["card_id"] == row["selected_card"]) + 1e-12
                        for candidate in eligible_valid)):
                red_flags.append((pair["trial_index"], row["attempt"], row["decision_index"]))
    lines.append(f"- 不正な候補/非最大PEの選択: {len(red_flags)}件 {red_flags}")
    lines.append(f"- PE同値・近同値（上位2候補の差≤1e-10）: zero-PE tie {tie_counts['zero_pe']}件、"
                 f"positive tie {tie_counts['positive']}件、negative tie {tie_counts['negative']}件。"
                 "zeroは最高PEの絶対値≤1e-10、positiveは最高PE>1e-10。")
    lines.append(f"- うち厳密な同値（手札順tie-break適用）: {exact_ties}。"
                 "近同値でも数値が異なれば最大PEで選択する。")
    lines.append(f"- 同値の識別子（trial,attempt,decision）: {ambiguous}")
    lines.append("- 合法Take候補に未対応カードがないか、Take不能カードが評価されていないか、最初の分岐の軸別値・H・低信頼予測を上表とJSONLで確認する。")
    lines.append(f"- この{len(pairs)}組は探索的診断であり、成功率やビルド強度の優劣は結論にしない。")
    lines.append("")
    summary["red_flags"] = red_flags
    summary["ambiguous_pe_takes"] = ambiguous
    summary["tie_counts"] = tie_counts
    summary["exact_tie_counts"] = exact_ties
    if old_summary is not None:
        old_applied = old_summary["pe_applied"]
        old_total = old_summary["pe_take_opportunities"]
        old_rate = old_applied / old_total
        diff = {"old_applied": old_applied, "old_take_opportunities": old_total,
                "old_rate": old_rate, "applied_delta": applied - old_applied,
                "take_opportunities_delta": len(takes) - old_total,
                "application_rate_delta_pp": 100 * (summary["pe_application_rate"] - old_rate),
                "fallback_delta": len(fallback) - old_summary["fallback_count"]}
        summary["old_spec_comparison"] = diff
        lines.extend(["## 旧・全提示カード判定との比較", "",
                      f"- 旧仕様: {old_applied}/{old_total}（{old_rate:.2%}）、fallback {old_summary['fallback_count']}件。",
                      f"- 新仕様: {applied}/{len(takes)}（{summary['pe_application_rate']:.2%}）、fallback {len(fallback)}件。",
                      f"- 適用件数 {diff['applied_delta']:+d}、Take判断数 {diff['take_opportunities_delta']:+d}、"
                      f"適用率 {diff['application_rate_delta_pp']:+.2f}ポイント、fallback {diff['fallback_delta']:+d}件。",
                      "- 同じ初期seed・trial IDの探索的比較。選択分岐後は手札/Run/RNGがずれ得るため、"
                      "旧ログの反実仮想12.19%や成功率の優劣と同一視しない。", ""])
    return summary, "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=10)
    parser.add_argument("--seed", type=int, default=sim.SEED)
    parser.add_argument("--max-attempts", type=int, default=10)
    parser.add_argument("--output-prefix", type=Path, default=Path("output/card_value_take_eligible_pilot_10"))
    parser.add_argument("--old-summary", type=Path, default=Path("output/card_value_take_pilot_10.json"),
                        help="read-only reference for matching 10-trial comparison")
    args = parser.parse_args()
    if args.trials <= 0 or args.max_attempts <= 0:
        parser.error("trials and max-attempts must be positive")
    if args.output_prefix.resolve() == args.old_summary.with_suffix("").resolve():
        parser.error("new output prefix must differ from the old pilot prefix")
    pairs = []
    was_enabled = sim.TAKE_BRANCH_ENABLED
    old_context = copy.deepcopy(sim.TAKE_BRANCH_CONTEXT)
    old_rows = list(sim.TAKE_BRANCH_ROWS)
    try:
        sim.TAKE_BRANCH_ENABLED = True
        for trial_index in range(args.trials):
            results = {}
            branches = {}
            for mode in ("legacy", "pe"):
                sim.TAKE_BRANCH_ROWS.clear()
                sim.TAKE_BRANCH_CONTEXT.clear()
                sim.TAKE_BRANCH_CONTEXT.update({"seed": args.seed, "trial_index": trial_index,
                                                "profile": "balanced", "allow_overdrive": True})
                config = replace(sim.SimConfig(max_attempts=args.max_attempts), take_mode=mode)
                rng = random.Random(args.seed + 1_000_000 + trial_index)
                result = sim.run_trial(rng, "balanced", config, True)
                results[mode] = trial_result_summary(result)
                branches[mode] = copy.deepcopy(sim.TAKE_BRANCH_ROWS)
            pe_takes = [row for row in branches["pe"] if row["action"] == "take"]
            pairs.append({"trial_index": trial_index, "results": results, "branches": branches,
                          "take_opportunities": len(pe_takes),
                          "pe_applied": sum(row["decision_source"] == "pe" for row in pe_takes),
                          "fallback_count": sum(row["decision_source"] == "fallback_legacy" for row in pe_takes),
                          "first_divergence": first_divergence(branches["legacy"], branches["pe"])})
    finally:
        sim.TAKE_BRANCH_ENABLED = was_enabled
        sim.TAKE_BRANCH_ROWS[:] = old_rows
        sim.TAKE_BRANCH_CONTEXT.clear()
        sim.TAKE_BRANCH_CONTEXT.update(old_context)
    old_summary = None
    if args.old_summary.exists():
        reference = json.loads(args.old_summary.read_text(encoding="utf-8"))
        if (reference["seed"], reference["trials"], reference["max_attempts"]) == (
                args.seed, args.trials, args.max_attempts):
            old_summary = reference
    summary, markdown = build_report(args.seed, args.max_attempts, pairs, old_summary)
    prefix = args.output_prefix
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.with_suffix(".md").write_text(markdown, encoding="utf-8")
    prefix.with_suffix(".json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with prefix.with_name(prefix.name + "_branches.jsonl").open("w", encoding="utf-8") as out:
        for pair in pairs:
            for mode in ("legacy", "pe"):
                for row in pair["branches"][mode]:
                    out.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"{prefix}: PE {summary['pe_applied']}/{summary['pe_take_opportunities']}, "
          f"fallback {summary['fallback_count']}, divergences "
          f"{sum(first is not None for first in summary['first_divergences'])}/{len(pairs)}")


if __name__ == "__main__":
    main()
