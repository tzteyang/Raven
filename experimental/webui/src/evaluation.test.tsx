/* Evaluation records distinguish protected requirements, failed evidence, candidate guidance and promotion. */

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { StandardBlock, PromotionStatus } from './views/Evaluation'
import { normalizeRecord } from './record'
import type { StandardRecord } from './model'

afterEach(cleanup)

it('shows protection and evidence without presenting candidate guidance as adopted', async () => {
  const standard: StandardRecord = {
    criteria: [{ id: 'tax', text: 'Include tax.', subject: 'Delivered quote', source: 'sedimented', strength: 'must_hold', provenance: 'human', kind: 'gate', authority: 'external', checks: [{ role: 'decision', method: 'llm', spec: '' }, { role: 'required', method: 'program', spec: 'tax_check' }], evidence_requirements: [{ kind: 'delivered_text', reference: 'quote.txt' }] }],
    derived_from: [],
    assessments: [{ id: 'run:1', version: 1, checks: [{ criterion: 'tax', method: 'program', result: 'fail', actual: 'Only subtotal present.', note: 'Tax missing.' }], unresolved: { tax: 'Need independent evidence.' } }],
    guidance: { entries: [{ id: 'candidate', kind: 'principle', state: 'candidate', scope: 'task:tax', text: 'Check complete costs.', episodes: ['run:1'] }], history: [{ candidate: 'candidate', accepted: false }] },
  }
  render(<StandardBlock standard={standard} />)
  fireEvent.click(screen.getByText('Evaluation criteria (1)'))
  expect(await screen.findByText(/protected external requirement/)).toBeTruthy()
  expect(screen.getByText('Subject: Delivered quote')).toBeTruthy()
  expect(screen.getByText('Whole criterion · Model judgment')).toBeTruthy()
  expect(screen.getByText('Necessary local check · Program verification: tax_check')).toBeTruthy()
  expect(screen.getByText('Required evidence: delivered text · quote.txt')).toBeTruthy()
  fireEvent.click(screen.getByText('Assessment 1 · evidence and review'))
  expect(await screen.findByText('Only subtotal present.')).toBeTruthy()
  fireEvent.click(screen.getByText('Construction guidance (1)'))
  expect(await screen.findByText('principle · candidate')).toBeTruthy()
  expect(screen.getByText('Kept as a candidate')).toBeTruthy()
  expect(screen.queryByText('Adopted after independent comparison')).toBeNull()
})

it('retains evaluation and promotion when normalizing a record', () => {
  const record = normalizeRecord({ promotion: { status: 'candidate', reason: 'No independent verification.' }, standard: { criteria: [], derived_from: [] } })
  expect(record.standard?.criteria).toEqual([])
  render(<PromotionStatus promotion={record.promotion} />)
  expect(screen.getByText('Harness verification · candidate')).toBeTruthy()
  expect(screen.getByText('No independent verification.')).toBeTruthy()
})

it('orders hierarchical criteria by parent and preserves pending construction and unvalidated repairs', async () => {
  const base = { source: 'derived', strength: 'must_hold', provenance: 'policy', kind: 'gate' as const, authority: 'model' as const }
  render(<StandardBlock standard={{
    criteria: [{ ...base, id: 'tax', parent_id: 'cost', text: 'Include tax.' }, { ...base, id: 'cost', parent_id: null, text: 'Include all costs.' }],
    derived_from: ['policy'],
    construction: [{ status: 'call_budget_exhausted', calls: 1, added: 2, steps: [{ target: 'cost', status: 'changed', note: 'Check required cost categories.' }] }],
    pending: [{ target: 'tax', reason: 'Review the tax coverage.' }],
    assessments: [{ id: 'one', version: 1, checks: [], repair_status: 'candidate', repair_validation: { tax: { accepted: false } } }],
  }} />)
  fireEvent.click(screen.getByText('Evaluation criteria (2)'))
  expect(await screen.findByText('Refines: cost')).toBeTruthy()
  const ids = [...document.querySelectorAll('.sc-fails > li > code')].map((node) => node.textContent)
  expect(ids).toEqual(['cost', 'tax'])
  fireEvent.click(screen.getByText('Rubric construction (1)'))
  expect(await screen.findByText('call budget exhausted')).toBeTruthy()
  expect(screen.getByText(/Review the tax coverage/)).toBeTruthy()
  fireEvent.click(screen.getByText('Assessment 1 · evidence and review'))
  expect(await screen.findByText('Rubric repair · candidate')).toBeTruthy()
  expect(screen.getByText('tax · Repair remains unvalidated')).toBeTruthy()
})
