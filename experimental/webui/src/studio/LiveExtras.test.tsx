/* What a live session adds around its trials: marking a turn of the round, starting from a saved version and picking
   the scenario's scripts to play. */

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { T } from './copy'
import { NewSessionDialog, ScriptsDialog } from './views/Dialogs'
import { ExamCompare, examName, examTakes } from './views/Compare'
import { CollectorAsk, Proposals } from './views/Proposals'
import { TrialPane } from './views/Trials'

import type { LiveInfo, LiveProposals, LiveQuestion } from './api'
import type { Thread, TrialView } from './types'

afterEach(cleanup)
// jsdom lays nothing out, so it has no scrolling; the pane scrolls its last turn into view.
Element.prototype.scrollIntoView = vi.fn()

const trial: TrialView = {
  id: '1:week-1',
  title: 'week-1',
  version: 'v1',
  status: 'done',
  source: 'live',
  exchanges: [
    { user: 'Monday', execution: { turn_id: 't1', artifact_id: '', records: [] } },
    { user: 'Friday', execution: { turn_id: 't2', artifact_id: '', records: [] } },
  ],
}

test('a turn is marked with what it should have been, which needs the words, and shows the marks it has', () => {
  const onMark = vi.fn()
  render(<TrialPane trial={trial} run={null} marking={{ given: [{ turn: 0, kind: 'wrong', note: 'made up a post' }], onMark }} />)
  expect(screen.getByText('made up a post')).toBeTruthy()
  fireEvent.click(screen.getAllByRole('button', { name: T.marks.fix })[1])
  const send = screen.getByRole('button', { name: T.markSend }) as HTMLButtonElement
  expect(send.disabled).toBe(true)
  fireEvent.change(screen.getByPlaceholderText(T.markAsk.fix), { target: { value: 'List the urgent posts first' } })
  fireEvent.click(send)
  expect(onMark).toHaveBeenCalledWith(1, 'fix', 'List the urgent posts first')
  fireEvent.click(screen.getAllByRole('button', { name: T.marks.right })[0])
  fireEvent.click(screen.getByRole('button', { name: T.markSend }))
  expect(onMark).toHaveBeenLastCalledWith(0, 'right', '')
})

test('an AI question is asked from the bar of a held trial, fills the box once and says what it tests', () => {
  const onAsk = vi.fn()
  const held: TrialView = { ...trial, status: 'running', exchanges: [] }
  const pane = (state: LiveQuestion | null, shown: TrialView = held, key = 'pane') => (
    <TrialPane key={key} trial={shown} run={null} onSay={vi.fn()} question={{ state, onAsk }} />
  )
  const { rerender } = render(pane(null))
  expect(screen.getByText(T.trialHint)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: T.questionAsk }))
  expect(onAsk).toHaveBeenCalledTimes(1)
  rerender(pane({ trial: 'week-1', at: 1, busy: true }))
  expect((screen.getByRole('button', { name: T.questionBusy }) as HTMLButtonElement).disabled).toBe(true)
  const drafted = { trial: 'week-1', at: 2, message: 'Monday: 12 new posts', aim: 'Spots the outage', good: 'Alerts at once' }
  rerender(pane(drafted))
  const box = screen.getByPlaceholderText(T.trialSay) as HTMLTextAreaElement
  expect(box.value).toBe('Monday: 12 new posts')
  expect(screen.getByText('Spots the outage') && screen.getByText(T.questionNote)).toBeTruthy()
  const sent: TrialView = { ...held, exchanges: [{ user: 'Monday: 12 new posts', execution: { turn_id: 't1', artifact_id: '', records: [] } }] }
  rerender(pane(drafted, sent, 'reopened'))
  expect((screen.getByPlaceholderText(T.trialSay) as HTMLTextAreaElement).value).toBe('')
  expect(screen.queryByText(T.questionNote) || screen.queryByText(T.trialHint)).toBeNull()
  rerender(pane({ trial: 'week-1', at: 3, error: 'the model provider failed' }))
  expect(screen.getByText(T.questionFailed('the model provider failed'))).toBeTruthy()
})

