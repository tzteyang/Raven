import { describe, expect, it } from 'vitest'

import { GAP, cursorOf, delivered, errorList, groupTurns, merge, mergeEvents, namesOf, panelItems, shortArguments, steps, stopped, toolItemState } from './live'

import type { CuratorEvent, CuratorProgress, KeptFile, LiveLog, LiveReply, Phase } from './live'
import type { RecordRow } from './model'

const said = (turn: string, text: string, drill = 'haggler'): RecordRow => ({ kind: 'provider.request', turn_id: turn, text, drill })
const reply = (turn: string, content: string): RecordRow => ({ kind: 'runner.event', turn_id: turn, event_type: 'Text', event: { content } })
const start = (turn: string, id: string, name: string, args: unknown = {}): RecordRow => ({ kind: 'runner.event', turn_id: turn, event_type: 'ToolEvent', event: { phase: 'start', tool_call_id: id, name, arguments: args } })
const complete = (turn: string, id: string, ok: boolean, text: string): RecordRow => ({ kind: 'runner.event', turn_id: turn, event_type: 'ToolEvent', event: { phase: 'complete', tool_call_id: id, ok, result_preview: text } })
const closed = (turn: string): RecordRow => ({ kind: 'loop.control', turn_id: turn, rollbacks: 0, rollbacks_refused: 0 })

describe('turn grouping', () => {
  it('groups rows by turn with the customer message, replies and tool calls in order', () => {
    const turns = groupTurns([
      { kind: 'runtime.bound', turn_id: null, targets: [] },
      said('t1', 'Can I get Sanya cheaper?'),
      start('t1', 'c1', 'read_skill', { skill_id: 'local/price-list' }),
      complete('t1', 'c1', true, 'price list'),
      said('t1', 'Can I get Sanya cheaper?'),
      reply('t1', 'Our prices follow the list.'),
      closed('t1'),
      said('t2', 'Then book it.'),
      start('t2', 'c2', 'write_file', { path: 'ticket.md' }),
    ])
    expect(turns.map((turn) => [turn.id, turn.drill, turn.customer, turn.open])).toEqual([
      ['t1', 'haggler', 'Can I get Sanya cheaper?', false],
      ['t2', 'haggler', 'Then book it.', true],
    ])
    expect(turns[0].items.map((item) => item.kind)).toEqual(['tool', 'reply'])
    expect(turns[0].items[0]).toMatchObject({ name: 'read_skill', ok: true, result: 'price list', args: '{"skill_id":"local/price-list"}' })
    expect(turns[1].items[0]).toMatchObject({ name: 'write_file', ok: null })
  })

  it('shows playbook progress once per graph, updated to its latest state', () => {
    const [turn] = groupTurns([
      said('t1', 'Please make the deck'),
      start('t1', 'c1', 'load_playbook'),
      { kind: 'dag.progress', turn_id: 't1', name: 'dag_run_started', payload: { run_id: 'r', nodes: [{ id: 'research', subagent: 'Raven-Research' }, { id: 'deck', subagent: 'Raven-PPT', depends_on: ['research'] }] } },
      { kind: 'dag.progress', turn_id: 't1', name: 'dag_node_updated', payload: { run_id: 'r', node: 'research', status: 'running', started_at: 10 } },
      reply('t1', 'Working on it.'),
      { kind: 'dag.progress', turn_id: 't1', name: 'dag_node_updated', payload: { run_id: 'r', node: 'research', status: 'completed', started_at: 10, ended_at: 70 } },
      said('t1', 'Background result: the deck is ready'),
      reply('t1', 'Here is your deck.'),
    ])
    expect(turn.items.map((item) => item.kind)).toEqual(['tool', 'dag', 'reply', 'message', 'reply'])
    const dag = turn.items[1]
    expect(dag.kind === 'dag' && dag.run.nodes.map((node) => [node.id, node.status, node.level])).toEqual([['research', 'completed', 0], ['deck', 'pending', 1]])
    expect(turn.open).toBe(true)
  })

  it('highlights the controls the host applied and the gates that refused, and marks the refused tool calls', () => {
    const [turn] = groupTurns([
      said('t1', 'Send me the deck'),
      { kind: 'action.call', turn_id: 't1', operation: 'handle_event', arguments: [{ event_id: 'e1', kind: 'proposal', stage: 'tools', calls: [{ name: 'deliver_files' }] }] },
      { kind: 'action.result', turn_id: 't1', operation: 'handle_event', result: { control: 'reject', reason: 'quote number missing', feedback: 'Add the quote number.' } },
      { kind: 'action.control', turn_id: 't1', receipt: { control_id: 'k1', source_id: 'e1', control: 'reject', status: 'applied', reason: 'quote number missing' } },
      start('t1', 'c1', 'deliver_files', { paths: ['plan.pptx'] }),
      complete('t1', 'c1', false, 'Action refused this call [k1]: Add the quote number.'),
      start('t1', 'c2', 'load_playbook'),
      complete('t1', 'c2', false, "Error: tool call 'load_playbook' was refused by gate handover-gate: no ticket"),
      { kind: 'action.control', turn_id: 't1', receipt: { control_id: 'k2', source_id: 'e9', control: 'revise', status: 'rejected' } },
      { kind: 'planning.error', turn_id: 't1', error: 'ValueError: view disagrees' },
      closed('t1'),
    ])
    expect(turn.items.map((item) => item.kind)).toEqual(['interception', 'tool', 'tool', 'interception', 'error'])
    expect(turn.items[0]).toMatchObject({ row: { kind: 'reject', mechanism: 'action.strategy', tool: 'deliver_files', detail: 'Add the quote number.' } })
    expect([turn.items[1], turn.items[2]]).toMatchObject([{ name: 'deliver_files', refused: true }, { name: 'load_playbook', refused: true }])
    expect(turn.items[3]).toMatchObject({ row: { kind: 'gate', mechanism: 'handover-gate', tool: 'load_playbook', reason: 'no ticket' } })
  })

  it('keeps the worker log each turn came from', () => {
    const turns = groupTurns([{ ...said('t1', 'a'), file: 'w1' }, closed('t1'), { ...said('t2', 'b'), file: 'replicas/1-session-7ae78d/w2' }])
    expect(turns.map((turn) => turn.file)).toEqual(['w1', 'replicas/1-session-7ae78d/w2'])
  })

  it('names a drill by its session once the record holds the label, and keeps an unknown label as it is', () => {
    const names = namesOf({ family: 'session-7ae78d' })
    expect(names).toEqual({ 'session-7ae78d': 'family' })
    const rows = [{ ...said('t1', 'a'), drill: 'session-7ae78d' }, { ...said('t2', 'b'), drill: 'session-324d9f' }]
    expect(groupTurns(rows, names).map((turn) => turn.drill)).toEqual(['family', 'session-324d9f'])
    expect(groupTurns(rows).map((turn) => turn.drill)).toEqual(['session-7ae78d', 'session-324d9f'])
  })
})

