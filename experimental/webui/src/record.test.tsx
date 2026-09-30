import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, test, vi } from 'vitest'

import {
  chainLabel, changesOf, columns, costLabel, evidenceCount, groupCurations, handedAfter, landed, ledgerMatrix, mechanismOf, modelLine,
  normalizeRecord, quotesOf, requirementsOf, roundSummaries, settle, statusOf, versionLabel,
} from './record'
import { RecordView } from './views/Record'

import type { LedgerRow } from './record'

const A1 = '1'.repeat(64)
const A2 = '2'.repeat(64)

const raw = {
  schema: 1,
  run: {
    name: 'staged-01',
    record_id: 'e5618b30afab4ceb8daf205a2c3bed6d',
    status: 'error',
    error: 'stopped by the suite: spend passed the $40 budget',
    chain: 'staged',
    settings: { chain: 'staged', models: { employee: 'deepseek/deepseek-flash', curator: 'deepseek/deepseek-flash', analyst: 'deepseek/deepseek-flash', subagents: 'z-ai/glm-5.3' }, rounds: 3 },
    revisions: ['198e3eca4c09a1a8be51', A1, A2],
    suite: { status: 'error', stopped: 'spend passed the $40 budget', notes: [] },
    warnings: [],
    reproduce: 'uv run python -m experimental.simulation --chain staged',
  },
  inputs: {
    profile: 'Harbour Light Travel',
    onboarding: 'Welcome aboard.',
    materials: [{ name: 'price-list', sha256: 'a'.repeat(64), given: 'opening' }, { name: 'brand-design-guide', sha256: 'b'.repeat(64), given: 'handed_over', round: 2 }],
    cards: [{ name: 'student', sha256: 'c'.repeat(64) }],
    baseline: { 'AGENTS.md': 'd'.repeat(64) },
  },
  curations: [
    { id: 'c0', round: 0, scope: 'root', understanding: 'The shop sells three packages.', changes: [{ target: 'memory.prompt', facet: 'memory', reason: 'Introduce the assistant as the AI consultant.', expected: 'First message says AI.' }], artifact_diff: [{ target: 'memory.prompt', path: 'AGENTS.md', change: 'modified', lines_added: 3, lines_removed: 0, diff: '--- a/AGENTS.md\n+++ b/AGENTS.md\n@@ -1 +1,3 @@\n+You are the AI consultant.' }], outcome: 'installed', error: null },
    {
      id: 'c1', round: 1, scope: 'root', understanding: 'Quotes must come from the price list.',
      changes: [
        { target: 'planning.strategy', facet: 'planning', treatment: 'add', reason: 'Hold the confirmed intake and the quote version.', expected: 'No quote before intake is confirmed.', addresses: ['R1'] },
        { target: 'action.review', facet: 'action', reason: 'Recompute every quoted total against the list.', expected: 'A wrong total is sent back.' },
      ],
      artifact_diff: [
        { target: 'planning.strategy', path: 'planning/consultation.py', change: 'added', lines_added: 40, lines_removed: 0, diff: '+class Consultation:\n+    pass' },
        { target: 'action.review', path: 'action/quote_gate.py', change: 'added', lines_added: 22, lines_removed: 0, diff: '+def review(draft, plan):\n+    return None' },
      ],
      outcome: 'installed', error: null,
    },
    { id: 'c1b', round: 1, scope: 'Raven-PPT', understanding: 'The deck must use the agency template.', changes: [{ target: 'capability.subagent_homes', reason: 'Tell the deck harness about the template.', expected: 'Decks on HL-MKT-TPL-08.' }], artifact_diff: [{ target: 'capability.subagent_homes', path: 'Raven-PPT/user_memory/profile/user.md', change: 'modified', lines_added: 5, lines_removed: 1, diff: '-old\n+Use HL-MKT-TPL-08.' }], outcome: 'installed', error: null },
    { id: 'c2', round: 2, scope: 'root', understanding: '', changes: [{ target: 'memory.prompt', facet: 'memory', reason: 'Never mention tools (G8).' }], artifact_diff: [], outcome: 'rejected', error: 'validation: authored content changed outside curation', validation: { errors: ['authored content changed outside curation'] } },
  ],
  rounds: [
    {
      number: 1, revision: A1,
      drills: [{ session: 'student-1', card: 'student', exchanges: [{ turn: 1, customer: 'Hi', assistant: 'The Value package is 2,980 per person.', delivered: [], playbook_runs: [] }] }],
      evaluation: { remark: 'Quotes were wrong.', items: [
        { criterion: 'quote-sheet-correct', severity: 'red_line', result: 'fail', session: 'student-1', actual: 'Total 5,000 yuan', note: 'The list says 5,960.' },
        { criterion: 'quote-sheet-correct', severity: 'red_line', result: 'fail', session: 'student-1', actual: '', note: 'Second quote also off.' },
        { criterion: 'ai-identity-disclosed', severity: 'red_line', result: 'pass', session: 'student-1' },
        { criterion: 'deck-template-and-brand', severity: 'standard', result: 'fail', session: 'student-1', actual: 'Plain white slides', note: '' },
        { criterion: 'no-internal-chatter', severity: 'standard', result: 'pass', session: 'student-1' },
      ], metrics: {} },
      analysis: { decision: 'curate', reason: 'Two gaps.', requirements: [
        { id: 'R1', situation: 'A student group asks for a quote.', behavior: 'Quote only from the price list.', observed: 'Totals were off twice.', evidence: ['student-1 turn 1'], acceptance: 'Every total matches.', strength: 'must_hold', recurrence: 0, grounds: ['check:quote-sheet-correct', 'case:q7'], criteria: ['quote-sheet-correct'], cases: ['q7'], link: 'grounds', held: true },
        { id: 'R2', behavior: 'Build decks on the agency template.', observed: 'Plain slides.', evidence: [], acceptance: 'Template used.', strength: 'should', repeats: 'R0', grounds: ['assessor:agency'], criteria: ['deck-template-and-brand'], cases: [], link: 'reading', held: null },
      ] },
      mechanism_evidence: [],
      curation: 'c1',
    },
    {
      number: 2, revision: A2,
      drills: [{ session: 'student-1', card: 'student', exchanges: [] }],
      evaluation: { items: [
        { criterion: 'quote-sheet-correct', severity: 'red_line', result: 'pass', session: 'student-1' },
        { criterion: 'ai-identity-disclosed', severity: 'red_line', result: 'pass', session: 'student-1' },
        { criterion: 'deck-template-and-brand', severity: 'standard', result: 'fail', session: 'student-1' },
        { criterion: 'deck-template-and-brand', severity: 'standard', result: 'pass', session: 'student-2' },
        { criterion: 'no-internal-chatter', severity: 'standard', result: 'fail', session: 'student-1', actual: 'Let me check my tools.' },
      ] },
      analysis: { decision: 'curate', reason: '', requirements: [] },
      mechanism_evidence: [
        { kind: 'participant', target: 'action.review', decision: 'resample', session: 'student-1', turn: 3, count: 2, intervention: true, summary: 'The quoted total did not match the list.' },
        { kind: 'planning', target: 'planning.strategy', decision: 'advance', session: 'student-1', turn: 2, count: 1, intervention: false, summary: 'Intake confirmed.' },
        { kind: 'hosting', target: 'capability.subagent_homes', decision: 'read', session: 'student-1', turn: 5, count: 1, intervention: false, summary: 'Raven-PPT read user.md.' },
        { kind: 'participant', target: 'action.review', decision: 'resample', session: 'professional-1', turn: 2, count: 1, intervention: true, summary: 'Another drill.' },
      ],
      curation: 'c2',
    },
    {
      number: 3, revision: A2, partial: true,
      drills: [],
      evaluation: { items: [
        { criterion: 'quote-sheet-correct', severity: 'red_line', result: 'pass', session: 'student-1' },
        { criterion: 'ai-identity-disclosed', severity: 'red_line', result: 'pass', session: 'student-1' },
        { criterion: 'deck-template-and-brand', severity: 'standard', result: 'fail', session: 'student-1' },
        { criterion: 'no-internal-chatter', severity: 'standard', result: 'unknown', session: 'student-1' },
      ] },
      analysis: null,
      mechanism_evidence: [{ kind: 'participant', target: 'action.review', decision: 'resample', session: 'student-1', turn: 4, count: 2, intervention: true, summary: 'Sent back twice.' }],
      curation: null,
    },
  ],
  ledger: [
    {
      criterion: 'deck-template-and-brand', severity: 'standard', rule: 'The deck is built on the agency template.',
      timeline: [
        { round: 0, result: 'unknown', fails: 0, passes: 0, requirements: [], changes: [], evidence: {} },
        { round: 1, result: 'fail', fails: 1, passes: 0, requirements: [1], changes: [{ curation: 'c1b', scope: 'Raven-PPT', target: 'capability.subagent_homes', facet: 'capability', paths: ['Raven-PPT/user_memory/profile/user.md'], outcome: 'installed', link: 'addresses' }], evidence: {} },
        { round: 2, result: 'mixed', fails: 1, passes: 1, requirements: [], changes: [], evidence: { 'hosting/read': 1 } },
        { round: 3, result: 'fail', fails: 1, passes: 0, requirements: [], changes: [], evidence: {} },
      ],
      sedimented_in: [{ round: 1, scope: 'Raven-PPT', facet: 'capability', target: 'capability.subagent_homes', paths: ['Raven-PPT/user_memory/profile/user.md'] }],
      status: 'still_failing',
    },
    {
      criterion: 'quote-sheet-correct', severity: 'red_line', rule: 'Every quote is a complete quote sheet from the price-list.',
      timeline: [
        { round: 0, result: 'unknown', fails: 0, passes: 0, requirements: [], changes: [], evidence: {} },
        { round: 1, result: 'fail', fails: 2, passes: 0, requirements: [0], changes: [
          { curation: 'c1', scope: 'root', target: 'planning.strategy', facet: 'planning', paths: ['planning/consultation.py'], outcome: 'installed', link: 'addresses' },
          { curation: 'c1', scope: 'root', target: 'action.review', facet: 'action', paths: ['action/quote_gate.py'], outcome: 'installed', link: 'addresses' },
        ], evidence: {} },
        { round: 2, result: 'pass', fails: 0, passes: 1, requirements: [], changes: [], evidence: { 'participant/resample': 2, 'planning/advance': 1 } },
        { round: 3, result: 'pass', fails: 0, passes: 1, requirements: [], changes: [], evidence: { 'participant/resample': 2 } },
      ],
      sedimented_in: [
        { round: 1, scope: 'root', facet: 'planning', target: 'planning.strategy', paths: ['planning/consultation.py'] },
        { round: 1, scope: 'root', facet: 'action', target: 'action.review', paths: ['action/quote_gate.py'] },
      ],
      status: 'held_since_round_2',
    },
    {
      criterion: 'ai-identity-disclosed', severity: 'red_line', rule: 'The first message says it is the AI consultant.',
      timeline: [
        { round: 0, result: 'unknown', fails: 0, passes: 0, requirements: [], changes: [{ curation: 'c0', scope: 'root', target: 'memory.prompt', facet: 'memory', paths: ['AGENTS.md'], outcome: 'installed', link: 'addresses' }], evidence: {} },
        { round: 1, result: 'pass', fails: 0, passes: 1, requirements: [], changes: [], evidence: {} },
        { round: 2, result: 'pass', fails: 0, passes: 1, requirements: [], changes: [], evidence: {} },
        { round: 3, result: 'pass', fails: 0, passes: 1, requirements: [], changes: [], evidence: {} },
      ],
      sedimented_in: [{ round: 0, scope: 'root', facet: 'memory', target: 'memory.prompt', paths: ['AGENTS.md'] }],
      status: 'never_failed',
    },
    {
      criterion: 'no-internal-chatter', severity: 'standard', rule: 'Never talk about tools (G8).',
      timeline: [
        { round: 0, result: 'unknown', fails: 0, passes: 0, requirements: [], changes: [], evidence: {} },
        { round: 1, result: 'pass', fails: 0, passes: 1, requirements: [], changes: [], evidence: {} },
        { round: 2, result: 'fail', fails: 1, passes: 0, requirements: [], changes: [{ curation: 'c2', scope: 'root', target: 'memory.prompt', facet: 'memory', paths: [], outcome: 'rejected', link: 'addresses' }], evidence: {} },
        { round: 3, result: 'unknown', fails: 0, passes: 0, requirements: [], changes: [], evidence: {} },
      ],
      sedimented_in: [],
      status: 'still_failing',
    },
    {
      criterion: 'deck-aesthetics', severity: 'standard', rule: 'Roughly 60/30/10 cream, lake blue and amber.',
      timeline: [0, 1, 2, 3].map((round) => ({ round, result: 'unknown', fails: 0, passes: 0, requirements: [], changes: [], evidence: {} })),
      sedimented_in: [],
      status: 'not_exercised',
    },
  ],
  cost: { total: 38.456, by_part: { simulation: 4.1, employee: 2.2, subagents: 32.156 }, source: 'suite-summary.json' },
}

