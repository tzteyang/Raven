/* Page state for the persona wall, outside React for the reason the playbook
 * library's is: the legacy shell opens and closes this page imperatively -- the
 * rail button, Escape, a language flip.
 *
 * One read and one action. The read is the library, filtered to the artifacts
 * that carry a coordinator seat. The action starts a conversation on one: the
 * Harness is staged on the composer and the engine freezes it onto the session
 * when the first message promotes it, which is why nothing here creates a
 * session of its own -- a wall that minted one per click would leave an empty
 * conversation behind every time a reader changed their mind.
 */

import { ds, shell } from '../../shell/bridge'
import { show as toast } from '../../shell/toast'

import type { PersonaRow, PersonaSource } from './types'

export interface PersonaState {
  /* null = not read yet, which is not the same as "no personas": one draws a
     skeleton, the other says the wall is empty. */
  rows: PersonaRow[] | null
  err: string
  query: string
}

const EMPTY: PersonaState = { rows: null, err: '', query: '' }

let state = EMPTY
const listeners = new Set<() => void>()

export const getState = (): PersonaState => state

export function subscribe(l: () => void): () => void {
  listeners.add(l)
  return () => listeners.delete(l)
}

function set(patch: Partial<PersonaState>): void {
  state = { ...state, ...patch }
  for (const l of listeners) l()
}

const source = (): PersonaSource => ds<PersonaSource>('persona')

/* A Persona is the coordinator seat, not the worker table: a stored Harness
   without one configures workers for a turn and has no identity to run as, so
   it belongs on the playbook page and not here. */
export const isPersona = (r: PersonaRow): boolean =>
  r.coordinator && (r.artifact_kind === 'harness' || r.artifact_kind === 'composite')

export async function load(): Promise<void> {
  try {
    const rows = await source().list()
    set({ rows: rows.filter(isPersona), err: '' })
  } catch (e) {
    set({ rows: [], err: (e as Error)?.message || String(e) })
  }
}

export function visible(): PersonaRow[] {
  const q = state.query.trim().toLowerCase()
  const rows = state.rows || []
  if (!q) return rows
  return rows.filter(r => `${r.name} ${r.description}`.toLowerCase().includes(q))
}

export function search(query: string): void {
  set({ query })
}

/* Opens a conversation that will be created on this Persona. The page closes
   first so the reader lands in the conversation they just started rather than
   on the wall they started it from. */
export function start(name: string): void {
  const sh = shell()
  const staged = sh.startPersona?.(name)
  if (staged === false) {
    toast(sh.T('gui.persona.start_failed', { name }, `Cannot start ${name} here`))
    return
  }
  sh.showPage(null)
}

export function openPage(): void {
  shell().showPage('personaPage')
  void load()
}

export function closePage(): void {
  shell().showPage(null)
}

/* Every visible string comes from t(), so a re-render is the whole redraw. */
export function redraw(): void {
  set({})
}

export function _resetForTests(): void {
  state = EMPTY
  listeners.clear()
}
