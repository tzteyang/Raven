/* Trials in two levels, the way ui-web lists a session's sub-agent tasks: a
   list (in the transcript under the version they tried, and as a popover
   from the pill above the composer) and, once a trial is picked, its whole
   process in the side pane -- each turn's tool calls, the mechanisms that
   stepped in (mechanisms.ts), playbook runs and sub-harnesses, the model
   inputs, the reply and what was delivered. */

import { useEffect, useRef, useState } from 'react'

import { dagRuns, replyText, timedOut } from '../../trial'
import { fileUrl, loadRaw } from '../api'
import { T } from '../copy'
import { interventions, modelInputs, turnEvents } from '../mechanisms'
import { Icon, Json, Markdown, fileName } from './bits'

import type { JSX } from 'react'
import type { Exchange, RecordRow } from '../../model'
import type { RawRef } from '../api'
import type { TurnEvent } from '../mechanisms'
import type { TrialView, TrialsEntry } from '../types'

type Row = RecordRow & Record<string, unknown>

const obj = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}

export interface TrialStats {
  turns: number
  deliverables: number
  interceptions: number
  playbooks: number
}

const childRecords = (records: RecordRow[]): { harness: string; records: RecordRow[] }[] =>
  (records as Row[])
    .filter((row) => row.kind === 'child.execution')
    .map((row) => ({ harness: String(row['harness'] ?? ''), records: Array.isArray(row['records']) ? (row['records'] as RecordRow[]) : [] }))

/** Interventions of one turn, in the root harness and in each sub-harness it ran. */
const turnInterventions = (records: RecordRow[]): number =>
  interventions(turnEvents(records)) + childRecords(records).reduce((sum, child) => sum + interventions(turnEvents(child.records)), 0)

export function stats(trial: TrialView): TrialStats {
  const records = trial.exchanges.flatMap((exchange) => exchange.execution.records)
  return {
    turns: trial.exchanges.length,
    deliverables: trial.exchanges.reduce((sum, exchange) => sum + (exchange.execution.deliverables?.length ?? 0), 0),
    interceptions: trial.exchanges.reduce((sum, exchange) => sum + turnInterventions(exchange.execution.records), 0),
    playbooks: dagRuns(records).length,
  }
}

function meta(trial: TrialView): string {
  const s = stats(trial)
  return [T.trialTurns(s.turns), s.deliverables ? T.trialDeliverables(s.deliverables) : '', s.interceptions ? T.trialInterceptions(s.interceptions) : '', s.playbooks ? T.trialPlaybooks(s.playbooks) : '']
    .filter(Boolean)
    .join(' · ')
}

const firstUser = (trial: TrialView): string => trial.exchanges[0]?.user ?? ''

export function TrialRow({ trial, active, onOpen }: { trial: TrialView; active: boolean; onOpen: () => void }): JSX.Element {
  const running = trial.status === 'running'
  return (
    <button type="button" className="sarow task st-trow" data-st={running ? 'run' : 'ok'} aria-current={active} onClick={onOpen}>
      <span className={`dot ${running ? 'run' : 'ok'}`} />
      <div className="bd">
        <div className="tline">
          <span className="nm">{trial.title}</span>
          <code className="st-vtag">{trial.version}</code>
          {trial.holdout && <span className="st-tag st-heldout">{T.heldOutTag}</span>}
        </div>
        {firstUser(trial) && <span className="st-first">{firstUser(trial)}</span>}
        <s className="st">{meta(trial)}</s>
      </div>
    </button>
  )
}

export function TrialsCard({ entry, live, current, activeTrial, onOpen, onNew }: {
  entry: TrialsEntry
  live: boolean
  current: string
  activeTrial: string | null
  onOpen: (id: string) => void
  onNew?: () => void
}): JSX.Element {
  const title = entry.holdout
    ? T.trialsHeldOut(entry.version, entry.trials.length)
    : entry.pending
      ? T.trialsPending(entry.round, entry.trials.length)
      : T.trialsOn(entry.version, entry.trials.length)
  return (
    <section className="st-card st-trials" id={`trials-${entry.key}`} data-holdout={entry.holdout || undefined}>
      <header className="st-card-h">
        <Icon name={entry.holdout ? 'shield' : 'flask'} size={13} />
        <span className="st-kicker">{title}</span>
        {entry.holdout && <span className="st-tag st-heldout" title={T.heldOutNote}>{T.heldOutTag}</span>}
        {entry.pending && <span className="st-tag live">{T.trialRunning}</span>}
        <span className="grow" />
        {live && onNew && entry.version === current && !entry.holdout && (
          <button type="button" className="st-link" onClick={onNew}><Icon name="plus" size={13} />{T.openTrial}</button>
        )}
      </header>
      {entry.holdout && <p className="st-quiet">{T.heldOutNote}</p>}
      <div className="salist tasks st-tlist">
        {entry.trials.map((trial) => <TrialRow key={trial.id} trial={trial} active={trial.id === activeTrial} onOpen={() => onOpen(trial.id)} />)}
      </div>
    </section>
  )
}

