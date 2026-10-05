// Layout-only fixture: render the real component without contacting the game API.
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);
const cache = new Map();
function load(file) {
  if (cache.has(file)) return cache.get(file);
  const source = fs.readFileSync(file, 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
    target: ts.ScriptTarget.ES2022,
  }}).outputText;
  const module = { exports: {} };
  cache.set(file, module.exports);
  const localRequire = id => id.startsWith('.')
    ? load(['.tsx', '.ts'].map(ext => path.resolve(path.dirname(file), id + ext)).find(fs.existsSync))
    : require(id);
  new Function('require', 'module', 'exports', compiled)(localRequire, module, module.exports);
  return module.exports;
}
const { ChoicePanels } = load(path.join(root, 'components/game-ui/choice-panels.tsx'));
const state = {
  status: 'combat', nonBlocking: true, cardBatchSupported: true, cardDrafts: 6,
  rerollsLeft: 1, recommendedCard: 'rapid_fire',
  run: { cardCount: 9 }, permanent: {},
  options: [
    ['experience', 'Experience', 'XP +20%', ['xp'], 1, 7.37],
    ['salvager', 'Salvager', '武器分解Pt +15%', ['dormant'], 1, 7.37],
    ['rapid_fire', 'Rapid Fire', 'Attack Speed +20%', ['as'], 1.129, 6.53],
  ].map(([key, name, description, tags, immediateMultiplier, nextTtk]) => ({
    key, name, description, tags, immediateMultiplier, nextTtk, rarity: 'C', eligible: true,
  })),
};
const css = ['globals.css', 'figma-main.css'].map(file =>
  fs.readFileSync(path.join(root, 'app', file), 'utf8').replace(/^@import[^;]+;\s*/gm, '')
).join('\n');
const html = `<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>カード選択レイアウト検証（進行操作なし）</title><style>html{line-height:1.5}button{font:inherit}</style><style>${css}</style><body><main class="figma-page">${renderToStaticMarkup(React.createElement(ChoicePanels, { state, busy: false, act: () => {}, onClose: () => {}, onOpenBag: () => {} }))}</main></body></html>`;
const output = path.join(root, '..', 'output', 'card_choice_layout_fixture_20261004.html');
fs.writeFileSync(output, html);
const server = http.createServer((_request, response) => {
  response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  response.end(html);
});
server.listen(4174, '127.0.0.1', () => console.log(`Layout fixture: http://localhost:4174/\n${output}`));