const record = normalizeRecord(raw)
const row = (criterion: string): LedgerRow => record.ledger.find((item) => item.criterion === criterion)!

describe('the record as read', () => {
  it('fills every list and names the root scope when the builder leaves them out', () => {
    const bare = normalizeRecord({ run: { name: 'x' }, curations: [{ id: 'c', round: 2, changes: [{ target: 'action.review' }] }], ledger: [{ criterion: 'a', timeline: [{ round: 1, changes: [{ target: 'memory.prompt' }] }] }] })
    expect(bare.rounds).toEqual([])
    expect(bare.inputs.materials).toEqual([])
    expect(bare.run.revisions).toEqual([])
    expect(bare.cost).toBeNull()
    expect(bare.value).toBeNull()
    expect(bare.curations[0].scope).toBe('root')
    expect(bare.curations[0].artifact_diff).toEqual([])
    expect(bare.ledger[0].timeline[0].changes[0]).toEqual({ curation: '', scope: 'root', target: 'memory.prompt', facet: undefined, paths: [] })
    expect(normalizeRecord(null).ledger).toEqual([])
  })

  it("keeps each requirement's id, grounds and whether it held, and each change's treatment and addresses", () => {
    const [first, second] = record.rounds[0].analysis!.requirements
    expect([first.id, first.situation, first.grounds, first.cases, first.link, first.held]).toEqual(['R1', 'A student group asks for a quote.', ['check:quote-sheet-correct', 'case:q7'], ['q7'], 'grounds', true])
    expect([second.id, second.repeats, second.held, second.link, second.criteria]).toEqual(['R2', 'R0', null, 'reading', ['deck-template-and-brand']])
    const planned = record.curations.find((curation) => curation.id === 'c1')!.changes
    expect(planned.map((change) => [change.target, change.treatment ?? null, change.addresses])).toEqual([['planning.strategy', 'add', ['R1']], ['action.review', null, []]])
  })

  it('labels chains, models, handovers and cost from any shape', () => {
    expect(chainLabel('staged')).toBe('staged')
    expect(chainLabel(['documents', 'by-stage'])).toBe('documents / by-stage')
    expect(chainLabel({ label: 'examples' })).toBe('examples')
    expect(chainLabel(null)).toBe('')
    expect(modelLine(record.run.settings.models)).toBe('employee & curator deepseek/deepseek-flash · sub-harness z-ai/glm-5.3')
    expect(modelLine({ employee: 'z-ai/glm-5.3-flashx', curator: 'z-ai/glm-5.3' }, true)).toBe('employee glm-5.3-flashx · curator glm-5.3 · sub-harness default')
    expect(modelLine({})).toBe('')
    expect(handedAfter(record, 2)).toEqual(['brand-design-guide'])
    expect(handedAfter(record, 1)).toEqual([])
    expect(costLabel(38.456)).toBe('$38.46')
  })

  it('counts evidence from numbers, lists and objects of either', () => {
    expect(evidenceCount(3)).toBe(3)
    expect(evidenceCount([{}, {}])).toBe(2)
    expect(evidenceCount({ 'action.review': 2, rows: [1, 2, 3] })).toBe(5)
    expect(evidenceCount({})).toBe(0)
    expect(evidenceCount(undefined)).toBe(0)
  })
})

