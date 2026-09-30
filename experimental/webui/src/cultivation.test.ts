import { describe, expect, it, test } from 'vitest'

import { handedOver, splitRemark, timeline, unwrap } from './cultivation'
import { harnessAt, revisions, roundVersions } from './derive'

import type { Reply } from './cultivation'
import type { Change, Curation, Diagnosis, Exchange, Feedback, Generated, RecordRow, Round, Run, Selection } from './model'

const change = (target: string, treatment: Change['treatment'] = 'add'): Change => ({ target, treatment, reason: `why ${target}`, expected: `expect ${target}`, verification: '' })

const identity = { implementation: 'model', prompts: 'abc123def456', model: 'deepseek/deepseek-flash', catalogue: true }

function curation(id: string, changes: Change[], values: Record<string, unknown> = {}, files: Record<string, string> = {}, chosen?: { diagnoses: Diagnosis[]; grounds: Selection['grounds'] }): Curation {
  const candidate: Generated['candidate'] = { plan: { understanding: `understood ${id}`, design: `design ${id}`, changes }, artifact: { values, files } }
  if (chosen) {
    candidate.attribution = { attribution: { diagnoses: chosen.diagnoses }, identity, record: `att-${id}.json` }
    candidate.selection = { understanding: `chose for ${id}`, targets: Object.keys(chosen.grounds), grounds: chosen.grounds }
  }
  return {
    file: `${id}.json`,
    active_artifact_id: id,
    generated: { candidate, validation: { errors: [], observations: [{ kind: 'runtime.bound', targets: Object.keys(values) }] }, trace: [] },
  }
}

const turn = (artifact: string, records: RecordRow[] = []): Exchange => ({
  user: 'Hello',
  execution: { turn_id: `t-${artifact}`, artifact_id: artifact, records },
})

const feedback = (decision: Feedback['decision']): Feedback => ({
  decision,
  reason: `because ${decision}`,
  requirements: decision === 'curate'
    ? [{ id: 'R1', situation: 'When a guest asks for a price', behavior: 'Quote only after confirming', observed: 'Quoted early', evidence: ['t-1'], expectation: 'unmet', acceptance: 'No price before confirmation', strength: 'must_hold', recurrence: 2 }]
    : [],
  filtered: [],
  task_updates: [],
})

const round = (sessions: Round['sessions'], decision: Feedback['decision'] | null, curations: Curation[] = []): Round => ({
  sessions,
  signals: [{ source: 'agency', text: `remark ${decision}`, items: [], metrics: {}, satisfied: false }],
  feedback: decision ? feedback(decision) : null,
  curated: decision === 'curate',
  analysis: [],
  curation: curations,
})

const planning = { kind: 'planning.call', operation: 'view' }

function cultivated(): Run {
  return {
    task_id: 't',
    task: 'Serve the agency',
    curator: 'improve',
    initial_curation: [curation('a1', [change('memory.strategy')], { 'memory.strategy': { factory: 'memory_impl:create' } }, { 'memory_impl.py': 'def create(): ...' })],
    rounds: [
      round({ student: [turn('a1')] }, 'curate', [
        curation(
          'a2',
          [change('planning.strategy', 'modify'), change('action.strategy')],
          {
            'planning.strategy': { factory: 'sop.plan:build', context: true },
            'action.strategy': { factory: 'gate:create', events: ['proposal'], dispatch: true },
          },
          { 'sop/plan.py': 'def build(): ...', 'gate.py': 'def create(): ...' },
          { diagnoses: [{ about: 'R1', state: 'not_triggered', mechanism: 'planning.strategy view' }], grounds: { 'planning.strategy': ['R1'], 'action.strategy': ['R1'] } },
        ),
      ]),
      round({ student: [turn('a2', [planning, planning, { kind: 'planning.error', error: 'x' }])] }, 'continue'),
      round({ student: [turn('a2', [planning])] }, 'curate', [{ file: 'c3.json', error: 'budget exhausted', active_artifact_id: 'a2' }]),
    ],
  }
}

const replies = (run: Run): Reply[] =>
  timeline(run, revisions(run)).flatMap((entry) => (entry.kind === 'reply' ? [entry.reply] : []))

