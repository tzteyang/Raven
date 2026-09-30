/* The parts of a trial: a drill's turns with interceptions inline where they
   happened, the playbook graphs the employee launched, its decks beside the
   previous version's, and the owner's verdicts with red lines marked. The trial
   panel beside the cultivation conversation puts them together. */

import { useEffect, useState } from 'react'

import { fileUrl, loadThumbs, thumbsUrl } from '../api'
import { fileName, tone, verdict } from '../derive'
import { dagRuns, duration, interceptions, interrupted, replyText, timedOut } from '../trial'
import { BasisBadge, Fold, RedLine, StrategyBadge } from './Badges'
import { Deliverables } from './Deliverables'
import { Markdown } from './Markdown'
import { InterruptedFor, NodeProcessPanel, NodeTally } from './Process'
import { Records } from './Records'

import type { Exchange, Scenario, Signal } from '../model'
import type { DagNode, DagRun, Interception } from '../trial'
import type { JSX } from 'react'

function headline(row: Interception): string {
  switch (row.kind) {
    case 'reject':
      return `The action strategy refused ${row.tool ?? 'a tool call'}`
    case 'revise':
      return 'The action strategy sent the draft back'
    case 'finish':
      return 'The action strategy ended the turn with its own reply'
    case 'gate':
      return `Gate ${row.mechanism} refused ${row.tool ?? 'a tool call'}: its check raised`
    case 'permission':
      return `Raven's permission check refused ${row.tool ?? 'a tool call'}`
    case 'budget':
      return 'Send-back refused'
  }
}

export function InterceptionRow({ row }: { row: Interception }): JSX.Element {
  const raven = row.mechanism === 'raven'
  return (
    <div className={`icpt ${row.kind}${raven ? ' raven' : ''}`}>
      <div className="icpt-hd">
        <span className="dia" />
        <span className="what">{headline(row)}</span>
        {raven ? <span className="dim">Raven itself, not the Harness</span> : <code>{row.mechanism}{row.phase ? ` · ${row.phase}` : ''}</code>}
        {raven ? null : <StrategyBadge strategy="action" />}
      </div>
      {row.reason ? <p className="reason">{row.reason}</p> : null}
      {row.detail ? (
        <Fold className="fold small" summary={row.kind === 'finish' ? 'Reply it supplied' : 'Correction returned to the model'}>
          {() => <Markdown text={row.detail} />}
        </Fold>
      ) : null}
    </div>
  )
}

export function Turn({ exchange, drill, version, over }: { exchange: Exchange; drill: string; version: string; over: boolean }): JSX.Element {
  const reply = replyText(exchange.execution)
  const late = timedOut(exchange.execution)
  const rows = interceptions(exchange.execution.records)
  const graphs = dagRuns(exchange.execution.records).map((graph) => (over ? interrupted(graph, null) : graph))
  return (
    <div className="turn">
      <div className="me-wrap">
        <p className="me">{exchange.user}</p>
        <span className="who">{drill} · customer</span>
      </div>
      {rows.map((row, i) => <InterceptionRow key={i} row={row} />)}
      {graphs.map((graph) => (
        <p key={graph.id} className="dagmark">
          <span className="dot" />Playbook run <code>{graph.id.slice(0, 12)}</code> · {graph.nodes.length} node{graph.nodes.length === 1 ? '' : 's'} · {graph.state}
        </p>
      ))}
      <div className="ai-wrap">
        <span className="who"><span className="wd" />employee<code>{version}</code></span>
        <div className="ai">{reply ? <Markdown text={reply} /> : late === null ? <span className="quiet">No reply text was recorded.</span> : null}</div>
        {late !== null ? <p className="bad small">The turn ran past the worker&apos;s timeout{late === true ? '' : ` of ${late} s`} and was stopped; the customer had no answer.</p> : null}
        <Records execution={exchange.execution} />
        <Deliverables paths={exchange.execution.deliverables ?? []} />
      </div>
    </div>
  )
}

