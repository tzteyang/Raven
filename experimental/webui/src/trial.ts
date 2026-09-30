/* What a trial's recorded turns show: the Action controls with the host's
   receipts, Raven's own refusals, the playbook runs from dag.progress, the
   decks each drill delivered, and whether a changed strategy was called. An
   Action decision is a request; the host's receipt (action.control) says
   whether it was applied, and only an applied receipt is an intervention, as
   experimental/analyst/activity.py counts it. Record kinds follow
   experimental/curator/raven_adapter/action/runtime.py, observe.py and
   worker.py. */

import { tone } from './derive'
import { strategyOf } from './mechanism'

import type { Execution, RecordRow, Round, Run, Signal } from './model'

type Row = RecordRow & Record<string, unknown>

const obj = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
const str = (value: unknown): string => (typeof value === 'string' ? value : value == null ? '' : JSON.stringify(value))
const names = (value: unknown): string[] =>
  Array.isArray(value) ? value.map((item) => (typeof item === 'string' ? item : str(obj(item).name))).filter(Boolean) : []

export function replyText(execution: Execution): string {
  return execution.records
    .filter((row) => row.kind === 'runner.event' && row['event_type'] === 'Text')
    .map((row) => str(obj(row['event']).content))
    .join('\n')
}

/** The worker timeout in seconds a turn ran past before it was stopped, true when the record names none, and null
    for a turn that ended in time (experimental/curator/raven_adapter/worker.py TurnTimeoutError). */
export function timedOut(execution: Execution): number | true | null {
  const outcome = obj(execution.outcome)
  if (outcome.timed_out !== true) return null
  return typeof outcome.timeout === 'number' ? outcome.timeout : true
}

/** One control an Action decision requested, with the host's latest receipt for it. */
export interface Control {
  id: string
  /** reject (refuse one dispatch), revise (send the draft back) or finish (end the turn with its own reply). */
  control: string
  /** requested, applied, rejected or unsupported. */
  status: string
  reason: string
  /** The correction or reply the decision carried. */
  detail: string
  /** What the decision acted on: the event's kind, stage and proposed calls, or the agent's request. */
  on: string
  /** For a reject, the tool the refusal came back on and that call's id. */
  tool: string | null
  call: string | null
  /** Position of the record that settled it among the turn's records. */
  at: number
}

/** The event or request a strategy call carried, whole or as studio.py's summary of it. */
const carried = (call: Row): Record<string, unknown> => {
  const args = call['arguments']
  return obj(Array.isArray(args) ? args[0] : args)
}

function subject(call: Row | undefined): string {
  if (!call) return ''
  const event = carried(call)
  if (call['operation'] === 'handle_request') return ['request', event.command === undefined ? '' : str(event.command)].filter(Boolean).join(' ')
  const calls = names(event.calls)
  const text = typeof event.text === 'string' ? event.text.slice(0, 120) : ''
  return [str(event.kind), str(event.stage), calls.join(', ') || text].filter(Boolean).join(' · ')
}

/** Every control a turn's Action decisions requested, once each, with its latest receipt; a decision to continue
    requests none. */
export function controls(records: RecordRow[]): Control[] {
  const calls = new Map<string, { call: Row; result?: Row }>()
  const found = new Map<string, Control>()
  let open: { call: Row; result?: Row } | undefined
  const tools = new Map<string, string>()
  ;(records as Row[]).forEach((row, at) => {
    const kind = str(row.kind)
    if (kind === 'action.call') {
      const event = carried(row)
      open = { call: row }
      const id = str(event.event_id ?? event.request_id)
      if (id) calls.set(id, open)
    } else if (kind === 'action.result' && open) {
      open.result = row
    } else if (kind === 'action.control') {
      const receipt = obj(row['receipt'])
      const id = str(receipt.control_id)
      const known = found.get(id)
      if (known) {
        known.status = str(receipt.status)
        if (receipt.reason) known.reason = str(receipt.reason)
        known.at = at
      } else if (receipt.control !== 'continue') {
        const source = calls.get(str(receipt.source_id))
        const result = obj(source?.result?.['result'])
        const decision = obj(result.decision ?? result)
        found.set(id, {
          id,
          control: str(receipt.control),
          status: str(receipt.status),
          reason: str(receipt.reason ?? decision.reason),
          detail: decision.control === receipt.control ? str(decision.feedback || decision.reply || decision.guidance) : '',
          on: subject(source?.call),
          tool: null,
          call: null,
          at,
        })
      }
    } else if (kind === 'runner.event' && row['event_type'] === 'ToolEvent') {
      const event = obj(row['event'])
      const call = str(event.tool_call_id)
      if (event.phase === 'start') tools.set(call, str(event.name))
      if (event.phase !== 'complete') return
      const text = str(event.result_preview)
      for (const control of found.values()) {
        if (control.control === 'reject' && control.id && text.includes(`[${control.id}]`)) {
          control.tool = tools.get(call) || null
          control.call = call || null
        }
      }
    }
  })
  return [...found.values()]
}