describe('versions', () => {
  it('number deployed revisions from v1 and keep the version on a failed one', () => {
    const run = cultivated()
    const all = revisions(run)
    expect(all.map((rev) => [rev.label, rev.deployed, rev.round])).toEqual([['v1', true, null], ['v2', true, 1], ['v2', false, 3]])
    expect(roundVersions(run, all)).toEqual(['v1', 'v2', 'v2'])
  })

  it('assemble the Harness at a version from every deployed revision up to it, retiring what a revision removes', () => {
    const run = cultivated()
    const all = revisions(run)
    expect(Object.keys(harnessAt(all, 'v1').values)).toEqual(['memory.strategy'])
    expect(Object.keys(harnessAt(all, 'v2').values)).toEqual(['memory.strategy', 'planning.strategy', 'action.strategy'])
    expect(Object.keys(harnessAt(all, 'v2').files)).toEqual(['memory_impl.py', 'sop/plan.py', 'gate.py'])
    run.rounds[0].curation[0].generated!.candidate.artifact.remove = ['memory.strategy']
    run.rounds[0].curation[0].generated!.candidate.artifact.remove_files = ['memory_impl.py']
    expect(Object.keys(harnessAt(revisions(run), 'v2').values)).toEqual(['planning.strategy', 'action.strategy'])
    expect(Object.keys(harnessAt(revisions(run), 'v2').files)).toEqual(['sop/plan.py', 'gate.py'])
  })
})

describe('cultivation timeline', () => {
  it('opens with onboarding and then alternates remark, requirements and reply per round', () => {
    const run = cultivated()
    expect(timeline(run, revisions(run)).map((entry) => entry.kind === 'remark' || entry.kind === 'requirements' ? `${entry.kind}:${entry.round}` : entry.kind)).toEqual([
      'onboarding', 'reply',
      'remark:1', 'requirements:1', 'reply',
      'remark:2', 'requirements:2', 'silence',
      'remark:3', 'requirements:3', 'reply',
    ])
  })

  it('labels each reply with its version, the version before it and the round that tried it', () => {
    const [onboarding, second, failed] = replies(cultivated())
    expect([onboarding.from, onboarding.revision.label, onboarding.trial]).toEqual(['v0', 'v1', 1])
    expect([second.from, second.revision.label, second.trial]).toEqual(['v1', 'v2', 2])
    expect([failed.from, failed.revision.label, failed.trial, failed.failure]).toEqual(['v2', 'v2', null, 'budget exhausted'])
    expect(second.understanding).toBe('understood a2')
  })

  it('carries the attribution a reply was chosen from, and its selection', () => {
    const [onboarding, second] = replies(cultivated())
    expect(onboarding.attribution).toBeNull()
    expect(second.attribution?.diagnoses).toEqual([{ about: 'R1', state: 'not_triggered', mechanism: 'planning.strategy view' }])
    expect(second.attribution?.identity).toMatchObject({ model: 'deepseek/deepseek-flash' })
    expect(second.selection?.grounds).toEqual({ 'planning.strategy': ['R1'], 'action.strategy': ['R1'] })
  })

  it('shows each change with its strategy, treatment, the inputs it addresses, its hooks, code and next-round calls', () => {
    const [, second] = replies(cultivated())
    const [plan, gate] = second.changes
    expect([plan.strategy, plan.treatment, gate.strategy, gate.treatment]).toEqual(['planning', 'modify', 'action', 'add'])
    expect(plan.addresses).toEqual(['R1'])
    expect(plan.hooks.map((hook) => hook.name)).toEqual(['factory', 'context'])
    expect(gate.hooks.map((hook) => hook.name)).toEqual(['factory', 'events', 'dispatch'])
    expect([plan.files, gate.files]).toEqual([['sop/plan.py'], ['gate.py']])
    expect([plan.bound, gate.bound]).toEqual([true, true])
    expect(plan.evidence).toMatchObject({ calls: 2, errors: 1 })
    expect(gate.evidence).toMatchObject({ calls: 0 })
  })

  it('says why a round has no reply', () => {
    const run = cultivated()
    const silences = timeline(run, revisions(run)).flatMap((entry) => (entry.kind === 'silence' ? [entry.text] : []))
    expect(silences).toEqual(['No revision: the Analyst kept the employee as it is and ran another trial.'])
  })

  it('stands a gap the Curator reported where its reply would be', () => {
    const run = cultivated()
    run.rounds[2].curation = []
    run.rounds[2].curated = false
    run.questions = [{ round: 3, stage: 'select', question: 'Which price list is current?' }]
    const last = timeline(run, revisions(run)).at(-1)
    expect(last).toMatchObject({ kind: 'silence', round: 3, text: expect.stringMatching(/gap at its select stage.*Which price list is current\?/) })
  })

  it('keeps a round held-out drills and their assessment beside its remark', () => {
    const run = cultivated()
    run.rounds[1].holdout = { 'holdout-1': [turn('a2')] }
    run.rounds[1].holdout_signals = [{ source: 'agency', text: 'held-out remark', items: [], metrics: {}, satisfied: true }]
    const remark = timeline(run, revisions(run)).find((entry) => entry.kind === 'remark' && entry.round === 2)
    expect(remark).toMatchObject({ heldOut: ['holdout-1'], holdout: [{ text: 'held-out remark' }] })
  })

  it('reads whether each requirement held after its revision from the history', () => {
    const run = cultivated()
    run.history = [{ round: 1, requirements: [{ id: 'R1', behavior: 'Quote only after confirming', strength: 'must_hold', acceptance: 'x', held: true }], revision: [], diagnoses: null, attributor: null }]
    const requirements = timeline(run, revisions(run)).filter((entry) => entry.kind === 'requirements')
    expect(requirements.map((entry) => (entry.kind === 'requirements' ? entry.held : null))).toEqual([{ R1: true }, {}, {}])
  })

  it('puts a control run on the baseline with no replies', () => {
    const run: Run = { task_id: 't', task: 'T', curator: 'untouched', initial_curation: [], rounds: [round({ a: [turn('base')] }, null)] }
    const entries = timeline(run, revisions(run))
    expect(entries.map((entry) => entry.kind)).toEqual(['onboarding', 'silence', 'remark', 'silence'])
    expect(entries[1]).toMatchObject({ text: expect.stringMatching(/^Control arm/) })
    expect(entries[2]).toMatchObject({ version: 'v0' })
    expect(entries[3]).toMatchObject({ text: expect.stringMatching(/did not complete/) })
  })
})

