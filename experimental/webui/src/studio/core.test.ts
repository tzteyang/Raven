/* The Studio's pure logic: the line diff, the prepared playbooks and Harness
   map, a recorded run read as a thread, a live session read from its record
   and its process's state with the steps one message stands for, the
   inspector's check for per-item verdicts reaching the Curator, and what the
   strategy-interaction records and the Curator's reads show. */

import { describe, expect, it } from 'vitest'

import { T } from './copy'
import { outputs, prepared, reads } from './curation'
import { counts, hunks, lineDiff } from './diff'
import { LOOSE, documents, harnessMap, layers, preparedPlaybooks, targetState } from './harness'
import { leaks } from './inspect'
import { closeRound, livePhase, liveThread, processes, sendRemark } from './live'
import { interventions, modelInputs, turnEvents } from './mechanisms'
import { observedOf, replayThread } from './replay'
import { versionAt } from './spy'

import type { Curation, Handover, Run, Signal } from '../model'
import type { LiveSnapshot, LiveState, StepReply } from './api'
import type { ProcessEntry, ScoreEntry, TrialsEntry } from './types'

/* The planning strategy compiles a playbook at prepare; the host check prepares a candidate twice, so the same spec
   is recorded twice. */
const book = {
  kind: 'strategy.setup',
  owner: 'planning',
  operation: 'playbook',
  value: {
    spec: {
      name: 'deck',
      nodes: [
        { id: 'research', subagent: 'Raven-Research', node_summary: 'check the facts', depends_on: [] },
        { id: 'brief', subagent: 'Raven', node_summary: 'write the brief', depends_on: ['research'] },
        { id: 'build', subagent: 'Raven-PPT', node_summary: 'build the deck', depends_on: ['research', 'brief'] },
      ],
    },
    requirements: {},
  },
}

const priceList: Handover = { name: 'price-list', kind: 'norm', files: ['uploads/price-list/price-list.md'] }

const signal = (text: string, items: { id: string; result: 'pass' | 'fail' }[] = [], attachments: Handover[] = [], source = 'agency'): Signal => ({
  source,
  text,
  items: items.map((item) => ({ ...item, session: 'family', expected: '', actual: '', note: '' })),
  metrics: {},
  satisfied: false,
  attachments,
})

const curation = (values: Record<string, unknown>, files: Record<string, string> = {}, children: Record<string, Record<string, unknown>> = {}): Curation =>
  ({
    file: 'c.json',
    changed: true,
    active_artifact_id: JSON.stringify(values).length.toString(),
    generated: {
      candidate: { plan: { understanding: 'u', design: 'd', changes: Object.keys(values).map((target) => ({ target, reason: 'r', expected: 'e', verification: 'v' })) }, artifact: { values, files } },
      validation: { errors: [], observations: [{}, {}] },
      trace: [{ event: 'model.call', stage: 'select' }, { event: 'query', stage: 'select' }, { event: 'model.call', stage: 'design' }],
    },
    revision: {
      root: { values, files },
      children: Object.fromEntries(Object.entries(children).map(([name, childValues]) => [name, { artifact: { values: childValues, files: {} }, plan: null }])),
    },
    feedback: { signals: [{ source: 'agency', text: 'remark', satisfied: false, attachments: [] }] },
  }) as unknown as Curation

function run(): Run {
  return {
    task_id: 't',
    task: 'the job',
    status: 'finished',
    stop: 'rounds exhausted',
    opening: [signal('here are the materials', [], [priceList])],
    initial_curation: [curation({ 'memory.strategy': { factory: 'memory_impl:create' } }, { 'memory_impl.py': 'one' })],
    rounds: [
      {
        sessions: { family: [{ user: 'hi', execution: { turn_id: 'x', artifact_id: '', records: [] } }] },
        signals: [signal('quote was wrong', [{ id: 'quote-correct', result: 'fail' }])],
        feedback: { decision: 'curate', reason: 'fix it', requirements: [], filtered: [], task_updates: [] },
        curated: true,
        analysis: [],
        curation: [curation({ 'memory.strategy': { factory: 'memory_impl:create' }, 'action.strategy': { factory: 'gate:create' } }, { 'memory_impl.py': 'one\ntwo', 'gate.py': 'code' }, { Raven: { 'action.strategy': { factory: 'child:create' } } })],
      },
      {
        sessions: { family: [{ user: 'again', execution: { turn_id: 'y', artifact_id: '', records: [] } }] },
        signals: [signal('better')],
        feedback: { decision: 'curate', reason: 'one more', requirements: [], filtered: [], task_updates: [] },
        curated: false,
        analysis: [],
        curation: [],
      },
    ],
  }
}

