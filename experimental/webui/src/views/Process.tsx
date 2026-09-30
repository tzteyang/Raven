/* A playbook node's sub-agent at work: a running tally on the node card, and
   the process panel below the graph with the node's prompt, its steps in
   order (tool calls, messages, thoughts folded, stderr, questions and
   approvals), its output and the judge's verdict. A running node is re-read
   on the live view's cadence until its graph says it has finished. */

import { memo, useEffect, useState } from 'react'

import { NO_SUCH_NODE, loadNodeProcess } from '../api'
import {
  PROCESS_POLL,
  SOURCE_HINT,
  SOURCE_LABEL,
  answerLabel,
  firstLine,
  grouping,
  plural,
  ranFor,
  sources,
  tally,
  thoughtLabel,
  toolLine,
  toolState,
  wasCut,
  when,
} from '../process'
import { Clamp, Fold } from './Badges'
import { Markdown } from './Markdown'

import type { NodeQuery } from '../api'
import type { NodeProcess, ProcessSource, ProcessStep } from '../process'
import type { JSX } from 'react'

interface Loaded {
  data: NodeProcess | null
  error: string
  loading: boolean
}

/* Re-read while `live`; once the graph says the node is over, read again until
   the record's transcript has landed, at most twice, since it may be written
   a moment after the node is marked finished. */
export function useNodeProcess(runId: string, dag: string, node: string, live: boolean, query: NodeQuery = {}): Loaded {
  const [state, setState] = useState<Loaded>({ data: null, error: '', loading: true })
  const { summary = false, source = 'auto', attempt = null } = query
  useEffect(() => {
    let alive = true
    let timer: ReturnType<typeof setTimeout> | undefined
    let followups = 0
    setState((prev) => ({ ...prev, loading: true }))
    const tick = async () => {
      let settled = false
      try {
        const data = await loadNodeProcess(runId, dag, node, { summary, source, attempt })
        if (!alive) return
        settled = data.source === 'transcript'
        setState({ data, error: '', loading: false })
      } catch (e) {
        if (!alive) return
        setState((prev) => ({ ...prev, error: (e as Error).message, loading: false }))
      }
      if (!alive) return
      if (live) timer = setTimeout(tick, PROCESS_POLL)
      else if (!settled && !summary && source === 'auto' && followups < 2) {
        followups += 1
        timer = setTimeout(tick, PROCESS_POLL)
      }
    }
    tick()
    return () => {
      alive = false
      if (timer) clearTimeout(timer)
    }
  }, [runId, dag, node, live, summary, source, attempt])
  return state
}

/** The node card's running tally, re-read while the node runs. */
export function NodeTally({ runId, dag, node, status }: { runId: string; dag: string; node: string; status: string }): JSX.Element | null {
  const { data } = useNodeProcess(runId, dag, node, status === 'running', { summary: true })
  if (!data) return null
  const line = tally(status, data)
  return <div className="tally" title={data.last ?? line}>{line.split(' · ').slice(1).join(' · ')}</div>
}

/** An interrupted node's frozen duration, read once from its own last step when the traces are available. */
export function InterruptedFor({ runId, dag, node, startedAt, endedAt, format }: { runId?: string; dag: string; node: string; startedAt: number | null; endedAt: number | null; format: (ms: number | null) => string }): JSX.Element {
  const { data } = useNodeProcess(runId ?? '', dag, node, false, { summary: true })
  const ran = ranFor(startedAt, endedAt, runId ? data?.last_at : null)
  return <span className="dur" title="Until the last thing it wrote before the run stopped">{ran === null ? '' : format(ran)}</span>
}

function ToolStep({ step, started, over }: { step: ProcessStep; started: number | null; over: boolean }): JSX.Element {
  const state = toolState(step, over)
  const { name, detail } = toolLine(step)
  const label = state === 'done' ? 'done' : state === 'unknown' ? step.status ?? '' : state
  return (
    <Fold
      className={`ltool pstep ${state}`}
      summary={
        <>
          <span className="dot" />
          <span className="nm">{name}</span>
          <span className="args" title={detail}>{detail}</span>
          <span className="st">{label}</span>
          {step.time ? <span className="at">{when(step.time, started)}</span> : null}
        </>
      }
    >
      {() => (
        <div className="pbody">
          {step.input ? (
            <>
              <p className="k">Arguments</p>
              <pre>{step.input}</pre>
            </>
          ) : null}
          <p className="k">
            Result
            {step.result_length && step.result && step.result_length > step.result.length ? ` · first ${grouping(step.result.length)} of ${grouping(step.result_length)} chars` : ''}
          </p>
          <pre>{step.result || (state === 'running' ? 'Still running.' : state === 'interrupted' ? 'The run stopped before this call returned.' : 'No result was recorded.')}</pre>
        </div>
      )}
    </Fold>
  )
}

