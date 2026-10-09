/* A cultivated run for tests: onboarding and three rounds, the last revision failing on its budget. */

import type { Change, Curation, Diagnosis, Exchange, Feedback, Generated, RecordRow, Round, Run, Selection } from './model'

export const change = (target: string, treatment: Change['treatment'] = 'add'): Change => ({ target, treatment, reason: `why ${target}`, expected: `expect ${target}`, verification: '' })

export const identity = { implementation: 'model', prompts: 'abc123def456', model: 'deepseek/deepseek-flash', catalogue: true }

export function curation(id: string, changes: Change[], values: Record<string, unknown> = {}, files: Record<string, string> = {}, chosen?: { diagnoses: Diagnosis[]; grounds: Selection['grounds'] }): Curation {
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

export const turn = (artifact: string, records: RecordRow[] = []): Exchange => ({
  user: 'Hello',
  execution: { turn_id: `t-${artifact}`, artifact_id: artifact, records },
})

export const feedback = (decision: Feedback['decision']): Feedback => ({
  decision,
  reason: `because ${decision}`,
  requirements: decision === 'curate'
    ? [{ id: 'R1', situation: 'When a guest asks for a price', behavior: 'Quote only after confirming', observed: 'Quoted early', evidence: ['t-1'], expectation: 'unmet', acceptance: 'No price before confirmation', strength: 'must_hold', recurrence: 2 }]
    : [],
  filtered: [],
  task_updates: [],
})

export const round = (sessions: Round['sessions'], decision: Feedback['decision'] | null, curations: Curation[] = []): Round => ({
  sessions,
  signals: [{ source: 'agency', text: `remark ${decision}`, items: [], metrics: {}, satisfied: false }],
  feedback: decision ? feedback(decision) : null,
  curated: decision === 'curate',
  analysis: [],
  curation: curations,
})

export const planning = { kind: 'planning.call', operation: 'view' }

export function cultivated(): Run {
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
