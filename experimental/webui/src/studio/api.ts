/* The Studio's reads from experimental/webui/serve.py: the run list the viewer
   also uses, a run with its model inputs cut down (studio.py), one kept
   record on request, and, when the server was started with a live
   configuration, the live sessions (live.py): what a session starts from,
   one session as the page polls it, and the steps the person takes. */

import type { CuratorProgress } from '../live'
import type { Exchange, Handover, MaterialOrigin, Run, RunEntry, RunStatus } from '../model'

export { fileUrl } from '../api'

export interface RawRef {
  round: number
  session: string
  turn: number
  index: number
  /** A record inside the sub-harness execution at `index`. */
  child?: number
}

async function read<T>(path: string): Promise<T> {
  const response = await fetch(path)
  if (!response.ok) throw new Error(`${path}: ${response.status}`)
  return (await response.json()) as T
}

export const listRuns = (): Promise<RunEntry[]> => read('/api/studio/runs')
export const loadStudioRun = (id: string): Promise<Run> => read(`/api/studio/runs/${id}`)

export function loadRaw(run: string, ref: RawRef): Promise<unknown> {
  const params = new URLSearchParams({ run, round: String(ref.round), session: ref.session, turn: String(ref.turn), index: String(ref.index) })
  if (ref.child !== undefined) params.set('child', String(ref.child))
  return read(`/api/studio/raw?${params.toString()}`)
}

/** A material the person may hand over, as the handover it becomes, with where it came from when the party did not
    simply give it. */
export interface LiveMaterial extends Handover {
  origin?: MaterialOrigin
}

/** One kept live session, as the session list names it. */
export interface LiveSummary {
  id: string
  title: string
  task: string
  created: number
  archived: { name: string; version: string | null } | null
  /** The session's run id (`<session>/<record>`) once its process opened the record. */
  run: string | null
  status: RunStatus | null
  models: Record<string, string>
  /** A process of this server is serving the session. */
  attached: boolean
  step: string | null
}

export interface LiveInfo {
  enabled: true
  scenario: string
  /** The scenario's profile, the task a new session starts from unless the person writes another. */
  task: string
  materials: LiveMaterial[]
  settings: { rounds: number; turns: number; curator: string | null; analyst: string | null; standard: boolean }
  sessions: LiveSummary[]
}

/** The trial the person is holding, as the session's process reports it (session_host.py). */
export interface LiveTrial {
  name: string
  exchanges: Exchange[]
  /** What the person said that the employee is answering. */
  said: string | null
  /** The conversation waits for the person. */
  waiting: boolean
}

/** What the session's process reports: the step under way, the loop's status and what it would do next. */
export interface LiveState {
  step: string | null
  /** When the step under way began, in seconds. */
  since: number
  error: string | null
  failed: string | null
  status: RunStatus | null
  onboarded: boolean
  reviewing: boolean
  outcome: { next: 'curate' | 'continue' | 'stop'; reason: string } | null
  rounds: number
  pending: { sessions: number; signals: number } | null
  trial: LiveTrial | null
  assessor: boolean
  ended: boolean
}

export interface LiveSnapshot extends LiveSummary {
  state: LiveState | null
  /** The process did not answer in time; `state` is the last one it gave. */
  busy: boolean
  stamp: string
  /** The Curator's progress file and, for a paused curation, the stage it stopped at. */
  progress: { curation: (CuratorProgress & { scope?: string }) | null; paused: string | null }
  /** The slim record, only when it changed since the stamp the page sent. */
  record?: Run
}

export interface StepReply {
  ok?: boolean
  error?: string
  state?: LiveState
}

/** What a live session starts from, or null when the server serves recorded runs only. */
export async function liveInfo(): Promise<LiveInfo | null> {
  const response = await fetch('/api/studio/live')
  if (response.status === 404) return null
  if (!response.ok) throw new Error(`/api/studio/live: ${response.status}`)
  return (await response.json()) as LiveInfo
}

export const liveSnapshot = (id: string, stamp: string | null): Promise<LiveSnapshot> =>
  read(`/api/studio/live/${encodeURIComponent(id)}${stamp ? `?stamp=${encodeURIComponent(stamp)}` : ''}`)

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  const value = (await response.json().catch(() => ({}))) as T & { error?: string }
  if (!response.ok && response.status !== 409) throw new Error(value.error ?? `${path}: ${response.status}`)
  return value
}

export const createLive = (title: string, task: string): Promise<LiveSummary> => post('/api/studio/live', { title, task })

/** Take one of the Session's steps; a step the session refused answers with `ok: false` and its reason. */
export const liveStep = (id: string, op: string, body: Record<string, unknown> = {}): Promise<StepReply> =>
  post(`/api/studio/live/${encodeURIComponent(id)}/${op}`, body)