describe('line diff', () => {
  it('keeps common lines and marks the rest', () => {
    const lines = lineDiff('a\nb\nc', 'a\nc\nd')
    expect(lines.map((line) => `${line.op}${line.text}`)).toEqual([' a', '-b', ' c', '+d'])
    expect(counts(lines)).toEqual({ added: 1, removed: 1 })
  })

  it('folds long unchanged runs to their context', () => {
    const before = Array.from({ length: 20 }, (_, i) => `l${i}`).join('\n')
    const after = before.replace('l10', 'changed')
    const out = hunks(lineDiff(before, after), 2)
    expect(out.map((hunk) => hunk.kind)).toEqual(['fold', 'lines', 'fold'])
    expect(out[0]).toEqual({ kind: 'fold', count: 8 })
  })
})

describe('harness', () => {
  it('reads each playbook a candidate prepared once, with its layers, and lists what prepare did', () => {
    const observations = [
      book,
      { kind: 'strategy.setup', owner: 'memory', operation: 'profile', value: { 'agent_memory/profile/agent.md': 'rules' } },
      book,
      { kind: 'capability.registration', receipt: { kind: 'skill', name: 'price-list', status: 'staged' } },
      { kind: 'runtime.bound', targets: ['planning.strategy'] },
    ]
    const [deck, ...rest] = preparedPlaybooks(observations)
    expect(rest).toEqual([])
    expect(deck.nodes.map((node) => [node.id, node.subagent, node.summary, node.dependsOn])).toEqual([
      ['research', 'Raven-Research', 'check the facts', []],
      ['brief', 'Raven', 'write the brief', ['research']],
      ['build', 'Raven-PPT', 'build the deck', ['research', 'brief']],
    ])
    expect(layers(deck.nodes).map((layer) => layer.map((node) => node.id))).toEqual([['research'], ['brief'], ['build']])
    expect(prepared(observations)).toEqual([
      { owner: 'planning', operation: 'playbook', summary: 'deck · 3 nodes: research, brief, build' },
      { owner: 'memory', operation: 'profile', summary: 'agent_memory/profile/agent.md' },
      { owner: 'capability', operation: 'register', summary: 'skill · price-list · staged' },
    ])
  })

  it('treats a strategy target as its binding, the module it names and the files that module names', () => {
    const artifact = { values: { 'action.strategy': { factory: 'gate:create' } }, files: { 'gate.py': 'open("prompts/review.md")', 'prompts/review.md': 'review', 'other.md': 'x' } }
    expect(documents('action.strategy', artifact).map((doc) => doc.path)).toEqual(['action.strategy.json', 'gate.py', 'prompts/review.md'])
    expect(documents(LOOSE, artifact).map((doc) => doc.path)).toEqual(['other.md'])
    const before = { values: { 'action.strategy': { factory: 'gate:create' } }, files: { 'gate.py': 'open("prompts/review.md")', 'prompts/review.md': 'old' } }
    expect(targetState('action.strategy', before, artifact)).toBe('changed')
    expect(targetState(LOOSE, before, artifact)).toBe('new')
  })

  it('maps each harness and strategy with new, changed and kept targets, and the files no code names apart', () => {
    const before = { root: { values: { 'memory.strategy': { factory: 'm:create' }, 'capability.strategy': { factory: 'c:create' } }, files: { 'm.py': '1', 'c.py': 'c' } }, children: {} }
    const after = {
      root: { values: { 'memory.strategy': { factory: 'm:create' }, 'capability.strategy': { factory: 'c:create' } }, files: { 'm.py': '2', 'c.py': 'c', 'notes.md': 'n' } },
      children: { Raven: { values: { 'action.strategy': { factory: 'a:create' } }, files: { 'a.py': '' } } },
    }
    const rows = harnessMap(before, after, 'root')
    expect(rows.map((row) => row.scope)).toEqual(['root', 'Raven'])
    expect(rows[0].cells.memory).toEqual([{ target: 'memory.strategy', state: 'changed' }])
    expect(rows[0].cells.capability).toEqual([{ target: 'capability.strategy', state: 'kept' }])
    expect(rows[0].cells.other).toEqual([{ target: LOOSE, state: 'new' }])
    expect(rows[1].cells.action).toEqual([{ target: 'action.strategy', state: 'new' }])
  })
})

