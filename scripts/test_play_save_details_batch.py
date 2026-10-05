"""Small deterministic regressions for manual-play UX; no balance trials."""
import copy
import json
import math
from pathlib import Path
import sys
import tempfile
import threading
import subprocess
import urllib.request
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'first-prestige-playtest'))
from equipment_session import EquipmentSession
from session_store import load, save, encode, decode
import new_w5000_rules as rules
from w5000_equipment_v01 import EquipmentItem


class SaveDetailsBatchTests(unittest.TestCase):
    def session(self):
        return EquipmentSession('balanced', 20260828)

    def roundtrip(self, session):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'save.json'
            before = session.rng.getstate()
            save(session, path)
            self.assertEqual(before, session.rng.getstate())
            restored = load(path)
            self.assertEqual(before, restored.rng.getstate())
            self.assertEqual(session.state(), restored.state())
            self.assertIs(restored.permanent._new_dp_state, restored.dp_state)
            return restored

    def test_mid_fight_hand_equipment_rng_continue(self):
        s = self.session()
        s.pending_cards.extend([(None, None)] * 3)
        s.pending_equipment.append(EquipmentItem('pending', 'weapon', '剣', 'C', 10, base_atk=1))
        s._store_waiting_weapons()
        s.action(dict(type='open_cards', elapsed=.1))
        restored = self.roundtrip(s)
        key = next(c.key for c in s.card_hand if s._card_payload(c)['eligible'])
        for instance in (s, restored):
            instance.action(dict(type='select_card', cardKey=key, elapsed=.2))
        self.assertEqual(s.state(), restored.state())
        self.assertEqual(s.rng.getstate(), restored.rng.getstate())

    def test_old_waiting_weapon_save_migrates_to_pouch_without_rng_or_equip(self):
        s = self.session()
        item = EquipmentItem('old-pending', 'weapon', '剣', 'C', 10, base_atk=1)
        s.pending_equipment.append(item)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'save.json'
            save(s, path)
            restored = load(path)
        self.assertEqual(restored.pending_equipment, [])
        self.assertEqual(restored.inventory.items[item.uid], item)
        self.assertIsNone(restored.inventory.weapon_slot)
        self.assertEqual(restored.rng.getstate(), s.rng.getstate())
        self.assertEqual(restored.run, s.run)

    def test_death_and_complete_roundtrip(self):
        s = self.session()
        s.fight['timeToKill'] = None
        s.action(dict(type='resolve'))
        restored = self.roundtrip(s)
        for instance in (s, restored):
            instance.action(dict(type='retry'))
        self.assertEqual(s.state(), restored.state())
        s.mode = 'complete'
        self.roundtrip(s)

    def test_bad_save_preserved_and_no_type_import(self):
        for value in (float('inf'), float('-inf'), float('nan')):
            encoded = json.loads(json.dumps(encode(value), allow_nan=False))
            restored = decode(encoded, {})
            self.assertTrue(math.isnan(restored) if math.isnan(value) else restored == value)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'save.json'
            for text in ('{bad json', json.dumps({'version': 999}),
                         json.dumps({'version': 1, 'profile': 'new_w5000_candidate',
                                     'state': {'t': 'data', 'c': 'os:system', 'v': None}})):
                path.write_text(text, encoding='utf-8')
                with self.assertRaises((ValueError, KeyError, TypeError)):
                    load(path)
                self.assertEqual(text, path.read_text(encoding='utf-8'))

    def test_save_progress_retains_rng_and_damage(self):
        s = self.session()
        before = s.rng.getstate()
        s.action(dict(type='save_progress', elapsed=.2))
        self.assertEqual(s.encounter_start, .2)
        self.assertEqual(s.rng.getstate(), before)
        self.roundtrip(s)

    def test_damage_rows_sum_and_read_is_pure(self):
        s = self.session()
        for key in ('power_up', 'rapid_fire', 'follow_up_strike', 'multi_hit', 're_action', 'execution', 'time_collapse'):
            rules.acquire(s.run, rules.BY_KEY[key])
        before = copy.deepcopy(s.__dict__)
        details = s.state()['damageDetails']
        self.assertAlmostEqual(sum(r['power'] for r in details['rows']), details['totalPower'])
        self.assertEqual(before['rng'].getstate(), s.rng.getstate())
        self.assertEqual(before['run'], s.run)
        self.assertEqual(before['dp_state'], s.dp_state)

    def test_batch_matches_sequential_and_stops_at_rare(self):
        s = self.session()
        s.pending_cards.extend([('C', None)] * 2 + [('R', None)])
        # Ordinary C/U hands only; the next forced Rare reward must stay manual.
        s._ensure_hand()
        s.card_forced_rarity = None
        control = copy.deepcopy(s)
        control.action(dict(type='select_card', cardKey=max((control._card_payload(c) for c in control.card_hand), key=lambda c: c['score'])['key']))
        # The second forced reward stays untouched, even though Common.
        s.action(dict(type='take_common_batch'))
        self.assertEqual(s.state(), control.state())
        self.assertEqual(s.rng.getstate(), control.rng.getstate())
        s.card_hand = [rules.BY_KEY['multi_hit']]
        s.card_forced_rarity = None
        before = s.run.card_count
        s.action(dict(type='take_common_batch'))
        self.assertEqual(s.run.card_count, before)

    def test_batch_is_bounded_and_does_not_retry_death(self):
        s = self.session()
        s.pending_cards.extend([(None, None)] * 25)
        hand = [rules.BY_KEY[k] for k in ('power_up', 'rapid_fire', 'experience')]
        with patch.object(rules, 'draw_hand', side_effect=lambda *args, **kwargs: list(hand)):
            s.action(dict(type='take_common_batch'))
        self.assertEqual(s.run.card_count, 20)
        self.assertEqual(s.state()['cardDrafts'], 5)
        s.mode = 'death'
        s.action(dict(type='take_common_batch'))
        self.assertEqual(s.mode, 'death')
        self.assertEqual(s.attempt, 1)

    def test_save_failure_is_visible_and_keeps_session(self):
        import sim_server
        s = self.session()
        with patch.object(sim_server, 'SESSION', s), patch('session_store.save', side_effect=OSError('disk full')):
            sim_server.persist_session()
            self.assertIn('disk full', sim_server.SAVE_ERROR)
            self.assertIs(sim_server.SESSION, s)
        sim_server.SAVE_ERROR = None

    def test_http_save_and_fresh_process_restore(self):
        import sim_server
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'save.json'
            with patch.object(sim_server, 'SESSION', None), patch.object(sim_server, 'SAVE_PATH', path), patch.object(sim_server, 'SAVE_ERROR', None):
                server = sim_server.ThreadingHTTPServer(('127.0.0.1', 0), sim_server.Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    def post(route, payload):
                        request = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/{route}',
                            data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
                        with urllib.request.urlopen(request, timeout=5) as response:
                            return json.load(response)
                    post('start', dict(profile='balanced', seed=20260828, equipmentMode=True))
                    state = post('action', dict(type='save_progress', elapsed=.2))
                    self.assertTrue(state['saveAvailable'])
                    self.assertIsNone(state['saveError'])
                    script = "import sys; sys.path.insert(0, sys.argv[1]); from session_store import load; s=load(sys.argv[2]); print(s.state()['fight']['elapsed'])"
                    result = subprocess.run([sys.executable, '-c', script,
                        str(Path(__file__).resolve().parents[1] / 'first-prestige-playtest'), str(path)],
                        capture_output=True, text=True, timeout=20)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(float(result.stdout.strip()), .2)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
