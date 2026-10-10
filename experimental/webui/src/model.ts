/* The shapes experimental/harness/loop/records.py joins: an iteration record with
   each round's analysis, attribution and curation records read in beside it,
   its typed history (experimental/harness/loop/history.py) and the ledger joined
   from it (experimental/harness/loop/ledger.py). serve.py adds the run directory's
   standard and compartment log (experimental/webui/rundir.py). Only the fields
   this page draws are typed; everything else stays open so a record growing a
   field is not a change here. */

/** `stalled` is the server's reading of a record that says running while nothing of the run has been written for long;
    `incomplete` and `needs_input` are a run whose research stage handed over no information before onboarding. */
export type RunStatus = 'running' | 'finished' | 'paused' | 'stopped' | 'error' | 'stalled' | 'incomplete' | 'needs_input'

export interface RunEntry {
  id: string
  /** The run's folder name, which says what the run is (for example sop-a-full). */
  name: string
  task: string
  curator: string | null
  /** Per round: checks passed, checks failed. */
  passes: [number, number][]
  rounds: number
  status: RunStatus
  error: string | null
  recorded: number
  /** How the owner hands over the materials in this run (documents, staged, by-stage, examples or a partition), from settings.json. */
  chain?: string | null
  /** Each model role's model name, the partner first (an older run names employee, simulation and the like), from
      settings.json. */
  models?: Record<string, string>
  /** Each model role's reasoning effort, from settings.json. */
  efforts?: Record<string, string>
  /** Why the suite stopped the run, from suite-summary.json. */
  stopped?: string | null
  /** The suite's total model spend for the run in USD. */
  spend?: number | null
  /** The value judge's verdict (qualifies, partial or none) and score, from suite-summary.json. */
  verdict?: string | null
  score?: number | null
}

export interface RecordRow {
  kind: string
  turn_id?: string | null
  [key: string]: unknown
}

export interface Execution {
  turn_id: string
  artifact_id: string
  records: RecordRow[]
  /** Kept copies of the files the turn handed over through deliver_files. */
  deliverables?: string[]
  /** How the turn ended; a turn that ran past the worker's timeout says `timed_out` with the `timeout` in seconds
      (experimental/harness/raven_adapter/worker.py TurnTimeoutError). */
  outcome?: Record<string, unknown>
  /** The run view's copy keeps only what the page reads of records it counts (webui/serve.py `slim`); the turn's
      whole records come from /api/turn. */
  records_cut?: boolean
}

export interface Exchange {
  user: string
  execution: Execution
}

export interface Item {
  id: string
  result: 'pass' | 'fail' | 'unknown' | number
  session: string | null
  expected: string
  actual: string
  note: string
  /** Where the criterion behind `expected` comes from (experimental/harness/participation/protocols.py Item): a counterpart's check, a
      dataset case, an earlier requirement held as a regression check, or a handed-over material it was drawn from. */
  basis?: '' | 'check' | 'case' | 'requirement' | 'material'
}

/** Where a material came from when the counterpart did not simply give it: induced or researched before the cultivation
    (experimental/harness/scenario/contract.py Origin), whether the counterpart confirmed it, and the ids of the rules or findings
    it holds. */
export interface MaterialOrigin {
  origin: string
  confirmed: boolean
  items: string[]
}

/** One material handed over with a signal (experimental/harness/participation/protocols.py Handover): its kind in the
    scenario's terms and its files relative to the employee's agent home (uploads/<material>/...). */
export interface Handover {
  name: string
  kind: 'norm' | 'fact' | 'exemplar' | 'counterexample' | string
  files: string[]
}

export interface Signal {
  /** agency for the owner, standard for the automatic standard assessor, or another assessor's name. */
  source: string
  text: string
  items: Item[]
  metrics: Record<string, number>
  satisfied: boolean | null
  attachments?: Handover[]
}

export interface Requirement {
  /** The loop's id (R1, R2 ...); a requirement raised again keeps the earlier id and names it in `repeats`. */
  id?: string
  /** The class of situation in which the behavior is expected. */
  situation?: string
  behavior: string
  observed: string
  evidence: string[]
  expectation: 'new' | 'unmet' | 'met_but_rejected'
  acceptance: string
  strength: 'must_hold' | 'should'
  recurrence?: number
  locations?: string[]
  repeats?: string | null
  /** The judgements it rests on (assessor:<name>, check:<item id>, case:<id>); the Curator never receives them. */
  grounds?: string[]
  /** The handed-over materials it draws on, by name. */
  materials?: string[]
}

export interface Feedback {
  decision: 'curate' | 'continue' | 'supplement' | 'clarify' | 'stop'
  reason: string
  requirements: Requirement[]
  filtered: string[]
  task_updates: string[]
}

export type Treatment = 'modify' | 'replace' | 'add'

