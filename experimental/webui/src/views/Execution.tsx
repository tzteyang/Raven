/* The Execution view: what a run spent, read from its execution ledger
   (/api/execution). Laid out as a cost dashboard: the headline figures, where
   the money went by part and by model, the loop's rounds against its stages,
   the run on a time axis with any stage opened as a waterfall, and the
   requests themselves. Unknown amounts stay unknown; stage figures include
   their descendants and are never added to each other. */

import { useEffect, useMemo, useState } from 'react'

import {
  PARTS,
  PART_LABEL,
  PART_NOTE,
  STAGE_ORDER,
  byModel,
  byPart,
  clock,
  compact,
  endOf,
  known,
  lanes,
  matrix,
  modelOf,
  money,
  parentsOf,
  partOf,
  percent,
  place,
  seconds,
  shares,
  under,
  waterfall,
  windowOf,
} from '../execution'
import { RavenMark } from './RavenMark'

import type { Breakdown, Cell, Operation, Part, Report, Window } from '../execution'
import type { CSSProperties, JSX, ReactNode } from 'react'

const POLL = 3000
const PAGE = 40

const stageTone = (stage: string): string => (STAGE_ORDER.includes(stage) ? stage : 'other')

function Amount({ value, unknown, title }: { value: string; unknown?: number; title?: string }): JSX.Element {
  return (
    <span className={value === 'unknown' ? 'ex-unknown' : 'ex-num'} title={title}>
      {value}
      {unknown ? <small className="ex-partial" title={`${unknown} without this figure reported`}>+{unknown}?</small> : null}
    </span>
  )
}

function Kpi({ label, value, note, tone }: { label: string; value: ReactNode; note?: ReactNode; tone?: string }): JSX.Element {
  return (
    <div className={`ex-kpi ${tone ?? ''}`.trim()}>
      <span className="ex-kpi-l">{label}</span>
      <strong className="ex-kpi-v">{value}</strong>
      {note ? <span className="ex-kpi-n">{note}</span> : null}
    </div>
  )
}

function Card({ title, aside, children, className = '' }: { title: string; aside?: ReactNode; children: ReactNode; className?: string }): JSX.Element {
  return (
    <section className={`ex-card ${className}`.trim()}>
      <header className="ex-card-hd">
        <h3>{title}</h3>
        {aside ? <span className="ex-card-aside">{aside}</span> : null}
      </header>
      {children}
    </section>
  )
}

function Empty({ children }: { children: ReactNode }): JSX.Element {
  return (
    <div className="ex-empty">
      <RavenMark size={40} className="ex-empty-mark" />
      <div>{children}</div>
    </div>
  )
}

