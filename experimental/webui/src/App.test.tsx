import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, onTestFinished, test, vi } from 'vitest'

import { App, entryLabel, entryTitle, groups, parseHash } from './App'
import { progress, roundVersions, revisions } from './derive'

import type { Run, RunEntry } from './model'

const diagnosis = { about: 'R1', state: 'not_triggered', mechanism: 'no intake step in the planning strategy' }

const run: Run = {
  task_id: 't',
  task: "Serve the agency's travellers",
  status: 'finished',
  initial_curation: [{ file: 'c1.json', active_artifact_id: 'artifact-0', generated: undefined }],
  rounds: [
    {
      sessions: {
        student: [
          {
            user: 'Plan a trip',
            execution: {
              turn_id: 'turn-1',
              artifact_id: 'artifact-0',
              records: [
                { kind: 'runner.event', event_type: 'Text', event: { content: 'Here is a three-day itinerary.' } },
                { kind: 'action.call', operation: 'handle_event', arguments: [{ event_id: 'e1', kind: 'proposal', stage: 'final' }] },
                { kind: 'action.result', operation: 'handle_event', result: { control: 'revise', reason: 'itinerary before the budget', feedback: 'Ask the budget first.' } },
                { kind: 'action.control', receipt: { control_id: 'k1', source_id: 'e1', control: 'revise', status: 'applied', reason: 'itinerary before the budget' } },
                { kind: 'tool.error', error: 'no pricing skill' },
              ],
            },
          },
        ],
      },
      signals: [
        { source: 'verifier', text: 'Never asked the budget.', items: [{ id: 'asks budget', result: 'fail', session: 'student', expected: '', actual: '', note: 'Here is' }], metrics: {}, satisfied: false },
        { source: 'dataset', text: '', items: [{ id: '7', result: 0.5, session: 'case:7', expected: 'Paris', actual: 'Lyon', note: '' }], metrics: { pass_rate: 0.5 }, satisfied: false },
      ],
      feedback: {
        decision: 'curate',
        reason: 'Intake gap.',
        requirements: [
          { id: 'R1', situation: 'Any new enquiry', behavior: 'Ask for the budget first.', observed: 'Recommended at once.', evidence: ['turn-1'], expectation: 'new', acceptance: 'Budget asked before any itinerary.', strength: 'must_hold' },
        ],
        filtered: ['Too chatty (preference)'],
        task_updates: [],
      },
      curated: true,
      analysis: [{ file: 'a1.json', trace: [{ event: 'model.call' }, { event: 'submit_feedback' }] }],
      attribution: [{ file: 'att-1.json', calls: 3, queries: 7, subjects: ['R1'], identity: { model: 'deepseek/deepseek-flash', implementation: 'model' }, attribution: { diagnoses: [diagnosis] } }],
      curation: [
        {
          file: 'c2.json',
          active_artifact_id: 'artifact-2-long-id',
          attribution: 'att-1.json',
          generated: {
            candidate: {
              plan: { understanding: 'Intake is missing.', design: 'Track intake in planning.', changes: [{ target: 'planning.strategy', treatment: 'add', reason: 'r', expected: 'Budget asked first', verification: 'planning state shows budget' }] },
              artifact: { values: { 'planning.strategy': { factory: 'plan:create', context: true } }, files: { 'plan.py': 'print(1)' } },
              attribution: { attribution: { diagnoses: [diagnosis] }, identity: { model: 'deepseek/deepseek-flash', implementation: 'model' }, record: 'att-1.json' },
              selection: { understanding: 'Planning owns the order of the intake.', targets: ['planning.strategy'], grounds: { 'planning.strategy': ['R1'] } },
            },
            validation: { errors: [], observations: [{ kind: 'runtime.bound', targets: ['planning.strategy'] }] },
            trace: [{ event: 'model.call' }],
          },
        },
      ],
    },
    {
      sessions: { student: [] },
      signals: [{ source: 'verifier', text: '', items: [{ id: 'asks budget', result: 'pass', session: 'student', expected: '', actual: '', note: '' }], metrics: {}, satisfied: true }],
      feedback: { decision: 'continue', reason: 'Every check passed.', requirements: [], filtered: [], task_updates: [] },
      curated: false,
      analysis: [],
      curation: [],
    },
  ],
  history: [
    { round: 1, requirements: [{ id: 'R1', behavior: 'Ask for the budget first.', strength: 'must_hold', acceptance: 'Budget asked before any itinerary.', held: true }], revision: [{ target: 'planning.strategy', treatment: 'add', addresses: ['R1'] }], diagnoses: [diagnosis], attributor: { model: 'deepseek/deepseek-flash' } },
  ],
  standard: {
    criteria: [{ id: 'derived-1', text: 'Name the source of every price.', source: 'derived', strength: 'should', provenance: 'material:sop Step 4', quote: 'name the source of every price' }],
    derived_from: ['sop'],
    calls: { rubric_builder: 1, assessor: 2 },
    revisions: [
      {
        version: 1,
        new_norms: ['sop'],
        changes: [{ id: 'derived-1', op: 'add', reason: 'new_norm', explanation: 'Step 4 states it.', before: '', text: 'Name the source of every price.', material: 'sop', quote: 'name the source of every price' }],
        unchecked: [{ material: 'sop', section: 'Step 9', reason: 'happens after the conversation' }],
      },
    ],
  },
}

