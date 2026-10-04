import type { ActionHandler, SessionState } from './types';
import { formatNumber, formatTime } from './types';
import { DPUpgrades } from './dp-upgrades';

export function ChoicePanels({ state, busy, act, onOpenBag, onClose }: { state: SessionState; busy: boolean; act: ActionHandler; onOpenBag?: () => void; onClose?: () => void }) {
  const run = state.run;
  const permanent = state.permanent;
  if (!run || !permanent || (state.status === 'combat' && !state.nonBlocking)) return null;

  if ((state.status === 'card' || (state.nonBlocking && state.status === 'combat')) && state.options?.length) {
    return <section className="decision decision--cards">
      {onClose && <button className="text-action" onClick={onClose}>閉じる（あとで選ぶ） ×</button>}
      {onOpenBag && <button className="text-action" onClick={onOpenBag}>所持品を確認</button>}
      <header><span>SELECTION // {String(run.cardCount + 1).padStart(2, '0')}</span><h2>次の構成要素を選択</h2><p>{state.nonBlocking ? `戦闘継続中・選択権 ${state.cardDrafts ?? 0}（死亡で消失）` : state.starterGuarantee ? '初期火力保証が有効です。' : state.forcedRarity ? `${state.forcedRarity}レアリティ確定報酬` : '戦闘は選択中停止しています。'}</p></header>
      <div className="card-options">{state.options.map((card, index) => <button key={card.key} disabled={!card.eligible || busy} onClick={() => act('select_card', { cardKey: card.key })} className={`rarity-${card.rarity} ${state.recommendedCard === card.key ? 'is-recommended' : ''}`}>
        <div className="card-options__number">0{index + 1}</div>
        <div className="card-options__rarity">{card.rarity} // {card.tags.join(' · ')}</div>
        <h3>{card.name}</h3>
        <p>{card.description}</p>
        <dl><div><dt>即時DPS</dt><dd>{card.immediateMultiplier === null ? 'DYNAMIC' : `×${card.immediateMultiplier.toFixed(3)}`}</dd></div><div><dt>次敵TTK</dt><dd>{card.nextTtk === null ? '不可' : `${card.nextTtk.toFixed(2)}s`}</dd></div></dl>
        <span className="card-options__select">このカードを選ぶ →</span>
      </button>)}</div>
      <button className="text-action" disabled={!state.rerollsLeft || busy} onClick={() => act('reroll')}>REROLL // 残り {state.rerollsLeft}</button>
    </section>;
  }

  if (state.status === 'weapon' && state.pendingWeapon) {
    const current = run.weapon;
    return <section className="decision decision--weapon"><header><span>WEAPON DROP</span><h2>新しい武器を検査</h2><p>装備するか、素材へ還元します。</p></header><div className="weapon-compare"><div><small>CURRENT</small><strong>{current ? `${current.rarity} / POWER ${current.power.toFixed(3)}` : 'NO WEAPON'}</strong><span>{current ? `Base ATK ×${(10 ** current.power).toFixed(2)}` : '空きスロット'}</span></div><b>→</b><div className="is-new"><small>NEW / W{state.pendingWeapon.originWave}</small><strong>{state.pendingWeapon.rarity} / POWER {state.pendingWeapon.power.toFixed(3)}</strong><span>Base ATK ×{(10 ** state.pendingWeapon.power).toFixed(2)}</span></div></div><div className="decision-actions"><button className="primary-paper-action" onClick={() => act('equip_weapon')} disabled={busy}>装備する →</button><button className="secondary-paper-action" onClick={() => act('smelt_weapon')} disabled={busy}>素材へ溶解</button></div></section>;
  }

  if (state.status === 'death' && state.death) {
    return <section className="decision decision--death">{onOpenBag && <button onClick={onOpenBag}>鞄で装備を確認</button>}
      <header><span>RUN TERMINATED</span><h2>Wave {state.death.failureWave}で時間切れ</h2><p>{state.death.reached}体撃破 / +{state.death.gainedDp} DP / {formatTime(state.death.runCombatSeconds)}</p></header>
      <div className="death-columns"><div><h3>DPを配分 / 残高 {permanent.bankedDp}</h3><p>{permanent.dpVersion}</p><DPUpgrades permanent={permanent} busy={busy} editable act={act} /></div>
        <div><h3>{state.equipmentMode ? '所持素材' : '統合工房'}</h3><div className="workshop-ledger">
          <div><span>武器素材</span><b>{formatNumber(permanent.weaponMaterial, 1)}</b>{!state.equipmentMode && <button disabled={!state.canForgeWeapon || busy} onClick={() => act('forge_weapon')}>武器生成 / {formatNumber(state.forgeWeaponCost, 1)}</button>}</div>
          <div><span>遺物素材</span><b>{formatNumber(permanent.relicMaterial, 1)}</b>{!state.equipmentMode && <button disabled={!state.canForgeRelic || busy} onClick={() => act('forge_relic')}>遺物生成 / {formatNumber(state.forgeRelicCost, 1)}</button>}</div>
        </div></div></div><button className="primary-paper-action retry-action" onClick={() => act('retry')} disabled={busy}>この育成で再挑戦 →</button></section>;
  }

  if (state.status === 'complete') {
    return <section className="decision decision--complete"><header><span>ARCHIVE COMPLETE</span><h2>Wave {state.targetWave ?? 500} 到達</h2><p>観測区間の記録が完了しました。</p></header><div className="completion-number">{state.targetWave ?? 500}</div><dl className="completion-ledger"><div><dt>RUN</dt><dd>{run.attempt}</dd></div><div><dt>DEATHS</dt><dd>{run.attempt - 1}</dd></div><div><dt>DP LEVEL</dt><dd>{permanent.levels.total}</dd></div><div><dt>COMBAT</dt><dd>{formatTime(run.totalCombatSeconds)}</dd></div></dl></section>;
  }

  return null;
}
