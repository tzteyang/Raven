/* A curation record as the Studio's process card shows it: for each scope
   (the root, then every child it changed) its attribution of every input, the
   selection that grounded each target on those diagnoses, the stages it went
   through and what it read (both from its generation trace, which starts with
   the attribution's investigation), its plan and what its preparation did,
   and the Harness before and after. The observations a curation is handed are
   not kept in its record; replay.ts rebuilds the lists from the round so a
   read names its turn by index. */

import { attributionOf } from '../attribution'
import { failure, overlay } from '../derive'
import { EMPTY, preparedPlaybooks } from './harness'

import type { AttributionView } from '../attribution'
import type { Artifact, AttributionRecord, Curation, Generated, TraceEvent } from '../model'
import type { CurationView, HarnessState, Observed, ObservedLists, Output, Prepared, Read, Scope, Stage, StageId } from './types'

export const STAGES: StageId[] = ['diagnose', 'select', 'design', 'implement', 'validate', 'repair', 'install']

type Trace = TraceEvent[]

// What each stage hands over, in the order the attribution and generation/run.py record it.
const SUBMITTED = new Set(['submit_diagnosis', 'report_gap', 'submit_selection', 'submit_plan', 'file.staged', 'preflight', 'submit_artifact', 'validation'])

const PREVIEW = 280
// raven/security/trust.py fences what a native tool returns; the preview shows only the body.
const FENCE = /^\[BEGIN UNTRUSTED [^\]]*\]\n?|\n?\[END UNTRUSTED [^\]]*\]$/g

const obj = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
const path = (value: unknown): string => (Array.isArray(value) && value.length ? ` · ${value.join('.')}` : '')
const text = (value: unknown): string => (typeof value === 'string' ? value : value == null ? '' : JSON.stringify(value))

/** The Curator's read-only queries in one trace, in the order it made them. */
export function reads(trace: Trace, observed: Observed[] = []): Read[] {
  return trace
    .filter((event) => event.event === 'query')
    .map((event) => {
      const args = obj(event.arguments)
      const result = obj(event.result)
      const failed = typeof result.error === 'string' || result.failed === true
      const body = String(result.error ?? result.text ?? '').replace(FENCE, '').replace(/\s+/g, ' ').trim()
      const index = event.tool === 'read_observation' && typeof args.index === 'number' ? args.index : null
      const tail = typeof args.path === 'string' ? args.path.split('/').slice(-2).join('/') : ''
      let target = [typeof args.pattern === 'string' ? `“${args.pattern}”` : '', tail].filter(Boolean).join(' · ') || JSON.stringify(event.arguments ?? {})
      if (event.tool === 'read_source') target = `${String(args.name ?? '')}${args.find ? ` · “${String(args.find)}”` : ''}`
      if (event.tool === 'read_fact') target = `${String(args.name ?? '')}${path(args.path)}`
      if (index !== null) target = `#${index}${path(args.path)}`
      return {
        stage: event.stage ?? '',
        tool: event.tool ?? '',
        target,
        preview: body.length > PREVIEW ? `${body.slice(0, PREVIEW)}…` : body,
        failed,
        observed: index === null ? null : observed[index] ?? null,
      }
    })
}

function counted(trace: Trace): Map<string, { calls: number; queries: number }> {
  const out = new Map<string, { calls: number; queries: number }>()
  for (const event of trace) {
    if (!event.stage) continue
    const row = out.get(event.stage) ?? { calls: 0, queries: 0 }
    if (event.event === 'model.call') row.calls++
    if (event.event === 'query') row.queries++
    out.set(event.stage, row)
  }
  return out
}

/** The final plan, then everything the Curator submitted or had checked, stage by stage. */
export function outputs(trace: Trace, plan: unknown): Output[] {
  const submitted = trace
    .filter((event) => SUBMITTED.has(event.event))
    .map((event) => {
      const { stage, event: name, ...rest } = event
      const value = 'output' in rest ? rest.output : rest
      return { stage: stage ?? '', event: name, value }
    })
  return plan ? [{ stage: '', event: 'candidate.plan', value: plan }, ...submitted] : submitted
}

