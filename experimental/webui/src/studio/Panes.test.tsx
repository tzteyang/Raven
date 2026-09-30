/* The ledger pane shows the loop's own join: a composite curation's child
   changes and diagnoses sit beside the root's, each marked with its harness.
   A material the party did not simply give carries its origin. */

import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, expect, test } from 'vitest'

import { T } from './copy'
import { HandoverChip } from './views/bits'
import { LedgerPane } from './views/Panes'

import type { Thread } from './types'

afterEach(cleanup)

test('a composite curation lists every scope of a requirement, the child ones marked with their harness', () => {
  const thread = {
    ledger: {
      rows: [
        {
          round: 1, requirement: 'R1', situation: 'A family asks for a plan', strength: 'must_hold', repeats: null,
          state: 'not_triggered', mechanism: 'planning', diagnoses: [{ scope: 'root', state: 'not_triggered' }, { scope: 'child/Raven-PPT', state: 'absent' }],
          attributor: null, curated: true, held: true,
          changes: [
            { scope: 'root', target: 'planning.strategy', treatment: 'modify' },
            { scope: 'child/Raven-PPT', target: 'planning.strategy', treatment: 'add' },
          ],
        },
      ],
      summary: [],
      holdout: [],
    },
    history: [
      {
        round: 1, requirements: [], diagnoses: null, attributor: null,
        revision: [
          { scope: 'root', target: 'planning.strategy', treatment: 'modify', addresses: ['R1'] },
          { scope: 'child/Raven-PPT', target: 'planning.strategy', treatment: 'add', addresses: ['R1'] },
        ],
      },
    ],
    recorded: {},
    questions: [],
  } as unknown as Thread
  const { container } = render(<LedgerPane thread={thread} />)
  const row = container.querySelector('.st-table tbody tr') as HTMLElement
  expect(within(row).getAllByText('planning.strategy')).toHaveLength(2)
  expect(within(row).getAllByText('Raven-PPT')).toHaveLength(2)
  expect(within(row).getAllByTitle(T.childScopeHint)).toHaveLength(2)
  const history = screen.getByText(T.historyTitle).parentElement as HTMLElement
  expect(within(history).getAllByText('Raven-PPT')).toHaveLength(1)
  expect(within(history).getAllByText('planning.strategy')).toHaveLength(2)
})

test('a material induced before the cultivation says so and whether the party confirmed it', () => {
  const material = { name: 'induced-candidates', kind: 'norm', files: ['uploads/induced-candidates/SKILL.md'] }
  const { container } = render(<HandoverChip material={material} origin={{ origin: 'induced', confirmed: false, items: ['induced-2'] }} />)
  const mark = container.querySelector('.st-origin') as HTMLElement
  expect(mark.textContent).toBe('Induced · Unconfirmed')
  expect(mark.title).toContain('induced-2')
  cleanup()
  const given = render(<HandoverChip material={material} origin={{ origin: 'given', confirmed: true, items: [] }} />)
  expect(given.container.querySelector('.st-origin')).toBeNull()
})
