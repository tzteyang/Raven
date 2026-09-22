// @vitest-environment happy-dom
/* The persona wall: what it lists, and what starting one does.
 *
 * The filter is the test that matters. The wall reads the same listing the
 * playbook page does, so a Workflow or a workers-only Harness reaching it would
 * put something on the wall that cannot be talked to.
 */

import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { PersonaApp } from './PersonaPage'
import * as store from './store'

import type { PersonaRow } from './types'

function row(name: string, over: Partial<PersonaRow> = {}): PersonaRow {
  return {
    name,
    description: `${name} description`,
    artifact_kind: 'harness',
    coordinator: true,
    workers: [{ label: 'planner', agent: 'Raven-Research' }],
    origin: 'user',
    disabled: false,
    error: '',
    ...over,
  }
}

const shell = { T: (k: string) => k, showPage: vi.fn(), startPersona: vi.fn(() => true) }

function install(rows: PersonaRow[]): void {
  window.RavenShell = shell as never
  window.DS = { persona: { list: async () => rows } } as never
}

beforeEach(() => {
  store._resetForTests()
  shell.showPage.mockClear()
  shell.startPersona.mockClear()
})

afterEach(() => {
  cleanup()
  delete window.RavenShell
  delete window.DS
})

describe('the persona wall', () => {
  it('lists only artifacts that carry a coordinator seat', async () => {
    install([
      row('travel-concierge'),
      row('nightly-report', { artifact_kind: 'workflow', coordinator: false }),
      row('worker-table', { coordinator: false }),
      row('composite-persona', { artifact_kind: 'composite' }),
    ])
    render(<PersonaApp />)
    await act(async () => { await store.load() })

    expect(await screen.findByText('travel-concierge')).toBeTruthy()
    expect(screen.getByText('composite-persona')).toBeTruthy()
    expect(screen.queryByText('nightly-report')).toBeNull()
    expect(screen.queryByText('worker-table')).toBeNull()
  })

  it('starts a conversation on the persona and leaves the wall', async () => {
    install([row('travel-concierge')])
    render(<PersonaApp />)
    await act(async () => { await store.load() })

    fireEvent.click(await screen.findByText('gui.persona.start'))

    expect(shell.startPersona).toHaveBeenCalledWith('travel-concierge')
    expect(shell.showPage).toHaveBeenCalledWith(null)
  })

  it('stays on the wall when this build cannot start one', async () => {
    install([row('travel-concierge')])
    shell.startPersona.mockReturnValueOnce(false)
    render(<PersonaApp />)
    await act(async () => { await store.load() })

    fireEvent.click(await screen.findByText('gui.persona.start'))

    expect(shell.showPage).not.toHaveBeenCalled()
  })

  it('tells an unread wall apart from an empty one', async () => {
    install([])
    render(<PersonaApp />)
    expect(screen.getByText('gui.persona.loading')).toBeTruthy()
    await act(async () => { await store.load() })
    expect(await screen.findByText('gui.persona.empty')).toBeTruthy()
  })
})
