'use client';

import { useEffect, useRef, useState } from 'react';
import type { ActionHandler, EquipmentItem, SessionState } from './types';
import { formatNumber } from './types';
import { ChoicePanels } from './choice-panels';
import { DPUpgrades } from './dp-upgrades';
import { EquipmentList, equipmentEffects, rarityNames } from './equipment-list';

const asset = (name: string, ext = 'png') => `/figma-main/${name}.${ext}`;
const icon = (name: string, alt: string) => <img src={asset(name)} alt={alt} />;
const costs = [4, 9, 16];
const materialValues: Record<string, number> = { C: 1, U: 3, R: 6 };

export function FigmaMain({ state, elapsed, progress, busy, paused, onPause, act, start }: {
  state: SessionState; elapsed: number; progress: number; busy: boolean;
  paused: boolean; onPause: () => void; act: ActionHandler; start: () => void;
}) {
  const [bag, setBag] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver(entries => setScale(Math.min(1, entries[0].contentRect.width / 1440)));
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  const [panel, setPanel] = useState<'none' | 'dp' | 'settings' | 'cards'>('none');
  const [selected, setSelected] = useState<string | null>(null);
  const [cardDetail, setCardDetail] = useState<string | null>(null);
  const [draftOpen, setDraftOpen] = useState(false);
  const [gearOpen, setGearOpen] = useState(false);
  useEffect(() => {
    if (draftOpen && state.status === 'combat' && (state.cardDrafts ?? 0) > 0 && !state.options?.length && !busy) act('open_cards');
  }, [draftOpen, state.status, state.cardDrafts, state.options?.length, busy]);
  const lastDrop = useRef<string | undefined>(undefined);
  const latestDrop = state.pendingEquipmentList?.at(-1)?.uid;
  useEffect(() => {
    if (latestDrop && latestDrop !== lastDrop.current) setGearOpen(true);
    lastDrop.current = latestDrop;
  }, [latestDrop]);
  const [relicSlot, setRelicSlot] = useState(0);
  const inv = state.equipment;
  const items = inv?.items ?? {};
  const weapon = inv?.weapon_slot ? items[inv.weapon_slot] : null;
  const relics = inv?.relic_slots.map(uid => uid ? items[uid] : null) ?? [null, null, null];
  const equipped = new Set([inv?.weapon_slot, ...(inv?.relic_slots ?? [])]);
  const stored = (kind: string) => Object.values(items).filter(item => item.kind === kind && !equipped.has(item.uid));
  const editable = !!inv && !busy && state.status !== 'idle' && state.status !== 'complete';
  const item = selected ? items[selected] : undefined;
  const player = state.player ?? state.fight;
  const hpSamples = state.fight?.hpSamples;
  const hpPercent = hpSamples ? 100 * (hpSamples.findLast(sample => sample.time <= elapsed)?.remaining ?? 1) : Math.max(0, 100 - progress);
  const dismantleValue = (value: EquipmentItem) => (value.kind === 'relic' ? materialValues[value.rarity] : ({ C: 1, U: 3, R: 8, E: 20, L: 50 }[value.rarity] ?? 0) * (state.equipmentDismantleMultiplier ?? 1)) + Math.floor(value.enhancement_spent / 2);
  const itemTitle = (value: EquipmentItem) => `${value.name} ${value.rarity} +${value.enhancement}`;
  const effects = equipmentEffects;
  const dragDrop = (event: React.DragEvent, action: string, slot = 0) => {
    event.preventDefault();
    const uid = event.dataTransfer.getData('application/x-equipment-id');
    if (editable && items[uid]) { act(action, { uid, slot }); if (action === 'gear_dismantle') setSelected(null); }
  };
  const tile = (value: EquipmentItem | null, label: string) => <button key={value?.uid ?? label} className={`fm-item rarity-${value?.rarity ?? 'empty'}`} title={value ? `${itemTitle(value)}\n${effects(value).join('\n')}` : label} onClick={() => value && setSelected(value.uid)} disabled={!value} draggable={!!value && editable} onDragStart={event => value && event.dataTransfer.setData('application/x-equipment-id', value.uid)}>
    {value ? icon(value.kind === 'weapon' ? 'imgRectangle4' : 'imgRectangle10', value.name) : <span>—</span>}
    {value ? <small>+{value.enhancement}</small> : null}
  </button>;
  const cards = <div className="fm-card-scroll">{state.run?.cards.map(card => <button className={`fm-card-wrap rarity-${card.rarity ?? 'C'}`} key={card.key} title={card.description} onClick={() => setCardDetail(card.key)}><div className="fm-card">{icon('imgRectangle7', '')}<span>{card.name}</span></div><small>{rarityNames[card.rarity ?? 'C']} ×{card.count}</small></button>)}{!state.run?.cards.length && <p>カード未取得</p>}</div>;
  const ownedCard = state.run?.cards.find(c => c.key === cardDetail);
  const battle = <section className="fm-battle" aria-label="戦闘">
    <img className="fm-stage-frame" src={asset('imgRectangle11', 'svg')} alt="" />
    <div className="fm-battle-inner">
      <img className="fm-inner-frame" src={asset('imgRectangle2', 'svg')} alt="" />
      <div className="fm-hp"><img src={asset('imgRectangle5', 'svg')} alt="" /><span>HP {state.fight ? `${hpPercent.toFixed(0)}% / ${state.fight.enemyHp}` : '—'}</span></div>
      <p className="fm-timer">残り時間 {Math.max(0, (state.fight?.timeLimit ?? 0) - elapsed).toFixed(1)}秒</p>
      <div className="fm-target"><img src={asset('imgEllipse1', 'svg')} alt="" /><span>敵</span></div>
      {state.fight ? <><span className="fm-damage">{state.fight.dps}</span><span className="fm-critical">{(state.fight.critChance * 100).toFixed(0)}%</span></> : null}
      <button className="fm-active" disabled><img src={asset('imgEllipse4', 'svg')} alt="" />Active LOCKED</button>
      <div className="fm-attack-mark">{weapon ? '剣の攻撃' : '通常攻撃'}</div>
    </div>
    <div className="fm-xp"><img src={asset('imgRectangle14', 'svg')} alt="" /><div className="fm-xp-fill" style={{ width: `${Math.min(100, 100 * (state.run?.xp ?? 0) / (state.run?.nextCardCost ?? 1))}%` }} /><span>XP {formatNumber(state.run?.xp, 1)} / {formatNumber(state.run?.nextCardCost ?? undefined, 1)}</span></div>
  </section>;

  return <div className="fm-container" ref={container}><div className="fm-screen" data-node-id="18:2" style={{ zoom: scale }}>
    {state.status === 'death' && <div className="fm-status" role="status">時間切れ — 再挑戦は手動です。開いている画面を閉じてDP購入・再挑戦へ。</div>}
    <section className="fm-left">
      <h1>WAVE数<br /><span>{state.fight?.wave ?? state.run?.kills ?? 0}/{state.targetWave ?? 5000}</span></h1>
      <img className="fm-left-rule" src={asset('imgLine7', 'svg')} alt="" />
      <div className="fm-loadout"><div className="fm-weapon-head">{weapon ? tile(weapon, '武器') : <div className="fm-empty-weapon">{icon('imgRectangle4', '')}<span>武器未装備</span></div>}<div><strong>{weapon?.name ?? '—'}</strong>{weapon && <small>{weapon.rarity} +{weapon.enhancement}</small>}</div></div>
        <div className="fm-weapon-effects">{weapon ? effects(weapon).slice(0, 4).map(line => <p key={line}>{line}</p>) : <p>W10で取得</p>}</div>
        <div className="fm-relics">{relics.map((relic, i) => <div key={i}>{tile(relic, `遺物枠${i + 1}`)}{relic && effects(relic).slice(0, 2).map(line => <p key={line}>{line}</p>)}</div>)}</div>
        {cards}
      </div>
    </section>
    <img className="fm-divider fm-divider-left" src={asset('imgLine1', 'svg')} alt="" />
    {battle}
    <img className="fm-divider fm-divider-right" src={asset('imgLine5', 'svg')} alt="" />
    <aside className="fm-right"><h2>ステータス</h2><dl>{[['基礎攻撃力', player?.baseAttack ?? '—'], ['クリティカル率', `${formatNumber((player?.critChance ?? 0) * 100, 1)}%`], ['クリティカル倍率', `${formatNumber(player?.critMultiplier)}倍`], ['攻撃速度', `${formatNumber(player?.attackSpeed)}/s`], ['追撃率', `${formatNumber((player?.followRate ?? 0) * 100)}%`], ['ヒット数', formatNumber(player?.hitCount)]].map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>
      <button onClick={() => setPanel('settings')}>詳細表示 …</button><h2>マイルストーン</h2>{[10, 100, 500, 2500, 4000, 5000].map(w => <p key={w}>W{w} {(state.permanent?.maxWave ?? 0) >= w ? '✓' : ''}</p>)}<p className="fm-progress">最高 W{state.permanent?.maxWave ?? 0}</p>
    </aside>
    <footer className="fm-footer"><img className="fm-footer-rule" src={asset('imgLine6', 'svg')} alt="" />
      <button onClick={() => setBag(true)}>{icon('imgRectangle6', '')}<span>鞄</span></button>
      <button onClick={() => setPanel('dp')}>{icon('imgRectangle16', '')}<span>DP</span></button>
      <button disabled>{icon('imgRectangle18', '')}<span>UB</span></button>
      <button disabled>{icon('imgRectangle8', '')}<span>転生</span></button>
      <div className="fm-footer-space" />
      <button onClick={() => setDraftOpen(true)}>{icon('imgRectangle17', '')}<span>選択 {state.cardDrafts ?? 0}</span></button>
      <button onClick={() => setPanel('cards')}><span>一覧</span></button>
      <button onClick={() => setPanel('settings')}><img src={asset('imgStar1', 'svg')} alt="" /><span>設定</span></button>
    </footer>
    {state.status === 'idle' && <div className="fm-start"><button disabled={busy} onClick={start}>開始</button></div>}
    {bag && <div className="fm-bag" role="dialog" aria-label="バックパック"><button className="fm-bag-close" onClick={() => setBag(false)}>鞄 ▲ 閉じる</button>{state.status === 'death' && <p className="fm-bag-death" role="status">時間切れ。鞄を閉じて再挑戦へ。</p>}<div className="fm-bag-grid">
      <section><h2>Relic</h2><div className="fm-equipped-row">{relics.map((r, i) => <div key={i} onDragOver={e => e.preventDefault()} onDrop={e => dragDrop(e, 'gear_equip', i)}>{tile(r, `遺物${i + 1}`)}</div>)}</div><h3>保管 {stored('relic').length}/{inv?.storage_capacity.relic ?? 5}</h3><div className="fm-storage" onDragOver={e => e.preventDefault()} onDrop={e => dragDrop(e, 'gear_unequip')}>{stored('relic').map(r => tile(r, r.uid))}</div></section>
      <section className="fm-compact">{battle}</section>
      <section className="fm-future"><span>╲　╱</span><strong>LOCKED</strong><span>╱　╲</span></section>
      <section><h2>Weapon <button onClick={() => setGearOpen(true)}>全装備を比較</button></h2><div className="fm-drop-slot" onDragOver={e => e.preventDefault()} onDrop={e => dragDrop(e, 'gear_equip')}>{tile(weapon, '装備枠へドロップ')}</div><h3>保管 {stored('weapon').length}/{inv?.storage_capacity.weapon ?? 5}</h3><div className="fm-storage" onDragOver={e => e.preventDefault()} onDrop={e => dragDrop(e, 'gear_unequip')}>{stored('weapon').map(w => tile(w, w.uid))}</div></section>
      <section><h2>Furnace ＋ Materials</h2><p>武器素材 {formatNumber(inv?.materials.weapon)}</p><p>遺物素材 {formatNumber(inv?.materials.relic)}</p><div className="fm-furnace" onDragOver={e => e.preventDefault()} onDrop={e => dragDrop(e, 'gear_dismantle')}><p>ここへドロップで即分解</p><p>確認操作なし／装備詳細の「分解」でも操作できます。</p></div></section>
      <section><h2>Card Case</h2>{cards}</section>
    </div></div>}
    {item && <div className="fm-modal-backdrop"><section className="fm-dialog" role="dialog" aria-label="装備詳細"><button className="fm-dialog-close" onClick={() => setSelected(null)}>閉じる ×</button><h2>{itemTitle(item)}</h2><p>取得 W{item.origin_wave}／品質 {item.quality}／重複 {item.duplicate_levels}/10</p>{effects(item).map(line => <p key={line}>{line}</p>)}<p>戦闘は継続中。変更はその時点から適用。</p>
      {item.kind === 'relic' && <label>装備先 <select value={relicSlot} onChange={e => setRelicSlot(Number(e.target.value))}>{[0, 1, 2].map(i => <option value={i} key={i}>枠{i + 1}</option>)}</select></label>}
      <button disabled={!editable} onClick={() => act(equipped.has(item.uid) ? 'gear_unequip' : 'gear_equip', { uid: item.uid, slot: relicSlot })}>{equipped.has(item.uid) ? '保管へ' : '装備'}</button>
      <button disabled={!editable || item.enhancement >= 3 || (inv?.materials[item.kind] ?? 0) < costs[item.enhancement]} onClick={() => act('gear_enhance', { uid: item.uid })}>強化 {costs[item.enhancement] ?? 'MAX'}素材</button>
      <button disabled={!editable} onClick={() => { act('gear_dismantle', { uid: item.uid }); setSelected(null); }}>分解 ＋{formatNumber(dismantleValue(item))}素材</button>
      {Object.values(items).filter(other => other.uid !== item.uid && other.kind === 'relic' && item.kind === 'relic' && other.name === item.name).map(other => <div key={other.uid}><p>同名 {itemTitle(other)}</p><button disabled={!editable || item.duplicate_levels >= 10} onClick={() => act('gear_absorb', { uid: item.uid, otherUid: other.uid })}>相手を消費して重複強化</button><button disabled={!editable} onClick={() => { act('gear_replace', { uid: item.uid, otherUid: other.uid }); setSelected(null); }}>相手へ交換（現在品を分解）</button></div>)}
    </section></div>}
    {gearOpen && !item && <EquipmentList state={state} busy={busy} act={act} close={() => setGearOpen(false)} />}
    {ownedCard && <div className="fm-modal-backdrop"><section className={`fm-dialog rarity-${ownedCard.rarity}`} role="dialog" aria-label="所持カード詳細"><button onClick={() => setCardDetail(null)}>閉じる ×</button><h2>{ownedCard.name}</h2><p>{rarityNames[ownedCard.rarity ?? 'C']} · 所持 ×{ownedCard.count}</p><p>{ownedCard.description}</p><p>上記は1枚の効果。現在の戦闘値は右のステータスへ反映されています。</p></section></div>}
{panel !== 'none' && <div className="fm-modal-backdrop"><section className="fm-dialog" role="dialog" aria-label={panel}><button onClick={() => setPanel('none')}>閉じる ×</button>{panel === 'cards' ? cards : panel === 'dp' ? <><h2>DP {state.permanent?.bankedDp ?? 0}</h2>{state.permanent && <DPUpgrades permanent={state.permanent} busy={busy} editable={state.status === 'death'} act={act} />}<p>{state.permanent?.dpVersion} / 死亡後に購入可能</p></> : <><h2>設定</h2><button onClick={onPause}>{paused ? '再開' : '一時停止'}</button><p>{state.candidateNotice ?? '旧プレイテスト'}</p></>}</section></div>}
  </div>{!bag && !item && !ownedCard && panel === 'none' && !gearOpen && (state.status === 'death' || state.status === 'complete' || (draftOpen && !!state.options?.length)) && <ChoicePanels state={state} busy={busy} act={act} onClose={() => setDraftOpen(false)} onOpenBag={() => setBag(true)} />}{draftOpen && !state.options?.length && state.status === 'combat' && <button className="fm-draft-empty" onClick={() => setDraftOpen(false)}>選択権なし・閉じる</button>}</div>;
}
