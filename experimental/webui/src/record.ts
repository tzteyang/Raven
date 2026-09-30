/* The cultivation record experimental/simulation/record.py builds for a run:
   its inputs, every curation with the harness scope it changed, each round's
   trial, evaluation, analysis and mechanism evidence, and the ledger that
   follows each of the owner's rules across rounds. This module reads that
   record defensively (a builder growing or dropping a field is not a crash
   here) and derives the ledger matrix, the round summaries and the chain of
   evidence behind one ledger cell. */

import type { Treatment } from './model'

export type Verdict = 'pass' | 'fail' | 'mixed' | 'unknown'
export type Tone = Verdict | 'none'

export const FACETS = ['memory', 'planning', 'capability', 'action'] as const
export const ROOT = 'root'

export interface RecordRun {
  name: string
  record_id?: string
  status?: string
  error?: string | null
  stop?: string | null
  started?: string | number | null
  updated?: string | number | null
  chain?: unknown
  /** How the run was set up (settings.json): chain, teaching, models, rounds, cards; never a credential. */
  settings: Record<string, unknown>
  revisions: unknown[]
  /** Why the suite stopped the run early, for example its spending budget. */
  stopped?: string | null
  /** What the suite wrote about the run when it finished it (suite-summary.json without its spend). */
  suite?: { stopped?: string | null; status?: string; notes?: string[] } | null
  warnings: string[]
  /** The simulation command that reproduces the run's setup. */
  reproduce?: string | null
}

export interface Material {
  name: string
  sha256?: string
  given?: unknown
  /** The round whose review handed the material over, when it was not given at onboarding. */
  round?: number
}

export interface RecordInputs {
  profile?: string | null
  onboarding?: string | null
  materials: Material[]
  cards: { name: string; sha256?: string }[]
  /** The employee's starting agent home as path -> SHA-256. */
  baseline: Record<string, string>
}

export interface PlannedChange {
  target: string
  facet?: string
  /** How the change treats the diagnosed mechanism: modify, replace or add. */
  treatment?: Treatment | null
  reason?: string
  expected?: string
  /** The inputs the change addresses (requirement ids, materials, playbook nodes, the task), as the round's typed
      history entry records them; empty for a curation outside that history. */
  addresses?: string[]
}

export interface ArtifactDiff {
  target: string
  path: string
  change?: string
  lines_added?: number
  lines_removed?: number
  diff?: string
}

export interface RecordCuration {
  id: string
  /** The round whose trial this curation answered; null or 0 for onboarding. */
  round: number | null
  /** "root" for the employee's own harness, else the child harness a playbook node reaches. */
  scope: string
  understanding: string
  changes: PlannedChange[]
  artifact_diff: ArtifactDiff[]
  outcome?: string | null
  error?: string | null
  design?: string
  /** Host check errors of the candidate. */
  validation_errors: string[]
}

export interface Delivered {
  name: string
  path?: string
  sha256?: string
  pages?: unknown[]
}

export interface PlaybookRun {
  run_id: string
  nodes: { id: string; subagent?: string | null; status?: string | null; seconds?: number | null }[]
}

export interface DrillExchange {
  turn: string | number
  customer: string
  assistant: string
  delivered: Delivered[]
  playbook_runs: PlaybookRun[]
}

export interface Drill {
  session: string
  card?: string | null
  exchanges: DrillExchange[]
}

export interface EvaluationItem {
  criterion: string
  severity?: string
  result: string | number
  session?: string | null
  actual?: string
  note?: string
}

export interface RecordRequirement {
  /** The requirement's id in the typed history; a repeating one keeps the id it was first raised under. */
  id?: string
  situation?: string
  behavior: string
  observed?: string
  evidence: string[]
  acceptance?: string
  strength?: string
  recurrence?: number
  /** The earlier requirement this one repeats. */
  repeats?: string | null
  /** The checks (`check:<criterion>`) and cases (`case:<id>`) it is grounded on. */
  grounds: string[]
  /** The criteria its check grounds name, or those a reading of it names. */
  criteria: string[]
  cases: string[]
  /** `grounds` when a check ground links it to criteria, `reading` when the evaluation side's reading of it does,
      else `none`. */
  link?: unknown
  /** Whether it held in the round after its revision, as the typed history records it; null until that round is
      judged. */
  held?: boolean | null
}

export interface MechanismEvidence {
  /** The harness the row ran in: root, or the child harness whose process recorded it. */
  scope?: string
  kind: string
  target?: string
  decision?: string
  session?: string | null
  turn?: string | number | null
  summary?: string
  /** How many rows of this kind, target and decision the turn recorded. */
  count?: number
  /** A review that sent work back or ended it, a refused tool or a rollback. */
  intervention?: boolean
}

