/* The execution ledger as the Execution view reads it: the report of
   /api/execution (raven.observability.report.build), regrouped into the
   figures a cost dashboard shows. Everything here is pure; the view only
   renders what these functions return.

   Two rules carry through every figure. An unknown amount is never a zero: a
   sum is null when no term is known, and a count of the unknown terms travels
   with it. And stage totals are inclusive of their descendants, so figures of
   nested operations are never added to each other; the matrix and the
   breakdowns only ever sum leaf requests. */

export type Status = 'ok' | 'error' | 'cancelled' | 'running'

export interface Usage {
  input_tokens?: number | null
  input_total_tokens?: number | null
  output_tokens?: number | null
  cache_read_tokens?: number | null
  cache_write_tokens?: number | null
  reasoning_tokens?: number | null
  total_tokens?: number | null
  cost_usd?: number | null
  quota_usd?: number | null
  inconsistent?: boolean
}

export interface Totals extends Usage {
  attempts: number
  external_calls?: number
  inconsistent_usage?: number
  unfinished: number
  failed: number
  partial_usage: number
  attempt_duration_ms?: number
  missing: Record<string, number>
}

export type Part = 'employee' | 'subagents' | 'simulation' | 'research'

export interface Operation {
  id: string
  parent_id: string | null
  kind?: 'span' | 'attempt' | 'external'
  name: string
  status: Status | string
  started_at: string
  ended_at?: string | null
  duration_ms: number | null
  attributes: Record<string, string | number | null | undefined>
  totals?: Totals
  usage?: Usage
  usage_complete?: boolean
  served_model?: string
  response_id?: string
  part?: Part
  error_type?: string
  http_status?: number
}

export interface Report {
  available: boolean
  run_ids?: string[]
  totals: Totals
  missing_parents: string[]
  spans: Operation[]
  attempts: Operation[]
}

/** A sum that stays unknown while no term is known, with the count of unknown terms. */
export interface Known {
  value: number | null
  unknown: number
}

export const known = (values: (number | null | undefined)[]): Known => {
  const found = values.filter((value): value is number => typeof value === 'number')
  return { value: found.length ? found.reduce((sum, value) => sum + value, 0) : null, unknown: values.length - found.length }
}

/** The loop's own order of its steps; stages the loop does not name follow, in the order they were first seen. */
export const STAGE_ORDER = ['onboard', 'trial', 'holdout', 'assess', 'analyse', 'curate']

export const PARTS: Part[] = ['employee', 'subagents', 'simulation', 'research']

export const PART_LABEL: Record<Part, string> = {
  employee: 'Employee',
  subagents: 'Subagents',
  simulation: 'Simulation',
  research: 'Research',
}

export const PART_NOTE: Record<Part, string> = {
  employee: 'the worker under cultivation, its own sessions',
  subagents: 'child harnesses the worker delegated to',
  simulation: 'the conversant, assessors, Analyst and Curator',
  research: 'external agent invocations, usage per whole invocation',
}

export const partOf = (row: Operation): Part => row.part ?? 'simulation'

/** A loop step's span: the one whose stage attribute is its own name (experimental.harness.loop.observability). */
export const isStep = (span: Operation): boolean => span.attributes.stage === span.name

export const roundOf = (span: Operation): number | null => {
  const value = span.attributes.round_index
  return typeof value === 'number' ? value : null
}

export const modelOf = (row: Operation): string => row.served_model ?? String(row.attributes.model ?? '') ?? ''

export interface Breakdown {
  key: string
  attempts: number
  external: number
  cost: Known
  quota: Known
  input: Known
  cacheRead: Known
  output: Known
  duration: Known
  failed: number
}

const breakdown = (key: string, rows: Operation[]): Breakdown => ({
  key,
  attempts: rows.filter((row) => row.kind !== 'external').length,
  external: rows.filter((row) => row.kind === 'external').length,
  cost: known(rows.map((row) => row.usage?.cost_usd)),
  quota: known(rows.map((row) => row.usage?.quota_usd)),
  input: known(rows.map((row) => row.usage?.input_total_tokens)),
  cacheRead: known(rows.map((row) => row.usage?.cache_read_tokens)),
  output: known(rows.map((row) => row.usage?.output_tokens)),
  duration: known(rows.map((row) => row.duration_ms)),
  failed: rows.filter((row) => row.status === 'error' || row.status === 'cancelled').length,
})

