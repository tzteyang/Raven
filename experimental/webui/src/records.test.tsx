/* A turn's records: the kinds row, and the work of a sub-harness the turn handed a task to. */
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Records } from './views/Records'

import type { Execution } from './model'

afterEach(cleanup)

/* jsdom does not open a <details> on a click; open it and fire the toggle the Fold listens to. */
const unfold = (text: string): void => {
  const details = screen.getByText(text).closest('details') as HTMLDetailsElement
  details.open = true
  fireEvent(details, new Event('toggle'))
}

const execution = (child: Record<string, unknown>): Execution => ({
  turn_id: 'turn-0001',
  artifact_id: 'a',
  records: [{ kind: 'memory.call' }, { kind: 'child.execution', harness: 'Raven-Oncall', records: [], ...child }],
})

describe('Records', () => {
  it("lists a sub-harness's tool calls with their results and its replies", () => {
    const steps = [
      { tool: 'ops_declare', arguments: '{"name": "watch"}', result: 'campaign declared', ok: true },
      { tool: 'exec', arguments: '{"command": "python3 store_read.py read 1"}', result: 'permission denied', ok: false },
      { text: 'Report written.' },
    ]
    render(<Records execution={execution({ steps, steps_omitted: 3 })} />)
    expect(screen.getByText('Raven-Oncall')).toBeTruthy()
    unfold('worked through 2 tool calls, 3 later steps not shown')
    expect(screen.getByText('ops_declare')).toBeTruthy()
    expect(screen.getByText('failed')).toBeTruthy()
    expect(screen.getByText('Report written.')).toBeTruthy()
    unfold('exec')
    expect(screen.getByText('permission denied')).toBeTruthy()
  })

  it('adds nothing for a sub-harness execution without steps', () => {
    const { container } = render(<Records execution={execution({})} />)
    expect(container.querySelector('.child-work')).toBeNull()
  })

  it("opens a cut turn's whole records from the server, and falls back to the page's copy when refused", async () => {
    const whole = [{ kind: 'memory.call', arguments: ['the whole model input'] }]
    const fetched: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      fetched.push(url)
      return url.includes('turn-0001') ? new Response(JSON.stringify({ records: whole })) : new Response(JSON.stringify({ error: 'no such turn' }), { status: 404 })
    }))
    const cut: Execution = { turn_id: 'turn-0001', artifact_id: 'a', records: [{ kind: 'memory.call' }], records_cut: true }
    render(<Records execution={cut} runId="w/r" />)
    unfold('turn-000')
    expect(await screen.findByText('1 record of turn')).toBeTruthy()
    expect(fetched).toEqual(['/api/turn?run=w%2Fr&turn=turn-0001'])
    expect(screen.queryByText(/the whole model input/)).toBeNull()
    const line = document.querySelector<HTMLDetailsElement>('details.rec')!
    line.open = true
    fireEvent(line, new Event('toggle'))
    expect(screen.getByText(/the whole model input/)).toBeTruthy()
    cleanup()
    render(<Records execution={{ ...cut, turn_id: 'turn-0002' }} runId="w/r" />)
    unfold('turn-000')
    expect(await screen.findByText("Showing the page's cut copy: no such turn.")).toBeTruthy()
    vi.unstubAllGlobals()
  })
})
