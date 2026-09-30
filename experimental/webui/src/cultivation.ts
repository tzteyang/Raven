/* The cultivation conversation, built from a joined run: the owner's onboarding,
   then per round its remark after the trial, the Analyst's requirements and the
   Curator's reply, which is its attribution of every input and the revision it
   made from it. Section 5 of experimental/simulation/BRIEF.md describes the
   exchange. */

import { attributionOf, attributionsOf, grounded, heldOf, materialOf } from './attribution'
import { failure, roundRecords, roundVersions, trialsOf } from './derive'
import { hooks, referenced, strategyOf } from './mechanism'
import { evidence } from './trial'

import type { AttributionView } from './attribution'
import type { Revision } from './derive'
import type { Hook, Strategy } from './mechanism'
import type { Evidence } from './trial'
import type { Curation, Diagnosis, Feedback, Handover, Question, Run, Selection, Signal, Treatment } from './model'

export type Entry =
  | { kind: 'onboarding'; task: string; opening: Signal[] }
  | { kind: 'remark'; round: number; version: string; signals: Signal[]; holdout: Signal[]; heldOut: string[] }
  | { kind: 'requirements'; round: number; feedback: Feedback; held: Record<string, boolean | null> }
  | { kind: 'reply'; reply: Reply }
  | { kind: 'silence'; round: number | null; text: string }

export interface ChangeView {
  target: string
  strategy: Strategy | null
  treatment: Treatment | null
  reason: string
  expected: string
  verification: string
  /** The inputs the selection grounded this target on. */
  addresses: string[]
  /** The binding value this revision authored for the target, when its artifact carries one. */
  value: unknown
  /** What the binding switches on: its factory and host consumers. */
  hooks: Hook[]
  /** Generated modules the binding names. */
  files: string[]
  /** Whether the host check bound this target when it validated the revision. */
  bound: boolean
  /** Call records for the target in the first trial of the version this revision produced. */
  evidence: Evidence | null
}

/** A material handed over just before a revision, with its diagnosis and the targets grounded on it. */
export interface Intake {
  name: string
  kind: string
  files: string[]
  diagnosis: Diagnosis | null
  targets: string[]
}

export interface Reply {
  revision: Revision
  /** Materials handed over just before this revision, by the opening or with the round's remark. */
  handover: Intake[]
  /** Materials pasted into the remark rather than attached. */
  pasted: string[]
  /** The version the employee was on before this revision. */
  from: string
  /** 1-based round that first tried the version this revision produced; null when none has yet. */
  trial: number | null
  attribution: AttributionView | null
  selection: Selection | null
  understanding: string
  design: string
  changes: ChangeView[]
  failure: string | null
  files: Record<string, string>
}

export interface Pasted {
  title: string
  text: string
}

const RULE = /^\s*---\s*$/
const HEADING = /^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$/

/* In the dialog delivery each material handed over later is pasted after the
   remark, behind a line holding only ---, and opens with its own heading. A ---
   inside a pasted material that no heading follows is a rule within it. */
export function splitRemark(text: string): { remark: string; pasted: Pasted[] } {
  const parts: string[][] = [[]]
  const lines = text.split('\n')
  lines.forEach((line, i) => {
    if (RULE.test(line)) {
      const next = lines.slice(i + 1).find((row) => row.trim())
      if (parts.length === 1 || (next !== undefined && HEADING.test(next))) {
        parts.push([])
        return
      }
    }
    parts[parts.length - 1].push(line)
  })
  const [remark, ...rest] = parts.map((part) => part.join('\n').trim())
  const pasted = rest.filter(Boolean).map((body, i) => ({
    title: body.split('\n').map((row) => HEADING.exec(row)?.[1]).find(Boolean) ?? `Pasted material ${i + 1}`,
    text: body,
  }))
  return { remark, pasted }
}

const BLOCK = /^\s*([-*+]\s|\d+[.)]\s|#|>|\||```)/
const FENCE = /^\s*```/

/** Prose hard-wrapped at a fixed width, joined back into paragraphs. Blank lines, list items, headings, quotes,
    table rows and fenced code keep their breaks; a list item's continuation joins its item. */
export function unwrap(text: string): string {
  const out: string[] = []
  let fenced = false
  for (const line of text.split('\n')) {
    const prev = out[out.length - 1]
    if (FENCE.test(line)) fenced = !fenced
    const join = !fenced && !FENCE.test(line) && prev !== undefined && prev.trim() !== '' && line.trim() !== '' &&
      !BLOCK.test(line) && !/^\s*(#|\||>|```)/.test(prev)
    if (join) out[out.length - 1] = `${prev.trimEnd()} ${line.trim()}`
    else out.push(line)
  }
  return out.join('\n')
}

/** The materials a round's signals handed over. */
export const handovers = (signals: Signal[]): Handover[] => signals.flatMap((signal) => signal.attachments ?? [])

