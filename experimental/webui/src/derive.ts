/* Views derived from a joined run: the employee versions its Harness revisions
   produced, which version each round tried, and the Harness as assembled at a
   version. */

import type { Artifact, Curation, Item, Round, Run } from './model'

export const BASELINE = 'v0'

export interface Revision {
  /** The version the employee is on after this revision: a new one when it deployed, the kept one otherwise. */
  label: string
  /** Whether this revision put a new Harness on the job; a failed or unchanged revision keeps the prior version. */
  deployed: boolean
  curation: Curation
  /** 1-based round whose feedback produced this revision; null for onboarding. */
  round: number | null
  artifact: string
  /** Unique within the run, for anchors and keys. */
  key: string
}

/** Why a revision did not put a Harness on the job, or null when it did. */
export function failure(curation: Curation): string | null {
  if (curation.error) return curation.error
  if (curation.missing) return `The curation record ${curation.missing} is missing.`
  if (curation.paused) {
    const { stage, scope, reason } = curation.paused
    const where = [stage ? `at ${stage}` : '', scope && scope !== 'root' ? `in ${scope}` : ''].filter(Boolean).join(' ')
    return `Paused${where ? ` ${where}` : ''}: ${reason ?? 'the call budget ran out'}`
  }
  if (!curation.generated) return 'The curation record holds no generated revision.'
  return curation.generated.validation.errors.length ? curation.generated.validation.errors.join('\n') : null
}

/* v1 is the Harness onboarding put on the job, then v2, v3, ... as later
   revisions deploy; the untouched baseline is v0. */
export function revisions(run: Run): Revision[] {
  const out: Revision[] = []
  let label = BASELINE
  let artifact: string | null = null
  let count = 0
  const add = (curation: Curation, round: number | null) => {
    const id = curation.active_artifact_id ?? ''
    const deployed = !failure(curation) && curation.changed !== false && (id === '' || id !== artifact)
    if (deployed) {
      count += 1
      label = `v${count}`
      artifact = id
    }
    out.push({ label, deployed, curation, round, artifact: id, key: `rev-${out.length}` })
  }
  for (const curation of run.initial_curation ?? []) add(curation, null)
  run.rounds.forEach((round, i) => round.curation.forEach((curation) => add(curation, i + 1)))
  return out
}

export const deployed = (all: Revision[]): Revision[] => all.filter((rev) => rev.deployed)

export function versionOf(artifact: string, all: Revision[]): string | null {
  const hit = all.find((rev) => rev.deployed && rev.artifact && rev.artifact === artifact)
  return hit ? hit.label : null
}

/** The version each round tried: from the artifact its turns ran on, else the last revision made before it. */
export function roundVersions(run: Run, all: Revision[]): string[] {
  return run.rounds.map((round, i) => {
    const seen = new Map<string, number>()
    for (const exchanges of Object.values(round.sessions)) {
      for (const exchange of exchanges) {
        const label = versionOf(exchange.execution.artifact_id, all)
        if (label) seen.set(label, (seen.get(label) ?? 0) + 1)
      }
    }
    if (seen.size) return [...seen].sort((a, b) => b[1] - a[1])[0][0]
    const before = all.filter((rev) => rev.round === null || rev.round < i + 1)
    return before.length ? before[before.length - 1].label : BASELINE
  })
}

/** The 1-based rounds that tried a version. */
export const trialsOf = (label: string, versions: string[]): number[] =>
  versions.flatMap((version, i) => (version === label ? [i + 1] : []))

/** An artifact laid over another: its values and files replace earlier ones, and what it retires is dropped. */
export function overlay(base: Artifact, change: Artifact | undefined): Artifact {
  if (!change) return base
  const values = { ...base.values, ...change.values }
  const files = { ...base.files, ...change.files }
  for (const target of change.remove ?? []) delete values[target]
  for (const path of change.remove_files ?? []) delete files[path]
  return { values, files }
}

/** The Harness as assembled at a version: every deployed revision up to it, laid over one another. */
export function harnessAt(all: Revision[], label: string): Artifact {
  let harness: Artifact = { values: {}, files: {} }
  for (const rev of deployed(all)) {
    harness = overlay(harness, rev.curation.generated?.candidate.artifact)
    if (rev.label === label) break
  }
  return harness
}

export function tone(result: Item['result']): 'pass' | 'fail' | 'unknown' {
  if (typeof result === 'number') return result >= 1 ? 'pass' : result <= 0 ? 'fail' : 'unknown'
  return result
}

export const verdict = (result: Item['result']): string => (typeof result === 'number' ? result.toFixed(2) : result)

export interface Progress {
  /** "source/id" -> one verdict per round, null where the item was not measured that round. */
  matrix: Record<string, (Item['result'] | null)[]>
  improved: string[]
  regressed: string[]
}

/* Mirrors experimental/iteration/records.py progress(): verdicts by round, and
   the items that flipped between fail and pass over the run. */
export function progress(run: Run): Progress {
  const matrix: Progress['matrix'] = {}
  run.rounds.forEach((round, i) => {
    for (const signal of round.signals) {
      for (const item of signal.items) {
        const key = `${signal.source}/${item.id}`
        matrix[key] ??= run.rounds.map(() => null)
        matrix[key][i] = item.result
      }
    }
  })
  const verdicts = (results: (Item['result'] | null)[]) => results.filter((r) => r === 'pass' || r === 'fail')
  const improved = Object.keys(matrix).filter((key) => {
    const v = verdicts(matrix[key])
    return v[0] === 'fail' && v[v.length - 1] === 'pass'
  }).sort()
  const regressed = Object.keys(matrix).filter((key) => {
    const v = verdicts(matrix[key])
    return v.some((r, i) => r === 'pass' && v[i + 1] === 'fail')
  }).sort()
  return { matrix, improved, regressed }
}

export const arm = (run: Run): string => (run.curator === 'untouched' ? 'control · no Curator' : 'Curator')

export const fileName = (path: string): string => path.split('/').pop() ?? path

/** The last HTML page a conversation handed over in each round, or null. */
export function pages(run: Run, session: string): (string | null)[] {
  return run.rounds.map((round) => {
    const files = (round.sessions[session] ?? []).flatMap((exchange) => exchange.execution.deliverables ?? [])
    return [...files].reverse().find((path) => /\.html?$/i.test(path)) ?? null
  })
}

/** Every record a round's turns left, in drill order. */
export const roundRecords = (round: Round) =>
  Object.values(round.sessions).flatMap((exchanges) => exchanges.flatMap((exchange) => exchange.execution.records))
