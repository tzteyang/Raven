import { describe, expect, it } from 'vitest'

import { revisions } from './derive'
import { cellTone, harnessRows, readBySubharness, redLines } from './harness'

import type { Change, Criterion, Curation, Exchange, Generated, Item, RecordRow, Round, Run } from './model'

const generated = (changes: [string, Change['treatment']][], values: Record<string, unknown> = {}, files: Record<string, string> = {}): Generated => ({
  candidate: {
    plan: { understanding: '', changes: changes.map(([target, treatment]): Change => ({ target, treatment, reason: '', expected: `expect ${target}`, verification: '' })) },
    artifact: { values, files },
  },
  validation: { errors: [], observations: [] },
  trace: [],
})

const curation = (id: string, root: Generated, children: Record<string, Generated> = {}): Curation => ({ active_artifact_id: id, generated: root, child_changes: children })

const item = (id: string, result: Item['result']): Item => ({ id, result, session: null, expected: '', actual: '', note: '' })

const exchange = (artifact: string, records: RecordRow[] = []): Exchange => ({ user: 'u', execution: { turn_id: 't', artifact_id: artifact, records } })

const round = (artifact: string, items: Item[], curations: Curation[] = [], records: RecordRow[] = []): Round => ({
  sessions: { haggler: [exchange(artifact, records)] },
  signals: [{ source: 'agency', text: '', items, metrics: {}, satisfied: false }],
  feedback: null,
  curated: curations.length > 0,
  analysis: [],
  curation: curations,
})

const dag: RecordRow = { kind: 'dag.progress', name: 'dag_run_started', payload: { run_id: 'r', nodes: [{ id: 'research', subagent: 'Raven-Research' }] } }

const run: Run = {
  task_id: 't',
  task: 'T',
  initial_curation: [curation('a1', generated([['memory.strategy', 'add']], { 'memory.strategy': { factory: 'memory_impl:create' } }, { 'memory_impl.py': '' }))],
  rounds: [
    round('a1', [item('no-discount', 'fail'), item('quote', 'fail'), item('tone', 'pass')], [
      curation(
        'a2',
        generated([['action.strategy', 'add']], { 'action.strategy': { factory: 'gate:create', events: ['proposal'] } }, { 'gate.py': '' }),
        { 'Raven-PPT': generated([['capability.strategy', 'modify']], { 'capability.strategy': { factory: 'deck.cap:create' } }, { 'deck/cap.py': '' }) },
      ),
    ]),
    round('a2', [item('no-discount', 'pass'), item('quote', 'fail'), item('tone', 'pass')], [], [dag]),
    round('a2', [item('no-discount', 'pass'), item('quote', 'pass'), item('tone', 'unknown')]),
  ],
}

const criteria: Criterion[] = [
  { id: 'no-discount', check: 'No discount', severity: 'red_line' },
  { id: 'quote', check: 'Quote from the list', severity: 'red_line' },
  { id: 'tone', check: 'Warm', severity: 'standard' },
]