export interface Change {
  target: string
  reason: string
  expected: string
  verification: string
  /** Whether the change modifies the diagnosed mechanism, replaces it or adds one beside it. */
  treatment?: Treatment | null
}

export interface Artifact {
  values: Record<string, unknown>
  files: Record<string, string>
  /** Target bindings the revision retires. */
  remove?: string[]
  /** Artifact files the revision retires. */
  remove_files?: string[]
}

/** The closed set of states an attribution puts an input in (experimental/harness/contract/attribution.py). */
export type DiagnosisState =
  | 'absent'
  | 'not_exposed'
  | 'not_triggered'
  | 'not_consumed'
  | 'wrong_logic'
  | 'blocked'
  | 'model_ignored'
  | 'uncovered'

export interface Diagnosis {
  /** A requirement id, material:<name>, node:<playbook>/<node>#<n>, or task. */
  about: string
  state: DiagnosisState | string
  mechanism?: string
  evidence?: string[]
  earlier?: string
  /** For a material: where its content lands and how the worker reads it. */
  placement?: string
}

/** Which attributor made an attribution: its implementation, prompts digest, model and options. */
export type AttributorIdentity = Record<string, unknown> & { implementation?: string; prompts?: string; model?: string | null }

/** The selection a generation grounded its targets on: for each target, the diagnosed inputs it addresses. */
export interface Selection {
  understanding: string
  targets: string[]
  grounds: Record<string, string[]>
}

/** An attribution record under the worker's attribution/ directory, joined by records.load. */
export interface AttributionRecord {
  file?: string
  missing?: string
  identity?: AttributorIdentity
  revision?: string
  subjects?: string[]
  input_key?: string
  calls?: number
  queries?: number
  /** The attributor's request, cut to its size by studio.py. */
  request?: unknown
  trace?: TraceEvent[]
  attribution?: { diagnoses: Diagnosis[] }
  /** Why the attribution paused; it resumes on the next call. */
  paused?: string
  error?: string
}

export interface TraceEvent {
  event: string
  stage?: string
  tool?: string
  [key: string]: unknown
}

export interface Budget {
  calls: number
  queries: number
  checks?: number
  repairs?: number
}

export interface HarnessPlan {
  understanding: string
  design?: string
  changes: Change[]
  node_reasons?: Record<string, string>
}

export interface Generated {
  candidate: {
    plan: HarnessPlan
    artifact: Artifact
    /** The attribution the plan was chosen from, with its attributor and its record's file name. */
    attribution?: { attribution: { diagnoses: Diagnosis[] }; identity?: AttributorIdentity; record?: string } | null
    selection?: Selection | null
  }
  validation: { errors: string[]; observations: ({ kind?: string; targets?: string[] } & Record<string, unknown>)[] }
  /** Starts with the attribution's investigation (stage diagnose), then the generation's stages. */
  trace: TraceEvent[]
}

export interface Curation {
  file?: string
  missing?: string
  error?: string
  active_artifact_id?: string
  changed?: boolean
  /** What the Curator was handed. */
  feedback?: unknown
  /** The root's attribution record by file name, and the identity of its attributor. */
  attribution?: string
  attributor?: AttributorIdentity
  /** What a composite curation spent: the shared generation budget and every scope's attributions. */
  budget?: { generation?: Budget; attribution?: Budget }
  /** A curation interrupted before it installed anything; the next call resumes it. `stage` is where it stopped (diagnose
      while attributing) and, for a composite curation, `scope` the harness it was generating (root or child/<name>). */
  paused?: { stage?: string; scope?: string; reason?: string; checkpoint?: string; calls?: number; queries?: number; attribution?: Budget }
  child_changes?: Record<string, Generated>
  withdrawn_children?: string[]
  revision?: { root: Artifact; children: Record<string, { artifact: Artifact; plan: HarnessPlan | null }> }
  generated?: Generated
}

export interface Analysis {
  file?: string
  missing?: string
  error?: string
  trace: { event: string; label?: string; tool?: string; error?: string }[]
  feedback?: Feedback
}

export interface Round {
  sessions: Record<string, Exchange[]>
  signals: Signal[]
  /** The round's verdicts by assessor, which the server joins in: a signal's own items, or the scorecard an assessor
      that only speaks (the simulated owner) kept in the analysis records. */
  verdicts?: Signal[]
  feedback: Feedback | null
  /** Whether the loop curated after this round; false for a round whose Curator reported a gap. */
  curated: boolean
  analysis: Analysis[]
  curation: Curation[]
  attribution?: AttributionRecord[]
  /** Held-out trials of the round and their assessment: recorded and measured, never read by the Analyst or cited
      to the Curator. */
  holdout?: Record<string, Exchange[]>
  holdout_signals?: Signal[]
}