/** Requests grouped by who they belong to, in the parts' fixed order; a part with no request is absent. */
export const byPart = (attempts: Operation[]): Breakdown[] =>
  PARTS.map((part) => breakdown(part, attempts.filter((row) => partOf(row) === part))).filter((row) => row.attempts + row.external)

/** Requests grouped by the model that served them, costliest first; unknown cost sorts last. */
export const byModel = (attempts: Operation[]): Breakdown[] => {
  const groups = new Map<string, Operation[]>()
  for (const row of attempts) {
    const key = modelOf(row) || 'unknown model'
    groups.set(key, [...(groups.get(key) ?? []), row])
  }
  return [...groups].map(([key, rows]) => breakdown(key, rows)).sort((a, b) => (b.cost.value ?? -1) - (a.cost.value ?? -1))
}

export interface Cell {
  round: number
  stage: string
  ids: string[]
  cost: Known
  attempts: number
  external: number
  output: Known
  input: Known
  status: Status
  duration: Known
}

export interface Matrix {
  rounds: number[]
  stages: string[]
  cells: Cell[]
}

const worst = (statuses: string[]): Status =>
  statuses.includes('error') ? 'error' : statuses.includes('cancelled') ? 'cancelled' : statuses.includes('running') ? 'running' : 'ok'

/** The loop's steps as a round-by-stage grid; a cell joins every step span of that round and stage. The figures
    are each step's inclusive totals, which only ever count the leaf requests under it; a cell's unknown cost is
    how many of those requests reported no price. */
export const matrix = (spans: Operation[]): Matrix => {
  const steps = spans.filter((span) => isStep(span) && roundOf(span) !== null)
  const rounds = [...new Set(steps.map((span) => roundOf(span) as number))].sort((a, b) => a - b)
  const seen = [...new Set(steps.map((span) => span.name))]
  const stages = [...STAGE_ORDER.filter((name) => seen.includes(name)), ...seen.filter((name) => !STAGE_ORDER.includes(name))]
  const cells: Cell[] = []
  for (const round of rounds) {
    for (const stage of stages) {
      const own = steps.filter((span) => roundOf(span) === round && span.name === stage)
      if (!own.length) continue
      const totals = own.map((span) => span.totals)
      cells.push({
        round,
        stage,
        ids: own.map((span) => span.id),
        cost: {
          value: known(totals.map((total) => total?.cost_usd)).value,
          unknown: totals.reduce((sum, total) => sum + (total?.missing?.cost_usd ?? 0), 0),
        },
        attempts: totals.reduce((sum, total) => sum + (total?.attempts ?? 0), 0),
        external: totals.reduce((sum, total) => sum + (total?.external_calls ?? 0), 0),
        output: known(totals.map((total) => total?.output_tokens)),
        input: known(totals.map((total) => total?.input_total_tokens)),
        status: worst(own.map((span) => span.status)),
        duration: known(own.map((span) => span.duration_ms)),
      })
    }
  }
  return { rounds, stages, cells }
}

/** The parent of every operation, for walking ancestry. */
export const parentsOf = (report: Report): Map<string, string | null> =>
  new Map([...report.spans, ...report.attempts].map((row) => [row.id, row.parent_id]))

/** Whether an operation sits under any of the selected spans. */
export const under = (row: Operation, selected: ReadonlySet<string>, parents: Map<string, string | null>): boolean => {
  if (!selected.size) return true
  let parent = row.parent_id
  const visited = new Set<string>()
  while (parent && !visited.has(parent)) {
    if (selected.has(parent)) return true
    visited.add(parent)
    parent = parents.get(parent) ?? null
  }
  return false
}

export interface Window {
  start: number
  end: number
}

const startOf = (row: Operation): number => Date.parse(row.started_at)

/** When an operation ended: its own end, else, while the run is live, now; a dead run's unfinished operation is
    drawn to the last moment anything else in the run was seen. */
export const endOf = (row: Operation, now: number, last: number): number => {
  if (row.ended_at) return Date.parse(row.ended_at)
  if (row.duration_ms != null) return startOf(row) + row.duration_ms
  return row.status === 'running' ? now : last
}

