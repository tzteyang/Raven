/* The Studio's rail, in ui-web's rail grammar: when the server keeps live
   sessions, the new-session action, the live sessions and the archived agents;
   then the recorded automated runs, one row each. */

import { useState } from 'react'

import { T } from '../copy'
import { Icon, RavenMark } from './bits'

import type { JSX, ReactNode } from 'react'
import type { RunEntry } from '../../model'
import type { LiveSession } from '../live'

export type Selected = { kind: 'live'; id: string } | { kind: 'run'; id: string } | null

const SHOWN = 12

function Group({ label, children }: { label: string; children: ReactNode }): JSX.Element {
  return (
    <>
      <div className="grp" data-empty><span className="lab">{label}</span></div>
      {children}
    </>
  )
}

/** A live session's row: busy while a step runs, its version once its record is read. */
function LiveRow({ session, current, onSelect }: { session: LiveSession; current: boolean; onSelect: () => void }): JSX.Element {
  const busy = session.summary.attached && !!(session.state?.step ?? session.summary.step)
  const version = session.archived?.version ?? (session.run ? session.current : '')
  return (
    <div className="sess" role="button" tabIndex={0} aria-current={current} onClick={onSelect} title={T.statuses[session.status] ?? session.status}>
      <div className="t">
        {session.archived ? <Icon name="archive" size={13} /> : busy ? <i className="dot run" /> : null}
        <span>{session.archived?.name ?? session.title}</span>
      </div>
      <span className="w"><span className="wt st-mono">{version}</span></span>
    </div>
  )
}

export function Rail({ live, runs, loading, selected, onSelect, onNew }: {
  /** The live sessions, or null when the server keeps none. */
  live: LiveSession[] | null
  runs: RunEntry[]
  loading: boolean
  selected: Selected
  onSelect: (selected: Selected) => void
  onNew: () => void
}): JSX.Element {
  const [all, setAll] = useState(false)
  const active = (live ?? []).filter((session) => !session.archived)
  const archived = (live ?? []).filter((session) => session.archived)
  const shown = all ? runs : runs.slice(0, SHOWN)
  const is = (kind: 'live' | 'run', id: string) => selected?.kind === kind && selected.id === id
  return (
    <aside className="rail">
      <div className="railtop">
        <span className="wordmark"><RavenMark />RAVEN<span className="st-sub">{T.product}</span></span>
      </div>
      {live && (
        <nav className="rail-nav">
          <button type="button" className="navi newrun" onClick={onNew}><Icon name="plus" /><span>{T.newSession}</span></button>
        </nav>
      )}
      <div className="list">
        {live && (
          <Group label={T.groupLive}>
            {active.length === 0 ? (
              <p className="st-railempty">{T.emptyLive}</p>
            ) : (
              active.map((session) => <LiveRow key={session.id} session={session} current={is('live', session.id)} onSelect={() => onSelect({ kind: 'live', id: session.id })} />)
            )}
          </Group>
        )}
        {archived.length > 0 && (
          <Group label={T.groupArchived}>
            {archived.map((session) => <LiveRow key={session.id} session={session} current={is('live', session.id)} onSelect={() => onSelect({ kind: 'live', id: session.id })} />)}
          </Group>
        )}
        <Group label={T.groupRuns}>
          {loading ? <p className="st-railempty">{T.loadingRuns}</p> : <></>}
          {shown.map((run) => (
            <div key={run.id} className="sess" role="button" tabIndex={0} aria-current={is('run', run.id)} onClick={() => onSelect({ kind: 'run', id: run.id })} title={`${run.name} · ${T.statuses[run.status] ?? run.status}`}>
              <div className="t"><i className={`st-led ${run.status}`} /><span>{run.name}</span></div>
              <span className="w"><span className="wt st-mono">{run.rounds}r</span></span>
            </div>
          ))}
        </Group>
        {runs.length > SHOWN && (
          <button type="button" className="grp-more" onClick={() => setAll(!all)}>{all ? T.fewerRuns : T.moreRuns(runs.length - SHOWN)}</button>
        )}
      </div>
    </aside>
  )
}
