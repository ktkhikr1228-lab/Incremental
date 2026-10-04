import type { ActionHandler, Permanent } from './types';

export function DPUpgrades({ permanent, busy, editable, act }: {
  permanent: Permanent; busy: boolean; editable: boolean; act: ActionHandler;
}) {
  const entries = permanent.dpUpgrades ?? [
    { key: 'atk', label: 'Base ATK', level: permanent.levels.atk, cost: permanent.nextDpCost, effect: '', unlocked: true, unlockWave: 0 },
    { key: 'attack_speed', label: 'Attack Speed', level: permanent.levels.attackSpeed, cost: permanent.nextDpCost, effect: '', unlocked: true, unlockWave: 0 },
    { key: 'xp', label: 'XP Gain', level: permanent.levels.xp, cost: permanent.nextDpCost, effect: '', unlocked: true, unlockWave: 0 },
  ];
  const reroll = permanent.rerollUpgrade;
  return <div className="upgrade-list">{entries.map(entry => <button key={entry.key}
    disabled={busy || !editable || !entry.unlocked || permanent.bankedDp < entry.cost}
    onClick={() => act('buy_dp', { upgrade: entry.key })}>
    <span>{entry.label}</span><b>{entry.unlocked ? `Lv ${entry.level} → ${entry.level + 1}` : `LOCKED / W${entry.unlockWave}`}</b>
    <small>{entry.effect} / COST {entry.cost} DP</small>
  </button>)}{reroll && <button disabled={busy || !editable || !reroll.unlocked || reroll.bought || permanent.bankedDp < reroll.cost}
    onClick={() => act('buy_dp', { upgrade: 'reroll' })}><span>Reroll +1 / Run</span>
    <b>{reroll.bought ? '購入済み' : reroll.unlocked ? '1 → 2回' : 'LOCKED / W400'}</b><small>COST {reroll.cost} DP</small></button>}</div>;
}
