/* The side pane's bodies besides a trial: one strategy target before and
   after a curation, the input inspector's three views of a round, what the
   Curator submitted at each stage as it was recorded, the run's ledger (did
   each requirement hold after its revision) with its typed history and the
   Curator's open questions, and the compartment audit of boundaries.jsonl.
   The pane itself (header, full-width toggle, Esc) is Studio.tsx's. */

import { Fragment, useState } from 'react'

import { identityLine } from '../../attribution'
import { hooks, strategyOf } from '../../mechanism'
import { T } from '../copy'
import { counts, hunks, lineDiff } from '../diff'
import { LOOSE, artifactOf, targetChanges, targetState } from '../harness'
import { columns } from '../inspect'
import { Fold, HandoverChip, Icon, Json, StateChip, Target } from './bits'

import type { JSX } from 'react'
import type { Boundaries, BoundaryRow, Signal } from '../../model'
import type { DocumentChange } from '../harness'
import type { CurationView, Output, ProcessEntry, Scope, Thread } from '../types'

function DocumentDiff({ change }: { change: DocumentChange }): JSX.Element {
  const lines = lineDiff(change.before ?? '', change.after ?? '')
  const { added, removed } = counts(lines)
  const status = change.before === null ? T.added : change.after === null ? T.removed : added || removed ? null : T.unchanged
  return (
    <div className="st-doc">
      <p className="st-doch">
        <code>{change.path}</code>
        {status ? <span className="st-dstat">{status}</span> : <span className="st-dstat"><b className="a">+{added}</b> <b className="d">−{removed}</b></span>}
      </p>
      {(added > 0 || removed > 0) && (
        <div className="st-diff">
          {hunks(lines).map((hunk, i) =>
            hunk.kind === 'fold' ? (
              <div key={i} className="st-dfold">{T.unchangedLines(hunk.count)}</div>
            ) : (
              hunk.lines.map((line, j) => (
                <div key={`${i}-${j}`} className="st-dl" data-op={line.op}>
                  <span className="op">{line.op === ' ' ? '' : line.op}</span>
                  <span>{line.text || ' '}</span>
                </div>
              ))
            ),
          )}
        </div>
      )}
    </div>
  )
}

export function DiffPane({ view, scope, root, target }: { view: CurationView; scope: string; root: boolean; target: string }): JSX.Element {
  const before = artifactOf(view.before, scope, root)
  const after = artifactOf(view.after, scope, root)
  const changes = targetChanges(target, before, after)
  const strategy = strategyOf(target)
  const bound = target === LOOSE ? [] : hooks(target, after.values[target] ?? before.values[target])
  const state = targetState(target, before, after)
  const changed = changes.filter((change) => change.before !== change.after)
  const same = changes.filter((change) => change.before === change.after)
  return (
    <>
      <div className="st-diffhead">
        <Target name={target} />
        <span className="st-meta">{T.diffVersions(view.from, view.to)} · {state === 'new' ? T.mapLegendNew : state === 'kept' ? T.mapLegendKept : state === 'removed' ? T.removed : T.mapLegendChanged}</span>
      </div>
      {(strategy || bound.length > 0) && (
        <dl className="st-kv">
          {strategy && <><dt>{T.ownsLabel}</dt><dd>{T.owns[strategy]}</dd></>}
          {bound.map((hook) => (
            <Fragment key={hook.name}>
              <dt>{T.hooks[hook.name] ?? hook.name}</dt>
              <dd><code>{hook.value}</code></dd>
            </Fragment>
          ))}
        </dl>
      )}
      {changed.map((change) => <DocumentDiff key={change.path} change={change} />)}
      {same.length > 0 && (
        <Fold summary={`${T.unchanged} · ${same.map((change) => change.path).join(', ')}`}>
          {same.map((change) => (
            <div key={change.path} className="st-doc">
              <p className="st-doch"><code>{change.path}</code></p>
              <Json value={change.after ?? ''} max={320} />
            </div>
          ))}
        </Fold>
      )}
    </>
  )
}

/* A record shown as its top-level fields, each folded under its name and size,
   so the three columns can be compared field by field rather than as one dump. */
const branches = (value: unknown): value is object => !!value && typeof value === 'object' && Object.keys(value).length > 0

