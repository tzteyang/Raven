/* The Studio's one view model. A recorded automated run (replay.ts) and an
   interactive session (live.ts) are both turned into a Thread: a conversation
   in which each change request leads to one background process card (the
   Analyst's decision, then the curation: the Curator's diagnosis of every
   input, its selection grounded on it and the revision), each installed
   version gets its trials, and the choice of what to do next sits between
   rounds. The components draw only this shape, so both modes read the same. */

import type { AttributionView } from '../attribution'
import type { Playbook } from './harness'
import type {
  Artifact,
  Boundaries,
  Budget,
  Exchange,
  Feedback,
  Handover,
  HarnessPlan,
  HistoryEntry,
  Ledger,
  MaterialOrigin,
  Question,
  Selection,
  Signal,
  StandardCriterion,
  StandardRecord,
} from '../model'

export type Mode = 'live' | 'replay'

/** The root Harness and each child Harness, as installed at one version. */
export interface HarnessState {
  root: Artifact
  children: Record<string, Artifact>
}

export type StageId = 'diagnose' | 'select' | 'design' | 'implement' | 'validate' | 'repair' | 'install'
export type StageState = 'done' | 'current' | 'todo' | 'skipped' | 'failed' | 'paused'

export interface Stage {
  id: StageId
  state: StageState
  calls: number
  queries: number
}

/** An observation a curation was handed: a trial turn the Analyst cited (the Curator saw it under `label`, its
    session's opaque label, empty when the server named none), or, first in a child's list, that child's own current
    execution. */
export interface Observed {
  kind: 'turn' | 'current'
  /** The drill's session key; empty for a child's current execution. */
  session: string
  turn: number
  user: string
  label: string
}

/** The observations of a curation by index: the root's and each child harness's. */
export interface ObservedLists {
  root: Observed[]
  children: Record<string, Observed[]>
}

/** What a candidate's preparation did, from the host check's strategy.setup and capability rows. */
export interface Prepared {
  owner: string
  operation: string
  summary: string
}

/** Something the Curator submitted at a stage, as its generation trace kept it; `candidate.plan` is the final plan
    the card renders. */
export interface Output {
  stage: string
  event: string
  value: unknown
}

/** One read-only query the Curator made while generating. */
export interface Read {
  stage: string
  tool: string
  target: string
  preview: string
  failed: boolean
  observed: Observed | null
}

/** One scope of a composed curation: the root, or a child Harness the root's plan asked to change. */
export interface Scope {
  name: string
  root: boolean
  plan: HarnessPlan | null
  stages: Stage[]
  reads: Read[]
  outputs: Output[]
  /** The scope's own attribution, which its selection grounded each target on. */
  attribution: AttributionView | null
  selection: Selection | null
  prepared: Prepared[]
  /** The playbooks the scope's planning strategy compiled when the candidate was prepared. */
  playbooks: Playbook[]
}

export interface CurationView {
  /** The version the curation started from and the one it produced; equal when nothing was installed. */
  from: string
  to: string
  deployed: boolean
  error: string | null
  scopes: Scope[]
  before: HarnessState
  after: HarnessState
  validation: { errors: string[]; observations: number }
  /** What the Curator was handed: the curation record's feedback field. */
  input: unknown
  /** How many trial turns it was also handed as observations, which the record does not keep. */
  observed: number
  /** What a composite curation spent, generation and attribution apart. */
  budget: { generation?: Budget; attribution?: Budget } | null
  /** Where an interrupted curation stopped, and in which harness (root or child/<name>); it resumes on the next call. */
  paused: { stage: StageId | null; scope: string; reason: string } | null
}

export interface TrialView {
  id: string
  title: string
  version: string
  status: 'running' | 'done'
  exchanges: Exchange[]
  /** A replay's trials are recorded drills; a live session's are the user's own conversations. */
  source: 'recorded' | 'live'
  /** A held-out drill: recorded and assessed, never read by the Analyst or cited to the Curator. */
  holdout?: boolean
  /** Waiting for the agent's reply to the last message. */
  busy?: boolean
}

