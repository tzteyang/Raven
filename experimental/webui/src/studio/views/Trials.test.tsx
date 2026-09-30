/* The trial pane closes cleanly where scrollIntoView returns a promise, as newer browsers' scroll methods do: an
   effect that returned it would hand React a cleanup that is not a function and blank the page on close. */

import { cleanup, render } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { TrialPane } from './Trials'

import type { TrialView } from '../types'

afterEach(cleanup)

const trial: TrialView = {
  id: '1:family',
  title: 'family',
  version: 'v1',
  status: 'done',
  exchanges: [{ user: 'hi', execution: { turn_id: 't', artifact_id: 'a', records: [] } }],
  source: 'recorded',
}

test('closing the trial pane survives a scrollIntoView that returns a promise', () => {
  const scroll = vi.fn(() => Promise.resolve())
  Element.prototype.scrollIntoView = scroll as unknown as Element['scrollIntoView']
  const { unmount } = render(<TrialPane trial={trial} run={null} />)
  expect(scroll).toHaveBeenCalled()
  expect(() => unmount()).not.toThrow()
})