const entries: RunEntry[] = [
  { id: 'w/r', name: 'w', task: run.task, curator: 'improve', passes: [[1, 1], [2, 0]], rounds: 2, status: 'finished', error: null, recorded: 1 },
]

const liveReply = {
  logs: [{ file: 'replicas/3-session-04a427/w1', start: 0, offset: 120, size: 120, reset: true, last_event: 1000 }],
  last_event: 1000, now: 1030, status: 'running', labels: { haggler: 'session-04a427' },
  phase: { name: 'trial', round: 3, stage: null, basis: 'a turn is in progress' },
  rows: [
    { kind: 'provider.request', turn_id: 'live-1', text: 'Is it cheaper in March?', drill: 'session-04a427' },
    { kind: 'runner.event', turn_id: 'live-1', event_type: 'ToolEvent', event: { phase: 'start', tool_call_id: 'c', name: 'read_skill', arguments: { skill_id: 'local/price-list' } } },
    { kind: 'action.call', turn_id: 'live-1', operation: 'handle_event', arguments: [{ event_id: 'e1', kind: 'proposal', stage: 'final' }] },
    { kind: 'action.result', turn_id: 'live-1', operation: 'handle_event', result: { control: 'revise', reason: 'discount promised', feedback: 'Quote the list price.' } },
    { kind: 'action.control', turn_id: 'live-1', receipt: { control_id: 'k1', source_id: 'e1', control: 'revise', status: 'applied', reason: 'discount promised' } },
  ].map((row) => ({ ...row, file: 'replicas/3-session-04a427/w1' })),
}

const scenario = { criteria: [{ id: 'asks budget', check: 'Asks the budget first', severity: 'red_line' }], initial: ['price-list'], materials: ['price-list'] }

afterEach(cleanup)

beforeEach(() => {
  window.location.hash = ''
  vi.stubGlobal('fetch', vi.fn(async (path: string) => ({
    ok: true,
    status: 200,
    json: async () => (path === '/api/runs' ? entries : path.startsWith('/api/scenario') ? scenario : path.startsWith('/api/live') ? liveReply : run),
  })))
})