/** A record's fields, folded by key; `deep` unfolds nested objects and lists the same way, so a string at any depth
    (a source file, a prose answer) reads as text rather than as an escaped JSON value. */
function Fields({ value, open = [], deep = false }: { value: unknown; open?: string[]; deep?: boolean }): JSX.Element {
  if (!branches(value) || (!deep && Array.isArray(value))) return <Json value={value} max={520} />
  const size = (item: unknown): string =>
    Array.isArray(item) ? `[${item.length}]` : item && typeof item === 'object' ? `{${Object.keys(item).length}}` : typeof item === 'string' ? T.chars(item.length) : String(item)
  return (
    <div className="st-fields">
      {Object.entries(value).map(([key, item]) => (
        <Fold key={key} open={open.includes(key)} summary={<><code>{key}</code><span className="st-meta">{size(item)}</span></>}>
          {deep && branches(item) ? <Fields value={item} open={open} deep /> : <Json value={item} max={420} />}
        </Fold>
      ))}
    </div>
  )
}

function OutputBlock({ output, open }: { output: Output; open: boolean }): JSX.Element {
  const [text, setText] = useState(false)
  const [copied, setCopied] = useState(false)
  const raw = JSON.stringify(output.value, null, 2) ?? String(output.value)
  const copy = () => {
    navigator.clipboard?.writeText(raw).then(
      () => {
        setCopied(true)
        window.setTimeout(() => setCopied(false), 1500)
      },
      () => undefined,
    )
  }
  return (
    <details className="st-output" open={open}>
      <summary>
        <Icon name="chevron" size={12} className="st-car" />
        {output.stage && <span className="st-rstage">{T.stages[output.stage] ?? output.stage}</span>}
        <b>{T.outputLabel[output.event] ?? output.event}</b>
        <code>{output.event}</code>
        <span className="st-meta">{T.chars(raw.length)}</span>
      </summary>
      <div className="st-output-b">
        <div className="st-output-bar">
          <div className="st-seg2" role="tablist">
            <button type="button" role="tab" aria-selected={!text} onClick={() => setText(false)}>{T.viewTree}</button>
            <button type="button" role="tab" aria-selected={text} onClick={() => setText(true)}>{T.viewText}</button>
          </div>
          <span className="grow" />
          <button type="button" className="st-link" onClick={copy}>{copied ? T.copied : T.copy}</button>
        </div>
        {text ? <Json value={raw} max={640} /> : <Fields value={output.value} open={['understanding', 'design', 'changes']} deep />}
      </div>
    </details>
  )
}

export function RawOutputPane({ scope }: { scope: Scope }): JSX.Element {
  return (
    <div className="st-outputs">
      <p className="st-meta">{T.rawOutputNote}</p>
      {scope.outputs.map((output, i) => <OutputBlock key={`${output.event}-${i}`} output={output} open={i === 0} />)}
    </div>
  )
}