describe('harness rows', () => {
  it('list the root and every child Harness changed or run, with its changes by version', () => {
    const rows = harnessRows(run, revisions(run))
    expect(rows.map((row) => row.harness)).toEqual(['Main agent', 'Raven-PPT', 'Raven-Research'])
    const [main, ppt, research] = rows
    expect(Object.keys(main.changes)).toEqual(['v1', 'v2'])
    expect(main.changes.v2).toEqual([{ target: 'action.strategy', strategy: 'action', treatment: 'add', expected: 'expect action.strategy', files: ['gate.py'] }])
    expect(ppt.changes.v2).toEqual([{ target: 'capability.strategy', strategy: 'capability', treatment: 'modify', expected: 'expect capability.strategy', files: ['deck/cap.py'] }])
    expect([main.last, ppt.last, research.last]).toEqual(['v2', 'v2', null])
  })

  it('name the files a later revision rewrote for a target whose code an earlier one wrote', () => {
    const profile = { 'memory.strategy': { factory: 'memory_impl:create' } }
    const later: Run = {
      ...run,
      initial_curation: [curation('a1', generated([['memory.strategy', 'add']], profile, { 'memory_impl.py': 'PROFILE = "memory_profile/agent.md"', 'memory_profile/agent.md': 'one' }))],
      rounds: [round('a1', [], [curation('a2', generated([['memory.strategy', 'modify']], {}, { 'memory_profile/agent.md': 'two' }))])],
    }
    const [main] = harnessRows(later, revisions(later))
    expect(main.changes.v1[0].files).toEqual(['memory_impl.py', 'memory_profile/agent.md'])
    expect(main.changes.v2[0].files).toEqual(['memory_profile/agent.md'])
  })

  it('show a withdrawn child Harness as restored to its baseline', () => {
    const withdrawn: Run = { ...run, rounds: [...run.rounds.slice(0, 2), round('a2', [], [{ ...curation('a3', generated([])), withdrawn_children: ['Raven-PPT'] }])] }
    const ppt = harnessRows(withdrawn, revisions(withdrawn)).find((row) => row.harness === 'Raven-PPT')!
    expect(ppt.changes.v3).toEqual([{ target: 'Restore baseline', strategy: null, treatment: null, expected: 'Authored child bindings retired', files: [] }])
    expect(ppt.last).toBe('v3')
  })
})

describe('red lines by version', () => {
  it('list red lines per round with the strategies the revision that produced each version changed', () => {
    const matrix = redLines(run, revisions(run), criteria)
    expect(matrix.marked).toBe(true)
    expect(matrix.columns.map((column) => [column.version, column.strategies, column.fresh])).toEqual([
      ['v1', ['memory'], true],
      ['v2', ['capability', 'action'], true],
      ['v2', [], false],
    ])
    expect(matrix.rows.map((row) => [row.criterion.id, row.cells.map(cellTone)])).toEqual([
      ['no-discount', ['fail', 'pass', 'pass']],
      ['quote', ['fail', 'fail', 'pass']],
    ])
    expect(matrix.others.map((row) => [row.criterion.id, row.cells.map(cellTone)])).toEqual([['tone', ['pass', 'pass', 'unknown']]])
  })

  it('fall back to every judged criterion when no scenario red line was judged', () => {
    const matrix = redLines(run, revisions(run), [{ id: 'elsewhere', check: '', severity: 'red_line' }])
    expect(matrix.marked).toBe(false)
    expect(matrix.rows.map((row) => row.criterion.id)).toEqual(['no-discount', 'quote', 'tone'])
    expect(matrix.others).toEqual([])
    expect(redLines(run, revisions(run), []).rows).toHaveLength(3)
  })

  it('count repeated verdicts of one criterion in a round', () => {
    const repeated: Run = { ...run, rounds: [round('a1', [item('quote', 'fail'), item('quote', 'pass')])] }
    const matrix = redLines(repeated, revisions(repeated), criteria)
    expect(matrix.rows[1].cells[0]).toEqual({ pass: 1, fail: 1, unknown: 0 })
    expect(cellTone(null)).toBe('none')
  })
})

it('reads the files a housed sub-harness reads on its next turn: its profile, tools note, user profile and skills', () => {
  expect(['TOOLS.md', 'agent_memory/profile/agent.md', 'skills/deck/SKILL.md', 'HEARTBEAT.md'].map(readBySubharness)).toEqual([true, true, true, false])
})

it('shows a child-only revision and its full strategy change without inventing a root change', () => {
  const root = curation('composite-v1', generated([]), { Hosted: generated([['action.strategy', 'replace']]) })
  const composite = { ...run, initial_curation: [root], rounds: [round('composite-v1', [])] }
  const all = revisions(composite)
  const rows = harnessRows(composite, all)
  expect(rows.find((row) => row.harness === 'Main agent')!.last).toBeNull()
  expect(rows.find((row) => row.harness === 'Hosted')!.changes.v1[0]).toMatchObject({ target: 'action.strategy', treatment: 'replace' })
  expect(redLines(composite, all, []).columns[0].strategies).toEqual(['action'])
})
