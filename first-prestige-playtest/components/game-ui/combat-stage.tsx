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

export function CombatStage({ fight, run, permanent, elapsed, duration, progress, speed, paused, busy, onSpeed, onPause, onResolve }: Props) {
  const remaining = Math.max(0, duration - elapsed);
  const hpWidth = fight.willWin ? Math.max(0, 100 - progress) : Math.max(13, 100 - progress * .72);
  const wave = String(fight.wave).padStart(3, '0');

  return <section className="combat" aria-label={`Wave ${fight.wave} 戦闘中`}>
    <div className="wave-mark" aria-label={`現在Wave ${fight.wave}`}>
      <span className="wave-mark__side">現在の波 //</span>
      <strong>{wave}</strong>
    </div>

    <div className="enemy-copy">
      <div className="enemy-copy__index">ENEMY // {fight.boss ? 'BOSS' : String((fight.wave % 23) + 1).padStart(3, '0')}</div>
      <h2>{fight.boss ? '虚蝕の主核' : '虚蝕の集合体'}</h2>
      <p>MASS OF NULL</p>
      <div className="enemy-copy__traits"><span>時間経過で増殖</span><span>高い群体HP</span></div>
    </div>

    <div className="objective">
      <b>OBJECTIVE</b>
      <span>敵の群れを殲滅し、次の波へ進め。</span>
      <small>TIP // DPSを上げるか、攻撃速度を強化しよう。</small>
    </div>

    <div className="battle-gauge">
      <div className="battle-gauge__label">HP</div>
      <div className="battle-gauge__numbers"><strong>{fight.enemyHp}</strong><span> / 10^{fight.hpPower.toFixed(2)}</span></div>
      <div className="battle-gauge__track"><i style={{ width: `${hpWidth}%` }} /></div>
      <div className="battle-gauge__time"><small>残り時間</small><strong>{remaining.toFixed(1)}s</strong></div>
    </div>

    <div className="damage-readout">
      <div className="section-kicker">現在のDPS</div>
      <strong>{fight.dps}</strong>
      <div className="damage-readout__line" />
    </div>

    <div className="damage-detail">
      <div className="section-kicker">DPS内訳</div>
      <dl>
        <div><dt>POWER</dt><dd>{fight.dpsPower.toFixed(3)}</dd></div>
        <div><dt>HIT / 秒</dt><dd>{fight.attackSpeed.toFixed(2)}</dd></div>
        <div><dt>CRITICAL</dt><dd>{(fight.critChance * 100).toFixed(1)}%</dd></div>
        <div><dt>CRIT倍率</dt><dd>×{fight.critMultiplier.toFixed(2)}</dd></div>
      </dl>
    </div>

    <div className="enemy-status">
      <div className="section-kicker">敵の状態</div>
      <strong>{fight.willWin ? '撃破可能' : '突破不可'}</strong>
      <span>{fight.willWin ? `${duration.toFixed(2)}s で撃破` : `あと ${Math.max(0, fight.enemyPower - fight.dpsPower).toFixed(2)} Power`}</span>
      <div className="tick-line"><i style={{ left: `${Math.min(100, progress)}%` }} /></div>
    </div>

    <div className="primary-control">
      <div className="section-kicker">ACTION_01</div>
      <button className="attack-button" disabled={busy} onClick={onResolve}><span>{paused ? '判定を実行' : '次の攻撃'}</span><b>→</b><small>SPACE</small></button>
      <div className="speed-row" aria-label="表示速度">
        <button className={paused ? 'is-active' : ''} onClick={onPause}>{paused ? '再開' : '停止'}</button>
        {[1, 8, 64, 256].map((value) => <button key={value} className={speed === value ? 'is-active' : ''} onClick={() => onSpeed(value)}>×{value}</button>)}
      </div>
    </div>

    <div className="build-line">
      <div><small>WEAPON</small><strong>{run.weapon ? `${run.weapon.rarity} / P${run.weapon.power.toFixed(2)}` : 'NONE'}</strong></div>
      <span>×</span><div><small>CARDS</small><strong>{String(run.cardCount).padStart(2, '0')}</strong></div>
      <span>×</span><div><small>RELIC</small><strong>{permanent.relicUnlocked ? `${permanent.relicTypes} TYPE` : 'LOCKED'}</strong></div>
      <span>×</span><div><small>DP BUILD</small><strong>{permanent.levels.atk}.{permanent.levels.attackSpeed}.{permanent.levels.xp}</strong></div>
      <div className="build-line__xp"><small>XP</small><strong>{formatNumber(run.xp, 1)} / {formatNumber(run.nextCardCost ?? 0, 0)}</strong></div>
    </div>
  </section>;
}
