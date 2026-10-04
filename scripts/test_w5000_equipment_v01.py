import json
import unittest
from w5000_equipment_v01 import EquipmentInventory, EquipmentItem


def relic(uid, name="学習レンズ", rarity="R"):
    return EquipmentItem(uid, "relic", name, rarity, 100)


class EquipmentTests(unittest.TestCase):
    def test_capacity_and_atomic_overflow(self):
        inv = EquipmentInventory()
        for i in range(5):
            inv.receive(relic(str(i)))
        before = inv.to_dict()
        with self.assertRaises(ValueError):
            inv.receive(relic("overflow"))
        self.assertEqual(before, inv.to_dict())
        inv.equip("0")
        inv.receive(relic("extra"))
        inv.equip("1")
        inv.validate()
        with self.assertRaises(ValueError):
            inv.unequip("1")

    def test_three_slots_and_no_double_equipping(self):
        inv = EquipmentInventory()
        for i in range(3):
            inv.receive(relic(str(i)))
            inv.equip(str(i), i)
        inv.equip("0", 1)
        self.assertEqual(inv.relic_slots, ["0", "1", "2"])
        inv.validate()

    def test_identity_rejection(self):
        inv = EquipmentInventory()
        inv.receive(relic("a"))
        with self.assertRaises(ValueError):
            inv.receive(relic("a"))

    def test_enhance_costs_and_refund(self):
        inv = EquipmentInventory(materials={"weapon": 0, "relic": 29})
        inv.receive(relic("a"))
        for multiplier in (1.08, 1.16, 1.24):
            inv.enhance("a")
            self.assertEqual(inv.items["a"].enhancement_multiplier, multiplier)
        with self.assertRaises(ValueError):
            inv.enhance("a")
        self.assertEqual(inv.dismantle_preview("a"), 20)
        self.assertIn("a", inv.items)
        self.assertEqual(inv.dismantle("a"), 20)
        self.assertEqual(inv.materials["relic"], 20)

    def test_insufficient_funds_atomic(self):
        inv = EquipmentInventory()
        inv.receive(relic("a"))
        before = inv.to_dict()
        with self.assertRaises(ValueError):
            inv.enhance("a")
        self.assertEqual(before, inv.to_dict())

    def test_duplicates_limit(self):
        inv = EquipmentInventory()
        inv.receive(relic("a"))
        for i in range(10):
            inv.receive(relic(str(i)))
            inv.absorb_duplicate("a", str(i))
        self.assertEqual(inv.items["a"].duplicate_multiplier, 1.2)
        inv.receive(relic("last"))
        before = inv.to_dict()
        with self.assertRaises(ValueError):
            inv.absorb_duplicate("a", "last")
        self.assertEqual(before, inv.to_dict())

    def test_replace_no_upgrade_transfer(self):
        inv = EquipmentInventory(materials={"weapon": 0, "relic": 4})
        inv.receive(relic("old"))
        inv.enhance("old")
        inv.equip("old", 2)
        inv.receive(relic("new", rarity="U"))
        self.assertEqual(inv.replace_relic("old", "new"), 8)
        self.assertEqual(inv.relic_slots[2], "new")
        self.assertEqual(inv.items["new"].enhancement, 0)

    def test_death_and_prestige(self):
        inv = EquipmentInventory()
        inv.receive(EquipmentItem("w", "weapon", "剣", "C", 10))
        inv.equip("w")
        inv.receive(relic("r"))
        inv.equip("r")
        inv.storage_capacity["relic"] = 6
        inv.on_death()
        self.assertEqual(set(inv.items), {"r"})
        self.assertEqual(inv.materials["weapon"], .5)
        inv.validate()
        inv.on_prestige()
        self.assertEqual(inv.to_dict(), EquipmentInventory().to_dict())

    def test_serialization_roundtrip_and_isolation(self):
        inv = EquipmentInventory()
        inv.receive(relic("r"))
        inv.equip("r")
        payload = json.loads(json.dumps(inv.to_dict()))
        restored = EquipmentInventory.from_dict(payload)
        self.assertEqual(inv.to_dict(), restored.to_dict())
        restored.items["r"].affixes["xp"] = .03
        self.assertEqual(inv.items["r"].affixes, {})

    def test_invalid_save(self):
        inv = EquipmentInventory()
        inv.receive(relic("r"))
        payload = inv.to_dict()
        payload["items"]["r"]["quality"] = 1.25
        with self.assertRaises(ValueError):
            EquipmentInventory.from_dict(payload)
        payload = inv.to_dict()
        payload["items"]["r"]["base_atk"] = float("nan")
        with self.assertRaises(ValueError):
            EquipmentInventory.from_dict(payload)


if __name__ == "__main__":
    unittest.main()
