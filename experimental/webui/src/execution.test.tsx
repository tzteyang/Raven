/** The Execution view keeps unknown amounts visible, opens a stage to its own requests, and never shows a stale run. */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { byModel, byPart, known, lanes, matrix, money, under, waterfall, windowOf } from './execution'
import { Execution } from './views/Execution'

import type { Operation, Report, Totals } from './execution'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

const totalsOf = (over: Partial<Totals> = {}): Totals => ({
  attempts: 2, failed: 0, unfinished: 1, partial_usage: 1, cost_usd: 0, input_total_tokens: 20, output_tokens: 5,
  cache_read_tokens: null, cache_write_tokens: null, missing: { cost_usd: 1 }, ...over,
})

const operation = { started_at: '2026-10-10T00:00:00Z', ended_at: '2026-10-10T00:00:02Z', duration_ms: 2000, status: 'ok' }

function report(): Report {
  return { available: true, run_ids: ['run-1'], totals: totalsOf(), missing_parents: [], spans: [
    { ...operation, id: 'root', parent_id: null, kind: 'span', name: 'experiment', attributes: {}, totals: totalsOf() },
    { ...operation, id: 'trial', parent_id: 'root', kind: 'span', name: 'trial', attributes: { round_index: 1, stage: 'trial' }, totals: totalsOf({ attempts: 1, unfinished: 0, partial_usage: 0, missing: { cost_usd: 0 } }) },
    { ...operation, id: 'assess', parent_id: 'root', kind: 'span', name: 'assess', attributes: { round_index: 1, stage: 'assess' }, totals: totalsOf({ attempts: 1, cost_usd: null, missing: { cost_usd: 1 } }) },
  ], attempts: [
    { ...operation, id: 'a1', parent_id: 'trial', kind: 'attempt', name: 'llm.attempt', attributes: { model: 'trial-model', stage: 'trial', round_index: 1, session_key: 'webchat:1' },
      usage: { cost_usd: 0, output_tokens: 5, input_total_tokens: 20 }, usage_complete: true, part: 'employee' },
    { ...operation, id: 'a2', parent_id: 'assess', kind: 'attempt', name: 'llm.attempt', attributes: { model: 'assess-model', stage: 'assess', round_index: 1 },
      status: 'running', duration_ms: null, ended_at: null, usage: {}, usage_complete: false, part: 'simulation' },
  ] }
}

test('a sum of nothing known is unknown, and an unknown term is counted beside a known sum', () => {
  expect(known([null, undefined])).toEqual({ value: null, unknown: 2 })
  expect(known([1.5, null, 2])).toEqual({ value: 3.5, unknown: 1 })
  expect(money(null)).toBe('unknown')
  expect(money(0)).toBe('$0')
  expect(money(0.0042)).toBe('$0.0042')
})

test('the grid joins each round and stage, keeping the loop order and the unpriced count', () => {
  const grid = matrix(report().spans)
  expect(grid.rounds).toEqual([1])
  expect(grid.stages).toEqual(['trial', 'assess'])
  expect(grid.cells.map((cell) => [cell.stage, cell.cost.value, cell.cost.unknown, cell.status])).toEqual([
    ['trial', 0, 0, 'ok'],
    ['assess', null, 1, 'ok'],
  ])
  expect(lanes(report().spans).map((lane) => [lane.round, lane.spans.map((span) => span.name)])).toEqual([[1, ['trial', 'assess']]])
})

test('parts and models group the requests without adding unknown amounts', () => {
  const body = report()
  expect(byPart(body.attempts).map((row) => [row.key, row.attempts, row.cost.value, row.cost.unknown])).toEqual([
    ['employee', 1, 0, 0],
    ['simulation', 1, null, 1],
  ])
  expect(byModel(body.attempts).map((row) => row.key)).toEqual(['trial-model', 'assess-model'])
})

test('a selected stage covers its descendants, and the waterfall walks them with their own requests as ticks', () => {
  const body = report()
  const parents = new Map<string, string | null>([...body.spans, ...body.attempts].map((row) => [row.id, row.parent_id]))
  expect(under(body.attempts[0], new Set(['trial']), parents)).toBe(true)
  expect(under(body.attempts[1], new Set(['trial']), parents)).toBe(false)
  expect(under(body.attempts[1], new Set(), parents)).toBe(true)
  const { rows, more } = waterfall(body, new Set(['root']), 2)
  expect(rows.map((row) => [row.op.name, row.depth, row.ticks.length])).toEqual([['experiment', 0, 0], ['trial', 1, 1]])
  expect(more).toBe(1)
})