const log = (file: string, over: Partial<LiveLog> = {}): LiveLog => ({ file, start: 0, offset: 10, size: 10, reset: false, last_event: 1, ...over })
const from = (file: string, row: RecordRow): RecordRow => ({ ...row, file })

const answer = (over: Partial<LiveReply>): LiveReply => ({
  logs: [log('w1')], rows: [], last_event: 1,
  phase: { name: 'trial', round: 1, stage: null, basis: '' }, status: 'running', curator: null, labels: {}, now: 2, ...over,
})

describe('merging polls', () => {
  it('appends new rows and keeps the same rows when nothing arrived', () => {
    const rows = [from('w1', said('t1', 'a'))]
    expect(merge(rows, answer({ rows: [from('w1', reply('t1', 'b'))] }))).toHaveLength(2)
    expect(merge(rows, answer({}))).toBe(rows)
  })

  it('replaces the rows of a log read from a fresh tail and keeps every other log', () => {
    const rows = [from('w1', said('t1', 'a')), from('replicas/1-family/w2', said('t2', 'b'))]
    const next = merge(rows, answer({ logs: [log('w1', { reset: true }), log('replicas/1-family/w2')], rows: [from('w1', reply('t9', 'z'))] }))
    expect(next.map((row) => [row['file'], row.turn_id])).toEqual([['replicas/1-family/w2', 't2'], ['w1', 't9']])
    expect(merge([], answer({ logs: [log('w1', { reset: true })], rows }))).toEqual(rows)
  })

  it('caps how many rows it keeps and names where to read each log from next', () => {
    const many = Array.from({ length: 10 }, (_, i) => from('w1', reply(`t${i}`, 'x')))
    expect(merge(many, answer({ rows: [from('w1', reply('t10', 'y'))] }), 5).map((row) => row.turn_id)).toEqual(['t6', 't7', 't8', 't9', 't10'])
    expect(cursorOf([log('w1'), log('replicas/1-family/w2', { offset: 20 })])).toBe('w1:10,replicas/1-family/w2:20')
  })
})