/* The generation trace keeps the attribution's investigation without its
   model calls, so the diagnose stage counts what the attribution record says
   it spent. */
function diagnoseCounts(trace: Trace, attribution: AttributionView | null): { calls: number; queries: number } {
  const seen = counted(trace).get('diagnose') ?? { calls: 0, queries: 0 }
  return { calls: attribution?.calls ?? seen.calls, queries: attribution?.queries ?? seen.queries }
}

/** The stages of a finished generation; repair is skipped when nothing needed repairing. */
export function finishedStages(trace: Trace, deployed: boolean, failed: boolean, attribution: AttributionView | null = null): Stage[] {
  const seen = counted(trace)
  return STAGES.map((id) => {
    if (id === 'diagnose') {
      const state: Stage['state'] = attribution?.error ? 'failed' : attribution?.paused ? 'paused' : 'done'
      return { id, state, ...diagnoseCounts(trace, attribution) }
    }
    const row = seen.get(id) ?? { calls: 0, queries: 0 }
    let state: Stage['state'] = 'done'
    if (id === 'repair' && !seen.has('repair')) state = 'skipped'
    if (id === 'validate' && failed) state = 'failed'
    if (id === 'install') state = deployed ? 'done' : failed ? 'failed' : 'skipped'
    if (!['repair', 'install', 'validate'].includes(id) && !seen.has(id)) state = failed ? 'skipped' : 'done'
    return { id, state, ...row }
  })
}

/** The stages of a curation interrupted at `at`: earlier ones done, that one paused, later ones to come. */
export function pausedStages(trace: Trace, at: StageId, attribution: AttributionView | null): Stage[] {
  const seen = counted(trace)
  const index = STAGES.indexOf(at)
  return STAGES.map((id, i) => {
    const counts = id === 'diagnose' ? diagnoseCounts(trace, attribution) : seen.get(id) ?? { calls: 0, queries: 0 }
    const state: Stage['state'] = i < index ? (id === 'repair' ? 'skipped' : 'done') : i === index ? 'paused' : 'todo'
    return { id, state, ...counts }
  })
}

/** The same stages while a live curation is at `index`: earlier ones done, later ones to come. */
export function liveStages(stages: Stage[], index: number): Stage[] {
  return stages.map((stage, i) => {
    if (i < index) return stage.state === 'skipped' ? stage : { ...stage, state: 'done' }
    if (i === index) return { ...stage, state: 'current', calls: 0, queries: 0 }
    return { ...stage, state: stage.state === 'skipped' ? 'skipped' : 'todo', calls: 0, queries: 0 }
  })
}

/** Where an interrupted curation stopped, as its record names it (diagnose while it attributed). */
export function pausedAt(curation: Curation): StageId | null {
  const named = curation.paused?.stage
  return named && (STAGES as string[]).includes(named) ? (named as StageId) : null
}

const short = (value: unknown, limit = 160): string => {
  const body = text(value).replace(/\s+/g, ' ').trim()
  return body.length > limit ? `${body.slice(0, limit)}…` : body
}

/* What prepare did, one row per distinct effect: a strategy's setup (a profile
   written, skills pinned, a playbook compiled) and each capability staged. The
   host check prepares a candidate more than once, so repeats are dropped. */
export function prepared(observations: Record<string, unknown>[]): Prepared[] {
  const out: Prepared[] = []
  const seen = new Set<string>()
  const add = (row: Prepared) => {
    const key = `${row.owner}|${row.operation}|${row.summary}`
    if (seen.has(key)) return
    seen.add(key)
    out.push(row)
  }
  for (const row of observations) {
    if (row.kind === 'strategy.setup') {
      const value = row.value
      const operation = text(row.operation)
      let summary = short(value)
      if (operation === 'playbook') {
        const spec = obj(obj(value).spec)
        const nodes = Array.isArray(spec.nodes) ? spec.nodes.map((node) => text(obj(node).id)).filter(Boolean) : []
        summary = [text(spec.name), nodes.length ? `${nodes.length} nodes: ${nodes.join(', ')}` : ''].filter(Boolean).join(' · ')
      } else if (value && typeof value === 'object' && !Array.isArray(value)) {
        summary = Object.keys(value).join(', ')
      } else if (Array.isArray(value)) {
        summary = value.map((item) => text(item)).join(', ')
      }
      add({ owner: text(row.owner), operation, summary })
    } else if (row.kind === 'capability.registration') {
      const receipt = obj(row.receipt)
      add({ owner: 'capability', operation: 'register', summary: [text(receipt.kind), text(receipt.name), text(receipt.status)].filter(Boolean).join(' · ') })
    }
  }
  return out
}

