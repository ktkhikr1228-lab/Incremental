import type { Permanent, RunView } from './types';
import { formatNumber, formatTime } from './types';

export function ProgressionLedger({ permanent, run }: { permanent: Permanent; run: RunView }) {
  const entries = [
    ['XP', `${formatNumber(run.xp, 1)} / ${formatNumber(run.nextCardCost ?? 0, 0)}`],
    ['DP', formatNumber(permanent.bankedDp, 0)],
    ['DP LEVEL', formatNumber(permanent.levels.total, 0)],
    ['WEAPON MAT.', formatNumber(permanent.weaponMaterial, 1)],
    ['RELIC MAT.', formatNumber(permanent.relicMaterial, 1)],
    ['BEST WAVE', String(permanent.maxWave).padStart(3, '0')],
  ];

  return <aside className="ledger" aria-label="恒久リソース">
    <div className="ledger__title"><span>永久リソース</span><small>PERMANENT LEDGER</small></div>
    <dl className="ledger__rows">{entries.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
    <div className="ledger__footer">
      <span>RUN {String(run.attempt).padStart(2, '0')}</span>
      <span>{formatTime(run.totalCombatSeconds)}</span>
    </div>
  </aside>;
}
