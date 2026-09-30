/* The live view's data: the compact worker-log rows /api/live serves from
   every log the run is writing (the employee's and each replica's that plays a
   drill), grouped by turn into what the page draws, in the order they
   happened: the customer's message, the employee's replies, tool calls,
   playbook progress, the Action controls the host applied and errors. */

import { strategyOf } from './mechanism'
import { dagRuns, interceptions } from './trial'

import type { Strategy } from './mechanism'
import type { RecordRow, RunStatus } from './model'
import type { DagRun, Interception } from './trial'

export interface Phase {
  name: string
  /** The round in progress, or the round being curated; 0 while onboarding. */
  round: number
  stage: string | null
  /** The evidence the phase rests on, in words. */
  basis: string
}

/** One followed worker log: its folder under the run, where this read started and ended, and whether it started a
    fresh tail because the page had no matching offset. */
export interface LiveLog {
  file: string
  start: number
  offset: number
  size: number
  reset: boolean
  last_event: number
}

export interface LiveReply {
  logs: LiveLog[]
  /** New rows of every followed log, each naming the log it came from in `file`. */
  rows: RecordRow[]
  last_event: number | null
  phase: Phase
  status: RunStatus
  /** The Curator's progress file, or null when the run has none. */
  curator: CuratorProgress | null
  /** Copies the worker kept of delivered files, newest first; absent from an older server. */
  deliveries?: KeptFile[]
  /** Each session the record already holds, by name, with the opaque label its session key and replica folder
      carry (experimental/iteration/hearing.py opaque). A drill of a round not yet recorded is known only by its label;
      absent from an older server. */
  labels?: Record<string, string>
  now: number
}

/** The session names by the opaque labels a reply's `labels` gives them. */
export const namesOf = (labels: Record<string, string>): Record<string, string> =>
  Object.fromEntries(Object.entries(labels).map(([name, label]) => [label, name]))

/** A delivered file's kept copy: `<worker root>/deliverables/<turn>/<name>`, served by /files. */
export interface KeptFile {
  turn: string
  name: string
  path: string
  size: number
  modified: number
}

export interface Delivered {
  turn: string
  name: string
  /** The kept copy, or null while the turn that handed it over is still open. */
  path: string | null
  title: string | null
  description: string | null
  size: number | null
  /** What the employee said with the files. */
  message: string | null
  /** When the copy was kept, in epoch seconds. */
  modified: number | null
}

/* A deliver_files result names what went out the moment it is handed over;
   the worker keeps a copy only as the turn closes. Files still waiting for
   their copy come first, latest first, then the kept ones, newest first. */
export function delivered(rows: RecordRow[], kept: KeptFile[]): Delivered[] {
  const said = new Map<string, Omit<Delivered, 'path' | 'modified'>>()
  const order: string[] = []
  for (const row of rows) {
    if (row.kind !== 'runner.event' || row['event_type'] !== 'ToolEvent' || !row.turn_id) continue
    const delivery = (event(row).delivery ?? null) as { message?: unknown; files?: unknown } | null
    if (!delivery || !Array.isArray(delivery.files)) continue
    for (const raw of delivery.files) {
      const file = (raw ?? {}) as Record<string, unknown>
      const name = text(file.name)
      if (!name) continue
      const key = `${row.turn_id}/${name}`
      if (!said.has(key)) order.push(key)
      said.set(key, {
        turn: row.turn_id,
        name,
        title: text(file.title) || null,
        description: text(file.description) || null,
        size: typeof file.size === 'number' ? file.size : null,
        message: text(delivery.message) || null,
      })
    }
  }
  const keptKeys = new Set(kept.map((file) => `${file.turn}/${file.name}`))
  const waiting = order
    .filter((key) => !keptKeys.has(key))
    .reverse()
    .map((key): Delivered => ({ ...said.get(key)!, path: null, modified: null }))
  const copies = [...kept]
    .sort((a, b) => b.modified - a.modified)
    .map((file): Delivered => {
      const known = said.get(`${file.turn}/${file.name}`)
      return {
        turn: file.turn,
        name: file.name,
        path: file.path,
        title: known?.title ?? null,
        description: known?.description ?? null,
        size: file.size,
        message: known?.message ?? null,
        modified: file.modified,
      }
    })
  return [...waiting, ...copies]
}