const seconds = (ms: number | null): string =>
  ms === null ? '' : ms < 1000 ? `${ms} ms` : ms < 60_000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.floor(ms / 60_000)} m ${Math.round((ms % 60_000) / 1000)} s`

const nodeTone = (status: string): string =>
  status === 'completed' ? 'ok' : status === 'failed' || status === 'exception' ? 'bad' : status === 'running' ? 'run' : status === 'interrupted' ? 'int' : 'skip'

interface NodeProps {
  node: DagNode
  now?: number
  /** With a run id the card opens the node's process below the graph. */
  runId?: string
  dag: string
  open: boolean
  onToggle: () => void
}

function Node({ node, now, runId, dag, open, onToggle }: NodeProps): JSX.Element {
  const elapsed = node.status === 'running' && node.startedAt !== null && now ? Math.max(0, now - node.startedAt) : null
  const body = (
    <>
      <div className="nd-hd"><span className="dot" /><code>{node.id}</code></div>
      {node.summary ? <div className="nd-sum">{node.summary}</div> : null}
      <div className="nd-meta">
        {node.subagent ? <span className="who">{node.subagent}</span> : null}
        <span className="st">{node.status}</span>
        {node.status === 'interrupted' ? (
          runId ? <InterruptedFor runId={runId} dag={dag} node={node.id} startedAt={node.startedAt} endedAt={node.endedAt} format={seconds} /> : duration(node) !== null ? <span className="dur">{seconds(duration(node))}</span> : null
        ) : duration(node) !== null ? <span className="dur">{seconds(duration(node))}</span> : null}
        {elapsed !== null ? <span className="dur">{seconds(elapsed)} so far</span> : null}
      </div>
      {runId && node.status === 'running' && !open ? <NodeTally runId={runId} dag={dag} node={node.id} status={node.status} /> : null}
      {node.dependsOn.length ? <div className="deps">after {node.dependsOn.join(', ')}</div> : null}
      {node.error ? <div className="bad small">{node.error}</div> : null}
    </>
  )
  if (!runId) return <div className={`nd ${nodeTone(node.status)}`} title={node.summary ?? ''}>{body}</div>
  return (
    <button
      className={`nd ${nodeTone(node.status)}${open ? ' open' : ''}`}
      title={open ? 'Hide what this node did' : 'Show what this node did'}
      aria-expanded={open}
      onClick={onToggle}
    >
      {body}
    </button>
  )
}

export interface GraphProps {
  graph: DagRun
  drill: string
  /** Now in ms, to show how long running nodes have been at it. */
  now?: number
  /** With a run id each node opens its sub-agent's process below the graph. */
  runId?: string
  /** The whole run has stopped: an open graph and its running nodes are drawn interrupted. */
  over?: boolean
  /** The run's last event in ms, where an interrupted node's duration stops. */
  stoppedAt?: number | null
}

/** A playbook graph in dependency order. */
export function Graph({ graph: recorded, drill, now, runId, over = false, stoppedAt = null }: GraphProps): JSX.Element {
  const [open, setOpen] = useState<string | null>(null)
  const graph = over ? interrupted(recorded, stoppedAt) : recorded
  const depth = Math.max(0, ...graph.nodes.map((node) => node.level))
  const levels = Array.from({ length: depth + 1 }, (_, level) => graph.nodes.filter((node) => node.level === level))
  const shown = open ? graph.nodes.find((node) => node.id === open) ?? null : null
  return (
    <div className="dag">
      <div className="dag-hd">
        <span className="nm">{drill}</span>
        <code>{graph.id.slice(0, 12)}</code>
        <span className={`st ${graph.state}`}>{graph.state}</span>
        {graph.summary ? <span className="quiet">{graph.summary}</span> : null}
      </div>
      {graph.error ? <p className="bad">{graph.error}</p> : null}
      <div className="lvls">
        {levels.map((nodes, i) => (
          <div key={i} className="lvl">
            {nodes.map((node) => (
              <Node
                key={node.id}
                node={node}
                now={now}
                runId={runId}
                dag={graph.id}
                open={open === node.id}
                onToggle={() => setOpen(open === node.id ? null : node.id)}
              />
            ))}
          </div>
        ))}
      </div>
      {runId && !shown ? <p className="dag-hint">Open a node to see what its sub-agent did.</p> : null}
      {runId && shown ? (
        <NodeProcessPanel
          runId={runId}
          dag={graph.id}
          node={shown.id}
          subagent={shown.subagent}
          status={shown.status}
          summary={shown.summary}
          over={over}
          onClose={() => setOpen(null)}
        />
      ) : null}
    </div>
  )
}

export interface Thumbs {
  pages: string[]
  error: string
  loading: boolean
}

/** Page images behind a thumbnail endpoint URL, loaded once per URL. */
export function useThumbs(url: string | null): Thumbs {
  const [state, setState] = useState<Thumbs>({ pages: [], error: '', loading: Boolean(url) })
  useEffect(() => {
    if (!url) {
      setState({ pages: [], error: '', loading: false })
      return
    }
    let live = true
    setState({ pages: [], error: '', loading: true })
    loadThumbs(url)
      .then((pages) => { if (live) setState({ pages, error: '', loading: false }) })
      .catch((e: Error) => { if (live) setState({ pages: [], error: e.message, loading: false }) })
    return () => { live = false }
  }, [url])
  return state
}

export function DeckHead({ label, path, thumbs }: { label: string; path: string | null; thumbs: Thumbs }): JSX.Element {
  return (
    <div className="deck-head">
      <span className="lbl">{label}</span>
      {path ? <a href={fileUrl(path)} target="_blank" rel="noreferrer">{fileName(path)}</a> : <span className="quiet">no deck</span>}
      {thumbs.loading ? <span className="quiet">rendering pages...</span> : null}
      {thumbs.error ? <span className="bad" title={thumbs.error}>thumbnails unavailable</span> : null}
      {thumbs.pages.length ? <span className="quiet">{thumbs.pages.length} pages</span> : null}
    </div>
  )
}

/* Page n of the previous version's deck beside page n of this one, so a
   change in the deliverable reads row by row. */
export function DeckCompare({
  session, current, previous, version, previousVersion,
}: { session: string; current: string | null; previous: { path: string; round: number } | null; version: string; previousVersion: string }): JSX.Element {
  const now = useThumbs(current ? thumbsUrl(current) : null)
  const before = useThumbs(previous ? thumbsUrl(previous.path) : null)
  const rows = Math.max(now.pages.length, before.pages.length)
  const page = (pages: string[], i: number, label: string) =>
    pages[i] ? <img src={fileUrl(pages[i])} alt={`${label} page ${i + 1}`} loading="lazy" /> : <span className="blank" />
  return (
    <div className="deckpair">
      <div className="deckpair-hd"><span className="nm">{session}</span></div>
      <div className="deck-grid">
        <DeckHead label={previous ? `before · round ${previous.round} · ${previousVersion}` : 'before'} path={previous?.path ?? null} thumbs={before} />
        <DeckHead label={`now · ${version}`} path={current} thumbs={now} />
        {Array.from({ length: rows }, (_, i) => (
          <div key={i} className="deck-row">
            <span className="pg">{i + 1}</span>
            {page(before.pages, i, 'before')}
            {page(now.pages, i, 'now')}
          </div>
        ))}
      </div>
    </div>
  )
}

const RANK: Record<string, number> = { fail: 0, unknown: 1, pass: 2 }

/** The owner's verdicts; with `failedFirst` the failures lead and passes follow, each group in the owner's order. */
export function Verdicts({ signals, scenario, failedFirst = false }: { signals: Signal[]; scenario: Scenario; failedFirst?: boolean }): JSX.Element {
  const severity = new Map(scenario.criteria.map((row) => [row.id, row.severity]))
  const arrange = (items: Signal['items']) =>
    failedFirst ? items.map((item, i) => ({ item, i })).sort((a, b) => RANK[tone(a.item.result)] - RANK[tone(b.item.result)] || a.i - b.i).map(({ item }) => item) : items
  const ordered = [...signals].sort((a, b) => Number(b.source === 'agency') - Number(a.source === 'agency'))
  if (!ordered.some((signal) => signal.items.length)) return <p className="quiet">No verdicts were recorded for this trial.</p>
  return (
    <>
      {ordered.filter((signal) => signal.items.length).map((signal, s) => (
        <div key={s} className="table">
          {ordered.length > 1 ? <p className="eyebrow">{signal.source}</p> : null}
          <table className="verdicts">
            <thead><tr><th>Criterion</th><th>Verdict</th><th>Drill</th><th>What the owner saw</th></tr></thead>
            <tbody>
              {arrange(signal.items).map((item, i) => {
                const result = tone(item.result)
                const red = severity.get(item.id) === 'red_line'
                return (
                  <tr key={i} className={`${result}${red ? ' red' : ''}`}>
                    <td>
                      <span className="n">{item.id}</span>{red ? <RedLine /> : null}<BasisBadge basis={item.basis} />
                      {item.expected ? <Fold className="fold small" summary="check">{() => <p className="check">{item.expected}</p>}</Fold> : null}
                    </td>
                    <td className={`v ${result}`}>{verdict(item.result)}</td>
                    <td className="drillcell">{item.session ?? ''}</td>
                    <td>
                      {result === 'fail' && item.actual ? <q>{item.actual}</q> : null}
                      {item.note ? <p className={result === 'fail' ? 'note' : 'note dim'}>{item.note}</p> : null}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ))}
    </>
  )
}
