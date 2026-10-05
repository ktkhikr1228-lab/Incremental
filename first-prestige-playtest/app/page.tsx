'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { ChoicePanels } from '@/components/game-ui/choice-panels';
import { CombatStage } from '@/components/game-ui/combat-stage';
import { LastAscentStage } from '@/components/game-ui/last-ascent-stage';
import { ProgressionLedger } from '@/components/game-ui/progression-ledger';
import { FigmaMain } from '@/components/game-ui/figma-main';
import './figma-main.css';
import type { SessionState } from '@/components/game-ui/types';

const API = 'http://127.0.0.1:8765/api';

export default function Home() {
  const [state, setState] = useState<SessionState>({ status: 'idle' });
  const [profile, setProfile] = useState('balanced');
  const [seed, setSeed] = useState(20_260_828);
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [paused, setPaused] = useState(false);
  const [speed, setSpeed] = useState(8);
  const [visualMode, setVisualMode] = useState<'archive' | 'ascent' | 'figma'>('figma');
  const [error, setError] = useState('');
  const [battleElapsed, setBattleElapsed] = useState(0);
  const resolving = useRef(false);
  const liveState = useRef(state);
  const elapsedRef = useRef(0);
  const actionQueue = useRef<Promise<boolean | void>>(Promise.resolve());
  const requests = useRef(0);
  const interactionRequests = useRef(0);
  liveState.current = state;
  elapsedRef.current = battleElapsed;

  const loadState = useCallback(async () => {
    try {
      const response = await fetch(`${API}/state`, { cache: 'no-store' });
      if (!response.ok) throw new Error('state');
      const restored = await response.json() as SessionState;
      setState(restored);
      // Reloading a saved fight must not advance it before the player resumes.
      if (restored.saveSupported && restored.status === 'combat') setPaused(true);
      setConnected(true);
    } catch {
      setConnected(false);
    }
  }, []);

  useEffect(() => { void loadState(); }, [loadState]);

  const start = useCallback(async () => {
    setBusy(true);
    setPaused(false);
    setBattleElapsed(0);
    try {
      const response = await fetch(`${API}/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile, seed, equipmentMode: visualMode === 'figma' }),
      });
      if (!response.ok) throw new Error('start');
      setState(await response.json());
      setConnected(true);
    } catch (error) {
      setError(error instanceof Error ? error.message : '開始できませんでした');
      setPaused(true);
    } finally {
      resolving.current = false;
      setBusy(false);
    }
  }, [profile, seed, visualMode]);

  const act = useCallback((type: string, extra: Record<string, unknown> = {}) => {
    const requestedFight = liveState.current.fight?.id;
    const background = type === 'resolve' || type === 'save_progress';
    requests.current += 1;
    if (!background) { interactionRequests.current += 1; setBusy(true); }
    const operation = async () => {
    setError('');
    try {
      const current = liveState.current;
      const response = await fetch(`${API}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type, ...extra, ...(current.nonBlocking ? {
          fightId: type === 'resolve' ? requestedFight : current.fight?.id,
          elapsed: elapsedRef.current,
        } : {}) }),
      });
      const result = await response.json() as SessionState & { error?: string };
      if (!response.ok) throw new Error(result.error ?? type);
      const sameFight = result.fight && current.fight && result.fight.wave === current.fight.wave && result.run?.attempt === current.run?.attempt;
      const nextElapsed = sameFight ? Math.max(elapsedRef.current, result.fight?.elapsed ?? 0) : result.fight?.elapsed ?? 0;
      liveState.current = result;
      elapsedRef.current = nextElapsed;
      setBattleElapsed(nextElapsed);
      setState(result);
      return true;
    } catch (error) {
      setError(error instanceof Error ? error.message : '操作できませんでした');
      setPaused(true);
      return false;
    } finally {
      if (type === 'resolve') resolving.current = false;
      requests.current -= 1;
      if (!background) {
        interactionRequests.current -= 1;
        setBusy(interactionRequests.current > 0);
      }
    }
    };
    const queued = actionQueue.current.then(operation, operation);
    actionQueue.current = queued;
    return queued;
  }, []);

  const fightKey = state.fight && state.run ? `${state.run.attempt}:${state.fight.wave}` : 'none';
  useEffect(() => {
    if (!state.saveSupported || state.status !== 'combat' || paused) return;
    const timer = window.setInterval(() => {
      if (!requests.current && !resolving.current) void act('save_progress');
    }, 5000);
    return () => window.clearInterval(timer);
  }, [act, state.saveSupported, state.status, paused]);
  useEffect(() => {
    setBattleElapsed(state.fight?.elapsed ?? 0);
    resolving.current = false;
  }, [fightKey]);

  useEffect(() => {
    const fight = state.fight;
    if (state.status !== 'combat' || !fight || paused || (busy && !state.nonBlocking)) return;
    const duration = fight.willWin ? fight.timeToKill ?? fight.timeLimit : fight.timeLimit;
    const timer = window.setInterval(() => {
      setBattleElapsed((current) => {
        const next = Math.min(duration, current + 0.05 * speed);
        if (next >= duration && !resolving.current) {
          resolving.current = true;
          window.setTimeout(() => void act('resolve'), 0);
        }
        return next;
      });
    }, 50);
    return () => window.clearInterval(timer);
  }, [act, busy, paused, speed, state.fight, state.status]);

  const fight = state.fight ?? null;
  const run = state.run;
  const permanent = state.permanent;
  const duration = fight ? (fight.willWin ? fight.timeToKill ?? fight.timeLimit : fight.timeLimit) : 1;
  const progress = Math.min(100, (battleElapsed / Math.max(.001, duration)) * 100);

  if (visualMode === 'figma') return <main className="figma-page">
    {!connected && <p role="alert">計算サーバーに接続できません。npm run devで起動してください。</p>}
    {error && <p className="fm-error" role="alert">{error}</p>}
    {state.saveError && <p className="fm-error" role="alert">{state.saveError}</p>}
    <FigmaMain state={state} elapsed={battleElapsed} progress={progress} busy={busy || !connected} paused={paused} onPause={() => setPaused(value => !value)} act={act} start={() => void start()} />
    <details className="fm-debug"><summary>接続・テスト設定</summary><p>{state.candidateNotice ?? '開始すると装備UI用の独立セッションになります。'}</p><label>速度 <select value={speed} onChange={e => setSpeed(Number(e.target.value))}>{[1, 2, 8, 32].map(s => <option key={s} value={s}>{s}倍</option>)}</select></label><button onClick={() => void start()} disabled={busy || !connected}>初期化して開始</button></details>
  </main>;

  return <main className={`archive-shell ${visualMode === 'ascent' ? 'archive-shell--ascent' : ''}`}>
    <div className="archive-background" aria-hidden="true" />
    <header className="archive-header">
      <div className="archive-brand"><strong>{visualMode === 'ascent' ? 'THE LAST ASCENT' : 'ZERO ARCHIVE'}</strong><span>{visualMode === 'ascent' ? '永続の塔・観測層 12' : '第一転生観測記録 // 01'}</span></div>
      <div className="run-settings">
        <div className="visual-mode-switch" aria-label="表示テーマ">
          <button className={visualMode === 'archive' ? 'is-active' : ''} onClick={() => setVisualMode('archive')}>02 ARCHIVE</button>
          <button className={visualMode === 'ascent' ? 'is-active' : ''} onClick={() => setVisualMode('ascent')}>03 ASCENT</button>
        </div>
        <label><span>STRATEGY</span><select value={profile} onChange={(event) => setProfile(event.target.value)}><option value="damage">火力型</option><option value="balanced">標準型</option><option value="synergy">シナジー型</option></select></label>
        <label><span>SEED</span><input type="number" value={seed} onChange={(event) => setSeed(Number(event.target.value))} /></label>
        <button className="new-run-button" onClick={() => void start()} disabled={!connected || busy}>{state.status === 'idle' ? '観測を開始' : 'RUNを初期化'}</button>
      </div>
    </header>

    {!connected ? <div className="connection-warning">計算エンジンとの接続が切れています。ローカルサーバーを再起動してください。</div> : null}

    {state.status === 'idle' ? <section className="idle-state"><span>OBSERVATION TARGET</span><strong>001—500</strong><p>敵の増殖速度と戦闘出力を記録する。</p><button onClick={() => void start()} disabled={!connected || busy}>観測を開始 →</button></section> : null}

    {run && permanent ? <>
      <ProgressionLedger permanent={permanent} run={run} />
      {fight && visualMode === 'archive' ? <CombatStage fight={fight} run={run} permanent={permanent} elapsed={battleElapsed} duration={duration} progress={progress} speed={speed} paused={paused} busy={busy} onSpeed={setSpeed} onPause={() => setPaused((value) => !value)} onResolve={() => { resolving.current = true; void act('resolve'); }} /> : null}
      {fight && visualMode === 'ascent' ? <LastAscentStage fight={fight} run={run} permanent={permanent} elapsed={battleElapsed} duration={duration} progress={progress} speed={speed} paused={paused} busy={busy} onSpeed={setSpeed} onPause={() => setPaused((value) => !value)} onResolve={() => { resolving.current = true; void act('resolve'); }} /> : null}
      <ChoicePanels state={state} busy={busy} act={(type, extra) => void act(type, extra)} />
      <aside className="event-tape" aria-label="イベントログ"><span>SYSTEM LOG //</span>{state.logs?.slice(0, 3).map((entry, index) => <p key={`${entry}-${index}`}>{entry}</p>)}</aside>
    </> : null}

    <div className="archive-coordinate archive-coordinate--left">ZA // FILE {String(run?.kills ?? 0).padStart(3, '0')}</div>
    <div className="archive-coordinate archive-coordinate--right">W1—500 // LOCAL RECORD</div>
  </main>;
}