export type InterceptionKind = 'reject' | 'revise' | 'finish' | 'gate' | 'permission' | 'budget'

export interface Interception {
  kind: InterceptionKind
  /** action.strategy for an applied control; the gate's name when a gate failed closed; raven for Raven's own checks. */
  mechanism: string
  /** What the control acted on (an Action event or request), or null for Raven's own refusals. */
  phase: string | null
  tool: string | null
  /** The tool_call_id of the refused call, for a reject, a gate or a permission refusal. */
  call: string | null
  reason: string
  /** What went back to the model, or the reply the strategy supplied. */
  detail: string
  /** Position among the turn's records. */
  at: number
}

const REFUSED_BY_GATE = /^Error: tool call '([^']*)' was refused by gate ([^:]+): ([\s\S]*)$/
const NEEDS_APPROVAL = /requires user approval \(([\s\S]*?)\), but this turn is not interactive/

/** Every intervention in one turn's records, in the order they happened: the applied Action controls, a gate that
    refused a call because its check raised, Raven's permission refusals, and send-backs its rollback budget refused. */
export function interceptions(records: RecordRow[]): Interception[] {
  const out: Interception[] = controls(records)
    .filter((control) => control.status === 'applied' && ['reject', 'revise', 'finish'].includes(control.control))
    .map((control) => ({
      kind: control.control as InterceptionKind,
      mechanism: 'action.strategy',
      phase: control.on || null,
      tool: control.tool,
      call: control.call,
      reason: control.reason,
      detail: control.detail,
      at: control.at,
    }))
  const tools = new Map<string, string>()
  records.forEach((raw, at) => {
    const row = raw as Row
    if (row.kind === 'runner.event' && row['event_type'] === 'ToolEvent') {
      const event = obj(row['event'])
      const call = str(event.tool_call_id)
      if (event.phase === 'start') tools.set(call, str(event.name))
      if (event.phase !== 'complete') return
      const text = str(event.result_preview)
      const tool = tools.get(call) || null
      const refused = REFUSED_BY_GATE.exec(text)
      if (refused) {
        out.push({ kind: 'gate', mechanism: refused[2], phase: null, tool: refused[1] || tool, call: call || null, reason: refused[3], detail: '', at })
        return
      }
      const approval = NEEDS_APPROVAL.exec(text)
      if (approval) out.push({ kind: 'permission', mechanism: 'raven', phase: null, tool, call: call || null, reason: approval[1], detail: '', at })
      return
    }
    if (row.kind === 'loop.control' && Number(row['rollbacks_refused']) > 0) {
      const count = Number(row['rollbacks_refused'])
      out.push({ kind: 'budget', mechanism: 'raven', phase: null, tool: null, call: null, reason: `${count} send-back${count === 1 ? ' was' : 's were'} refused: the turn's rollback budget was spent`, detail: '', at })
    }
  })
  return out.sort((a, b) => a.at - b.at)
}

export interface DagNode {
  id: string
  subagent: string | null
  summary: string | null
  dependsOn: string[]
  status: string
  startedAt: number | null
  endedAt: number | null
  output: string | null
  error: string | null
  /** 0 for a node with no dependencies, else one more than its deepest dependency. */
  level: number
}

export interface DagRun {
  id: string
  summary: string | null
  nodes: DagNode[]
  /** "completed" once the run's manifest arrived, "stopped" or "error" when it closed without one, else "running";
      "interrupted" when the whole run stopped while the graph was still open (see `interrupted`). */
  state: 'running' | 'completed' | 'stopped' | 'error' | 'interrupted'
  error: string | null
}

export const INTERRUPTED = 'interrupted'

/** A graph as it stands once the run stopped: an open graph and its running nodes read as interrupted, each
    node's duration frozen at `stoppedAt` (ms, the run's last event) when that is known. */