describe('the ledger matrix', () => {
  const matrix = ledgerMatrix(record)

  it('has an onboarding column before the rounds, each round with the version its drills ran on', () => {
    expect(columns(record).map((column) => [column.round, column.label, column.revision, column.partial])).toEqual([
      [0, 'Onboarding', null, false], [1, 'Round 1', 'v1', false], [2, 'Round 2', 'v2', false], [3, 'Round 3', 'v2', true],
    ])
    expect(versionLabel(record, '198e3eca4c09a1a8be51c0ffee')).toBe('v0')
    expect(versionLabel(record, 'f'.repeat(64))).toBe('ffffffff')
    expect(versionLabel(record, null)).toBeNull()
  })

  it('puts red lines first, keeps the builder order within each group and sets aside rules nothing touched', () => {
    expect(matrix.rows.map((item) => [item.row.criterion, item.red])).toEqual([
      ['quote-sheet-correct', true], ['ai-identity-disclosed', true], ['deck-template-and-brand', false], ['no-internal-chatter', false],
    ])
    expect(matrix.quiet.map((item) => item.row.criterion)).toEqual(['deck-aesthetics'])
  })

  it('marks each cell with its verdict, the requirements raised, the changes landed and the mechanisms fired', () => {
    const quote = matrix.rows[0].cells
    expect(quote.map((cell) => cell.tone)).toEqual(['none', 'fail', 'pass', 'pass'])
    expect(quote[1].requirements).toBe(1)
    expect(quote[1].landed).toEqual([
      { facet: 'planning', scope: 'root', targets: ['planning.strategy'], installed: true },
      { facet: 'action', scope: 'root', targets: ['action.review'], installed: true },
    ])
    expect(quote.map((cell) => cell.fired)).toEqual([0, 0, 3, 2])
    const deck = matrix.rows[2].cells
    expect(deck.map((cell) => cell.tone)).toEqual(['none', 'fail', 'mixed', 'fail'])
    expect(deck[1].landed).toEqual([{ facet: 'capability', scope: 'Raven-PPT', targets: ['capability.subagent_homes'], installed: true }])
    expect(deck[2].fired).toBe(1)
    const identity = matrix.rows[1].cells
    expect(identity[0].landed).toEqual([{ facet: 'memory', scope: 'root', targets: ['memory.prompt'], installed: true }])
    expect(identity[1].requirements).toBe(0)
    const chatter = matrix.rows[3].cells
    expect(chatter.map((cell) => cell.tone)).toEqual(['none', 'pass', 'fail', 'unknown'])
    expect(chatter[2].landed).toEqual([{ facet: 'memory', scope: 'root', targets: ['memory.prompt'], installed: false, outcome: 'rejected' }])
  })

  it('folds changes to one chip per scope, facet and outcome, installed and root first', () => {
    const chips = landed([
      { curation: 'b', scope: 'Raven-PPT', target: 'capability.subagent_homes', paths: [] },
      { curation: 'a', scope: 'root', target: 'action.tool_gates', paths: [], outcome: 'error' },
      { curation: 'a', scope: 'root', target: 'action.review', paths: [] },
      { curation: 'a', scope: 'root', target: 'action.hooks', facet: 'action', paths: [] },
      { curation: 'a', scope: 'root', target: 'prompt.resources', paths: [] },
    ])
    expect(chips.map((chip) => [chip.scope, chip.facet, chip.targets, chip.installed])).toEqual([
      ['root', 'action', ['action.review', 'action.hooks'], true],
      ['root', 'other', ['prompt.resources'], true],
      ['Raven-PPT', 'capability', ['capability.subagent_homes'], true],
      ['root', 'action', ['action.tool_gates'], false],
    ])
  })

  it('says where each rule stands in the record\'s words, with what the verdicts add', () => {
    expect(matrix.rows.map((item) => [item.settle.text, item.settle.tone, item.settle.note])).toEqual([
      ['held since round 2', 'pass', ''],
      ['never failed', 'pass', ''],
      ['still failing', 'fail', ''],
      ['still failing', 'fail', 'regressed in round 2'],
    ])
    expect(statusOf('held_since_round_3')).toEqual({ tone: 'pass', text: 'held since round 3' })
    expect(statusOf('not_exercised')).toEqual({ tone: 'unknown', text: 'not exercised' })
    const bare = (timeline: LedgerRow['timeline']): LedgerRow => ({ criterion: 'x', timeline, sedimented_in: [] })
    expect(settle(bare([{ round: 1, result: 'fail', changes: [] }])).text).toBe('still failing, nothing sedimented')
    expect(settle({ ...bare([{ round: 1, result: 'fail', changes: [] }]), status: 'still_failing' })).toEqual({ tone: 'fail', text: 'still failing', note: 'nothing sedimented' })
    expect(settle(bare([{ round: 1, fails: 1, passes: 1, changes: [] }])).text).toBe('mixed in round 1')
    expect(settle(bare([{ round: 1, result: 'pass', changes: [] }, { round: 2, result: 'fail', changes: [] }, { round: 3, result: 'pass', changes: [] }])).text).toBe('held since round 3')
    expect(settle(bare([])).text).toBe('not judged yet')
  })
})