describe('pasted materials', () => {
  it('leave a remark without a separator whole', () => {
    expect(splitRemark('The quote was wrong twice.')).toEqual({ remark: 'The quote was wrong twice.', pasted: [] })
  })

  it('split each material pasted after a --- line, titled by its first heading', () => {
    const text = 'Fix the deck.\n\n---\n\n# Brand guide\n\nUse navy.\n\n---\n\n## Price list\n\n| a | b |'
    expect(splitRemark(text)).toEqual({
      remark: 'Fix the deck.',
      pasted: [
        { title: 'Brand guide', text: '# Brand guide\n\nUse navy.' },
        { title: 'Price list', text: '## Price list\n\n| a | b |' },
      ],
    })
  })

  it('keep a rule inside a pasted material that no heading follows, and name an untitled material', () => {
    const text = 'Remark.\n---\n# Guide\nPart one\n---\nPart two\n---\nno heading here'
    expect(splitRemark(text).pasted).toEqual([{ title: 'Guide', text: '# Guide\nPart one\n---\nPart two\n---\nno heading here' }])
    expect(splitRemark('Remark.\n---\nplain text').pasted).toEqual([{ title: 'Pasted material 1', text: 'plain text' }])
  })

  it('name what a round handed over: attached materials and pasted materials of the owner', () => {
    expect(handedOver([
      { source: 'agency', text: 'Here.\n---\n# Brand guide\nNavy.', items: [], metrics: {}, satisfied: false, attachments: [{ name: 'logo', kind: 'exemplar', files: ['uploads/logo/logo.png'] }] },
      { source: 'verifier', text: 'x\n---\n# Not a paste', items: [], metrics: {}, satisfied: null },
    ])).toEqual(['logo', 'Brand guide'])
  })
})

describe('handover in replies', () => {
  it('pair each material handed over before a revision with its diagnosis and the targets grounded on it', () => {
    const run = cultivated()
    const sop = { name: 'service-sop', kind: 'norm', files: ['uploads/service-sop/sop.md'] }
    const deck = { name: 'deck-template', kind: 'exemplar', files: ['uploads/deck-template/plan.pptx'] }
    run.opening = [{ source: 'agency', text: 'Welcome aboard.', items: [], metrics: {}, satisfied: null, attachments: [sop, deck] }]
    const placed: Diagnosis = { about: 'material:service-sop', state: 'not_exposed', placement: 'uploads only; nothing reads it' }
    run.initial_curation = [curation('a1', [change('memory.strategy')], { 'memory.strategy': { factory: 'memory_impl:create' } }, {}, { diagnoses: [placed], grounds: { 'memory.strategy': ['material:service-sop'] } })]
    run.rounds[0].signals[0].text = 'Still wrong.\n\n---\n\n# Brand guide\n\nNavy.'
    const entries = timeline(run, revisions(run))
    expect(entries[0]).toMatchObject({ kind: 'onboarding', opening: run.opening })
    const [onboarding, second, failed] = replies(run)
    expect(onboarding.handover).toEqual([
      { ...sop, diagnosis: placed, targets: ['memory.strategy'] },
      { ...deck, diagnosis: null, targets: [] },
    ])
    expect([onboarding.pasted, second.handover, second.pasted]).toEqual([[], [], ['Brand guide']])
    expect(failed.handover).toEqual([])
  })
})

test('hard-wrapped prose joins back into paragraphs while lists, tables and code keep their lines', () => {
  const text = 'You are its\ntravel consultant.\n\n- collect the budget\n  and dates\n- quote from the list\n\n| a | b |\n| - | - |\n\n```\nkeep\nthis\n```'
  expect(unwrap(text)).toBe('You are its travel consultant.\n\n- collect the budget and dates\n- quote from the list\n\n| a | b |\n| - | - |\n\n```\nkeep\nthis\n```')
})
