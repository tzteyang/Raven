import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { nodeUrl } from './api'
import { answerLabel, firstLine, growing, ranFor, sources, tally, thoughtLabel, toolLine, toolState, wasCut, when } from './process'
import { dagRuns } from './trial'
import { Live } from './views/Live'
import { Graph } from './views/Trials'

import type { NodeProcess, ProcessStep } from './process'
import type { RecordRow } from './model'

const counts = { tools: 12, failed: 1, running: 1, messages: 3, thoughts: 4, thought_chars: 900, errors: 0 }

const reply = (over: Partial<NodeProcess> = {}): NodeProcess => ({
  dag: 'run-1',
  node: 'research',
  subagent: 'Raven-Research',
  summary: 'Research the destination',
  status: 'completed',
  started_at: 1_000_000,
  ended_at: 1_060_000,
  error: null,
  lane: 'acp',
  source: 'transcript',
  available: { transcript: true, journal: true, provider: false },
  attempt: null,
  attempts: [1],
  title: null,
  stop_reason: null,
  counts,
  last: 'web_search: trains to Xiamen',
  last_at: 1_011_000,
  omitted: 0,
  verdicts: [{ outcome: 'accomplished', reason: 'Every item carries a source.' }],
  prompt_source: 'prompt file',
  prompt_length: 22,
  output_length: 19,
  steps: [
    { kind: 'thought', time: 1_002_000, text: 'Look up the trains first.', length: 5000 },
    { kind: 'tool', time: 1_003_000, id: 'c1', name: 'web_search', title: 'web_search: trains to Xiamen', args: 'query=trains to Xiamen', input: '{"query": "trains to Xiamen"}', status: 'completed', result: 'G1 07:00 4h47m' },
    { kind: 'message', time: 1_010_000, text: 'Trains found; hotels next.', length: 26 },
    { kind: 'stderr', time: 1_000_500, text: '[run] llm: own key\nWARNING slow', length: 30, level: 'warning' },
    { kind: 'question', time: 1_011_000, text: 'Who reads the deck?', status: 'decline' },
  ],
  prompt: 'Research the trip now.',
  output: '# Report\n\nTrains: G1',
  ...over,
})

describe('node process helpers', () => {
  it('writes the running tally the node card shows', () => {
    expect(tally('running', { counts, last: 'web_search: trains to Xiamen' })).toBe('running · 12 tool calls · 1 failed · last: web_search: trains to Xiamen')
    expect(tally('completed', { counts: { ...counts, failed: 0, tools: 1 }, last: 'x' })).toBe('completed · 1 tool call')
    expect(tally('pending', null)).toBe('pending')
    expect(tally('running', { counts, last: 'a'.repeat(200) }, 20)).toMatch(/last: a{17}\.\.\.$/)
  })

  it('splits a tool title into its name and the rest, and maps statuses to states', () => {
    const step: ProcessStep = { kind: 'tool', time: null, name: 'web_search', title: 'web_search: trains', args: 'query=trains', status: 'running' }
    expect(toolLine(step)).toEqual({ name: 'web_search', detail: 'trains' })
    expect(toolLine({ ...step, title: 'Who reads it? | Real photos?', name: 'ask_user' })).toEqual({ name: 'ask_user', detail: 'Who reads it? | Real photos?' })
    expect(toolLine({ ...step, title: 'ppt_build', name: 'ppt_build', args: 'draft=True' })).toEqual({ name: 'ppt_build', detail: 'draft=True' })
    expect(['running', 'completed', 'failed', 'cancelled', 'pending', 'no result'].map((status) => toolState({ ...step, status }))).toEqual([
      'running', 'done', 'failed', 'failed', 'pending', 'unknown',
    ])
  })

  it('dates a step from the node start, else by the clock, else not at all', () => {
    expect(when(1_072_000, 1_000_000)).toBe('+1:12')
    expect(when(1_000_000 + 3_725_000, 1_000_000)).toBe('+1:02:05')
    expect(when(null, 1_000_000)).toBe('')
    expect(when(5_000, null)).toBe(new Date(5_000).toLocaleTimeString())
  })

  it('labels thoughts, answers and sources', () => {
    const thought: ProcessStep = { kind: 'thought', time: null, text: '\n\nFirst line\nsecond', length: 12345 }
    expect(thoughtLabel(thought)).toBe('Thought · 12,345 chars')
    expect(wasCut(thought)).toBe(true)
    expect(firstLine(thought.text)).toBe('First line')
    expect(answerLabel({ kind: 'permission', time: null, status: 'selected' })).toBe('approved')
    expect(answerLabel({ kind: 'question', time: null, status: 'decline' })).toBe('no one answered')
    expect(answerLabel({ kind: 'question', time: null, status: 'asked' })).toBe('waiting')
    expect(sources({ available: { transcript: true, journal: false, provider: true } })).toEqual(['transcript', 'provider'])
    expect(growing('running') && growing('pending') && !growing('completed')).toBe(true)
  })

  it('freezes an interrupted node at the later of the run\'s last event and its own last step', () => {
    expect(ranFor(1_000, 7_900, 65_000)).toBe(64_000)
    expect(ranFor(1_000, 7_900, null)).toBe(6_900)
    expect(ranFor(1_000, null, undefined)).toBeNull()
    expect(ranFor(null, 7_900, 65_000)).toBeNull()
    expect(toolState({ kind: 'tool', time: null, status: 'running' }, true)).toBe('interrupted')
    expect(toolState({ kind: 'tool', time: null, status: 'completed' }, true)).toBe('done')
  })

  it('asks the server for one node, a summary, a source or an attempt', () => {
    expect(nodeUrl('w/r', 'run-1', 'research')).toBe('/api/node?run=w%2Fr&dag=run-1&node=research')
    expect(nodeUrl('w/r', 'd', 'n', { summary: true, source: 'journal', attempt: 2 })).toBe('/api/node?run=w%2Fr&dag=d&node=n&summary=1&source=journal&attempt=2')
    expect(nodeUrl('w/r', 'd', 'n', { source: 'auto' })).toBe('/api/node?run=w%2Fr&dag=d&node=n')
  })
})