export interface RecordRound {
  number: number
  revision?: string | null
  drills: Drill[]
  evaluation: { remark?: string; items: EvaluationItem[]; metrics?: Record<string, number> } | null
  analysis: { decision?: string; reason?: string; requirements: RecordRequirement[] } | null
  mechanism_evidence: MechanismEvidence[]
  curation?: unknown
  /** A trial cut off mid-round: turns no recorded round holds. */
  partial?: boolean
}

export interface LedgerChange {
  curation: string
  scope: string
  target: string
  facet?: string
  paths: string[]
  /** The curation's outcome; only an installed change is in the harness. */
  outcome?: string
  /** How the change was attached to the rule: `addresses`, since it addresses a requirement grounded on the rule. */
  link?: string
}

export interface LedgerCell {
  round: number
  result?: string | null
  fails?: number
  passes?: number
  requirements?: unknown[]
  changes: LedgerChange[]
  evidence?: unknown
}

export interface Sediment {
  round: number | null
  scope: string
  facet?: string
  target: string
  paths: string[]
}

export interface LedgerRow {
  criterion: string
  severity?: string
  rule?: string
  timeline: LedgerCell[]
  sedimented_in: Sediment[]
  status?: string
}

export interface CultivationRecord {
  schema: number
  run: RecordRun
  inputs: RecordInputs
  curations: RecordCuration[]
  rounds: RecordRound[]
  ledger: LedgerRow[]
  cost: { total: number; by_part: Record<string, number> } | null
  /** The value judge's reading of this run (experimental/simulation/value.py), when the record carries one. */
  value: ValueVerdict | null
}

/** A rule sedimented as planning or action that failed before and held after, with where the evidence is. */
export interface ValueCase {
  criterion: string
  severity?: string
  rule?: string
  /** The earliest planning or action landing that carries the rule. */
  sedimented: Sediment
  failed_in: number[]
  held_in: number[]
  /** Mechanism rows of the sedimented targets in the drills that judged the rule, and how many intervened. */
  mechanism_rows: number
  interventions: number
  targets: string[]
}

export interface ValueVerdict {
  /** qualifies, partial or none. */
  verdict: string
  score: number
  checks: { name: string; ok: boolean; detail: string }[]
  cases: ValueCase[]
  /** Planning or action installed at onboarding that intervened and held; there is no before to compare with. */
  held_cases: ValueCase[]
}

type Loose = Record<string, unknown>

const obj = (value: unknown): Loose => (value && typeof value === 'object' && !Array.isArray(value) ? (value as Loose) : {})
const list = (value: unknown): unknown[] => (Array.isArray(value) ? value : [])
const text = (value: unknown): string => (typeof value === 'string' ? value : value === null || value === undefined ? '' : String(value))
const strings = (value: unknown): string[] => list(value).map(text).filter(Boolean)
const num = (value: unknown): number | undefined => (typeof value === 'number' && Number.isFinite(value) ? value : undefined)
const roundOf = (value: unknown): number | null => (typeof value === 'number' && Number.isFinite(value) ? value : null)

export const scopeOf = (value: unknown): string => text(value) || ROOT
export const isRoot = (scope: string | null | undefined): boolean => !scope || scope === ROOT

/** The facet a change works through: the one the record names, else the target's leading part when it is a facet. */
export function facetOf(target: string, facet?: string | null): string {
  if (facet) return facet
  const head = target.split('.')[0]
  return (FACETS as readonly string[]).includes(head) ? head : 'other'
}

const change = (value: unknown): LedgerChange => {
  const row = obj(value)
  return {
    curation: text(row.curation),
    scope: scopeOf(row.scope),
    target: text(row.target),
    facet: text(row.facet) || undefined,
    paths: strings(row.paths),
    ...(typeof row.outcome === 'string' ? { outcome: row.outcome } : {}),
    ...(typeof row.link === 'string' ? { link: row.link } : {}),
  }
}

