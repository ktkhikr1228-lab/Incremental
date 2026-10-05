import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import ts from 'typescript';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);
function load(file, hooks) {
  const module = { exports: {} };
  const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
  }}).outputText;
  const localRequire = id => id === 'react' && hooks ? hooks : id.startsWith('.')
    ? load(['.tsx', '.ts'].map(ext => path.resolve(path.dirname(file), id + ext)).find(fs.existsSync), hooks) : require(id);
  new Function('require', 'module', 'exports', code)(localRequire, module, module.exports);
  return module.exports;
}
const { ChoicePanels } = load(path.join(root, 'components/game-ui/choice-panels.tsx'));
function nodes(node) {
  if (Array.isArray(node)) return node.flatMap(nodes);
  if (!node || typeof node !== 'object') return [];
  return [node, ...nodes(node.props?.children)];
}
const card = { key: 'rapid_fire', name: 'Rapid Fire', description: 'AS +20%', rarity: 'C',
  tags: ['as'], eligible: true, immediateMultiplier: 1.2, nextTtk: 2 };
const state = { status: 'combat', nonBlocking: true, run: { cardCount: 4 }, permanent: {},
  options: [card, { ...card, key: 'eye' }, { ...card, key: 'illegal', eligible: false }], rerollsLeft: 1 };
test('candidate cards omit DPS/TTK diagnostics in both placements', () => {
  const { renderToStaticMarkup } = require('react-dom/server');
  for (const placement of ['edge', 'modal']) {
    const html = renderToStaticMarkup(ChoicePanels({ state, busy: false, placement, act() {} }));
    assert.ok(!html.includes('即時DPS'));
    assert.ok(!html.includes('次敵TTK'));
    assert.ok(!html.includes('<dl>'));
    assert.ok(html.includes('Rapid Fire'));
    assert.ok(html.includes('AS +20%'));
    assert.ok(html.includes('このカードを選ぶ'));
  }
});
test('all five rarities display full names in separate badges', () => {
  const { renderToStaticMarkup } = require('react-dom/server');
  for (const [rarity, name] of Object.entries({ C: 'Common', U: 'Uncommon', R: 'Rare', E: 'Epic', L: 'Legendary' })) {
    const html = renderToStaticMarkup(ChoicePanels({ state: { ...state, options: [{ ...card, rarity }] }, busy: false, placement: 'edge', act() {} }));
    assert.ok(html.includes(`class="card-rarity-badge">${name}</span>`));
    assert.ok(html.includes('class="card-options__tags">as</span>'));
  }
});
test('edge displays three candidates and preserves selection/reroll actions', () => {
  const calls = [];
  const tree = ChoicePanels({ state, busy: false, placement: 'edge', act: (...args) => calls.push(args) });
  assert.match(tree.props.className, /decision--cards-edge/);
  const cards = nodes(tree).filter(n => n.type === 'button' && n.props.className?.startsWith('rarity-'));
  assert.equal(cards.length, 3);
  assert.equal(cards[2].props.disabled, true);
  cards[0].props.onClick();
  nodes(tree).find(n => n.type === 'button' && n.props.className === 'text-action').props.onClick();
  assert.deepEqual(calls, [['select_card', { cardKey: 'rapid_fire' }], ['reroll']]);
});
test('compact result keeps DP and manual retry, hides all equipment/material actions', () => {
  const calls = [];
  const death = { ...state, status: 'death', death: { failureWave: 205, reached: 204, gainedDp: 33, runCombatSeconds: 531 } };
  const tree = ChoicePanels({ state: death, compactResult: true, busy: false,
    act: (...args) => calls.push(args), onOpenBag() {} });
  assert.match(tree.props.className, /decision--death-compact/);
  assert.ok(nodes(tree).some(n => n.type?.name === 'DPUpgrades'));
  assert.ok(!nodes(tree).some(n => n.props?.className === 'workshop-ledger'));
  assert.ok(!nodes(tree).some(n => n.type === 'button' && n.props.children === '鞄で装備を確認'));
  nodes(tree).find(n => n.props?.className?.includes('retry-action')).props.onClick();
  assert.deepEqual(calls, [['retry']]);
});
test('archive/default result and default card placement are unchanged', () => {
  const death = { ...state, status: 'death', death: { failureWave: 205, reached: 204, gainedDp: 33, runCombatSeconds: 531 } };
  const tree = ChoicePanels({ state: death, busy: false, act() {} });
  assert.ok(nodes(tree).some(n => n.props?.className === 'workshop-ledger'));
  assert.equal(ChoicePanels({ state, busy: false, act() {} }).props.className, 'decision decision--cards');
});
test('Main wires edge/compact options without automatic card draws or panel overlap', () => {
  const values = [], effects = [], calls = [];
  let index = 0;
  const hooks = { useState(initial) { const i = index++; values[i] ??= initial; return [values[i], v => { values[i] = v; }]; },
    useRef(current) { return { current }; }, useEffect(callback) { effects.push(callback); } };
  const { FigmaMain } = load(path.join(root, 'components/game-ui/figma-main.tsx'), hooks);
  const s = { ...state, cardDrafts: 2, run: { ...state.run, cards: [] } };
  function render() {
    index = 0; effects.length = 0;
    const tree = FigmaMain({ state: s, busy: false, elapsed: 0, progress: 0, paused: true,
      onPause() {}, start() {}, act: (...args) => calls.push(args) });
    effects.forEach(callback => callback());
    return nodes(tree).find(n => n.type?.name === 'ChoicePanels');
  }
  assert.equal(render(), undefined); assert.deepEqual(calls, []);
  values[5] = true;
  const edge = render(); assert.equal(edge.props.placement, 'edge'); assert.equal(edge.props.compactResult, true);
  values[2] = 'settings'; assert.equal(render(), undefined);
  values[2] = 'none'; s.options = []; render();
  assert.deepEqual(calls, [['open_cards']]);
});
