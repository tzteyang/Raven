/* The Studio's live mode against a stubbed server: without a live
   configuration it only replays, and each action on the dock is one of the
   Session's steps, posted to its route. */

import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { T } from './copy'
import { Studio } from './Studio'

import type { Run } from '../model'
import type { LiveInfo, LiveSnapshot, LiveState, LiveSummary } from './api'

const ID = 'live-20260929120000-abcdef'

const summary: LiveSummary = {
  id: ID,
  title: 'Agency',
  task: 'the job',
  created: 1,
  archived: null,
  run: `${ID}/r`,
  status: 'running',
  models: { curator: 'deepseek/deepseek-flash' },
  attached: true,
  step: null,
}

const info: LiveInfo = {
  enabled: true,
  scenario: 'travel_agency',
  task: 'the job',
  materials: [{ name: 'service-sop', kind: 'norm', files: ['uploads/service-sop/SKILL.md'] }],
  settings: { rounds: 2, turns: 3, curator: null, analyst: null, standard: false },
  sessions: [summary],
}

const state = (values: Partial<LiveState> = {}): LiveState => ({
  step: null,
  since: 1,
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

const fresh: Run = { task_id: 't', task: 'the job', status: 'running', opening: [], initial_curation: [], rounds: [] }
const exchange = { user: 'hello', execution: { turn_id: 'x', artifact_id: '', records: [] } }
const reviewed: Run = {
  ...fresh,
  rounds: [
    {
      sessions: { 'trial-1': [exchange] },
      signals: [{ source: 'human', text: 'ask the budget first', items: [], metrics: {}, satisfied: null, attachments: [] }],
      feedback: { decision: 'curate', reason: 'intake gap', requirements: [], filtered: [], task_updates: [] },
      curated: true,
      analysis: [],
      curation: [],
    },
  ],
  pending: { review: { activity: [] } },
}

const snapshot = (live: Partial<LiveState>, record: Run): LiveSnapshot => ({
  ...summary,
  state: state(live),
  busy: false,
  stamp: 's',
  progress: { curation: null, paused: null },
  record,
})

function server(current: () => LiveSnapshot, live = true, download?: () => Promise<Response>): [string, unknown][] {
  const posts: [string, unknown][] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string, init?: RequestInit) => {
      const answer = (value: unknown, status = 200) => ({ ok: status < 400, status, json: async () => value })
      if (init?.method === 'POST') {
        posts.push([path, JSON.parse(String(init.body))])
        return answer({ ok: true, state: current().state })
      }
      if (path === '/api/studio/runs') return answer([])
      if (path === '/api/studio/live') return live ? answer(info) : answer({ error: 'off' }, 404)
      if (path === `/api/studio/live/${ID}/export` && download) return download()
      if (path.startsWith(`/api/studio/live/${ID}`)) return answer(current())
      return answer({ error: 'unknown endpoint' }, 404)
    }),
  )
  return posts
}

