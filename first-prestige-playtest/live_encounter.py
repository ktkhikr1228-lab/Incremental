"""Segmented expected/discrete combat for manual UI mutations only.

Keeps elapsed time, remaining HP and fractional attack progress across edits.
Uses the candidate temporal integral; no future cards or random combat draws.
"""
import math
import new_w5000_rules as rules


def project(enemy_power, limit, snap, start=0.0, remaining=1.0, phase=0.0):
    required = 10 ** max(-308, min(308, enemy_power - snap.log_dps))
    hopeless = enemy_power - snap.log_dps > 308
    # Integral anchor is the previous attack, not the UI action timestamp.
    # Otherwise repeatedly opening panels loses fractional attack damage.
    anchor = start - phase / snap.attack_speed
    base = rules.epic.temporal_integral(max(0.0, anchor), limit, snap)
    if anchor < 0:
        base += anchor * snap.first_strike_mult
    max_hits = max(0, int(math.floor(phase + (limit - start) * snap.attack_speed + 1e-12)))

    def normal(n):
        if n <= 0 or hopeless:
            return 0.0
        time = start + (n - phase) / snap.attack_speed
        return max(0.0, rules.epic.temporal_integral(time, limit, snap) - base) / required

    def first(target):
        lo, hi = 1, max_hits
        if hi < 1 or normal(hi) < target * (1 - 1e-12):
            return None
        while lo < hi:
            mid = (lo + hi) // 2
            if normal(mid) >= target * (1 - 1e-12):
                hi = mid
            else:
                lo = mid + 1
        return lo

    crossing = first(remaining - .30) if remaining > .30 and snap.execution_mult > 1 else None
    cross_damage = normal(crossing) if crossing is not None else 0.0

    def damage(n):
        value = normal(n)
        if snap.execution_mult > 1:
            if remaining <= .30:
                value *= snap.execution_mult
            elif crossing is not None and n >= crossing:
                value = cross_damage + (value - cross_damage) * snap.execution_mult
        return value

    def hp(time):
        n = max(0, math.floor(phase + (min(limit, max(start, time)) - start) * snap.attack_speed + 1e-12))
        return max(0.0, min(remaining, remaining - damage(n)))

    ttk = None
    if max_hits and damage(max_hits) >= remaining * (1 - 1e-12):
        lo, hi = 1, max_hits
        while lo < hi:
            mid = (lo + hi) // 2
            if damage(mid) >= remaining * (1 - 1e-12):
                hi = mid
            else:
                lo = mid + 1
        ttk = start + (lo - phase) / snap.attack_speed
    return ttk, hp