describe('replay', () => {
  const thread = replayThread('w/x', run())
  const cards = thread.entries.filter((entry): entry is ProcessEntry => entry.kind === 'process')

  it('cuts the loop where a person would: request, process card, trials of the version it installed', () => {
    expect(thread.entries.map((entry) => entry.kind)).toEqual(['head', 'request', 'process', 'trials', 'note', 'request', 'process', 'trials', 'note', 'request', 'process', 'note'])
    expect(thread.versions).toEqual(['v0', 'v1', 'v2'])
    expect(cards[0].onboarding).toBe(true)
    expect(cards[0].curation?.to).toBe('v1')
    expect(cards[1].curation?.from).toBe('v1')
    expect(cards[1].curation?.to).toBe('v2')
  })

  it('says the last round was not curated and why', () => {
    expect(cards[2].curation).toBeNull()
    expect(cards[2].footer).toEqual({ kind: 'last-round', version: 'v2' })
  })

  it('counts each stage of a scope from its trace', () => {
    const stages = cards[1].curation!.scopes[0].stages
    expect(stages.find((stage) => stage.id === 'select')).toMatchObject({ state: 'done', calls: 1, queries: 1 })
    expect(stages.find((stage) => stage.id === 'repair')?.state).toBe('skipped')
    expect(stages.find((stage) => stage.id === 'install')?.state).toBe('done')
  })

  it('carries the child harnesses the curation installed', () => {
    expect(Object.keys(cards[1].curation!.after.children)).toEqual(['Raven'])
    expect(cards[1].curation!.before.root.files['memory_impl.py']).toBe('one')
  })

  it('shows the attribution before the selection that grounded each target, and what the attribution spent', () => {
    const recorded = run()
    const generated = recorded.rounds[0].curation[0].generated!
    generated.candidate.attribution = { attribution: { diagnoses: [{ about: 'R1', state: 'not_exposed', mechanism: 'memory compose' }] }, identity: { model: 'm' }, record: 'a1.json' }
    generated.candidate.selection = { understanding: 'why', targets: ['memory.strategy'], grounds: { 'memory.strategy': ['R1'] } }
    recorded.rounds[0].attribution = [{ file: 'a1.json', calls: 8, queries: 24, subjects: ['R1'], identity: { model: 'm' }, attribution: { diagnoses: [] } }]
    const thread = replayThread('w/x', recorded)
    const scope = thread.entries.filter((entry): entry is ProcessEntry => entry.kind === 'process')[1].curation!.scopes[0]
    expect(scope.attribution?.diagnoses.map((diagnosis) => [diagnosis.about, diagnosis.state])).toEqual([['R1', 'not_exposed']])
    expect(scope.attribution?.identity).toEqual({ model: 'm' })
    expect(scope.stages[0]).toMatchObject({ id: 'diagnose', state: 'done', calls: 8, queries: 24 })
    expect(scope.selection?.grounds).toEqual({ 'memory.strategy': ['R1'] })
    expect(thread.recorded?.['1:R1']).toEqual({ state: 'not_exposed', changes: [{ target: 'memory.strategy', treatment: null }] })
  })

  it('stops a paused curation at the stage and in the harness its record names and keeps the version', () => {
    const recorded = run()
    const paused = { stage: 'design', scope: 'child/Raven-PPT', reason: 'the model call budget is spent', checkpoint: 'c' }
    recorded.rounds[0].curation = [{ file: 'p.json', paused, budget: { generation: { calls: 3, queries: 5 } } }]
    const card = replayThread('w/x', recorded).entries.filter((entry): entry is ProcessEntry => entry.kind === 'process')[1]
    expect(card.curation?.scopes[0].stages.map((stage) => stage.state)).toEqual(['done', 'done', 'paused', 'todo', 'todo', 'todo', 'todo'])
    expect(card.curation?.paused).toEqual({ stage: 'design', scope: 'child/Raven-PPT', reason: 'the model call budget is spent' })
    expect(card.curation?.budget).toEqual({ generation: { calls: 3, queries: 5 } })
    expect(card.footer).toEqual({ kind: 'paused', version: 'v1', stage: 'design', scope: 'child/Raven-PPT', reason: 'the model call budget is spent' })
    expect(T.stepPaused(T.stages.design, 'child/Raven-PPT')).toBe('Curation paused in child Harness Raven-PPT at "Design"')
    recorded.rounds[0].curation = [{ file: 'p.json', paused: { reason: 'select: a reason naming a stage is not read', checkpoint: 'c' } }]
    const unnamed = replayThread('w/x', recorded).entries.filter((entry): entry is ProcessEntry => entry.kind === 'process')[1]
    expect(unnamed.curation?.paused?.stage).toBeNull()
  })

  it('ends a round whose Curator reported a gap with its question', () => {
    const recorded = run()
    recorded.rounds[0].curation = []
    recorded.rounds[0].curated = false
    recorded.questions = [{ round: 1, stage: 'select', question: 'Which price list is current?' }]
    const card = replayThread('w/x', recorded).entries.filter((entry): entry is ProcessEntry => entry.kind === 'process')[1]
    expect(card.footer).toEqual({ kind: 'asked', version: 'v1', stage: 'select', question: 'Which price list is current?' })
  })

  it('reads the standard assessor as a scorecard and keeps held-out drills and their assessment apart', () => {
    const recorded = run()
    recorded.standard = { criteria: [{ id: 'C1', text: 'Quote from the list', source: 'declared', strength: 'must_hold', provenance: 'check:C1' }], derived_from: [] }
    recorded.rounds[0].signals.push(signal('', [{ id: 'C1', result: 'fail' }], [], 'standard'))
    recorded.rounds[0].holdout = { quiet: [{ user: 'hello', execution: { turn_id: 'h', artifact_id: '', records: [] } }] }
    recorded.rounds[0].holdout_signals = [signal('held-out remark', [{ id: 'C1', result: 'pass' }])]
    const entries = replayThread('w/x', recorded).entries
    const scores = entries.filter((entry): entry is ScoreEntry => entry.kind === 'score')
    expect(scores.map((entry) => [entry.round, entry.signal.source, entry.holdout, entry.criteria.length])).toEqual([[1, 'standard', false, 1], [1, 'agency', true, 1]])
    const heldOut = entries.find((entry): entry is TrialsEntry => entry.kind === 'trials' && !!entry.holdout)!
    expect(heldOut.trials.map((trial) => [trial.id, trial.holdout])).toEqual([['1:holdout:quiet', true]])
  })

  it('shows the trials of the round still in progress', () => {
    const recorded = run()
    recorded.status = 'running'
    recorded.stop = undefined
    recorded.pending = { sessions: { family: [{ user: 'third', execution: { turn_id: 'z', artifact_id: '', records: [] } }] } }
    const last = replayThread('w/x', recorded).entries.filter((entry): entry is TrialsEntry => entry.kind === 'trials').at(-1)!
    expect([last.round, last.pending, last.trials[0].status]).toEqual([3, true, 'running'])
  })
})

