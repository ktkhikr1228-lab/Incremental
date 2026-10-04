"""Isolated candidate inventory; not imported by formal/D/E or playtest.

No combat, drop RNG, forge, or reroll behavior is introduced here.
"""
from dataclasses import dataclass, field
import math


ENHANCEMENT_MULTIPLIERS = (1.0, 1.08, 1.16, 1.24)
ENHANCEMENT_COSTS = (4, 9, 16)
RELIC_DISMANTLE = {"C": 1, "U": 3, "R": 6}
WEAPON_DISMANTLE = {"C": 1, "U": 3, "R": 8, "E": 20, "L": 50}


@dataclass
class EquipmentItem:
    uid: str
    kind: str
    name: str
    rarity: str
    origin_wave: int
    base_atk: float = 0.0
    quality: float = 1.0
    affixes: dict[str, float] = field(default_factory=dict)
    unique_key: str | None = None
    enhancement: int = 0
    enhancement_spent: int = 0
    duplicate_levels: int = 0

    def validate(self):
        allowed = WEAPON_DISMANTLE if self.kind == "weapon" else RELIC_DISMANTLE
        if self.kind not in {"weapon", "relic"} or self.rarity not in allowed:
            raise ValueError("Invalid equipment kind/rarity")
        if not self.uid or not self.name or self.origin_wave < 0:
            raise ValueError("Invalid item identity")
        if not 0 <= self.enhancement <= 3 or not 0 <= self.duplicate_levels <= 10:
            raise ValueError("Invalid upgrade levels")
        if self.enhancement_spent != sum(ENHANCEMENT_COSTS[:self.enhancement]):
            raise ValueError("Invalid enhancement expenditure")
        values = [self.base_atk, self.quality, *self.affixes.values()]
        if any(not math.isfinite(v) or v < 0 for v in values):
            raise ValueError("Invalid numeric value")
        if self.kind == "relic" and self.quality != 1.0:
            raise ValueError("Relic quality is fixed in v0.1")

    @property
    def enhancement_multiplier(self):
        return ENHANCEMENT_MULTIPLIERS[self.enhancement]

    @property
    def duplicate_multiplier(self):
        """Only positive numeric unique effects may use this multiplier."""
        return 1.0 + 0.02 * self.duplicate_levels