const progress = (over: Partial<CuratorProgress>): CuratorProgress => ({
  started: 1, updated: 2, stage: 'select', calls: 1, queries: 0, checks: 0, repairs: 0, staged: [], events: [], ...over,
})
const ev = (event: string, over: Partial<CuratorEvent> = {}): CuratorEvent => ({ stage: 'implement', event, ...over })

describe('curator panel', () => {
  it('keeps events across polls of a sliding window', () => {
    const a = ev('query', { tool: 'read_fact', arguments: '{"name": "a"}' })
    const b = ev('query', { tool: 'read_fact', arguments: '{"name": "b"}' })
    const c = ev('model.call', { call: '3' })
    const d = ev('file.staged', { path: 'pkg/gate.py' })
    expect(mergeEvents([], [a, b])).toEqual([a, b])
    expect(mergeEvents([a, b], [b, c])).toEqual([a, b, c])
    const kept = [a, b, c]
    expect(mergeEvents(kept, [b, c])).toBe(kept)
    expect(mergeEvents([a, b], [c, d])).toEqual([a, b, GAP, c, d])
  })

  it('reads the stage as a step, diagnose while the attribution runs and validate while the last event is a validation', () => {
    const states = (value: CuratorProgress) => steps(value).map((step) => `${step.id}:${step.state}`)
    expect(states(progress({ stage: 'diagnose' }))).toEqual(['diagnose:current', 'select:todo', 'design:todo', 'implement:todo', 'validate:todo', 'repair:todo'])
    expect(states(progress({ stage: 'design' }))).toEqual(['diagnose:done', 'select:done', 'design:current', 'implement:todo', 'validate:todo', 'repair:todo'])
    expect(states(progress({ stage: 'implement', events: [ev('validation', { stage: 'validate', errors: '[]' })] }))).toEqual(['diagnose:done', 'select:done', 'design:done', 'implement:done', 'validate:current', 'repair:todo'])
    expect(states(progress({ stage: 'repair', repairs: 1 }))).toEqual(['diagnose:done', 'select:done', 'design:done', 'implement:done', 'validate:done', 'repair:current'])
    expect(states(progress({ stage: 'implement', finished: true, error: null }))).toEqual(['diagnose:done', 'select:done', 'design:done', 'implement:done', 'validate:done', 'repair:skipped'])
    expect(states(progress({ stage: 'implement', finished: true, error: 'boom' }))[3]).toBe('implement:failed')
    expect(steps(progress({ stage: null }))[0]).toMatchObject({ id: 'diagnose', label: 'diagnose', state: 'current' })
  })

  it('turns events into rows: notes, queries, staged files, submissions with strategies, checks and rejections', () => {
    const items = panelItems([
      ev('model.call', { stage: 'select', call: '1' }),
      ev('model.note', { content: 'I will gate delivery.' }),
      ev('query', { tool: 'read_source', arguments: '{"path": "raven/contracts/tool_gate.py", "start": 1}' }),
      ev('query.rejected', { tool: 'read_fact', arguments: '{"name": "x"}' }),
      ev('file.staged', { path: 'pkg/gate.py' }),
      ev('submit_plan', { targets: ['action.strategy', 'planning.strategy'], understanding: 'Quote only after confirming.' }),
      ev('preflight', { arguments: '{"targets": ["action.strategy"]}' }),
      ev('validation', { stage: 'validate', errors: "['gate lacks adjudicate']" }),
      ev('validation', { stage: 'validate', errors: '[]' }),
      ev('output.rejected', { tool: 'submit_artifact', error: 'files must be a mapping' }),
      ev('output.missing'),
      GAP,
      ev('tool.skipped', { tool: 'read_file' }),
    ])
    expect(items.map((item) => item.kind)).toEqual(['call', 'note', 'query', 'query', 'staged', 'submit', 'check', 'check', 'check', 'rejected', 'rejected', 'gap', 'other'])
    expect(items[2]).toEqual({ kind: 'query', tool: 'read_source', argument: 'path=raven/contracts/tool_gate.py, start=1', rejected: false })
    expect(items[3]).toMatchObject({ rejected: true })
    expect(items[5]).toEqual({ kind: 'submit', name: 'submit_plan', targets: [{ target: 'action.strategy', strategy: 'action' }, { target: 'planning.strategy', strategy: 'planning' }], understanding: 'Quote only after confirming.' })
    expect(items[7]).toMatchObject({ name: 'validation', errors: ["'gate lacks adjudicate'"] })
    expect(items[8]).toMatchObject({ name: 'validation', errors: [] })
    expect(items[9]).toMatchObject({ tool: 'submit_artifact', error: 'files must be a mapping' })
  })

  it('shortens arguments and reads error lists', () => {
    expect(shortArguments('{"name": "uploads"}')).toBe('name=uploads')
    expect(shortArguments('not json {')).toBe('not json {')
    expect(shortArguments(`{"text": "${'x'.repeat(200)}"}`, 20)).toBe('text=xxxxxxxxxxxxxxx...')
    expect(errorList('["a", "b"]')).toEqual(['a', 'b'])
    expect(errorList('[]')).toEqual([])
    expect(errorList(undefined)).toEqual([])
  })
})

