/* Each rendered part of the conversation reads as its own source: the slices of the record behind it, each under its
   path; the part's switch keeps its clicks from opening or closing the part around it. Source is highlighted by its
   language, and a module's imports of other generated modules are found. */

import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, test } from 'vitest'

import { importsOf } from './mechanism'
import { changeParts, diagnosisParts, intakeParts, selectionParts } from './sources'
import { CodeBlock, highlighted, languageOf, lines } from './views/Code'
import { RawPanel, useShowAs } from './views/Raw'

import type { Reply } from './cultivation'
import type { RawPart } from './sources'

afterEach(cleanup)

const FILES = {
  'brand_capability.py': 'from brand_types import Norm\nfrom . import brand_parse\n\ndef create(host):\n    return Norm(host)\n',
  'brand_types.py': 'class Norm:\n    pass\n',
  'brand_parse.py': 'import re\n',
}

const change = { target: 'capability.strategy', treatment: 'modify', reason: 'norms arrived', expected: 'supplied', verification: 'registered' }
const reply = {
  revision: {
    curation: {
      file: 'c1.json',
      generated: {
        candidate: {
          plan: { understanding: 'Keep what holds.', design: '# Scope', changes: [change] },
          artifact: { values: { 'capability.strategy': { factory: 'brand_capability:create' } }, files: FILES },
          selection: { understanding: 'Chose capability.', targets: ['capability.strategy'], grounds: { 'capability.strategy': ['material:watch-brief', 'information:e14f'] } },
        },
        validation: { errors: [], observations: [] },
        trace: [],
      },
    },
  },
  handover: [{ name: 'watch-brief', kind: 'norm', files: ['uploads/watch-brief/SKILL.md'], diagnosis: null, targets: ['capability.strategy'] }],
  pasted: [],
  attribution: { record: null, diagnoses: [{ about: 'material:watch-brief', state: 'uncovered' }, { about: 'information:e14f', state: 'covered' }] },
  selection: { understanding: 'Chose capability.', targets: ['capability.strategy'], grounds: { 'capability.strategy': ['material:watch-brief', 'information:e14f'] } },
} as unknown as Reply

test('a change reads as its plan entry, its binding, the module its factory names, the modules that imports, and its grounds', () => {
  const parts = changeParts(reply, 0)
  expect(parts.map((part) => [part.path, part.as, part.folded ?? false])).toEqual([
    ['generated.candidate.plan.changes[0]', 'json', false],
    ['generated.candidate.artifact.values["capability.strategy"]', 'json', false],
    ['generated.candidate.artifact.files["brand_capability.py"]', 'code', false],
    ['generated.candidate.artifact.files["brand_types.py"]', 'code', true],
    ['generated.candidate.artifact.files["brand_parse.py"]', 'code', true],
    ['generated.candidate.selection.grounds["capability.strategy"]', 'json', false],
  ])
  expect(parts[0].value).toBe(change)
  expect(parts[2].value).toBe(FILES['brand_capability.py'])
  expect(changeParts(reply, 4)).toEqual([])
})

test('the hand-over, the diagnosis and the selection read as the slices they were drawn from', () => {
  expect(intakeParts(reply).map((part) => [part.path, part.value])).toEqual([
    ['signals[].attachments', [{ name: 'watch-brief', kind: 'norm', files: ['uploads/watch-brief/SKILL.md'] }]],
    ['attribution.diagnoses (these materials)', [{ about: 'material:watch-brief', state: 'uncovered' }]],
    ['generated.candidate.selection.grounds (these materials)', { 'capability.strategy': ['material:watch-brief', 'information:e14f'] }],
  ])
  expect(diagnosisParts(reply)).toEqual([])
  expect(selectionParts(reply).map((part) => [part.path, part.as])).toEqual([
    ['generated.candidate.selection.understanding', 'prose'],
    ['generated.candidate.selection', 'json'],
  ])
})

