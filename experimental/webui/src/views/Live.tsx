/* The live view: a run's worker logs as they are written (the employee's and
   each replica's playing a drill), grouped by turn, polled every few seconds
   from /api/live by each log's byte offset. New turns land at the bottom; the
   page follows them only while the reader is already at the bottom, so
   reading further up is never interrupted. */

import { Fragment, memo, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'

import { fileUrl, loadLive, thumbsUrl } from '../api'
import { cursorOf, delivered, groupTurns, merge, mergeEvents, namesOf, panelItems, steps, stopped, toolItemState } from '../live'
import { DECK } from '../trial'
import { Clamp, Fold, StrategyBadge } from './Badges'
import { Deliverables } from './Deliverables'
import { Markdown } from './Markdown'
import { DeckHead, Graph, InterceptionRow, useThumbs } from './Trials'

import type { CuratorEvent, CuratorProgress, Delivered, KeptFile, LiveItem, LiveLog, LiveTurn, PanelItem, Phase } from '../live'
import type { RecordRow } from '../model'
import type { JSX } from 'react'

const RUNNING_POLL = 3000
const IDLE_POLL = 15000
const NEAR_BOTTOM = 120

const ago = (seconds: number): string =>
  seconds < 60 ? `${Math.max(0, Math.round(seconds))} s` : seconds < 3600 ? `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s` : `${Math.floor(seconds / 3600)} h ${Math.floor((seconds % 3600) / 60)} min`

const megabytes = (bytes: number): string => `${(bytes / 1_000_000).toFixed(1)} MB`

/** A log's folder as the reader knows it: a replica's round and drill (replicas/1-session-3fa2b1/<worker> is 1-family
    once `names` knows the label), else the worker. */
const logLabel = (file: string | null, names: Record<string, string> = {}): string => {
  if (!file) return ''
  const parts = file.split('/')
  if (parts[0] !== 'replicas' || !parts[1]) return parts[0].slice(0, 8)
  const [, round, label] = /^(\d+)-(.+)$/.exec(parts[1]) ?? []
  return label && names[label] ? `${round}-${names[label]}` : parts[1]
}

function Tool({ item, over }: { item: Extract<LiveItem, { kind: 'tool' }>; over: boolean }): JSX.Element {
  const state = toolItemState(item, over)
  return (
    <Fold
      className={`ltool ${state}`}
      summary={
        <>
          <span className="dot" />
          <span className="nm">{item.name || 'tool'}</span>
          <span className="args">{item.args}</span>
          <span className="st">{state}</span>
        </>
      }
    >
      {() => <pre>{item.result || (state === 'interrupted' ? 'The run stopped before this call returned.' : 'No result yet.')}</pre>}
    </Fold>
  )
}

interface Stop {
  /** The run is not running: whatever is still open was interrupted. */
  over: boolean
  /** The run's last event in ms, where interrupted durations stop. */
  at: number | null
}

function Item({ item, drill, now, runId, stop }: { item: LiveItem; drill: string; now: number; runId: string; stop: Stop }): JSX.Element {
  switch (item.kind) {
    case 'reply':
      return (
        <div className="ai-wrap">
          <span className="who"><span className="wd" />employee</span>
          <div className="ai"><Markdown text={item.text} /></div>
        </div>
      )
    case 'tool':
      return <Tool item={item} over={stop.over} />
    case 'dag':
      return <Graph graph={item.run} drill={drill} now={now} runId={runId} over={stop.over} stoppedAt={stop.at} />
    case 'interception':
      return <InterceptionRow row={item.row} />
    case 'message':
      return (
        <div className="lmsg">
          <span className="k">Delivered back into the conversation</span>
          <Clamp long={item.text.length > 600}><p>{item.text}</p></Clamp>
        </div>
      )
    case 'error':
      return <p className="err">{item.text}</p>
  }
}

/* Memoised so the one-second clock re-renders only the turn still in progress. */
const Turn = memo(function Turn({ turn, now, runId, over, stoppedAt, names }: { turn: LiveTurn; now: number; runId: string; over: boolean; stoppedAt: number | null; names: Record<string, string> }): JSX.Element {
  const stop = useMemo(() => ({ over, at: stoppedAt }), [over, stoppedAt])
  return (
    <div className={`lturn${turn.open && !over ? ' open' : ''}`}>
      <div className="lturn-hd">
        <span className="nm">{turn.drill ?? 'turn'}</span>
        <code>{turn.id.slice(0, 8)}</code>
        {turn.file ? <code className="dim" title={turn.file}>{logLabel(turn.file, names)}</code> : null}
        {turn.open && !over ? <span className="pulse"><span className="dot" />in progress</span> : null}
        {turn.open && over ? <span className="halted" title="The run stopped before this turn closed">interrupted</span> : null}
      </div>
      {turn.customer ? (
        <div className="me-wrap">
          <p className="me">{turn.customer}</p>
          <span className="who">{turn.drill ?? 'customer'} · customer</span>
        </div>
      ) : null}
      {turn.items.map((item, i) => <Item key={i} item={item} drill={turn.drill ?? 'turn'} now={now} runId={runId} stop={stop} />)}
    </div>
  )
})

function PanelRow({ item }: { item: PanelItem }): JSX.Element {
  switch (item.kind) {
    case 'call':
      return <p className="crow call">model call {item.call}{item.stage ? ` · ${item.stage}` : ''}</p>
    case 'note':
      return <div className="crow note"><Clamp long={item.text.length > 420}><Markdown text={item.text} /></Clamp></div>
    case 'query':
      return (
        <p className={`crow query${item.rejected ? ' refused' : ''}`}>
          <span className="dot" /><span className="nm">{item.tool || 'query'}</span><span className="args">{item.argument}</span>
          {item.rejected ? <span className="st">refused</span> : null}
        </p>
      )
    case 'staged':
      return <p className="crow staged"><span className="k">staged</span><code>{item.path}</code></p>
    case 'submit':
      return (
        <div className="crow submit">
          <p><span className="nm">{item.name}</span>{item.targets.map(({ target, strategy }) => <span key={target} className="tgt"><code>{target}</code><StrategyBadge strategy={strategy} /></span>)}</p>
          {item.understanding ? <Clamp long={item.understanding.length > 300}><Markdown text={item.understanding} /></Clamp> : null}
        </div>
      )
    case 'check':
      return (
        <div className={`crow check ${item.errors.length ? 'bad' : 'ok'}`}>
          <p>
            <span className="nm">{item.name}</span>
            <span className="st">{item.errors.length ? `${item.errors.length} error${item.errors.length === 1 ? '' : 's'}` : item.name === 'validation' ? 'passed' : 'ran; its result is not in the progress file'}</span>
            {item.detail ? <span className="args">{item.detail}</span> : null}
          </p>
          {item.errors.map((error, i) => <p key={i} className="err">{error}</p>)}
        </div>
      )
    case 'rejected':
      return <p className="crow rejected"><span className="nm">{item.name}</span>{item.tool ? <code>{item.tool}</code> : null}<span>{item.error}</span></p>
    case 'gap':
      return <p className="crow gap">Earlier events were not kept between polls.</p>
    case 'other':
      return <p className="crow call">{item.name}{item.detail ? ` · ${item.detail}` : ''}</p>
  }
}

/* The Curator's revision as it happens, from its progress file: the stage, the
   budget spent, the files staged and the event stream in order. */
function CuratorPanel({ progress, events, now }: { progress: CuratorProgress; events: CuratorEvent[]; now: number }): JSX.Element {
  const items = useMemo(() => panelItems(events), [events])
  return (
    <section className="cpanel">
      <div className="cpanel-hd">
        <span className="cd" />
        <span className="nm">Curator</span>
        <span>{progress.finished ? (progress.error ? 'revision failed' : 'revision finished') : 'revising the Harness'}</span>
        <span className="quiet">started {ago(now / 1000 - progress.started)} ago · updated {ago(now / 1000 - progress.updated)} ago</span>
      </div>
      <ol className="steps">
        {steps(progress).map((step) => <li key={step.id} className={step.state}><span className="dot" />{step.label}</li>)}
      </ol>
      <p className="budget">
        <span>{progress.calls} model calls</span><span>{progress.queries} queries</span><span>{progress.checks} checks</span><span>{progress.repairs} repairs</span>
      </p>
      {progress.staged.length ? (
        <p className="mats light"><span className="k">Staged</span>{progress.staged.map((path) => <code key={path}>{path}</code>)}</p>
      ) : null}
      {progress.error ? <div className="failed"><Markdown text={progress.error} /></div> : null}
      <div className="cstream">
        {items.length === 0 ? <p className="quiet">No event yet.</p> : null}
        {items.map((item, i) => <PanelRow key={i} item={item} />)}
      </div>
    </section>
  )
}

const kilobytes = (bytes: number): string => (bytes >= 1_000_000 ? megabytes(bytes) : `${Math.max(1, Math.round(bytes / 1000))} KB`)

/* One delivered file: a deck as its pages, a page in a sandboxed frame, anything else as a link. */
function DeliveredFile({ file, now }: { file: Delivered; now: number }): JSX.Element {
  const deck = Boolean(file.path && DECK.test(file.name))
  const thumbs = useThumbs(deck && file.path ? thumbsUrl(file.path) : null)
  return (
    <div className="dfile">
      <div className="dfile-hd">
        <span className="nm">{file.title ?? file.name}</span>
        {file.title ? <code>{file.name}</code> : null}
        {file.size !== null ? <span className="quiet">{kilobytes(file.size)}</span> : null}
        <span className="quiet">turn <code>{file.turn.slice(0, 8)}</code></span>
        {file.modified !== null ? <span className="quiet">kept {ago(now / 1000 - file.modified)} ago</span> : null}
      </div>
      {file.description ? <p className="dfile-desc">{file.description}</p> : null}
      {file.path === null ? (
        <p className="quiet small">Handed over; the worker keeps its copy as the turn closes, and the pages appear then.</p>
      ) : deck ? (
        <>
          <DeckHead label="deck" path={file.path} thumbs={thumbs} />
          {thumbs.pages.length ? (
            <div className="dstrip">
              {thumbs.pages.map((page, i) => (
                <a key={page} href={fileUrl(page)} target="_blank" rel="noreferrer" title={`page ${i + 1}`}>
                  <img src={fileUrl(page)} alt={`${file.name} page ${i + 1}`} loading="lazy" />
                </a>
              ))}
            </div>
          ) : null}
        </>
      ) : (
        <Deliverables paths={[file.path]} />
      )}
    </div>
  )
}

const SHOWN_DELIVERIES = 3

/* What the employee has handed over so far, newest first, before the round is recorded. */
function DeliveredPanel({ files, now }: { files: Delivered[]; now: number }): JSX.Element | null {
  if (!files.length) return null
  const recent = files.slice(0, SHOWN_DELIVERIES)
  const older = files.slice(SHOWN_DELIVERIES)
  return (
    <section className="dpanel" id="live-delivered" aria-label="Delivered files">
      <p className="eyebrow">Delivered files <span className="cnt">{files.length}</span></p>
      {recent.map((file) => <DeliveredFile key={`${file.turn}/${file.name}`} file={file} now={now} />)}
      {older.length ? (
        <Fold className="fold small" summary={`${older.length} earlier file${older.length === 1 ? '' : 's'}`}>
          {() => (
            <ul className="dolder">
              {older.map((file) => (
                <li key={`${file.turn}/${file.name}`}>
                  {file.path ? <a href={fileUrl(file.path)} target="_blank" rel="noreferrer">{file.name}</a> : <span>{file.name}</span>}
                  {file.title ? <span className="quiet"> · {file.title}</span> : null}
                  <span className="quiet"> · turn {file.turn.slice(0, 8)}</span>
                </li>
              ))}
            </ul>
          )}
        </Fold>
      ) : null}
    </section>
  )
}

interface State {
  curator: CuratorProgress | null
  /** Copies of delivered files the worker has kept, newest first. */
  kept: KeptFile[]
  events: CuratorEvent[]
  /** The logs followed at the last poll, with where each was read to; null before the first answer. */
  logs: LiveLog[] | null
  /** Where the page began reading each log, when that was not its start. */
  starts: Record<string, number>
  rows: RecordRow[]
  phase: Phase | null
  lastEvent: number | null
  /** Server clock minus page clock, in ms, so "ago" is measured on the server's clock. */
  skew: number
  /** Session names by opaque label (see live.ts namesOf). */
  names: Record<string, string>
  error: string
}

const EMPTY: State = { curator: null, kept: [], events: [], logs: null, starts: {}, rows: [], phase: null, lastEvent: null, skew: 0, names: {}, error: '' }

export function Live({ runId, running }: { runId: string; running: boolean }): JSX.Element {
  const [state, setState] = useState<State>(EMPTY)
  const [clock, setClock] = useState(Date.now())
  const [unseen, setUnseen] = useState(0)
  const root = useRef<HTMLDivElement>(null)
  const follow = useRef(true)
  const current = useRef<State>(EMPTY)

  useEffect(() => {
    let live = true
    let timer: ReturnType<typeof setTimeout> | undefined
    current.current = EMPTY
    follow.current = true
    setState(EMPTY)
    setUnseen(0)
    const poll = async () => {
      const before = current.current
      try {
        const reply = await loadLive(runId, cursorOf(before.logs ?? []))
        if (!live) return
        const progress = reply.curator ?? null
        const same = progress && before.curator && before.curator.started === progress.started
        const starts = { ...before.starts }
        for (const log of reply.logs) if (log.reset) starts[log.file] = log.start
        const names = namesOf(reply.labels ?? {})
        const next: State = {
          curator: progress,
          kept: Array.isArray(reply.deliveries) ? reply.deliveries : before.kept,
          events: !progress ? [] : same ? mergeEvents(before.events, progress.events ?? []) : [...(progress.events ?? [])],
          logs: reply.logs,
          starts,
          rows: merge(before.rows, reply),
          phase: reply.phase,
          lastEvent: reply.last_event,
          skew: reply.now * 1000 - Date.now(),
          names: JSON.stringify(names) === JSON.stringify(before.names) ? before.names : names,
          error: '',
        }
        const grew = next.rows.length - before.rows.length + next.events.length - before.events.length
        if (grew > 0 && !follow.current) setUnseen((count) => count + grew)
        current.current = next
        setState(next)
      } catch (e) {
        if (!live) return
        current.current = { ...before, error: (e as Error).message }
        setState(current.current)
      }
      if (live) timer = setTimeout(poll, running ? RUNNING_POLL : IDLE_POLL)
    }
    poll()
    return () => {
      live = false
      if (timer) clearTimeout(timer)
    }
  }, [runId, running])

  useEffect(() => {
    const tick = setInterval(() => setClock(Date.now()), 1000)
    return () => clearInterval(tick)
  }, [])

  /* Whether the reader sits at the bottom decides whether new turns are followed. */
  useEffect(() => {
    const page = root.current?.closest('.page')
    if (!page) return
    const watch = () => {
      follow.current = page.scrollHeight - page.scrollTop - page.clientHeight < NEAR_BOTTOM
      if (follow.current) setUnseen(0)
    }
    watch()
    page.addEventListener('scroll', watch, { passive: true })
    return () => page.removeEventListener('scroll', watch)
  }, [])

  const turns = useMemo(() => groupTurns(state.rows, state.names), [state.rows, state.names])
  const files = useMemo(() => delivered(state.rows, state.kept), [state.rows, state.kept])

  /* Instant, not the page's smooth scrolling: mid-animation scroll events would read as the reader leaving the bottom. */
  useLayoutEffect(() => {
    const page = root.current?.closest('.page')
    if (page && follow.current) page.scrollTo?.({ top: page.scrollHeight, behavior: 'instant' })
  }, [turns, state.events])

  const now = clock + state.skew
  const phase = state.phase
  const over = stopped(running, phase)
  const stoppedAt = state.lastEvent ? state.lastEvent * 1000 : null
  const latest = Math.max(state.lastEvent ?? 0, state.curator?.updated ?? 0)
  const quiet = latest ? (now - latest * 1000) / 1000 : null
  /* The Curator's work never reaches the worker log, so while it is the latest activity it takes the page. */
  const curating = Boolean(state.curator) && (phase?.name === 'curating' || (state.curator!.updated > (state.lastEvent ?? 0) && phase?.name !== 'trial'))
  const toBottom = () => {
    const page = root.current?.closest('.page')
    follow.current = true
    page?.scrollTo?.({ top: page.scrollHeight, behavior: 'instant' })
    setUnseen(0)
  }
  return (
    <div className={`live${over ? ' over' : ''}`} ref={root}>
      <div className={`live-hd${over ? ` over ${(phase?.name ?? 'finished').replace(/\W+/g, '-')}` : ''}`}>
        <span className={`phase ${(phase?.name ?? 'unknown').replace(/\W+/g, '-')}`}>
          <span className="dot" />{phase?.name ?? 'connecting'}{phase?.stage ? ` · ${phase.stage}` : ''}
        </span>
        {phase ? <span className="rd">{phase.round === 0 ? 'onboarding' : `round ${phase.round}`}</span> : null}
        {quiet !== null ? <span className="ago">last event {ago(quiet)} ago</span> : <span className="ago">no worker log yet</span>}
        <span className="basis" title={phase?.basis ?? ''}>{phase?.basis ?? ''}</span>
        {state.error ? <span className="bad" title={state.error}>polling failed</span> : null}
        {files.length ? (
          <button className="dpill" onClick={() => document.getElementById('live-delivered')?.scrollIntoView({ block: 'start' })} title="Show the delivered files">
            {files.length} delivered
          </button>
        ) : null}
      </div>
      {over ? (
        <p className={`live-stop ${(phase?.name ?? 'finished').replace(/\W+/g, '-')}`}>
          <span className="k">{phase?.name === 'finished' ? 'Run finished' : 'Run stopped'}</span>
          <span>{phase?.name === 'finished' ? 'Nothing below is live any more.' : 'Nothing below is live; nodes and tool calls still open when it stopped are marked interrupted.'}</span>
          {phase?.basis ? <span className="why" title={phase.basis}>{phase.basis}</span> : null}
        </p>
      ) : null}
      {Object.values(state.starts).some((start) => start > 0) ? (
        <p className="quiet small">
          Showing {Object.entries(state.starts).filter(([, start]) => start > 0).map(([file, start]) => `${logLabel(file, state.names)} from ${megabytes(start)}`).join(', ')} on;
          earlier turns of this trial are in the Cultivation view once the round is recorded.
        </p>
      ) : null}
      {state.logs?.length ? (
        <p className="quiet small">
          Following {state.logs.length} worker log{state.logs.length === 1 ? '' : 's'}:{' '}
          {state.logs.map((log, i) => <Fragment key={log.file}>{i ? ', ' : ''}<code title={log.file}>{logLabel(log.file, state.names)}</code></Fragment>)} · {turns.length} turn{turns.length === 1 ? '' : 's'}
        </p>
      ) : null}
      <DeliveredPanel files={files} now={now} />
      {turns.length === 0 && state.logs !== null && !curating ? <p className="quiet">No turn in the worker log yet.</p> : null}
      {state.error && state.logs === null ? (
        <p className="quiet">The server did not answer /api/live ({state.error}). A server started before the live view existed needs a restart of experimental.webui.serve.</p>
      ) : null}
      {curating ? (
        <>
          {turns.length ? (
            <Fold className="fold" summary={`Turns in the worker log (${turns.length})`}>
              {() => turns.map((turn) => <Turn key={turn.id} turn={turn} now={0} runId={runId} over={over} stoppedAt={stoppedAt} names={state.names} />)}
            </Fold>
          ) : null}
          <CuratorPanel progress={state.curator!} events={state.events} now={now} />
        </>
      ) : (
        turns.map((turn) => (
          <div key={turn.id}>
            <Turn turn={turn} now={turn.open && !over ? now : 0} runId={runId} over={over} stoppedAt={stoppedAt} names={state.names} />
          </div>
        ))
      )}
      {unseen > 0 ? <button className="unseen" onClick={toBottom}>New events below</button> : null}
    </div>
  )
}