/** A requirement as the history keeps it; `held` is decided by the round after its revision. */
export interface Raised {
  id: string
  situation?: string
  behavior: string
  strength: string
  acceptance: string
  repeats?: string | null
  materials?: string[]
  grounds?: string[]
  held?: boolean | null
}

export interface Revised {
  /** The harness the change is in: root, or child/<name> for a child harness of a composite curation. */
  scope?: string
  target: string
  treatment?: Treatment | null
  reason?: string
  /** The inputs (diagnosis abouts) the selection grounded this target on. */
  addresses?: string[]
  expected?: string
  verification?: string
}

/** One round of the typed history (experimental/harness/loop/history.py); round 0 is onboarding. */
export interface HistoryEntry {
  round: number
  satisfied?: Record<string, boolean | null>
  results?: Record<string, Record<string, unknown>>
  failed_in?: Record<string, Record<string, string>>
  requirements: Raised[]
  mechanisms_acted?: Record<string, unknown>[]
  understanding?: string
  /** None when nothing was revised after the round. */
  revision: Revised[] | null
  /** Each diagnosis with the harness scope whose attribution made it (root, or child/<name>). */
  diagnoses: { about: string; state: string; mechanism?: string; earlier?: string; scope?: string }[] | null
  attributor: AttributorIdentity | null
}

/** One requirement joined along the loop's chain: diagnosis, changes grounded on it, whether it held. */
export interface LedgerJoin {
  round: number
  requirement: string
  situation?: string
  strength?: string
  repeats?: string | null
  /** The root's diagnosis, else the first scope's. */
  state: string | null
  mechanism: string | null
  /** Every scope's diagnosis of it, the root's among them, for a composite curation. */
  diagnoses?: { scope: string; state: string }[]
  attributor: AttributorIdentity | null
  curated: boolean
  /** The changes that address it, in any harness scope. */
  changes: { scope?: string; target: string; treatment: Treatment | null }[]
  held: boolean | null
}

export interface LedgerGroup {
  attributor: AttributorIdentity | null
  state: string | null
  treatment: Treatment | null
  judged: number
  held: number
}

export interface HeldOut {
  round: number
  source: string
  satisfied: boolean | null
  items: number
  passed: number
  failed: number
}

export interface Ledger {
  rows: LedgerJoin[]
  summary: LedgerGroup[]
  holdout: HeldOut[]
}

/** A gap the Curator reported instead of revising; the round stays unrevised and the question waits here. */
export interface Question {
  round: number
  stage: string
  question: string
}

/** A criterion of the automatic standard assessor (experimental/harness/assessor/standard.py). */
export interface StandardCriterion {
  id: string
  parent_id?: string | null
  text: string
  subject?: string
  derivation?: string
  evidence_requirements?: { kind: string; reference: string }[]
  source: 'declared' | 'derived' | 'sedimented' | string
  strength: 'must_hold' | 'should' | string
  provenance: string
  situation?: string
  acceptance?: string
  /** For a derived criterion, the norm passage it rests on, verbatim. */
  quote?: string
  kind?: 'gate' | 'guardrail' | 'quality' | ''
  authority?: 'external' | 'model' | ''
  checks?: { method: string; spec: string; role?: 'decision' | 'required' }[]
}

/** One change of a rubric builder revision (experimental/harness/assessor/builder.py), with its reason. */
export interface StandardChange {
  id: string
  parent_id?: string | null
  op: 'add' | 'rewrite' | 'remove' | string
  reason: string
  explanation: string
  /** The criterion's text before a rewrite or removal. */
  before: string
  /** The criterion as added or rewritten, the norm it rests on and the passage it quotes. */
  text: string
  material: string
  quote: string
}

/** One numbered revision of the derived criteria: the norms new to it, what it changed, and the passages it found
    nothing checkable in. */
export interface StandardRevision {
  version: number
  base_version?: string
  rubric_version?: string
  note?: string
  scope?: { allow: { op: string; id?: string | null; parent_id?: string | null; fields: string[] }[] }
  new_norms: string[]
  changes: StandardChange[]
  unchecked: { material: string; section: string; reason: string }[]
}

/** standard.json, written when the run ends; `calls` counts its model calls by label (rubric_builder, assessor). */
export interface StandardRecord {
  criteria: StandardCriterion[]
  /** The norms the rubric builder read. */
  derived_from: string[]
  revisions?: StandardRevision[]
  calls?: Record<string, number>
  error?: string
  construction?: { status: string; calls?: number; added?: number; error?: string; reason?: string; rubric_version?: string; steps?: { target: string; status: string; note: string }[] }[]
  pending?: { target: string; reason: string }[]
  assessments?: {
    id: string
    version: number
    rubric_version?: string
    repair_status?: string
    repair_validation?: Record<string, { accepted: boolean; error?: string; kind?: string }>
    repair_rejected?: string
    evidence_restored?: string[]
    checks: { criterion: string; method: string; result: string; actual: string; note: string }[]
    review?: { issues: { criterion: string; target: string; evidence: string; correction: string }[] }
    unresolved?: Record<string, string>
    review_error?: string
    repair_error?: string
    learning_error?: string
  }[]
  guidance?: {
    entries: { id: string; state: string; kind: string; scope: string; text: string; episodes: string[] }[]
    history: { candidate?: string; accepted?: boolean; error?: string; rollback?: string; comparisons?: { case: string; before: boolean | null; after: boolean | null; oracle: { result: string; actual: string } }[] }[]
  }
}

