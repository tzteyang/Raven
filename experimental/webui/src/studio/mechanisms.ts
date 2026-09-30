/* What one turn's records say the four strategies did. An Action decision is
   a request and the host's receipt says whether it was applied (trial.ts
   reads both); only an applied receipt is an intervention, as
   experimental/analyst/activity.py counts it, and a tool refusal naming that
   control is the same intervention seen again. Raven's own refusals, the
   guidance Action and Planning put before the model, the strategies asking
   one another, capability selection and registration, Memory's organisation
   and compaction of the context and strategy errors are listed beside them. */

import { controls, interceptions } from '../trial'

import type { RecordRow } from '../model'
import type { Control, Interception } from '../trial'

type Row = RecordRow & Record<string, unknown>

const obj = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
const str = (value: unknown): string => (typeof value === 'string' ? value : value == null ? '' : JSON.stringify(value))
const names = (value: unknown): string[] =>
  Array.isArray(value) ? value.map((item) => (typeof item === 'string' ? item : str(obj(item).name))).filter(Boolean) : []

const STRATEGIES = ['action.', 'capability.', 'memory.', 'planning.', 'strategy.']

export type TurnEvent =
  | { kind: 'control'; control: Control }
  | { kind: 'refusal'; hit: Interception }
  | { kind: 'guidance'; source: 'action' | 'planning'; text: string }
  | { kind: 'peer'; target: string; operation: string; request: string; result: string }
  | { kind: 'select'; count: number; tools: string[]; skills: string[] }
  | { kind: 'register'; name: string; what: string; status: string; reason: string }
  | { kind: 'memory'; operation: string; summary: string }
  | { kind: 'error'; source: string; text: string }

export function turnEvents(records: RecordRow[]): TurnEvent[] {
  const placed: { at: number; event: TurnEvent }[] = controls(records).map((control) => ({ at: control.at, event: { kind: 'control', control } }))
  for (const hit of interceptions(records)) {
    if (hit.mechanism !== 'action.strategy') placed.push({ at: hit.at, event: { kind: 'refusal', hit } })
  }
  const registered = new Set<string>()
  const select = { count: 0, tools: new Set<string>(), skills: new Set<string>(), at: -1 }
  let asked: Row | undefined
  let organised = false
  let planned = ''
  ;(records as Row[]).forEach((row, at) => {
    const kind = str(row.kind)
    const add = (event: TurnEvent) => placed.push({ at, event })
    if (kind === 'action.result') {
      const result = obj(row['result'])
      const guidance = obj(result.decision ?? result).guidance
      if (typeof guidance === 'string' && guidance.trim()) add({ kind: 'guidance', source: 'action', text: guidance })
    } else if (kind === 'planning.context') {
      const content = str(row['content']).trim()
      if (content && content !== planned) add({ kind: 'guidance', source: 'planning', text: content })
      planned = content
    } else if (kind === 'strategy.peer_request') {
      asked = row
    } else if (kind === 'strategy.peer_result') {
      add({ kind: 'peer', target: str(row['target']), operation: str(row['operation']), request: str(asked?.['arguments']), result: str(row['result']) })
      asked = undefined
    } else if (kind === 'capability.result' && row['operation'] === 'select') {
      const result = obj(row['result'])
      select.count++
      select.at = at
      names(result.tools).forEach((name) => select.tools.add(name))
      names(result.skills).forEach((name) => select.skills.add(name))
    } else if (kind === 'capability.register' || kind === 'capability.registration') {
      const receipt = obj(row['receipt'])
      const key = [receipt.kind, receipt.name, receipt.candidate, receipt.status].map(str).join('|')
      if (!registered.has(key)) {
        registered.add(key)
        add({ kind: 'register', name: str(receipt.name), what: str(receipt.kind), status: str(receipt.status), reason: str(receipt.reason) })
      }
    } else if (kind === 'memory.result') {
      const operation = str(row['operation'])
      if (operation === 'initialize' && !organised) {
        organised = true
        add({ kind: 'memory', operation, summary: names(obj(row['result']).order).join(' › ') || str(row['result']) })
      } else if (operation !== 'initialize' && operation !== 'compose' && !(asked?.['target'] === 'memory' && asked['operation'] === operation)) {
        add({ kind: 'memory', operation, summary: str(row['result']) })
      }
    } else if (kind === 'memory.compaction') {
      add({ kind: 'memory', operation: 'compaction', summary: [str(row['pressure']), str(row['status']), str(row['error'])].filter(Boolean).join(' · ') })
    } else if (kind.endsWith('.error') && STRATEGIES.some((prefix) => kind.startsWith(prefix))) {
      add({ kind: 'error', source: [kind.split('.')[0], str(row['operation'])].filter(Boolean).join('.'), text: str(row['error']) })
    }
  })
  if (select.count) placed.push({ at: select.at, event: { kind: 'select', count: select.count, tools: [...select.tools], skills: [...select.skills] } })
  return placed.sort((a, b) => a.at - b.at).map(({ event }) => event)
}

/** Interventions in the Analyst's sense: applied controls, and a gate that refused a call because its check raised. */
export const interventions = (events: TurnEvent[]): number =>
  events.filter((event) => (event.kind === 'control' && event.control.status === 'applied') || (event.kind === 'refusal' && event.hit.kind === 'gate')).length

/** The model inputs of a turn: the assembled `model.input` where recorded, else the provider requests, each with
    the Memory context estimate taken for it. */
export function modelInputs(records: RecordRow[]): { row: Row; tokens: number | null; allowance: number | null }[] {
  const rows = records as Row[]
  const assembled = rows.some((row) => row.kind === 'model.input')
  const out: { row: Row; tokens: number | null; allowance: number | null }[] = []
  let context: Row | undefined
  for (const row of rows) {
    if (row.kind === 'memory.context') context = row
    if (row.kind === (assembled ? 'model.input' : 'provider.request')) {
      out.push({ row, tokens: context ? Number(context['estimated_tokens'] ?? 0) || null : null, allowance: context ? Number(context['allowance'] ?? 0) || null : null })
      context = undefined
    }
  }
  return out
}
