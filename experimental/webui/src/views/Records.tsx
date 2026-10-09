import { Fold } from './Badges'

import type { Execution, RecordRow } from '../model'
import type { JSX } from 'react'

/** One step of a sub-harness execution as the server previews it (webui/studio.py `child_steps`): a tool call with
    its result, or something the sub-harness said. */
interface ChildStep {
  tool?: string
  arguments?: string
  result?: string
  ok?: boolean
  text?: string
}

/* A sub-harness the turn handed work to, read as its own steps: each tool call with its result, and its replies. */
function ChildWork({ row }: { row: RecordRow }): JSX.Element | null {
  const steps = Array.isArray(row['steps']) ? (row['steps'] as ChildStep[]) : []
  if (steps.length === 0) return null
  const calls = steps.filter((step) => step.tool !== undefined).length
  const omitted = Number(row['steps_omitted'] ?? 0)
  return (
    <Fold
      className="act child-work"
      summary={
        <>
          <span className="k">{String(row['harness'] ?? 'sub-harness')}</span>
          <span className="g">worked through {calls} tool call{calls === 1 ? '' : 's'}{omitted > 0 ? `, ${omitted} later steps not shown` : ''}</span>
        </>
      }
    >
      {() => (
        <div className="child-steps">
          {steps.map((step, i) =>
            step.tool !== undefined ? (
              <Fold
                key={i}
                className={`ltool ${step.ok === false ? 'failed' : 'done'}`}
                summary={
                  <>
                    <span className="dot" />
                    <span className="nm">{step.tool || 'tool'}</span>
                    <span className="args">{step.arguments}</span>
                    {step.ok === false ? <span className="st">failed</span> : null}
                  </>
                }
              >
                {() => <pre>{step.result || 'No result was recorded.'}</pre>}
              </Fold>
            ) : (
              <div key={i} className="lmsg"><span className="k">said</span><p>{step.text}</p></div>
            ),
          )}
        </div>
      )}
    </Fold>
  )
}

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
      {execution.records.filter((row) => row.kind === 'child.execution').map((row, i) => <ChildWork key={i} row={row} />)}
      {[...errors].map(([text, count]) => <p key={text} className="err">{text}{count > 1 ? ` ×${count}` : ''}</p>)}
    </>
  )
}