@dataclass
class EquipmentInventory:
    items: dict[str, EquipmentItem] = field(default_factory=dict)
    weapon_slot: str | None = None
    relic_slots: list[str | None] = field(default_factory=lambda: [None] * 3)
    storage_capacity: dict[str, int] = field(default_factory=lambda: {"weapon": 5, "relic": 5})
    materials: dict[str, float] = field(default_factory=lambda: {"weapon": 0, "relic": 0})

    def equipped_ids(self):
        return {uid for uid in [self.weapon_slot, *self.relic_slots] if uid is not None}

    def stored_ids(self, kind):
        return [uid for uid, item in self.items.items()
                if item.kind == kind and uid not in self.equipped_ids()]

    def validate(self):
        if len(self.relic_slots) != 3:
            raise ValueError("Exactly three relic slots required")
        slots = [uid for uid in [self.weapon_slot, *self.relic_slots] if uid is not None]
        if len(slots) != len(set(slots)):
            raise ValueError("Item equipped twice")
        for uid, kind in [(self.weapon_slot, "weapon"), *[(u, "relic") for u in self.relic_slots]]:
            if uid is not None and (uid not in self.items or self.items[uid].kind != kind):
                raise ValueError("Invalid equipment slot")
        for uid, item in self.items.items():
            item.validate()
            if uid != item.uid:
                raise ValueError("Item ID mismatch")
        for kind in ("weapon", "relic"):
            if (not isinstance(self.storage_capacity[kind], int)
                    or self.storage_capacity[kind] < 5
                    or not math.isfinite(self.materials[kind]) or self.materials[kind] < 0):
                raise ValueError("Invalid capacity/balance")
            if len(self.stored_ids(kind)) > self.storage_capacity[kind]:
                raise ValueError("Storage full")

    def receive(self, item):
        """Reject overflow; caller must offer manual choices, never auto-dismantle."""
        item.validate()
        if item.uid in self.items:
            raise ValueError("Duplicate item ID")
        if len(self.stored_ids(item.kind)) >= self.storage_capacity[item.kind]:
            raise ValueError("Storage full")
        self.items[item.uid] = item

    def equip(self, uid, slot=0):
        item = self.items[uid]
        if uid in self.equipped_ids():
            return
        if item.kind == "weapon":
            self.weapon_slot = uid
        else:
            if slot not in range(3):
                raise ValueError("Invalid relic slot")
            self.relic_slots[slot] = uid

    def unequip(self, uid):
        item = self.items[uid]
        if uid not in self.equipped_ids():
            return
        if len(self.stored_ids(item.kind)) >= self.storage_capacity[item.kind]:
            raise ValueError("Storage full")
        self._clear_slot(uid)

    def _clear_slot(self, uid):
        if self.weapon_slot == uid:
            self.weapon_slot = None
        self.relic_slots = [None if u == uid else u for u in self.relic_slots]

    def dismantle_preview(self, uid):
        item = self.items[uid]
        table = WEAPON_DISMANTLE if item.kind == "weapon" else RELIC_DISMANTLE
        return table[item.rarity] + item.enhancement_spent // 2

    def dismantle(self, uid):
        amount = self.dismantle_preview(uid)
        kind = self.items[uid].kind
        self._clear_slot(uid)
        del self.items[uid]
        self.materials[kind] += amount
        return amount

    def enhance(self, uid):
        item = self.items[uid]
        if item.enhancement == 3:
            raise ValueError("Enhancement limit")
        cost = ENHANCEMENT_COSTS[item.enhancement]
        if self.materials[item.kind] < cost:
            raise ValueError("Insufficient material")
        self.materials[item.kind] -= cost
        item.enhancement += 1
        item.enhancement_spent += cost

    def absorb_duplicate(self, kept_uid, consumed_uid):
        kept, consumed = self.items[kept_uid], self.items[consumed_uid]
        if kept_uid == consumed_uid or kept.kind != "relic" or consumed.kind != "relic" or kept.name != consumed.name:
            raise ValueError("Requires two same-name relics")
        if kept.duplicate_levels >= 10:
            raise ValueError("Duplicate limit")
        self._clear_slot(consumed_uid)
        del self.items[consumed_uid]
        kept.duplicate_levels += 1

    def replace_relic(self, old_uid, new_uid):
        old, new = self.items[old_uid], self.items[new_uid]
        if old_uid == new_uid or old.kind != "relic" or new.kind != "relic" or old.name != new.name:
            raise ValueError("Requires two same-name relics")
        slot = self.relic_slots.index(old_uid) if old_uid in self.relic_slots else None
        amount = self.dismantle(old_uid)
        if slot is not None:
            self.equip(new_uid, slot)
        return amount

    def on_death(self):
        """Candidate recovery: 50% normal weapon value, not upgrade refund."""
        for uid in list(self.items):
            item = self.items[uid]
            if item.kind == "weapon":
                self.materials["weapon"] += WEAPON_DISMANTLE[item.rarity] / 2
                self._clear_slot(uid)
                del self.items[uid]

    def on_prestige(self):
        self.items.clear()
        self.weapon_slot = None
        self.relic_slots = [None] * 3
        self.storage_capacity = {"weapon": 5, "relic": 5}
        self.materials = {"weapon": 0, "relic": 0}

    def to_dict(self):
        from dataclasses import asdict
        self.validate()
        return {"version": 1, **asdict(self)}

    @classmethod
    def from_dict(cls, data):
        import copy
        state = copy.deepcopy(data)
        if state.pop("version", None) != 1:
            raise ValueError("Unsupported inventory version")
        state["items"] = {uid: EquipmentItem(**item) for uid, item in state["items"].items()}
        result = cls(**state)
        result.validate()
        return result
