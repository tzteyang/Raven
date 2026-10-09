/* The cultivation loop's structure, for the map the Cultivation view opens on: one lap for onboarding and one per
   round, each a fixed row of stations with who acts there, how far the run got and a few facts. Everything is read
   from the same timeline the conversation is built from (cultivation.ts), so the map and the conversation cannot
   disagree; the live phase (serve.py phase) marks the station a running run is at. */

import { handovers, timeline } from './cultivation'
import { STRATEGIES } from './mechanism'
import { trialSummary } from './trial'

import type { Entry, Reply } from './cultivation'
import type { Revision } from './derive'
import type { Run } from './model'

export type StationId = 'handover' | 'version' | 'trial' | 'assess' | 'analyse' | 'diagnose' | 'design' | 'implement'
export type Actor = 'owner' | 'employee' | 'assessors' | 'analyst' | 'curator'
/** `current` is where a running run is; `ahead` is not reached yet; `skipped` was passed over, with the reason in `note`. */
export type StationState = 'done' | 'failed' | 'current' | 'ahead' | 'skipped'

export interface Station {
  id: StationId
  actor: Actor
  label: string
  state: StationState
  facts: string[]
  note: string
}

/** Round 0 is onboarding. */
export interface Lap {
  round: number
  stations: Station[]
  /** The Curator's replies of this lap, in order; a failed revision and a later one can share a round. */
  replies: Reply[]
}

/** The run's phase as /api/phase reports it. */
export interface Phase {
  name: string
  round: number
  stage: string | null
  basis?: string
}

export const ONBOARDING: StationId[] = ['handover', 'diagnose', 'design', 'implement']
export const ROUND: StationId[] = ['version', 'trial', 'assess', 'analyse', 'diagnose', 'design', 'implement']

const ACTOR: Record<StationId, Actor> = {
  handover: 'owner',
  version: 'employee',
  trial: 'employee',
  assess: 'assessors',
  analyse: 'analyst',
  diagnose: 'curator',
  design: 'curator',
  implement: 'curator',
}

export const LABEL: Record<StationId, string> = {
  handover: 'Handover',
  version: 'Version',
  trial: 'Trial',
  assess: 'Assess',
  analyse: 'Analyse',
  diagnose: 'Diagnose',
  design: 'Select · design',
  implement: 'Implement · repair',
}

const STAGE: Record<string, StationId> = {
  diagnose: 'diagnose',
  select: 'design',
  design: 'design',
  implement: 'implement',
  repair: 'implement',
}

/** The station a phase puts a running run at; null for a phase that names none (finished, stalled, unknown). */
export function at(phase: Phase | null): { round: number; station: StationId } | null {
  if (!phase) return null
  switch (phase.name) {
    case 'researching':
      return { round: 0, station: 'handover' }
    case 'curating':
      return { round: phase.round, station: STAGE[phase.stage ?? ''] ?? 'diagnose' }
    case 'trial':
      return { round: phase.round, station: 'trial' }
    case 'judging or analysing':
      return { round: phase.round, station: 'assess' }
    default:
      return null
  }
}

const plural = (count: number, word: string): string => `${count} ${word}${count === 1 ? '' : 's'}`

function curatorFacts(id: StationId, reply: Reply): string[] {
  switch (id) {
    case 'diagnose': {
      const diagnoses = reply.attribution?.diagnoses ?? []
      if (!diagnoses.length) return ['no attribution recorded']
      const counts = new Map<string, number>()
      for (const diagnosis of diagnoses) counts.set(diagnosis.state, (counts.get(diagnosis.state) ?? 0) + 1)
      const top = [...counts].sort((a, b) => b[1] - a[1]).slice(0, 2).map(([state, n]) => `${n} ${state.replace(/_/g, ' ')}`)
      return [plural(diagnoses.length, 'input'), top.join(' · ')]
    }
    case 'design': {
      const strategies = STRATEGIES.filter((name) => reply.changes.some((change) => change.strategy === name))
      return [plural(reply.changes.length, 'target'), strategies.join(' · ')].filter(Boolean)
    }
    default: {
      const files = Object.keys(reply.files).length
      const outcome = reply.revision.deployed ? `installed ${reply.revision.label}` : `failed · stays ${reply.revision.label}`
      return [outcome, files ? plural(files, 'file') : ''].filter(Boolean)
    }
  }
}

/** Every lap of the run, onboarding first, with a lap for the round a running run is trying but has not recorded.
    `entries` is the run's timeline when the caller already holds it. */
