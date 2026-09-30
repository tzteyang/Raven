import { describe, expect, it } from 'vitest'

import { controls, dagRuns, decks, duration, evidence, interceptions, interrupted, opened, replyText, scoredSignals, timedOut, trialSummary } from './trial'

import type { Exchange, RecordRow, Round, Run } from './model'

const start = (id: string, name: string, args: Record<string, unknown> = {}): RecordRow => ({
  kind: 'runner.event', event_type: 'ToolEvent', event: { phase: 'start', tool_call_id: id, name, arguments: args },
})
const complete = (id: string, text: string, ok = false): RecordRow => ({
  kind: 'runner.event', event_type: 'ToolEvent', event: { phase: 'complete', tool_call_id: id, name: '', result_preview: text, ok },
})

const call = (id: string, operation: string, event: Record<string, unknown>): RecordRow => ({ kind: 'action.call', operation, arguments: [{ [operation === 'handle_request' ? 'request_id' : 'event_id']: id, ...event }] })
const decided = (operation: string, result: Record<string, unknown>): RecordRow => ({ kind: 'action.result', operation, result })
const receipt = (control_id: string, source_id: string, control: string, status: string, reason: string | null = null): RecordRow => ({
  kind: 'action.control', receipt: { control_id, source_id, control, status, reason },
})

/* An Action proposal rejected and applied (its refusal returned on the tool call it refused), a revise the host
   rejected because another control was queued, a continue with guidance, and an agent request finished with a
   reply. */
const acted: RecordRow[] = [
  call('e1', 'handle_event', { kind: 'proposal', stage: 'final', calls: [{ name: 'deliver_files' }] }),
  decided('handle_event', { control: 'reject', reason: 'price before confirmation', feedback: 'Confirm the dates first.' }),
  receipt('c1', 'e1', 'reject', 'requested', 'price before confirmation'),
  call('e2', 'handle_event', { kind: 'proposal', stage: 'final', text: 'Here is the plan' }),
  decided('handle_event', { control: 'revise', reason: 'no budget table', feedback: 'Add the budget table.' }),
  receipt('c2', 'e2', 'revise', 'rejected', 'another control is queued for this boundary'),
  receipt('c1', 'e1', 'reject', 'applied', 'price before confirmation'),
  start('t1', 'deliver_files'),
  complete('t1', 'Action refused this call [c1]: Confirm the dates first.'),
  call('e3', 'handle_event', { kind: 'progress' }),
  decided('handle_event', { control: 'continue', guidance: 'Check the drive times.' }),
  call('q1', 'handle_request', { command: 'handover' }),
  decided('handle_request', { reply: 'noted', decision: { control: 'finish', reason: 'needs a colleague', reply: 'A colleague will call you.' } }),
  receipt('c3', 'q1', 'finish', 'requested'),
  receipt('c3', 'q1', 'finish', 'applied'),
]

describe('action controls', () => {
  it('pair each control with the decision that requested it and keep its latest receipt', () => {
    expect(controls(acted).map((control) => [control.id, control.control, control.status, control.on, control.tool])).toEqual([
      ['c1', 'reject', 'applied', 'proposal · final · deliver_files', 'deliver_files'],
      ['c2', 'revise', 'rejected', 'proposal · final · Here is the plan', null],
      ['c3', 'finish', 'applied', 'request handover', null],
    ])
    expect(controls(acted).map((control) => control.detail)).toEqual(['Confirm the dates first.', 'Add the budget table.', 'A colleague will call you.'])
    expect(controls(acted)[1].reason).toBe('another control is queued for this boundary')
  })
})