function Step({ step, started, over }: { step: ProcessStep; started: number | null; over: boolean }): JSX.Element {
  const at = step.time ? <span className="at">{when(step.time, started)}</span> : null
  switch (step.kind) {
    case 'tool':
      return <ToolStep step={step} started={started} over={over} />
    case 'message':
      return (
        <div className="pmsg">
          <div className="pmsg-hd"><span className="k">said</span>{at}</div>
          <Clamp long={(step.text ?? '').length > 900}><Markdown text={step.text ?? ''} /></Clamp>
        </div>
      )
    case 'thought':
      return (
        <Fold
          className="pthought"
          summary={
            <>
              <span className="k">{thoughtLabel(step)}</span>
              <span className="pre">{firstLine(step.text)}</span>
              {at}
            </>
          }
        >
          {() => (
            <div className="pbody">
              <p className="txt">{step.text}</p>
              {wasCut(step) ? <p className="quiet small">The reply carries the first {grouping(step.text?.length ?? 0)} characters.</p> : null}
            </div>
          )}
        </Fold>
      )
    case 'input':
      return (
        <div className="pmsg input">
          <div className="pmsg-hd"><span className="k">message from the parent</span>{at}</div>
          <Clamp long={(step.text ?? '').length > 600}><p className="txt">{step.text}</p></Clamp>
        </div>
      )
    case 'stderr': {
      const lines = (step.text ?? '').split('\n').length
      return (
        <Fold
          className={`perr ${step.level ?? 'info'}`}
          summary={
            <>
              <span className="k">stderr · {plural(lines, 'line')}</span>
              <span className="pre">{firstLine(step.text)}</span>
              {at}
            </>
          }
        >
          {() => <pre>{step.text}</pre>}
        </Fold>
      )
    }
    case 'permission':
    case 'question':
      return (
        <p className={`pask ${step.kind}`}>
          <span className="k">{step.kind === 'permission' ? 'asked for approval' : 'asked the user'}</span>
          <span className="txt" title={step.text}>{step.text}</span>
          <span className="st">{answerLabel(step)}</span>
          {at}
        </p>
      )
    case 'plan':
      return <pre className="pplan">{step.text}</pre>
    case 'error':
      return <p className="err">{step.text}{at}</p>
  }
}

function SourceSwitch({ process, chosen, onChoose }: { process: NodeProcess; chosen: ProcessSource | 'auto'; onChoose: (source: ProcessSource | 'auto') => void }): JSX.Element | null {
  const offered = sources(process)
  if (offered.length < 2) {
    return <span className="psrc one" title={SOURCE_HINT[process.source]}>{SOURCE_LABEL[process.source]}</span>
  }
  return (
    <span className="psrc" role="group" aria-label="Where the steps are read from">
      {offered.map((source) => (
        <button
          key={source}
          className={process.source === source ? 'on' : ''}
          title={SOURCE_HINT[source]}
          aria-pressed={process.source === source}
          onClick={() => onChoose(chosen !== 'auto' && source === process.source ? 'auto' : source)}
        >
          {SOURCE_LABEL[source]}
        </button>
      ))}
    </span>
  )
}

export interface PanelProps {
  runId: string
  dag: string
  node: string
  subagent: string | null
  /** The node's status as the graph has it; the panel re-reads while it says running. */
  status: string
  /** The whole run has stopped, so a call still open is interrupted rather than running. */
  over: boolean
  summary: string | null
  onClose: () => void
}