export function loopOf(
  run: Run, all: Revision[], versions: string[], red: Set<string>, phase: Phase | null, entries: Entry[] = timeline(run, all),
): Lap[] {
  const running = run.status === 'running'
  const here = running ? at(phase) : null
  const replies = (round: number): Reply[] =>
    entries.flatMap((entry) => (entry.kind === 'reply' && (entry.reply.revision.round ?? 0) === round ? [entry.reply] : []))
  const silence = (round: number): string =>
    entries
      .filter((entry): entry is Extract<Entry, { kind: 'silence' }> => entry.kind === 'silence' && (entry.round ?? 0) === round)
      .map((entry) => entry.text)
      .join(' ')
  const active = [...all].reverse().find((rev) => rev.deployed)?.label ?? 'v0'
  const recorded = run.rounds.length
  const last = Math.max(recorded, here && here.round > recorded ? here.round : 0)

  const lap = (round: number): Lap => {
    const ids = round === 0 ? ONBOARDING : ROUND
    const own = replies(round)
    const final = own[own.length - 1] ?? null
    const record = round > 0 ? run.rounds[round - 1] : undefined
    const version = round > 0 ? versions[round - 1] ?? active : null
    const summary = record && version ? trialSummary(run, round - 1, version, red) : null
    const facts = (id: StationId): string[] | null => {
      switch (id) {
        case 'handover': {
          const materials = handovers(run.opening ?? []).length
          const research = run.research
          if (!materials && !research && !own.length) return null
          const studied = research?.status ? `research ${research.status} · ${plural(research.evidence?.length ?? 0, 'item')}` : research ? 'no research process recorded' : 'no research'
          return [plural(materials, 'material'), studied]
        }
        case 'version': {
          if (!version) return null
          const made = all.find((rev) => rev.deployed && rev.label === version)
          const changes = made?.curation.generated?.candidate.plan.changes.length ?? 0
          return [version, version === 'v0' ? 'baseline' : plural(changes, 'change')]
        }
        case 'trial': {
          if (!summary || !summary.drills.length) return null
          const turns = summary.drills.reduce((total, drill) => total + drill.turns, 0)
          const decks = summary.drills.filter((drill) => drill.deck).length
          const extra = [decks ? plural(decks, 'deck') : '', summary.interceptions ? plural(summary.interceptions, 'interception') : '']
          return [`${plural(summary.drills.length, 'drill')} · ${plural(turns, 'turn')}`, extra.filter(Boolean).join(' · ')].filter(Boolean)
        }
        case 'assess':
          if (!summary || summary.passed + summary.failed + summary.unknown === 0) return null
          return [
            `${summary.passed} pass · ${summary.failed} fail${summary.unknown ? ` · ${summary.unknown} unknown` : ''}`,
            summary.redFailed ? `${plural(summary.redFailed, 'red line')} missed` : 'no red line missed',
          ]
        case 'analyse':
          if (!record?.feedback) return null
          return [plural(record.feedback.requirements.length, 'requirement'), `decision: ${record.feedback.decision}`]
        default:
          return final ? curatorFacts(id, final) : null
      }
    }
    const index = here && here.round === round ? ids.indexOf(here.station) : -1
    let failedOnce = false
    const stations = ids.map((id, position): Station => {
      const known = facts(id)
      const base = { id, actor: ACTOR[id], label: LABEL[id], facts: known ?? [] }
      if (index === position) return { ...base, state: 'current', note: phase?.basis ?? '' }
      if (index >= 0 && position > index) return { ...base, state: 'ahead', note: 'not reached yet' }
      if (index >= 0 && !known) return { ...base, state: 'done', note: 'done; its record is written with the revision' }
      if (known) {
        const failed = id === 'implement' && final !== null && !final.revision.deployed
        return { ...base, state: failed ? 'failed' : 'done', note: failed ? final.failure ?? '' : '' }
      }
      if (running && round >= last) return { ...base, state: 'ahead', note: 'not reached yet' }
      if (run.status === 'error' && round === last && !failedOnce) {
        failedOnce = true
        return { ...base, state: 'failed', note: run.error ?? 'the run ended with an error' }
      }
      const reason = ACTOR[id] === 'curator' ? silence(round) : ''
      return { ...base, state: 'skipped', note: reason || (round === last ? 'the run ended before this step' : 'nothing was recorded for this step') }
    })
    return { round, stations, replies: own }
  }

  return Array.from({ length: last + 1 }, (_, round) => lap(round))
}

/** A lap in brief, for its board: how its trial was judged and what the Curator made of it, each empty where the
    lap has not got there. */
export function summaryOf(lap: Lap): { judged: string[]; made: string } {
  const station = (id: StationId) => lap.stations.find((item) => item.id === id)
  const assess = station('assess')
  const implement = station('implement')
  const judged = !assess || assess.state === 'ahead' ? [] : assess.state === 'current' ? ['assess now'] : assess.facts.length ? assess.facts : assess.state === 'failed' ? ['failed'] : []
  const made = !implement || implement.state === 'ahead' ? '' : implement.state === 'current' ? 'implement now' : implement.facts[0] ?? (implement.state === 'skipped' ? 'no revision' : implement.state)
  return { judged, made }
}