/** One generation trace event as the Curator's progress file keeps it; long fields arrive cut. */
export interface CuratorEvent {
  stage?: string | null
  event: string
  tool?: string
  path?: string
  call?: string
  content?: string
  error?: string
  /** The validation errors as the Curator wrote them: text, not a parsed list. */
  errors?: string
  arguments?: string
  targets?: string[]
  understanding?: string
}

export interface CuratorProgress {
  started: number
  updated: number
  stage: string | null
  calls: number
  queries: number
  checks: number
  repairs: number
  staged: string[]
  /** The last 40 trace events. */
  events: CuratorEvent[]
  finished?: boolean
  error?: string | null
}

export type LiveItem =
  | { kind: 'reply'; text: string }
  | { kind: 'tool'; id: string; name: string; args: string; ok: boolean | null; result: string; refused: boolean }
  | { kind: 'dag'; run: DagRun }
  | { kind: 'interception'; row: Interception }
  | { kind: 'message'; text: string }
  | { kind: 'error'; text: string }

export interface LiveTurn {
  id: string
  drill: string | null
  customer: string | null
  items: LiveItem[]
  /** No loop.control row has closed the turn yet. */
  open: boolean
  /** The worker log the turn came from: the employee's, or a replica's such as replicas/1-session-3fa2b1/<worker>. */
  file: string | null
}

const text = (value: unknown): string => (typeof value === 'string' ? value : value == null ? '' : JSON.stringify(value))
const event = (row: RecordRow): Record<string, unknown> => (row['event'] as Record<string, unknown>) ?? {}

/** The turns of the followed logs; a drill goes by its name when `names` (see `namesOf`) knows its session label. */
export function groupTurns(rows: RecordRow[], names: Record<string, string> = {}): LiveTurn[] {
  const order: string[] = []
  const byTurn = new Map<string, RecordRow[]>()
  const files = new Map<string, string | null>()
  for (const row of rows) {
    const id = row.turn_id
    if (!id) continue
    if (!byTurn.has(id)) {
      byTurn.set(id, [])
      order.push(id)
      files.set(id, text(row['file']) || null)
    }
    byTurn.get(id)!.push(row)
  }
  return order.map((id) => {
    const turnRows = byTurn.get(id)!
    const placed: { at: number; item: LiveItem }[] = []
    const tools = new Map<string, Extract<LiveItem, { kind: 'tool' }>>()
    const graphs = new Map(dagRuns(turnRows).map((run) => [run.id, run]))
    const drawn = new Set<string>()
    let customer: string | null = null
    let drill: string | null = null
    let open = true
    turnRows.forEach((row, at) => {
      if (row.kind === 'provider.request') {
        const said = text(row['text'])
        if (customer === null) {
          customer = said
          const label = text(row['drill'])
          drill = names[label] ?? (label || null)
        } else if (said && said !== customer && !placed.some(({ item }) => item.kind === 'message' && item.text === said)) {
          placed.push({ at, item: { kind: 'message', text: said } })
        }
      } else if (row.kind === 'runner.event' && row['event_type'] === 'Text') {
        const reply = text(event(row).content)
        if (reply) placed.push({ at, item: { kind: 'reply', text: reply } })
      } else if (row.kind === 'runner.event' && row['event_type'] === 'ToolEvent') {
        const detail = event(row)
        const call = text(detail.tool_call_id)
        if (detail.phase === 'start') {
          const item = { kind: 'tool' as const, id: call, name: text(detail.name), args: text(detail.arguments), ok: null, result: '', refused: false }
          tools.set(call, item)
          placed.push({ at, item })
        } else {
          const item = tools.get(call)
          if (item) {
            item.ok = detail.ok === undefined ? null : Boolean(detail.ok)
            item.result = text(detail.result_preview)
          }
        }
      } else if (row.kind === 'dag.progress') {
        const run = graphs.get(text((row['payload'] as Record<string, unknown>)?.run_id))
        if (run && !drawn.has(run.id)) {
          drawn.add(run.id)
          placed.push({ at, item: { kind: 'dag', run } })
        }
      } else if (row.kind === 'loop.control' || row.kind === 'runtime.closed') {
        open = false
      } else if (row.kind.endsWith('.error')) {
        placed.push({ at, item: { kind: 'error', text: text(row['error']) } })
      }
    })
    for (const found of interceptions(turnRows)) {
      placed.push({ at: found.at, item: { kind: 'interception', row: found } })
      const item = found.call ? tools.get(found.call) : undefined
      if (item) item.refused = true
    }
    placed.sort((a, b) => a.at - b.at)
    return { id, drill, customer, items: placed.map(({ item }) => item), open, file: files.get(id) ?? null }
  })
}