function Shares({ rows, label }: { rows: Breakdown[]; label: (key: string) => string }): JSX.Element {
  const parts = shares(rows)
  const total = known(rows.map((row) => row.cost.value))
  return (
    <div className="ex-shares">
      <div className="ex-bar" role="img" aria-label="Share of reported cost">
        {parts.map((part) => (
          <span key={part.key} className="ex-bar-seg" data-key={part.key} style={{ width: `${part.share * 100}%` }} title={`${label(part.key)}: ${money(part.cost.value)}`} />
        ))}
      </div>
      <ul className="ex-share-list">
        {rows.map((row) => (
          <li key={row.key}>
            <i className="ex-swatch" data-key={row.key} />
            <span className="ex-share-k">{label(row.key)}</span>
            <span className="ex-share-n">{row.attempts}{row.external ? ` + ${row.external} ext` : ''}</span>
            <Amount value={money(row.cost.value)} unknown={row.cost.unknown} />
            <span className="ex-share-p">{percent(row.cost.value, total.value)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Models({ rows }: { rows: Breakdown[] }): JSX.Element {
  const top = Math.max(...rows.map((row) => row.cost.value ?? 0), 0)
  return (
    <div className="ex-table">
      <table>
        <thead>
          <tr>
            <th>Model</th>
            <th className="n">Requests</th>
            <th className="n">Input</th>
            <th className="n">Cache read</th>
            <th className="n">Output</th>
            <th className="n">Mean latency</th>
            <th className="n">Cost</th>
            <th className="ex-bar-col" aria-hidden="true" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <td className="ex-model"><code>{row.key}</code>{row.failed ? <span className="ex-flag bad">{row.failed} failed</span> : null}</td>
              <td className="n">{row.attempts}{row.external ? ` + ${row.external} ext` : ''}</td>
              <td className="n"><Amount value={compact(row.input.value)} unknown={row.input.unknown} /></td>
              <td className="n"><Amount value={compact(row.cacheRead.value)} unknown={row.cacheRead.unknown} /></td>
              <td className="n"><Amount value={compact(row.output.value)} unknown={row.output.unknown} /></td>
              <td className="n">{row.duration.value == null ? <Amount value="unknown" /> : seconds(row.duration.value / Math.max(1, row.attempts + row.external - row.duration.unknown))}</td>
              <td className="n"><Amount value={money(row.cost.value)} unknown={row.cost.unknown} /></td>
              <td className="ex-bar-col"><span className="ex-hbar" style={{ width: `${top ? ((row.cost.value ?? 0) / top) * 100 : 0}%` }} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Grid({ spans, selected, onSelect }: { spans: Operation[]; selected: ReadonlySet<string>; onSelect: (cell: Cell) => void }): JSX.Element {
  const grid = useMemo(() => matrix(spans), [spans])
  const top = Math.max(...grid.cells.map((cell) => cell.cost.value ?? 0), 0)
  const byRound = new Map(grid.rounds.map((round) => [round, known(grid.cells.filter((cell) => cell.round === round).map((cell) => cell.cost.value))]))
  const byStage = new Map(grid.stages.map((stage) => [stage, known(grid.cells.filter((cell) => cell.stage === stage).map((cell) => cell.cost.value))]))
  if (!grid.cells.length) return <p className="quiet">This run recorded no loop steps; its requests are listed below.</p>
  return (
    <div className="ex-table">
      <table className="ex-grid">
        <thead>
          <tr>
            <th>Round</th>
            {grid.stages.map((stage) => <th key={stage} className="n"><span className="ex-stage" data-stage={stageTone(stage)}>{stage}</span></th>)}
            <th className="n">Round total</th>
          </tr>
        </thead>
        <tbody>
          {grid.rounds.map((round) => (
            <tr key={round}>
              <th>{round === 0 ? 'Onboarding' : `Round ${round}`}</th>
              {grid.stages.map((stage) => {
                const cell = grid.cells.find((row) => row.round === round && row.stage === stage)
                if (!cell) return <td key={stage} className="n ex-cell-none" />
                const active = cell.ids.some((id) => selected.has(id))
                const heat = top && cell.cost.value != null ? Math.sqrt(cell.cost.value / top) : 0
                return (
                  <td key={stage} className="n">
                    <button
                      type="button"
                      className={`ex-cell ${cell.status}`}
                      aria-pressed={active}
                      style={{ '--heat': heat } as CSSProperties}
                      onClick={() => onSelect(cell)}
                      aria-label={`${stage}, ${round === 0 ? 'onboarding' : `round ${round}`}: ${cell.attempts} requests${cell.external ? ` + ${cell.external} external` : ''}, ${compact(cell.output.value)} output tokens, ${seconds(cell.duration.value)}`}
                    >
                      <span className="ex-cell-v"><Amount value={money(cell.cost.value)} unknown={cell.cost.unknown} /></span>
                      <span className="ex-cell-n">{cell.attempts}{cell.external ? `+${cell.external}` : ''} req · {compact(cell.output.value)} out</span>
                      {cell.status !== 'ok' ? <span className={`ex-cell-s ${cell.status}`}>{cell.status === 'running' ? 'unfinished' : cell.status}</span> : null}
                    </button>
                  </td>
                )
              })}
              <td className="n ex-sum"><Amount value={money(byRound.get(round)?.value)} unknown={byRound.get(round)?.unknown} /></td>
            </tr>
          ))}
          <tr className="ex-sum-row">
            <th>Stage total</th>
            {grid.stages.map((stage) => <td key={stage} className="n ex-sum"><Amount value={money(byStage.get(stage)?.value)} unknown={byStage.get(stage)?.unknown} /></td>)}
            <td />
          </tr>
        </tbody>
      </table>
    </div>
  )
}

function Timeline({ report, selected, running, onToggle }: { report: Report; selected: ReadonlySet<string>; running: boolean; onToggle: (span: Operation) => void }): JSX.Element {
  const now = Date.now()
  const window = useMemo(() => windowOf([...report.spans, ...report.attempts], running, now), [report, running, now])
  const rows = useMemo(() => lanes(report.spans), [report.spans])
  if (!window || !rows.length) return <p className="quiet">Nothing to place on a time axis yet.</p>
  const ticks = [0, 0.25, 0.5, 0.75, 1]
  return (
    <div className="ex-lanes">
      <div className="ex-axis" aria-hidden="true">
        {ticks.map((tick) => <span key={tick} style={{ left: `${tick * 100}%` }}>{seconds((window.end - window.start) * tick)}</span>)}
      </div>
      {rows.map((lane) => (
        <div key={lane.round ?? 'root'} className="ex-lane">
          <span className="ex-lane-l">{lane.round === null ? 'run' : lane.round === 0 ? 'onboarding' : `round ${lane.round}`}</span>
          <div className="ex-lane-t">
            {lane.spans.map((span) => {
              const at = place(span, window, now)
              return (
                <button
                  key={span.id}
                  type="button"
                  className={`ex-span ${span.status}`}
                  data-stage={stageTone(span.name)}
                  aria-pressed={selected.has(span.id)}
                  style={{ left: `${at.left * 100}%`, width: `${at.width * 100}%` }}
                  title={`${span.name}: ${money(span.totals?.cost_usd)}, ${span.totals?.attempts ?? 0} requests, ${seconds(span.duration_ms ?? endOf(span, now, window.end) - Date.parse(span.started_at))}${span.status === 'running' ? ' so far' : ''}`}
                  onClick={() => onToggle(span)}
                >
                  <span>{span.name}</span>
                </button>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}

function Waterfall({ report, selected, running }: { report: Report; selected: ReadonlySet<string>; running: boolean }): JSX.Element {
  const now = Date.now()
  const { rows, more } = useMemo(() => waterfall(report, selected), [report, selected])
  const window = useMemo<Window | null>(() => windowOf(rows.map((row) => row.op), running, now), [rows, running, now])
  if (!rows.length || !window) return <p className="quiet">Select a stage above to open it.</p>
  return (
    <div className="ex-wf">
      {rows.map(({ op, depth, ticks }) => {
        const at = place(op, window, now)
        return (
          <div key={op.id} className="ex-wf-row" style={{ '--depth': depth } as CSSProperties}>
            <span className="ex-wf-name" title={op.name}>
              <i className="ex-swatch" data-stage={stageTone(String(op.attributes.stage ?? op.name))} />
              {op.name}
              {op.attributes.session_key ? <small>{String(op.attributes.session_key)}</small> : null}
            </span>
            <span className="ex-wf-track">
              <span className={`ex-wf-bar ${op.status}`} style={{ left: `${at.left * 100}%`, width: `${at.width * 100}%` }} />
              {ticks.map((tick) => {
                const mark = place(tick, window, now)
                return <i key={tick.id} className={`ex-tick ${tick.status}`} data-part={partOf(tick)} style={{ left: `${mark.left * 100}%`, width: `${Math.max(mark.width * 100, 0.3)}%` }} title={`${modelOf(tick)}: ${money(tick.usage?.cost_usd)}, ${seconds(tick.duration_ms)}`} />
              })}
            </span>
            <span className="ex-wf-n">{(op.totals?.attempts ?? 0) + (op.totals?.external_calls ?? 0) ? <Amount value={money(op.totals?.cost_usd)} unknown={op.totals?.missing?.cost_usd} /> : <span className="quiet">no requests</span>}</span>
            <span className="ex-wf-n quiet">{seconds(op.duration_ms)}{op.status === 'running' ? ' so far' : ''}</span>
          </div>
        )
      })}
      {more ? <p className="quiet ex-more">{more} deeper operations not drawn.</p> : null}
    </div>
  )
}

function Requests({ rows, start, running }: { rows: Operation[]; start: number; running: boolean }): JSX.Element {
  const [part, setPart] = useState<'' | Part>('')
  const [status, setStatus] = useState('')
  const [model, setModel] = useState('')
  const [open, setOpen] = useState<string | null>(null)
  const [shown, setShown] = useState(PAGE)
  const filtered = rows.filter(
    (row) => (!part || partOf(row) === part) && (!status || row.status === status) && (!model || modelOf(row).toLowerCase().includes(model.toLowerCase())),
  )
  const status_ = (row: Operation): string => (row.status === 'running' && !running ? 'unfinished' : row.status)
  return (
    <>
      <div className="ex-filters">
        <label>
          <span className="sr">Part</span>
          <select value={part} onChange={(e) => setPart(e.target.value as '' | Part)}>
            <option value="">every part</option>
            {PARTS.map((name) => <option key={name} value={name}>{PART_LABEL[name]}</option>)}
          </select>
        </label>
        <label>
          <span className="sr">Status</span>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">any status</option>
            <option value="ok">ok</option>
            <option value="error">error</option>
            <option value="cancelled">cancelled</option>
            <option value="running">unfinished</option>
          </select>
        </label>
        <label>
          <span className="sr">Model</span>
          <input type="search" placeholder="model" value={model} onChange={(e) => setModel(e.target.value)} />
        </label>
        <span className="ex-count">{filtered.length === rows.length ? `${rows.length} requests` : `${filtered.length} of ${rows.length} requests`}</span>
      </div>
      <div className="ex-table">
        <table className="ex-req">
          <thead>
            <tr>
              <th>At</th>
              <th>Part</th>
              <th>Stage</th>
              <th>Model</th>
              <th>Status</th>
              <th className="n">Duration</th>
              <th className="n">Input</th>
              <th className="n">Cache</th>
              <th className="n">Output</th>
              <th className="n">Cost</th>
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, shown).map((row) => {
              const round = row.attributes.round_index
              return [
                <tr key={row.id} className={open === row.id ? 'open' : ''} onClick={() => setOpen(open === row.id ? null : row.id)}>
                  <td className="ex-at"><code>{seconds(Date.parse(row.started_at) - start)}</code></td>
                  <td><span className="ex-part" data-key={partOf(row)}>{PART_LABEL[partOf(row)]}</span></td>
                  <td className="ex-stagecell">{row.attributes.stage ? <span className="ex-stage" data-stage={stageTone(String(row.attributes.stage))}>{String(row.attributes.stage)}</span> : <span className="quiet">—</span>}{typeof round === 'number' ? <small>r{round}</small> : null}</td>
                  <td className="ex-model"><code>{modelOf(row) || 'unknown model'}</code>{row.kind === 'external' ? <span className="ex-flag">external</span> : null}</td>
                  <td><span className={`ex-status ${row.status}`}><i className="dot" />{status_(row)}{row.usage_complete === false && row.status !== 'running' ? ' · usage incomplete' : ''}</span></td>
                  <td className="n">{row.duration_ms == null ? <Amount value={running && row.status === 'running' ? `${seconds(Date.now() - Date.parse(row.started_at))} so far` : 'unknown'} /> : seconds(row.duration_ms)}</td>
                  <td className="n"><Amount value={compact(row.usage?.input_total_tokens)} /></td>
                  <td className="n"><Amount value={compact(row.usage?.cache_read_tokens)} /></td>
                  <td className="n"><Amount value={compact(row.usage?.output_tokens)} /></td>
                  <td className="n"><Amount value={money(row.usage?.cost_usd)} /></td>
                </tr>,
                open === row.id ? (
                  <tr key={`${row.id}-d`} className="ex-detail">
                    <td colSpan={10}>
                      <dl>
                        <dt>Operation</dt><dd><code>{row.id}</code> · {row.kind === 'external' ? 'external invocation' : 'request attempt'} · pid {String((row as Operation & { pid?: number }).pid ?? '')}</dd>
                        <dt>Provider</dt><dd>{String(row.attributes.provider ?? 'unknown')} · requested <code>{String(row.attributes.model ?? 'unknown')}</code>{row.served_model ? <> · served <code>{row.served_model}</code></> : null}</dd>
                        <dt>Response</dt><dd>{row.response_id ? <code>{row.response_id}</code> : 'no response id'}{row.http_status ? ` · HTTP ${row.http_status}` : ''}{row.error_type ? ` · ${row.error_type}` : ''}</dd>
                        <dt>Session</dt><dd>{row.attributes.session_key ? <code>{String(row.attributes.session_key)}</code> : 'none (simulation side)'}{row.attributes.turn_id ? <> · turn <code>{String(row.attributes.turn_id)}</code></> : null}</dd>
                        <dt>Tokens</dt><dd>fresh input {compact(row.usage?.input_tokens)} · cache read {compact(row.usage?.cache_read_tokens)} · cache write {compact(row.usage?.cache_write_tokens)} · reasoning {compact(row.usage?.reasoning_tokens)} · total {compact(row.usage?.total_tokens)}{row.usage?.inconsistent ? <span className="ex-flag bad">inconsistent counters</span> : null}</dd>
                        <dt>Money</dt><dd>reported {money(row.usage?.cost_usd)} · quota equivalent {money(row.usage?.quota_usd)}</dd>
                        <dt>When</dt><dd>{clock(row.started_at)}{row.ended_at ? ` to ${clock(row.ended_at)}` : ''}</dd>
                      </dl>
                    </td>
                  </tr>
                ) : null,
              ]
            })}
          </tbody>
        </table>
      </div>
      {filtered.length > shown ? <button type="button" className="ex-more-btn" onClick={() => setShown(shown + PAGE)}>Show {Math.min(PAGE, filtered.length - shown)} more</button> : null}
    </>
  )
}

export function Execution({ runId, running }: { runId: string; running: boolean }): JSX.Element {
  const [report, setReport] = useState<Report | null>(null)
  const [error, setError] = useState('')
  const [refreshed, setRefreshed] = useState<number | null>(null)
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set())

  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    setReport(null)
    setSelected(new Set())
    setError('')
    const load = async (): Promise<void> => {
      try {
        const response = await fetch(`/api/execution?run=${encodeURIComponent(runId)}`, { signal: controller.signal })
        const body = (await response.json()) as Report & { error?: string }
        if (!response.ok || !body.totals) throw new Error(body.error ?? 'Execution accounting is unavailable.')
        if (!controller.signal.aborted) {
          setReport(body)
          setError('')
          setRefreshed(Date.now())
        }
      } catch (reason) {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : String(reason))
      } finally {
        if (!controller.signal.aborted && running) timer = setTimeout(() => { void load() }, POLL)
      }
    }
    void load()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [runId, running])

  const parents = useMemo(() => (report ? parentsOf(report) : new Map<string, string | null>()), [report])
  const shown = useMemo(() => (report ? report.attempts.filter((row) => under(row, selected, parents)) : []), [report, selected, parents])
  const parts = useMemo(() => byPart(shown), [shown])
  const models = useMemo(() => byModel(shown), [shown])
  const window = useMemo(() => (report ? windowOf([...report.spans, ...report.attempts], running) : null), [report, running])

  const toggle = (span: Operation): void => {
    const next = new Set(selected)
    if (next.has(span.id)) next.delete(span.id)
    else next.add(span.id)
    setSelected(next)
  }
  const pick = (cell: Cell): void => {
    const all = cell.ids.every((id) => selected.has(id))
    setSelected(all ? new Set() : new Set(cell.ids))
  }

  if (!report) {
    return (
      <div className="ex">
        <Empty>{error ? <p role="alert" className="bad">{error}</p> : <p role="status">Loading execution accounting...</p>}</Empty>
      </div>
    )
  }
  if (!report.available) {
    return (
      <div className="ex">
        <Empty>
          <p>No execution accounting was recorded for this run.</p>
          <p className="quiet">Runs started before the ledger existed keep their spend in the record's own summary.</p>
        </Empty>
      </div>
    )
  }

  const totals = report.totals
  const root = report.spans.find((span) => !span.parent_id)
  const wall = window ? window.end - window.start : null
  const selectedSpans = report.spans.filter((span) => selected.has(span.id))
  const cacheShare = percent(totals.cache_read_tokens ?? null, totals.input_total_tokens ?? null)
  const flags: { text: string; tone: 'bad' | 'warn' | 'dim' }[] = [
    totals.unfinished ? { text: `${totals.unfinished} unfinished${running ? '' : ', outcome unknown'}`, tone: running ? 'dim' : 'warn' } : null,
    totals.failed ? { text: `${totals.failed} failed`, tone: 'bad' } : null,
    totals.missing.cost_usd ? { text: `${totals.missing.cost_usd} without a reported price`, tone: 'warn' } : null,
    totals.partial_usage ? { text: `${totals.partial_usage} without a final usage report`, tone: 'warn' } : null,
    totals.inconsistent_usage ? { text: `${totals.inconsistent_usage} with conflicting cache counters`, tone: 'bad' } : null,
    report.missing_parents.length ? { text: `${report.missing_parents.length} parent operations missing`, tone: 'bad' } : null,
  ].filter((flag): flag is { text: string; tone: 'bad' | 'warn' | 'dim' } => flag !== null)

  return (
    <div className="ex">
      <header className="ex-hd">
        <RavenMark size={34} />
        <div className="ex-hd-t">
          <h2>Execution ledger</h2>
          <p className="ex-hd-sub">
            <code>{report.run_ids?.join(', ') || runId}</code>
            {root ? <> · {root.name} started {clock(root.started_at)}</> : null}
            {running ? <span className="ex-live"><i className="dot" />auto-updating{refreshed ? ` · ${new Date(refreshed).toLocaleTimeString()}` : ''}</span> : <span className="quiet"> · recorded</span>}
          </p>
        </div>
        <div className="ex-flags">
          {flags.length ? flags.map((flag) => <span key={flag.text} className={`ex-flag-chip ${flag.tone}`}>{flag.text}</span>) : <span className="ex-flag-chip good">every request priced and finished</span>}
        </div>
      </header>
      {error ? <p role="alert" className="ex-stale">Refresh failed: {error} Showing the last snapshot received.</p> : null}

      <div className="ex-kpis">
        <Kpi
          label="Reported cost"
          tone="amber"
          value={<Amount value={money(totals.cost_usd)} />}
          note={<>{totals.missing.cost_usd ? `${totals.missing.cost_usd} calls unpriced · ` : ''}{totals.quota_usd != null ? `quota equivalent ${money(totals.quota_usd)}, not counted` : 'provider-reported, never estimated'}</>}
        />
        <Kpi
          label="Requests"
          value={<>{totals.attempts.toLocaleString()}{totals.external_calls ? <small> + {totals.external_calls} external</small> : null}</>}
          note={<>{totals.failed} failed · {totals.unfinished} unfinished · {seconds(totals.attempt_duration_ms)} in flight</>}
        />
        <Kpi
          label="Input tokens"
          value={<Amount value={compact(totals.input_total_tokens)} unknown={totals.missing.input_total_tokens} />}
          note={<>{cacheShare ? `${cacheShare} served from cache` : 'cache share unknown'}{totals.cache_write_tokens ? ` · ${compact(totals.cache_write_tokens)} written` : ''}</>}
        />
        <Kpi
          label="Output tokens"
          value={<Amount value={compact(totals.output_tokens)} unknown={totals.missing.output_tokens} />}
          note={totals.reasoning_tokens ? <>{compact(totals.reasoning_tokens)} of them reasoning</> : <>reasoning, when reported, is included</>}
        />
        <Kpi
          label="Wall time"
          value={wall == null ? <Amount value="unknown" /> : seconds(wall)}
          note={running ? 'so far' : root?.status === 'running' ? 'the run never closed its record' : 'first start to last end'}
        />
      </div>

      <div className="ex-two">
        <Card title="Where the money went" aside={selected.size ? `within ${selectedSpans.map((span) => span.name).join(', ')}` : 'whole run'}>
          {parts.length ? <Shares rows={parts} label={(key) => PART_LABEL[key as Part]} /> : <p className="quiet">No requests here.</p>}
          <ul className="ex-notes">
            {parts.map((row) => <li key={row.key}><b>{PART_LABEL[row.key as Part]}</b> {PART_NOTE[row.key as Part]}</li>)}
          </ul>
        </Card>
        <Card title="By model" aside={`${models.length} model${models.length === 1 ? '' : 's'}`}>
          {models.length ? <Models rows={models} /> : <p className="quiet">No requests here.</p>}
        </Card>
      </div>

      <Card title="Rounds and stages" aside="reported cost per step; click a cell to open it">
        <Grid spans={report.spans} selected={selected} onSelect={pick} />
      </Card>

      <Card
        title="Timeline"
        aside={selected.size ? <button type="button" className="ex-clear" onClick={() => setSelected(new Set())}>Show the whole run</button> : 'click a stage to open its operations'}
      >
        <Timeline report={report} selected={selected} running={running} onToggle={toggle} />
        {selected.size ? <Waterfall report={report} selected={selected} running={running} /> : null}
      </Card>

      <Card title="Requests" aside={selected.size ? `under ${selectedSpans.map((span) => span.name).join(', ')}` : 'every request of the run'}>
        <Requests rows={shown} start={window?.start ?? 0} running={running} />
      </Card>

      <p className="ex-foot quiet">
        Amounts are what providers reported; an unknown figure is not a zero. Input counts include cache reads and writes.
        A stage's figures include every request under it, so nested figures are never added together. Research invocations
        report usage for the whole invocation; their internal requests are not observable.
      </p>
    </div>
  )
}