/** The run's own time window: from the earliest start to the latest known end (or now while live). */
export const windowOf = (rows: Operation[], live: boolean, now = Date.now()): Window | null => {
  if (!rows.length) return null
  const starts = rows.map(startOf)
  const ends = rows.filter((row) => row.ended_at || row.duration_ms != null).map((row) => endOf(row, now, 0))
  const last = ends.length ? Math.max(...ends) : Math.max(...starts)
  const end = live ? Math.max(last, now) : last
  return { start: Math.min(...starts), end: Math.max(end, Math.min(...starts) + 1) }
}

export interface Lane {
  round: number | null
  spans: Operation[]
}

/** The top-level steps as lanes, one per round; a run with no step spans shows its root spans in one lane. */
export const lanes = (spans: Operation[]): Lane[] => {
  const steps = spans.filter(isStep)
  if (!steps.length) {
    const roots = spans.filter((span) => !span.parent_id)
    return roots.length ? [{ round: null, spans: roots }] : []
  }
  const rounds = [...new Set(steps.map(roundOf))].sort((a, b) => (a ?? -1) - (b ?? -1))
  return rounds.map((round) => ({ round, spans: steps.filter((span) => roundOf(span) === round) }))
}

export interface Row {
  op: Operation
  depth: number
  ticks: Operation[]
}

/** A selected span's subtree in document order, span rows with their own requests as ticks; at most `limit` rows,
    the rest counted. */
export const waterfall = (
  report: Report,
  selected: ReadonlySet<string>,
  limit = 120,
): { rows: Row[]; more: number } => {
  const children = new Map<string, Operation[]>()
  for (const span of report.spans) {
    if (span.parent_id) children.set(span.parent_id, [...(children.get(span.parent_id) ?? []), span])
  }
  const ticks = new Map<string, Operation[]>()
  for (const row of report.attempts) {
    if (row.parent_id) ticks.set(row.parent_id, [...(ticks.get(row.parent_id) ?? []), row])
  }
  const rows: Row[] = []
  let more = 0
  const walk = (span: Operation, depth: number): void => {
    if (rows.length >= limit) {
      more += 1
      return
    }
    rows.push({ op: span, depth, ticks: ticks.get(span.id) ?? [] })
    for (const child of (children.get(span.id) ?? []).sort((a, b) => startOf(a) - startOf(b))) walk(child, depth + 1)
  }
  for (const span of report.spans.filter((span) => selected.has(span.id)).sort((a, b) => startOf(a) - startOf(b))) walk(span, 0)
  return { rows, more }
}

/** Fraction of the window an operation spans, clamped to it. */
export const place = (row: Operation, window: Window, now: number): { left: number; width: number } => {
  const span = Math.max(1, window.end - window.start)
  const start = Math.max(window.start, startOf(row))
  const end = Math.min(window.end, Math.max(start, endOf(row, now, window.end)))
  return { left: (start - window.start) / span, width: Math.max((end - start) / span, 0.0015) }
}

/* ---- formatting ------------------------------------------------------------ */

export const money = (value: number | null | undefined): string =>
  value == null ? 'unknown' : value === 0 ? '$0' : value < 0.01 ? `$${value.toFixed(4)}` : value < 100 ? `$${value.toFixed(2)}` : `$${Math.round(value).toLocaleString()}`

export const compact = (value: number | null | undefined): string =>
  value == null ? 'unknown' : value < 10_000 ? value.toLocaleString() : value < 1_000_000 ? `${(value / 1_000).toFixed(value < 100_000 ? 1 : 0)}k` : `${(value / 1_000_000).toFixed(2)}M`

export const seconds = (ms: number | null | undefined): string => {
  if (ms == null) return 'unknown'
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(s < 10 ? 1 : 0)} s`
  if (s < 3600) return `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`
  return `${Math.floor(s / 3600)} h ${Math.round((s % 3600) / 60)} min`
}

export const percent = (part: number | null, whole: number | null): string =>
  part == null || !whole ? '' : `${Math.round((part / whole) * 100)}%`

export const clock = (iso: string): string => {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

/** Where the money went, as shares of the known total; parts with unknown cost are listed but take no width. */
export const shares = (rows: Breakdown[]): { key: string; share: number; cost: Known }[] => {
  const total = rows.reduce((sum, row) => sum + (row.cost.value ?? 0), 0)
  return rows.map((row) => ({ key: row.key, share: total && row.cost.value != null ? row.cost.value / total : 0, cost: row.cost }))
}