describe('live session', () => {
  const state = (values: Partial<LiveState> = {}): LiveState => ({
    step: null,
    since: 100,
    error: null,
    failed: null,
    status: 'running',
    onboarded: true,
    reviewing: false,
    outcome: null,
    rounds: 0,
    pending: { sessions: 0, signals: 0 },
    trial: null,
    assessor: false,
    ended: false,
    ...values,
  })
  const snapshot = (values: Partial<LiveSnapshot> = {}): LiveSnapshot => ({
    id: 'live-20260929120000-abcdef',
    title: 'Agency',
    task: 'the job',
    created: 1,
    archived: null,
    run: 'live-20260929120000-abcdef/r',
    status: 'running',
    models: { employee: 'deepseek/deepseek-flash' },
    attached: true,
    step: null,
    state: state(),
    busy: false,
    stamp: 's',
    progress: { curation: null, paused: null },
    ...values,
  })
  const fresh = (values: Partial<Run> = {}): Run => ({ task_id: 't', task: 'the job', status: 'running', opening: [], initial_curation: [], rounds: [], ...values })
  const progress = { started: 101, updated: 102, stage: 'select', calls: 3, queries: 5, checks: 0, repairs: 0, staged: [], events: [] }
  const inProgress = (): Run => ({
    ...run(),
    status: 'running',
    stop: undefined,
    pending: {
      sessions: { 'trial-1': [{ user: 'hello', execution: { turn_id: 'z', artifact_id: '', records: [] } }] },
      signals: [signal('ask the budget first', [], [], 'human')],
    },
  })

  it('reads a session before its onboarding as its head alone, and one that could not start with why', () => {
    const waiting = liveThread(snapshot({ state: state({ onboarded: false }) }), fresh())
    expect(waiting.entries.map((entry) => entry.kind)).toEqual(['head'])
    expect(waiting.entries[0]).toMatchObject({ baseline: T.liveBaseline, models: { employee: 'deepseek/deepseek-flash' } })
    expect(livePhase(waiting)).toEqual({ kind: 'onboard' })
    const broken = liveThread(snapshot({ run: null, state: state({ onboarded: false, failed: 'starting', error: 'ValueError: no key' }) }), null)
    expect(broken.entries.map((entry) => entry.kind)).toEqual(['head', 'note'])
    expect(livePhase(broken)).toEqual({ kind: 'unstarted', error: 'ValueError: no key' })
  })

  it('shows the onboarding curation under way from the Curator progress that belongs to it', () => {
    const onboarding = snapshot({ state: state({ onboarded: false, step: 'onboard' }), progress: { curation: progress, paused: null } })
    const session = liveThread(onboarding, fresh({ opening: [signal('here is the SOP', [], [priceList], 'human')] }))
    const card = processes(session)[0]
    expect([card.onboarding, card.curationState, card.footer]).toEqual([true, 'running', { kind: 'curating', version: 'v1' }])
    expect(card.progress).toEqual({ stage: 'select', calls: 3, queries: 5, scope: null })
    expect(session.entries[1]).toMatchObject({ kind: 'request', you: true, text: 'here is the SOP' })
    expect(livePhase(session)).toEqual({ kind: 'busy', step: 'onboard' })
    const stale = liveThread({ ...onboarding, progress: { curation: { ...progress, started: 50 }, paused: null } }, fresh())
    expect(processes(stale)[0].progress).toEqual({ stage: 'diagnose', calls: 0, queries: 0, scope: null })
  })

  it('holds the open trial beside the round in progress, with what the person said while the employee answers', () => {
    const trial = { name: 'trial-2', exchanges: [], said: 'Plan a trip', waiting: false }
    const session = liveThread(snapshot({ state: state({ step: 'trial', trial, pending: { sessions: 1, signals: 1 } }) }), inProgress())
    const pending = session.entries.find((entry): entry is TrialsEntry => entry.kind === 'trials' && !!entry.pending)!
    expect(pending.trials.map((item) => [item.id, item.title, item.status, !!item.busy])).toEqual([
      ['3:trial-1', 'Trial 1', 'done', false],
      ['3:trial-2', 'Trial 2', 'running', true],
    ])
    expect(pending.trials[1].exchanges.map((exchange) => exchange.user)).toEqual(['Plan a trip'])
    expect(session.entries.at(-1)).toMatchObject({ kind: 'request', you: true, text: 'ask the budget first' })
    expect(session.entries.some((entry) => entry.kind === 'note' && entry.tone === 'auto')).toBe(false)
    expect(session.current).toBe('v2')
    expect(livePhase(session)).toEqual({ kind: 'trial' })
    const between = liveThread(snapshot({ state: state({ pending: { sessions: 1, signals: 1 } }) }), inProgress())
    expect(livePhase(between)).toEqual({ kind: 'round', trials: 1, remarks: 1 })
  })

  it('shows the analysis under way with the remarks it reads', () => {
    const session = liveThread(snapshot({ state: state({ step: 'analyse', pending: { sessions: 1, signals: 1 } }) }), inProgress())
    const card = processes(session).at(-1)!
    expect([card.round, card.analysis, card.footer.kind, card.signals.map((item) => item.text)]).toEqual([3, 'running', 'analysing', ['ask the budget first']])
  })

  it('leaves a curation the Analyst asked for to the person, and names the stage a paused one stopped at', () => {
    const asked: Run = {
      ...fresh(),
      initial_curation: run().initial_curation,
      rounds: [{ ...run().rounds[0], curated: true, curation: [] }],
      pending: { review: { activity: [] } },
    }
    const review = liveThread(snapshot({ state: state({ reviewing: true, outcome: { next: 'curate', reason: '' } }) }), asked)
    expect(processes(review).at(-1)?.footer).toEqual({ kind: 'review', version: 'v1' })
    expect(livePhase(review)).toEqual({ kind: 'review' })
    const curating = liveThread(snapshot({ state: state({ reviewing: true, step: 'curate' }), progress: { curation: progress, paused: null } }), asked)
    expect(processes(curating).at(-1)).toMatchObject({ curationState: 'running', footer: { kind: 'curating', version: 'v2' } })
    const paused = liveThread(snapshot({ state: state({ reviewing: true, status: 'paused' }), progress: { curation: null, paused: 'design' } }), { ...asked, status: 'paused', stop: 'out of calls' })
    expect(processes(paused).at(-1)?.footer).toEqual({ kind: 'paused', version: 'v1', stage: 'design', scope: 'root', reason: 'out of calls' })
    expect(livePhase(paused)).toEqual({ kind: 'paused', step: 'curate' })
  })

  it('reads a session whose process is gone, one that ended and one that was archived', () => {
    const asked: Run = { ...fresh(), initial_curation: run().initial_curation, rounds: [{ ...run().rounds[0], curated: true, curation: [] }] }
    const gone = liveThread(snapshot({ attached: false, state: null }), asked)
    expect(processes(gone).at(-1)?.footer).toEqual({ kind: 'interrupted', version: 'v1' })
    expect(gone.entries.at(-1)).toMatchObject({ kind: 'note', key: 'detached', text: T.liveGone })
    expect(livePhase(gone)).toEqual({ kind: 'detached' })
    const finished = { ...run(), stop: 'archived as Agency v2' }
    expect(livePhase(liveThread(snapshot({ attached: false, state: null }), finished))).toEqual({ kind: 'ended' })
    const archived = liveThread(snapshot({ attached: false, archived: { name: 'Agency v2', version: 'v2' } }), finished)
    expect(archived.entries.filter((entry) => entry.kind === 'note').map((entry) => entry.key)).toEqual(['archive'])
    expect([archived.archived, livePhase(archived)]).toEqual([{ name: 'Agency v2', version: 'v2' }, { kind: 'archived' }])
  })

  it('sends a message as the steps it stands for, and stops the chain at a step that fails', async () => {
    const taken: [string, Record<string, unknown> | undefined][] = []
    const take = (sessions: number, refused = '') => async (op: string, body?: Record<string, unknown>): Promise<StepReply> => {
      taken.push([op, body])
      return op === refused ? { ok: false, error: 'no' } : { ok: true, state: state({ pending: { sessions, signals: 1 } }) }
    }
    const settle = async () => state()
    const ops = () => taken.splice(0).map(([op]) => op)
    await sendRemark(take(0), settle, { text: 'here is the SOP', materials: ['price-list'], onboarded: false, assess: true })
    expect(taken).toEqual([['onboard', { text: 'here is the SOP', materials: ['price-list'] }]])
    ops()
    await sendRemark(take(0), settle, { text: 'later', materials: [], onboarded: true, assess: true })
    expect(ops()).toEqual(['signal'])
    await sendRemark(take(1), settle, { text: 'fix the quote', materials: [], onboarded: true, assess: false })
    expect(ops()).toEqual(['signal', 'analyse'])
    await sendRemark(take(1), settle, { text: 'fix the quote', materials: [], onboarded: true, assess: true })
    expect(ops()).toEqual(['signal', 'assess', 'analyse'])
    expect((await sendRemark(take(1, 'signal'), settle, { text: 'x', materials: [], onboarded: true, assess: false })).ok).toBe(false)
    expect(ops()).toEqual(['signal'])
    const failed = await closeRound(take(1), async () => state({ failed: 'assess', error: 'boom' }), true)
    expect([ops(), failed.ok, failed.error]).toEqual([['assess'], false, 'boom'])
  })
})