/** The record with every list present and every scope named, whatever the builder left out. */
export function normalizeRecord(raw: unknown): CultivationRecord {
  const value = obj(raw)
  const run = obj(value.run)
  const inputs = obj(value.inputs)
  const cost = obj(value.cost)
  return {
    schema: num(value.schema) ?? 0,
    run: {
      ...(run as Partial<RecordRun>),
      name: text(run.name),
      settings: obj(run.settings),
      revisions: list(run.revisions),
      warnings: strings(run.warnings),
      suite: run.suite ? (obj(run.suite) as RecordRun['suite']) : null,
    },
    inputs: {
      profile: typeof inputs.profile === 'string' ? inputs.profile : null,
      onboarding: typeof inputs.onboarding === 'string' ? inputs.onboarding : null,
      materials: list(inputs.materials).map((item) => ({ ...obj(item), name: text(obj(item).name) }) as Material),
      cards: list(inputs.cards).map((item) => ({ name: text(obj(item).name), sha256: text(obj(item).sha256) || undefined })),
      baseline: Object.fromEntries(Object.entries(obj(inputs.baseline)).filter(([, value]) => typeof value === 'string')) as Record<string, string>,
    },
    curations: list(value.curations).map((item) => {
      const row = obj(item)
      return {
        id: text(row.id),
        round: roundOf(row.round),
        scope: scopeOf(row.scope),
        understanding: text(row.understanding),
        changes: list(row.changes).map((entry) => ({ ...(obj(entry) as Partial<PlannedChange>), target: text(obj(entry).target), addresses: strings(obj(entry).addresses) })),
        artifact_diff: list(row.artifact_diff).map((entry) => ({ ...(obj(entry) as Partial<ArtifactDiff>), target: text(obj(entry).target), path: text(obj(entry).path) })),
        outcome: typeof row.outcome === 'string' ? row.outcome : null,
        error: typeof row.error === 'string' && row.error ? row.error : null,
        design: text(row.design),
        validation_errors: strings(obj(row.validation).errors),
      }
    }),
    rounds: list(value.rounds).map((item, i) => {
      const row = obj(item)
      const evaluation = row.evaluation ? obj(row.evaluation) : null
      const analysis = row.analysis ? obj(row.analysis) : null
      return {
        number: num(row.number) ?? i + 1,
        revision: typeof row.revision === 'string' ? row.revision : null,
        drills: list(row.drills).map((entry) => {
          const drill = obj(entry)
          return {
            session: text(drill.session),
            card: typeof drill.card === 'string' ? drill.card : null,
            exchanges: list(drill.exchanges).map((one) => {
              const exchange = obj(one)
              return {
                turn: typeof exchange.turn === 'number' ? exchange.turn : text(exchange.turn),
                customer: text(exchange.customer),
                assistant: text(exchange.assistant),
                delivered: list(exchange.delivered).map((file) => ({ ...obj(file), name: text(obj(file).name) }) as Delivered),
                playbook_runs: list(exchange.playbook_runs).map((run) => ({ run_id: text(obj(run).run_id), nodes: list(obj(run).nodes) as PlaybookRun['nodes'] })),
              }
            }),
          }
        }),
        evaluation: evaluation
          ? {
              remark: text(evaluation.remark),
              items: list(evaluation.items).map((entry) => ({ ...(obj(entry) as Partial<EvaluationItem>), criterion: text(obj(entry).criterion), result: (obj(entry).result as string | number) ?? 'unknown' })),
              metrics: obj(evaluation.metrics) as Record<string, number>,
            }
          : null,
        analysis: analysis
          ? {
              decision: text(analysis.decision) || undefined,
              reason: text(analysis.reason),
              requirements: list(analysis.requirements).map(requirement),
            }
          : null,
        mechanism_evidence: list(row.mechanism_evidence).map((entry) => ({ ...(obj(entry) as Partial<MechanismEvidence>), kind: text(obj(entry).kind) })),
        curation: row.curation ?? null,
        partial: row.partial === true,
      }
    }),
    ledger: list(value.ledger).map((item) => {
      const row = obj(item)
      return {
        criterion: text(row.criterion),
        severity: text(row.severity) || undefined,
        rule: text(row.rule),
        status: text(row.status) || undefined,
        timeline: list(row.timeline).map((entry) => {
          const cell = obj(entry)
          return {
            round: num(cell.round) ?? 0,
            result: typeof cell.result === 'string' ? cell.result : null,
            fails: num(cell.fails),
            passes: num(cell.passes),
            requirements: Array.isArray(cell.requirements) ? cell.requirements : undefined,
            changes: list(cell.changes).map(change),
            evidence: cell.evidence,
          }
        }),
        sedimented_in: list(row.sedimented_in).map((entry) => {
          const sediment = obj(entry)
          return { round: roundOf(sediment.round), scope: scopeOf(sediment.scope), facet: text(sediment.facet) || undefined, target: text(sediment.target), paths: strings(sediment.paths) }
        }),
      }
    }),
    cost: typeof cost.total === 'number' ? { total: cost.total, by_part: obj(cost.by_part) as Record<string, number> } : null,
    value: verdictOf(value.value),
  }
}

const rounds = (value: unknown): number[] => list(value).map(num).filter((item): item is number => item !== undefined)

function valueCase(value: unknown): ValueCase {
  const row = obj(value)
  const sediment = obj(row.sedimented)
  return {
    criterion: text(row.criterion),
    severity: text(row.severity) || undefined,
    rule: text(row.rule) || undefined,
    sedimented: { round: roundOf(sediment.round), scope: scopeOf(sediment.scope), facet: text(sediment.facet) || undefined, target: text(sediment.target), paths: strings(sediment.paths) },
    failed_in: rounds(row.failed_in),
    held_in: rounds(row.held_in),
    mechanism_rows: num(row.mechanism_rows) ?? 0,
    interventions: num(row.interventions) ?? 0,
    targets: strings(row.targets),
  }
}

