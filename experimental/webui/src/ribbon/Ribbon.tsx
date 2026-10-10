/* The ribbon page: a recorded run as a route in the left column, the chosen
   part of it in the panel on the right. It reads the Studio's run endpoints and
   its replayed thread, so it shows exactly what /studio shows, laid out by
   version instead of as one transcript; /studio stays as it is. A run still
   going is read again every twenty seconds. */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { listRuns, loadStudioRun } from '../studio/api'
import { replayThread } from '../studio/replay'
import { RavenMark } from '../studio/views/bits'
import { Chat, messagesOf, stageOf } from './Chat'
import { Detail } from './Detail'
import { focusOf } from './layout'
import { routeOf } from './route'
import { RouteView } from './RouteView'

import type { JSX } from 'react'
import type { Run, RunEntry } from '../model'
import type { Thread } from '../studio/types'
import type { Tab } from './layout'

const REFRESH = 20000
const STATUS: Record<string, string> = {
  running: 'Running',
  finished: 'Finished',
  paused: 'Paused',
  stopped: 'Stopped',
  error: 'Error',
  stalled: 'Stalled',
  incomplete: 'Incomplete',
  needs_input: 'Needs input',
}

function initial(): string | null {
  return new URLSearchParams(window.location.search).get('run')
}

export function Ribbon(): JSX.Element {
  const [runs, setRuns] = useState<RunEntry[]>([])
  const [id, setId] = useState<string | null>(initial)
  const [thread, setThread] = useState<Thread | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab | null>(null)

  const known = useRef<RunEntry[]>([])
  useEffect(() => {
    listRuns().then(
      (rows) => {
        known.current = rows
        setRuns(rows)
      },
      (failure: Error) => setError(failure.message),
    )
  }, [])
  useEffect(() => {
    if (!id && runs.length) setId((runs.find((run) => run.status === 'running') ?? runs[0]).id)
  }, [id, runs])

  const load = useCallback(
    (run: string) =>
      loadStudioRun(run).then(
        (data: Run) => {
          setThread(replayThread(run, data, known.current.find((row) => row.id === run)))
          setError(null)
        },
        (failure: Error) => setError(failure.message),
      ),
    [],
  )
  useEffect(() => {
    if (!id) return
    setThread(null)
    setSelected(null)
    setTab(null)
    load(id)
    const url = new URL(window.location.href)
    url.searchParams.set('run', id)
    window.history.replaceState(null, '', url)
  }, [id, load])

  const route = useMemo(() => (thread ? routeOf(thread) : null), [thread])
  useEffect(() => {
    if (!id || !route?.live) return
    const timer = window.setInterval(() => load(id), REFRESH)
    return () => window.clearInterval(timer)
  }, [id, route?.live, load])

  const focus = route ? focusOf(route, selected) : null
  const messages = useMemo(() => (route ? messagesOf(route) : []), [route])
  const stage = route && focus ? stageOf(route, messages, tab ? null : selected, tab ?? focus.tab, focus.leg) : null
  const choose = useCallback((key: string | null) => {
    setSelected(key)
    setTab(null)
  }, [])
  const entry = runs.find((run) => run.id === id)
  return (
    <div className="rb-app">
      <header className="rb-top">
        <RavenMark size={20} />
        <h1>{thread?.title ?? entry?.name ?? 'Cultivation route'}</h1>
        {entry && <span className={`rb-status rb-${entry.status}`}>{STATUS[entry.status] ?? entry.status}</span>}
        <span className="grow" />
        <select className="rb-pick" value={id ?? ''} onChange={(event) => setId(event.target.value)} aria-label="Choose a run">
          {runs.map((run) => (
            <option key={run.id} value={run.id}>{run.name}</option>
          ))}
        </select>
        <a className="rb-link" href={`/studio${id ? `?run=${encodeURIComponent(id)}` : ''}`}>Classic view</a>
      </header>
      <main className="rb-main">
        <section className="rb-left">
          {error && <p className="rb-error">{error}</p>}
          {!route && !error && <p className="rb-quiet rb-pad">Loading...</p>}
          {route && (
            <>
              <RouteView route={route} seed={id ?? ''} selected={selected} onSelect={choose} />
              <div className="rb-legend">
                {['memory', 'planning', 'capability', 'action'].map((name) => (
                  <span key={name}><i className={`rb-sw rb-${name}`} />{name}</span>
                ))}
                <span><i className="rb-sw rb-native" />native</span>
              </div>
              <Chat messages={messages} route={route} focus={selected ? focus!.leg : null} selected={selected} onSelect={choose} />
            </>
          )}
        </section>
        {route && focus && stage && id && (
          <Detail route={route} run={id} leg={focus.leg} tab={tab ?? focus.tab} trial={focus.trial} stage={stage} onTab={setTab} />
        )}
      </main>
    </div>
  )
}
