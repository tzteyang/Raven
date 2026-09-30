/* What a Harness change is, read from its target and the binding value the
   revision authored. A Harness has four first-class strategies, each one
   factory binding (experimental/curator/raven_adapter/targets/): memory,
   planning, capability and action. A binding names the factory whose code the
   artifact's files hold, and switches on the host consumers the strategy is
   called from (the binding classes in raven_adapter/<strategy>/contracts.py). */

import type { Artifact } from './model'

export const STRATEGIES = ['memory', 'planning', 'capability', 'action'] as const
export type Strategy = (typeof STRATEGIES)[number]

/** The strategy a target binds, from its leading part; null for anything else. */
export function strategyOf(target: string): Strategy | null {
  const head = target.split('.')[0]
  return (STRATEGIES as readonly string[]).includes(head) ? (head as Strategy) : null
}

/** What each strategy owns, after the effect its target declares. */
export const OWNS: Record<Strategy, string> = {
  memory: 'Context: prepares the profile and storage, initialises each session and composes every model input',
  planning: 'The session plan: initialises and revises it through interactions, projects its view and guidance, and prepares reusable playbooks',
  capability: 'Tools and Skills: registers the resources it prepares and selects the active ones before each model call',
  action: 'Judgments: handles host events and agent requests, and requests controls (reject, revise, finish) that the host applies or refuses',
}

export interface Hook {
  /** The binding field: factory, events, tool, dispatch, requests, context, observe, intake, archive, compact, sources. */
  name: string
  value: string
}

const obj = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
const list = (value: unknown): string[] => (Array.isArray(value) ? value.map(String) : [])

/** The factory a binding names and every host consumer it switches on, in the binding's own terms. */
export function hooks(target: string, value: unknown): Hook[] {
  const binding = obj(value)
  const out: Hook[] = []
  if (typeof binding.factory === 'string') out.push({ name: 'factory', value: binding.factory })
  const tool = obj(binding.tool)
  if (typeof tool.name === 'string') out.push({ name: 'tool', value: tool.name })
  if (binding.requests === true) out.push({ name: 'requests', value: 'peer requests' })
  const strategy = strategyOf(target)
  if (strategy === 'action') {
    const events = list(binding.events)
    out.push({ name: 'events', value: (events.length ? events : ['proposal']).join(', ') })
    if (binding.dispatch === true) out.push({ name: 'dispatch', value: 'per-call gate' })
  }
  if (strategy === 'planning') {
    if (binding.context === true) out.push({ name: 'context', value: 'guidance before model calls' })
    const phases = list(binding.observe)
    if (phases.length) out.push({ name: 'observe', value: phases.join(', ') })
  }
  if (strategy === 'memory') {
    if (binding.observe === true) out.push({ name: 'observe', value: 'host evidence' })
    if (binding.intake === true) out.push({ name: 'intake', value: 'before initialize' })
    if (binding.archive === true) out.push({ name: 'archive', value: 'each sent turn' })
    const compact = list(binding.compact)
    if (compact.length) out.push({ name: 'compact', value: compact.join(', ') })
    if (binding.require_sources === false) out.push({ name: 'sources', value: 'opaque baseline accepted' })
  }
  return out
}

const REFERENCE = /([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*):[A-Za-z_]\w*/g

/** Generated modules a value names as module:symbol entry points. */
export function referenced(value: unknown, files: Record<string, string>): string[] {
  const text = JSON.stringify(value ?? null)
  const found = new Set<string>()
  for (const match of text.matchAll(REFERENCE)) {
    const module = match[1].replace(/\./g, '/')
    for (const path of [`${module}.py`, `${module}/__init__.py`]) if (path in files) found.add(path)
  }
  return [...found]
}

/** The artifact files a target consists of: the modules its binding names, then the supporting files those modules
    name by path (a profile text, a template). */
export function targetFiles(target: string, artifact: Artifact): string[] {
  if (!(target in artifact.values)) return []
  const modules = referenced(artifact.values[target], artifact.files)
  const source = modules.map((path) => artifact.files[path]).join('\n')
  const assets = Object.keys(artifact.files).filter((path) => !modules.includes(path) && source.includes(path))
  return [...modules, ...assets]
}

/** Artifact files no target's code names: supporting files the reader finds only in the artifact. */
export function looseFiles(artifact: Artifact): string[] {
  const claimed = new Set(Object.keys(artifact.values).flatMap((target) => targetFiles(target, artifact)))
  return Object.keys(artifact.files).filter((path) => !claimed.has(path))
}
