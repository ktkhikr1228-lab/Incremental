// Real component/CSS layout fixtures only; no game API, save, RNG or actions.
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const prefix = process.argv[2] ?? 'compact';
const require = createRequire(import.meta.url);
function load(file) {
  const module = { exports: {} };
  const compiled = ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
  }}).outputText;
  const localRequire = id => id.startsWith('.')
    ? load(['.tsx', '.ts'].map(ext => path.resolve(path.dirname(file), id + ext)).find(fs.existsSync)) : require(id);
  new Function('require', 'module', 'exports', compiled)(localRequire, module, module.exports);
  return module.exports;
}
const { FigmaMain } = load(path.join(root, 'components/game-ui/figma-main.tsx'));
const { ChoicePanels } = load(path.join(root, 'components/game-ui/choice-panels.tsx'));
const state = { status: 'combat', nonBlocking: true, targetWave: 5000, cardBatchSupported: true,
  cardDrafts: 6, rerollsLeft: 1, recommendedCard: 'rapid_fire', equipmentMode: true,
  run: { cardCount: 9, cards: [
    { key: 'rapid_fire', name: 'Rapid Fire', rarity: 'C', count: 1, description: 'AS +20%' },
    { key: 'quick_learner', name: 'Quick Learner', rarity: 'U', count: 1, description: '条件XP +30%' },
    { key: 'critical_conversion', name: 'Critical Conversion', rarity: 'R', count: 1, description: 'CritからAll Damage' },
  ], kills: 46, xp: 92.5, nextCardCost: 170 },
  fight: { wave: 46, timeLimit: 10, enemyHp: '61.04', dps: '31.84', critChance: .34 },
  player: { baseAttack: 7.21, attackSpeed: 3.3, critChance: .34, critMultiplier: 2, hitCount: 1, followRate: 0 },
  permanent: { maxWave: 217, bankedDp: 40, dpVersion: 'v0.1 BC candidate', levels: { total: 30 },
    dpUpgrades: ['Base ATK', 'Attack Speed', 'XP Gain', 'Crit Rate', 'Crit Multiplier', 'Weapon ATK', 'Luck', 'Weapon Find', 'Weapon Quality'].map((label, i) => ({ key: label, label, level: 6, cost: 14, effect: '+28% / Lv', unlocked: i < 4, unlockWave: [0, 0, 0, 100, 250, 500, 750, 1000, 1500][i] })),
    rerollUpgrade: { unlocked: false, bought: false, cost: 90 } },
  options: [
    ['experience', 'Experience', 'XP +20%', ['xp'], 1, 2.17, 'C'],
    ['overclock', 'Overclock', 'AS +25% / Weapon ATK +10%', ['as'], 1.096, 1.95, 'U'],
    ['multi_hit', 'Multi-Hit', 'Hit Count +0.20', ['hit'], 1.129, 1.9, 'R'],
  ].map(([key, name, description, tags, immediateMultiplier, nextTtk, rarity]) => ({ key, name, description, tags, immediateMultiplier, nextTtk, rarity, eligible: true })),
};
const css = ['globals.css', 'figma-main.css'].map(file => fs.readFileSync(path.join(root, 'app', file), 'utf8').replace(/^@import[^;]+;\s*/gm, '')).join('\n');
function html(death) {
  const s = death ? { ...state, status: 'death', death: { failureWave: 205, reached: 204, gainedDp: 33, runCombatSeconds: 531 } } : state;
  const main = renderToStaticMarkup(React.createElement(FigmaMain, { state: s, elapsed: 1.2, progress: 12, busy: false, paused: true, onPause() {}, act() {}, start() {} }));
  const cards = death ? '' : renderToStaticMarkup(React.createElement(ChoicePanels, { state: s, busy: false, placement: 'edge', act() {}, onClose() {}, onOpenBag() {} }));
  const markup = death ? main : main.slice(0, -6) + cards + '</div>';
  return `<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>UI検証（API接続なし）</title><style>html{line-height:1.5}button{font:inherit}</style><style>${css}</style><body><main class="figma-page">${markup}</main><script>const c=document.querySelector('.fm-container'),s=document.querySelector('.fm-screen');new ResizeObserver(()=>s.style.zoom=Math.max(.01,Math.min(1,c.clientWidth/1440,c.clientHeight/900))).observe(c);</script></body></html>`;
}
for (const death of [false, true]) fs.writeFileSync(path.join(root, '..', 'output', `${prefix}_${death ? 'result' : 'cards'}_fixture_20261005.html`), html(death));
http.createServer((request, response) => {
  if (request.url.startsWith('/figma-main/')) {
    const file = path.resolve(root, 'public', '.' + request.url);
    const allowed = path.resolve(root, 'public', 'figma-main') + path.sep;
    if (!file.startsWith(allowed) || !fs.existsSync(file)) { response.writeHead(404); response.end(); return; }
    response.writeHead(200, { 'Content-Type': file.endsWith('.svg') ? 'image/svg+xml' : 'image/png' });
    response.end(fs.readFileSync(file)); return;
  }
  response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  response.end(html(request.url.includes('death')));
}).listen(4174, '127.0.0.1', () => console.log('Layout-only preview http://localhost:4174/ or /?death'));