test('the cultivation view is the owner and the Curator in conversation, round by round', async () => {
  render(<App />)
  expect(await screen.findByText("Serve the agency's travellers")).toBeTruthy()
  expect(screen.getByText('owner · onboarding')).toBeTruthy()
  expect(screen.getByText('price-list')).toBeTruthy()
  expect(screen.getByText('This revision failed, so the employee stays on v0.')).toBeTruthy()
  expect(screen.getByText('Never asked the budget.')).toBeTruthy()
  expect(screen.getByText('Ask for the budget first.')).toBeTruthy()
  expect(screen.getAllByText('curate').length).toBeGreaterThan(0)
  expect(screen.getByText('Intake is missing.')).toBeTruthy()
  expect(screen.getAllByText('planning.strategy').length).toBeGreaterThan(0)
  expect(screen.getAllByText('planning', { selector: '.cls' }).length).toBeGreaterThan(0)
  expect(screen.getByText('add', { selector: '.treat' })).toBeTruthy()
  expect(screen.getByText('R1', { selector: '.rid' })).toBeTruthy()
  expect(screen.getByText('held next round')).toBeTruthy()
  const diagnoses = document.querySelector<HTMLElement>('.diagnoses')!
  expect(within(diagnoses).getByText('not triggered')).toBeTruthy()
  expect(within(diagnoses).getByText('no intake step in the planning strategy')).toBeTruthy()
  expect(within(diagnoses).getByText('deepseek/deepseek-flash · model')).toBeTruthy()
  expect(within(diagnoses).getByText('3 calls · 7 queries')).toBeTruthy()
  expect(screen.getByText('R1', { selector: '.change .about' })).toBeTruthy()
  expect(screen.getByText('No revision: the Analyst kept the employee as it is and ran another trial.')).toBeTruthy()
  expect(screen.getByText('finished · on v1')).toBeTruthy()
  fireEvent.click(screen.getByText(/Generated code and bindings/))
  expect(await screen.findByText('Round 2 trial of v1: no call recorded (planning.call and planning.callback records).')).toBeTruthy()
  expect(screen.getByText('plan:create')).toBeTruthy()
  expect(screen.getByText('Bound by the host check before deployment.')).toBeTruthy()
  fireEvent.click(screen.getByText("the Curator's technical design"))
  expect(await screen.findByText('Track intake in planning.')).toBeTruthy()
  expect(screen.getByText('plan.py', { selector: '.asm code.ref' })).toBeTruthy()
  fireEvent.click(screen.getByText('plan.py', { selector: 'summary code' }))
  expect(await screen.findByText((_, node) => !!node?.classList.contains('cb-code') && node.textContent === 'print(1)')).toBeTruthy()
  const reply = document.querySelector<HTMLElement>('.say.curator:not(:has(.failed))')!
  expect(within(reply.querySelector<HTMLElement>(':scope > .who')!).queryByRole('button', { name: 'raw' })).toBeNull()
  const change = reply.querySelector<HTMLElement>('.changes .change')!
  fireEvent.click(within(change).getByRole('button', { name: 'raw' }))
  const panel = reply.querySelector<HTMLElement>('.changes .change[data-raw] .rawpanel')!
  expect([...panel.querySelectorAll('.rp-path')].map((path) => path.textContent)).toEqual([
    'generated.candidate.plan.changes[0]',
    'generated.candidate.artifact.values["planning.strategy"]',
    'generated.candidate.artifact.files["plan.py"]',
    'generated.candidate.selection.grounds["planning.strategy"]',
  ])
  expect(within(panel).getByText('c2.json')).toBeTruthy()
  const implementation = panel.querySelector<HTMLElement>('.codeblock[data-language="python"]')!
  expect(implementation.querySelector('.cb-code')!.textContent).toBe('print(1)')
  expect(implementation.querySelector('.hljs-built_in')!.textContent).toBe('print')
  expect(within(reply).getByText('Intake is missing.', { selector: '.under p' })).toBeTruthy()
  const understanding = reply.querySelector<HTMLElement>('.part')!
  fireEvent.click(within(understanding).getByRole('button', { name: 'raw' }))
  expect(understanding.querySelector('.codeblock[data-prose] .cb-code')!.textContent).toBe('Intake is missing.')
  expect(within(understanding).getByText('generated.candidate.plan.understanding')).toBeTruthy()
  fireEvent.click(within(understanding).getByRole('button', { name: 'rendered' }))
  expect(within(reply).getByText('Intake is missing.', { selector: '.under p' })).toBeTruthy()
  fireEvent.click(within(reply.querySelector<HTMLElement>('.changes .change')!).getByRole('button', { name: 'rendered' }))
  expect(reply.querySelector('.changes details.change')).toBeTruthy()
  const standard = document.querySelector<HTMLElement>('.standard-block')!
  expect(within(standard).getByText('1 written by the rubric builder from sop')).toBeTruthy()
  fireEvent.click(within(standard).getByText('Revision 1: 1 added · new: sop'))
  expect(await within(standard).findByText('Step 4 states it.')).toBeTruthy()
  expect(within(standard).getByText('sop: name the source of every price')).toBeTruthy()
  expect(within(standard).getByText('not checkable: sop Step 9, happens after the conversation')).toBeTruthy()
})

test("a silent owner's remark says it only measured the round", async () => {
  vi.stubGlobal('fetch', vi.fn(async (path: string) => ({
    ok: true,
    status: 200,
    json: async () => (path === '/api/runs' ? entries : path.startsWith('/api/scenario') ? scenario : path.startsWith('/api/live') ? liveReply : { ...run, measuring: ['agency'] }),
  })))
  render(<App />)
  expect(await screen.findByText("Serve the agency's travellers")).toBeTruthy()
  const marks = document.querySelectorAll('.say.owner .who .silent')
  expect(marks.length).toBe(run.rounds.length)
  expect(marks[0].textContent).toBe('silent · measurement only')
})

