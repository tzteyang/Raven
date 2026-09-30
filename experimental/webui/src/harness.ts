/* The harness view's two tables: what each harness of the employee (the
   root and every child Harness) changed in each version, and the red-line
   verdicts by version beside the strategies the revision that produced each
   version changed. It reports co-occurrence only; it does not claim a change
   caused a verdict. */

import { deployed, overlay, roundVersions, tone } from './derive'
import { STRATEGIES, strategyOf, targetFiles } from './mechanism'
import { dagRuns } from './trial'

import type { Revision } from './derive'
import type { Strategy } from './mechanism'
import type { Artifact, Change, Criterion, Generated, Run } from './model'

export const ROOT = 'Main agent'

export interface HarnessChange {
  target: string
  strategy: Strategy | null
  treatment: Change['treatment'] | null
  expected: string
  files: string[]
}

export interface HarnessRow {
  harness: string
  /** version label -> the changes that version made to this harness */
  changes: Record<string, HarnessChange[]>
  /** The last version that changed this harness, or null when none did. */
  last: string | null
}

const EMPTY: Artifact = { values: {}, files: {} }

/* A revision's artifact carries only what it changed, so a target's files are
   read from the Harness as assembled at that version and kept when the
   revision rewrote them. */
const changesOf = (generated: Generated, assembled: Artifact): HarnessChange[] =>
  generated.candidate.plan.changes.map((change) => ({
    target: change.target,
    strategy: strategyOf(change.target),
    treatment: change.treatment ?? null,
    expected: change.expected,
    files: targetFiles(change.target, assembled).filter((path) => path in generated.candidate.artifact.files),
  }))

/* The root always has a row; a child Harness has one once a revision changed
   or withdrew it, or a playbook node ran it. */
export function harnessRows(run: Run, all: Revision[]): HarnessRow[] {
  const rows = new Map<string, HarnessRow>()
  const row = (harness: string) => {
    if (!rows.has(harness)) rows.set(harness, { harness, changes: {}, last: null })
    return rows.get(harness)!
  }
  const assembled = new Map<string, Artifact>()
  const assemble = (harness: string, generated: Generated): Artifact => {
    const next = overlay(assembled.get(harness) ?? EMPTY, generated.candidate.artifact)
    assembled.set(harness, next)
    return next
  }
  row(ROOT)
  for (const rev of deployed(all)) {
    const generated = rev.curation.generated
    if (generated) {
      const state = assemble(ROOT, generated)
      if (generated.candidate.plan.changes.length) {
        const target = row(ROOT)
        target.changes[rev.label] = changesOf(generated, state)
        target.last = rev.label
      }
    }
    for (const [name, child] of Object.entries(rev.curation.child_changes ?? {})) {
      const target = row(name)
      target.changes[rev.label] = changesOf(child, assemble(name, child))
      if (target.changes[rev.label].length) target.last = rev.label
    }
    for (const name of rev.curation.withdrawn_children ?? []) {
      const target = row(name)
      assembled.delete(name)
      target.changes[rev.label] = [{ target: 'Restore baseline', strategy: null, treatment: null, expected: 'Authored child bindings retired', files: [] }]
      target.last = rev.label
    }
  }
  for (const round of run.rounds) {
    for (const exchanges of Object.values(round.sessions)) {
      for (const exchange of exchanges) {
        for (const graph of dagRuns(exchange.execution.records)) {
          for (const node of graph.nodes) if (node.subagent) row(node.subagent)
        }
      }
    }
  }
  const [root, ...rest] = rows.values()
  return [root, ...rest.sort((a, b) => a.harness.localeCompare(b.harness))]
}

export interface Cell {
  pass: number
  fail: number
  unknown: number
}

export interface Column {
  round: number
  version: string
  /** The strategies the revision that produced this version changed, in the root or a child; empty for the baseline
      or a repeat. */
  strategies: Strategy[]
  /** Whether this version is the first trial of a new revision rather than a repeat of the previous one. */
  fresh: boolean
}

export interface Matrix {
  columns: Column[]
  rows: { criterion: Criterion; cells: (Cell | null)[] }[]
  /** The judged criteria that are not red lines, when red lines are marked. */
  others: { criterion: Criterion; cells: (Cell | null)[] }[]
  /** False when no red line of the scenario was judged in this run, so every judged criterion is listed instead. */
  marked: boolean
}

export function redLines(run: Run, all: Revision[], criteria: Criterion[]): Matrix {
  const versions = roundVersions(run, all)
  const producer = new Map(deployed(all).map((rev) => [rev.label, rev]))
  const columns = versions.map((version, i): Column => {
    const fresh = i === 0 || versions[i - 1] !== version
    const rev = producer.get(version)
    const changed = fresh && rev ? new Set([
      ...(rev.curation.generated?.candidate.plan.changes ?? []),
      ...Object.values(rev.curation.child_changes ?? {}).flatMap((child) => child.candidate.plan.changes),
    ].map((change) => strategyOf(change.target))) : new Set<Strategy | null>()
    return { round: i + 1, version, strategies: STRATEGIES.filter((name) => changed.has(name)), fresh }
  })
  const judged = new Map<string, (Cell | null)[]>()
  run.rounds.forEach((round, i) => {
    for (const signal of round.signals) {
      for (const item of signal.items) {
        const cells = judged.get(item.id) ?? run.rounds.map(() => null)
        const cell = cells[i] ?? { pass: 0, fail: 0, unknown: 0 }
        cell[tone(item.result)] += 1
        cells[i] = cell
        judged.set(item.id, cells)
      }
    }
  })
  const red = criteria.filter((criterion) => criterion.severity === 'red_line')
  const marked = red.some((criterion) => judged.has(criterion.id))
  const known = (id: string): Criterion => criteria.find((criterion) => criterion.id === id) ?? { id, check: '', severity: 'standard' }
  const rowOf = (criterion: Criterion) => ({ criterion, cells: judged.get(criterion.id) ?? run.rounds.map(() => null) })
  const redIds = new Set(red.map((criterion) => criterion.id))
  return {
    columns,
    rows: (marked ? red : [...judged.keys()].map(known)).map(rowOf),
    others: marked ? [...judged.keys()].filter((id) => !redIds.has(id)).map(known).map(rowOf) : [],
    marked,
  }
}

export const cellTone = (cell: Cell | null): 'pass' | 'fail' | 'unknown' | 'none' =>
  cell === null ? 'none' : cell.fail ? 'fail' : cell.pass ? 'pass' : 'unknown'

/** One file of a housed sub-harness home, as /api/subharnesses lists it; only prose files carry their text. */
export interface HomeFile {
  path: string
  size: number
  modified: number
  text?: string | null
  truncated?: boolean
}

export interface HousedHome {
  name: string
  files: HomeFile[]
}

/** The files a housed sub-harness reads on its next turn: its profile, tools note and user profile, and its skills. */
export const SUBHARNESS_READS = ['agent_memory/profile/agent.md', 'agent_memory/profile/soul.md', 'TOOLS.md', 'user_memory/profile/user.md']

export const readBySubharness = (path: string): boolean => SUBHARNESS_READS.includes(path) || path.startsWith('skills/')