describe('interceptions', () => {
  it('reads a raising gate, a permission refusal and a spent rollback budget', () => {
    const rows = interceptions([
      start('c1', 'load_playbook'),
      complete('c1', "Error: tool call 'load_playbook' was refused by gate handover-gate: no handover ticket with a phone number"),
      start('c2', 'edit_file'),
      complete('c2', 'Error: This call requires user approval (it rewrites a guest record), but this turn is not interactive This command will not run here.'),
      { kind: 'loop.control', rollbacks: 2, rollbacks_refused: 1 },
    ])
    expect(rows.map((row) => [row.kind, row.mechanism, row.tool])).toEqual([
      ['gate', 'handover-gate', 'load_playbook'],
      ['permission', 'raven', 'edit_file'],
      ['budget', 'raven', null],
    ])
    expect(rows[0].reason).toBe('no handover ticket with a phone number')
    expect(rows[1].reason).toBe('it rewrites a guest record')
  })

  it('count only the controls the host applied, each where it was settled', () => {
    const rows = interceptions(acted)
    expect(rows.map((row) => [row.kind, row.mechanism, row.tool, row.call])).toEqual([
      ['reject', 'action.strategy', 'deliver_files', 't1'],
      ['finish', 'action.strategy', null, null],
    ])
    expect(rows[0]).toMatchObject({ reason: 'price before confirmation', detail: 'Confirm the dates first.', phase: 'proposal · final · deliver_files' })
    expect(rows[1].detail).toBe('A colleague will call you.')
  })
})

const progress = (name: string, payload: Record<string, unknown>): RecordRow => ({ kind: 'dag.progress', conversation: 'c', name, payload })

describe('playbook runs', () => {
  it('rebuild each node with its sub-harness, status, timing and depth', () => {
    const [run] = dagRuns([
      progress('dag_run_started', {
        run_id: 'r1',
        task_summary: 'Trip plan deck',
        nodes: [
          { id: 'research', subagent: 'Raven-Research', depends_on: [] },
          { id: 'brief', subagent: 'raven', depends_on: ['research'] },
          { id: 'deck', subagent: 'Raven-PPT', depends_on: ['brief'] },
        ],
      }),
      progress('dag_node_updated', { run_id: 'r1', node: 'research', status: 'running', started_at: 1000 }),
      progress('dag_node_updated', { run_id: 'r1', node: 'research', status: 'completed', started_at: 1000, ended_at: 61000 }),
      progress('dag_run_completed', {
        run_id: 'r1',
        manifest: {
          files: [
            { node: 'research', subagent: 'Raven-Research', status: 'completed', started_at: 1000, ended_at: 61000, output_file: '/x/research.md' },
            { node: 'brief', subagent: 'raven', status: 'completed', started_at: 61000, ended_at: 70000 },
            { node: 'deck', subagent: 'Raven-PPT', status: 'failed', error: 'template missing' },
          ],
        },
      }),
    ])
    expect(run.state).toBe('completed')
    expect(run.summary).toBe('Trip plan deck')
    expect(run.nodes.map((node) => [node.id, node.subagent, node.status, node.level])).toEqual([
      ['research', 'Raven-Research', 'completed', 0],
      ['brief', 'raven', 'completed', 1],
      ['deck', 'Raven-PPT', 'failed', 2],
    ])
    expect(duration(run.nodes[0])).toBe(60000)
    expect(duration(run.nodes[2])).toBeNull()
    expect(run.nodes[0].output).toBe('/x/research.md')
    expect(run.nodes[2].error).toBe('template missing')
  })

  it('keep a run that has not finished and one known only from its manifest', () => {
    const runs = dagRuns([
      progress('dag_run_started', { run_id: 'live', nodes: [{ id: 'a', subagent: 'Raven-Research' }] }),
      progress('dag_run_completed', { run_id: 'late', manifest: { files: [{ node: 'z', subagent: 'Raven-PPT', status: 'completed' }] } }),
      progress('dag_run_completed', { run_id: 'stopped', manifest: { stopped: true } }),
    ])
    expect(runs.map((run) => [run.id, run.state, run.nodes.length])).toEqual([['live', 'running', 1], ['late', 'completed', 1], ['stopped', 'stopped', 0]])
  })
})

const exchange = (records: RecordRow[], deliverables: string[] = []): Exchange => ({
  user: 'u', execution: { turn_id: 't', artifact_id: 'a', records, deliverables },
})
const roundOf = (sessions: Round['sessions']): Round => ({ sessions, signals: [], feedback: null, curated: false, analysis: [], curation: [] })

