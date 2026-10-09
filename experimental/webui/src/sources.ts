/* What each rendered part of the cultivation conversation was drawn from: the slices of the curation record (or the
   round's signals and the Analyst's feedback) behind it, each with the path it sits at in that record, so the page
   can show a part as rendered or as its own source. A Curator change is backed by its plan entry, the binding value it
   authored, the modules that binding names, the generated modules those import, and the inputs it was grounded on. */

import { materialOf } from './attribution'
import { importsOf, targetFiles } from './mechanism'

import type { Reply } from './cultivation'
import type { Feedback, Signal } from './model'

export interface RawPart {
  /** Where the slice sits in its record, e.g. generated.candidate.plan.changes[0]. */
  path: string
  /** json: shown as the record's JSON; prose: Markdown source; code: a generated file, highlighted by its name. */
  as: 'json' | 'prose' | 'code'
  value: unknown
  /** The generated file's name, for a code slice. */
  file?: string
  /** Shown closed until opened: a supporting module, not the slice itself. */
  folded?: boolean
}

const key = (name: string): string => JSON.stringify(name)

const generatedOf = (reply: Reply) => reply.revision.curation.generated

export function understandingParts(reply: Reply): RawPart[] {
  return [{ path: 'generated.candidate.plan.understanding', as: 'prose', value: reply.understanding }]
}

export function designParts(reply: Reply): RawPart[] {
  return [{ path: 'generated.candidate.plan.design', as: 'prose', value: reply.design }]
}

export function selectionParts(reply: Reply): RawPart[] {
  if (!reply.selection) return []
  const { understanding, ...rest } = reply.selection
  return [
    { path: 'generated.candidate.selection.understanding', as: 'prose', value: understanding },
    { path: 'generated.candidate.selection', as: 'json', value: rest },
  ]
}

/** The diagnoses as the attribution record keeps them, else as the candidate carries them. */
export function diagnosisParts(reply: Reply): RawPart[] {
  const attached = generatedOf(reply)?.candidate.attribution
  if (attached) return [{ path: 'generated.candidate.attribution', as: 'json', value: attached }]
  const record = reply.attribution?.record
  return record ? [{ path: `attribution/${record.file ?? 'record'}`, as: 'json', value: record }] : []
}

/** One planned change: its plan entry, its binding value, the modules the binding names (and supporting files they
    name), the generated modules those import, and the inputs the selection grounded the target on. */
export function changeParts(reply: Reply, index: number): RawPart[] {
  const candidate = generatedOf(reply)?.candidate
  const entry = candidate?.plan.changes[index]
  if (!candidate || !entry) return []
  const artifact = { ...candidate.artifact, values: candidate.artifact.values ?? {}, files: candidate.artifact.files ?? {} }
  const target = entry.target
  const own = targetFiles(target, artifact)
  const used = [...new Set(own.flatMap((path) => importsOf(path, artifact.files)))].filter((path) => !own.includes(path))
  const grounds = candidate.selection?.grounds?.[target]
  return [
    { path: `generated.candidate.plan.changes[${index}]`, as: 'json', value: entry },
    ...(target in artifact.values ? [{ path: `generated.candidate.artifact.values[${key(target)}]`, as: 'json' as const, value: artifact.values[target] }] : []),
    ...own.map((path) => ({ path: `generated.candidate.artifact.files[${key(path)}]`, as: 'code' as const, value: artifact.files[path], file: path })),
    ...used.map((path) => ({ path: `generated.candidate.artifact.files[${key(path)}]`, as: 'code' as const, value: artifact.files[path], file: path, folded: true })),
    ...(grounds ? [{ path: `generated.candidate.selection.grounds[${key(target)}]`, as: 'json' as const, value: grounds }] : []),
  ]
}

/** What the owner handed over before this revision, with the diagnoses and grounds that name those materials. */
export function intakeParts(reply: Reply): RawPart[] {
  const names = new Set(reply.handover.map((item) => item.name))
  const diagnoses = (reply.attribution?.diagnoses ?? []).filter((diagnosis) => names.has(materialOf(diagnosis.about) ?? ''))
  const grounds = Object.fromEntries(
    Object.entries(reply.selection?.grounds ?? {}).filter(([, abouts]) => abouts.some((about) => names.has(materialOf(about) ?? ''))),
  )
  return [
    { path: 'signals[].attachments', as: 'json', value: reply.handover.map(({ name, kind, files }) => ({ name, kind, files })) },
    ...(reply.pasted.length ? [{ path: 'signals[].text (pasted material titles)', as: 'json' as const, value: reply.pasted }] : []),
    ...(diagnoses.length ? [{ path: 'attribution.diagnoses (these materials)', as: 'json' as const, value: diagnoses }] : []),
    ...(Object.keys(grounds).length ? [{ path: 'generated.candidate.selection.grounds (these materials)', as: 'json' as const, value: grounds }] : []),
  ]
}

export function validationParts(reply: Reply): RawPart[] {
  const validation = generatedOf(reply)?.validation
  return validation ? [{ path: 'generated.validation', as: 'json', value: validation }] : []
}

/** Why a revision failed, as the record says it: its error, the missing record, its pause, or the host check. */
export function failureParts(reply: Reply): RawPart[] {
  const { curation } = reply.revision
  const fields = Object.fromEntries((['error', 'missing', 'paused'] as const).filter((name) => curation[name] !== undefined).map((name) => [name, curation[name]]))
  const errors = curation.generated?.validation.errors ?? []
  return [
    ...(Object.keys(fields).length ? [{ path: '(record fields)', as: 'json' as const, value: fields }] : []),
    ...(errors.length ? [{ path: 'generated.validation.errors', as: 'json' as const, value: errors }] : []),
  ]
}

export const feedbackParts = (feedback: Feedback): RawPart[] => [{ path: 'feedback', as: 'json', value: feedback }]

/** Each signal of the round: its text as the Markdown it was written in, then its other fields. */
export const signalParts = (signals: Signal[]): RawPart[] =>
  signals.flatMap((signal, i) => {
    const { text, ...rest } = signal
    return [
      ...(text ? [{ path: `signals[${i}].text (${signal.source})`, as: 'prose' as const, value: text }] : []),
      { path: `signals[${i}]${text ? ', without its text' : ` (${signal.source})`}`, as: 'json' as const, value: rest },
    ]
  })