beforeEach(() => {
  Element.prototype.scrollTo = () => undefined
  Element.prototype.scrollIntoView = () => undefined
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

async function open(): Promise<HTMLElement> {
  render(<Studio />)
  fireEvent.click(await screen.findByText('Agency'))
  return screen.findByRole('heading', { name: 'Agency' })
}

const dock = () => within(document.querySelector('.st-dockbar') as HTMLElement)

test('without a live configuration the Studio only replays: nothing starts a session', async () => {
  server(() => snapshot({}, fresh), false)
  render(<Studio />)
  await waitFor(() => expect(fetch).toHaveBeenCalledWith('/api/studio/live'))
  expect(screen.queryByText(T.newSession)).toBeNull()
  expect(screen.queryByText(T.groupLive)).toBeNull()
})

test('the first message is the onboarding, with the materials the person attached', async () => {
  const posts = server(() => snapshot({ onboarded: false }, fresh))
  await open()
  const box = await screen.findByPlaceholderText(T.composerFirst)
  fireEvent.change(box, { target: { value: 'here is the SOP' } })
  fireEvent.click(screen.getByLabelText(T.attach))
  fireEvent.click(screen.getByRole('option', { name: /service-sop/ }))
  fireEvent.click(screen.getByLabelText(T.send))
  await waitFor(() => expect(posts).toEqual([[`/api/studio/live/${ID}/onboard`, { text: 'here is the SOP', materials: ['service-sop'] }]]))
})

test('between rounds the dock opens a trial, and a round with a trial goes to the Analyst', async () => {
  let current = snapshot({}, fresh)
  const posts = server(() => current)
  await open()
  const button = await dock().findByRole('button', { name: T.openTrial })
  current = snapshot({ pending: { sessions: 1, signals: 0 } }, { ...fresh, pending: { sessions: { 'trial-1': [exchange] } } })
  fireEvent.click(button)
  await waitFor(() => expect(posts.map(([path]) => path)).toEqual([`/api/studio/live/${ID}/trial`]))
  fireEvent.click(await dock().findByRole('button', { name: T.dockAnalyse }))
  await waitFor(() => expect(posts.map(([path]) => path).at(-1)).toBe(`/api/studio/live/${ID}/analyse`))
})

test('a curation the Analyst asked for is the person to start or skip, and a paused one resumes', async () => {
  let current = snapshot({ reviewing: true, outcome: { next: 'curate', reason: '' } }, reviewed)
  const posts = server(() => current)
  await open()
  expect(await screen.findByText(T.footer.review('v0'))).toBeTruthy()
  fireEvent.click(await dock().findByRole('button', { name: T.dockCurate }))
  await waitFor(() => expect(posts.map(([path]) => path)).toEqual([`/api/studio/live/${ID}/curate`]))
  current = snapshot({ reviewing: true, status: 'paused' }, { ...reviewed, status: 'paused', stop: 'out of calls' })
  fireEvent.click(dock().getByRole('button', { name: T.dockSkip }))
  await waitFor(() => expect(posts.map(([path]) => path).at(-1)).toBe(`/api/studio/live/${ID}/skip`))
  fireEvent.click(await dock().findByRole('button', { name: T.dockResume }))
  await waitFor(() => expect(posts.map(([path]) => path).at(-1)).toBe(`/api/studio/live/${ID}/curate`))
})

test('a session whose process is gone offers to resume it, which the server answers', async () => {
  const posts = server(() => ({ ...snapshot({}, reviewed), attached: false, state: null }))
  await open()
  expect(await screen.findByText(T.liveGone)).toBeTruthy()
  fireEvent.click(await dock().findByRole('button', { name: T.dockReattach }))
  await waitFor(() => expect(posts.map(([path]) => path)).toEqual([`/api/studio/live/${ID}/resume`]))
})

test('while a curation waits, a remark goes to the Curator alone and does not close another round', async () => {
  const current = snapshot({ reviewing: true, outcome: { next: 'curate', reason: '' } }, reviewed)
  const posts = server(() => current)
  await open()
  const box = (await screen.findByPlaceholderText(T.composerReview)) as HTMLTextAreaElement
  expect(box.disabled).toBe(false)
  fireEvent.change(box, { target: { value: 'That requirement is wrong: keep the greeting.' } })
  fireEvent.keyDown(box, { key: 'Enter' })
  await waitFor(() => expect(posts).toEqual([[`/api/studio/live/${ID}/signal`, { text: 'That requirement is wrong: keep the greeting.', materials: [] }]]))
})

test('a session is deleted only once the person confirms, and leaves the page', async () => {
  const posts = server(() => snapshot({}, fresh))
  await open()
  const confirm = vi.fn(() => false)
  vi.stubGlobal('confirm', confirm)
  fireEvent.click(screen.getByRole('button', { name: T.deleteSession }))
  expect(confirm).toHaveBeenCalledWith(T.deleteConfirm('Agency'))
  expect(posts).toEqual([])
  confirm.mockReturnValue(true)
  fireEvent.click(screen.getByRole('button', { name: T.deleteSession }))
  await waitFor(() => expect(posts.map(([path]) => path)).toEqual([`/api/studio/live/${ID}/delete`]))
  await waitFor(() => expect(screen.queryByRole('heading', { name: 'Agency' })).toBeNull())
})

test.each([false, undefined])('export explains why a session without a saved employee is unavailable (%s)', async (exportable) => {
  server(() => ({ ...snapshot({}, fresh), exportable }))
  await open()
  const button = await screen.findByRole('button', { name: T.exportEmployee }) as HTMLButtonElement
  await waitFor(() => expect(button.parentElement?.title).toBe(T.exportUnsaved))
  expect(button.disabled).toBe(true)
  fireEvent.click(button)
  expect(fetch).not.toHaveBeenCalledWith(`/api/studio/live/${ID}/export`, expect.anything())
})

test.each([
  { step: 'curate' },
  { trial: { name: 'trial', exchanges: [], said: null, waiting: true } },
])('a saved employee cannot be exported during a step or trial (%j)', async (live) => {
  server(() => ({ ...snapshot(live, fresh), exportable: true }))
  await open()
  const button = await screen.findByRole('button', { name: T.exportEmployee }) as HTMLButtonElement
  await waitFor(() => expect(button.parentElement?.title).toBe(T.exportBusy))
  expect(button.disabled).toBe(true)
})

test('an ended saved session exports from the top bar, shows progress, and explains how to use its package', async () => {
  let finish!: (response: Response) => void
  const download = vi.fn(() => new Promise<Response>((resolve) => { finish = resolve }))
  server(() => ({ ...snapshot({ ended: true, status: 'finished' }, { ...fresh, status: 'finished' }), exportable: true, attached: false }), true, download)
  vi.stubGlobal('URL', class extends URL {
    static createObjectURL = vi.fn(() => 'blob:employee-package')
    static revokeObjectURL = vi.fn()
  })
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
  await open()
  const button = await screen.findByRole('button', { name: T.exportEmployee }) as HTMLButtonElement
  await waitFor(() => expect(button.disabled).toBe(false))
  expect(document.querySelector('.top')?.contains(button)).toBe(true)
  fireEvent.click(button)
  expect(await screen.findByRole('button', { name: T.exporting })).toBe(button)
  expect(button.disabled).toBe(true)
  expect(button.getAttribute('aria-busy')).toBe('true')
  fireEvent.click(button)
  expect(download).toHaveBeenCalledOnce()

  finish(new Response('employee package', { headers: { 'Content-Type': 'application/zip', 'Content-Disposition': 'attachment; filename=agency.zip' } }))

  expect(await screen.findByRole('status')).toHaveProperty('textContent', T.exportDone)
  expect(click).toHaveBeenCalledOnce()
  expect(button.disabled).toBe(false)
  expect(button.getAttribute('aria-busy')).toBe('false')
  await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:employee-package'), { timeout: 2000 })
})

test('a refused export uses the existing error area and leaves the download button available for a retry', async () => {
  server(() => ({ ...snapshot({}, fresh), exportable: true }), true, async () => new Response(JSON.stringify({ error: 'Employee is being saved' }), {
    status: 409, headers: { 'Content-Type': 'application/json' },
  }))
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
  await open()
  const button = await screen.findByRole('button', { name: T.exportEmployee }) as HTMLButtonElement
  await waitFor(() => expect(button.disabled).toBe(false))
  fireEvent.click(button)

  const error = await screen.findByText(T.liveRefused('Employee is being saved'))
  expect(error.classList.contains('st-refusal')).toBe(true)
  expect(button.disabled).toBe(false)
  expect(click).not.toHaveBeenCalled()
  expect(screen.queryByText(T.exportDone)).toBeNull()
})
