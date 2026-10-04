import type { Fight, Permanent, RunView } from './types';
import { formatNumber } from './types';

type Props = {
  fight: Fight;
  run: RunView;
  permanent: Permanent;
  elapsed: number;
  duration: number;
  progress: number;
  speed: number;
  paused: boolean;
  busy: boolean;
  onSpeed: (value: number) => void;
  onPause: () => void;
  onResolve: () => void;
};

export function LastAscentStage({ fight, run, permanent, elapsed, duration, progress, speed, paused, busy, onSpeed, onPause, onResolve }: Props) {
  const remaining = Math.max(0, duration - elapsed);
  const hpWidth = fight.willWin ? Math.max(0, 100 - progress) : Math.max(13, 100 - progress * .72);
  const wave = String(fight.wave).padStart(3, '0');

  return <section className="ascent-combat" aria-label={`Wave ${fight.wave} 戦闘中`}>
    <div className="ascent-wave" aria-label={`現在Wave ${fight.wave}`}>
      <span>WAVE</span>
      <strong>{wave}</strong>
    </div>

    <div className="ascent-clock">
      <small>残り時間</small>
      <strong>{remaining.toFixed(1)}<em>s</em></strong>
    </div>

    <div className="ascent-enemy-copy">
      <h2>{fight.boss ? '虚蝕の主核' : '虚無の観測者'}</h2>
      <p>{fight.boss ? 'SOVEREIGN OF THE NULL' : 'OBSERVER OF THE NULL'}</p>
      <div className="ascent-hp-numbers"><span>{fight.enemyHp}</span><b>/</b><span>10^{fight.hpPower.toFixed(2)}</span></div>
      <div className="ascent-hp-track"><i style={{ width: `${hpWidth}%` }} /></div>
    </div>

    <div className="ascent-damage">
      <span>現在DPS</span>
      <strong>{fight.dps}</strong>
      <small>総ダメージ / 秒</small>
    </div>

    <dl className="ascent-breakdown">
      <div><dt>攻撃速度</dt><dd>{fight.attackSpeed.toFixed(2)} / 秒</dd></div>
      <div><dt>クリティカル</dt><dd>{(fight.critChance * 100).toFixed(1)}%</dd></div>
      <div><dt>Crit倍率</dt><dd>×{fight.critMultiplier.toFixed(2)}</dd></div>
      <div><dt>敵Power</dt><dd>{fight.enemyPower.toFixed(2)}</dd></div>
    </dl>

    <div className="ascent-card-fan" aria-hidden="true" />

    <div className="ascent-resource-line">
      <div><small>XP</small><strong>{formatNumber(run.xp, 1)} / {formatNumber(run.nextCardCost ?? 0, 0)}</strong></div>
      <div><small>現在の武器</small><strong>{run.weapon ? `${run.weapon.rarity} / P${run.weapon.power.toFixed(2)}` : 'NONE'}</strong></div>
      <div><small>記憶 / 遺物</small><strong>{run.cardCount} CARDS / {permanent.relicUnlocked ? `${permanent.relicTypes} RELIC` : 'SEALED'}</strong></div>
      <div><small>次のDP合計Lv</small><strong>{permanent.levels.total + 1} / COST {permanent.nextDpCost}</strong></div>
      <div><small>判定</small><strong>{fight.willWin ? `${duration.toFixed(2)}sで撃破` : `不足 ${Math.max(0, fight.enemyPower - fight.dpsPower).toFixed(2)}P`}</strong></div>
    </div>

    <div className="ascent-primary-control">
      <button className="ascent-attack-button" disabled={busy} onClick={onResolve}>
        <span>{paused ? '判定を実行' : '攻撃を継続'}</span>
      </button>
      <div className="ascent-speed-row" aria-label="表示速度">
        <span>速度</span>
        <button className={paused ? 'is-active' : ''} onClick={onPause}>{paused ? '再開' : '停止'}</button>
        {[1, 8, 64, 256].map((value) => <button key={value} className={speed === value ? 'is-active' : ''} onClick={() => onSpeed(value)}>×{value}</button>)}
      </div>
    </div>
  </section>;
}
