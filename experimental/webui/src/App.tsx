import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { NO_SCENARIO, listRuns, loadRun, loadScenario } from './api'
import { revisions, roundVersions, trialsOf } from './derive'
import { VERDICT_LABEL, modelLine } from './record'
import { Compare } from './views/Compare'
import { Cultivation } from './views/Cultivation'
import { HarnessView } from './views/Harness'
import { Live } from './views/Live'
import { RecordView } from './views/Record'
import { RevisionRail } from './views/RevisionRail'
import { TrialPanel } from './views/TrialPanel'

import type { Revision } from './derive'
import type { Run, RunEntry, RunStatus, Scenario } from './model'
import type { CSSProperties, JSX, PointerEvent as ReactPointerEvent } from 'react'

const STATUS_LABEL: Record<RunStatus, string> = {
  running: 'running',
  finished: 'finished',
  paused: 'paused on the Curator budget',
  error: 'ended with an error',
  stalled: 'stalled or stopped',
}

export type View = 'live' | 'cultivation' | 'harness' | 'record'

const VIEWS: { id: View; label: string }[] = [
  { id: 'live', label: 'Live' },
  { id: 'cultivation', label: 'Cultivation' },
  { id: 'harness', label: 'Harness' },
  { id: 'record', label: 'Record' },
]

/** A run is named by its folder; its chain, the arm, each round's passed/judged checks and its models follow. */
export function entryLabel(entry: RunEntry): string {
  const arm = entry.curator === 'untouched' ? 'control' : 'Curator'
  const scores = entry.passes.map(([pass, fail]) => `${pass}/${pass + fail}`).join(' → ')
  const state = entry.stopped
    ? ' · stopped by the suite'
    : entry.status === 'finished' ? '' : ` · ${entry.status === 'stalled' ? 'stalled or stopped' : entry.status}`
  const models = modelLine(entry.models, true)
  const verdict = entry.verdict ? ` · ${VERDICT_LABEL[entry.verdict] ?? entry.verdict}${typeof entry.score === 'number' ? ` ${entry.score}` : ''}` : ''
  return `${entry.name}${entry.chain ? ` · ${entry.chain}` : ''} · ${arm}${scores ? ` · ${scores}` : ''}${models ? ` · ${models}` : ''}${verdict}${state}`
}

/** The full stop reason and models of a run, for the run list's hover text. */
export const entryTitle = (entry: RunEntry): string =>
  [modelLine(entry.models), entry.stopped ? `Stopped: ${entry.stopped}` : '', entry.error ?? ''].filter(Boolean).join('\n')

/** Current runs first, then archived ones (folders named archive-...). */
export function groups(entries: RunEntry[]): [string, RunEntry[]][] {
  const current = entries.filter((entry) => !entry.name.startsWith('archive-'))
  const archived = entries.filter((entry) => entry.name.startsWith('archive-'))
  return ([['Runs', current], ['Archive', archived]] as [string, RunEntry[]][]).filter(([, rows]) => rows.length)
}

const roundOf = (value: string | undefined): number | null => {
  const number = Number(value)
  return value && Number.isInteger(number) && number > 0 ? number : null
}

/** The view and the trial open beside the conversation that a location hash names (#live, #cultivation,
    #cultivation/trial/2, #harness, #record); the older #trials/2 opens that trial too. `chosen` is false without one. */
