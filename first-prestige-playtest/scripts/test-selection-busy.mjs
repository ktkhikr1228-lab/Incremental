import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import ts from 'typescript';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);
function load(file, hooks, fetch) {
  const module = { exports: {} };
  const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
  }}).outputText;
  function localRequire(id) {
    if (id.endsWith('.css')) return {};
    if (id === 'react') return hooks;
    if (id.startsWith('.') || id.startsWith('@/')) {
      const base = id.startsWith('@/') ? path.join(root, id.slice(2)) : path.resolve(path.dirname(file), id);
      return load(['.tsx', '.ts'].map(ext => base + ext).find(fs.existsSync), hooks, fetch);
    }
    return require(id);
  }
  new Function('require', 'module', 'exports', 'fetch', code)(localRequire, module, module.exports, fetch);
  return module.exports;
}
function find(node, name) {
  if (Array.isArray(node)) return node.map(n => find(n, name)).find(Boolean);
  if (!node || typeof node !== 'object') return;
  if (node.type?.name === name) return node;
  return find(node.props?.children, name);
}
function fixture() {
  const values = [], responses = [], busyChanges = [];
  const hooks = {
    useState(initial) { const i = values.length; values.push(initial); return [initial, v => { values[i] = v; if (i === 4) busyChanges.push(v); }]; },
    useRef(current) { return { current }; }, useEffect() {}, useCallback(fn) { return fn; },
  };
  const fetch = () => new Promise(resolve => responses.push(resolve));
  const { default: Home } = load(path.join(root, 'app/page.tsx'), hooks, fetch);
  const act = find(Home(), 'FigmaMain').props.act;
  return { act, values, busyChanges, finish(ok = true) {
    assert.ok(responses.length, 'request must have started');
    responses.shift()({ ok, json: async () => ok ? { status: 'combat', nonBlocking: true } : { error: 'rejected' } });
  }};
}
test('combat resolve and autosave never disable selection controls', async () => {
  for (const type of ['resolve', 'save_progress']) {
    const f = fixture(); const pending = f.act(type);
    assert.equal(typeof pending.then, 'function', 'Main must preserve action result promise');
    await Promise.resolve(); f.finish(); assert.equal(await pending, true);
    assert.deepEqual(f.busyChanges, []);
  }
});
test('selection remains guarded while foreground request is in flight', async () => {
  const f = fixture(); const pending = f.act('select_card', { cardKey: 'rapid_fire' });
  assert.equal(f.values[4], true);
  await Promise.resolve(); f.finish(); assert.equal(await pending, true);
  assert.deepEqual(f.busyChanges, [true, false]);
});
test('background completion cannot unlock queued foreground selection', async () => {
  const f = fixture(); const background = f.act('resolve');
  const foreground = f.act('select_card', { cardKey: 'rapid_fire' });
  await Promise.resolve(); f.finish(); await background;
  assert.equal(f.values[4], true);
  await Promise.resolve(); f.finish(); await foreground;
  assert.deepEqual(f.busyChanges, [true, false]);
});
test('foreground error returns false and releases busy without corrupting queue', async () => {
  const f = fixture(); const failed = f.act('gear_receive', { uid: 'fixture', equip: true });
  await Promise.resolve(); f.finish(false); assert.equal(await failed, false);
  assert.equal(f.values[4], false); assert.equal(f.values[5], true);
  const next = f.act('save_progress'); await Promise.resolve(); f.finish();
  assert.equal(await next, true); assert.deepEqual(f.busyChanges, [true, false]);
});
test('busy legal cards are not styled as ineligible cards', () => {
  const { ChoicePanels } = load(path.join(root, 'components/game-ui/choice-panels.tsx'));
  const card = { key: 'rapid_fire', name: 'Rapid Fire', rarity: 'C', tags: ['as'],
    description: 'AS +20%', eligible: true, immediateMultiplier: 1.2, nextTtk: 1 };
  const tree = ChoicePanels({ state: { status: 'combat', nonBlocking: true,
    run: { cardCount: 1 }, permanent: {}, options: [card, { ...card, key: 'illegal', eligible: false }] }, busy: true, act() {} });
  function collect(node) {
    if (Array.isArray(node)) return node.flatMap(collect);
    if (!node || typeof node !== 'object') return [];
    return [...(node.type === 'button' && node.props.className?.startsWith('rarity-') ? [node] : []), ...collect(node.props?.children)];
  }
  const cards = collect(tree);
  assert.equal(cards[0].props.disabled, true); assert.equal(cards[0].props['data-ineligible'], undefined);
  assert.equal(cards[1].props.disabled, true); assert.equal(cards[1].props['data-ineligible'], true);
});