describe('delivered files', () => {
  const handed = (turn: string, id: string, files: Record<string, unknown>[], message = 'Here is your deck.'): RecordRow => ({
    kind: 'runner.event', turn_id: turn, event_type: 'ToolEvent',
    event: { phase: 'complete', tool_call_id: id, ok: true, result_preview: 'Delivered', delivery: { message, files } },
  })
  const kept = (turn: string, name: string, modified: number): KeptFile => ({ turn, name, path: `/runs/w/deliverables/${turn}/${name}`, size: 10, modified })

  it('lists files still waiting for their kept copy first, then kept copies newest first, with what the turn said', () => {
    const rows = [
      handed('t1', 'a', [{ name: 'deck.pptx', title: 'Trip deck', description: 'Five nights', size: 885652 }]),
      handed('t2', 'b', [{ name: 'plan.html', title: 'Plan page' }]),
      handed('t3', 'c', [{ name: 'deck.pptx', title: 'Revised deck' }], 'Dates fixed.'),
    ]
    const files = delivered(rows, [kept('t1', 'deck.pptx', 100), kept('t2', 'plan.html', 200), kept('t0', 'old.pdf', 50)])
    expect(files.map((file) => [file.turn, file.name, file.path !== null])).toEqual([
      ['t3', 'deck.pptx', false],
      ['t2', 'plan.html', true],
      ['t1', 'deck.pptx', true],
      ['t0', 'old.pdf', true],
    ])
    expect(files[0]).toMatchObject({ title: 'Revised deck', message: 'Dates fixed.', modified: null })
    expect(files[2]).toMatchObject({ title: 'Trip deck', description: 'Five nights', size: 10, path: '/runs/w/deliverables/t1/deck.pptx' })
    expect(files[3]).toMatchObject({ title: null, message: null })
  })

  it('ignores tool results without a delivery and shows nothing before anything is handed over', () => {
    expect(delivered([complete('t1', 'x', true, 'ok'), reply('t1', 'hi')], [])).toEqual([])
  })
})

describe('a stopped run', () => {
  const phase = (name: string): Phase => ({ name, round: 1, stage: null, basis: '' })

  it('stops looking live when the record or the phase says so', () => {
    expect(stopped(true, phase('trial'))).toBe(false)
    expect(stopped(true, null)).toBe(false)
    expect(stopped(false, phase('trial'))).toBe(true)
    for (const name of ['error', 'finished', 'paused', 'stalled or stopped']) expect(stopped(true, phase(name))).toBe(true)
  })

  it('reads a tool call still open as interrupted once the run stopped', () => {
    const [turn] = groupTurns([said('t1', 'Deck?'), start('t1', 'c1', 'load_playbook'), start('t1', 'c2', 'web_search'), complete('t1', 'c2', true, 'ok')])
    const [open, done] = turn.items.filter((item) => item.kind === 'tool') as Extract<(typeof turn.items)[number], { kind: 'tool' }>[]
    expect([toolItemState(open, false), toolItemState(open, true)]).toEqual(['running', 'interrupted'])
    expect(toolItemState(done, true)).toBe('done')
    expect(toolItemState({ ...open, refused: true }, true)).toBe('refused')
  })
})