test('the loop line above the conversation sends it to a station, and marks the station pointed at in it', async () => {
  const sent: string[] = []
  const scroll = vi.fn(function (this: HTMLElement) {
    sent.push(this.dataset.station ?? this.dataset.reply ?? '')
  })
  const kept = Element.prototype.scrollIntoView
  Element.prototype.scrollIntoView = scroll as unknown as Element['scrollIntoView']
  onTestFinished(() => {
    Element.prototype.scrollIntoView = kept
  })
  render(<App />)
  const line = await screen.findByRole('group', { name: 'The cultivation loop' })
  expect(screen.getByText("Serve the agency's travellers")).toBeTruthy()
  fireEvent.click(within(line).getByRole('button', { name: /^round 1, Analyse/ }))
  expect(sent).toEqual(['1:analyse'])
  const requirements = document.querySelector<HTMLElement>('[data-station="1:analyse"]')!
  expect(requirements.classList.contains('flash')).toBe(true)
  expect(within(requirements).getByText('Ask for the budget first.')).toBeTruthy()
  fireEvent.click(within(line).getByRole('button', { name: /^round 1, Diagnose/ }))
  fireEvent.click(within(line).getByRole('button', { name: /^round 2, Diagnose/ }))
  expect(sent.slice(1)).toEqual(['1:diagnose', '2:diagnose'])
  expect(document.querySelector('[data-station="2:diagnose"]')!.textContent).toBe('No revision: the Analyst kept the employee as it is and ran another trial.')
  fireEvent.mouseOver(screen.getByText('Never asked the budget.'))
  expect(within(line).getByRole('button', { name: /^round 1, Assess/ }).hasAttribute('data-on')).toBe(true)
  expect(within(line).getByRole('button', { name: /^round 1, Assess/ }).getAttribute('aria-current')).toBe('location')
})

test('a read of the previous run that answers late is not drawn under the run picked since', async () => {
  let late: (value: unknown) => void = () => undefined
  const second = { ...run, task: 'Serve the second agency' }
  const listed = [...entries, { ...entries[0], id: 'x/s', name: 'x', task: second.task }]
  vi.stubGlobal('fetch', vi.fn(async (path: string) => {
    if (path === '/api/runs/w/r') await new Promise((resolve) => { late = resolve })
    return {
      ok: true,
      status: 200,
      json: async () => (path === '/api/runs' ? listed : path.startsWith('/api/scenario') ? scenario : path === '/api/runs/x/s' ? second : run),
    }
  }))
  render(<App />)
  const picker = await screen.findByLabelText('Run')
  await screen.findByRole('option', { name: /^x/ })
  fireEvent.change(picker, { target: { value: 'x/s' } })
  expect(await screen.findByText('Serve the second agency')).toBeTruthy()
  late(undefined)
  await new Promise((resolve) => setTimeout(resolve, 20))
  expect(screen.queryByText("Serve the agency's travellers")).toBeNull()
  expect(screen.getByText('Serve the second agency')).toBeTruthy()
})

test('a trial opens beside the conversation from its card, with drills, interceptions and verdicts, red lines marked', async () => {
  render(<App />)
  await screen.findByText("Serve the agency's travellers")
  expect(screen.queryByRole('tab', { name: 'Trials' })).toBeNull()
  const card = document.getElementById('trial-1')!
  expect(within(card).getByText('Round 1 trial')).toBeTruthy()
  expect(within(card).getByText('1 failed')).toBeTruthy()
  expect(within(card).getByText('1 interception')).toBeTruthy()
  fireEvent.click(within(card).getByText('student'))
  const panel = await screen.findByRole('complementary', { name: 'Round 1 trial' })
  expect(window.location.hash).toBe('#cultivation/trial/1')
  expect(card.className).toContain('on')
  expect(screen.getByText("Serve the agency's travellers")).toBeTruthy()
  expect(within(panel).getByText('Plan a trip')).toBeTruthy()
  expect(within(panel).getByText('Here is a three-day itinerary.')).toBeTruthy()
  expect(within(panel).getByText('The action strategy sent the draft back')).toBeTruthy()
  expect(within(panel).getByText('no pricing skill')).toBeTruthy()
  fireEvent.click(within(panel).getByRole('tab', { name: /Verdicts/ }))
  expect(within(panel).getAllByText('red line').length).toBeGreaterThan(0)
  expect(within(panel).getByText('asks budget')).toBeTruthy()
  fireEvent.click(within(panel).getByRole('button', { name: 'Next round' }))
  expect(await screen.findByRole('complementary', { name: 'Round 2 trial' })).toBeTruthy()
  expect(window.location.hash).toBe('#cultivation/trial/2')
  fireEvent.keyDown(window, { key: 'Escape' })
  expect(screen.queryByRole('complementary')).toBeNull()
  expect(window.location.hash).toBe('#cultivation')
})