describe('inspector', () => {
  it('finds a per-item verdict id in what the Curator was handed, as a key or a value', () => {
    const signals = [signal('text', [{ id: 'quote-correct', result: 'fail' }])]
    expect(leaks(signals, { signals: [{ text: 'remark' }], history: [] })).toEqual([])
    expect(leaks(signals, { history: [{ results: { agency: { 'quote-correct': 'fail' } } }] })).toEqual([
      { id: 'quote-correct', at: 'feedback.history[0].results.agency.quote-correct' },
    ])
  })
})

describe('strategy interactions', () => {
  const call = (id: string, stage: string, calls: string[], operation = 'handle_event') => ({
    kind: 'action.call',
    operation,
    arguments: [operation === 'handle_event' ? { event_id: id, kind: 'proposal', stage, calls: calls.map((name) => ({ name })) } : { request_id: id, command: { finish: true } }],
  })
  const result = (decision: Record<string, unknown>, operation = 'handle_event') => ({
    kind: 'action.result',
    operation,
    result: operation === 'handle_event' ? decision : { reply: { ready: true }, decision },
  })
  const receipt = (id: string, source: string, control: string, status: string) => ({
    kind: 'action.control',
    receipt: { control_id: id, source_id: source, control, status, reason: null },
  })

  it('counts a control once when its receipt is applied, and keeps a rejected one as evidence', () => {
    const records = [
      call('e1', 'dispatch', ['publish']),
      result({ control: 'reject', feedback: 'Verify first.' }),
      receipt('c1', 'e1', 'reject', 'applied'),
      { kind: 'runner.event', event_type: 'ToolEvent', event: { phase: 'complete', tool_call_id: 'p', result_preview: 'Action refused this call [c1]: Verify first.' } },
      call('r1', '', [], 'handle_request'),
      result({ control: 'finish', reply: 'Done.' }, 'handle_request'),
      receipt('c2', 'r1', 'finish', 'requested'),
      receipt('c2', 'r1', 'finish', 'applied'),
      call('e2', 'reply', []),
      result({ control: 'revise', feedback: 'Cite the source.' }),
      receipt('c3', 'e2', 'revise', 'requested'),
      receipt('c3', 'e2', 'revise', 'rejected'),
    ]
    const events = turnEvents(records)
    expect(events.map((event) => (event.kind === 'control' ? [event.control.control, event.control.status, event.control.detail, event.control.on] : event.kind))).toEqual([
      ['reject', 'applied', 'Verify first.', 'proposal · dispatch · publish'],
      ['finish', 'applied', 'Done.', 'request {"finish":true}'],
      ['revise', 'rejected', 'Cite the source.', 'proposal · reply'],
    ])
    expect(interventions(events)).toBe(2)
    const refused = [...records, { kind: 'runner.event', event_type: 'ToolEvent', event: { phase: 'complete', tool_call_id: 'g', result_preview: "Error: tool call 'publish' was refused by gate verify: check raised" } }]
    expect(turnEvents(refused).at(-1)).toMatchObject({ kind: 'refusal', hit: { kind: 'gate', mechanism: 'verify', tool: 'publish' } })
    expect(interventions(turnEvents(refused))).toBe(3)
  })

  it('lists guidance, peer requests, selections, registrations and what Memory did beside the controls', () => {
    const records = [
      { kind: 'action.result', operation: 'handle_event', result: { control: 'continue', guidance: 'Check the drive times.' } },
      { kind: 'planning.context', content: 'Step 2 of 4' },
      { kind: 'planning.context', content: 'Step 2 of 4' },
      { kind: 'memory.result', operation: 'initialize', result: { order: ['identity', 'memory'] } },
      { kind: 'memory.result', operation: 'compose', result: { messages: [] } },
      { kind: 'capability.result', operation: 'select', result: { tools: ['probe'], skills: [{ name: 'evidence' }] } },
      { kind: 'capability.result', operation: 'select', result: { tools: ['probe', 'read'], skills: [] } },
      { kind: 'capability.registration', receipt: { name: 'up', kind: 'skill', candidate: 'x', status: 'staged' } },
      { kind: 'capability.register', receipt: { name: 'up', kind: 'skill', candidate: 'x', status: 'staged' } },
      { kind: 'strategy.peer_request', target: 'memory', operation: 'interact', arguments: { text: 'NOTE' } },
      { kind: 'memory.result', operation: 'interact', result: { count: 1 } },
      { kind: 'strategy.peer_result', target: 'memory', operation: 'interact', result: { count: 1 } },
      { kind: 'memory.compaction', pressure: 'context', status: 'applied' },
      { kind: 'action.error', operation: 'handle_event', error: 'ValueError: bad' },
    ]
    expect(turnEvents(records)).toEqual([
      { kind: 'guidance', source: 'action', text: 'Check the drive times.' },
      { kind: 'guidance', source: 'planning', text: 'Step 2 of 4' },
      { kind: 'memory', operation: 'initialize', summary: 'identity › memory' },
      { kind: 'select', count: 2, tools: ['probe', 'read'], skills: ['evidence'] },
      { kind: 'register', name: 'up', what: 'skill', status: 'staged', reason: '' },
      { kind: 'peer', target: 'memory', operation: 'interact', request: '{"text":"NOTE"}', result: '{"count":1}' },
      { kind: 'memory', operation: 'compaction', summary: 'context · applied' },
      { kind: 'error', source: 'action.handle_event', text: 'ValueError: bad' },
    ])
    expect(interventions(turnEvents(records))).toBe(0)
  })

  it('pairs each assembled model input with the context estimate taken for it', () => {
    const inputs = modelInputs([
      { kind: 'memory.context', estimated_tokens: 900, allowance: 4000 },
      { kind: 'model.input', messages: { count: 3 } },
      { kind: 'provider.request', model: 'm' },
      { kind: 'model.input', messages: { count: 5 } },
    ])
    expect(inputs.map((input) => [input.row.kind, input.tokens, input.allowance])).toEqual([
      ['model.input', 900, 4000],
      ['model.input', null, null],
    ])
    expect(modelInputs([{ kind: 'provider.request', model: 'm' }]).map((input) => input.row.kind)).toEqual(['provider.request'])
  })

  it('rebuilds the observations a curation read: the cited turns for the root, and a child its own execution first', () => {
    const exchange = (user: string, records: Record<string, unknown>[]) => ({ user, execution: { turn_id: `turn-${user}`, artifact_id: 'a', records: records as never } })
    const requirement = (evidence: string[], observed = '') => ({ behavior: 'b', observed, evidence, expectation: 'unmet' as const, acceptance: 'a', strength: 'must_hold' as const })
    const round = {
      sessions: {
        family: [exchange('hi', [{ kind: 'model.input' }]), exchange('plan', [{ kind: 'child.execution', harness: 'Raven-PPT', records: [] }])],
        solo: [exchange('deck', [{ kind: 'dag.progress', records: [{ kind: 'child.execution', harness: 'Raven-PPT', records: [] }] }, { kind: 'child.execution', harness: 'Raven', records: [] }])],
        quiet: [exchange('skip', [])],
      },
      feedback: { decision: 'curate', reason: 'r', requirements: [requirement(['turn-hi', 'turn-deck: the deck was late']), requirement([], 'in turn-plan the plan skipped')], filtered: [], task_updates: [] },
    } as unknown as Parameters<typeof observedOf>[0]
    const current = { kind: 'current', session: '', turn: -1, user: '', label: 'execution.current' }
    const hi = { kind: 'turn', session: 'family', turn: 0, user: 'hi', label: 'session-7ae78d' }
    const plan = { kind: 'turn', session: 'family', turn: 1, user: 'plan', label: 'session-7ae78d' }
    const deck = { kind: 'turn', session: 'solo', turn: 0, user: 'deck', label: 'session-324d9f' }
    const labels = { family: 'session-7ae78d', solo: 'session-324d9f', quiet: 'session-c822b8' }
    expect(observedOf(round, labels)).toEqual({ root: [hi, plan, deck], children: { 'Raven-PPT': [current, plan, deck], Raven: [current, deck] } })
    expect(observedOf(round)?.root.map((observed) => observed.label)).toEqual(['', '', ''])
    const unheard = { ...round, feedback: null } as unknown as Parameters<typeof observedOf>[0]
    expect(observedOf(unheard)).toBeNull()
  })

  it('names the trial turn behind each observation the Curator read', () => {
    const observed = [
      { kind: 'turn' as const, session: 'family', turn: 0, user: 'hi', label: 'session-7ae78d' },
      { kind: 'turn' as const, session: 'family', turn: 1, user: 'plan it', label: 'session-7ae78d' },
    ]
    const trace = [
      { stage: 'select', event: 'model.call' },
      { stage: 'select', event: 'query', tool: 'read_observation', arguments: { index: 1, path: ['records', 4] }, result: { index: 1, text: '{"kind": "action.control"}' } },
      { stage: 'design', event: 'query', tool: 'read_source', arguments: { name: 'action', find: 'handle_event' }, result: { text: 'def handle_event' } },
      { stage: 'design', event: 'query', tool: 'read_fact', arguments: { name: 'targets', path: ['memory'] }, result: { error: 'no such path' } },
    ]
    expect(reads(trace, observed)).toEqual([
      { stage: 'select', tool: 'read_observation', target: '#1 · records.4', preview: '{"kind": "action.control"}', failed: false, observed: observed[1] },
      { stage: 'design', tool: 'read_source', target: 'action · “handle_event”', preview: 'def handle_event', failed: false, observed: null },
      { stage: 'design', tool: 'read_fact', target: 'targets · memory', preview: 'no such path', failed: true, observed: null },
    ])
  })
})

