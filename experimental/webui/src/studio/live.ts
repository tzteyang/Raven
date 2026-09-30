/* An interactive cultivation session, stepped by the person on the page and
   run by the server (experimental/webui/live.py and session_host.py): the
   session's process holds the employee and the loop's Session, and each of
   the person's actions is one of the Session's steps. The thread is the
   session's record read the way a recorded run is read (replay.ts), with what
   the record does not hold yet laid over it from the state the process
   reports: the step under way, the trial the person is holding, the remarks
   of the round in progress and the Curator's progress. `livePhase` says what
   the person can do next, and `sendRemark` takes the steps one message
   stands for. */

import { T } from './copy'
import { STAGES } from './curation'
import { replayThread, requests } from './replay'

import type { Exchange, Run, RunEntry } from '../model'
import type { LiveSnapshot, LiveState, LiveSummary, StepReply } from './api'
import type { CurationProgress, Entry, Footer, ProcessEntry, StageId, Thread, TrialView, TrialsEntry } from './types'

export interface LiveSession extends Thread {
  mode: 'live'
  summary: LiveSummary
  state: LiveState | null
  /** The process did not answer the last poll in time; `state` is the last one it gave. */
  busy: boolean
  /** The session's record, once its process opened it. */
  run: Run | null
}

export const processes = (session: Thread): ProcessEntry[] =>
  session.entries.filter((entry): entry is ProcessEntry => entry.kind === 'process')

export const trialsOf = (session: Thread): TrialView[] =>
  session.entries.flatMap((entry) => (entry.kind === 'trials' ? entry.trials : []))

export const openTrials = (session: Thread): TrialView[] => trialsOf(session).filter((trial) => trial.status === 'running')

export function lastFooter(session: Thread): Footer | null {
  const all = processes(session)
  return all.length ? all[all.length - 1].footer : null
}

const TRIAL = /^trial-(\d+)$/
const BUSY = ['onboard', 'trial', 'assess', 'analyse', 'curate']

const trialTitle = (name: string, fallback: string): string => {
  const match = TRIAL.exec(name)
  return match ? T.trialTitle(Number(match[1])) : fallback
}

/** The trial the person holds, with what they said last while the employee answers it. */
function held(state: LiveState, round: number, version: string): TrialView | null {
  const trial = state.trial
  if (!trial) return null
  const answering = !trial.waiting && trial.said !== null
  const said: Exchange[] = answering ? [{ user: trial.said ?? '', execution: { turn_id: '', artifact_id: '', records: [] } }] : []
  return {
    id: `${round}:${trial.name}`,
    title: trialTitle(trial.name, trial.name),
    version,
    status: 'running',
    exchanges: [...trial.exchanges, ...said],
    source: 'live',
    busy: answering,
  }
}

/** Where the curation under way stands, once the Curator's progress file belongs to this step. */
export function progressOf(snapshot: LiveSnapshot): CurationProgress {
  const progress = snapshot.progress.curation
  const since = snapshot.state?.since ?? 0
  if (!progress || progress.finished || progress.started < since - 1) return { stage: 'diagnose', calls: 0, queries: 0, scope: null }
  const stage = (STAGES as string[]).includes(progress.stage ?? '') ? (progress.stage as StageId) : 'diagnose'
  return { stage, calls: progress.calls, queries: progress.queries, scope: progress.scope ?? null }
}

const nextVersion = (versions: string[]): string => `v${versions.length}`

function card(round: number, onboarding: boolean, footer: Footer, extra: Partial<ProcessEntry> = {}): ProcessEntry {
  return {
    kind: 'process',
    key: `proc-${round}`,
    round,
    onboarding,
    analysis: onboarding ? 'none' : 'done',
    feedback: null,
    signals: [],
    assessor: [],
    handover: false,
    held: {},
    curation: null,
    attribution: null,
    curationState: 'none',
    footer,
    ...extra,
  }
}