export function interrupted(graph: DagRun, stoppedAt: number | null): DagRun {
  if (graph.state !== 'running') return graph
  return {
    ...graph,
    state: 'interrupted',
    nodes: graph.nodes.map((item) =>
      item.status === 'running'
        ? {
            ...item,
            status: INTERRUPTED,
            endedAt: item.endedAt ?? (stoppedAt !== null && item.startedAt !== null ? Math.max(item.startedAt, stoppedAt) : null),
          }
        : item,
    ),
  }
}

const num = (value: unknown): number | null => (typeof value === 'number' && Number.isFinite(value) ? value : null)

/** The playbook graphs a set of records ran, with each node's sub-harness, status and timing. */
export function dagRuns(records: RecordRow[]): DagRun[] {
  const runs = new Map<string, DagRun>()
  const node = (run: DagRun, id: string): DagNode => {
    let found = run.nodes.find((item) => item.id === id)
    if (!found) {
      found = { id, subagent: null, summary: null, dependsOn: [], status: 'pending', startedAt: null, endedAt: null, output: null, error: null, level: 0 }
      run.nodes.push(found)
    }
    return found
  }
  for (const raw of records) {
    if (raw.kind !== 'dag.progress') continue
    const payload = obj(raw['payload'])
    const id = str(payload.run_id)
    if (!id) continue
    const run = runs.get(id) ?? { id, summary: null, nodes: [], state: 'running', error: null }
    runs.set(id, run)
    if (raw['name'] === 'dag_run_started') {
      run.summary = str(payload.task_summary) || null
      for (const spec of Array.isArray(payload.nodes) ? payload.nodes : []) {
        const row = obj(spec)
        const item = node(run, str(row.id))
        item.subagent = str(row.subagent) || null
        item.summary = str(row.node_summary) || null
        item.dependsOn = Array.isArray(row.depends_on) ? row.depends_on.map(str) : []
      }
    } else if (raw['name'] === 'dag_node_updated') {
      const item = node(run, str(payload.node))
      item.status = str(payload.status) || item.status
      item.startedAt = num(payload.started_at) ?? item.startedAt
      item.endedAt = num(payload.ended_at) ?? item.endedAt
    } else if (raw['name'] === 'dag_run_completed') {
      const manifest = obj(payload.manifest)
      const files = Array.isArray(manifest.files) ? manifest.files : []
      for (const entry of files) {
        const row = obj(entry)
        const item = node(run, str(row.node))
        item.subagent = str(row.subagent) || item.subagent
        item.status = str(row.status) || item.status
        item.startedAt = num(row.started_at) ?? item.startedAt
        item.endedAt = num(row.ended_at) ?? item.endedAt
        item.output = str(row.output_file) || null
        item.error = str(row.error) || null
        if (!item.dependsOn.length && Array.isArray(row.depends_on)) item.dependsOn = row.depends_on.map(str)
        item.summary ??= str(row.node_summary) || null
      }
      run.state = manifest.error ? 'error' : manifest.stopped ? 'stopped' : 'completed'
      run.error = manifest.error ? str(manifest.error) : null
    }
  }
  for (const run of runs.values()) {
    const byId = new Map(run.nodes.map((item) => [item.id, item]))
    const depth = (item: DagNode, seen: Set<string>): number => {
      if (seen.has(item.id)) return 0
      seen.add(item.id)
      const deps = item.dependsOn.map((dep) => byId.get(dep)).filter((dep): dep is DagNode => Boolean(dep))
      return deps.length ? 1 + Math.max(...deps.map((dep) => depth(dep, new Set(seen)))) : 0
    }
    for (const item of run.nodes) item.level = depth(item, new Set())
  }
  return [...runs.values()]
}

export const duration = (item: DagNode): number | null =>
  item.startedAt !== null && item.endedAt !== null ? Math.max(0, item.endedAt - item.startedAt) : null

export const DECK = /\.(pptx|ppt|odp)$/i

export interface DeckPair {
  session: string
  current: string | null
  /** The same drill's last deck in the latest earlier round that delivered one. */
  previous: { path: string; round: number } | null
}

const lastDeck = (round: Round | undefined, session: string): string | null =>
  [...(round?.sessions[session] ?? []).flatMap((exchange) => exchange.execution.deliverables ?? [])]
    .reverse()
    .find((path) => DECK.test(path)) ?? null