function verdictOf(value: unknown): ValueVerdict | null {
  const row = obj(value)
  if (typeof row.verdict !== 'string') return null
  return {
    verdict: row.verdict,
    score: num(row.score) ?? 0,
    checks: Object.entries(obj(row.checks)).map(([name, check]) => ({ name, ok: obj(check).ok === true, detail: text(obj(check).detail) })),
    cases: list(row.cases).map(valueCase),
    held_cases: list(row.held_cases).map(valueCase),
  }
}

/** The verdict in words a reader of the page expects. */
export const VERDICT_LABEL: Record<string, string> = { qualifies: 'qualifies', partial: 'partial', none: 'no case' }

function requirement(value: unknown): RecordRequirement {
  const row = obj(value)
  return {
    id: text(row.id) || undefined,
    situation: text(row.situation),
    behavior: text(row.behavior),
    observed: text(row.observed),
    evidence: strings(row.evidence),
    acceptance: text(row.acceptance),
    strength: text(row.strength) || undefined,
    recurrence: num(row.recurrence),
    repeats: text(row.repeats) || null,
    grounds: strings(row.grounds),
    criteria: strings(row.criteria),
    cases: strings(row.cases),
    link: row.link,
    held: typeof row.held === 'boolean' ? row.held : null,
  }
}

/** A chain label from whatever shape the record gives it: a word, a list of steps or an object naming it. */
export function chainLabel(chain: unknown): string {
  if (typeof chain === 'string') return chain
  if (Array.isArray(chain)) return chain.map(chainLabel).filter(Boolean).join(' / ')
  const row = obj(chain)
  for (const key of ['label', 'name', 'kind']) if (typeof row[key] === 'string') return row[key] as string
  return Object.values(row).filter((item) => typeof item === 'string').join(' / ')
}

export const costLabel = (amount: number): string => `$${amount.toFixed(2)}`

/** The materials the owner handed over in the review of this round, in scenario order. */
export const handedAfter = (record: CultivationRecord, round: number): string[] =>
  record.inputs.materials.filter((item) => item.given === 'handed_over' && item.round === round).map((item) => item.name)

const shortModel = (name: string): string => name.split('/').pop() ?? name

/* The models behind a run on one line: employee, curator and sub-harness, the
   first two merged when they are the same model. Without a sub-harness model
   the sub-harnesses run on their own deployment's default. */
export function modelLine(models: unknown, short = false): string {
  const row = obj(models)
  const name = (key: string): string => (typeof row[key] === 'string' && row[key] ? (short ? shortModel(row[key] as string) : (row[key] as string)) : '')
  const employee = name('employee')
  const curator = name('curator')
  if (!employee && !curator) return ''
  const parts = employee && employee === curator ? [`employee & curator ${employee}`] : [employee && `employee ${employee}`, curator && `curator ${curator}`]
  parts.push(`sub-harness ${name('subagents') || 'default'}`)
  return parts.filter(Boolean).join(' · ')
}

export const isRed = (severity?: string): boolean => severity === 'red_line'

/** One judged result read as pass, fail or unknown; numbers are scores in [0, 1]. */
export function resultTone(result: unknown): Verdict {
  if (typeof result === 'number') return result >= 1 ? 'pass' : result <= 0 ? 'fail' : 'unknown'
  return result === 'pass' || result === 'fail' || result === 'mixed' ? result : 'unknown'
}

/* The record's own result wins; without one, counts decide, and drills that
   split between passing and failing make the cell mixed. */
export function cellVerdict(cell: Pick<LedgerCell, 'result' | 'fails' | 'passes'>): Verdict {
  if (cell.result === 'pass' || cell.result === 'fail' || cell.result === 'mixed' || cell.result === 'unknown') return cell.result
  const fails = cell.fails ?? 0
  const passes = cell.passes ?? 0
  if (fails && passes) return 'mixed'
  if (fails) return 'fail'
  if (passes) return 'pass'
  return 'unknown'
}

/** How many mechanism events a cell's evidence counts: a number, a list's length, or the sum over an object's values. */
export function evidenceCount(evidence: unknown): number {
  if (typeof evidence === 'number') return Number.isFinite(evidence) ? evidence : 0
  if (Array.isArray(evidence)) return evidence.length
  if (evidence && typeof evidence === 'object') return Object.values(evidence).reduce((sum: number, item) => sum + evidenceCount(item), 0)
  return 0
}

export const roundAt = (record: CultivationRecord, number: number): RecordRound | undefined =>
  record.rounds.find((round) => round.number === number)