test('proposed checks are settled with one of two answers or a rule of your own, and settled ones are listed', () => {
  const onAdopt = vi.fn()
  const options = [
    { example: 'EverOS scored 93.05% on LoCoMo', rule: 'Cite the score with its source, no superlative' },
    { example: 'EverOS is SOTA', rule: 'Superlatives are allowed' },
  ]
  const proposals: LiveProposals = {
    at: 2,
    items: [
      { topic: 'May the line say SOTA?', why: 'Trial 1 wrote SOTA', options, chosen: null },
      { topic: 'How long?', why: 'Trial 1 ran long', options, chosen: { option: null, rule: 'Five lines at most' } },
    ],
  }
  const { rerender } = render(<Proposals proposals={proposals} adopted={['Five lines at most']} onAdopt={onAdopt} />)
  expect(screen.getByText('May the line say SOTA?') && screen.getByText(T.proposeChosen('Five lines at most'))).toBeTruthy()
  expect(screen.getByText('Five lines at most')).toBeTruthy()
  const picks = screen.getAllByRole('button', { name: T.proposePick })
  expect(picks).toHaveLength(2)
  fireEvent.click(picks[1])
  expect(onAdopt).toHaveBeenLastCalledWith(0, { option: 1 })
  const mine = screen.getByRole('button', { name: T.proposeUseOwn }) as HTMLButtonElement
  expect(mine.disabled).toBe(true)
  fireEvent.change(screen.getByPlaceholderText(T.proposeOwn), { target: { value: '  Name the source  ' } })
  fireEvent.click(mine)
  expect(onAdopt).toHaveBeenLastCalledWith(0, { rule: 'Name the source' })
  rerender(<Proposals proposals={{ at: 3, busy: true }} adopted={[]} />)
  expect(screen.getByText(T.proposeBusy)).toBeTruthy()
  rerender(<Proposals proposals={{ at: 4, error: 'the model provider failed' }} adopted={[]} />)
  expect(screen.getByText(T.proposeFailed('the model provider failed'))).toBeTruthy()
  rerender(<Proposals proposals={null} adopted={[]} />)
  expect(document.querySelector('.st-proposals')).toBeNull()
})

test('an exam question is laid side by side across the versions that sat it, each with its own verdicts', () => {
  const said = (text: string) => ({ user: 'Compare us with mem0', execution: { turn_id: 't', artifact_id: '', records: [{ kind: 'runner.event', event_type: 'Text', event: { content: text } }] } })
  const take = (round: number, version: string, text: string): TrialView => ({ id: `${round}:holdout:e01`, title: 'e01', version, status: 'done', source: 'live', holdout: true, exchanges: [said(text)] as TrialView['exchanges'] })
  const item = (id: string, result: 'pass' | 'fail', note: string) => ({ id, result, session: 'e01', expected: '', actual: '', note })
  const signal = (items: ReturnType<typeof item>[]) => ({ source: 'facts-judge', text: '', items, attachments: [] })
  const thread = {
    entries: [
      { kind: 'trials', key: 'holdout-1', round: 1, version: 'v1', holdout: true, trials: [take(1, 'v1', 'Old answer'), { ...take(1, 'v1', 'x'), id: '1:holdout:e02' }] },
      { kind: 'score', key: 's1', round: 1, holdout: true, criteria: [], signal: signal([item('F-cells:e01', 'fail', 'Two cells wrong\nmore'), item('P-lead:e01', 'pass', ''), { ...item('F-cells:e02', 'fail', ''), session: 'e02' }]) },
      { kind: 'trials', key: 'holdout-2', round: 2, version: 'v2', holdout: true, trials: [take(2, 'v2', 'New answer')] },
      { kind: 'score', key: 's2', round: 2, holdout: true, criteria: [], signal: signal([item('F-cells:e01', 'pass', ''), item('P-lead:e01', 'pass', '')]) },
    ],
  } as unknown as Thread
  const takes = examTakes(thread, 'e01')
  expect(takes.map((t) => [t.round, t.trial.version, t.items.length])).toEqual([[1, 'v1', 2], [2, 'v2', 2]])
  expect(examName(takes[0].trial)).toBe('e01')
  render(<ExamCompare takes={takes} />)
  expect(screen.getByText('Compare us with mem0') && screen.getByText('Old answer') && screen.getByText('New answer')).toBeTruthy()
  expect(screen.getByText(T.compareFailed(1, 2)) && screen.getByText(T.compareFailed(0, 2)) && screen.getByText('Two cells wrong')).toBeTruthy()
  fireEvent.change(screen.getAllByRole('combobox', { name: T.compareVersion })[0], { target: { value: '1' } })
  expect(screen.getAllByText('New answer')).toHaveLength(2)
})

test('a trial without the AI question shows neither its button nor its hint', () => {
  render(<TrialPane trial={{ ...trial, status: 'running' }} run={null} onSay={vi.fn()} />)
  expect(screen.queryByRole('button', { name: T.questionAsk }) || screen.queryByText(T.trialHint)).toBeNull()
})

test('a trial without marking offers no marks', () => {
  render(<TrialPane trial={trial} run={null} />)
  expect(screen.queryByRole('button', { name: T.marks.wrong })).toBeNull()
})