/** Per drill of a round (0-based), its delivered deck beside the previous round's deck for the same drill. */
export function decks(run: Run, index: number): DeckPair[] {
  const round = run.rounds[index]
  if (!round) return []
  return Object.keys(round.sessions).flatMap((session) => {
    const current = lastDeck(round, session)
    let previous: DeckPair['previous'] = null
    for (let i = index - 1; i >= 0 && !previous; i--) {
      const path = lastDeck(run.rounds[i], session)
      if (path) previous = { path, round: i + 1 }
    }
    return current || previous ? [{ session, current, previous }] : []
  })
}

const OPENERS = new Set(['read_skill', 'use_skill'])

/** Scenario materials the employee opened in a round, by skill name. */
export function opened(round: Round | undefined, materials: string[]): string[] {
  if (!round || !materials.length) return []
  const names = new Set<string>()
  for (const exchanges of Object.values(round.sessions)) {
    for (const exchange of exchanges) {
      for (const row of exchange.execution.records) {
        const event = obj(row['event'])
        if (row.kind !== 'runner.event' || event.phase !== 'start' || !OPENERS.has(str(event.name))) continue
        const skill = str(obj(event.arguments).skill_id ?? obj(event.arguments).name).split('/').pop() ?? ''
        if (materials.includes(skill)) names.add(skill)
      }
    }
  }
  return materials.filter((name) => names.has(name))
}

export interface Evidence {
  /** How many records show the strategy being called, or null for a target that is not one of the four strategies. */
  calls: number | null
  errors: number
  note: string
}

/** Whether a round's records show a changed strategy being called, and how often: its call and host callback rows. */
export function evidence(target: string, records: RecordRow[]): Evidence {
  const count = (test: (row: Row) => boolean) => records.filter((row) => test(row as Row)).length
  const role = strategyOf(target)
  if (!role) return { calls: null, errors: 0, note: 'not one of the four strategies; no call is recorded' }
  const calls = count((row) => row.kind === `${role}.call` || row.kind === `${role}.callback`)
  return { calls, errors: count((row) => row.kind === `${role}.error`), note: `${role}.call and ${role}.callback records` }
}

export interface DrillSummary {
  name: string
  turns: number
  /** Interceptions by the Harness (Raven's own permission refusals are not counted). */
  interceptions: number
  graphs: number
  /** The last deck the drill delivered in this round, if any. */
  deck: string | null
}

export interface TrialSummary {
  round: number
  version: string
  drills: DrillSummary[]
  passed: number
  failed: number
  /** Failed verdicts on criteria the scenario marks as red lines. */
  redFailed: number
  unknown: number
  interceptions: number
  graphs: number
}

/** The round's verdicts by assessor, as the server joined them (experimental/webui/rundir.py verdicts: a speaking
    assessor's scorecard kept in the analysis records stands in for its signal); a round read without that join
    counts the verdicts its signals carry. */
export const scoredSignals = (round: Round): Signal[] => round.verdicts ?? round.signals.filter((signal) => signal.items.length)

/** One round's trial at a glance: its drills, the owner's verdicts and what the Harness did. */
export function trialSummary(run: Run, index: number, version: string, red: Set<string>): TrialSummary | null {
  const round = run.rounds[index]
  if (!round) return null
  const drills = Object.entries(round.sessions).map(([name, exchanges]): DrillSummary => ({
    name,
    turns: exchanges.length,
    interceptions: exchanges.reduce((total, exchange) => total + interceptions(exchange.execution.records).filter((row) => row.mechanism !== 'raven').length, 0),
    graphs: exchanges.reduce((total, exchange) => total + dagRuns(exchange.execution.records).length, 0),
    deck: lastDeck(round, name),
  }))
  const items = scoredSignals(round).flatMap((signal) => signal.items)
  const failed = items.filter((item) => tone(item.result) === 'fail')
  return {
    round: index + 1,
    version,
    drills,
    passed: items.filter((item) => tone(item.result) === 'pass').length,
    failed: failed.length,
    redFailed: failed.filter((item) => red.has(item.id)).length,
    unknown: items.filter((item) => tone(item.result) === 'unknown').length,
    interceptions: drills.reduce((total, drill) => total + drill.interceptions, 0),
    graphs: drills.reduce((total, drill) => total + drill.graphs, 0),
  }
}