/** Onboarding curations answer no trial: their round is null or 0. */
export const isOnboarding = (round: number | null): boolean => round === null || round === 0

export interface Column {
  /** 0 for onboarding, else the round number. */
  round: number
  label: string
  /** The version the round's drills ran on, as the record's transcript labels it (v0 is the first known artifact). */
  revision: string | null
  /** The artifact id behind that version. */
  artifact: string | null
  partial: boolean
}

/* A round names the artifact its drills ran on; run.revisions lists the known
   artifacts in install order (a prefix may stand for the hired baseline). */
export function versionLabel(record: CultivationRecord, artifact: string | null | undefined): string | null {
  if (!artifact) return null
  const known = record.run.revisions.map((item) => (typeof item === 'string' ? item : revisionLabel(item)))
  const index = known.findIndex((item) => item && (item === artifact || artifact.startsWith(item) || item.startsWith(artifact)))
  if (index >= 0) return `v${index}`
  return /^[0-9a-f]{16,}$/i.test(artifact) ? artifact.slice(0, 8) : artifact
}

export function columns(record: CultivationRecord): Column[] {
  const onboarding =
    record.curations.some((curation) => isOnboarding(curation.round)) ||
    record.ledger.some((row) => row.timeline.some((cell) => cell.round === 0) || row.sedimented_in.some((item) => isOnboarding(item.round)))
  const numbers = new Set(record.rounds.map((round) => round.number))
  for (const row of record.ledger) for (const cell of row.timeline) if (cell.round > 0) numbers.add(cell.round)
  const rounds = [...numbers].sort((a, b) => a - b).map((number): Column => {
    const round = roundAt(record, number)
    return { round: number, label: `Round ${number}`, revision: versionLabel(record, round?.revision), artifact: round?.revision ?? null, partial: round?.partial === true }
  })
  return onboarding ? [{ round: 0, label: 'Onboarding', revision: null, artifact: null, partial: false }, ...rounds] : rounds
}

export interface Landed {
  facet: string
  scope: string
  targets: string[]
  /** False when the curation that planned these changes was not installed (rejected, error, paused). */
  installed: boolean
  outcome?: string
}

export const isInstalled = (item: { outcome?: string | null }): boolean => !item.outcome || item.outcome === 'installed'

/** A cell's changes folded to one chip per facet, scope and outcome: root scope first, installed before planned-only. */
export function landed(changes: LedgerChange[]): Landed[] {
  const by = new Map<string, Landed>()
  for (const item of changes) {
    const facet = facetOf(item.target, item.facet)
    const installed = isInstalled(item)
    const key = `${item.scope}\u0000${facet}\u0000${installed}`
    const hit = by.get(key) ?? { facet, scope: item.scope, targets: [], installed, ...(installed ? {} : { outcome: item.outcome }) }
    if (!hit.targets.includes(item.target)) hit.targets.push(item.target)
    by.set(key, hit)
  }
  const order = (facet: string) => {
    const at = (FACETS as readonly string[]).indexOf(facet)
    return at < 0 ? FACETS.length : at
  }
  return [...by.values()].sort(
    (a, b) => Number(!a.installed) - Number(!b.installed) || Number(!isRoot(a.scope)) - Number(!isRoot(b.scope)) || a.scope.localeCompare(b.scope) || order(a.facet) - order(b.facet),
  )
}

export interface Resolved<T> {
  rows: T[]
  /** Where the rows came from: the ledger itself, or a match the page made because the ledger named none. */
  source: 'ledger' | 'matched'
}

/* A ledger cell may name its requirements by index into the round's analysis,
   by behavior text or as whole objects; without any, the round's requirements
   that list this criterion are shown as a match. */
export function requirementsOf(record: CultivationRecord, criterion: string, cell: LedgerCell | undefined, round: number): Resolved<RecordRequirement> {
  const all = roundAt(record, round)?.analysis?.requirements ?? []
  if (cell?.requirements !== undefined) {
    const rows = cell.requirements.flatMap((item): RecordRequirement[] => {
      if (typeof item === 'number') return all[item] ? [all[item]] : []
      if (typeof item === 'string') {
        const hit = all.find((row) => row.behavior === item || row.link === item)
        return [hit ?? { behavior: item, evidence: [], grounds: [], criteria: [], cases: [] }]
      }
      return item && typeof item === 'object' ? [requirement(item)] : []
    })
    return { rows, source: 'ledger' }
  }
  return { rows: all.filter((row) => row.criteria.includes(criterion)), source: 'matched' }
}

export interface ChangeLink {
  change: LedgerChange
  curation: RecordCuration | null
  plan: PlannedChange | null
  diffs: ArtifactDiff[]
}