const rows = (status: string): RecordRow[] => [
  { kind: 'dag.progress', name: 'dag_run_started', payload: { run_id: 'run-1', task_summary: 'Make the deck', nodes: [{ id: 'research', subagent: 'Raven-Research', node_summary: 'Research the destination', depends_on: [] }, { id: 'build', subagent: 'Raven-PPT', depends_on: ['research'] }] } },
  { kind: 'dag.progress', name: 'dag_node_updated', payload: { run_id: 'run-1', node: 'research', status, started_at: 1_000_000 } },
]

describe('the node process panel', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('opens a node below its graph with prompt, steps, output and the verdict', async () => {
    const fetch = vi.fn(async (path: string) => ({ ok: true, status: 200, json: async () => (path.includes('summary=1') ? { ...reply(), steps: undefined } : reply()) }))
    vi.stubGlobal('fetch', fetch)
    const [graph] = dagRuns([...rows('completed')])
    render(<Graph graph={graph} drill="haggler" runId="w/r" />)
    expect(screen.getByText('Open a node to see what its sub-agent did.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /^research/ }))
    expect(await screen.findByText('trains to Xiamen')).toBeTruthy()
    expect(fetch.mock.calls[0][0]).toBe('/api/node?run=w%2Fr&dag=run-1&node=research')
    expect(screen.getByText('Thought · 5,000 chars')).toBeTruthy()
    expect(screen.queryByText('Look up the trains first.', { selector: '.txt' })).toBeNull()
    expect(screen.getByText('Trains found; hotels next.')).toBeTruthy()
    expect(screen.getByText('no one answered')).toBeTruthy()
    expect(screen.getByText('Output · 19 chars')).toBeTruthy()
    expect(screen.getByText('Report')).toBeTruthy()
    expect(screen.getByText('accomplished')).toBeTruthy()
    expect(screen.getByText('Prompt · 22 chars · from the prompt file')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'frame journal' })).toBeTruthy()
    fireEvent.click(screen.getByText('Thought · 5,000 chars'))
    expect(await screen.findByText('Look up the trains first.', { selector: '.txt' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'frame journal' }))
    await waitFor(() => expect(fetch.mock.calls.some((call) => String(call[0]).includes('source=journal'))).toBe(true))
    fireEvent.click(screen.getByRole('button', { name: 'Close the process' }))
    expect(screen.queryByText('trains to Xiamen')).toBeNull()
  })

  it('shows a running node its tally on the card and keeps re-reading while it runs', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const fetch = vi.fn(async (path: string) => ({
      ok: true,
      status: 200,
      json: async () => (path.includes('summary=1') ? { ...reply({ status: 'running', source: 'journal' }), steps: undefined, prompt: undefined, output: undefined } : reply({ status: 'running', source: 'journal', output: null })),
    }))
    vi.stubGlobal('fetch', fetch)
    const [graph] = dagRuns(rows('running'))
    render(<Graph graph={graph} drill="haggler" runId="w/r" now={1_030_000} />)
    expect(await screen.findByText('12 tool calls · 1 failed · last: web_search: trains to Xiamen')).toBeTruthy()
    const before = fetch.mock.calls.length
    await vi.advanceTimersByTimeAsync(3100)
    expect(fetch.mock.calls.length).toBeGreaterThan(before)
    vi.useRealTimers()
  })

  it('says a server without the endpoint needs a restart', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404, json: async () => ({}) })))
    const [graph] = dagRuns(rows('completed'))
    render(<Graph graph={graph} drill="haggler" runId="w/r" />)
    fireEvent.click(screen.getByRole('button', { name: /^research/ }))
    expect(await screen.findByText(/needs a restart of experimental.webui.serve/)).toBeTruthy()
  })

  it('says when the record kept nothing of the node', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404, json: async () => ({ error: 'no such node' }) })))
    const [graph] = dagRuns(rows('completed'))
    render(<Graph graph={graph} drill="haggler" runId="w/r" />)
    fireEvent.click(screen.getByRole('button', { name: /^research/ }))
    expect(await screen.findByText(/Nothing of this node was kept/)).toBeTruthy()
  })

  it('draws plain cards without a run id', () => {
    const [graph] = dagRuns(rows('completed'))
    render(<Graph graph={graph} drill="haggler" />)
    expect(screen.queryByRole('button', { name: /^research/ })).toBeNull()
    expect(screen.getByText('research')).toBeTruthy()
  })
})