describe('decks and materials', () => {
  it('pair each drill deck with the same drill deck of the latest earlier round', () => {
    const run: Run = {
      task_id: 't', task: 'T', initial_curation: [],
      rounds: [
        roundOf({ haggler: [exchange([], ['/r/deliverables/1/plan.pptx'])], student: [exchange([])] }),
        roundOf({ haggler: [exchange([])], student: [exchange([], ['/r/deliverables/2/notes.md'])] }),
        roundOf({ haggler: [exchange([], ['/r/deliverables/3/a.pptx']), exchange([], ['/r/deliverables/4/b.pptx'])], student: [exchange([])] }),
      ],
    }
    expect(decks(run, 2)).toEqual([{ session: 'haggler', current: '/r/deliverables/4/b.pptx', previous: { path: '/r/deliverables/1/plan.pptx', round: 1 } }])
    expect(decks(run, 1)).toEqual([{ session: 'haggler', current: null, previous: { path: '/r/deliverables/1/plan.pptx', round: 1 } }])
    expect(decks(run, 0)[0].previous).toBeNull()
  })

  it('list the scenario materials the employee opened', () => {
    const round = roundOf({ a: [exchange([start('1', 'read_skill', { skill_id: 'local/price-list' }), start('2', 'read_skill', { skill_id: 'local/other' }), start('3', 'read_file', { path: 'price-list' })])] })
    expect(opened(round, ['service-sop', 'price-list'])).toEqual(['price-list'])
    expect(opened(round, [])).toEqual([])
  })

  it('read the reply text of a turn', () => {
    expect(replyText(exchange([{ kind: 'runner.event', event_type: 'Text', event: { content: 'Hi' } }, { kind: 'runner.event', event_type: 'Text', event: { content: 'there' } }]).execution)).toBe('Hi\nthere')
  })

  it('say when a turn ran past the worker timeout and was stopped', () => {
    const turn = exchange([]).execution
    expect(timedOut({ ...turn, outcome: { timed_out: true, timeout: 600, explicit_reply: false } })).toBe(600)
    expect(timedOut({ ...turn, outcome: { timed_out: true } })).toBe(true)
    expect(timedOut({ ...turn, outcome: { explicit_reply: true } })).toBeNull()
    expect(timedOut(turn)).toBeNull()
  })
})

describe('call evidence', () => {
  const records: RecordRow[] = [
    { kind: 'memory.call', operation: 'initialize' },
    { kind: 'memory.call', operation: 'compose' },
    { kind: 'memory.callback', operation: 'intake', phase: 'user_inbound' },
    { kind: 'memory.error', operation: 'compose', error: 'x' },
    { kind: 'action.call', operation: 'handle_event' },
    { kind: 'capability.effective', view: {} },
  ]

  it('count the call and host callback records of the strategy a target binds', () => {
    expect(evidence('memory.strategy', records)).toMatchObject({ calls: 3, errors: 1 })
    expect(evidence('action.strategy', records)).toMatchObject({ calls: 1, errors: 0 })
    expect(evidence('planning.strategy', records)).toMatchObject({ calls: 0, errors: 0 })
  })

  it('say when a target is not one of the four strategies', () => {
    expect(evidence('files', records).calls).toBeNull()
  })
})