test('the harness view shows changes by harness and red lines by version', async () => {
  render(<App />)
  await screen.findByText("Serve the agency's travellers")
  fireEvent.click(screen.getByRole('tab', { name: 'Harness' }))
  expect(await screen.findByText('Red lines by version')).toBeTruthy()
  const table = screen.getByText('Changes by harness').closest('section')!
  expect(within(table).getByText('Main agent')).toBeTruthy()
  expect(within(table).getAllByText('planning.strategy').length).toBe(1)
  expect(within(table).getByText('add', { selector: '.treat' })).toBeTruthy()
  expect(within(table).getByText('plan.py')).toBeTruthy()
  expect(screen.getAllByText('fail').length).toBeGreaterThan(0)
})



test('progress reports verdicts by round and the flips between them', () => {
  const signal = (results: Record<string, 'pass' | 'fail' | 'unknown'>) => ({
    source: 'agency', text: '', metrics: {}, satisfied: null,
    items: Object.entries(results).map(([id, result]) => ({ id, result, session: null, expected: '', actual: '', note: '' })),
  })
  const run = {
    task_id: 't', task: 'T', rounds: [
      { sessions: {}, signals: [signal({ intake: 'fail', price: 'pass' })], feedback: { decision: 'curate', reason: '', requirements: [], filtered: [], task_updates: [] }, curated: true, analysis: [], curation: [] },
      { sessions: {}, signals: [signal({ intake: 'pass', price: 'fail' })], feedback: { decision: 'continue', reason: '', requirements: [], filtered: [], task_updates: [] }, curated: false, analysis: [], curation: [] },
    ], initial_curation: [],
  } as unknown as Run
  const report = progress(run)
  expect(report.matrix['agency/intake']).toEqual(['fail', 'pass'])
  expect(report.improved).toEqual(['agency/intake'])
  expect(report.regressed).toEqual(['agency/price'])
})


test('round versions follow the artifact each round ran on, else the last revision before the round', () => {
  expect(roundVersions(run, revisions(run))).toEqual(['v0', 'v1'])
})

test('the location hash names the view and the trial open beside the conversation', () => {
  expect(parseHash('#cultivation/trial/3')).toEqual({ view: 'cultivation', round: 3, chosen: true })
  expect(parseHash('#trials/3')).toEqual({ view: 'cultivation', round: 3, chosen: true })
  expect(parseHash('#trials/x')).toEqual({ view: 'cultivation', round: null, chosen: true })
  expect(parseHash('#cultivation')).toEqual({ view: 'cultivation', round: null, chosen: true })
  expect(parseHash('#harness')).toEqual({ view: 'harness', round: null, chosen: true })
  expect(parseHash('#harness/trial/2')).toEqual({ view: 'harness', round: null, chosen: true })
  expect(parseHash('#live')).toEqual({ view: 'live', round: null, chosen: true })
  expect(parseHash('#record')).toEqual({ view: 'record', round: null, chosen: true })
  expect(parseHash('')).toEqual({ view: 'cultivation', round: null, chosen: false })
  expect(parseHash('#nowhere')).toEqual({ view: 'cultivation', round: null, chosen: false })
})

describe('run labels', () => {
  it('name each run by its folder, arm and per-round results, archives last', () => {
    const control: RunEntry = { ...entries[0], id: 'archive-c/r', name: 'archive-c', curator: 'untouched', passes: [[4, 7]], status: 'running' }
    expect(entryLabel(entries[0])).toBe('w · Curator · 1/2 → 2/2')
    expect(entryLabel(control)).toBe('archive-c · control · 4/11 · running')
    expect(entryLabel({ ...entries[0], status: 'stalled' })).toBe('w · Curator · 1/2 → 2/2 · stalled or stopped')
    const suite: RunEntry = {
      ...entries[0], status: 'error', disclose: 'staged', stopped: 'spend passed the $40 budget',
      models: { partner: 'deepseek/deepseek-flash', curator: 'deepseek/deepseek-flash', 'sub-harness': 'z-ai/glm-5.3' },
    }
    expect(entryLabel(suite)).toBe('w · staged · Curator · 1/2 → 2/2 · deepseek-flash · sub-harness glm-5.3 · stopped by the suite')
    expect(entryTitle(suite)).toBe('partner, curator deepseek/deepseek-flash · sub-harness z-ai/glm-5.3\nStopped: spend passed the $40 budget')
    expect(groups([control, entries[0]]).map(([group, rows]) => [group, rows.map((row) => row.name)])).toEqual([
      ['Runs', ['w']],
      ['Archive', ['archive-c']],
    ])
  })
})

