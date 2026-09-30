import { Fold } from './Badges'

import type { Execution } from '../model'
import type { JSX } from 'react'

/* What the host recorded for one turn: a quiet mono row of kinds, the rows themselves behind it. */
export function Records({ execution }: { execution: Execution }): JSX.Element {
  const counts = new Map<string, number>()
  for (const row of execution.records) counts.set(row.kind, (counts.get(row.kind) ?? 0) + 1)
  const errors = new Map<string, number>()
  for (const row of execution.records) {
    if (row.kind.endsWith('.error')) {
      const text = String(row['error'] ?? row.kind).replace(/^\w+Error: /, '')
      errors.set(text, (errors.get(text) ?? 0) + 1)
    }
  }
  return (
    <>
      <Fold
        className="act"
        summary={
          <>
            <span className="g">{execution.turn_id.slice(0, 8)}</span>
            {[...counts.entries()].map(([kind, count]) => (
              <span key={kind} className={kind.endsWith('.error') ? 'k bad' : 'k'}>
                {kind}{count > 1 ? ` ×${count}` : ''}
              </span>
            ))}
            <span className="g">{execution.records.length} record{execution.records.length === 1 ? '' : 's'}</span>
          </>
        }
      >
        {() => <pre>{JSON.stringify(execution.records, null, 2)}</pre>}
      </Fold>
      {[...errors].map(([text, count]) => <p key={text} className="err">{text}{count > 1 ? ` ×${count}` : ''}</p>)}
    </>
  )
}
