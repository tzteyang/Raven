/* A recorded automated run read as a Studio thread. The loop runs trial,
   assessment, analysis and curation; the thread cuts the same ring where a
   person would: the assessor's review is the change request (the automatic
   standard assessor's is a scorecard), the Analyst and the Curator answer it
   in one background card, the next round's drills are the trials of the
   version it installed, and the loop's own decision to go on stands where a
   person would choose to continue or archive. A round's held-out drills and
   their assessment sit beside its trials, marked as never read by the Analyst
   or the Curator; the round still in progress shows its recorded trials. */

import { attributionOf, attributionsOf, grounded, heldOf } from '../attribution'
import { BASELINE, revisions, roundVersions } from '../derive'
import { T } from './copy'
import { curationView } from './curation'
import { EMPTY_STATE } from './harness'

import type { AttributionView } from '../attribution'
import type { Curation, Exchange, RecordRow, Round, Run, RunEntry, Signal } from '../model'
import type { Entry, Footer, HarnessState, Observed, ObservedLists, ProcessEntry, Recorded, Scope, Thread, TrialView } from './types'

export function speaker(source: string): { name: string; you: boolean } {
  if (source === 'human' || source === 'user') return { name: T.speakerYou, you: true }
  if (source === 'agency') return { name: T.speakerOwner, you: false }
  return { name: T.speakerAssessor(source), you: false }
}

/* The standard assessor has no voice of its own, so its signal is a
   scorecard; every other signal is a request in the speaker's words. */
export function requests(run: Run, signals: Signal[], round: number, onboarding: boolean, holdout = false): Entry[] {
  return signals.map((signal, i): Entry => {
    if (signal.source === 'standard' || holdout) {
      return { kind: 'score', key: `score-${round}-${holdout ? 'h' : ''}${i}`, round, signal, criteria: run.standard?.criteria ?? [], holdout }
    }
    const who = speaker(signal.source)
    return {
      kind: 'request',
      key: `req-${round}-${i}`,
      round,
      speaker: who.name,
      you: who.you,
      text: signal.text,
      attachments: signal.attachments ?? [],
      onboarding,
    }
  })
}

/* An assessor that keeps a private scorecard writes it under the run's
   analysis folder beside the Analyst's record; the Analyst's own record is the
   one with a generation trace. */
function assessorRecords(round: Round): unknown[] {
  return round.analysis.filter((record) => {
    const row = record as unknown as Record<string, unknown>
    return !Array.isArray(row.trace) || 'scorecard' in row || 'shortfalls' in row
  })
}

const STOPS: [RegExp, string][] = [
  [/^the analyst stopped the run/, T.stops.analyst],
  [/^every (assessor|evaluator) is satisfied/, T.stops.satisfied],
  [/^no (assessor|evaluator) produced a signal/, T.stops.silent],
  [/^rounds exhausted/, T.stops.exhausted],
]

export function stopText(stop: string | undefined): string {
  if (!stop) return ''
  const hit = STOPS.find(([pattern]) => pattern.test(stop))
  return T.runEnded(hit ? hit[1] : stop)
}

export function trialsOf(sessions: Record<string, Exchange[]>, number: number, version: string, how: { holdout?: boolean; pending?: boolean } = {}): TrialView[] {
  return Object.entries(sessions).map(([key, exchanges]) => ({
    id: `${number}:${how.holdout ? 'holdout:' : ''}${key}`,
    title: how.holdout ? T.trialHeldOut(key) : T.trialFrom(key),
    version,
    status: how.pending ? 'running' : 'done',
    exchanges,
    source: 'recorded',
    holdout: how.holdout,
  }))
}

const escaped = (text: string): string => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/* Child harness executions inside a turn's records, the way
   experimental/curator/composition/context.py child_observations finds them:
   a child.execution row is taken whole and not entered, any other row with
   records is entered. */
function childRuns(records: RecordRow[], found: string[] = []): string[] {
  for (const row of records) {
    if (row.kind === 'child.execution') found.push(String(row['harness'] ?? ''))
    else if (Array.isArray(row['records'])) childRuns(row['records'] as RecordRow[], found)
  }
  return found
}

/* The observations a round's curation reads by index, rebuilt the way the loop
   handed them over. The root gets the turns a requirement's evidence or
   observation names by turn id, in session order, each under its session's
   opaque label, which the server supplies as `labels` since the loop's rule
   (experimental/iteration/hearing.py opaque, cited, heard_observations) is a
   hash the page does not recompute. A child gets its own current execution
   first, then its executions inside those cited turns
   (experimental/curator/composition/run.py and context.py). With no feedback
   there are none. */