describe('a stopped run in the views', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('draws a node still running when the run stopped as interrupted, its duration frozen and no timer', async () => {
    const fetch = vi.fn(async () => ({ ok: true, status: 200, json: async () => reply({ status: 'running', source: 'journal', output: null, verdicts: [], last_at: 1_125_000, steps: [{ kind: 'tool', time: 1_003_000, id: 'c1', name: 'web_search', title: 'web_search: hotels', status: 'running' }] }) }))
    vi.stubGlobal('fetch', fetch)
    const [graph] = dagRuns(rows('running'))
    render(<Graph graph={graph} drill="haggler" runId="w/r" now={9_000_000} over stoppedAt={1_072_000} />)
    expect(screen.getByText('interrupted', { selector: '.dag-hd .st' })).toBeTruthy()
    expect(screen.getByText('interrupted', { selector: '.nd-meta .st' })).toBeTruthy()
    expect(screen.getByText('1 m 12 s')).toBeTruthy()
    expect(await screen.findByText('2 m 5 s')).toBeTruthy()
    expect(screen.queryByText(/so far/)).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /^research/ }))
    expect(await screen.findByText('hotels')).toBeTruthy()
    expect(screen.getByText('interrupted', { selector: 'details.ltool .st' }).closest('details')?.className).toContain('interrupted')
    expect(screen.getByText(/The run stopped before this node finished/)).toBeTruthy()
    expect(screen.queryByText(/working · re-read/)).toBeNull()
    const calls = fetch.mock.calls.length
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(fetch.mock.calls.length).toBe(calls)
  })

  it('marks the live header stopped and freezes open turns and tool calls', async () => {
    const live = {
      logs: [{ file: 'w1', start: 0, offset: 10, size: 10, reset: true, last_event: 1072 }],
      last_event: 1072, now: 5000, status: 'error',
      phase: { name: 'error', round: 1, stage: null, basis: 'stopped by the operator at 07:20' },
      curator: null,
      labels: {},
      deliveries: [{ turn: 't1', name: 'plan.html', path: '/runs/w/deliverables/t1/plan.html', size: 2000, modified: 1000 }],
      rows: [
        { kind: 'provider.request', turn_id: 't1', text: 'Make the deck', drill: 'chen' },
        { kind: 'runner.event', turn_id: 't1', event_type: 'ToolEvent', event: { phase: 'start', tool_call_id: 'c1', name: 'load_playbook', arguments: { name: 'deck' } } },
        ...rows('running').map((row) => ({ ...row, turn_id: 't1' })),
      ].map((row) => ({ ...row, file: 'w1' })),
    }
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => live })))
    render(<Live runId="w/r" running={false} />)
    expect(await screen.findByText('Run stopped')).toBeTruthy()
    expect(screen.getByText('stopped by the operator at 07:20', { selector: '.why' })).toBeTruthy()
    expect(screen.getByText('interrupted', { selector: '.halted' })).toBeTruthy()
    expect(screen.queryByText('in progress')).toBeNull()
    expect(screen.getByText('interrupted', { selector: 'details.ltool .st' })).toBeTruthy()
    expect(screen.getByText('interrupted', { selector: '.nd-meta .st' })).toBeTruthy()
    expect(screen.queryByText(/so far/)).toBeNull()
    expect(screen.getByText('1 delivered')).toBeTruthy()
    expect(screen.getByText('plan.html', { selector: '.dfile-hd .nm' })).toBeTruthy()
  })
})