export interface Promotion {
  status: 'candidate' | 'accepted' | 'rejected'
  reason: string
  revision?: string
  witnesses?: { satisfied: boolean | null; error?: string; policy: { kind: string } }[]
}

/** The research stage's records under information/ (experimental/cultivation/collector/, read by rundir.research): how the
    collection before onboarding ended, the review's verdict, each dimension's coverage, and the calls per stage with
    every reply that was missing, rejected or failed. */
export interface ResearchRecord {
  status: string
  stop_reason: string
  seconds?: number | null
  review: { accepted: boolean; reason: string; issues: string[] }
  title: string
  sections: { dimension: string; coverage: string; text: string; reason: string; evidence: number; channels?: string[] }[]
  resources: { name: string; purpose: string; availability: string }[]
  unresolved: { dimension: string; question: string; reason: string; blocking: boolean }[]
  stages: { stage: string; calls: number; queries: number; submitted: boolean }[]
  trouble: { stage: string; event: string; error: string; tools: string[]; charged: boolean }[]
  /** Evidence count by channel: request (the task), tool (materials read), research (the web), user (the counterpart's answers). */
  channels?: Record<string, number>
  /** The research and answer evidence itself: the question each answers, and a finding, a group's synthesis or the
      counterpart's answer (`kind` empty when it could not answer). */
  evidence?: {
    id: string
    channel: string
    kind: 'finding' | 'synthesis' | 'answer' | ''
    question: string
    attempt: string
    text: string
    sources: string[]
    dimensions: string[]
  }[]
  /** Every research group of every wave. */
  groups?: {
    wave: string
    group: number | null
    status: string
    dimensions: string[]
    questions: string[]
    error: string
    admitted: number
    refused: number
    withheld: number
    unanswered: number
    seconds?: number | null
  }[]
  /** Each research agent the collector ran: the model asked for and its effort, the models it reported answering
      with (a Claude Code agent may hand parts to a smaller model) and its calls. */
  researchers?: { agent: string; asked: string | null; effort: string | null; models: string[]; calls: number }[]
  errors: string[]
}

/** One row of boundaries.jsonl: a role's compartment entered, a value admitted, a violation or leaving. */
export interface BoundaryRow {
  time: number | null
  role: string
  event: 'enter' | 'admit' | 'violation' | 'leave' | string
  where: string
  hits: string[]
}

export interface Boundaries {
  rows: BoundaryRow[]
  violations: BoundaryRow[]
  counts: Record<string, Record<string, number>>
  total: number
  error?: string
}

/** The round in progress as the record keeps it until the round is analysed (or curated). */
export interface Pending {
  sessions?: Record<string, Exchange[]>
  signals?: Signal[]
  holdout?: Record<string, Exchange[]>
  holdout_signals?: Signal[]
  review?: { activity: unknown[] }
}

export interface Run {
  task_id: string
  task: string
  status?: RunStatus
  stop?: string
  curator?: string
  rounds: Round[]
  initial_curation: Curation[]
  initial_attribution?: AttributionRecord[]
  /** Signals the first curation took as its feedback, such as the owner's onboarding message. */
  opening?: Signal[]
  error?: string
  history?: HistoryEntry[]
  ledger?: Ledger
  questions?: Question[]
  /** Assessors whose signals only measure each round: recorded, kept from the Analyst and the Curator
      (experimental/harness/loop/session.py `measuring`), such as an owner who watches without speaking. */
  measuring?: string[]
  pending?: Pending
  /** Each session the record names, with the opaque label it goes by wherever the Curator sees it
      (experimental/harness/participation/hearing.py opaque); the server adds it beside the record. */
  labels?: Record<string, string>
  /** Each material the counterpart did not simply give, by name, from the provenance the run's settings keep. */
  origins?: Record<string, MaterialOrigin>
  standard?: StandardRecord | null
  promotion?: Promotion
  stable_revision?: Promotion
  research?: ResearchRecord | null
  boundaries?: Boundaries | null
}

export interface Criterion {
  id: string
  check: string
  severity: 'red_line' | 'standard'
}

/** What /api/scenario serves: empty lists when the server has no scenario or an older server answers. */
export interface Scenario {
  criteria: Criterion[]
  initial: string[]
  materials: string[]
}
