/* The Harness as the Studio draws it: which of the four strategies a target
   binds, what a target consists of (its binding value, the modules the
   binding names and the supporting files those modules name), how a target
   changed between two versions, and the playbooks a candidate's planning
   strategy prepared, as the host check recorded them. Targets follow
   experimental/curator/raven_adapter/targets/. */

import { STRATEGIES, looseFiles, strategyOf, targetFiles } from '../mechanism'

import type { Artifact } from '../model'
import type { HarnessState } from './types'

export const SURFACES = STRATEGIES
export type Surface = (typeof SURFACES)[number] | 'other'

export const EMPTY: Artifact = { values: {}, files: {} }
export const EMPTY_STATE: HarnessState = { root: EMPTY, children: {} }

export const surfaceOf = (target: string): Surface => strategyOf(target) ?? 'other'

/** The artifact's supporting files no target's code names, shown under this name. */
export const LOOSE = 'files'

export interface Document {
  path: string
  text: string
}

const pretty = (value: unknown): string => (typeof value === 'string' ? value : JSON.stringify(value, null, 2))

/** What a target consists of in one artifact: its binding value, then its code and the files that code names. */
export function documents(target: string, artifact: Artifact): Document[] {
  if (target === LOOSE) return looseFiles(artifact).map((path) => ({ path, text: artifact.files[path] }))
  if (!(target in artifact.values)) return []
  return [
    { path: `${target}.json`, text: pretty(artifact.values[target]) },
    ...targetFiles(target, artifact).map((path) => ({ path, text: artifact.files[path] })),
  ]
}

export interface DocumentChange {
  path: string
  before: string | null
  after: string | null
}

/** Each document of a target in either version, paired by path; unchanged ones are kept so a reader sees the whole target. */
export function targetChanges(target: string, before: Artifact, after: Artifact): DocumentChange[] {
  const old = new Map(documents(target, before).map((doc) => [doc.path, doc.text]))
  const now = new Map(documents(target, after).map((doc) => [doc.path, doc.text]))
  const paths = [...new Set([...now.keys(), ...old.keys()])]
  return paths.map((path) => ({ path, before: old.get(path) ?? null, after: now.get(path) ?? null }))
}

export type TargetState = 'new' | 'changed' | 'kept' | 'removed'

export function targetState(target: string, before: Artifact, after: Artifact): TargetState {
  const had = target === LOOSE ? looseFiles(before).length > 0 : target in before.values
  const has = target === LOOSE ? looseFiles(after).length > 0 : target in after.values
  if (!had && has) return 'new'
  if (had && !has) return 'removed'
  const changed = targetChanges(target, before, after).some((doc) => doc.before !== doc.after)
  return changed ? 'changed' : 'kept'
}

export interface Cell {
  target: string
  state: TargetState
}

export interface MapRow {
  scope: string
  root: boolean
  cells: Record<Surface, Cell[]>
  changed: number
}

const emptyCells = (): Record<Surface, Cell[]> => ({ memory: [], planning: [], capability: [], action: [], other: [] })

function row(scope: string, root: boolean, before: Artifact, after: Artifact): MapRow {
  const cells = emptyCells()
  const targets = [...new Set([...Object.keys(after.values), ...Object.keys(before.values)])].sort()
  if (looseFiles(after).length || looseFiles(before).length) targets.push(LOOSE)
  let changed = 0
  for (const target of targets) {
    const state = targetState(target, before, after)
    if (state !== 'kept') changed++
    cells[surfaceOf(target)].push({ target, state })
  }
  return { scope, root, cells, changed }
}

/** One row per Harness (the root, then each child) and one column per strategy. */
export function harnessMap(before: HarnessState, after: HarnessState, rootName: string): MapRow[] {
  const children = [...new Set([...Object.keys(after.children), ...Object.keys(before.children)])].sort()
  return [
    row(rootName, true, before.root, after.root),
    ...children.map((name) => row(name, false, before.children[name] ?? EMPTY, after.children[name] ?? EMPTY)),
  ]
}

export function artifactOf(state: HarnessState, scope: string, root: boolean): Artifact {
  return root ? state.root : state.children[scope] ?? EMPTY
}

export interface PlaybookNode {
  id: string
  subagent: string
  summary: string
  dependsOn: string[]
  /** The node's whole definition, to tell whether it changed. */
  raw: string
}

export interface Playbook {
  name: string
  nodes: PlaybookNode[]
}

const obj = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}

/* The planning strategy compiles its playbooks at prepare through the host
   (PlanningHost.playbook), which records each spec as a strategy.setup row of
   operation playbook; the nodes are the spec's own (raven's DagNodeSpec). */
export function preparedPlaybooks(observations: Record<string, unknown>[]): Playbook[] {
  const books = new Map<string, Playbook>()
  for (const row of observations) {
    if (row.kind !== 'strategy.setup' || row.operation !== 'playbook') continue
    const spec = obj(obj(row.value).spec)
    const name = typeof spec.name === 'string' ? spec.name : ''
    if (!name) continue
    const nodes = (Array.isArray(spec.nodes) ? spec.nodes : []).map((item): PlaybookNode => {
      const node = obj(item)
      const depends = node.depends_on ?? node.dependsOn
      return {
        id: String(node.id ?? ''),
        subagent: String(node.subagent ?? ''),
        summary: String(node.node_summary ?? node.nodeSummary ?? ''),
        dependsOn: Array.isArray(depends) ? depends.map(String) : [],
        raw: JSON.stringify(node),
      }
    })
    books.set(name, { name, nodes })
  }
  return [...books.values()].sort((a, b) => a.name.localeCompare(b.name))
}

/** Each node's layer: 0 without dependencies, else one more than its deepest dependency. */
export function layers(nodes: PlaybookNode[]): PlaybookNode[][] {
  const depth = new Map<string, number>()
  const byId = new Map(nodes.map((node) => [node.id, node]))
  const visit = (id: string, seen: Set<string>): number => {
    if (depth.has(id)) return depth.get(id)!
    const node = byId.get(id)
    if (!node || seen.has(id)) return 0
    seen.add(id)
    const level = node.dependsOn.length ? Math.max(...node.dependsOn.map((dep) => visit(dep, seen) + 1)) : 0
    depth.set(id, level)
    return level
  }
  nodes.forEach((node) => visit(node.id, new Set()))
  const out: PlaybookNode[][] = []
  for (const node of nodes) (out[depth.get(node.id) ?? 0] ??= []).push(node)
  return out.filter(Boolean)
}