const sameRound = (a: number | null, b: number): boolean => (isOnboarding(a) ? b === 0 : a === b)

/* The changes a cell shows: the ones the ledger lists in it, else the rule's
   sediments that landed after that round (onboarding's for column 0). */
export function cellChanges(row: LedgerRow | undefined, cell: LedgerCell | undefined, round: number): LedgerChange[] {
  if (cell?.changes.length) return cell.changes
  return (row?.sedimented_in ?? [])
    .filter((item) => sameRound(item.round, round))
    .map((item) => ({ curation: '', scope: item.scope, target: item.target, facet: item.facet, paths: item.paths }))
}

/** Each change a cell shows, with the curation that made it, its planned reason and its file diffs. */
export function changesOf(record: CultivationRecord, cell: LedgerCell | undefined, row?: LedgerRow, round = cell?.round ?? 0): ChangeLink[] {
  return cellChanges(row, cell, round).map((item) => {
    const curation =
      record.curations.find((one) => item.curation && one.id === item.curation) ??
      record.curations.find(
        (one) =>
          !item.curation &&
          sameRound(one.round, round) &&
          one.scope === item.scope &&
          (one.changes.some((change) => change.target === item.target) || one.artifact_diff.some((diff) => diff.target === item.target)),
      ) ??
      null
    const plan = curation?.changes.find((row) => row.target === item.target) ?? null
    /* A generated module is diffed under "files"; the change names it among its paths when its value references it. */
    const diffs = (curation?.artifact_diff ?? []).filter(
      (row) => (row.target === item.target && (!item.paths.length || item.paths.includes(row.path))) || (row.target === 'files' && item.paths.includes(row.path)),
    )
    return { change: item, curation, plan, diffs }
  })
}

/** The targets sedimented for a rule before a round's trial, so in force during it. */
export const inForce = (row: LedgerRow, round: number): Sediment[] =>
  row.sedimented_in.filter((item) => isOnboarding(item.round) || (item.round as number) < round)

const looksLikeEvidence = (item: unknown): item is MechanismEvidence => Boolean(item) && typeof item === 'object' && typeof (item as Loose).kind === 'string'

/* Evidence the ledger lists row by row, or by index into the round's
   mechanism evidence, is taken as given. Otherwise the round's evidence for
   targets in force for this rule, from the drills its verdicts name, is
   shown as a match; a cell whose evidence
   holds only counts keeps its count on the marker. */
export function mechanismOf(record: CultivationRecord, row: LedgerRow, cell: LedgerCell | undefined, round: number): Resolved<MechanismEvidence> & { count: number } {
  const all = roundAt(record, round)?.mechanism_evidence ?? []
  const evidence = cell?.evidence
  const parts = Array.isArray(evidence) ? [evidence] : Object.values(obj(evidence)).filter(Array.isArray)
  const listed = parts.flat()
  if (listed.length && listed.every((item) => looksLikeEvidence(item) || typeof item === 'number')) {
    const rows = listed.flatMap((item) => (typeof item === 'number' ? (all[item] ? [all[item]] : []) : [{ ...item }]))
    return { rows, source: 'ledger', count: rows.length }
  }
  const targets = new Set(inForce(row, round).map((item) => item.target))
  const sessions = new Set(
    (roundAt(record, round)?.evaluation?.items ?? []).filter((item) => item.criterion === row.criterion && item.session).map((item) => item.session as string),
  )
  const rows = all.filter((item) => item.target && targets.has(item.target) && (!sessions.size || (item.session && sessions.has(item.session))))
  const weight = rows.reduce((sum, item) => sum + (item.count ?? 1), 0)
  return { rows, source: 'matched', count: evidence !== undefined && evidence !== null && typeof evidence !== 'string' ? evidenceCount(evidence) : weight }
}

export interface Quote {
  item: EvaluationItem
  tone: Verdict
  card: string | null
  /** The employee's last reply in the cited drill, when the evaluation quotes nothing itself. */
  reply: string | null
}

/** The owner's verdicts on a criterion in a round, failures first, each with the drill it cites. */
export function quotesOf(record: CultivationRecord, criterion: string, round: number): Quote[] {
  const found = roundAt(record, round)
  const items = (found?.evaluation?.items ?? []).filter((item) => item.criterion === criterion)
  const rank: Record<Verdict, number> = { fail: 0, mixed: 1, unknown: 2, pass: 3 }
  return items
    .map((item) => {
      const drill = found?.drills.find((row) => row.session === item.session)
      const last = drill?.exchanges[drill.exchanges.length - 1]
      return { item, tone: resultTone(item.result), card: drill?.card ?? null, reply: item.actual ? null : last?.assistant || null }
    })
    .sort((a, b) => rank[a.tone] - rank[b.tone])
}