export function observedOf(round: Round, labels: Record<string, string> = {}): ObservedLists | null {
  const feedback = round.feedback
  if (!feedback) return null
  const text = feedback.requirements.map((requirement) => [...requirement.evidence, requirement.observed].join(' ')).join(' ')
  const root: Observed[] = []
  const children: Record<string, Observed[]> = {}
  Object.entries(round.sessions).forEach(([session, exchanges]) => {
    exchanges.forEach((exchange, turn) => {
      const id = exchange.execution.turn_id
      if (!id || !new RegExp(`(?<![\\w-])${escaped(id)}(?![\\w-])`).test(text)) return
      const observed: Observed = { kind: 'turn', session, turn, user: exchange.user, label: labels[session] ?? '' }
      root.push(observed)
      for (const harness of childRuns(exchange.execution.records)) (children[harness] ??= []).push(observed)
    })
  })
  const current: Observed = { kind: 'current', session: '', turn: -1, user: '', label: 'execution.current' }
  return { root, children: Object.fromEntries(Object.entries(children).map(([name, rows]) => [name, [current, ...rows]])) }
}

/** What one card's attribution and selection say of each input, for the ledger pane to set beside the history. */
function recordedOf(number: number, attribution: AttributionView | null, scope: Scope | undefined, into: Record<string, Recorded>): void {
  const targets = grounded(scope?.selection).targets
  const treatments = new Map((scope?.plan?.changes ?? []).map((change) => [change.target, change.treatment ?? null]))
  for (const diagnosis of attribution?.diagnoses ?? []) {
    const changes = Object.entries(targets)
      .filter(([, abouts]) => abouts.includes(diagnosis.about))
      .map(([target]) => ({ target, treatment: treatments.get(target) ?? null }))
    into[`${number}:${diagnosis.about}`] = { state: diagnosis.state, changes }
  }
}

