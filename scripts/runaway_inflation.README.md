# 暴走インフレーション実験アダプター

このワークスペースには元のIncrementalゲーム本体がないため、`scripts/runaway_inflation.js` は既存ゲームへ接続するための独立ランタイムとして追加しています。

```js
import { RunawayInflation, triggerInfinity } from "./runaway_inflation.js";

const runaway = new RunawayInflation();
triggerInfinity(runaway.state); // Infinity到達を実験開始

// 既存ゲームのrequestAnimationFrame / tickerから呼ぶ
runaway.tick(deltaSeconds, (view) => updateOnlyInflationPanel(view));
```

実装済みの実験挙動:

- Infinityコスト到達後、メタ通貨を毎秒25,000ループでバッチ処理。
- 1秒ごとに攻撃指数を `((exponent^2)^3)` へ更新し、`break_eternity.js` のDecimalで攻撃力を再計算。
- 各ディメンションを「自分以外の全ディメンションの積 × メタパワー」で増加。
- UI更新は毎秒10回まで。数値計算は描画から切り離して継続。
- `e...` と矢印表記を使うフォーマッターを提供。

ホスト側で以下を追加してから利用してください。

```powershell
npm install break_eternity.js
```