test('a new session started from a saved version takes its job and names it', () => {
  const info = {
    enabled: true,
    scenario: 'gtm-oncall',
    task: 'Watch the community',
    materials: [],
    settings: { rounds: 4, turns: 8, curator: null, analyst: null, standard: true },
    versions: [{ name: 'exp14 after-A', task: 'The job it was cultivated on' }],
    sessions: [],
  } as LiveInfo
  const onCreate = vi.fn()
  render(<NewSessionDialog info={info} error={null} onCreate={onCreate} onCancel={() => undefined} />)
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'exp14 after-A' } })
  const job = screen.getByDisplayValue('The job it was cultivated on') as HTMLTextAreaElement
  expect(job.readOnly).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: T.create }))
  expect(onCreate).toHaveBeenCalledWith(expect.objectContaining({ task: 'The job it was cultivated on', version: 'exp14 after-A' }))
})

test('the scripts picked are the ones played', () => {
  const onPlay = vi.fn()
  const scripts = [
    { name: 'A2025-10-13', title: 'Anytype, week of 2025-10-13', exam: false, steps: 5 },
    { name: 'O2025-12-08', title: 'Obsidian, week of 2025-12-08', exam: false, steps: 5 },
  ]
  render(<ScriptsDialog scripts={scripts} onPlay={onPlay} onCancel={() => undefined} />)
  expect((screen.getByRole('button', { name: T.playN(0) }) as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(screen.getByLabelText(/Obsidian/))
  fireEvent.click(screen.getByRole('button', { name: T.playN(1) }))
  expect(onPlay).toHaveBeenCalledWith(['O2025-12-08'])
})

test('the questions of the information preparation wait together, each answered or skipped in any order', () => {
  const onAnswer = vi.fn()
  const questions = [
    { id: 'q1', dimension: 'role', question: 'Who signs off a comparison?', reason: 'Nobody named an owner.', proposal: 'The lead', assumption: 'The lead signs off' },
    { id: 'q2', dimension: 'scope', question: 'Which competitors matter most?', reason: 'The brief names none.' },
  ]
  render(<CollectorAsk questions={questions} onAnswer={onAnswer} />)
  expect(screen.getByText('Who signs off a comparison?') && screen.getByText(T.collectorAssumption('The lead signs off'))).toBeTruthy()
  const answers = screen.getAllByRole('button', { name: T.collectorAnswer }) as HTMLButtonElement[]
  expect(answers.map((button) => button.disabled)).toEqual([true, true])
  fireEvent.change(screen.getByLabelText('Which competitors matter most?'), { target: { value: '  mem0 and Zep  ' } })
  fireEvent.click(answers[1])
  expect(onAnswer).toHaveBeenLastCalledWith('q2', { text: 'mem0 and Zep' })
  fireEvent.click(screen.getAllByRole('button', { name: T.collectorSkip })[0])
  expect(onAnswer).toHaveBeenLastCalledWith('q1', { skip: true })
})

test('a new session picks its scenario, and a scenario is built from the job, files and one request per line', async () => {
  const configured = { name: 'travel_agency', title: 'Travel agency', task: 'the job', built: false, materials: [], scripts: [] }
  const info: LiveInfo = {
    enabled: true,
    scenario: 'travel_agency',
    task: 'the job',
    materials: [],
    settings: { rounds: 2, turns: 3, curator: null, analyst: null, standard: false },
    scenarios: [configured],
    sessions: [],
  }
  const built = { name: 'scn-0a1b2c3d', title: 'Weekly report', task: 'Write the weekly report.', built: true, materials: [], scripts: [] }
  const onBuild = vi.fn(async () => built)
  const onCreate = vi.fn()
  render(<NewSessionDialog info={info} error={null} onCreate={onCreate} onBuild={onBuild} onCancel={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: T.newScenarioBuild }))
  const build = screen.getByRole('button', { name: T.buildDo }) as HTMLButtonElement
  expect(build.disabled).toBe(true)
  fireEvent.change(screen.getByLabelText(T.buildName), { target: { value: ' Weekly report ' } })
  fireEvent.change(screen.getByLabelText(T.buildProfile), { target: { value: 'Write the weekly report.' } })
  fireEvent.change(screen.getByLabelText(T.buildPractice), { target: { value: 'This week\n\n  Last month  ' } })
  fireEvent.change(screen.getByLabelText(T.buildChecks), { target: { value: 'Cite every number' } })
  fireEvent.click(build)
  expect(onBuild).toHaveBeenCalledWith({
    title: 'Weekly report',
    profile: 'Write the weekly report.',
    files: [],
    practice: ['This week', 'Last month'],
    exam: [],
    checks: ['Cite every number'],
  })
  const picker = (await screen.findByLabelText(T.newScenario)) as HTMLSelectElement
  expect(picker.value).toBe('scn-0a1b2c3d')
  expect((screen.getByPlaceholderText(T.newTaskPlaceholder) as HTMLTextAreaElement).value).toBe('Write the weekly report.')
  fireEvent.click(screen.getByRole('button', { name: T.create }))
  expect(onCreate).toHaveBeenCalledWith({ title: T.titleFrom('Write the weekly report.'), task: 'Write the weekly report.', scenario: 'scn-0a1b2c3d' })
})