/** Where a live curation under way stands, from the Curator's progress file: its stage, what it has spent so far and,
    in a composite curation, the child harness it is revising. */
export interface CurationProgress {
  stage: StageId
  calls: number
  queries: number
  scope: string | null
}

export type Footer =
  | { kind: 'curating'; version: string }
  | { kind: 'review'; version: string }
  | { kind: 'interrupted'; version: string }
  | { kind: 'deployed'; version: string }
  | { kind: 'kept'; version: string; reason: string }
  | { kind: 'continue'; version: string }
  | { kind: 'supplement'; version: string; need: string }
  | { kind: 'clarify'; version: string; question: string }
  | { kind: 'stop'; version: string; handoverUnused: boolean }
  | { kind: 'last-round'; version: string }
  | { kind: 'asked'; version: string; stage: string; question: string }
  | { kind: 'paused'; version: string; stage: string | null; scope: string; reason: string }
  | { kind: 'failed'; version: string; error: string }
  | { kind: 'analysis-failed'; error: string }
  | { kind: 'analysing' }

export interface HeadEntry {
  kind: 'head'
  key: string
  task: string
  baseline: string
  models: Record<string, string>
  note?: string
}

export interface RequestEntry {
  kind: 'request'
  key: string
  round: number
  speaker: string
  you: boolean
  text: string
  attachments: Handover[]
  onboarding: boolean
}

/** The automatic standard assessor's signal: a scorecard, not a remark; it has no voice of its own. */
export interface ScoreEntry {
  kind: 'score'
  key: string
  round: number
  signal: Signal
  /** The criteria standard.json keeps (source, strength, provenance), when the run ended and wrote it. */
  criteria: StandardCriterion[]
  holdout: boolean
}

export interface ProcessEntry {
  kind: 'process'
  key: string
  round: number
  onboarding: boolean
  analysis: 'none' | 'running' | 'done' | 'failed'
  feedback: Feedback | null
  /** The signals the Analyst read. */
  signals: Signal[]
  /** Records the assessor kept for itself (its scorecard), which never reach the Curator. */
  assessor: unknown[]
  /** A curation that ran because the request handed material over although the Analyst did not ask for one. */
  handover: boolean
  /** Per requirement raised this round, whether it held in the round after its revision (the history's reading). */
  held: Record<string, boolean | null>
  curation: CurationView | null
  /** The attribution of a round whose curation left no record, such as one interrupted or asking a question. */
  attribution: AttributionView | null
  curationState: 'none' | 'running' | 'done' | 'failed'
  /** While a live curation runs, and before it leaves a record: how far it has got. */
  progress?: CurationProgress
  footer: Footer
}

export interface TrialsEntry {
  kind: 'trials'
  key: string
  round: number
  version: string
  trials: TrialView[]
  /** The round's held-out drills, or the round still in progress. */
  holdout?: boolean
  pending?: boolean
}

export interface NoteEntry {
  kind: 'note'
  key: string
  tone: 'choice' | 'auto' | 'end' | 'archive'
  text: string
}

export type Entry = HeadEntry | RequestEntry | ScoreEntry | ProcessEntry | TrialsEntry | NoteEntry

/** What a round's attribution record and selection say of one input, keyed `${round}:${about}`; the ledger counts
    the typed history, which may lack them. */
export interface Recorded {
  state: string
  changes: { target: string; treatment: string | null }[]
}

export interface Thread {
  id: string
  title: string
  mode: Mode
  entries: Entry[]
  /** v0, v1, ... in the order they were installed. */
  versions: string[]
  current: string
  status: string
  archived?: { name: string; version: string }
  /** The run this thread shows: a recorded run, or a live session's own once its process opened the record. */
  source?: string
  /** A recorded run's typed history, ledger, open questions, standard and compartment log. */
  history?: HistoryEntry[]
  ledger?: Ledger | null
  questions?: Question[]
  standard?: StandardRecord | null
  boundaries?: Boundaries | null
  recorded?: Record<string, Recorded>
  /** Materials the party did not simply give (induced or researched), by name. */
  origins?: Record<string, MaterialOrigin>
}