describe('markdown', () => {
  it('renders model text with emphasis and tables, and shows raw html as text', async () => {
    const { Markdown } = await import('./views/Markdown')
    const { container } = render(<Markdown text={'**Quote sheet**\n\n| Item | Amount |\n|---|---|\n| Party total | 9,400 yuan |\n\n<script>x</script>'} />)
    expect(container.querySelector('strong')?.textContent).toBe('Quote sheet')
    expect(container.querySelector('table td')?.textContent).toBe('Party total')
    expect(container.querySelector('script')).toBeNull()
  })
})

test('a run whose research stage stopped shows why, and that no round ran', async () => {
  const stopped: Run = {
    ...run,
    status: 'incomplete',
    initial_curation: [],
    rounds: [],
    history: [],
    research: {
      status: 'incomplete',
      stop_reason: 'error',
      seconds: 276,
      review: { accepted: false, reason: 'assess: submission budget exhausted', issues: ['Complete collection and review before handoff.'] },
      title: 'Unfinished expert information',
      sections: [{ dimension: 'role', coverage: 'missing', text: '', reason: 'Not assessed before execution ended.', evidence: 0 }],
      resources: [],
      unresolved: [],
      stages: [{ stage: 'assess', calls: 4, queries: 6, submitted: false }],
      trouble: [{ stage: 'assess', event: 'output.rejected', error: 'This is the last call', tools: ['read_file'], charged: false }],
      channels: { tool: 13, research: 1, user: 2, request: 2 },
      evidence: [
        { id: 'evidence-14', channel: 'research', kind: 'finding', question: 'Which articles govern superlatives?', attempt: 'research-3', text: 'Article 9 bans superlatives.', sources: ['https://example.org/law'], dimensions: ['knowledge'] },
        { id: 'evidence-15', channel: 'user', kind: 'answer', question: 'When is the launch?', attempt: '', text: 'The launch is on 12 December.', sources: [], dimensions: [] },
        { id: 'evidence-16', channel: 'user', kind: '', question: 'What is the budget?', attempt: '', text: '', sources: [], dimensions: [] },
      ],
      groups: [{ wave: '1', group: 3, status: 'accepted', dimensions: ['knowledge'], questions: ['Which articles govern superlatives?'], error: '', admitted: 1, refused: 0, withheld: 0, unanswered: 0 }],
      errors: [],
    },
  }
  vi.stubGlobal('fetch', vi.fn(async (path: string) => ({
    ok: true,
    status: 200,
    json: async () => (path === '/api/runs' ? entries : path.startsWith('/api/scenario') ? scenario : stopped),
  })))
  render(<App />)
  const block = await screen.findByText('Curator side · research stage', { exact: false })
  const research = block.closest<HTMLElement>('.research-block')!
  expect(within(research).getByText('The collection stopped (error) before a review accepted it.')).toBeTruthy()
  expect(within(research).getByText('assess: submission budget exhausted')).toBeTruthy()
  expect(within(research).getByText('5 min')).toBeTruthy()
  expect(within(research).getByText('role missing')).toBeTruthy()
  fireEvent.click(within(research).getByText('Missing, rejected or failed replies (1)'))
  expect(await within(research).findByText('· called read_file', { exact: false })).toBeTruthy()
  expect(screen.getByText('The research stage handed over no information, so onboarding stopped before the Curator was called and no round ran.')).toBeTruthy()
  expect(within(research).getByText('research 1')).toBeTruthy()
  expect(within(research).getByText("owner's answers 2")).toBeTruthy()
  fireEvent.click(within(research).getByText('Research groups (1)'))
  expect(await within(research).findByText('Which articles govern superlatives?')).toBeTruthy()
  fireEvent.click(within(research).getByText('Research findings (1)'))
  expect(await within(research).findByText('https://example.org/law')).toBeTruthy()
  fireEvent.click(within(research).getByText("The owner's answers (2)"))
  expect(await within(research).findByText('The launch is on 12 December.')).toBeTruthy()
  expect(within(research).getByText('What is the budget?')).toBeTruthy()
  expect(within(research).getByText('Not answered.')).toBeTruthy()
})

