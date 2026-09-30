/* A render error shows its message and a way back instead of a blank page. */

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { T } from './copy'
import { Crash } from './Crash'

import type { JSX } from 'react'

afterEach(cleanup)

let broken = true
function Boom(): JSX.Element {
  if (broken) throw new Error('pane state went missing')
  return <p>back</p>
}

test('a render error is shown with its message, and the page renders again after going back', () => {
  const quiet = vi.spyOn(console, 'error').mockImplementation(() => undefined)
  render(<Crash><Boom /></Crash>)
  expect(screen.getByRole('alert').textContent).toContain('pane state went missing')
  expect(screen.getByText(T.crashTitle)).toBeTruthy()
  broken = false
  fireEvent.click(screen.getByText(T.crashRetry))
  expect(screen.getByText('back')).toBeTruthy()
  quiet.mockRestore()
})