describe('the chain of evidence behind a cell', () => {
  it('takes requirements by index, and matches them by criterion when the ledger names none', () => {
    expect(requirementsOf(record, 'quote-sheet-correct', row('quote-sheet-correct').timeline[1], 1).rows.map((item) => item.behavior)).toEqual(['Quote only from the price list.'])
    const matched = requirementsOf(record, 'deck-template-and-brand', undefined, 1)
    expect(matched.source).toBe('matched')
    expect(matched.rows.map((item) => item.behavior)).toEqual(['Build decks on the agency template.'])
  })

  it('links each change to its curation, planned reason and the diffs of the paths it names', () => {
    const links = changesOf(record, row('quote-sheet-correct').timeline[1], row('quote-sheet-correct'), 1)
    expect(links.map((link) => [link.change.target, link.change.link, link.plan?.reason, link.diffs.map((diff) => diff.path)])).toEqual([
      ['planning.strategy', 'addresses', 'Hold the confirmed intake and the quote version.', ['planning/consultation.py']],
      ['action.review', 'addresses', 'Recompute every quoted total against the list.', ['action/quote_gate.py']],
    ])
    const onboarding = changesOf(record, row('ai-identity-disclosed').timeline[0], row('ai-identity-disclosed'), 0)
    expect(onboarding.map((link) => [link.curation?.id, link.diffs.map((diff) => diff.path)])).toEqual([['c0', ['AGENTS.md']]])
    const withModule = normalizeRecord({
      ...raw,
      curations: [{ ...raw.curations[1], artifact_diff: [...raw.curations[1].artifact_diff, { target: 'files', path: 'gates/quote.py', change: 'added', lines_added: 9, lines_removed: 0, diff: '+x' }] }],
    })
    const moduleLinks = changesOf(withModule, { round: 1, changes: [{ curation: 'c1', scope: 'root', target: 'action.review', paths: ['action/quote_gate.py', 'gates/quote.py'] }] }, undefined, 1)
    expect(moduleLinks[0].diffs.map((diff) => diff.path)).toEqual(['action/quote_gate.py', 'gates/quote.py'])
    const fromSediment = changesOf(record, undefined, row('ai-identity-disclosed'), 0)
    expect(fromSediment.map((link) => [link.curation?.id, link.plan?.reason])).toEqual([['c0', 'Introduce the assistant as the AI consultant.']])
  })

  it('keeps the ledger\'s counts and shows the round\'s rows for targets in force, from the drills the verdicts name', () => {
    const quote = row('quote-sheet-correct')
    const second = mechanismOf(record, quote, quote.timeline[2], 2)
    expect([second.source, second.count]).toEqual(['matched', 3])
    expect(second.rows.map((item) => [item.target, item.session])).toEqual([['action.review', 'student-1'], ['planning.strategy', 'student-1']])
    const third = mechanismOf(record, quote, quote.timeline[3], 3)
    expect([third.count, third.rows.length]).toEqual([2, 1])
    const listed = mechanismOf(record, quote, { ...quote.timeline[2], evidence: { rows: [0, 2] } }, 2)
    expect([listed.source, listed.count, listed.rows.map((item) => item.kind)]).toEqual(['ledger', 2, ['participant', 'hosting']])
    const deck = row('deck-template-and-brand')
    expect(mechanismOf(record, deck, deck.timeline[2], 2).rows.map((item) => item.target)).toEqual(['capability.subagent_homes'])
    expect(mechanismOf(record, deck, deck.timeline[1], 1).rows).toEqual([])
  })

  it('quotes the failing drills first, with the last reply when the verdict quotes nothing', () => {
    const quotes = quotesOf(record, 'quote-sheet-correct', 1)
    expect(quotes.map((quote) => [quote.tone, quote.item.actual, quote.card])).toEqual([['fail', 'Total 5,000 yuan', 'student'], ['fail', '', 'student']])
    expect(quotes[1].reply).toBe('The Value package is 2,980 per person.')
    expect(quotesOf(record, 'deck-template-and-brand', 2).map((quote) => quote.tone)).toEqual(['fail', 'pass'])
  })
})