/** What a round's owner handed over, by name: the materials attached to its signals and those pasted into its remark. */
export function handedOver(signals: Signal[]): string[] {
  return [
    ...handovers(signals).map((item) => item.name),
    ...signals.flatMap((signal) => (signal.source === 'agency' ? splitRemark(signal.text).pasted.map((item) => item.title) : [])),
  ]
}

function reply(run: Run, revision: Revision, from: string, versions: string[], signals: Signal[]): Reply {
  const curation: Curation = revision.curation
  const generated = curation.generated
  const artifact = generated?.candidate.artifact ?? { values: {}, files: {} }
  const trial = revision.deployed ? trialsOf(revision.label, versions)[0] ?? null : null
  const records = trial ? roundRecords(run.rounds[trial - 1]) : []
  const bound = new Set(
    (generated?.validation.observations ?? []).filter((row) => row.kind === 'runtime.bound').flatMap((row) => row.targets ?? []),
  )
  const attribution = attributionOf(curation, attributionsOf(run, revision.round ?? 0), generated)
  const selection = generated?.candidate.selection ?? null
  const grounds = grounded(selection)
  const changes = (generated?.candidate.plan.changes ?? []).map((change): ChangeView => {
    const value = artifact.values[change.target]
    return {
      target: change.target,
      strategy: strategyOf(change.target),
      treatment: change.treatment ?? null,
      reason: change.reason,
      expected: change.expected,
      verification: change.verification,
      addresses: grounds.targets[change.target] ?? [],
      value,
      hooks: hooks(change.target, value),
      files: referenced(value, artifact.files),
      bound: bound.has(change.target),
      evidence: trial ? evidence(change.target, records) : null,
    }
  })
  const diagnosed = new Map((attribution?.diagnoses ?? []).map((diagnosis) => [materialOf(diagnosis.about), diagnosis]))
  return {
    revision,
    handover: handovers(signals).map((item) => ({
      ...item,
      diagnosis: diagnosed.get(item.name) ?? null,
      targets: grounds.by[`material:${item.name}`] ?? [],
    })),
    pasted: signals.flatMap((signal) => (signal.source === 'agency' ? splitRemark(signal.text).pasted.map((item) => item.title) : [])),
    from,
    trial,
    attribution,
    selection,
    understanding: generated?.candidate.plan.understanding ?? '',
    design: generated?.candidate.plan.design ?? '',
    changes,
    failure: failure(curation),
    files: artifact.files,
  }
}

const SILENCE: Record<string, string> = {
  continue: 'kept the employee as it is and ran another trial',
  supplement: 'asked for more evidence before changing anything',
  clarify: 'asked for clarification before changing anything',
  stop: 'stopped the run',
}

const asked = (question: Question): string =>
  `The Curator reported a gap at its ${question.stage} stage and revised nothing; its question waits for whoever can answer it: ${question.question}`

export function timeline(run: Run, all: Revision[]): Entry[] {
  const versions = roundVersions(run, all)
  const opening = run.opening ?? []
  const questions = run.questions ?? []
  const entries: Entry[] = [{ kind: 'onboarding', task: run.task, opening }]
  let current = 'v0'
  const push = (revision: Revision, signals: Signal[]) => {
    entries.push({ kind: 'reply', reply: reply(run, revision, current, versions, signals) })
    current = revision.label
  }
  const onboarding = all.filter((rev) => rev.round === null)
  onboarding.forEach((revision) => push(revision, opening))
  for (const question of questions.filter((item) => item.round === 0)) entries.push({ kind: 'silence', round: null, text: asked(question) })
  if (!onboarding.length && !questions.some((item) => item.round === 0)) {
    entries.push({
      kind: 'silence',
      round: null,
      text: run.curator === 'untouched'
        ? 'Control arm: no Curator takes part, so the employee works on its baseline (v0) with the materials alone.'
        : 'No onboarding revision was recorded; the employee starts on its baseline (v0).',
    })
  }
  run.rounds.forEach((round, i) => {
    const number = i + 1
    entries.push({
      kind: 'remark',
      round: number,
      version: versions[i],
      signals: round.signals,
      holdout: round.holdout_signals ?? [],
      heldOut: Object.keys(round.holdout ?? {}),
    })
    if (round.feedback) entries.push({ kind: 'requirements', round: number, feedback: round.feedback, held: heldOf(run, number) })
    const replies = all.filter((rev) => rev.round === number)
    replies.forEach((revision) => push(revision, round.signals))
    const gaps = questions.filter((item) => item.round === number)
    for (const question of gaps) entries.push({ kind: 'silence', round: number, text: asked(question) })
    if (replies.length || gaps.length) return
    const text = !round.feedback
      ? 'The Analyst did not complete this round, so the Curator made no revision.'
      : round.curated
        ? run.status === 'running' && number === run.rounds.length
          ? 'The Curator is revising the Harness.'
          : 'The Curator recorded no revision for this round.'
        : round.feedback.decision === 'curate'
          ? 'No revision: this was the last round, and no later round would test one.'
          : `No revision: the Analyst ${SILENCE[round.feedback.decision] ?? round.feedback.decision}.`
    entries.push({ kind: 'silence', round: number, text })
  })
  return entries
}