/** The Harness a curation installed: its revision snapshot when the record has one, else its artifact laid over the prior state. */
export function stateAfter(curation: Curation, before: HarnessState): HarnessState {
  if (curation.revision?.root) {
    const children: Record<string, Artifact> = {}
    for (const [name, child] of Object.entries(curation.revision.children ?? {})) children[name] = child?.artifact ?? EMPTY
    return { root: curation.revision.root, children }
  }
  const children = { ...before.children }
  for (const [name, generated] of Object.entries(curation.child_changes ?? {})) {
    children[name] = overlay(before.children[name] ?? EMPTY, generated?.candidate?.artifact)
  }
  return { root: overlay(before.root, curation.generated?.candidate.artifact), children }
}

function scopeOf(name: string, root: boolean, generated: Generated | undefined, attribution: AttributionView | null, stages: Stage[], observed: Observed[]): Scope {
  const trace = generated?.trace ?? (root ? attribution?.record?.trace ?? [] : [])
  return {
    name,
    root,
    plan: generated?.candidate.plan ?? null,
    stages,
    reads: reads(trace, observed),
    outputs: outputs(trace, generated?.candidate.plan),
    attribution,
    selection: generated?.candidate.selection ?? null,
    prepared: prepared(generated?.validation.observations ?? []),
    playbooks: preparedPlaybooks(generated?.validation.observations ?? []),
  }
}

/** A child's observations when the round cited none of its turns: only its own current execution. */
const CURRENT: Observed[] = [{ kind: 'current', session: '', turn: -1, user: '', label: 'execution.current' }]

export function curationView(
  curation: Curation,
  before: HarnessState,
  from: string,
  to: string,
  deployed: boolean,
  observed: ObservedLists | null = null,
  attributions: AttributionRecord[] = [],
): CurationView {
  const error = failure(curation)
  const failed = !deployed && !!error && !curation.paused
  const generated = curation.generated
  const rootAttribution = attributionOf(curation, attributions, generated, true)
  const at = curation.paused ? pausedAt(curation) : null
  const stagesOf = (trace: Trace, attribution: AttributionView | null) =>
    at ? pausedStages(trace, at, attribution) : finishedStages(trace, deployed, failed, attribution)
  const rootTrace = generated?.trace ?? rootAttribution?.record?.trace ?? []
  const scopes: Scope[] = [
    scopeOf('', true, generated, rootAttribution, stagesOf(rootTrace, rootAttribution), observed?.root ?? []),
    ...Object.entries(curation.child_changes ?? {}).map(([name, child]) => {
      const attribution = attributionOf(null, attributions, child, false)
      return scopeOf(name, false, child, attribution, stagesOf(child?.trace ?? [], attribution), observed?.children[name] ?? CURRENT)
    }),
  ]
  const after = deployed ? stateAfter(curation, before) : before
  return {
    from,
    to,
    deployed,
    error: deployed ? null : error ?? (curation.changed === false ? 'unchanged' : null),
    scopes,
    before,
    after,
    validation: {
      errors: generated?.validation.errors ?? [],
      observations: generated?.validation.observations.length ?? 0,
    },
    input: curation.feedback ?? null,
    observed: observed?.root.length ?? 0,
    budget: curation.budget ?? null,
    paused: curation.paused ? { stage: at, scope: curation.paused.scope ?? 'root', reason: curation.paused.reason ?? '' } : null,
  }
}