test('an opening leads the conversation with its uploads, and pasted materials fold under the remark', async () => {
  const opened: Run = {
    ...run,
    opening: [{
      source: 'agency', text: 'Welcome. **Read the SOP first.**', items: [], metrics: {}, satisfied: null,
      attachments: [
        { name: 'service-sop', kind: 'norm', files: ['uploads/service-sop/service-sop.md'] },
        { name: 'plan-deck-template', kind: 'exemplar', files: ['uploads/plan-deck-template/plan-deck-template.pptx'] },
        { name: 'logo', kind: 'exemplar', files: ['uploads/logo/logo.png'] },
      ],
    }],
    initial_curation: [{
      file: 'c0.json',
      active_artifact_id: 'artifact-0',
      generated: {
        candidate: {
          plan: { understanding: 'Read the SOP.', changes: [{ target: 'capability.strategy', treatment: 'add', reason: 'r', expected: 'e', verification: '' }, { target: 'action.strategy', treatment: 'add', reason: 'r', expected: 'e', verification: '' }] },
          artifact: { values: { 'capability.strategy': { factory: 'cap:create' }, 'action.strategy': { factory: 'gate:create' } }, files: {} },
          attribution: { attribution: { diagnoses: [{ about: 'material:service-sop', state: 'not_exposed', placement: 'a skill package, read only on demand' }] }, record: 'att-0.json' },
          selection: { understanding: 'Pin the SOP.', targets: ['capability.strategy'], grounds: { 'capability.strategy': ['material:service-sop'] } },
        },
        validation: { errors: [], observations: [] },
        trace: [],
      },
    }],
    rounds: [{ ...run.rounds[0], signals: [{ ...run.rounds[0].signals[0], source: 'agency', text: 'Never asked the budget.\n\n---\n\n# Brand guide\n\nUse navy only.' }] }, run.rounds[1]],
  }
  const urls: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (path: string) => {
    urls.push(path)
    const body = path === '/api/runs' ? entries : path.startsWith('/api/scenario') ? scenario : path.startsWith('/api/thumbs') ? { pages: ['/c/page-01.png', '/c/page-02.png'] } : opened
    return { ok: true, status: 200, json: async () => body, text: async () => '# Service SOP\n\nConfirm before quoting.' }
  }))
  render(<App />)
  expect(await screen.findByText('Read the SOP first.')).toBeTruthy()
  expect(screen.queryByText("Opening materials in the scenario's staged plan")).toBeNull()
  expect(screen.getByText('logo.png', { selector: '.att code' })).toBeTruthy()
  expect(screen.getByText('service-sop', { selector: '.att-name' })).toBeTruthy()
  expect(screen.getByText('norm', { selector: '.att .att-kind' })).toBeTruthy()
  fireEvent.click(screen.getByText('service-sop.md', { selector: '.att-chip' }))
  expect(await screen.findByText('Confirm before quoting.')).toBeTruthy()
  expect(urls).toContain('/api/scenario?run=w%2Fr')
  expect(urls).toContain('/api/upload?run=w%2Fr&path=uploads%2Fservice-sop%2Fservice-sop.md')
  fireEvent.click(screen.getByText('plan-deck-template.pptx', { selector: '.att-chip' }))
  expect(await screen.findByAltText('plan-deck-template.pptx page 2')).toBeTruthy()
  expect(urls).toContain('/api/thumbs?run=w%2Fr&upload=uploads%2Fplan-deck-template%2Fplan-deck-template.pptx')
  expect(screen.getByText('Never asked the budget.')).toBeTruthy()
  expect(screen.queryByText('Use navy only.')).toBeNull()
  fireEvent.click(screen.getByText('Brand guide', { selector: '.pasted .ttl' }))
  expect(await screen.findByText('Use navy only.')).toBeTruthy()
  const intake = document.querySelector<HTMLElement>('.intake')!
  expect(within(intake).getByText('service-sop')).toBeTruthy()
  expect(within(intake).getByText('capability.strategy', { selector: '.hardt' })).toBeTruthy()
  expect(within(intake).getByText('not exposed')).toBeTruthy()
  expect(within(intake).getByText('a skill package, read only on demand')).toBeTruthy()
  expect(within(intake).getByText('logo')).toBeTruthy()
  expect(screen.getAllByText('action.strategy').length).toBeGreaterThan(0)
  expect(screen.getByText('Brand guide', { selector: '.intake code' })).toBeTruthy()
})

test('only uploads the server can reach open as chips', async () => {
  const { attachmentKind, openable } = await import('./views/Attachments')
  expect(attachmentKind('uploads/a.md')).toBe('text')
  expect(attachmentKind('uploads/deck.PPTX')).toBe('deck')
  expect(attachmentKind('uploads/logo.png')).toBe('other')
  expect(openable('uploads/a.md')).toBe(true)
  expect(openable('skills/a.md')).toBe(false)
  expect(openable('uploads/logo.png')).toBe(false)
})