/** Rows after a poll: a log read from a fresh tail replaces what the page held of that log, any other log's new rows
    are appended; rows of logs the server no longer follows stay. */
export function merge(rows: RecordRow[], reply: LiveReply, cap = 6000): RecordRow[] {
  const fresh = new Set(reply.logs.filter((log) => log.reset).map((log) => log.file))
  if (!fresh.size && reply.rows.length === 0) return rows
  const next = [...rows.filter((row) => !fresh.has(text(row['file']))), ...reply.rows]
  return next.length > cap ? next.slice(next.length - cap) : next
}

/** Where to read each followed log from next, as the `logs` query value. */
export const cursorOf = (logs: LiveLog[]): string => logs.map((log) => `${log.file}:${log.offset}`).join(',')

/* The progress file keeps a sliding window of the last 40 events, so events are
   kept across polls by appending what lies past the longest overlap; a window
   that does not overlap leaves a gap marker. */
export const GAP: CuratorEvent = { event: 'gap' }

export function mergeEvents(kept: CuratorEvent[], window: CuratorEvent[]): CuratorEvent[] {
  const keys = kept.map((event) => JSON.stringify(event))
  const next = window.map((event) => JSON.stringify(event))
  for (let k = Math.min(keys.length, next.length); k > 0; k--) {
    if (keys.slice(keys.length - k).every((key, i) => key === next[i])) {
      return k === next.length ? kept : [...kept, ...window.slice(k)]
    }
  }
  return kept.length ? [...kept, GAP, ...window] : [...window]
}

export type StepId = 'diagnose' | 'select' | 'design' | 'implement' | 'validate' | 'repair'
export type StepState = 'done' | 'current' | 'todo' | 'failed' | 'skipped'

export const STEP_LABEL: Record<StepId, string> = {
  diagnose: 'diagnose',
  select: 'understand / select',
  design: 'design',
  implement: 'implement',
  validate: 'validate',
  repair: 'repair',
}

const ORDER: StepId[] = ['diagnose', 'select', 'design', 'implement', 'validate', 'repair']

/** Where the curation stands: diagnose while its attribution runs, then the generation's stage, read as validate
    while the latest event is a validation. */
export function steps(progress: CuratorProgress): { id: StepId; label: string; state: StepState }[] {
  const last = progress.events[progress.events.length - 1]
  const stage = (ORDER as string[]).includes(progress.stage ?? '') ? (progress.stage as StepId) : 'diagnose'
  const current: StepId = stage !== 'repair' && (last?.event === 'validation' || last?.stage === 'validate') ? 'validate' : stage
  const at = ORDER.indexOf(current)
  return ORDER.map((id, i) => {
    let state: StepState
    if (progress.finished && !progress.error) state = id === 'repair' && !progress.repairs ? 'skipped' : 'done'
    else if (id === current) state = progress.finished ? 'failed' : 'current'
    else if (id === 'repair') state = 'todo'
    else state = i < at ? 'done' : 'todo'
    return { id, label: STEP_LABEL[id], state }
  })
}