export function liveThread(snapshot: LiveSnapshot, run: Run | null): LiveSession {
  const state = snapshot.state
  const entry: RunEntry = {
    id: snapshot.run ?? snapshot.id,
    name: snapshot.title,
    task: snapshot.task,
    curator: null,
    passes: [],
    rounds: run?.rounds.length ?? 0,
    status: run?.status ?? 'running',
    error: null,
    recorded: 0,
    models: snapshot.models,
  }
  const base = run ? replayThread(snapshot.run ?? snapshot.id, run, entry) : null
  const versions = base?.versions ?? ['v0']
  const current = base?.current ?? 'v0'
  const head: Entry = { kind: 'head', key: 'head', task: run?.task ?? snapshot.task, baseline: T.liveBaseline, models: snapshot.models }
  let entries: Entry[] = [head, ...(base?.entries.slice(1) ?? [])]
  const step = state?.step ?? null
  const running = snapshot.attached && step !== null && BUSY.includes(step)
  const status = run?.status ?? null

  entries = entries
    .filter((item) => !(item.kind === 'note' && item.tone === 'auto'))
    .filter((item) => !(snapshot.archived && item.kind === 'note' && item.key === 'end'))
    .map((item): Entry =>
      item.kind === 'trials'
        ? { ...item, trials: item.trials.map((trial) => ({ ...trial, source: 'live', status: 'done', title: trialTitle(trial.id.split(':').slice(1).join(':'), trial.title) })) }
        : item,
    )

  const replace = (key: string, change: (item: ProcessEntry) => ProcessEntry | null) => {
    entries = entries.flatMap((item) => {
      if (item.kind !== 'process' || item.key !== key) return [item]
      const next = change(item)
      return next ? [next] : []
    })
  }
  const last = processes({ entries } as Thread).at(-1)

  if (last?.onboarding && !state?.onboarded && step !== 'onboard' && status !== 'paused') replace(last.key, () => null)
  if (step === 'onboard' && !processes({ entries } as Thread).some((item) => item.onboarding)) {
    entries.push(card(0, true, { kind: 'curating', version: nextVersion(versions) }))
  }
  const final = processes({ entries } as Thread).at(-1)
  if (final) {
    const curating = running && (step === 'curate' || (step === 'onboard' && final.onboarding))
    replace(final.key, (item) => {
      if (curating) return { ...item, curationState: 'running', footer: { kind: 'curating', version: nextVersion(versions) }, progress: progressOf(snapshot) }
      if (item.footer.kind === 'paused' && !item.footer.stage && snapshot.progress.paused) {
        return { ...item, footer: { ...item.footer, stage: snapshot.progress.paused } }
      }
      if (item.footer.kind === 'curating' && state?.reviewing && status === 'running') {
        return { ...item, curationState: 'none', footer: { kind: 'review', version: current } }
      }
      if (item.footer.kind === 'curating') return { ...item, curationState: 'none', footer: { kind: 'interrupted', version: current } }
      return item
    })
  }

  const round = (run?.rounds.length ?? 0) + 1
  const pendingKey = `trials-${round}`
  const holding = state && snapshot.attached ? held(state, round, current) : null
  const recorded = entries.find((item): item is TrialsEntry => item.kind === 'trials' && item.key === pendingKey)
  if (holding) {
    if (recorded) entries = entries.map((item) => (item === recorded ? { ...recorded, trials: [...recorded.trials, holding] } : item))
    else entries.push({ kind: 'trials', key: pendingKey, round, version: current, trials: [holding], pending: true })
  }
  const remarks = run?.pending?.signals ?? []
  if (remarks.length) entries.push(...requests(run!, remarks, round, false))
  if (running && step === 'assess') entries.push({ kind: 'note', key: 'assessing', tone: 'choice', text: T.liveAssessing })
  if (running && step === 'analyse') {
    entries.push(card(round, false, { kind: 'analysing' }, { analysis: 'running', signals: remarks }))
  }

  if (state?.failed === 'starting' && state.error) entries.push({ kind: 'note', key: 'failed', tone: 'end', text: T.liveStartFailed(state.error) })
  else if (state?.failed && state.error && status !== 'error') {
    entries.push({ kind: 'note', key: 'failed', tone: 'end', text: T.liveStepFailed(T.liveSteps[state.failed] ?? state.failed, state.error) })
  }
  if (snapshot.archived) {
    entries.push({ kind: 'note', key: 'archive', tone: 'archive', text: T.archivedAs(snapshot.archived.name, snapshot.archived.version ?? current) })
  } else if (!snapshot.attached && run && (status === 'running' || status === 'paused')) {
    entries.push({ kind: 'note', key: 'detached', tone: 'end', text: T.liveGone })
  }

  return {
    ...(base ?? { versions, current, history: [], questions: [], recorded: {}, origins: {} }),
    id: snapshot.id,
    title: snapshot.title,
    mode: 'live',
    entries,
    versions,
    current,
    status: status ?? 'running',
    archived: snapshot.archived ? { name: snapshot.archived.name, version: snapshot.archived.version ?? current } : undefined,
    source: snapshot.run ?? undefined,
    summary: snapshot,
    state,
    busy: snapshot.busy,
    run,
  }
}