describe('curations and rounds', () => {
  it('group curations by the round they answered, onboarding first and the root harness before children', () => {
    expect(groupCurations(record.curations).map((group) => [group.round, group.scopes.map((scope) => [scope.scope, scope.curations.map((item) => item.id)])])).toEqual([
      [null, [['root', ['c0']]]],
      [1, [['root', ['c1']], ['Raven-PPT', ['c1b']]]],
      [2, [['root', ['c2']]]],
    ])
  })

  it('summarise each round in one line: verdicts, decision, curation outcome by scope and handovers', () => {
    const [onboarding, first, second, third] = roundSummaries(record)
    expect(onboarding.round).toBeNull()
    expect(onboarding.curations).toEqual([{ scope: 'root', outcome: 'installed', facets: ['memory'], error: null }])
    expect([first.revision, first.pass, first.fail, first.redFailed, first.decision, first.requirements]).toEqual(['v1', 2, 3, 2, 'curate', 2])
    expect(first.curations.map((item) => [item.scope, item.outcome, item.facets])).toEqual([['root', 'installed', ['planning', 'action']], ['Raven-PPT', 'installed', ['capability']]])
    expect([second.fired, second.interventions, second.handed]).toEqual([5, 3, ['brand-design-guide']])
    expect([second.curations[0].outcome, second.curations[0].error]).toEqual(['rejected', 'validation: authored content changed outside curation'])
    expect([third.decision, third.curations, third.unknown, third.partial, third.interventions]).toEqual([null, [], 1, true, 2])
  })
})