export function TrialList({ trials, activeTrial, onOpen, onClose }: { trials: TrialView[]; activeTrial: string | null; onOpen: (id: string) => void; onClose: () => void }): JSX.Element {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const away = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node) && !(event.target as HTMLElement).closest('[data-trial-toggle]')) onClose()
    }
    const key = (event: KeyboardEvent) => event.key === 'Escape' && onClose()
    document.addEventListener('mousedown', away)
    document.addEventListener('keydown', key)
    return () => {
      document.removeEventListener('mousedown', away)
      document.removeEventListener('keydown', key)
    }
  }, [onClose])
  const running = trials.filter((trial) => trial.status === 'running')
  const done = trials.filter((trial) => trial.status !== 'running')
  return (
    <div className="st-pop" ref={ref} role="dialog" aria-label={T.trialsAll(trials.length)}>
      <div className="salist tasks">
        {trials.length === 0 && <p className="tkempty st-empty">{T.trialNone}</p>}
        {running.length > 0 && <div className="wsgrp">{T.trialRunning}</div>}
        {running.map((trial) => <TrialRow key={trial.id} trial={trial} active={trial.id === activeTrial} onOpen={() => onOpen(trial.id)} />)}
        {done.length > 0 && <div className="wsgrp">{T.trialDone}</div>}
        {[...done].reverse().map((trial) => <TrialRow key={trial.id} trial={trial} active={trial.id === activeTrial} onOpen={() => onOpen(trial.id)} />)}
      </div>
    </div>
  )
}

function RawInput({ run, reference }: { run: string; reference: RawRef }): JSX.Element {
  const [state, setState] = useState<{ value?: unknown; error?: string; loading?: boolean }>({})
  const load = () => {
    setState({ loading: true })
    loadRaw(run, reference).then(
      (value) => setState({ value }),
      (error: Error) => setState({ error: error.message }),
    )
  }
  if (state.value !== undefined) {
    const value = obj(state.value)
    return <Json value={obj(value.parameters).messages ?? value.messages ?? state.value} max={420} />
  }
  return (
    <button type="button" className="st-link" onClick={load} disabled={state.loading}>
      {state.loading ? T.loading : state.error ? `${T.loadFailed}: ${state.error}` : T.loadRaw}
    </button>
  )
}

function Mechanism({ event }: { event: TurnEvent }): JSX.Element {
  switch (event.kind) {
    case 'control': {
      const { control } = event
      const applied = control.status === 'applied'
      return (
        <p className={`st-act ${applied ? 'hit' : 'st-muted'}`} data-status={control.status}>
          <Icon name="shield" size={13} />
          <b>{T.control[control.control] ?? control.control}</b>
          <code>{['action', control.on, control.tool].filter(Boolean).join(' · ')}</code>
          <em className="st-cstatus">{T.controlStatus[control.status] ?? control.status}</em>
          {(control.detail || control.reason) && <span>{control.detail || control.reason}</span>}
        </p>
      )
    }
    case 'refusal':
      return (
        <p className="st-act hit">
          <Icon name="shield" size={13} />
          <b>{T.intercept[event.hit.kind] ?? event.hit.kind}</b>
          <code>{event.hit.mechanism}{event.hit.tool ? ` · ${event.hit.tool}` : ''}</code>
          <span>{event.hit.reason}</span>
        </p>
      )
    case 'guidance':
      return (
        <p className="st-act">
          <Icon name="spark" size={13} />
          <b>{T.guidance[event.source]}</b>
          <span>{event.text}</span>
        </p>
      )
    case 'peer':
      return (
        <p className="st-act">
          <Icon name="link" size={13} />
          <b>{T.peer(event.target, event.operation)}</b>
          <code>{event.request}</code>
          <span>→ {event.result}</span>
        </p>
      )
    case 'select':
      return (
        <p className="st-act">
          <Icon name="tool" size={13} />
          <b>{T.selected(event.count)}</b>
          <span>{T.selectedTools(event.tools)}; {T.selectedSkills(event.skills)}</span>
        </p>
      )
    case 'register':
      return (
        <p className="st-act">
          <Icon name="plus" size={13} />
          <b>{T.registered(event.what, event.name)}</b>
          <code>{event.status}</code>
          {event.reason && <span>{event.reason}</span>}
        </p>
      )
    case 'memory':
      return (
        <p className="st-act">
          <Icon name="layers" size={13} />
          <b>{T.memoryOp[event.operation] ?? `memory.${event.operation}`}</b>
          <span>{event.summary}</span>
        </p>
      )
    case 'error':
      return (
        <p className="st-act hit">
          <Icon name="alert" size={13} />
          <b>{T.strategyError}</b>
          <code>{event.source}</code>
          <span>{event.text}</span>
        </p>
      )
  }
}