/** What the person can do next in a live session. */
export type Phase =
  | { kind: 'starting' }
  | { kind: 'unstarted'; error: string }
  | { kind: 'archived' }
  | { kind: 'ended' }
  | { kind: 'detached' }
  | { kind: 'busy'; step: string }
  | { kind: 'trial' }
  | { kind: 'onboard' }
  | { kind: 'paused'; step: 'onboard' | 'curate' }
  | { kind: 'review' }
  | { kind: 'round'; trials: number; remarks: number }
  | { kind: 'between' }

export function livePhase(session: LiveSession): Phase {
  const state = session.state
  if (session.archived) return { kind: 'archived' }
  if (state?.failed === 'starting') return { kind: 'unstarted', error: state.error ?? '' }
  if (!session.summary.attached) return session.run && (session.status === 'finished' || session.status === 'error') ? { kind: 'ended' } : { kind: 'detached' }
  if (!state || state.step === 'starting') return { kind: 'starting' }
  if (state.status === 'finished' || state.status === 'error' || state.ended) return { kind: 'ended' }
  if (state.trial) return { kind: 'trial' }
  if (state.step) return { kind: 'busy', step: state.step }
  if (state.status === 'paused') return { kind: 'paused', step: state.reviewing ? 'curate' : 'onboard' }
  if (!state.onboarded) return { kind: 'onboard' }
  if (state.reviewing) return { kind: 'review' }
  const trials = state.pending?.sessions ?? 0
  const remarks = state.pending?.signals ?? 0
  return trials || remarks ? { kind: 'round', trials, remarks } : { kind: 'between' }
}

export type Take = (op: string, body?: Record<string, unknown>) => Promise<StepReply>

/** Close the round in progress: the automatic assessor first when it is configured and has not assessed the round,
    then the Analyst. `settle` waits for a background step to end and gives the state it ended in. */
export async function closeRound(take: Take, settle: () => Promise<LiveState | null>, assess: boolean): Promise<StepReply> {
  if (assess) {
    const assessed = await take('assess')
    if (!assessed.ok) return assessed
    const state = await settle()
    if (state?.failed === 'assess') return { ok: false, error: state.error ?? '', state }
  }
  return take('analyse')
}

/** One message from the composer: the onboarding before the session is onboarded, else a remark that joins the round
    in progress and, once the round has a trial, closes it (`closeRound`). */
export async function sendRemark(
  take: Take,
  settle: () => Promise<LiveState | null>,
  message: { text: string; materials: string[]; onboarded: boolean; assess: boolean },
): Promise<StepReply> {
  const body = { text: message.text, materials: message.materials }
  if (!message.onboarded) return take('onboard', body)
  const said = await take('signal', body)
  if (!said.ok || !said.state?.pending?.sessions) return said
  return closeRound(take, settle, message.assess)
}
