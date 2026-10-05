import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import ts from 'typescript';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);
function load(file, reactOverride) {
  const module = { exports: {} };
  const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
  }}).outputText;
  const localRequire = id => id === 'react' && reactOverride ? reactOverride : id.startsWith('.')
    ? load(['.tsx', '.ts'].map(ext => path.resolve(path.dirname(file), id + ext)).find(fs.existsSync), reactOverride)
    : require(id);
  new Function('require', 'module', 'exports', code)(localRequire, module, module.exports);
  return module.exports;
}
const { EquipmentList } = load(path.join(root, 'components/game-ui/equipment-list.tsx'));
const item = { uid: 'weapon-test', kind: 'weapon', rarity: 'C', name: '剣',
  origin_wave: 10, base_atk: 1, quality: 1, enhancement: 0, duplicate_levels: 0, affixes: {} };
function buttons(node) {
  if (!node || typeof node !== 'object') return [];
  if (Array.isArray(node)) return node.flatMap(buttons);
  return [...(node.type === 'button' ? [node] : []), ...buttons(node.props?.children)];
}
function fixture(act, { drop = true, busy = false, worn = false } = {}) {
  let returned = 0;
  let closed = 0;
  const tree = EquipmentList({
    state: { status: 'combat', pendingEquipmentList: drop ? [item] : [],
      equipment: { items: drop ? {} : { [item.uid]: item }, weapon_slot: worn ? item.uid : null, relic_slots: [] } },
    busy, act, close: () => closed++, onEquipped: () => returned++,
  });
  return { equip: buttons(tree).find(b => b.props.children === '装備'),
    store: buttons(tree).find(b => b.props.children === '保管'), counts: () => ({ returned, closed }) };
}
test('pending weapon returns only after successful response', async () => {
  let finish;
  const calls = [];
  const f = fixture((...args) => { calls.push(args); return new Promise(resolve => { finish = resolve; }); });
  const click = f.equip.props.onClick();
  assert.equal(f.counts().returned, 0);
  finish(true); await click;
  assert.deepEqual(calls, [['gear_receive', { uid: item.uid, equip: true }]]);
  assert.deepEqual(f.counts(), { returned: 1, closed: 0 });
});
test('stored weapon success returns to main', async () => {
  const calls = [];
  const f = fixture(async (...args) => { calls.push(args); return true; }, { drop: false });
  await f.equip.props.onClick();
  assert.equal(calls[0][0], 'gear_equip'); assert.equal(f.counts().returned, 1);
});
test('failure, rejection and unconfirmed void result keep list open', async () => {
  for (const act of [async () => false, async () => { throw new Error('capacity'); }, () => {}]) {
    const f = fixture(act); await f.equip.props.onClick();
    assert.deepEqual(f.counts(), { returned: 0, closed: 0 });
  }
});
test('storage does not return; busy and worn equip stay disabled', async () => {
  const f = fixture(async () => true); await f.store.props.onClick();
  assert.equal(f.counts().returned, 0);
  assert.equal(fixture(async () => true, { busy: true }).equip.props.disabled, true);
  assert.equal(fixture(async () => true, { drop: false, worn: true }).equip.props.disabled, true);
});
test('Main uses pouch for stored/overflow weapons and returns after equip success', async () => {
  const values = [], refs = [], effects = [];
  let stateIndex = 0, refIndex = 0;
  const hooks = {
    useState(initial) { const i = stateIndex++; if (!(i in values)) values[i] = initial; return [values[i], v => { values[i] = v; }]; },
    useRef(initial) { const i = refIndex++; return refs[i] ??= { current: initial }; },
    useEffect(callback) { effects.push(callback); },
  };
  const { FigmaMain } = load(path.join(root, 'components/game-ui/figma-main.tsx'), hooks);
  const calls = [];
  let accepted = true, rejected = false;
  const state = { status: 'combat', run: { cards: [] }, pendingEquipmentList: [item],
    equipment: { items: {}, weapon_slot: null, relic_slots: [null, null, null],
      storage_capacity: { weapon: 5, relic: 5 }, materials: { weapon: 0, relic: 0 } } };
  function render() {
    stateIndex = 0; refIndex = 0; effects.length = 0;
    const tree = FigmaMain({ state, elapsed: 0, progress: 0, busy: false, paused: true, onPause() {},
      act: async (...args) => { calls.push(args); if (rejected) throw new Error('full'); return accepted; }, start() {} });
    effects.forEach(callback => callback()); return tree;
  }
  function find(node, name) {
    if (Array.isArray(node)) return node.map(n => find(n, name)).find(Boolean);
    if (!node || typeof node !== 'object') return;
    if (node.type?.name === name) return node;
    return find(node.props?.children, name);
  }
  assert.equal(find(render(), 'EquipmentList'), undefined);
  assert.equal(values[0], false, 'drop must not automatically open a panel');
  buttons(render()).find(b => b.props['aria-label']?.startsWith('武器ポーチ')).props.onClick();
  assert.equal(values[0], true);
  assert.ok(buttons(render()).some(b => b.props.draggable && b.props.title?.startsWith('剣 C')));
  values[3] = item.uid;
  await buttons(render()).find(b => b.props.children === '装備').props.onClick();
  assert.deepEqual(calls, [['gear_receive', { uid: item.uid, slot: 0, equip: true }]]);
  assert.equal(values[0], false); assert.equal(values[3], null);
  state.pendingEquipmentList = []; state.equipment.items[item.uid] = item;
  values[0] = true; values[3] = item.uid;
  await buttons(render()).find(b => b.props.children === '装備').props.onClick();
  assert.equal(calls[1][0], 'gear_equip'); assert.equal(values[0], false);
  for (const reject of [false, true]) {
    accepted = false; rejected = reject;
    values[0] = true; values[3] = item.uid;
    await buttons(render()).find(b => b.props.children === '装備').props.onClick();
    assert.equal(values[0], true); assert.equal(values[3], item.uid);
  }
});

