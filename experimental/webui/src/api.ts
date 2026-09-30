import { normalizeRecord } from './record'

import type { HousedHome } from './harness'
import type { LiveReply } from './live'
import type { Run, RunEntry, Scenario } from './model'
import type { NodeProcess, ProcessSource } from './process'
import type { CultivationRecord } from './record'

/* A refused request's own words when the server gave them, such as a run record that failed to load. */
async function read<T>(path: string): Promise<T> {
  const response = await fetch(path)
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { error?: unknown } | null
    throw new Error(typeof body?.error === 'string' ? body.error : `${path}: ${response.status}`)
  }
  return (await response.json()) as T
}

export const NO_SCENARIO: Scenario = { criteria: [], initial: [], materials: [] }

export const listRuns = (): Promise<RunEntry[]> => read('/api/runs')
export const loadRun = (id: string): Promise<Run> => read(`/api/runs/${id}`)
export const fileUrl = (path: string): string => `/files?path=${encodeURIComponent(path)}`

/* The page works without a scenario: an older server answers this path with the
   page itself, and a run from another scenario simply has no red lines marked. */
export async function loadScenario(): Promise<Scenario> {
  try {
    const value = await read<Partial<Scenario>>('/api/scenario')
    return {
      criteria: Array.isArray(value.criteria) ? value.criteria : [],
      initial: Array.isArray(value.initial) ? value.initial : [],
      materials: Array.isArray(value.materials) ? value.materials : [],
    }
  } catch {
    return NO_SCENARIO
  }
}

export const thumbsUrl = (path: string): string => `/api/thumbs?path=${encodeURIComponent(path)}`
export const uploadThumbsUrl = (run: string, path: string): string =>
  `/api/thumbs?run=${encodeURIComponent(run)}&upload=${encodeURIComponent(path)}`
/** A text file or deck the owner uploaded, relative to the run's agent home; the server serves only home/uploads. */
export const uploadUrl = (run: string, path: string): string =>
  `/api/upload?run=${encodeURIComponent(run)}&path=${encodeURIComponent(path)}`

/** Page images of a deck, rendered by the server on first request; `url` is a thumbsUrl or uploadThumbsUrl. */
export async function loadThumbs(url: string): Promise<string[]> {
  const response = await fetch(url)
  const body = (await response.json().catch(() => ({}))) as { pages?: string[]; error?: string }
  if (!response.ok || !Array.isArray(body.pages)) throw new Error(body.error ?? `thumbnails: ${response.status}`)
  return body.pages
}

export async function loadText(url: string): Promise<string> {
  const response = await fetch(url)
  if (!response.ok) throw new Error(`${url}: ${response.status}`)
  return response.text()
}

/** New rows of a run's worker logs since each one's offset in `logs` (live.ts cursorOf); a log without one starts
    from a fresh tail. */
export const loadLive = (run: string, logs: string): Promise<LiveReply> =>
  read(`/api/live?run=${encodeURIComponent(run)}${logs ? `&logs=${encodeURIComponent(logs)}` : ''}`)

export interface NodeQuery {
  /** Counts and the last step only, for a node card's running tally. */
  summary?: boolean
  source?: ProcessSource | 'auto'
  attempt?: number | null
}

export function nodeUrl(run: string, dag: string, node: string, query: NodeQuery = {}): string {
  const params = new URLSearchParams({ run, dag, node })
  if (query.summary) params.set('summary', '1')
  if (query.source && query.source !== 'auto' && query.source !== 'none') params.set('source', query.source)
  if (query.attempt) params.set('attempt', String(query.attempt))
  return `/api/node?${params.toString()}`
}

/** The error the server gives for a node it cannot find in the run's traces, as opposed to a missing endpoint. */
export const NO_SUCH_NODE = 'no such node'

/** One playbook node's process: its steps, prompt, output and verdicts, read by the server from the run's traces. */
export async function loadNodeProcess(run: string, dag: string, node: string, query: NodeQuery = {}): Promise<NodeProcess> {
  const path = nodeUrl(run, dag, node, query)
  const response = await fetch(path)
  const body = (await response.json().catch(() => ({}))) as NodeProcess & { error?: string }
  if (!response.ok) throw new Error(body.error === NO_SUCH_NODE ? NO_SUCH_NODE : `${path}: ${response.status}`)
  return body
}

/** The housed sub-harness homes of a run, as the record keeps them now. */
export const loadSubharnesses = (run: string): Promise<HousedHome[]> =>
  read<{ homes?: HousedHome[] }>(`/api/subharnesses?run=${encodeURIComponent(run)}`).then((body) => (Array.isArray(body.homes) ? body.homes : []))

/** The error /api/record gives while experimental/simulation/record.py cannot be imported. */
export const RECORD_UNAVAILABLE = 'record builder not available'

export type RecordReply =
  | { ok: true; record: CultivationRecord }
  | { ok: false; status: number; error: string; detail?: string }

/* An older server answers /api/record with the page itself or "unknown endpoint";
   either reads as a server that predates this view. */
export async function loadRecord(run: string): Promise<RecordReply> {
  const response = await fetch(`/api/record?run=${encodeURIComponent(run)}`)
  const body = (await response.json().catch(() => null)) as Record<string, unknown> | null
  if (!body) return { ok: false, status: response.status, error: 'not answered', detail: 'The server did not answer /api/record with JSON; a server started before this view existed needs a restart.' }
  if (!response.ok || typeof body.error === 'string') {
    const error = typeof body.error === 'string' ? body.error : `${response.status}`
    const detail = error === 'unknown endpoint' ? 'The server predates the Record view; restart it.' : typeof body.detail === 'string' ? body.detail : undefined
    return { ok: false, status: response.status, error, detail }
  }
  return { ok: true, record: normalizeRecord(body) }
}

export interface Bundle {
  name: string
  path: string
  kind: 'folder' | 'archive'
  modified: number
  size: number
  count: number
  files: string[]
}

/** One run of a mining session, as the suite ranked it by the value judge's score. */
export interface MiningRun {
  label: string
  /** The simulation arguments that set the run's disclosure plan. */
  plan: string[]
  name: string
  status?: string
  rounds?: number
  stopped?: string | null
  spend?: number | null
  value: { verdict?: string; score?: number; cases?: number } | null
}

export interface MiningSession {
  file: string
  modified: number
  spend?: number | null
  ranking: MiningRun[]
}

/** The mining summaries in the runs root, newest first; none when the server predates them. */
export async function loadMining(): Promise<MiningSession[]> {
  try {
    const value = await read<{ sessions?: MiningSession[] }>('/api/mining')
    return Array.isArray(value.sessions) ? value.sessions : []
  } catch {
    return []
  }
}

/** Where the newest exported bundle of a run is; the exporter writes it under <run dir>/record/, the page never does. */
export async function loadBundle(run: string): Promise<{ folder: string; bundle: Bundle | null } | null> {
  try {
    const value = await read<{ folder?: string; bundle?: Bundle | null }>(`/api/record/export?run=${encodeURIComponent(run)}`)
    return { folder: value.folder ?? '', bundle: value.bundle ?? null }
  } catch {
    return null
  }
}
