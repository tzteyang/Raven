import { useEffect, useState } from 'react'

import { loadTurnRecords } from '../api'
import { Fold } from './Badges'
import { CodeBlock, copyText } from './Code'

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

const said = (value: unknown): string => (typeof value === 'string' ? value : '')

/** A record's line in the list: what the row says it was about, from the fields most kinds carry. */
function about(row: RecordRow): string {
  const event = row['event'] && typeof row['event'] === 'object' ? (row['event'] as Record<string, unknown>) : {}
  const parts = [said(row['operation']), said(row['source']), said(row['event_type']), said(event.name), said(event.phase), said(row['method']), said(row['harness'])]
  const text = said(row['error'])
  return [...parts.filter(Boolean), text.slice(0, 120)].filter(Boolean).join(' · ')
}

const size = (row: RecordRow): string => {
  const length = JSON.stringify(row).length
  return length < 1024 ? `${length} B` : length < 1024 * 1024 ? `${(length / 1024).toFixed(1)} KB` : `${(length / 1024 / 1024).toFixed(1)} MB`
}

/* A turn's records one line each, in the order they happened; a line opens into that record as highlighted JSON. */
function RecordList({ rows, turn }: { rows: RecordRow[]; turn: string }): JSX.Element {
  const [copied, setCopied] = useState(false)
  const copy = () => void copyText(JSON.stringify(rows, null, 2)).then(() => { setCopied(true); window.setTimeout(() => setCopied(false), 1200) })
  return (
    <div className="rec-list">
      <p className="rec-hd">
        <span className="dim">{rows.length} record{rows.length === 1 ? '' : 's'} of turn <code>{turn}</code></span>
        <button className="cb-copy" onClick={copy}>{copied ? 'copied' : 'copy all as JSON'}</button>
      </p>
      <ol>
        {rows.map((row, i) => (
          <li key={i}>
            <Fold className="rec" summary={<><span className="rec-i">{i + 1}</span><span className={row.kind.endsWith('.error') ? 'rec-k bad' : 'rec-k'}>{row.kind}</span><span className="rec-about">{about(row)}</span><span className="rec-size">{size(row)}</span></>}>
              {() => <CodeBlock text={JSON.stringify(row, null, 2)} language="json" title={<code>{row.kind}</code>} />}
            </Fold>
          </li>
        ))}
      </ol>
    </div>
  )
}

/* A turn's whole records, fetched when the fold opens if the run view's copy was cut; until then, or when the server
   cannot give them, the copy the page holds, said to be cut. */
function WholeRecords({ execution, runId }: { execution: Execution; runId?: string }): JSX.Element {
  const fetching = Boolean(execution.records_cut && runId)
  const [whole, setWhole] = useState<RecordRow[] | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  useEffect(() => {
    if (!fetching) return
    let live = true
    loadTurnRecords(runId!, execution.turn_id).then((rows) => { if (live) setWhole(rows) }, (error: Error) => { if (live) setFailed(error.message) })
    return () => { live = false }
  }, [fetching, runId, execution.turn_id])
  if (fetching && whole === null && failed === null) return <p className="quiet small">Loading the turn&apos;s whole records...</p>
  return (
    <>
      {execution.records_cut && whole === null ? <p className="warn small">Showing the page&apos;s cut copy{failed ? `: ${failed}` : ''}.</p> : null}
      <RecordList rows={whole ?? execution.records} turn={execution.turn_id} />
    </>
  )
}

/* What the host recorded for one turn: a quiet mono row of kinds, the rows themselves behind it. */
export function Records({ execution, runId }: { execution: Execution; runId?: string }): JSX.Element {
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
        {() => <WholeRecords execution={execution} runId={runId} />}
      </Fold>
      {execution.records.filter((row) => row.kind === 'child.execution').map((row, i) => <ChildWork key={i} row={row} />)}
      {[...errors].map(([text, count]) => <p key={text} className="err">{text}{count > 1 ? ` ×${count}` : ''}</p>)}
    </>
  )
}