afterEach(cleanup)

const reply = (status: number, body: unknown) => ({ ok: status < 400, status, json: async () => body })

test('the record view shows the header, the ledger and a cell\'s chain of evidence', async () => {
  vi.stubGlobal('fetch', vi.fn(async (path: string) => (
    path.startsWith('/api/record/export')
      ? reply(200, { folder: '/runs/staged-01/record', bundle: { name: 'bundle-1', path: '/runs/staged-01/record/bundle-1', kind: 'folder', modified: 1, size: 10, count: 2, files: ['README.md', 'record.json'] } })
      : reply(200, raw)
  )))
  const trial = vi.fn()
  render(<RecordView runId="staged-01/r" live={false} onTrial={trial} onRemark={() => undefined} />)
  expect(await screen.findByText('Knowledge-sedimentation ledger')).toBeTruthy()
  expect(screen.getByText('staged', { selector: 'code.chainv' })).toBeTruthy()
  expect(screen.getByText('employee & curator deepseek/deepseek-flash · sub-harness z-ai/glm-5.3')).toBeTruthy()
  expect(screen.getByText('$38.46')).toBeTruthy()
  expect(screen.getByText('spend passed the $40 budget')).toBeTruthy()
  expect(screen.getByText('/runs/staged-01/record/bundle-1')).toBeTruthy()
  expect(screen.getByText('+1 handed over', { selector: 'th .announced' })).toBeTruthy()
  expect(screen.getByText('held since round 2')).toBeTruthy()
  expect(screen.getByText('regressed in round 2')).toBeTruthy()
  expect(screen.getByText('Raven-PPT', { selector: '.facet .sc' })).toBeTruthy()
  expect(screen.getByTitle(/^Planned but not installed \(rejected\): memory.prompt/)).toBeTruthy()
  expect(screen.getByText('deck-aesthetics', { selector: '.quietrules code' })).toBeTruthy()
  expect(screen.getByText('on v1')).toBeTruthy()
  expect(screen.getByText('v0–v2')).toBeTruthy()
  const quoteRow = screen.getByText('quote-sheet-correct', { selector: 'th .n' }).closest('tr')!
  fireEvent.click(within(quoteRow).getAllByRole('button')[0])
  const chain = document.getElementById('evidence-chain')!
  expect(within(chain).getByText('Total 5,000 yuan')).toBeTruthy()
  expect(within(chain).getByText('Quote only from the price list.')).toBeTruthy()
  expect(within(chain).getByText('Recompute every quoted total against the list.')).toBeTruthy()
  expect(within(chain).getAllByText('by addresses').length).toBeGreaterThan(0)
  expect(within(chain).getByText('addresses R1')).toBeTruthy()
  fireEvent.click(within(chain).getByText('action/quote_gate.py', { selector: 'summary code' }))
  expect(await within(chain).findByText(/def review\(draft, plan\)/)).toBeTruthy()
  fireEvent.click(within(chain).getByText('round 1 trial'))
  expect(trial).toHaveBeenCalledWith(1)
  fireEvent.click(within(quoteRow).getAllByRole('button')[1])
  const next = document.getElementById('evidence-chain')!
  expect(within(next).getByText('The quoted total did not match the list.')).toBeTruthy()
  expect(within(next).getAllByText('since round 1').length).toBe(2)
})