function PanelBody({ runId, dag, node, subagent, status, summary, over, onClose }: PanelProps): JSX.Element {
  const [source, setSource] = useState<ProcessSource | 'auto'>('auto')
  const [attempt, setAttempt] = useState<number | null>(null)
  const running = status === 'running'
  const { data, error, loading } = useNodeProcess(runId, dag, node, running, { source, attempt })
  const steps = data?.steps ?? []
  const started = data?.started_at ?? null
  return (
    <section className="nproc" aria-label={`Process of ${node}`}>
      <div className="nproc-hd">
        <span className={`dot ${running ? 'run' : status === 'completed' ? 'ok' : status === 'failed' ? 'bad' : status === 'interrupted' ? 'int' : ''}`} />
        <code className="nm">{node}</code>
        {subagent ? <span className="who">{subagent}</span> : null}
        {data?.lane ? <span className="lane">{data.lane === 'acp' ? 'external sub-harness' : 'in-process'}</span> : null}
        <span className="st">{data ? tally(status, data, 60) : status}</span>
        <span className="grow" />
        {data ? <SourceSwitch process={data} chosen={source} onChoose={setSource} /> : null}
        {data && data.attempts.length > 1 ? (
          <select className="patt" value={attempt ?? ''} onChange={(e) => setAttempt(e.target.value ? Number(e.target.value) : null)} aria-label="Attempt">
            <option value="">last attempt</option>
            {data.attempts.map((n) => <option key={n} value={n}>attempt {n}</option>)}
          </select>
        ) : null}
        <button className="pclose" onClick={onClose} aria-label="Close the process">Close</button>
      </div>
      {summary || data?.title ? <p className="nproc-sum">{summary}{summary && data?.title ? ' · ' : ''}{data?.title ? <span className="quiet">{data.title}</span> : null}</p> : null}
      {error === NO_SUCH_NODE && !data ? (
        <p className="quiet">Nothing of this node was kept: the record's agent home has no playbook run with this id, as in runs recorded before node transcripts were kept.</p>
      ) : error && !data ? (
        <p className="quiet">
          The server did not answer /api/node ({error}). A server started before the process view existed needs a restart of experimental.webui.serve.
        </p>
      ) : null}
      {error && data ? <p className="bad small">Refreshing failed: {error}</p> : null}
      {!data && loading ? <p className="quiet">Reading the node's traces...</p> : null}
      {data?.error ? <div className="failed"><Markdown text={data.error} /></div> : null}
      {data?.prompt ? (
        <Fold className="fold psec" summary={`Prompt · ${grouping(data.prompt_length)} chars${data.prompt_source ? ` · from the ${data.prompt_source}` : ''}`}>
          {() => <div className="pdoc"><Markdown text={data.prompt ?? ''} /></div>}
        </Fold>
      ) : null}
      {data ? (
        <div className="ptl">
          {data.omitted ? <p className="quiet small">{plural(data.omitted, 'earlier step')} not shown.</p> : null}
          {steps.length === 0 ? (
            <p className="quiet small">
              {data.source === 'none' ? (running ? 'The sub-agent has not written anything yet.' : 'No trace of this node was found in the record or the state root.') : 'No step recorded yet.'}
            </p>
          ) : null}
          {steps.map((step, i) => <Step key={`${step.kind}-${step.id ?? ''}-${i}`} step={step} started={started} over={over} />)}
          {running && !over ? <p className="pwork"><span className="dot" />working · re-read every {PROCESS_POLL / 1000} s from the {SOURCE_LABEL[data.source]}</p> : null}
          {status === 'interrupted' ? <p className="pstop">The run stopped before this node finished; what is shown is all it wrote.</p> : null}
        </div>
      ) : null}
      {data?.output ? (
        <Fold className="fold psec" open summary={`Output · ${grouping(data.output_length)} chars`}>
          {() => (
            <div className="pdoc">
              <Clamp long={data.output_length > 3000}><Markdown text={data.output ?? ''} /></Clamp>
            </div>
          )}
        </Fold>
      ) : null}
      {data?.verdicts.map((verdict, i) => (
        <div key={i} className={`pverdict ${verdict.outcome === 'accomplished' ? 'ok' : 'bad'}`}>
          <p><span className="k">Judge</span><span className="v">{verdict.outcome}</span></p>
          {verdict.reason ? (
            <Fold className="fold small" summary="Why">
              {() => <Markdown text={verdict.reason} />}
            </Fold>
          ) : null}
        </div>
      ))}
    </section>
  )
}

/* Memoised on its props so the live view's one-second clock does not re-render the output's Markdown. */
export const NodeProcessPanel = memo(function NodeProcessPanel(props: PanelProps): JSX.Element {
  return <PanelBody key={`${props.runId}|${props.dag}|${props.node}`} {...props} />
})