test('acquired weapons appear immediately beside prestige and open their own pouch detail without game actions', () => {
  const values = [];
  let index = 0;
  const hooks = {
    useState(initial) { const i = index++; if (!(i in values)) values[i] = initial; return [values[i], v => { values[i] = v; }]; },
    useRef(initial) { return { current: initial }; }, useEffect() {},
  };
  const { FigmaMain } = load(path.join(root, 'components/game-ui/figma-main.tsx'), hooks);
  const stored = { ...item, uid: 'stored-weapon', name: '大剣', rarity: 'R' };
  const overflow = { ...item, uid: 'overflow-weapon', name: '弓', rarity: 'U' };
  const worn = { ...item, uid: 'worn-weapon' };
  const relic = { ...item, uid: 'relic', kind: 'relic' };
  const state = { status: 'combat', run: { cards: [] }, pendingEquipmentList: [overflow, relic],
    equipment: { items: { [stored.uid]: stored, [worn.uid]: worn }, weapon_slot: worn.uid,
      relic_slots: [null, null, null], storage_capacity: { weapon: 5, relic: 5 }, materials: { weapon: 0, relic: 0 } } };
  const calls = [];
  function render() {
    index = 0;
    return FigmaMain({ state, elapsed: 0, progress: 0, busy: false, paused: true,
      onPause() {}, act(...args) { calls.push(args); }, start() {} });
  }
  function nodes(node) {
    if (Array.isArray(node)) return node.flatMap(nodes);
    if (!node || typeof node !== 'object') return [];
    return [node, ...nodes(node.props?.children)];
  }
  const footer = nodes(render()).find(n => n.type === 'footer');
  const children = footer.props.children;
  const pouchIndex = children.findIndex(n => n?.props?.['aria-label'] === '入手した武器');
  assert.ok(pouchIndex > 0);
  assert.equal(children[pouchIndex - 1].props.children[1].props.children, '転生');
  const tiles = buttons(children[pouchIndex]);
  assert.equal(tiles.length, 2, 'stored and pending weapons only; omit equipped weapon and relic');
  assert.equal(tiles[0].key, stored.uid);
  assert.match(tiles[0].props['aria-label'], /大剣 Rare/);
  assert.equal(values[0], false, 'acquisition must not automatically open a panel');
  for (const tile of tiles) {
    tile.props.onClick();
    assert.equal(values[0], true);
    assert.equal(values[3], tile.key);
    assert.ok(nodes(render()).some(n => n.props?.['aria-label'] === '装備詳細'));
  }
  assert.deepEqual(calls, [], 'opening a weapon must not equip, draw, or change game state');
  state.equipment.items = {}; state.equipment.weapon_slot = null; state.pendingEquipmentList = [];
  values[0] = false; values[3] = null;
  assert.equal(buttons(nodes(render()).find(n => n.props?.['aria-label'] === '入手した武器')).length, 0);
});