test('a running run opens on the live view, grouped by turn with interceptions highlighted', async () => {
  const running = { ...run, status: 'running' }
  vi.stubGlobal('fetch', vi.fn(async (path: string) => ({
    ok: true,
    status: 200,
    json: async () => (path === '/api/runs' ? entries : path.startsWith('/api/scenario') ? scenario : path.startsWith('/api/live') ? liveReply : running),
  })))
  render(<App />)
  expect(await screen.findByText('Is it cheaper in March?')).toBeTruthy()
  expect(screen.getByRole('tab', { name: 'Live' }).getAttribute('aria-selected')).toBe('true')
  expect(screen.getByText('round 3')).toBeTruthy()
  expect(screen.getByText('last event 30 s ago')).toBeTruthy()
  expect(screen.getByText('a turn is in progress')).toBeTruthy()
  expect(screen.getByText('read_skill')).toBeTruthy()
  expect(screen.getByText('The action strategy sent the draft back')).toBeTruthy()
  expect(screen.getByText('in progress')).toBeTruthy()
  expect(screen.getAllByText('3-haggler', { selector: 'code' }).length).toBeGreaterThan(0)
  expect(screen.getByText('haggler', { selector: '.lturn-hd .nm' })).toBeTruthy()
  const calls = (fetch as unknown as { mock: { calls: string[][] } }).mock.calls.map((call) => call[0])
  expect(calls).toContain('/api/live?run=w%2Fr')
})

test('while the Curator revises, the live view shows its progress instead of an empty turn list', async () => {
  const onboarding = { ...run, status: 'running', initial_curation: [], rounds: [] }
  const curating = {
    ...liveReply,
    rows: [],
    last_event: null,
    phase: { name: 'curating', round: 0, stage: 'implement', basis: "the Curator's progress file is being written (4 calls, 9 queries, 0 checks, 0 repairs)" },
    curator: {
      started: 900, updated: 1020, stage: 'implement', calls: 4, queries: 9, checks: 0, repairs: 0, staged: ['pkg/gate.py'],
      events: [
        { stage: 'implement', event: 'model.note', content: 'Gate delivery until the ticket exists.' },
        { stage: 'implement', event: 'submit_plan', targets: ['action.strategy'] },
        { stage: 'validate', event: 'validation', errors: "['gate lacks adjudicate']" },
      ],
    },
  }
  vi.stubGlobal('fetch', vi.fn(async (path: string) => ({
    ok: true,
    status: 200,
    json: async () => (path === '/api/runs' ? entries : path.startsWith('/api/scenario') ? scenario : path.startsWith('/api/live') ? curating : onboarding),
  })))
  render(<App />)
  expect(await screen.findByText('Gate delivery until the ticket exists.')).toBeTruthy()
  expect(screen.getByText('revising the Harness')).toBeTruthy()
  expect(screen.getByText('validate').closest('li')?.className).toBe('current')
  expect(screen.getByText('4 model calls')).toBeTruthy()
  expect(screen.getByText('pkg/gate.py')).toBeTruthy()
  expect(screen.getByText('submit_plan')).toBeTruthy()
  expect(screen.getByText("'gate lacks adjudicate'")).toBeTruthy()
  expect(screen.getByText('onboarding')).toBeTruthy()
  expect(screen.queryByText('No turn in the worker log yet.')).toBeNull()
})

test('a run the list reads as stalled is not treated as running', async () => {
  vi.stubGlobal('fetch', vi.fn(async (path: string) => ({
    ok: true,
    status: 200,
    json: async () => (path === '/api/runs' ? [{ ...entries[0], status: 'stalled' }] : path.startsWith('/api/scenario') ? scenario : path.startsWith('/api/live') ? liveReply : { ...run, status: 'running' }),
  })))
  render(<App />)
  expect(await screen.findByText('stalled or stopped · on v1')).toBeTruthy()
  expect(screen.getByRole('tab', { name: 'Cultivation' }).getAttribute('aria-selected')).toBe('true')
})

test('the record tab asks the server for the run\'s cultivation record', async () => {
  const urls: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (path: string) => {
    urls.push(path)
    if (path.startsWith('/api/record/export')) return { ok: true, status: 200, json: async () => ({ folder: '/w/record', bundle: null }) }
    if (path.startsWith('/api/record')) return { ok: false, status: 503, json: async () => ({ error: 'record builder not available', detail: 'ModuleNotFoundError' }) }
    return { ok: true, status: 200, json: async () => (path === '/api/runs' ? entries : path.startsWith('/api/scenario') ? scenario : run) }
  }))
  render(<App />)
  await screen.findByText("Serve the agency's travellers")
  fireEvent.click(screen.getByRole('tab', { name: 'Record' }))
  expect(await screen.findByText('The record builder is not available on this server.')).toBeTruthy()
  expect(urls).toContain('/api/record?run=w%2Fr')
  expect(window.location.hash).toBe('#record')
})
