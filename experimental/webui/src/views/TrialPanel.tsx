/* The trial panel: one round's trial drawn out beside the cultivation
   conversation, the way ui-web opens a workspace beside the chat. It reads the
   round the reader opened from a trial card; the conversation stays in place
   on the left. Four tabs: the drills as conversations, the playbook graphs, the
   decks beside the previous version's, and the owner's verdicts. */

import { useEffect, useMemo, useState } from 'react'

import { roundVersions } from '../derive'
import { dagRuns, decks, opened, scoredSignals, trialSummary } from '../trial'
import { DeckCompare, Graph, Turn, Verdicts } from './Trials'

import type { Revision } from '../derive'
import type { Run, Scenario } from '../model'
import type { TrialSummary } from '../trial'
import type { JSX } from 'react'

export type TrialTab = 'drills' | 'playbook' | 'decks' | 'verdicts'

function Icon({ d, label }: { d: string; label: string }): JSX.Element {
  return (
    <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" focusable="false" data-icon={label}>
      <path d={d} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

const PREV = 'M10 3.5 5.5 8l4.5 4.5'
const NEXT = 'M6 3.5 10.5 8 6 12.5'
const CLOSE = 'M4 4l8 8M12 4l-8 8'
const EXPAND = 'M9.5 2.5h4v4M6.5 13.5h-4v-4M13.5 2.5 9 7M2.5 13.5 7 9'
const SHRINK = 'M13.5 6.5h-4v-4M2.5 9.5h4v4M9.5 6.5l4-4M6.5 9.5l-4 4'

/** Verdicts at a glance, the same words as the card that opened the panel. */
export function TrialTally({ summary }: { summary: TrialSummary }): JSX.Element {
  const judged = summary.passed + summary.failed + summary.unknown
  return (
    <span className={`ttally ${summary.failed ? 'bad' : judged ? 'good' : 'dim'}`}>
      <span className="dot" />
      {!judged ? 'not judged' : summary.failed ? `${summary.failed} failed` : 'all passed'}
      {summary.redFailed ? <span className="red"> · {summary.redFailed} red line{summary.redFailed === 1 ? '' : 's'}</span> : null}
      {judged ? <span className="rest"> · {summary.passed} passed</span> : null}
    </span>
  )
}

export function TrialPanel({
  run, runId, live, revisions, scenario, round, drill, full, onRound, onDrill, onFull, onClose,
}: {
  run: Run
  runId?: string
  live: boolean
  revisions: Revision[]
  scenario: Scenario
  round: number
  drill: string | null
  full: boolean
  onRound: (round: number) => void
  onDrill: (drill: string) => void
  onFull: (full: boolean) => void
  onClose: () => void
}): JSX.Element {
  const versions = useMemo(() => roundVersions(run, revisions), [run, revisions])
  const count = run.rounds.length
  const chosen = Math.min(Math.max(round, 1), Math.max(count, 1))
  const index = chosen - 1
  const version = versions[index] ?? 'v0'
  const red = useMemo(() => new Set(scenario.criteria.filter((row) => row.severity === 'red_line').map((row) => row.id)), [scenario])
  const summary = trialSummary(run, index, version, red)
  const [tab, setTab] = useState<TrialTab>('drills')

  useEffect(() => {
    if (drill) setTab('drills')
  }, [drill, chosen])
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [onClose])

  const current = run.rounds[index]
  if (!current || !summary) {
    return (
      <aside className="ws trialws" aria-label="Trial">
        <div className="ws-top"><span className="ws-ttl">No trial has run yet.</span><button className="ws-btn" title="Close" onClick={onClose}><Icon d={CLOSE} label="close" /></button></div>
      </aside>
    )
  }
  const names = Object.keys(current.sessions)
  const picked = drill && names.includes(drill) ? drill : names[0] ?? null
  const graphs = Object.entries(current.sessions).flatMap(([name, exchanges]) =>
    exchanges.flatMap((exchange) => dagRuns(exchange.execution.records).map((graph) => ({ name, graph }))),
  )
  const pairs = decks(run, index)
  const seen = new Set(run.rounds.slice(0, index).flatMap((item) => opened(item, scenario.materials)))
  const materials = opened(current, scenario.materials)
  const judged = summary.passed + summary.failed + summary.unknown
  const tabs: { id: TrialTab; label: string; count: string }[] = [
    { id: 'drills', label: 'Conversations', count: String(names.length) },
    { id: 'playbook', label: 'Playbook', count: String(graphs.length) },
    { id: 'decks', label: 'Decks', count: String(pairs.filter((pair) => pair.current).length) },
    { id: 'verdicts', label: 'Verdicts', count: summary.failed ? `${summary.failed}/${judged}` : String(judged) },
  ]
  return (
    <aside className="ws trialws" aria-label={`Round ${chosen} trial`}>
      <div className="ws-top">
        <div className="ws-ttl">
          <span className="eyebrow">Trial · round {chosen} of {count}</span>
          <h2>Round {chosen} <span className="on">on</span> <code className="ver">{version}</code></h2>
          <TrialTally summary={summary} />
        </div>
        <div className="ws-acts">
          <button className="ws-btn" title="Previous round" aria-label="Previous round" disabled={chosen <= 1} onClick={() => onRound(chosen - 1)}><Icon d={PREV} label="previous" /></button>
          <button className="ws-btn" title="Next round" aria-label="Next round" disabled={chosen >= count} onClick={() => onRound(chosen + 1)}><Icon d={NEXT} label="next" /></button>
          <button className="ws-btn" title={full ? 'Back beside the conversation' : 'Take the whole page'} aria-label={full ? 'Shrink' : 'Expand'} onClick={() => onFull(!full)}><Icon d={full ? SHRINK : EXPAND} label="expand" /></button>
          <button className="ws-btn" title="Close (Esc)" aria-label="Close the trial" onClick={onClose}><Icon d={CLOSE} label="close" /></button>
        </div>
      </div>
      <nav className="wseg" role="tablist" aria-label="Trial parts">
        {tabs.map((item) => (
          <button key={item.id} role="tab" aria-selected={tab === item.id} onClick={() => setTab(item.id)}>
            {item.label}<span className={`bdg${item.id === 'verdicts' && summary.failed ? ' bad' : ''}`}>{item.count}</span>
          </button>
        ))}
      </nav>
      <div className="ws-body" key={`${chosen}-${tab}`}>
        {tab === 'drills' ? (
          <div className="ws-sec">
            {materials.length ? (
              <p className="mats light">
                <span className="k">Materials opened</span>
                {materials.map((name) => <code key={name} className={seen.has(name) ? '' : 'new'} title={seen.has(name) ? '' : 'first opened in this trial'}>{name}</code>)}
              </p>
            ) : null}
            {names.length > 1 ? (
              <div className="dpick" role="tablist" aria-label="Drills">
                {summary.drills.map((item) => (
                  <button key={item.name} role="tab" aria-selected={item.name === picked} onClick={() => onDrill(item.name)}>
                    <span className="nm">{item.name}</span>
                    <span className="m">{item.turns} turn{item.turns === 1 ? '' : 's'}</span>
                    {item.interceptions ? <span className="hard" title="Interceptions by the Harness">{item.interceptions}</span> : null}
                    {item.deck ? <span className="deck" title="Delivered a deck">deck</span> : null}
                  </button>
                ))}
              </div>
            ) : null}
            {picked ? (
              <div className="thread">
                {current.sessions[picked].length === 0 ? <p className="quiet">No messages.</p> : null}
                {current.sessions[picked].map((exchange, i) => <Turn key={i} exchange={exchange} drill={picked} version={version} over={!live} />)}
              </div>
            ) : <p className="quiet">No drill ran in this trial.</p>}
          </div>
        ) : null}
        {tab === 'playbook' ? (
          <div className="ws-sec">
            {graphs.length === 0 ? <p className="quiet">No playbook graph ran in this trial.</p> : null}
            {graphs.map(({ name, graph }) => <Graph key={graph.id} graph={graph} drill={name} runId={runId} over={!live} />)}
          </div>
        ) : null}
        {tab === 'decks' ? (
          <div className="ws-sec">
            {pairs.length === 0 ? <p className="quiet">No drill delivered a deck in this trial or before it.</p> : null}
            {pairs.map((pair) => (
              <DeckCompare
                key={pair.session}
                session={pair.session}
                current={pair.current}
                previous={pair.previous}
                version={version}
                previousVersion={pair.previous ? versions[pair.previous.round - 1] : ''}
              />
            ))}
          </div>
        ) : null}
        {tab === 'verdicts' ? (
          <div className="ws-sec">
            <Verdicts signals={scoredSignals(current)} scenario={scenario} failedFirst />
          </div>
        ) : null}
      </div>
    </aside>
  )
}
