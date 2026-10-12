/* The Studio's reads from experimental/webui/serve.py: the run list the viewer
   also uses, a run with its model inputs cut down (studio.py), one kept
   record on request, and, when the server was started with a live
   configuration, the live sessions (live.py): what a session starts from,
   one session as the page polls it, and the steps the person takes. */

import { T } from './copy'

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

/** A material the person may hand over, as the handover it becomes, with where it came from when the counterpart did not
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
  /** The saved version the session started from, when not the clean baseline. */
  start?: string | null
  /** The session's run id (`<session>/<record>`) once its process opened the record. */
  run: string | null
  status: RunStatus | null
  models: Record<string, string>
  /** A process of this server is serving the session. */
  attached: boolean
  step: string | null
  /** The scenario built on the page the session works in; absent for the configured one. */
  scenario?: string | null
  /** The session has a saved employee that can be downloaded. */
  exportable?: boolean
  /** The step whose failure ended the run and may be taken again on the round it recorded, and why it failed. */
  retry?: { step: 'analyse' | 'assess'; error: string } | null
}

/** A scenario sessions may start in: the configured one, or one built on the page. */
export interface LiveScenario {
  name: string
  title: string
  task: string
  built: boolean
  materials: LiveMaterial[]
  scripts: LiveScript[]
}

/** What the person gives to build a scenario on the page. */
export interface ScenarioDraft {
  title: string
  profile: string
  files: { name: string; text: string }[]
  practice: string[]
  exam: string[]
  checks: string[]
}

/** One of the scenario's scripts: a practice script plays as a trial of the round, an exam script only in the exam. */
export interface LiveScript {
  name: string
  title: string
  exam: boolean
  steps: number
}

/** A saved version a new session may start from, with the job it was cultivated on. */
export interface LiveVersion {
  name: string
  task: string
}

export interface LiveInfo {
  enabled: true
  scenario: string
  /** The scenario's profile, the task a new session starts from unless the person writes another. */
  task: string
  materials: LiveMaterial[]
  settings: { rounds: number; turns: number; curator: string | null; analyst: string | null; standard: boolean }
  scripts?: LiveScript[]
  versions?: LiveVersion[]
  /** Every scenario offered, the configured one first. */
  scenarios?: LiveScenario[]
  sessions: LiveSummary[]
}

/** An exam's score of one version. */
export interface ExamScore {
  failed: number
  judged: number
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

/** The AI's draft of the next message of the trial the person holds: still being drafted, drafted, or why not. */
export interface LiveQuestion {
  trial: string
  /** When it was asked for or answered, in seconds; a new draft has a new one. */
  at: number
  busy?: boolean
  message?: string
  /** What the message tests and what a good answer does, for the person alone. */
  aim?: string
  good?: string
  error?: string
}

/** One answer to a proposed check: how a reply would read, and the rule that answer stands for. */
export interface LiveOption {
  example: string
  rule: string
}

/** A matter the person has not settled, put by the AI as a choice between two answers; `chosen` once settled. */
export interface LiveProposal {
  topic: string
  why: string
  options: LiveOption[]
  chosen: { option: number | null; rule: string } | null
}

/** The AI's latest proposal of acceptance checks: still being made, made, or why not. */
export interface LiveProposals {
  at: number
  busy?: boolean
  error?: string
  items?: LiveProposal[]
}

/** What the session's process reports: the step under way, the loop's status and what it would do next. */
/** A question the person asked the Analyst or the Curator about its step of a round, and the answer, which comes from
    what that step recorded and changes nothing. */
export interface LiveInquiry {
  role: 'analyst' | 'curator'
  /** The round asked about; 0 is the onboarding. */
  round: number
  question: string
  at: number
  busy?: boolean
  answer?: string
  error?: string
}

/** A point the information preparation asks the person before the onboarding curation; skipped, it keeps its
    `assumption`. */
export interface CollectorQuestion {
  id: string
  dimension: string
  question: string
  reason: string
  proposal?: string | null
  assumption?: string
}

export interface LiveInformation {
  /** The questions waiting for the person, all at once. */
  questions: CollectorQuestion[]
  asked: (CollectorQuestion & { answer: string | null })[]
}

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
  /** An automatic assessor already assessed the round in progress. */
  assessed?: boolean
  /** The scripted trials under way, each with the steps it has played. */
  scripts?: { name: string; done: number; steps: number }[]
  /** The exam score of the installed version and of the one before the last curation; null without exam scripts. */
  exam?: { current: ExamScore | null; previous: ExamScore | null } | null
  /** The installed revision, which names the version once a curation installed it. */
  revision?: string | null
  /** The version before the last curation can be put back. */
  revertible?: boolean
  /** The AI question asked for in the trial the person holds. */
  question?: LiveQuestion | null
  /** The checks the AI proposed last, and the rules the person settled, which every automatic assessment applies. */
  proposals?: LiveProposals | null
  adopted?: string[]
  /** The questions asked about the steps of this session, oldest first. */
  inquiries?: LiveInquiry[]
  /** The information preparation's questions; null when the session prepares none. */
  information?: LiveInformation | null
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

export const createLive = (title: string, task: string, version?: string, scenario?: string): Promise<LiveSummary> =>
  post('/api/studio/live', { title, task, ...(version ? { version } : {}), ...(scenario ? { scenario } : {}) })

export const buildScenario = (draft: ScenarioDraft): Promise<LiveScenario> => post('/api/studio/live/scenarios', draft)

/** Take one of the Session's steps; a step the session refused answers with `ok: false` and its reason. */
export const liveStep = (id: string, op: string, body: Record<string, unknown> = {}): Promise<StepReply> =>
  post(`/api/studio/live/${encodeURIComponent(id)}/${op}`, body)

/** Download the saved employee, keeping a refused request out of the browser's downloads. */
export async function exportLive(id: string): Promise<void> {
  const path = `/api/studio/live/${encodeURIComponent(id)}/export`
  const response = await fetch(path, { credentials: 'same-origin' })
  if (!response.ok || response.headers.get('Content-Type')?.split(';')[0].trim().toLowerCase() !== 'application/zip') {
    const value = await response.json().catch(() => ({})) as { error?: string }
    throw new Error(value?.error ?? (response.ok ? T.exportInvalid : `${path}: ${response.status}`))
  }
  const filename = response.headers.get('Content-Disposition')?.match(/(?:^|;)\s*filename="?([^";]+)"?/i)?.[1]
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filename && /^[a-z\d][a-z\d._-]*\.zip$/i.test(filename) ? filename : 'employee.zip'
  link.hidden = true
  document.body.append(link)
  try {
    link.click()
  } finally {
    link.remove()
    // The browser must start reading the blob before it is released.
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
}