describe('a graph whose run stopped', () => {
  const rows = [
    progress('dag_run_started', { run_id: 'r2', nodes: [{ id: 'research', subagent: 'Raven-Research' }, { id: 'deck', subagent: 'Raven-PPT', depends_on: ['research'] }] }),
    progress('dag_node_updated', { run_id: 'r2', node: 'research', status: 'running', started_at: 10_000 }),
  ]

  it('reads the open graph and its running node as interrupted, the duration frozen at the last event', () => {
    const [graph] = dagRuns(rows)
    const stopped = interrupted(graph, 70_000)
    expect(stopped.state).toBe('interrupted')
    expect(stopped.nodes.map((node) => [node.id, node.status])).toEqual([['research', 'interrupted'], ['deck', 'pending']])
    expect(duration(stopped.nodes[0])).toBe(60_000)
    expect(duration(interrupted(graph, null).nodes[0])).toBeNull()
    expect(graph.nodes[0].status).toBe('running')
  })

  it('leaves a graph that closed as it was', () => {
    const [graph] = dagRuns([...rows, progress('dag_run_completed', { run_id: 'r2', manifest: { files: [{ node: 'research', status: 'completed', started_at: 10_000, ended_at: 20_000 }] } })])
    expect(interrupted(graph, 70_000)).toBe(graph)
  })
})

describe('a trial at a glance', () => {
  it('counts drills, verdicts with red lines, Harness interceptions and delivered decks', () => {
    const exchange = (records: RecordRow[], deliverables: string[] = []): Exchange => ({ user: 'hi', execution: { turn_id: 't', artifact_id: 'a', records, deliverables } })
    const review = [
      call('e1', 'handle_event', { kind: 'proposal', stage: 'final' }),
      decided('handle_event', { control: 'revise', reason: 'no price', feedback: 'Quote first.' }),
      receipt('c1', 'e1', 'revise', 'applied'),
    ]
    const item = (id: string, result: 'pass' | 'fail' | 'unknown') => ({ id, result, session: null, expected: '', actual: '', note: '' })
    const run = {
      task_id: 't', task: 'T', initial_curation: [],
      rounds: [{
        sessions: { family: [exchange(review), exchange([], ['/d/deck.pptx'])], student: [exchange([])] },
        signals: [{ source: 'agency', text: '', metrics: {}, satisfied: null, items: [item('quote', 'fail'), item('intake', 'fail'), item('tone', 'pass'), item('deck', 'unknown')] }],
        feedback: null, curated: false, analysis: [], curation: [],
      }],
    } as unknown as Run
    const summary = trialSummary(run, 0, 'v1', new Set(['quote']))!
    expect([summary.round, summary.version, summary.passed, summary.failed, summary.redFailed, summary.unknown]).toEqual([1, 'v1', 1, 2, 1, 1])
    expect(summary.drills).toEqual([
      { name: 'family', turns: 2, interceptions: 1, graphs: 0, deck: '/d/deck.pptx' },
      { name: 'student', turns: 1, interceptions: 0, graphs: 0, deck: null },
    ])
    expect(summary.interceptions).toBe(1)
    expect(trialSummary(run, 1, 'v1', new Set())).toBeNull()
  })

  it('counts the verdicts the server joined into the round, and else the ones its signals carry', () => {
    const item = (id: string, result: 'pass' | 'fail') => ({ id, result, session: 'family', expected: '', actual: '', note: '', basis: 'check' })
    const scorecard = { source: 'agency', text: 'Three things to change.', metrics: {}, satisfied: false, items: [item('wbt-daily', 'fail'), item('wbt-intake', 'pass')] }
    const standard = { source: 'standard', text: '', metrics: {}, satisfied: false, items: [item('S1', 'fail')] }
    const round = {
      sessions: { family: [] },
      signals: [{ ...scorecard, items: [] }, standard],
      verdicts: [standard, scorecard],
      feedback: null, curated: true, curation: [], analysis: [],
    } as unknown as Round
    expect(scoredSignals(round).map((signal) => [signal.source, signal.items.map((row) => row.id)])).toEqual([['standard', ['S1']], ['agency', ['wbt-daily', 'wbt-intake']]])
    const summary = trialSummary({ task_id: 't', task: 'T', initial_curation: [], rounds: [round] } as unknown as Run, 0, 'v1', new Set(['wbt-daily']))!
    expect([summary.passed, summary.failed, summary.redFailed]).toEqual([1, 2, 1])
    const unjoined = { ...round, verdicts: undefined } as unknown as Round
    expect(scoredSignals(unjoined).map((signal) => signal.source)).toEqual(['standard'])
  })
})