export interface MatrixCell {
  column: Column
  cell: LedgerCell | undefined
  tone: Tone
  requirements: number
  landed: Landed[]
  fired: number
}

export interface Settle {
  tone: Tone
  text: string
  /** What the page reads from the verdicts beyond the record's status: a regression, a mixed round, nothing sedimented. */
  note: string
}

export interface MatrixRow {
  row: LedgerRow
  red: boolean
  cells: MatrixCell[]
  settle: Settle
}

const HELD = /^held_since_round_(\d+)$/

/** The record's status for a rule in words and tone: never_failed, not_exercised, still_failing, held_since_round_N. */
export function statusOf(status: string): { tone: Tone; text: string } {
  const held = HELD.exec(status)
  if (held) return { tone: 'pass', text: `held since round ${held[1]}` }
  if (status === 'never_failed') return { tone: 'pass', text: 'never failed' }
  if (status === 'still_failing') return { tone: 'fail', text: 'still failing' }
  if (status === 'not_exercised') return { tone: 'unknown', text: 'not exercised' }
  return { tone: 'unknown', text: status.replace(/_/g, ' ') }
}

/* The record's status leads; the verdicts add a note when the rule regressed
   after passing, split its drills, or kept failing with nothing sedimented. */
export function settle(row: LedgerRow): Settle {
  const read = verdictSettle(row)
  if (!row.status) return { ...read, note: '' }
  const stated = statusOf(row.status)
  const note = /^(regressed|mixed)/.test(read.text) ? read.text : read.text.includes('nothing sedimented') ? 'nothing sedimented' : ''
  return { tone: stated.tone === 'unknown' && read.tone !== 'unknown' ? read.tone : stated.tone, text: stated.text, note }
}

/** Where a rule stands after the last judged round, read from its verdicts: held since round N, never failed, still failing, regressed or mixed. */
export function verdictSettle(row: LedgerRow): { tone: Tone; text: string } {
  const judged = [...row.timeline]
    .filter((cell) => cell.round > 0)
    .sort((a, b) => a.round - b.round)
    .map((cell) => ({ round: cell.round, verdict: cellVerdict(cell) }))
    .filter((cell) => cell.verdict !== 'unknown')
  if (!judged.length) return { tone: 'unknown', text: 'not judged yet' }
  const last = judged[judged.length - 1]
  if (judged.every((cell) => cell.verdict === 'pass')) return { tone: 'pass', text: judged.length > 1 ? 'never failed' : `passed in round ${last.round}` }
  if (last.verdict === 'pass') {
    let start = judged.length - 1
    while (start > 0 && judged[start - 1].verdict === 'pass') start -= 1
    return { tone: 'pass', text: `held since round ${judged[start].round}` }
  }
  const before = judged[judged.length - 2]
  if (last.verdict === 'mixed') return { tone: 'mixed', text: `mixed in round ${last.round}` }
  if (before?.verdict === 'pass') return { tone: 'fail', text: `regressed in round ${last.round}` }
  return { tone: 'fail', text: row.sedimented_in.length ? 'still failing' : 'still failing, nothing sedimented' }
}

/* A rule with no verdict in any round and no change planned or landed for it
   says nothing yet; the matrix lists it apart so the rows that do lead. */
const quiet = (item: MatrixRow): boolean => item.cells.every((cell) => cell.tone === 'none' && !cell.landed.length) && !item.row.sedimented_in.length

/** One row per criterion, red lines first and the builder's order kept within each group; one cell per column. */
export function ledgerMatrix(record: CultivationRecord): { columns: Column[]; rows: MatrixRow[]; quiet: MatrixRow[] } {
  const cols = columns(record)
  const all = record.ledger.map((row): MatrixRow => ({
    row,
    red: isRed(row.severity),
    settle: settle(row),
    cells: cols.map((column): MatrixCell => {
      const cell = row.timeline.find((item) => item.round === column.round)
      const judged = column.round > 0 && cell !== undefined && (cellVerdict(cell) !== 'unknown' || quotesOf(record, row.criterion, column.round).length > 0)
      const changes = cellChanges(row, cell, column.round)
      return {
        column,
        cell,
        tone: judged ? cellVerdict(cell!) : 'none',
        requirements: column.round > 0 ? requirementsOf(record, row.criterion, cell, column.round).rows.length : 0,
        landed: landed(changes),
        fired: column.round > 0 ? mechanismOf(record, row, cell, column.round).count : 0,
      }
    }),
  }))
  const rows = all.filter((item) => !quiet(item))
  return { columns: cols, rows: [...rows.filter((item) => item.red), ...rows.filter((item) => !item.red)], quiet: all.filter(quiet) }
}

export interface ScopeGroup {
  scope: string
  curations: RecordCuration[]
}

export interface CurationGroup {
  /** null for onboarding. */
  round: number | null
  scopes: ScopeGroup[]
}