function Sample({ parts }: { parts: RawPart[] }) {
  const [raw, showAs] = useShowAs('sample')
  return (
    <details className="sample">
      <summary>Sample{showAs}</summary>
      {raw ? <RawPanel file="c1.json" parts={parts} /> : <p>rendered body</p>}
    </details>
  )
}

test("a part's switch shows its slices under their paths, folds a supporting module, and leaves the part around it as it was", () => {
  const { container } = render(<Sample parts={changeParts(reply, 0)} />)
  const details = container.querySelector('details')!
  fireEvent.click(screen.getByRole('button', { name: 'raw' }))
  expect(details.open).toBe(false)
  expect(screen.getByRole('button', { name: 'raw' }).getAttribute('aria-pressed')).toBe('true')
  const panel = container.querySelector<HTMLElement>('.rawpanel')!
  expect(within(panel).getByText('c1.json')).toBeTruthy()
  const blocks = [...panel.querySelectorAll<HTMLElement>(':scope > .rp-part > .codeblock')]
  expect(blocks.map((block) => block.dataset.language)).toEqual(['json', 'json', 'python', 'json'])
  expect([...blocks[2].querySelectorAll('.hljs-keyword')].map((span) => span.textContent)).toContain('def')
  expect(blocks[2].querySelector('.cb-gutter')!.textContent).toBe('1\n2\n3\n4\n5')
  expect(panel.querySelectorAll('details.rp-fold')).toHaveLength(2)
  fireEvent.click(screen.getByRole('button', { name: 'rendered' }))
  expect(container.querySelector('.rawpanel')).toBeNull()
  expect(screen.getByText('rendered body')).toBeTruthy()
})

test('a part with nothing behind it says so', () => {
  render(<RawPanel parts={[]} />)
  expect(screen.getByText('The record holds nothing behind this part.')).toBeTruthy()
  expect(screen.getByText('from the run record')).toBeTruthy()
})

test('the language comes from the path, else from the text, and plain text is escaped', () => {
  expect(languageOf('a/b.py', '')).toBe('python')
  expect(languageOf('notes.TOML', '')).toBe('ini')
  expect(languageOf('Makefile', 'all:')).toBe('plaintext')
  expect(languageOf(undefined, '{"a": 1}')).toBe('json')
  expect(languageOf(undefined, '{not json')).toBe('plaintext')
  expect(highlighted('<b>&', 'plaintext')).toBe('&lt;b&gt;&amp;')
  expect(highlighted('x = "<b>"', 'python')).toContain('&lt;b&gt;')
})

test('a token over several lines keeps its colour on each, and JSON wraps with a number on every source line', () => {
  expect(lines('<span class="s">"""a\nb"""</span>\nx')).toEqual(['<span class="s">"""a</span>', '<span class="s">b"""</span>', 'x'])
  const { container } = render(<CodeBlock text={'{\n  "reason": "a long sentence"\n}'} language="json" />)
  const rows = [...container.querySelectorAll('.cb-row')]
  expect(rows.map((row) => row.querySelector('.cb-n')!.textContent)).toEqual(['1', '2', '3'])
  expect(rows[1].querySelector('.hljs-string')!.textContent).toBe('"a long sentence"')
  expect(container.querySelector('.cb-gutter')).toBeNull()
})

test('a module imports the generated modules it names, relative ones against its own folder', () => {
  const files = { 'pkg/a.py': 'from .b import x\nfrom ..top import y\nimport pkg.c, os\nfrom pkg import a\n', 'pkg/b.py': '', 'top.py': '', 'pkg/c.py': '', 'pkg/__init__.py': '' }
  expect(importsOf('pkg/a.py', files)).toEqual(['pkg/b.py', 'top.py', 'pkg/c.py', 'pkg/__init__.py'])
  expect(importsOf('top.py', files)).toEqual([])
  expect(importsOf('missing.py', files)).toEqual([])
})