describe('version spy', () => {
  const versions = ['v0', 'v1', 'v2']

  it('shows the last version whose start has passed the reading line', () => {
    expect(versionAt(versions, [-900, 120, 800], 300, false)).toBe('v1')
    expect(versionAt(versions, [-900, -400, 250], 300, false)).toBe('v2')
    expect(versionAt(versions, [40, 700, 1600], 300, false)).toBe('v0')
  })

  it('shows the last version at the end of the transcript and skips a version with no start on the page', () => {
    expect(versionAt(versions, [-900, 120, 800], 300, true)).toBe('v2')
    expect(versionAt(versions, [-900, null, 800], 300, false)).toBe('v0')
    expect(versionAt([], [], 300, false)).toBeNull()
  })
})

describe('curator output', () => {
  it('lists the final plan, then each stage submission as recorded, keeping a staged file with its path', () => {
    const plan = { understanding: 'u', design: 'd', changes: [] }
    const trace = [
      { stage: 'select', event: 'model.call', call: 1 },
      { stage: 'select', event: 'submit_selection', output: { understanding: 'u', targets: ['action.strategy'] } },
      { stage: 'select', event: 'query', tool: 'read_source', arguments: {}, result: {} },
      { stage: 'design', event: 'submit_plan', output: plan },
      { stage: 'implement', event: 'file.staged', path: 'a.py', result: { staged: 'a.py', chars: 10 } },
      { stage: 'validate', event: 'validation', errors: [], observations: [] },
    ]
    expect(outputs(trace, plan)).toEqual([
      { stage: '', event: 'candidate.plan', value: plan },
      { stage: 'select', event: 'submit_selection', value: { understanding: 'u', targets: ['action.strategy'] } },
      { stage: 'design', event: 'submit_plan', value: plan },
      { stage: 'implement', event: 'file.staged', value: { path: 'a.py', result: { staged: 'a.py', chars: 10 } } },
      { stage: 'validate', event: 'validation', value: { errors: [], observations: [] } },
    ])
    expect(outputs([], null)).toEqual([])
  })
})
