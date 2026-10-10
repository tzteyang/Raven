/* The loop canvas: a board per lap with its stations in loop order, the version each board hands the next, the
   station read or pointed at in the conversation marked, picking a station, the running station marked, and the
   pointer's pull on a board. */

import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, test } from 'vitest'

import { revisions, roundVersions } from './derive'
import { loopOf } from './loop'
import { cultivated } from './run.fixture'
import { LoopMap } from './views/LoopMap'

import type { Phase } from './loop'
import type { Run } from './model'
import type { Picked } from './views/LoopMap'

afterEach(cleanup)

const draw = (run: Run, { phase = null, active = null, hot = null, onPick = () => undefined }: { phase?: Phase | null; active?: string | null; hot?: string | null; onPick?: (picked: Picked) => void } = {}) => {
  const all = revisions(run)
  return render(<LoopMap laps={loopOf(run, all, roundVersions(run, all), new Set(), phase)} active={active} hot={hot} onPick={onPick} />)
}
const stations = (container: HTMLElement): HTMLElement[] => [...container.querySelectorAll<HTMLElement>('.lb-stop')]

test('every lap sits on a board of its own with its stations in loop order, each board handing its version to the next', () => {
  const { container } = draw({ ...cultivated(), status: 'finished' })
  const named = stations(container).map((button) => button.getAttribute('aria-label')!.split(':')[0])
  expect(named.slice(0, 6)).toEqual(['onboarding, Handover', 'onboarding, Diagnose', 'onboarding, Select · design', 'onboarding, Implement · repair', 'round 1, Version', 'round 1, Trial'])
  expect(named).toHaveLength(4 + 3 * 7)
  expect([...container.querySelectorAll('.lb-name')].map((name) => name.textContent)).toEqual(['onboarding', 'round 1', 'round 2', 'round 3'])
  expect([...container.querySelectorAll('.lb-made')].map((made) => made.textContent)).toEqual(['installed v1', 'installed v2', 'no revision', 'failed · stays v2'])
  expect(container.querySelectorAll('.lb-seg[data-part=again]')).toHaveLength(3)
  expect([...container.querySelectorAll('.react-flow__edge.lb-carry')].map((edge) => edge.textContent)).toEqual(['v1', 'v2', 'v2'])
  expect(screen.getByRole('button', { name: 'Fit View' })).toBeTruthy()
})

test('a round judged shows how inside its track', () => {
  const run: Run = { ...cultivated(), status: 'finished' }
  const all = revisions(run)
  const laps = loopOf(run, all, roundVersions(run, all), new Set(), null).map((lap) => ({
    ...lap,
    stations: lap.stations.map((station) => (lap.round === 1 && station.id === 'assess' ? { ...station, state: 'done' as const, facts: ['3 pass · 1 fail', 'no red line missed'] } : station)),
  }))
  const { container } = render(<LoopMap laps={laps} active={null} hot={null} onPick={() => undefined} />)
  expect([...container.querySelectorAll('.lb-judged')].map((judged) => [...judged.children].map((line) => line.textContent))).toEqual([['3 pass · 1 fail', 'no red line missed']])
})

test('the station read in the conversation is the current location, its board is marked, and the one pointed at there is lit', () => {
  const { container } = draw({ ...cultivated(), status: 'finished' }, { active: '1:assess', hot: '2:design' })
  expect(screen.getByRole('button', { name: /^round 1, Assess/ }).getAttribute('aria-current')).toBe('location')
  expect(screen.getByRole('button', { name: /^round 2, Select · design/ }).hasAttribute('data-on')).toBe(true)
  expect([...container.querySelectorAll('.lb[data-here] .lb-name')].map((name) => name.textContent)).toEqual(['round 1'])
})

test('picking a station names its round and station, and every station is a button the keyboard reaches', () => {
  const picked: Picked[] = []
  const { container } = draw({ ...cultivated(), status: 'finished' }, { onPick: (value) => picked.push(value) })
  fireEvent.click(screen.getByRole('button', { name: /^onboarding, Diagnose/ }))
  fireEvent.click(screen.getByRole('button', { name: /^round 2, Analyse/ }))
  expect(picked).toEqual([{ round: 0, station: 'diagnose' }, { round: 2, station: 'analyse' }])
  expect(stations(container).every((station) => station.tagName === 'BUTTON' && station.tabIndex === 0)).toBe(true)
})

test('the station a running run is at pulses, the track into it flows and so does the hand-off into its board', () => {
  const { container } = draw({ ...cultivated(), status: 'running' }, { phase: { name: 'trial', round: 4, stage: null, basis: 'a turn is in progress' } })
  expect(screen.getByRole('button', { name: 'round 4, Trial: a turn is in progress' }).dataset.state).toBe('current')
  expect(container.querySelectorAll('.lb-stop[data-state=current]')).toHaveLength(1)
  expect(container.querySelectorAll('.lb[data-live] .lb-seg[data-part=flow]')).toHaveLength(1)
  expect([...container.querySelectorAll('.react-flow__edge.lb-carry.animated')].map((edge) => edge.textContent)).toEqual(['v2'])
})

test('a pointer over a board pulls the stations near it, settles them when it leaves, and names the station under it', () => {
  const { container } = draw({ ...cultivated(), status: 'finished' })
  const board = container.querySelectorAll<HTMLElement>('.lb')[1]
  const [near, , , far] = within(board).getAllByRole('button')
  const at = (x: number) => () => ({ left: x, top: 0, right: x + 24, bottom: 24, width: 24, height: 24, x, y: 0, toJSON: () => ({}) }) as DOMRect
  near.getBoundingClientRect = at(0)
  far.getBoundingClientRect = at(400)
  fireEvent.pointerMove(board, { clientX: 12, clientY: 12 })
  expect(Number(near.style.getPropertyValue('--w'))).toBe(1)
  expect(Number(far.style.getPropertyValue('--w'))).toBe(0)
  fireEvent.pointerLeave(board)
  expect(near.style.getPropertyValue('--w')).toBe('')
  fireEvent.pointerEnter(near)
  expect(screen.getByRole('tooltip').textContent).toBe('round 1 Version v1 · 1 change')
})
