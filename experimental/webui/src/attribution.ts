/* The attribution before each curation and what followed it, read from the
   joined run: the diagnoses an attributor made of every input of the curation
   (a requirement by id, a handed-over material as material:<name>, a node
   requirement routed to a child as node:<playbook>/<node>#<n>, or the task),
   which attributor made them and what it spent, the selection that grounded
   each target on them, and whether each requirement held in the round after
   its revision. `held` is the loop's own reading, kept in the typed history
   (experimental/iteration/ledger.py decides it); this page only shows it. */

import type { AttributionRecord, AttributorIdentity, Curation, Diagnosis, DiagnosisState, Generated, HistoryEntry, Run, Selection } from './model'

/** The closed set of diagnosis states, in the order the attribution contract lists them. */
export const STATES: DiagnosisState[] = ['absent', 'not_exposed', 'not_triggered', 'not_consumed', 'wrong_logic', 'blocked', 'model_ignored', 'uncovered']

export interface AttributionView {
  /** The attribution record the diagnoses come from, when the round kept one. */
  record: AttributionRecord | null
  diagnoses: Diagnosis[]
  identity: AttributorIdentity | null
  /** What the attribution spent on its own budget. */
  calls: number | null
  queries: number | null
  /** The inputs it had to diagnose. */
  subjects: string[]
  paused: string | null
  error: string | null
}

/** The attribution records of a round; round 0 is onboarding. */
export const attributionsOf = (run: Run, round: number): AttributionRecord[] =>
  (round === 0 ? run.initial_attribution : run.rounds[round - 1]?.attribution) ?? []

const routed = (record: AttributionRecord): boolean => (record.subjects ?? []).some((about) => about.startsWith('node:'))

/* A composite curation copies every scope's attribution records beside the
   root's; a child's always carries the node requirements routed to it. A
   curation that paused before generating names no record, so the root's is
   then the round's completed one that routes nothing. */
function rootRecord(records: AttributionRecord[]): AttributionRecord | null {
  const roots = records.filter((record) => !routed(record))
  return roots.find((record) => record.attribution && !record.paused && !record.error) ?? roots[0] ?? null
}

/** The attribution one scope's generation was chosen from; for the root, the curation's own record name. */
export function attributionOf(curation: Curation | null, records: AttributionRecord[], generated?: Generated, root = true): AttributionView | null {
  const attached = generated?.candidate.attribution ?? null
  const name = attached?.record || (root ? curation?.attribution : undefined)
  const record = (name ? records.find((item) => item.file === name) : undefined) ?? (root && !attached ? rootRecord(records) : null)
  const diagnoses = attached?.attribution.diagnoses ?? record?.attribution?.diagnoses ?? []
  if (!record && !attached) return null
  return {
    record,
    diagnoses,
    identity: attached?.identity ?? record?.identity ?? (root ? curation?.attributor ?? null : null),
    calls: typeof record?.calls === 'number' ? record.calls : null,
    queries: typeof record?.queries === 'number' ? record.queries : null,
    subjects: record?.subjects ?? diagnoses.map((diagnosis) => diagnosis.about),
    paused: record?.paused ?? null,
    error: record?.error ?? null,
  }
}

/** The inputs a selection grounded each target on, as target -> diagnosis abouts; and the reverse. */
export function grounded(selection: Selection | null | undefined): { targets: Record<string, string[]>; by: Record<string, string[]> } {
  const targets = selection?.grounds ?? {}
  const by: Record<string, string[]> = {}
  for (const [target, abouts] of Object.entries(targets)) for (const about of abouts) (by[about] ??= []).push(target)
  return { targets, by }
}

/** The history entry of a round (0 is onboarding), when the record keeps one. */
export const entryOf = (run: Run, round: number): HistoryEntry | undefined => (run.history ?? []).find((entry) => entry.round === round)

/** Per requirement raised in `round`, whether it held in the round after its revision; null until that round is
    judged, and absent for a round the history does not keep. */
export function heldOf(run: Run, round: number): Record<string, boolean | null> {
  const entry = entryOf(run, round)
  return Object.fromEntries((entry?.requirements ?? []).map((raised) => [raised.id, raised.held ?? null]))
}

/** The attributor as one line: its model, implementation and a short prompts digest. */
export function identityLine(identity: AttributorIdentity | null | undefined): string {
  if (!identity) return ''
  const prompts = typeof identity.prompts === 'string' ? identity.prompts.slice(0, 8) : ''
  return [identity.model ? String(identity.model) : '', identity.implementation ? String(identity.implementation) : '', prompts ? `prompts ${prompts}` : '', identity.catalogue === false ? 'no catalogue' : '']
    .filter(Boolean)
    .join(' · ')
}

/** A material's name in an about, or null for any other input. */
export const materialOf = (about: string): string | null => (about.startsWith('material:') ? about.slice('material:'.length) : null)