test('the time window ends at the last known end for a recorded run and at now while live', () => {
  const rows: Operation[] = report().attempts
  const recorded = windowOf(rows, false, Date.parse('2026-10-10T01:00:00Z'))
  expect(recorded).toEqual({ start: Date.parse('2026-10-10T00:00:00Z'), end: Date.parse('2026-10-10T00:00:02Z') })
  expect(windowOf(rows, true, Date.parse('2026-10-10T01:00:00Z'))?.end).toBe(Date.parse('2026-10-10T01:00:00Z'))
})

test('unknown amounts stay visible and opening a stage filters by ancestry', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => report() }))
  render(<Execution runId="one/run" running={false} />)
  expect((await screen.findAllByText('trial-model')).length).toBe(2)
  expect(screen.getAllByText('unknown').length).toBeGreaterThan(0)
  expect(screen.getByText('1 without a reported price')).toBeTruthy()
  expect(screen.getByText('1 unfinished, outcome unknown')).toBeTruthy()
  expect(screen.getByText('unfinished', { selector: '.ex-status' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'trial' }))
  expect(screen.queryAllByText('assess-model')).toEqual([])
  expect(screen.getByText('under trial')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Show the whole run' }))
  expect(screen.getAllByText('assess-model').length).toBe(2)
})

test('a grid cell opens its stage too, and the request filters narrow by part', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => report() }))
  render(<Execution runId="one/run" running={false} />)
  await screen.findAllByText('trial-model')
  const grid = screen.getByText('Rounds and stages').closest('section') as HTMLElement
  fireEvent.click(within(grid).getByRole('button', { name: /^assess, round 1/ }))
  expect(screen.queryAllByText('trial-model')).toEqual([])
  expect(screen.getAllByText('assess-model').length).toBe(2)
  fireEvent.click(within(grid).getByRole('button', { name: /^assess, round 1/ }))
  expect(screen.getAllByText('trial-model').length).toBe(2)
  fireEvent.change(screen.getByLabelText('Part'), { target: { value: 'employee' } })
  expect(screen.getAllByText('assess-model').length).toBe(1)
  expect(screen.getByText('1 of 2 requests')).toBeTruthy()
})

test('older runs report absent accounting instead of zero consumption', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ...report(), available: false }) }))
  render(<Execution runId="old/run" running={false} />)
  expect(await screen.findByText('No execution accounting was recorded for this run.')).toBeTruthy()
  expect(screen.queryByText('$0')).toBeNull()
})

test('a failed accounting read is visible', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: async () => ({ error: 'Ledger unavailable' }) }))
  render(<Execution runId="one/run" running={false} />)
  expect((await screen.findByRole('alert')).textContent).toBe('Ledger unavailable')
})

test('external invocations and quota equivalents stay separate from native requests and cash', async () => {
  const body = report()
  const totals = totalsOf({ attempts: 0, external_calls: 2, cost_usd: null, quota_usd: 0.5, missing: { cost_usd: 2 } })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ...body, totals }) }))
  render(<Execution runId="one/run" running={false} />)
  const requests = (await screen.findByText('Requests', { selector: '.ex-kpi-l' })).parentElement as HTMLElement
  expect(requests.textContent).toContain('0 + 2 external')
  const cost = screen.getByText('Reported cost').parentElement as HTMLElement
  expect(cost.textContent).toContain('unknown')
  expect(cost.textContent).toContain('quota equivalent $0.50, not counted')
})

test('a response from the previous run cannot replace the selected run', async () => {
  let finish: (value: unknown) => void = () => {}
  const pending = new Promise((resolve) => { finish = resolve })
  const fetch = vi.fn().mockReturnValueOnce(pending).mockResolvedValue({ ok: true, json: async () => ({ ...report(), available: false }) })
  vi.stubGlobal('fetch', fetch)
  const view = render(<Execution runId="first/run" running={false} />)
  view.rerender(<Execution runId="second/run" running={false} />)
  await screen.findByText('No execution accounting was recorded for this run.')
  finish({ ok: true, json: async () => report() })
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
  expect(screen.queryAllByText('trial-model')).toEqual([])
})
