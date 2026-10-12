/* A requirement's examples on its card: wrong ones first, each with the quoted input, what the worker did, the handling
   and the rule. */

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { T } from './copy'
import { Examples } from './views/ProcessCard'

afterEach(cleanup)

test('a requirement lists its wrong examples before its right ones, with the handling of each wrong one', () => {
  render(
    <Examples
      examples={[
        { kind: 'right', turn: 'turn-right-0001', input: 'The app crashes on start.', output: 'Urgent alert sent.', why: 'Kept the red line.' },
        { kind: 'wrong', turn: 'turn-wrong-0001', input: 'I cannot open the app.', output: 'No alert.', handling: 'Alert the team the same day.', why: 'Breaks the red line.' },
      ]}
    />,
  )
  fireEvent.click(screen.getByText(T.examples(1, 1)))
  const labels = screen.getAllByText(/^(Wrong|Right) · /).map((node) => node.textContent)
  expect(labels).toEqual([`${T.exampleWrong} · turn-wro`, `${T.exampleRight} · turn-rig`])
  expect(screen.getByText('Alert the team the same day.')).toBeTruthy()
  expect(screen.getAllByText(T.exampleHandling)).toHaveLength(1)
})

test('the simple view keeps what the Curator concluded and leaves out the inspector and the loop internals', async () => {
  const actions = { onDiff: () => {}, onRaw: () => {}, onInspect: () => {}, onEvidence: () => {} }
  const plan = { understanding: 'Added a quote check\nso replies cite sources', design: 'Design in full', changes: [], node_reasons: {} }
  const scope = { name: '', root: true, plan, outputs: [], stages: [], attribution: null, selection: null, reads: [], playbooks: [] }
  const card = { kind: 'process', key: 'r1', round: 1, onboarding: true, footer: { kind: 'analysing' } }
  const curation = { scopes: [scope], deployed: true, validation: { errors: [], observations: 0 }, paused: false, error: null, budget: null }
  const shown = async (view: 'simple' | 'full', withCuration: boolean) => {
    cleanup()
    vi.resetModules()
    localStorage.setItem('studio.detail', view)
    const { ProcessCard } = await import('./views/ProcessCard')
    const { T: words } = await import('./copy')
    render(<ProcessCard card={{ ...card, ...(withCuration ? { curation } : {}) } as never} mode="live" latest actions={actions as never} />)
    return words
  }
  const words = await shown('full', false)
  expect(screen.getByText(words.inspector)).toBeTruthy()
  await shown('simple', true)
  localStorage.removeItem('studio.detail')
  expect(screen.queryByText(words.inspector)).toBeNull()
  expect(screen.getByText('Added a quote check')).toBeTruthy()
  expect(screen.queryByText(words.design)).toBeNull()
})

test('a card asks the Analyst and the Curator about its round and shows each answer, busy question or failure', async () => {
  vi.resetModules()
  localStorage.setItem('studio.detail', 'simple')
  const { ProcessCard } = await import('./views/ProcessCard')
  const { T: words } = await import('./copy')
  localStorage.removeItem('studio.detail')
  const asked: unknown[] = []
  const scope = { name: '', root: true, plan: { understanding: 'Checked the quotes' }, outputs: [], stages: [], attribution: null, selection: null, reads: [], playbooks: [] }
  const curation = { scopes: [scope], deployed: true, validation: { errors: [], observations: 0 }, paused: false, error: null, budget: null }
  const card = {
    kind: 'process', key: 'r2', round: 2, onboarding: false, footer: { kind: 'analysing' }, analysis: 'done', curationState: 'done',
    feedback: { decision: 'curate', reason: 'Quotes drift', requirements: [], filtered: [] }, held: {}, curation,
  }
  const inquiries = [
    { role: 'analyst', round: 2, question: 'Why curate?', at: 1, answer: 'Because **two** quotes drifted.' },
    { role: 'curator', round: 2, question: 'What changed?', at: 2, error: 'timed out' },
    { role: 'analyst', round: 1, question: 'Another round', at: 3, answer: 'Not shown here' },
  ]
  const actions = { onDiff: () => {}, onRaw: () => {}, onInspect: () => {}, inquiries, onInquire: (...args: unknown[]) => asked.push(args) }
  const { rerender } = render(<ProcessCard card={card as never} mode="live" latest actions={actions as never} />)
  expect(screen.getByText('two').tagName).toBe('STRONG')
  expect(screen.getByText(words.askFailed('timed out'))).toBeTruthy()
  expect(screen.queryByText('Not shown here')).toBeNull()
  const box = screen.getByPlaceholderText(words.askPlaceholder)
  fireEvent.change(screen.getByLabelText(words.askRole), { target: { value: 'curator' } })
  fireEvent.change(box, { target: { value: '  Why the quote check?  ' } })
  fireEvent.click(screen.getByText(words.askSend))
  expect(asked).toEqual([[2, 'curator', 'Why the quote check?']])
  expect((box as HTMLInputElement).value).toBe('')
  rerender(<ProcessCard card={card as never} mode="live" latest actions={{ ...actions, inquiries: [...inquiries, { role: 'curator', round: 2, question: 'Why the quote check?', at: 4, busy: true }] } as never} />)
  expect(screen.getByText(words.askBusy)).toBeTruthy()
  fireEvent.change(box, { target: { value: 'More?' } })
  fireEvent.click(screen.getByText(words.askSend))
  expect(asked).toEqual([[2, 'curator', 'Why the quote check?'], [2, 'curator', 'More?']])
  rerender(<ProcessCard card={{ ...card, onboarding: true, round: 0, feedback: null, curation: null } as never} mode="live" latest actions={actions as never} />)
  expect(screen.queryByPlaceholderText(words.askPlaceholder)).toBeNull()
})