function Activity({ exchange, run }: { exchange: Exchange; run: string | null }): JSX.Element | null {
  const records = exchange.execution.records as Row[]
  const tools = records
    .filter((row) => row.kind === 'runner.event' && row['event_type'] === 'ToolEvent' && obj(row['event']).phase === 'start')
    .map((row) => String(obj(row['event']).name ?? ''))
    .filter(Boolean)
  const inputs = modelInputs(records)
  const assembled = inputs.some((input) => input.row.kind === 'model.input')
  const children = childRecords(records).map((child) => ({ ...child, events: turnEvents(child.records) }))
  const events = turnEvents(records)
  const graphs = dagRuns(records)
  if (!tools.length && !inputs.length && !children.length && !events.length && !graphs.length) return null
  return (
    <div className="st-acts">
      {tools.length > 0 && <p className="st-act"><Icon name="tool" size={13} />{T.tools(tools)}</p>}
      {events.map((event, i) => <Mechanism key={i} event={event} />)}
      {graphs.map((graph) => (
        <div key={graph.id} className="st-act st-dagrow">
          <Icon name="graph" size={13} />
          <span>{graph.summary ?? graph.id}</span>
          <span className="st-dagnodes">
            {graph.nodes.map((node) => (
              <span key={node.id} className="st-dagnode" data-st={node.status}>{node.summary ?? node.id}<small>{node.subagent}</small></span>
            ))}
          </span>
        </div>
      ))}
      {children.length > 0 && <p className="st-act"><Icon name="layers" size={13} />{T.childRuns(children.map((child) => child.harness))}</p>}
      {children.map((child, c) => child.events.map((event, i) => (
        <div key={`${c}-${i}`} className="st-child"><Mechanism event={event} /></div>
      )))}
      {inputs.length > 0 && (
        <details className="st-fold st-raw">
          <summary><Icon name="cpu" size={13} />{T.modelCalls(inputs.length)} · {assembled ? T.modelInput : T.rawInput}</summary>
          <div className="st-fold-b">
            {inputs.map(({ row, tokens, allowance }, i) => (
              <div key={i} className="st-rawrow">
                <code>
                  {[row['model'] ? String(row['model']) : '', T.messages(Number(obj(row['messages']).count ?? 0)), tokens ? T.contextTokens(tokens, allowance) : '']
                    .filter(Boolean)
                    .join(' · ')}
                </code>
                {run && row['ref'] ? <RawInput run={run} reference={row['ref'] as RawRef} /> : null}
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  )
}

function Turn({ exchange, run, busy }: { exchange: Exchange; run: string | null; busy: boolean }): JSX.Element {
  const text = replyText(exchange.execution)
  const late = timedOut(exchange.execution)
  const files = exchange.execution.deliverables ?? []
  return (
    <div className="st-turn">
      <div className="st-me"><div className="msg me">{exchange.user}</div></div>
      {busy ? (
        <p className="st-quiet"><i className="dot run" /> {T.trialThinking}</p>
      ) : (
        <div className="st-reply">
          <Activity exchange={exchange} run={run} />
          {text && <Markdown text={text} />}
          {late !== null && <p className="st-warn">{T.turnTimedOut(late === true ? null : late)}</p>}
          {files.length > 0 && (
            <div className="tkchips">
              {files.map((path) => (
                <a key={path} className="wchip" href={fileUrl(path)} target="_blank" rel="noreferrer"><Icon name="file" size={13} />{fileName(path)}</a>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function TrialPane({ trial, run, onSay, onEnd }: { trial: TrialView; run: string | null; onSay?: (text: string) => void; onEnd?: () => void }): JSX.Element {
  const [draft, setDraft] = useState('')
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => {
    end.current?.scrollIntoView({ block: 'end' })
  }, [trial.exchanges.length, trial.busy])
  const running = trial.status === 'running'
  const s = stats(trial)
  const send = () => {
    const text = draft.trim()
    if (!text || !onSay || trial.busy) return
    onSay(text)
    setDraft('')
  }
  return (
    <>
      <div className="tkbar st-tkbar" data-st={running ? 'run' : 'ok'}>
        <span className={`dot ${running ? 'run' : 'ok'}`} />
        <span className="st">{running ? T.trialRunning : T.trialDone}</span>
        <span>· {trial.version}</span>
        <span>· {T.trialTurns(s.turns)}</span>
        {s.interceptions > 0 && <span>· {T.trialInterceptions(s.interceptions)}</span>}
        <span className="grow" />
        {running && onEnd && <button type="button" className="st-btn" onClick={onEnd}>{T.trialEnd}</button>}
      </div>
      <div className="st-turns">
        {trial.exchanges.map((exchange, i) => (
          <Turn key={i} exchange={exchange} run={run} busy={!!trial.busy && i === trial.exchanges.length - 1} />
        ))}
        <div ref={end} />
      </div>
      {running && onSay && (
        <div className="st-tcomposer">
          <textarea
            value={draft}
            rows={2}
            placeholder={T.trialSay}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault()
                send()
              }
            }}
          />
          <button type="button" className="go" disabled={!draft.trim() || !!trial.busy} onClick={send} aria-label={T.send}><Icon name="up" size={15} /></button>
        </div>
      )}
    </>
  )
}
