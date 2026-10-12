/* A run read as a route: one leg per installed version of the Harness, from
   the bare baseline to the version on trial now. A leg carries the requests
   heard while it held, the trials played on it and the process that ended it
   (the Analyst's decision and the curation). Each version's Harness
   commitments are replayed from the plans' commitment operations the way the
   host applies them (experimental/harness/contract/commitments.py), so the
   ribbon's strands are the list the Curator itself kept. A run recorded before
   commitments existed has none; its strands fall back to the installed targets. */

import type { ProcessEntry, RequestEntry, Thread, TrialView } from '../studio/types'

export interface Commitment {
  id: string
  surface: string
  statement: string
  serves: string[]
  retired?: string
}

export interface CommitmentOp {
  action: 'add' | 'modify' | 'retire'
  id: string
  surface?: string
  statement?: string
  serves?: string[]
  reason?: string
}

export type Mark = 'add' | 'modify' | 'move' | 'retire'

export interface Strand {
  surface: string
  count: number
}

export interface Leg {
  index: number
  version: string
  /** The commitments in force in this version; null for a run recorded before commitments were kept. */
  commitments: Commitment[] | null
  /** How the curation that produced this version changed each commitment it touched, by id. */
  marks: Record<string, Mark>
  /** Why each commitment retired by that curation was retired, by id. */
  retired: Commitment[]
  strands: Strand[]
  requests: RequestEntry[]
  trials: TrialView[]
  /** The round's drills are still being played. */
  playing: boolean
  /** The Analyst's decision and the curation that closed this leg, when one did. */
  process: ProcessEntry | null
  /** How the leg ends: a curation installed a new version, settled without new code, is under way, failed, or none ran. */
  end: 'waist' | 'knot' | 'curating' | 'failed' | 'open'
  opening: boolean
}

export interface Route {
  legs: Leg[]
  /** Something is still happening at the head of the route. */
  live: boolean
  /** Whether the run recorded commitments at all. */
  recorded: boolean
}

export const SURFACES = ['memory.strategy', 'planning.strategy', 'capability.strategy', 'action.strategy', 'native']

/** The list after `ops`, in order, as the host's `apply` leaves it. */
export function apply(current: Commitment[], ops: CommitmentOp[]): Commitment[] {
  const entries = new Map(current.map((item) => [item.id, item]))
  for (const op of ops) {
    if (op.action === 'add') {
      entries.set(op.id, { id: op.id, surface: op.surface ?? '', statement: op.statement ?? '', serves: op.serves ?? [] })
      continue
    }
    const existing = entries.get(op.id)
    if (!existing || existing.retired) continue
    if (op.action === 'retire') {
      entries.set(op.id, { ...existing, retired: op.reason || 'retired' })
      continue
    }
    entries.set(op.id, {
      ...existing,
      ...(op.surface ? { surface: op.surface } : {}),
      ...(op.statement ? { statement: op.statement } : {}),
      ...(op.serves?.length ? { serves: op.serves } : {}),
    })
  }
  return [...entries.values()]
}

export function active(commitments: Commitment[] | null): Commitment[] {
  return (commitments ?? []).filter((item) => !item.retired)
}

function marksOf(before: Commitment[], ops: CommitmentOp[]): Record<string, Mark> {
  const prior = new Map(before.map((item) => [item.id, item]))
  const marks: Record<string, Mark> = {}
  for (const op of ops) {
    if (op.action === 'add' || op.action === 'retire') marks[op.id] = op.action
    else marks[op.id] = op.surface && op.surface !== prior.get(op.id)?.surface ? 'move' : 'modify'
  }
  return marks
}

/** The root scope's commitment operations in a process's curation plan, as the design stage returned them. */
export function opsOf(process: ProcessEntry | null): CommitmentOp[] | null {
  const root = process?.curation?.scopes.find((scope) => scope.root)
  const plan = root?.plan as { commitments?: CommitmentOp[] } | null | undefined
  return Array.isArray(plan?.commitments) ? plan!.commitments! : null
}

function strandsOf(commitments: Commitment[] | null, targets: string[]): Strand[] {
  const counts = new Map<string, number>()
  if (commitments) for (const item of active(commitments)) counts.set(item.surface, (counts.get(item.surface) ?? 0) + 1)
  else for (const target of targets) counts.set(target, 1)
  const order = [...SURFACES, ...[...counts.keys()].filter((key) => !SURFACES.includes(key)).sort()]
  return order.filter((surface) => counts.has(surface)).map((surface) => ({ surface, count: counts.get(surface)! }))
}

function endOf(process: ProcessEntry): Leg['end'] {
  const view = process.curation
  if (process.curationState === 'running' || view?.paused) return 'curating'
  if (view?.deployed) return 'waist'
  if (view?.error === 'unchanged') return 'knot'
  if (view) return 'failed'
  return 'open'
}

export function routeOf(thread: Thread): Route {
  const recorded = thread.entries.some((entry) => entry.kind === 'process' && opsOf(entry) !== null)
  const fresh = (index: number, version: string, commitments: Commitment[] | null, targets: string[], opening = false): Leg => ({
    index,
    version,
    commitments,
    marks: {},
    retired: [],
    strands: strandsOf(commitments, targets),
    requests: [],
    trials: [],
    playing: false,
    process: null,
    end: 'open',
    opening,
  })
  const legs: Leg[] = [fresh(0, thread.versions[0] ?? 'v0', recorded ? [] : null, [], true)]
  /* A process closes its leg; the next leg opens with whatever follows it, so a run that ended there draws no empty
     leg, while a version just installed on a run still going does show. */
  let carry: (() => Leg) | null = null
  const leg = (): Leg => {
    if (carry) {
      legs.push(carry())
      carry = null
    }
    return legs[legs.length - 1]
  }
  for (const entry of thread.entries) {
    if (entry.kind === 'request') leg().requests.push(entry)
    else if (entry.kind === 'trials' && !entry.holdout) {
      const current = leg()
      current.trials.push(...entry.trials)
      current.playing = current.playing || !!entry.pending || entry.trials.some((trial) => trial.status === 'running')
    } else if (entry.kind === 'process') {
      const closing = leg()
      closing.process = entry
      closing.end = endOf(entry)
      if (closing.end === 'curating') continue
      const settled = closing.end === 'waist' || closing.end === 'knot'
      const ops = settled ? opsOf(entry) ?? [] : []
      const before = closing.commitments
      const view = entry.curation
      carry = () => {
        const commitments = before ? apply(before, ops) : null
        const targets = Object.keys((settled ? view?.after : view?.before)?.root.values ?? {})
        const next = fresh(legs.length, closing.end === 'waist' && view ? view.to : closing.version, commitments, targets)
        if (before && ops.length) {
          next.marks = marksOf(before, ops)
          next.retired = (commitments ?? []).filter((item) => next.marks[item.id] === 'retire')
        }
        return next
      }
    }
  }
  const head = legs[legs.length - 1]
  const live = thread.status === 'running' || head.playing || head.end === 'curating'
  if (carry && live) leg()
  return { legs, live, recorded }
}