test('the record view says so when the record builder is not available', async () => {
  vi.stubGlobal('fetch', vi.fn(async (path: string) => (
    path.startsWith('/api/record/export') ? reply(200, { folder: '/r/record', bundle: null }) : reply(503, { error: 'record builder not available', detail: "ModuleNotFoundError: No module named 'experimental.simulation.record'" })
  )))
  render(<RecordView runId="w/r" live={false} onTrial={() => undefined} onRemark={() => undefined} />)
  expect(await screen.findByText('The record builder is not available on this server.')).toBeTruthy()
  expect(screen.getByText(/No module named/)).toBeTruthy()
})

test('the record view leads with the value verdict and ends with the mining sessions that ranked the run', async () => {
  const value = {
    verdict: 'partial',
    score: 21,
    checks: {
      rounds: { ok: true, detail: '3 completed rounds after onboarding' },
      cases: { ok: true, detail: '1 rules went from failing to holding under planning or action' },
      delivered: { ok: false, detail: 'the last round lacks a deck in some drill' },
    },
    cases: [{
      criterion: 'quote-sheet-correct', severity: 'red_line', rule: 'S4.2: every figure matches the price list.',
      sedimented: { round: 1, scope: 'root', facet: 'action', target: 'action.review', paths: ['action/quote_gate.py'] },
      failed_in: [1], held_in: [2, 3], mechanism_rows: 5, interventions: 3, targets: ['action.review'],
    }],
    held_cases: [],
  }
  const sessions = [{
    file: 'hoh-mining-0925-1200.json', modified: 1, spend: 51.2,
    ranking: [
      { label: 'by-stage', plan: ['--chain', 'by-stage'], name: 'hoh-by-stage-0925', rounds: 4, spend: 25, value: { verdict: 'qualifies', score: 40, cases: 2 } },
      { label: 'r1-1', plan: ['--partition', JSON.stringify([['service-sop'], ['price-list']])], name: 'staged-01', rounds: 3, spend: 26.2, value: { verdict: 'partial', score: 21, cases: 1 } },
    ],
  }]
  vi.stubGlobal('fetch', vi.fn(async (path: string) => (
    path.startsWith('/api/record/export') ? reply(200, { folder: '/r/record', bundle: null })
      : path.startsWith('/api/mining') ? reply(200, { sessions })
        : reply(200, { ...raw, value })
  )))
  const open = vi.fn()
  render(<RecordView runId="staged-01/r" live={false} onTrial={() => undefined} onRemark={() => undefined} onOpenRun={open} />)
  expect(await screen.findByText('Value verdict')).toBeTruthy()
  expect(screen.getByText('partial', { selector: '.verdict .chip' })).toBeTruthy()
  expect(screen.getByText('the last round lacks a deck in some drill').closest('li')!.textContent).toContain('not met')
  expect(screen.getByText('3 interventions', { selector: 'table.cases .mk' })).toBeTruthy()
  fireEvent.click(screen.getByText('quote-sheet-correct', { selector: 'table.cases button' }))
  expect(within(document.getElementById('evidence-chain')!).getByText('The quoted total did not match the list.')).toBeTruthy()
  expect(await screen.findByText('hoh-mining-0925-1200.json')).toBeTruthy()
  expect(screen.getByText('r1-1').closest('tr')!.className).toBe('this')
  expect(screen.getByText('r1-1').getAttribute('title')).toBe('onboarding: service-sop · after round 1: price-list')
  fireEvent.click(screen.getByText('hoh-by-stage-0925'))
  expect(open).toHaveBeenCalledWith('hoh-by-stage-0925')
})
