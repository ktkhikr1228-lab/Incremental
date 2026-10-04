import type { ActionHandler, EquipmentItem, SessionState } from './types';
import { formatNumber } from './types';

export const rarityNames: Record<string, string> = { C: 'Common', U: 'Uncommon', R: 'Rare', E: 'Epic', L: 'Legendary' };
const affixNames: Record<string, string> = { weapon_atk_additive: 'Weapon ATK', weapon_atk_pct: 'Weapon ATK', base_atk_pct: 'Base ATK', attack_speed_pct: 'AS', crit_rate: 'Crit率', crit_multiplier: 'Crit倍率', all_damage_pct: 'All Damage' };
export function equipmentEffects(item: EquipmentItem): string[] {
  const strength = [1, 1.08, 1.16, 1.24][item.enhancement];
  const lines = item.kind === 'weapon'
    ? [`基礎Weapon ATK ${formatNumber(item.base_atk * item.quality * strength)}`]
    : [item.unique_key === 'learning_lens' ? `XP +${formatNumber(10 * ({ C: 1, U: 1.25, R: 1.5 }[item.rarity] ?? 1) * strength * (1 + .02 * item.duplicate_levels))}%` : '固有効果未接続'];
  return [...lines, ...Object.entries(item.affixes).map(([key, amount]) => `${affixNames[key] ?? key} +${formatNumber(amount * strength * (key === 'weapon_atk_additive' || key === 'crit_multiplier' ? 1 : 100))}${key === 'crit_rate' ? 'pt' : key.endsWith('_pct') ? '%' : ''}`)];
}

export function EquipmentList({ state, busy, act, close }: { state: SessionState; busy: boolean; act: ActionHandler; close: () => void }) {
  const inv = state.equipment;
  const pending = state.pendingEquipmentList ?? [];
  const equipped = new Set([inv?.weapon_slot, ...(inv?.relic_slots ?? [])]);
  const all = [...pending, ...Object.values(inv?.items ?? {})];
  return <div className="fm-modal-backdrop"><section className="fm-dialog fm-equipment-list" role="dialog" aria-label="武器・装備一覧">
    <button className="fm-dialog-close" onClick={close}>閉じる ×</button>
    <h2>武器・装備一覧</h2><p>戦闘継続中。拾った装備と所持品を比較して、装備／保管／分解を選択。</p>
    <div className="fm-equipment-grid">{all.map(item => {
      const drop = pending.some(p => p.uid === item.uid);
      const worn = equipped.has(item.uid);
      return <article key={item.uid} className={`fm-equipment-entry rarity-${item.rarity}`}>
        <small>{drop ? '今回獲得' : worn ? '装備中' : '保管中'} · W{item.origin_wave}</small>
        <h3>{item.name} +{item.enhancement}</h3><b>{rarityNames[item.rarity]}</b>
        {equipmentEffects(item).map(line => <p key={line}>{line}</p>)}
        <p>品質 {formatNumber(item.quality, 3)}</p>
        <button disabled={busy || worn} onClick={() => act(drop ? 'gear_receive' : 'gear_equip', { uid: item.uid, equip: true })}>装備</button>
        <button disabled={busy || (!drop && !worn)} onClick={() => act(drop ? 'gear_receive' : 'gear_unequip', { uid: item.uid })}>保管</button>
        <button disabled={busy} onClick={() => act(drop ? 'gear_discard' : 'gear_dismantle', { uid: item.uid })}>分解</button>
      </article>;
    })}</div>{!all.length && <p>所持装備なし</p>}
  </section></div>;
}