export function parseHash(hash: string): { view: View; round: number | null; chosen: boolean } {
  const [name, second, third] = hash.replace(/^#\/?/, '').split('/')
  if (name === 'trials') return { view: 'cultivation', round: roundOf(second), chosen: true }
  const chosen = VIEWS.some((item) => item.id === name)
  const view = chosen ? (name as View) : 'cultivation'
  return { view, round: view === 'cultivation' && second === 'trial' ? roundOf(third) : null, chosen }
}

const hashOf = (view: View, round: number | null): string => (view === 'cultivation' && round ? `#cultivation/trial/${round}` : `#${view}`)

const PANEL_KEY = 'rsi-runs.trial-panel-width'
const PANEL_MIN = 420
const CHAT_MIN = 480

function storedWidth(): number {
  try {
    const value = Number(window.localStorage.getItem(PANEL_KEY))
    if (Number.isFinite(value) && value >= PANEL_MIN) return value
  } catch {
    /* storage refused: the default width stands */
  }
  return Math.round(Math.min(Math.max(window.innerWidth * 0.5, PANEL_MIN), 860))
}

const clampWidth = (width: number): number => Math.round(Math.max(PANEL_MIN, Math.min(width, window.innerWidth - CHAT_MIN)))

export function App(): JSX.Element {
  const [entries, setEntries] = useState<RunEntry[] | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [run, setRun] = useState<Run | null>(null)
  const [error, setError] = useState('')
  const [against, setAgainst] = useState('')
  const [other, setOther] = useState<Run | null>(null)
  const [scenario, setScenario] = useState<Scenario>(NO_SCENARIO)
  const [place, setPlace] = useState(() => parseHash(window.location.hash))
  const [shown, setShown] = useState<string | null>(null)
  const [refreshed, setRefreshed] = useState<number | null>(null)
  const [drill, setDrill] = useState<string | null>(null)
  const [full, setFull] = useState(false)
  const [width, setWidth] = useState(storedWidth)
  const [dragging, setDragging] = useState(false)
  /* Set once the reader picks a run themselves; until then the page follows the newest running run. */
  const picked = useRef(false)

  useEffect(() => {
    listRuns()
      .then((rows) => {
        setEntries(rows)
        if (rows.length && !selected) setSelected(rows[0].id)
      })
      .catch((e: Error) => setError(e.message))
    loadScenario().then(setScenario)
    const follow = () => setPlace(parseHash(window.location.hash))
    window.addEventListener('hashchange', follow)
    return () => window.removeEventListener('hashchange', follow)
  }, [])

  useEffect(() => {
    if (!selected) return
    setRun(null)
    setShown(null)
    loadRun(selected)
      .then((loaded) => {
        setRun(loaded)
        setRefreshed(Date.now())
      })
      .catch((e: Error) => setError(e.message))
  }, [selected])

  /* A run that is still going is re-read every few seconds, so the views grow
     while the loop runs; the list is re-read more slowly for runs that appear. */
  /* The run list knows when a record that says running has had no write for long; that reading wins. */
  const listed = entries?.find((entry) => entry.id === selected)?.status
  const status: RunStatus = listed === 'stalled' && run?.status === 'running' ? 'stalled' : run?.status ?? 'finished'
  useEffect(() => {
    if (!selected || status !== 'running') return
    const timer = setInterval(() => {
      loadRun(selected)
        .then((loaded) => {
          setRun(loaded)
          setRefreshed(Date.now())
        })
        .catch(() => undefined)
    }, 3000)
    return () => clearInterval(timer)
  }, [selected, status])
  useEffect(() => {
    const timer = setInterval(() => {
      listRuns()
        .then((rows) => {
          setEntries(rows)
          const newest = rows.find((row) => row.status === 'running')
          if (!newest || picked.current) return
          setSelected((current) => {
            const now = rows.find((row) => row.id === current)
            return !now || now.status !== 'running' ? newest.id : current
          })
        })
        .catch(() => undefined)
    }, 10000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    if (!against) {
      setOther(null)
      return
    }
    loadRun(against)
      .then(setOther)
      .catch((e: Error) => setError(e.message))
  }, [against])

  const revs = useMemo(() => (run ? revisions(run) : []), [run])
  const versions = useMemo(() => (run ? roundVersions(run, revs) : []), [run, revs])
  const active = [...revs].reverse().find((rev) => rev.deployed)?.label ?? 'v0'
  /* A running run opens on the live view unless the address names another. */
  const view: View = place.chosen ? place.view : status === 'running' ? 'live' : 'cultivation'
  const panel = view === 'cultivation' && place.round !== null && Boolean(run?.rounds.length)
  const loaded = Boolean(run)
  /* A trial named by the address, or opened from elsewhere, brings its card into view once the run is on the page. */
  useEffect(() => {
    if (!loaded || view !== 'cultivation' || place.round === null) return
    requestAnimationFrame(() => requestAnimationFrame(() => document.getElementById(`trial-${place.round}`)?.scrollIntoView?.({ block: 'nearest' })))
  }, [loaded, view, place.round])

  const go = (view: View, round: number | null = null): void => {
    const next = hashOf(view, round)
    if (window.location.hash !== next) window.history.pushState(null, '', next)
    setPlace({ view, round: view === 'cultivation' ? round : null, chosen: true })
  }
  const reveal = (anchor: string): void => {
    requestAnimationFrame(() => requestAnimationFrame(() => document.getElementById(anchor)?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' })))
  }
  /* Opening a trial keeps the reader in the conversation: the card that stands for it comes into view on the left
     and the trial is drawn out on the right. */
  const trial = (round: number, name?: string): void => {
    setShown(versions[round - 1] ?? null)
    setDrill(name ?? null)
    go('cultivation', round)
    reveal(`trial-${round}`)
  }
  const closeTrial = useCallback((): void => {
    setFull(false)
    const next = hashOf('cultivation', null)
    if (window.location.hash !== next) window.history.pushState(null, '', next)
    setPlace({ view: 'cultivation', round: null, chosen: true })
  }, [])
  const open = (revision: Revision | null): void => {
    const label = revision ? revision.label : 'v0'
    setShown(label)
    const round = trialsOf(label, versions)[0]
    go('cultivation', place.round !== null && round ? round : null)
    reveal(revision ? `reply-${revision.key}` : 'remark-1')
  }
  const drag = (event: ReactPointerEvent<HTMLButtonElement>): void => {
    event.preventDefault()
    const grip = event.currentTarget
    grip.setPointerCapture?.(event.pointerId)
    setDragging(true)
    const move = (next: PointerEvent) => setWidth(clampWidth(window.innerWidth - next.clientX))
    const stop = () => {
      grip.removeEventListener('pointermove', move)
      grip.removeEventListener('pointerup', stop)
      grip.removeEventListener('pointercancel', stop)
      setDragging(false)
      setWidth((value) => {
        try {
          window.localStorage.setItem(PANEL_KEY, String(value))
        } catch {
          /* storage refused: the width lasts for this visit */
        }
        return value
      })
    }
    grip.addEventListener('pointermove', move)
    grip.addEventListener('pointerup', stop)
    grip.addEventListener('pointercancel', stop)
  }
  const remark = (round: number): void => {
    go('cultivation')
    requestAnimationFrame(() => requestAnimationFrame(() => document.getElementById(`remark-${round}`)?.scrollIntoView({ block: 'start', behavior: 'smooth' })))
  }
  const compare = (id: string): void => {
    setAgainst(id)
    if (id) go('harness')
  }
  const name = (selected ?? '').split('/')[0]
  const newer = entries?.find((entry) => entry.status === 'running' && entry.id !== selected) ?? null
  const choose = (id: string): void => {
    picked.current = true
    setSelected(id)
  }

  return (
    <div className="app">
      <header className="topbar">
        <span className="wordmark">RSI Runs</span>
        <label className="picker">
          <span className="sr">Run</span>
          <select value={selected ?? ''} onChange={(e) => choose(e.target.value)} disabled={!entries?.length}>
            {entries?.length === 0 ? <option value="">No recorded runs</option> : null}
            {groups(entries ?? []).map(([group, rows]) => (
              <optgroup key={group} label={group}>
                {rows.map((entry) => (
                  <option key={entry.id} value={entry.id} title={entryTitle(entry)}>{entryLabel(entry)}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        <nav className="views" role="tablist" aria-label="Views">
          {VIEWS.map((item) => (
            <button key={item.id} role="tab" aria-selected={view === item.id} className={view === item.id ? 'active' : ''} onClick={() => go(item.id)}>
              {item.id === 'live' && status === 'running' ? <span className="dot live-dot" /> : null}
              {item.label}
            </button>
          ))}
        </nav>
        <span className="grow" />
        <label className="picker vs">
          <span className="sr">Compare with</span>
          <select value={against} onChange={(e) => compare(e.target.value)} disabled={!entries?.length} title="Compare this run with another arm, shown in the Harness view">
            <option value="">no comparison</option>
            {groups((entries ?? []).filter((entry) => entry.id !== selected)).map(([group, rows]) => (
              <optgroup key={group} label={group}>
                {rows.map((entry) => (
                  <option key={entry.id} value={entry.id}>vs {entryLabel(entry)}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        {run ? (
          <span className={`status ${status}`} title={run.stop ?? run.error ?? ''}>
            <span className="dot" />
            {STATUS_LABEL[status]}
            {run.curator === 'untouched' ? ' · control arm' : ''}
            {` · on ${active}`}
          </span>
        ) : null}
        {status === 'running' && refreshed ? (
          <span className="refreshed" title="The page re-reads a running run every 3 seconds and the run list every 10 seconds">
            auto-updating · {new Date(refreshed).toLocaleTimeString()}
          </span>
        ) : null}
      </header>
      {error ? <p className="bad pad">{error}</p> : null}
      {newer && status !== 'running' ? (
        <p className="notice">
          A newer run is going: {newer.name}. <button onClick={() => choose(newer.id)}>Open it</button>
        </p>
      ) : null}
      {run && view === 'cultivation' && status === 'running' ? (
        <p className="notice">
          This run is still going; Live shows what the employee and the Curator are doing right now.{' '}
          <button onClick={() => go('live')}>Open Live</button>
        </p>
      ) : null}
      {run ? <RevisionRail revisions={revs} versions={versions} shown={shown} onOpen={open} /> : null}
      <div
        className="split"
        data-open={panel ? 'true' : 'false'}
        data-full={panel && full ? 'true' : 'false'}
        data-drag={dragging ? 'true' : 'false'}
        style={{ '--wsw': `${width}px` } as CSSProperties}
      >
      <main className="page">
        {selected && !run && !error ? <p className="quiet pad">Loading run...</p> : null}
        {run && selected && view === 'live' ? <Live runId={selected} running={status === 'running'} /> : null}
        {run && view === 'cultivation' ? <Cultivation run={run} runId={selected ?? ''} name={name} revisions={revs} scenario={scenario} trial={panel ? place.round : null} onTrial={trial} /> : null}
        {run && selected && view === 'record' ? (
          <RecordView
            runId={selected}
            entry={entries?.find((entry) => entry.id === selected)}
            live={status === 'running'}
            onTrial={trial}
            onRemark={remark}
            onOpenRun={(runName) => {
              const target = entries?.find((entry) => entry.name === runName)
              if (target) choose(target.id)
            }}
          />
        ) : null}
        {run && view === 'harness' ? (
          <div className="harness-wrap">
            {other ? <Compare left={other} right={run} /> : null}
            <HarnessView run={run} runId={selected ?? undefined} revisions={revs} scenario={scenario} />
          </div>
        ) : null}
      </main>
      {panel && run ? (
        <div className="ws-wrap">
          <button className="grip" aria-label="Drag to resize the trial panel" title="Drag to resize" data-drag={dragging ? 'true' : 'false'} onPointerDown={drag} />
          <TrialPanel
            run={run}
            runId={selected ?? undefined}
            live={status === 'running'}
            revisions={revs}
            scenario={scenario}
            round={place.round!}
            drill={drill}
            full={full}
            onRound={(round) => trial(round)}
            onDrill={setDrill}
            onFull={setFull}
            onClose={closeTrial}
          />
        </div>
      ) : null}
      </div>
    </div>
  )
}