export function replayThread(id: string, run: Run, entry?: RunEntry): Thread {
  const all = revisions(run)
  const byCuration = new Map<Curation, (typeof all)[number]>()
  let index = 0
  for (const curation of run.initial_curation ?? []) byCuration.set(curation, all[index++])
  for (const round of run.rounds) for (const curation of round.curation) byCuration.set(curation, all[index++])
  const questions = run.questions ?? []
  const running = (run.status ?? entry?.status) === 'running'
  const recorded: Record<string, Recorded> = {}

  let state: HarnessState = EMPTY_STATE
  let current = BASELINE
  const versions = [BASELINE]
  const entries: Entry[] = [
    {
      kind: 'head',
      key: 'head',
      task: run.task,
      baseline: entry?.name ?? id,
      models: entry?.models ?? {},
    },
  ]

  const curate = (curation: Curation, number: number, round?: Round) => {
    const rev = byCuration.get(curation)
    const from = current
    const deployed = !!rev?.deployed
    const view = curationView(curation, state, from, deployed ? rev!.label : from, deployed, round ? observedOf(round, run.labels) : null, attributionsOf(run, number))
    if (deployed) {
      state = view.after
      current = rev!.label
      versions.push(current)
    }
    return view
  }

  /* A card's end: what the curation came to, or why there was none. */
  const ending = (number: number, view: ReturnType<typeof curate> | null, curated: boolean, last: boolean): Footer | null => {
    const question = questions.find((item) => item.round === number)
    if (question) return { kind: 'asked', version: current, stage: question.stage, question: question.question }
    if (view?.paused) return { kind: 'paused', version: current, stage: view.paused.stage, scope: view.paused.scope, reason: view.paused.reason }
    if (view) return view.deployed ? { kind: 'deployed', version: view.to } : { kind: 'kept', version: view.from, reason: view.error ?? '' }
    if (curated && last && running) return { kind: 'curating', version: `v${versions.length}` }
    if (curated && last && run.status === 'error') return { kind: 'failed', version: current, error: run.error ?? '' }
    if (curated && last && run.status === 'paused') return { kind: 'paused', version: current, stage: null, scope: 'root', reason: run.stop ?? '' }
    return null
  }

  entries.push(...requests(run, run.opening ?? [], 0, true))
  const onboarding = run.initial_curation ?? []
  const attributions = attributionsOf(run, 0)
  const cards = onboarding.length ? onboarding : run.rounds.length === 0 && (attributions.length || running || run.status !== 'finished') ? [null] : []
  for (const curation of cards) {
    const view = curation ? curate(curation, 0) : null
    const footer = ending(0, view, true, run.rounds.length === 0) ?? { kind: 'kept', version: current, reason: '' }
    recordedOf(0, view?.scopes[0].attribution ?? attributionOf(null, attributions), view?.scopes[0], recorded)
    entries.push({
      kind: 'process',
      key: 'proc-0',
      round: 0,
      onboarding: true,
      analysis: 'none',
      feedback: null,
      signals: run.opening ?? [],
      assessor: [],
      handover: false,
      held: {},
      curation: view,
      attribution: view ? null : attributionOf(null, attributions),
      curationState: view ? (view.deployed ? 'done' : 'failed') : footer.kind === 'curating' ? 'running' : 'none',
      footer,
    })
  }

  const tried = roundVersions(run, all)
  run.rounds.forEach((round, i) => {
    const number = i + 1
    const last = number === run.rounds.length
    entries.push({ kind: 'trials', key: `trials-${number}`, round: number, version: tried[i], trials: trialsOf(round.sessions, number, tried[i]) })
    if (Object.keys(round.holdout ?? {}).length) {
      entries.push({ kind: 'trials', key: `holdout-${number}`, round: number, version: tried[i], trials: trialsOf(round.holdout ?? {}, number, tried[i], { holdout: true }), holdout: true })
    }
    entries.push({ kind: 'note', key: `auto-${number}`, tone: 'auto', text: T.autoContinue })
    entries.push(...requests(run, round.signals, number, false))
    entries.push(...requests(run, round.holdout_signals ?? [], number, false, true))
    const curation = round.curation[0] ?? null
    const view = curation ? curate(curation, number, round) : null
    const feedback = round.feedback
    const attached = round.signals.some((signal) => (signal.attachments ?? []).length > 0)
    let footer: Footer
    const ended = ending(number, view, round.curated, last)
    if (!feedback) footer = { kind: 'analysis-failed', error: round.analysis.find((a) => a.error)?.error ?? run.error ?? '' }
    else if (ended) footer = ended
    else if (feedback.decision === 'stop') footer = { kind: 'stop', version: current, handoverUnused: attached }
    else if (round.curated) footer = { kind: 'kept', version: current, reason: T.noCurationRecord }
    else if (feedback.decision === 'curate' || attached) footer = { kind: 'last-round', version: current }
    else if (feedback.decision === 'supplement') footer = { kind: 'supplement', version: current, need: feedback.reason }
    else if (feedback.decision === 'clarify') footer = { kind: 'clarify', version: current, question: feedback.reason }
    else footer = { kind: 'continue', version: current }
    const card: ProcessEntry = {
      kind: 'process',
      key: `proc-${number}`,
      round: number,
      onboarding: false,
      analysis: feedback ? 'done' : 'failed',
      feedback,
      signals: round.signals,
      assessor: assessorRecords(round),
      handover: round.curated && !!feedback && feedback.decision !== 'curate',
      held: heldOf(run, number),
      curation: view,
      attribution: view ? null : attributionOf(null, attributionsOf(run, number)),
      curationState: view ? (view.deployed ? 'done' : 'failed') : footer.kind === 'curating' ? 'running' : 'none',
      footer,
    }
    recordedOf(number, view?.scopes[0].attribution ?? card.attribution, view?.scopes[0], recorded)
    entries.push(card)
  })
  const pending = run.pending?.sessions ?? {}
  if (Object.keys(pending).length) {
    const number = run.rounds.length + 1
    entries.push({ kind: 'trials', key: `trials-${number}`, round: number, version: current, trials: trialsOf(pending, number, current, { pending: running }), pending: true })
  }
  const end = stopText(run.stop)
  if (run.status === 'error' && run.error) entries.push({ kind: 'note', key: 'error', tone: 'end', text: T.runFailed(run.error) })
  else if (end) entries.push({ kind: 'note', key: 'end', tone: 'end', text: end })

  return {
    id,
    title: entry?.name ?? id,
    mode: 'replay',
    entries,
    versions,
    current,
    status: run.status ?? entry?.status ?? 'finished',
    source: id,
    history: run.history ?? [],
    ledger: run.ledger ?? null,
    questions,
    standard: run.standard ?? null,
    boundaries: run.boundaries ?? null,
    recorded,
    origins: run.origins ?? {},
  }
}