/** Curations by the round they answered (onboarding first), then by scope with the root harness first. */
export function groupCurations(curations: RecordCuration[]): CurationGroup[] {
  const rounds = new Map<number, RecordCuration[]>()
  for (const curation of curations) {
    const key = isOnboarding(curation.round) ? 0 : (curation.round as number)
    rounds.set(key, [...(rounds.get(key) ?? []), curation])
  }
  return [...rounds.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([round, rows]) => {
      const scopes = new Map<string, RecordCuration[]>()
      for (const row of rows) scopes.set(row.scope, [...(scopes.get(row.scope) ?? []), row])
      return {
        round: round === 0 ? null : round,
        scopes: [...scopes.entries()]
          .sort((a, b) => Number(!isRoot(a[0])) - Number(!isRoot(b[0])) || a[0].localeCompare(b[0]))
          .map(([scope, list]) => ({ scope, curations: list })),
      }
    })
}

export const scopeLabel = (scope: string): string => (isRoot(scope) ? 'root harness' : scope)

export interface RoundSummary {
  round: number | null
  revision: string | null
  pass: number
  fail: number
  unknown: number
  redFailed: number
  decision: string | null
  requirements: number
  /** Mechanism rows the round's drills recorded, and how many of them sent work back, ended it or refused a tool. */
  fired: number
  interventions: number
  partial: boolean
  /** Materials the owner handed over in this round's review. */
  handed: string[]
  /** One entry per scope that a curation answering this round touched. */
  curations: { scope: string; outcome: string; facets: string[]; error: string | null }[]
}

/** One line per round: the verdict counts, the Analyst's decision and what each scope's curation came to. */
export function roundSummaries(record: CultivationRecord): RoundSummary[] {
  const groups = groupCurations(record.curations)
  const outcomeOf = (round: number | null) =>
    (groups.find((group) => group.round === round)?.scopes ?? []).flatMap((group) =>
      group.curations.map((curation) => ({
        scope: group.scope,
        outcome: curation.outcome || (curation.error ? 'failed' : 'recorded'),
        facets: [...new Set(curation.changes.map((item) => facetOf(item.target, item.facet)))],
        error: curation.error ?? null,
      })),
    )
  const onboarding: RoundSummary[] = groups.some((group) => group.round === null)
    ? [{ round: null, revision: null, pass: 0, fail: 0, unknown: 0, redFailed: 0, decision: null, requirements: 0, fired: 0, interventions: 0, partial: false, handed: [], curations: outcomeOf(null) }]
    : []
  return [
    ...onboarding,
    ...[...record.rounds]
      .sort((a, b) => a.number - b.number)
      .map((round) => {
        const items = round.evaluation?.items ?? []
        const tones = items.map((item) => resultTone(item.result))
        return {
          round: round.number,
          revision: versionLabel(record, round.revision),
          pass: tones.filter((tone) => tone === 'pass').length,
          fail: tones.filter((tone) => tone === 'fail').length,
          unknown: tones.filter((tone) => tone === 'unknown' || tone === 'mixed').length,
          redFailed: items.filter((item, i) => tones[i] === 'fail' && isRed(item.severity)).length,
          decision: round.analysis?.decision ?? null,
          requirements: round.analysis?.requirements.length ?? 0,
          fired: round.mechanism_evidence.reduce((sum, row) => sum + (row.count ?? 1), 0),
          interventions: round.mechanism_evidence.filter((row) => row.intervention).reduce((sum, row) => sum + (row.count ?? 1), 0),
          partial: round.partial === true,
          handed: handedAfter(record, round.number),
          curations: outcomeOf(round.number),
        }
      }),
  ]
}

/** Rounds whose trial was judged. */
export const completed = (record: CultivationRecord): number => record.rounds.filter((round) => round.evaluation && round.evaluation.items.length).length

/** A revision entry as a short label, whatever shape the record gives it. */
export function revisionLabel(value: unknown): string {
  if (typeof value === 'string') return value
  const row = obj(value)
  for (const key of ['label', 'version', 'id', 'artifact']) if (typeof row[key] === 'string' && row[key]) return row[key] as string
  return ''
}

/** Unified diff lines tagged for colouring. */
export function diffLines(diff: string): { kind: 'add' | 'del' | 'hunk' | 'meta' | 'ctx'; text: string }[] {
  return diff.split('\n').map((line) => {
    if (line.startsWith('+++') || line.startsWith('---')) return { kind: 'meta', text: line }
    if (line.startsWith('@@')) return { kind: 'hunk', text: line }
    if (line.startsWith('+')) return { kind: 'add', text: line }
    if (line.startsWith('-')) return { kind: 'del', text: line }
    return { kind: 'ctx', text: line }
  })
}