export type PanelItem =
  | { kind: 'call'; call: string; stage: string }
  | { kind: 'note'; text: string; stage: string }
  | { kind: 'query'; tool: string; argument: string; rejected: boolean }
  | { kind: 'staged'; path: string }
  | { kind: 'submit'; name: string; targets: { target: string; strategy: Strategy | null }[]; understanding: string }
  | { kind: 'check'; name: string; errors: string[]; detail: string }
  | { kind: 'rejected'; name: string; tool: string; error: string }
  | { kind: 'gap' }
  | { kind: 'other'; name: string; detail: string }

/** A tool call's arguments as one short line: key=value pairs from the JSON text, else the text itself. */
export function shortArguments(text: string | undefined, limit = 90): string {
  if (!text) return ''
  let line = text
  try {
    const value = JSON.parse(text)
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      line = Object.entries(value).map(([key, item]) => `${key}=${typeof item === 'string' ? item : JSON.stringify(item)}`).join(', ')
    }
  } catch {
    line = text
  }
  return line.length > limit ? `${line.slice(0, limit)}...` : line
}

/** Validation errors arrive as the text of a list; an empty list means none. */
export function errorList(text: string | undefined): string[] {
  const trimmed = (text ?? '').trim()
  if (!trimmed || trimmed === '[]') return []
  try {
    const value = JSON.parse(trimmed)
    if (Array.isArray(value)) return value.map(String)
  } catch {
    /* not JSON: the Curator wrote the list's repr */
  }
  return [trimmed.replace(/^\[|\]$/g, '')]
}

export function panelItems(events: CuratorEvent[]): PanelItem[] {
  return events.map((event): PanelItem => {
    const stage = event.stage ?? ''
    switch (event.event) {
      case 'gap':
        return { kind: 'gap' }
      case 'model.call':
        return { kind: 'call', call: event.call ?? '', stage }
      case 'model.note':
        return { kind: 'note', text: event.content ?? '', stage }
      case 'query':
      case 'query.rejected':
        return { kind: 'query', tool: event.tool ?? '', argument: shortArguments(event.arguments), rejected: event.event === 'query.rejected' }
      case 'file.staged':
        return { kind: 'staged', path: event.path ?? '' }
      case 'preflight':
        return { kind: 'check', name: 'preflight', errors: event.error ? [event.error] : errorList(event.errors), detail: shortArguments(event.arguments) }
      case 'validation':
        return { kind: 'check', name: 'validation', errors: errorList(event.errors), detail: '' }
      case 'output.rejected':
      case 'output.missing':
        return { kind: 'rejected', name: event.event, tool: event.tool ?? '', error: event.error ?? (event.event === 'output.missing' ? 'the model neither submitted nor queried' : '') }
      default:
        if (event.event.startsWith('submit_')) {
          return {
            kind: 'submit',
            name: event.event,
            targets: (event.targets ?? []).map((target) => ({ target, strategy: strategyOf(target) })),
            understanding: event.understanding ?? '',
          }
        }
        return { kind: 'other', name: event.event, detail: [event.tool, event.path, event.error].filter(Boolean).join(' · ') }
    }
  })
}

/** Phases in which nothing of the run is moving any more. */
const STOPPED = new Set(['error', 'finished', 'paused', 'stalled or stopped'])

/** Whether the run has stopped, by its record's status or the phase the server reads from its files. */
export const stopped = (running: boolean, phase: Phase | null): boolean => !running || (phase !== null && STOPPED.has(phase.name))

/** A live tool call's state; one still open when the run stopped reads as interrupted. */
export function toolItemState(item: Extract<LiveItem, { kind: 'tool' }>, over: boolean): string {
  if (item.refused) return 'refused'
  if (item.ok === null) return over ? 'interrupted' : 'running'
  return item.ok ? 'done' : 'failed'
}
