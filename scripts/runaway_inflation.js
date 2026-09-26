/*
 * Runaway inflation experiment adapter.
 *
 * This file intentionally has no UI or framework dependency.  Wire its
 * `tick` method into the existing game loop and call `render` from the UI
 * layer.  Install break_eternity.js in the host app before importing this
 * module:
 *
 *   npm i break_eternity.js
 */
// break_eternity.js v2 exposes Decimal as its default ESM export.
import Decimal from "break_eternity.js";

const D = (value) => Decimal.fromValue(value);
const ZERO = D(0);
const ONE = D(1);
const TEN = D(10);

export const RUNAWAY_CONFIG = Object.freeze({
  infinityCost: D("1e308"),
  metaLoopsPerSecond: 25_000,
  uiUpdatesPerSecond: 10,
  dimensionCount: 8,
});

const clampPositive = (value) => D(value).max(ONE);

function productOfOtherDimensions(dimensions, excludedIndex) {
  let product = ONE;
  for (let index = 0; index < dimensions.length; index += 1) {
    if (index !== excludedIndex) product = product.mul(clampPositive(dimensions[index]));
  }
  return product;
}

// Exponentiation is deliberately aggressive: every simulation second squares
// the exponent and then cubes it.  Decimal.pow keeps the value out of JS
// Number/Infinity space.
function runawayAttackPower(state) {
  const exponent = D(state.attackExponent);
  const nextExponent = exponent.pow(2).pow(3);
  state.attackExponent = nextExponent;
  state.attackPower = D(state.attackBase).pow(nextExponent);
  return state.attackPower;
}

function runMetaLoop(state, iterations) {
  for (let index = 0; index < iterations; index += 1) {
    state.eternity = state.eternity.add(ONE);
    state.reality = state.reality.add(ONE);
    // Meta currencies feed back into all dimensions on every loop.
    state.metaPower = state.metaPower.mul("1.01").add(ONE);
    for (let dimension = 0; dimension < state.dimensions.length; dimension += 1) {
      const crossProduct = productOfOtherDimensions(state.dimensions, dimension);
      state.dimensions[dimension] = state.dimensions[dimension]
        .add(crossProduct.mul(state.metaPower));
    }
  }
}

function formatArrow(value) {
  const decimal = D(value);
  if (decimal.layer >= 2) return `↑${decimal.layer} ${decimal.mag.toFixed(2)}`;
  return `↑${decimal.mag.toFixed(2)}`;
}

// Compact display intentionally supports e1.00e15 / ee308-like output while
// switching to arrows once break_eternity enters higher layers.
export function formatRunaway(value) {
  const decimal = D(value);
  if (!decimal.isFinite()) return "↑∞";
  if (decimal.layer >= 2) return formatArrow(decimal);
  if (decimal.layer === 1) return `ee${decimal.mag.toFixed(0)}`;
  if (decimal.gte("1e6")) {
    const logarithm = decimal.log10();
    const exponent = logarithm.floor();
    const mantissa = TEN.pow(logarithm.sub(exponent));
    return `e${mantissa.toFixed(2)}e${exponent.toFixed(0)}`;
  }
  return decimal.toStringWithDecimalPlaces(2);
}

export class RunawayInflation {
  constructor(options = {}) {
    this.config = { ...RUNAWAY_CONFIG, ...options };
    this.state = {
      infinity: ZERO,
      eternity: ZERO,
      reality: ZERO,
      attackBase: D(options.attackBase ?? 2),
      attackExponent: ONE,
      attackPower: D(options.attackBase ?? 2),
      metaPower: ONE,
      dimensions: Array.from(
        { length: options.dimensionCount ?? RUNAWAY_CONFIG.dimensionCount },
        () => ONE,
      ),
      elapsedSeconds: 0,
      attackAccumulator: 0,
      dirty: true,
    };
    this.lastUiUpdate = 0;
  }

  tick(deltaSeconds, render = undefined) {
    const delta = Math.max(0, Number(deltaSeconds));
    const infinityReached = D(this.state.infinity).gte(this.config.infinityCost);
    if (infinityReached) {
      // Batch the requested "tens of thousands per second" loop so the host
      // loop does not allocate one task/callback per prestige.
      runMetaLoop(this.state, Math.floor(delta * this.config.metaLoopsPerSecond));
      this.state.attackAccumulator += delta;
      while (this.state.attackAccumulator >= 1) {
        this.state.attackAccumulator -= 1;
        runawayAttackPower(this.state);
      }
      this.state.dirty = true;
    }
    this.state.elapsedSeconds += delta;

    const uiInterval = 1 / this.config.uiUpdatesPerSecond;
    if (render && this.state.dirty && this.state.elapsedSeconds - this.lastUiUpdate >= uiInterval) {
      this.lastUiUpdate = this.state.elapsedSeconds;
      this.state.dirty = false;
      render(this.snapshot());
    }
  }

  snapshot() {
    return {
      ...this.state,
      attackBase: D(this.state.attackBase),
      attackExponent: D(this.state.attackExponent),
      attackPower: D(this.state.attackPower),
      metaPower: D(this.state.metaPower),
      dimensions: this.state.dimensions.map((value) => D(value)),
    };
  }

  displaySnapshot() {
    const snapshot = this.snapshot();
    return {
      infinity: formatRunaway(snapshot.infinity),
      eternity: formatRunaway(snapshot.eternity),
      reality: formatRunaway(snapshot.reality),
      attackPower: formatRunaway(snapshot.attackPower),
      attackExponent: formatRunaway(snapshot.attackExponent),
      dimensions: snapshot.dimensions.map(formatRunaway),
    };
  }
}

export function triggerInfinity(state, amount = RUNAWAY_CONFIG.infinityCost) {
  state.infinity = D(state.infinity).add(amount);
}
