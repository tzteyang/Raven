/* A line diff for showing a Harness file before and after a curation, with
   unchanged stretches folded down to a few lines of context. Files the Curator
   writes are at most a few thousand lines, so a longest-common-subsequence
   table is small enough; past LIMIT lines the two sides are shown as a whole
   replacement instead. */

export interface DiffLine {
  op: ' ' | '+' | '-'
  text: string
}

export type Hunk = { kind: 'lines'; lines: DiffLine[] } | { kind: 'fold'; count: number }

const LIMIT = 4000

export function lineDiff(before: string, after: string): DiffLine[] {
  const a = before === '' ? [] : before.split('\n')
  const b = after === '' ? [] : after.split('\n')
  if (a.length > LIMIT || b.length > LIMIT) {
    return [...a.map((text) => ({ op: '-' as const, text })), ...b.map((text) => ({ op: '+' as const, text }))]
  }
  const n = a.length
  const m = b.length
  const width = m + 1
  const table = new Uint32Array((n + 1) * width)
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      table[i * width + j] = a[i] === b[j] ? table[(i + 1) * width + j + 1] + 1 : Math.max(table[(i + 1) * width + j], table[i * width + j + 1])
    }
  }
  const out: DiffLine[] = []
  let i = 0
  let j = 0
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      out.push({ op: ' ', text: a[i] })
      i++
      j++
    } else if (table[(i + 1) * width + j] >= table[i * width + j + 1]) {
      out.push({ op: '-', text: a[i++] })
    } else {
      out.push({ op: '+', text: b[j++] })
    }
  }
  while (i < n) out.push({ op: '-', text: a[i++] })
  while (j < m) out.push({ op: '+', text: b[j++] })
  return out
}

/** The diff with every unchanged run longer than twice `context` folded to a count. */
export function hunks(lines: DiffLine[], context = 3): Hunk[] {
  const out: Hunk[] = []
  let current: DiffLine[] = []
  let run: DiffLine[] = []
  const flush = (last: boolean) => {
    const first = out.length === 0 && current.length === 0
    const head = first ? 0 : context
    const tail = last ? 0 : context
    if (run.length > head + tail + 1) {
      current.push(...run.slice(0, head))
      if (current.length) out.push({ kind: 'lines', lines: current })
      out.push({ kind: 'fold', count: run.length - head - tail })
      current = run.slice(run.length - tail)
    } else {
      current.push(...run)
    }
    run = []
  }
  for (const line of lines) {
    if (line.op === ' ') {
      run.push(line)
    } else {
      flush(false)
      current.push(line)
    }
  }
  flush(true)
  if (current.length) out.push({ kind: 'lines', lines: current })
  return out
}

export function counts(lines: DiffLine[]): { added: number; removed: number } {
  let added = 0
  let removed = 0
  for (const line of lines) {
    if (line.op === '+') added++
    else if (line.op === '-') removed++
  }
  return { added, removed }
}