function SignalView({ signal }: { signal: Signal }): JSX.Element {
  return (
    <div className="st-sig">
      <p className="st-meta">
        <code>{signal.source}</code> · {T.satisfied[String(signal.satisfied)]}
        {signal.items.length > 0 && ` · ${T.items(signal.items.length)}`}
      </p>
      {signal.text && <p className="st-sigtext">{signal.text.length > 600 ? `${signal.text.slice(0, 600)}…` : signal.text}</p>}
      {signal.items.length > 0 && (
        <table className="st-items">
          <tbody>
            {signal.items.map((item) => (
              <tr key={item.id}>
                <td>
                  <code>{item.id}</code>
                  {item.basis && <span className="st-chip src" title={T.basisHint[item.basis] ?? item.basis}>{T.basis[item.basis] ?? item.basis}</span>}
                </td>
                <td data-result={String(item.result)}>{typeof item.result === 'number' ? item.result.toFixed(2) : T.verdicts[item.result] ?? item.result}</td>
                <td>{item.expected}</td>
                <td>{item.session ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {(signal.attachments ?? []).length > 0 && (
        <div className="st-atts st-atts-start">{(signal.attachments ?? []).map((material) => <HandoverChip key={material.name} material={material} />)}</div>
      )}
    </div>
  )
}

function Observed({ card }: { card: ProcessEntry }): JSX.Element {
  const view = card.curation!
  const read = view.scopes[0].reads.filter((item) => item.tool === 'read_observation')
  return (
    <div className="st-observed">
      <p className="st-meta">{T.observedHanded(view.observed, new Set(read.filter((item) => item.observed).map((item) => item.target.split(' ')[0])).size)}</p>
      <ul className="st-list">
        {read.map((item, i) => (
          <li key={i}>
            <code>{item.target}</code> {item.observed ? T.readObserved(item.observed) : T.readFailed}
          </li>
        ))}
      </ul>
    </div>
  )
}

export function InspectorPane({ card }: { card: ProcessEntry }): JSX.Element {
  const view = columns(card)
  return (
    <div className="st-cols">
      <div className="st-col">
        <h4>{T.colAssessor}</h4>
        <p className="st-meta">{T.colAssessorNote}</p>
        {view.assessor.length ? view.assessor.map((record, i) => <Fields key={i} value={record} open={['scorecard', 'shortfalls']} />) : <p className="st-none">{T.noAssessorRecord}</p>}
      </div>
      <div className="st-col">
        <h4>{T.colAnalyst}</h4>
        <p className="st-meta">{T.colAnalystNote}</p>
        {card.onboarding && <p className="st-none">{T.onboardingSkipsAnalyst}</p>}
        {!card.onboarding && view.analyst.map((signal, i) => <SignalView key={i} signal={signal} />)}
      </div>
      <div className="st-col">
        <h4>{T.colCurator}</h4>
        <p className="st-meta">{T.colCuratorNote}</p>
        {view.curator === null ? (
          <p className="st-none">{T.noCuratorInput}</p>
        ) : (
          <>
            <p className={view.leaks.length ? 'st-bad st-leak' : 'st-good st-leak'}>
              {view.leaks.length ? T.leakFound(new Set(view.leaks.map((leak) => leak.id)).size) : T.leakNone}
            </p>
            {view.leaks.length > 0 && (
              <ul className="st-list st-leaks">
                {view.leaks.slice(0, 12).map((leak, i) => <li key={i}><code>{leak.id}</code> <span className="st-meta">{leak.at}</span></li>)}
              </ul>
            )}
            <Fields value={view.curator} open={['signals', 'requirements']} />
            {card.curation && card.curation.observed > 0 && <Observed card={card} />}
          </>
        )}
      </div>
    </div>
  )
}

const ratio = (held: number, judged: number): string => (judged ? `${Math.round((held / judged) * 100)}%` : '—')

function Held({ held }: { held: boolean | null | undefined }): JSX.Element {
  return <span className="st-held" data-held={String(held ?? null)} title={T.heldHint}>{T.held[String(held ?? null)]}</span>
}

/** A child harness scope of a composite curation (child/<name>); the root needs no mark. */
function Scope({ scope }: { scope?: string }): JSX.Element | null {
  if (!scope || scope === 'root') return null
  return <span className="st-scope" title={T.childScopeHint}>{T.childScope(scope)}</span>
}

/* The ledger is the loop's own join (experimental/iteration/ledger.py) and is
   shown as recorded. Where the history left a requirement undiagnosed but the
   round's attribution record diagnosed it, the record's state is shown beside
   the empty cell, since the ledger counts only the history. */
export function LedgerPane({ thread }: { thread: Thread }): JSX.Element {
  const rows = thread.ledger?.rows ?? []
  const summary = thread.ledger?.summary ?? []
  const holdout = thread.ledger?.holdout ?? []
  const recorded = thread.recorded ?? {}
  const questions = thread.questions ?? []
  const revised = (thread.history ?? []).filter((entry) => (entry.revision ?? []).length > 0)
  const missing = rows.filter((row) => row.state === null && recorded[`${row.round}:${row.requirement}`])
  return (
    <div className="st-ledger">
      <p className="st-meta">{T.ledgerNote}</p>
      {missing.length > 0 && <p className="st-warn">{T.ledgerMissing} ({missing.map((row) => row.requirement).join(', ')})</p>}
      {questions.length > 0 && (
        <section className="st-lsec">
          <p className="st-label">{T.questions}</p>
          {questions.map((question, i) => (
            <p key={i} className="st-question"><span className="st-rid">{T.roundLabel(question.round).split(' ·')[0]}</span><span className="st-rstage">{T.stages[question.stage] ?? question.stage}</span>{question.question}</p>
          ))}
        </section>
      )}
      <section className="st-lsec">
        <p className="st-label">{T.ledgerRows}</p>
        {rows.length === 0 ? (
          <p className="st-none">{T.ledgerEmpty}</p>
        ) : (
          <table className="st-table">
            <thead>
              <tr><th>{T.ledgerCols.round}</th><th>{T.ledgerCols.requirement}</th><th>{T.ledgerCols.state}</th><th>{T.ledgerCols.changes}</th><th>{T.ledgerCols.held}</th></tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const record = recorded[`${row.round}:${row.requirement}`]
                return (
                  <tr key={`${row.round}-${row.requirement}`}>
                    <td className="n">{row.round}</td>
                    <td title={row.situation}>
                      <span className="st-rid">{row.requirement}</span>
                      {row.strength && <span className={`st-chip ${row.strength === 'must_hold' ? 'must' : 'should'}`}>{T.strength[row.strength] ?? row.strength}</span>}
                      {row.repeats && <span className="st-repeat">{T.repeats(row.repeats)}</span>}
                      {row.situation && <p className="st-sit">{row.situation}</p>}
                    </td>
                    <td>
                      {row.state ? <StateChip state={row.state} /> : <span className="st-none">{T.ledgerNone}</span>}
                      {!row.state && record && <p className="st-recorded" title={T.ledgerMissing}>{T.ledgerRecorded}<StateChip state={record.state} /></p>}
                      {(row.diagnoses ?? []).filter((diagnosis) => diagnosis.scope !== 'root').map((diagnosis) => (
                        <p key={diagnosis.scope} className="st-scoped"><Scope scope={diagnosis.scope} /><StateChip state={diagnosis.state} /></p>
                      ))}
                    </td>
                    <td>
                      {row.changes.map((change) => (
                        <p key={`${change.scope ?? 'root'}:${change.target}`} className="st-lchange"><Scope scope={change.scope} /><Target name={change.target} />{change.treatment && <span className="st-treat" data-treatment={change.treatment}>{T.treatment[change.treatment] ?? change.treatment}</span>}</p>
                      ))}
                      {!row.changes.length && !record?.changes.length && <span className="st-none">{row.curated ? T.ledgerNone : T.ledgerUncurated}</span>}
                      {!row.changes.length && record?.changes.map((change) => (
                        <p key={change.target} className="st-lchange st-recorded"><Target name={change.target} />{change.treatment && <span className="st-treat" data-treatment={change.treatment}>{T.treatment[change.treatment] ?? change.treatment}</span>}</p>
                      ))}
                    </td>
                    <td><Held held={row.held} /></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </section>
      <section className="st-lsec">
        <p className="st-label">{T.ledgerSummary}</p>
        {summary.length === 0 ? (
          <p className="st-none">{T.ledgerNoSummary}</p>
        ) : (
          <table className="st-table">
            <thead>
              <tr><th>{T.ledgerCols.attributor}</th><th>{T.ledgerCols.state}</th><th>{T.ledgerCols.treatment}</th><th>{T.ledgerCols.judged}</th><th>{T.ledgerCols.held}</th><th>{T.ledgerCols.ratio}</th></tr>
            </thead>
            <tbody>
              {summary.map((group, i) => (
                <tr key={i}>
                  <td><code>{identityLine(group.attributor) || T.ledgerNone}</code></td>
                  <td>{group.state ? <StateChip state={group.state} /> : T.ledgerNone}</td>
                  <td>{group.treatment ? <span className="st-treat" data-treatment={group.treatment}>{T.treatment[group.treatment] ?? group.treatment}</span> : T.ledgerNone}</td>
                  <td className="n">{group.judged}</td>
                  <td className="n">{group.held}</td>
                  <td className="n">{ratio(group.held, group.judged)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      {holdout.length > 0 && (
        <section className="st-lsec">
          <p className="st-label">{T.ledgerHoldout} · {T.scoreHeldOut}</p>
          <table className="st-table">
            <thead>
              <tr><th>{T.ledgerCols.round}</th><th>{T.ledgerSource}</th><th>{T.ledgerSatisfied}</th><th>{T.ledgerItems}</th></tr>
            </thead>
            <tbody>
              {holdout.map((row, i) => (
                <tr key={i}>
                  <td className="n">{row.round}</td>
                  <td><code>{row.source}</code></td>
                  <td><span className="st-sat" data-sat={String(row.satisfied)}>{T.scoreSatisfied[String(row.satisfied)]}</span></td>
                  <td className="n">{T.scoreCounts(row.passed, row.failed, row.items)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      {revised.length > 0 && (
        <section className="st-lsec">
          <p className="st-label">{T.historyTitle}</p>
          {revised.map((entry) => (
            <div key={entry.round} className="st-hist">
              <p className="st-histhead">
                <span className="st-rid">{entry.round === 0 ? T.onboardingLabel.split(' ·')[0] : T.roundLabel(entry.round).split(' ·')[0]}</span>
                {entry.attributor ? <code>{identityLine(entry.attributor)}</code> : <span className="st-none">{T.historyNoAttributor}</span>}
              </p>
              {(entry.revision ?? []).map((change) => (
                <p key={`${change.scope ?? 'root'}:${change.target}`} className="st-lchange">
                  <Scope scope={change.scope} />
                  <Target name={change.target} />
                  {change.treatment && <span className="st-treat" data-treatment={change.treatment}>{T.treatment[change.treatment] ?? change.treatment}</span>}
                  {(change.addresses ?? []).length ? (change.addresses ?? []).map((about) => <span key={about} className="st-aboutchip">{T.about(about)}</span>) : <span className="st-none">{T.historyNoAddresses}</span>}
                </p>
              ))}
            </div>
          ))}
        </section>
      )}
    </div>
  )
}

const clock = (time: number | null): string => (time ? new Date(time * 1000).toLocaleTimeString('en-GB', { hour12: false }) : '')

function AuditRow({ row }: { row: BoundaryRow }): JSX.Element {
  return (
    <tr data-event={row.event}>
      <td className="n">{clock(row.time)}</td>
      <td>{T.auditRoles[row.role] ?? row.role}</td>
      <td><span className="st-aev" data-event={row.event}>{T.auditEvents[row.event] ?? row.event}</span></td>
      <td><code>{row.where}</code></td>
      <td>{row.hits.map((hit, i) => <code key={i} className="st-hit">{hit}</code>)}</td>
    </tr>
  )
}

/** Every role's compartment entries, admissions, violations and leavings, violations first. */
export function AuditPane({ boundaries }: { boundaries: Boundaries | null | undefined }): JSX.Element {
  const [all, setAll] = useState(false)
  if (!boundaries) return <p className="st-none">{T.auditMissing}</p>
  if (boundaries.error) return <p className="st-bad">{boundaries.error}</p>
  const events = ['enter', 'admit', 'violation', 'leave']
  const shown = all ? boundaries.rows : boundaries.rows.slice(-200)
  return (
    <div className="st-audit">
      <p className="st-meta">{T.auditNote}</p>
      <p className={boundaries.violations.length ? 'st-bad st-leak' : 'st-good st-leak'}>
        {boundaries.violations.length ? T.auditViolations(boundaries.violations.length) : T.auditClean}
      </p>
      <table className="st-table">
        <thead>
          <tr><th />{events.map((event) => <th key={event}>{T.auditEvents[event]}</th>)}</tr>
        </thead>
        <tbody>
          {Object.entries(boundaries.counts).map(([role, byEvent]) => (
            <tr key={role} data-event={byEvent.violation ? 'violation' : undefined}>
              <td>{T.auditRoles[role] ?? role}</td>
              {events.map((event) => <td key={event} className="n" data-hot={event === 'violation' && byEvent[event] ? true : undefined}>{byEvent[event] ?? 0}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      {boundaries.violations.length > 0 && (
        <section className="st-lsec">
          <p className="st-label">{T.auditEvents.violation}</p>
          <table className="st-table st-auditrows">
            <tbody>{boundaries.violations.map((row, i) => <AuditRow key={i} row={row} />)}</tbody>
          </table>
        </section>
      )}
      <section className="st-lsec">
        <p className="st-label">{T.auditShown(shown.length, boundaries.total)}</p>
        <table className="st-table st-auditrows">
          <tbody>{shown.map((row, i) => <AuditRow key={i} row={row} />)}</tbody>
        </table>
        {!all && boundaries.rows.length > shown.length && <button type="button" className="st-link" onClick={() => setAll(true)}>{T.auditAll(boundaries.rows.length)}</button>}
      </section>
    </div>
  )
}
