/* The record view: a run's cultivation record as experimental/simulation/record.py
   builds it. It leads with the knowledge-sedimentation ledger (each of the
   owner's rules by round: did it fail, what did the Analyst ask for, what did the
   Curator land in which harness, did a mechanism fire, did the employee then
   comply), opens the chain of evidence behind any cell, and ends with the round
   summaries, the curations by harness scope and the record's inputs. The value
   judge's verdict comes first when the record carries one, and the mining
   sessions that ranked this run come last. */

import { useEffect, useMemo, useState } from 'react'

import { RECORD_UNAVAILABLE, loadBundle, loadMining, loadRecord } from '../api'
import {
  chainLabel, changesOf, completed, costLabel, diffLines, facetOf, groupCurations, handedAfter, inForce, isOnboarding,
  isRoot, ledgerMatrix, mechanismOf, modelLine, quotesOf, requirementsOf, revisionLabel, roundAt, roundSummaries, scopeLabel,
  VERDICT_LABEL,
} from '../record'
import { Clamp, Fold, HeldBadge, RedLine, TreatmentBadge } from './Badges'
import { Markdown } from './Markdown'

import type { Bundle, MiningSession, RecordReply } from '../api'
import type { RunEntry } from '../model'
import type {
  ArtifactDiff, ChangeLink, CultivationRecord, Landed, Material, MatrixCell, MatrixRow, MechanismEvidence, RecordCuration, RecordRequirement,
  RoundSummary, Tone, ValueCase, ValueVerdict,
} from '../record'
import type { JSX } from 'react'

const REFRESH = 15000

/* How the record linked a requirement or a change to a rule: a requirement by
   its check grounds or, without any, by the evaluation side's reading of which
   rules it restates (attribution.json); a change by the requirements it
   addresses. `none` shows no mark. */
const LINK_HINT: Record<string, string> = {
  grounds: 'The requirement is grounded on this criterion as a check',
  reading: "The evaluation side read the requirement as restating this rule (the owner's scorecard stays private, so the requirement names no check)",
  addresses: 'The change addresses a requirement linked to this criterion, as the typed history records it',
}

const plural = (count: number, word: string): string => `${count} ${word}${count === 1 ? '' : 's'}`

const when = (value: unknown): string => {
  const date = typeof value === 'number' ? new Date(value * 1000) : typeof value === 'string' && value ? new Date(value) : null
  return date && !Number.isNaN(date.getTime()) ? date.toLocaleString() : ''
}

const humanize = (value: string): string => value.replace(/_/g, ' ')

/* Model-written errors run to many paragraphs; the first line stands in for them until the reader opens it. */
function LongText({ text, className = '', limit = 220 }: { text: string; className?: string; limit?: number }): JSX.Element {
  if (text.length <= limit) return <Markdown className={className} text={text} />
  const excerpt = text.replace(/\s+/g, ' ').slice(0, limit)
  return (
    <Fold className={`fold long ${className}`} summary={<span className="excerpt">{excerpt}...</span>}>
      {() => <Markdown className={className} text={text} />}
    </Fold>
  )
}

/* The page is often opened over plain http from another machine, where the
   asynchronous clipboard is unavailable; a selected textarea still copies. */
async function copyText(value: string): Promise<boolean> {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(value)
    return true
  }
  const area = document.createElement('textarea')
  area.value = value
  area.style.position = 'fixed'
  area.style.opacity = '0'
  document.body.appendChild(area)
  area.select()
  const done = document.execCommand?.('copy') ?? false
  area.remove()
  return done
}

function FacetChip({ item }: { item: Landed }): JSX.Element {
  const where = `${item.targets.join(', ')}${isRoot(item.scope) ? '' : ` in ${item.scope}`}`
  return (
    <span className={`facet ${item.facet}${item.installed ? '' : ' planned'}`} title={item.installed ? `Change landed: ${where}` : `Planned but not installed (${item.outcome ?? 'not installed'}): ${where}`}>
      {item.facet}
      {isRoot(item.scope) ? null : <span className="sc">{item.scope}</span>}
    </span>
  )
}

const VERDICT_TEXT: Record<Tone, string> = { pass: 'pass', fail: 'fail', mixed: 'mixed', unknown: 'unknown', none: '·' }

function verdictText(cell: MatrixCell): string {
  const fails = cell.cell?.fails ?? 0
  const judged = fails + (cell.cell?.passes ?? 0)
  if ((cell.tone === 'fail' || cell.tone === 'mixed') && judged > 1) return `${fails}/${judged} fail`
  return VERDICT_TEXT[cell.tone]
}

interface Place {
  criterion: string
  round: number
}

function Header({ record, entry, bundle }: { record: CultivationRecord; entry: RunEntry | undefined; bundle: { folder: string; bundle: Bundle | null } | null }): JSX.Element {
  const { run, cost } = record
  const chain = chainLabel(run.chain) || entry?.chain || ''
  const models = modelLine(run.settings.models) || modelLine(entry?.models)
  const stopped = run.stopped || run.suite?.stopped || entry?.stopped || ''
  const revisions = run.revisions.map(revisionLabel).filter(Boolean)
  const [copied, setCopied] = useState(false)
  const copy = (path: string): void => {
    copyText(path).then(setCopied, () => setCopied(false))
  }
  const parts = cost ? Object.entries(cost.by_part).filter(([, amount]) => typeof amount === 'number') : []
  return (
    <div className="task">
      <span className="eyebrow">Record</span>
      <h2>{run.name || entry?.name || 'Cultivation record'}</h2>
      <p className="quiet">
        The cultivation record of this run: what the owner taught, how each rule was sedimented into the employee's harness, and whether the employee then complied. It is read from the run's records; no model is called.
      </p>
      <dl className="rstats">
        <div><dt>status</dt><dd><span className={`dot ${run.status ?? ''}`} />{run.status ?? 'unknown'}</dd></div>
        <div><dt>chain</dt><dd>{chain ? <code className="chainv">{chain}</code> : <span className="dim">not recorded</span>}</dd></div>
        <div><dt>rounds</dt><dd>{completed(record)}{typeof run.settings.rounds === 'number' ? ` of ${run.settings.rounds}` : ''} judged</dd></div>
        <div>
          <dt>versions</dt>
          <dd title={revisions.map((id, i) => `v${i} ${id.slice(0, 12)}`).join(' → ')}>{revisions.length ? `v0–v${revisions.length - 1}` : '0'}</dd>
        </div>
        <div>
          <dt>cost</dt>
          <dd title={parts.map(([part, amount]) => `${part} ${costLabel(amount)}`).join(' · ')}>
            {cost ? costLabel(cost.total) : entry?.spend != null ? costLabel(entry.spend) : <span className="dim">not recorded</span>}
          </dd>
        </div>
        {run.record_id ? <div><dt>record</dt><dd><code>{run.record_id.slice(0, 12)}</code></dd></div> : null}
      </dl>
      {models ? <p className="rline"><span className="k">models</span>{models}</p> : null}
      {parts.length ? <p className="rline"><span className="k">spend</span>{parts.map(([part, amount]) => `${part} ${costLabel(amount)}`).join(' · ')}</p> : null}
      {when(run.started) || when(run.updated) ? (
        <p className="rline"><span className="k">time</span>{[when(run.started) && `started ${when(run.started)}`, when(run.updated) && `updated ${when(run.updated)}`].filter(Boolean).join(' · ')}</p>
      ) : null}
      {stopped ? <p className="rstop"><span className="k">stopped</span>{stopped}</p> : null}
      {run.error && !(stopped && run.error.includes(stopped)) ? <div className="rstop"><span className="k">error</span><LongText text={run.error} /></div> : null}
      {!run.error && run.stop && run.stop !== stopped ? <p className="rline"><span className="k">ended</span>{run.stop}</p> : null}
      {run.warnings.map((warning) => <p key={warning} className="rline"><span className="k">warning</span><span className="warn">{warning}</span></p>)}
      {bundle ? (
        bundle.bundle ? (
          <div className="rbundle">
            <span className="k">exported bundle</span>
            <code title={bundle.bundle.path}>{bundle.bundle.path}</code>
            <button className="link" onClick={() => copy(bundle.bundle!.path)}>{copied ? 'copied' : 'copy path'}</button>
            <span className="dim">{plural(bundle.bundle.count, 'file')} · {when(bundle.bundle.modified)}</span>
            {bundle.bundle.files.length > 1 ? (
              <Fold className="fold small" summary="files in the bundle">{() => <ul className="plain mono-list">{bundle.bundle!.files.map((file) => <li key={file}>{file}</li>)}</ul>}</Fold>
            ) : null}
          </div>
        ) : (
          <p className="rline"><span className="k">bundle</span><span className="dim">No bundle exported yet under <code>{bundle.folder}</code>; the exporter writes one when the run ends.</span></p>
        )
      ) : null}
    </div>
  )
}

function Ledger({ record, selected, onSelect }: { record: CultivationRecord; selected: Place | null; onSelect: (place: Place | null) => void }): JSX.Element {
  const matrix = useMemo(() => ledgerMatrix(record), [record])
  const red = matrix.rows.filter((row) => row.red).length
  if (!matrix.rows.length && !matrix.quiet.length) return <p className="quiet">The record holds no ledger yet: no criterion has been judged.</p>
  return (
    <>
      <p className="lede">
        One row per rule the owner holds, red lines first; one column per round. Read a row left to right: the round a rule failed, the requirement the Analyst raised, the change the Curator landed in the harness after that trial, and whether the next trials passed while the landed mechanism fired. A rule that turns to pass after its change landed is the owner's knowledge sedimented into the harness.
      </p>
      <p className="legend">
        <span><span className="lchip pass">pass</span><span className="lchip fail">fail</span><span className="lchip mixed">mixed</span><span className="lchip unknown">unknown</span></span>
        <span><span className="mk req">req</span> requirement raised</span>
        <span><span className="facet planning">facet</span> change landed after the trial</span>
        <span><span className="facet planning planned">facet</span> planned, not installed</span>
        <span><span className="mk fired">fired</span> mechanism evidence in the trial</span>
      </p>
      <div className="table ledger-wrap">
        <table className="ledger">
          <thead>
            <tr>
              <th className="rule">Rule <span className="cnt">{plural(matrix.rows.length, 'rule')}{red ? ` · ${red} red` : ''}</span></th>
              {matrix.columns.map((column) => {
                const handed = column.round > 0 ? handedAfter(record, column.round) : []
                return (
                  <th key={column.round} className="col">
                    <span className="v">{column.label}</span>
                    {column.revision ? <small title={column.artifact ?? ''}>on {column.revision}{column.partial ? ' · cut off' : ''}</small> : column.round === 0 ? <small>before round 1</small> : column.partial ? <small>cut off</small> : null}
                    {handed.length ? <span className="announced" title={`Handed over in this round's review: ${handed.join(', ')}`}>+{handed.length} handed over</span> : null}
                  </th>
                )
              })}
              <th className="now">Now</th>
            </tr>
          </thead>
          <tbody>
            {matrix.rows.map((item) => <LedgerLine key={item.row.criterion} item={item} selected={selected} onSelect={onSelect} />)}
          </tbody>
        </table>
      </div>
      {matrix.quiet.length ? (
        <p className="rline quietrules">
          <span className="k">not exercised</span>
          <span className="dim">{plural(matrix.quiet.length, 'rule')} with no verdict in any round and no change for them:</span>
          {matrix.quiet.map((item) => <code key={item.row.criterion} title={item.row.rule}>{item.row.criterion}</code>)}
        </p>
      ) : null}
    </>
  )
}

function LedgerLine({ item, selected, onSelect }: { item: MatrixRow; selected: Place | null; onSelect: (place: Place | null) => void }): JSX.Element {
  const { row } = item
  return (
    <tr className={item.red ? 'red' : ''}>
      <th scope="row" className="rule">
        <span className="n">{row.criterion}</span>
        {item.red ? <RedLine /> : null}
        {row.rule ? <span className="rt" title={row.rule}>{row.rule}</span> : null}
      </th>
      {item.cells.map((cell) => {
        const on = selected?.criterion === row.criterion && selected.round === cell.column.round
        const empty = cell.tone === 'none' && !cell.landed.length
        return (
          <td key={cell.column.round} className={`lc ${cell.tone}${on ? ' sel' : ''}`}>
            {empty ? <span className="dim">·</span> : (
              <button onClick={() => onSelect(on ? null : { criterion: row.criterion, round: cell.column.round })} aria-pressed={on} title="Open the chain of evidence for this rule and round">
                {cell.tone === 'none' ? null : <span className="lv">{verdictText(cell)}</span>}
                <span className="lmk">
                  {cell.requirements ? <span className="mk req" title={`${plural(cell.requirements, 'requirement')} raised by the Analyst`}>req {cell.requirements}</span> : null}
                  {cell.landed.map((landed) => <FacetChip key={`${landed.scope}-${landed.facet}`} item={landed} />)}
                  {cell.fired ? <span className="mk fired" title={`${plural(cell.fired, 'mechanism event')} recorded in this trial`}>fired {cell.fired}</span> : null}
                </span>
              </button>
            )}
          </td>
        )
      })}
      <td className={`now ${item.settle.tone}`}>
        <span className="st" title={row.status ? `The record's status: ${row.status}` : 'Read from the verdicts'}>{item.settle.text}</span>
        {item.settle.note ? <span className="bst">{item.settle.note}</span> : null}
      </td>
    </tr>
  )
}

function Diff({ diff }: { diff: ArtifactDiff }): JSX.Element {
  const counts = `+${diff.lines_added ?? 0} −${diff.lines_removed ?? 0}`
  return (
    <Fold className="fold src diff" summary={<><code>{diff.path}</code> <span className="dim">{diff.change ?? 'changed'} · {counts}</span></>}>
      {() => diff.diff ? (
        <pre className="diffp">{diffLines(diff.diff).map((line, i) => <span key={i} className={line.kind}>{line.text}{'\n'}</span>)}</pre>
      ) : <p className="quiet small">The record keeps no diff text for this file.</p>}
    </Fold>
  )
}

function Requirement({ item }: { item: RecordRequirement }): JSX.Element {
  return (
    <li className="creq">
      <span className="marks">
        {item.id ? <span className="rid">{item.id}</span> : null}
        {item.repeats ? <span className="recur" title={`Raised again: it repeats ${item.repeats}`}>repeats {item.repeats}</span> : null}
        {item.strength ? <span className={`strength ${item.strength}`}>{item.strength === 'must_hold' ? 'must hold' : humanize(item.strength)}</span> : null}
        {item.recurrence ? <span className="recur">recurred ×{item.recurrence}</span> : null}
        {typeof item.link === 'string' && item.link !== 'none' ? <span className="mk link" title={LINK_HINT[item.link] ?? ''}>linked by {item.link}</span> : null}
        <HeldBadge held={item.held} />
      </span>
      <Markdown className="beh" text={item.behavior} />
      <dl>
        {item.situation ? <><dt>situation</dt><dd><Markdown text={item.situation} /></dd></> : null}
        {item.observed ? <><dt>observed</dt><dd><Markdown text={item.observed} /></dd></> : null}
        {item.acceptance ? <><dt>accept</dt><dd><Markdown text={item.acceptance} /></dd></> : null}
        {item.evidence.length ? <><dt>evidence</dt><dd className="ev">{item.evidence.join(' · ')}</dd></> : null}
        {item.cases.length ? <><dt>cases</dt><dd className="ev">{item.cases.join(' · ')}</dd></> : null}
      </dl>
    </li>
  )
}

function ChangeView({ link }: { link: ChangeLink }): JSX.Element {
  const { change, curation, plan, diffs } = link
  const facet = facetOf(change.target, change.facet ?? plan?.facet)
  return (
    <li className="cchange">
      <div className="change-hd">
        <code>{change.target}</code>
        <span className={`facet ${facet}`}>{facet}</span>
        <span className="harness-chip">{scopeLabel(change.scope)}</span>
        {curation?.outcome || change.outcome ? <span className={`chip ${(change.outcome ?? curation?.outcome) === 'installed' ? '' : 'fail'}`}>{change.outcome ?? curation?.outcome}</span> : null}
        <TreatmentBadge treatment={plan?.treatment} />
        {change.link ? <span className="mk link" title={LINK_HINT[change.link] ?? ''}>by {change.link}</span> : null}
        {plan?.addresses?.length ? <span className="dim small" title="The inputs this change addresses, as the typed history records them">addresses {plan.addresses.join(', ')}</span> : null}
        {change.paths.length ? <span className="dim small">{change.paths.join(', ')}</span> : null}
      </div>
      {plan?.reason || plan?.expected ? (
        <dl>
          {plan.reason ? <><dt>why</dt><dd><Markdown text={plan.reason} /></dd></> : null}
          {plan.expected ? <><dt>expect</dt><dd><Markdown text={plan.expected} /></dd></> : null}
        </dl>
      ) : null}
      {curation?.error ? <LongText className="bad small" text={`Curation ${curation.outcome ?? 'error'}: ${curation.error}`} limit={180} /> : null}
      {diffs.map((diff, i) => <Diff key={`${diff.path}-${i}`} diff={diff} />)}
      {!curation ? <p className="quiet small">The curation this change names is not in the record.</p> : null}
    </li>
  )
}

function Evidence({ rows }: { rows: MechanismEvidence[] }): JSX.Element {
  return (
    <ul className="plain mech">
      {rows.map((row, i) => (
        <li key={i}>
          <span className="mk fired">{row.kind}</span>
          {row.target ? <code>{row.scope && !isRoot(row.scope) ? `${row.scope}: ${row.target}` : row.target}</code> : null}
          {row.decision ? <span className={`dec${row.intervention ? ' int' : ''}`} title={row.intervention ? 'An intervention: work sent back or ended, a tool refused, or a rollback' : ''}>{row.decision}</span> : null}
          {row.count && row.count > 1 ? <span className="dim">×{row.count}</span> : null}
          {row.session ? <span className="dim">{row.session}{row.turn !== null && row.turn !== undefined && row.turn !== '' ? ` · turn ${row.turn}` : ''}</span> : null}
          {row.summary ? <span className="sum">{row.summary}</span> : null}
        </li>
      ))}
    </ul>
  )
}

function Chain({
  record, place, onClose, onTrial, onRemark,
}: { record: CultivationRecord; place: Place; onClose: () => void; onTrial: (round: number) => void; onRemark: (round: number) => void }): JSX.Element | null {
  const row = record.ledger.find((item) => item.criterion === place.criterion)
  if (!row) return null
  const { round } = place
  const cell = row.timeline.find((item) => item.round === round)
  const quotes = round > 0 ? quotesOf(record, row.criterion, round) : []
  const requirements = round > 0 ? requirementsOf(record, row.criterion, cell, round) : { rows: [], source: 'ledger' as const }
  const changes = changesOf(record, cell, row, round)
  const mechanism = round > 0 ? mechanismOf(record, row, cell, round) : { rows: [], source: 'ledger' as const, count: 0 }
  const force = round > 0 ? inForce(row, round) : []
  const next = row.timeline.filter((item) => item.round > round).sort((a, b) => a.round - b.round)[0]
  const matrixRow = ledgerMatrix(record).rows.find((item) => item.row.criterion === row.criterion)
  const tone = matrixRow?.cells.find((item) => item.column.round === round)?.tone ?? 'none'
  const nextTone = matrixRow?.cells.find((item) => item.column.round === next?.round)?.tone
  return (
    <div className="chainp" id="evidence-chain">
      <div className="chainp-hd">
        <code className="n">{row.criterion}</code>
        {row.severity === 'red_line' ? <RedLine /> : null}
        <span className="rd">{round === 0 ? 'Onboarding' : `Round ${round}`}</span>
        {tone !== 'none' ? <span className={`lchip ${tone}`}>{tone}</span> : null}
        <span className="grow" />
        {round > 0 ? <button className="link" onClick={() => onTrial(round)}>round {round} trial</button> : null}
        {round > 0 ? <button className="link" onClick={() => onRemark(round)}>owner's remark</button> : null}
        <button className="pclose" onClick={onClose} aria-label="Close the chain of evidence">close</button>
      </div>
      {row.rule ? <p className="chainp-rule">{row.rule}</p> : null}
      <ol className="steps-v">
        {round > 0 ? (
          <li>
            <span className="k">In force during the trial</span>
            {force.length ? (
              <p className="chips">
                {force.map((item, i) => (
                  <span key={i} className="inforce">
                    <code>{item.target}</code>
                    <span className={`facet ${facetOf(item.target, item.facet)}`}>{facetOf(item.target, item.facet)}</span>
                    {isRoot(item.scope) ? null : <span className="harness-chip">{item.scope}</span>}
                    <span className="dim">{isOnboarding(item.round) ? 'since onboarding' : `since round ${item.round}`}</span>
                  </span>
                ))}
              </p>
            ) : <p className="quiet small">Nothing had been sedimented for this rule before this trial.</p>}
            {mechanism.rows.length ? <Evidence rows={mechanism.rows} /> : null}
            {mechanism.rows.length && mechanism.source === 'matched' ? (
              <p className="quiet small">The ledger lists no evidence rows for this cell; these are the trial's mechanism events on the targets in force.</p>
            ) : null}
            {!mechanism.rows.length && mechanism.count ? <p className="quiet small">The ledger counts {plural(mechanism.count, 'mechanism event')} without listing them.</p> : null}
            {!mechanism.rows.length && !mechanism.count && force.length ? <p className="quiet small">No mechanism event was recorded for these targets in this trial.</p> : null}
          </li>
        ) : null}
        {round > 0 ? (
          <li>
            <span className="k">The owner's verdict</span>
            {quotes.length ? (
              <ul className="plain quotes">
                {quotes.map((quote, i) => (
                  <li key={i} className={quote.tone}>
                    <p className="qhd">
                      <span className={`lchip ${quote.tone}`}>{quote.tone}</span>
                      {quote.item.session ? <code>{quote.item.session}</code> : null}
                      {quote.card && quote.card !== quote.item.session ? <span className="dim">card {quote.card}</span> : null}
                    </p>
                    {quote.item.actual ? <blockquote>{quote.item.actual}</blockquote> : quote.reply ? (
                      <>
                        <span className="qk">The verdict quotes nothing; the employee's last reply in this drill:</span>
                        <blockquote className="reply">{quote.reply.length > 900 ? `${quote.reply.slice(0, 900)}...` : quote.reply}</blockquote>
                      </>
                    ) : null}
                    {quote.item.note ? <p className="qnote">{quote.item.note}</p> : null}
                  </li>
                ))}
              </ul>
            ) : <p className="quiet small">The owner judged nothing on this rule in this round.</p>}
          </li>
        ) : null}
        {round > 0 ? (
          <li>
            <span className="k">The Analyst's requirements</span>
            {requirements.rows.length ? (
              <>
                <ul className="plain">{requirements.rows.map((item, i) => <Requirement key={i} item={item} />)}</ul>
                {requirements.source === 'matched' ? <p className="quiet small">Matched by the criteria each requirement names; the ledger did not link them itself.</p> : null}
              </>
            ) : <p className="quiet small">No requirement named this rule after this round{roundAt(record, round)?.analysis?.decision ? ` (the Analyst decided ${roundAt(record, round)?.analysis?.decision})` : ''}.</p>}
          </li>
        ) : null}
        <li>
          <span className="k">{round === 0 ? 'Sedimented at onboarding' : 'The Curator’s change after this trial'}</span>
          {changes.length ? <ul className="plain">{changes.map((link, i) => <ChangeView key={i} link={link} />)}</ul> : <p className="quiet small">No change for this rule landed after this {round === 0 ? 'onboarding' : 'trial'}.</p>}
        </li>
        {next ? (
          <li>
            <span className="k">Then</span>
            <p className="small">Round {next.round}: {nextTone && nextTone !== 'none' ? <span className={`lchip ${nextTone}`}>{nextTone}</span> : <span className="dim">not judged</span>}</p>
          </li>
        ) : null}
      </ol>
    </div>
  )
}

function RoundLine({ item, onTrial, onRemark }: { item: RoundSummary; onTrial: (round: number) => void; onRemark: (round: number) => void }): JSX.Element {
  return (
    <li>
      <span className="rn">{item.round === null ? 'Onboarding' : `Round ${item.round}`}</span>
      {item.revision ? <code className="ver">{item.revision}</code> : null}
      {item.round !== null && item.pass + item.fail + item.unknown === 0 ? <span className="counts dim">not judged</span> : null}
      {item.round !== null && item.pass + item.fail + item.unknown > 0 ? (
        <span className="counts">
          <span className="p">{item.pass} pass</span>
          <span className="f">{item.fail} fail{item.redFailed ? ` (${item.redFailed} red)` : ''}</span>
          {item.unknown ? <span className="u">{item.unknown} unknown</span> : null}
        </span>
      ) : null}
      {item.decision ? (
        <span className="part">Analyst <span className={`chip ${item.decision}`}>{item.decision}</span>{item.requirements ? ` ${plural(item.requirements, 'requirement')}` : ''}</span>
      ) : item.round !== null ? <span className="part dim">no analysis</span> : null}
      {item.curations.length ? item.curations.map((curation, i) => (
        <span key={i} className="part" title={curation.error ?? ''}>
          Curator{isRoot(curation.scope) ? '' : ` · ${curation.scope}`} <span className={`chip ${curation.error ? 'fail' : ''}`}>{curation.outcome}</span>
          {curation.facets.length ? <span className="dim"> {curation.facets.join(', ')}</span> : null}
        </span>
      )) : item.round !== null ? <span className="part dim">no curation</span> : null}
      {item.partial ? <span className="announced" title="The trial was cut off; its turns are in no recorded round">cut off</span> : null}
      {item.fired ? <span className="mk fired" title="Mechanism rows the round's drills recorded">fired {item.fired}</span> : null}
      {item.interventions ? <span className="mk int" title="Reviews that sent work back or ended it, refused tools and rollbacks">{item.interventions} intervention{item.interventions === 1 ? '' : 's'}</span> : null}
      {item.handed.length ? <span className="announced" title={`Handed over in this round's review: ${item.handed.join(', ')}`}>+{item.handed.length} handed over</span> : null}
      {item.round !== null ? (
        <span className="links">
          <button className="link" onClick={() => onTrial(item.round!)}>trial</button>
          <button className="link" onClick={() => onRemark(item.round!)}>remark</button>
        </span>
      ) : null}
    </li>
  )
}

function CurationCard({ curation }: { curation: RecordCuration }): JSX.Element {
  return (
    <div className="ccard">
      <div className="ccard-hd">
        <span className={`chip ${curation.error ? 'fail' : ''}`}>{curation.outcome || (curation.error ? 'failed' : 'recorded')}</span>
        <span className="dim">{plural(curation.changes.length, 'change')} · {plural(curation.artifact_diff.length, 'file')}</span>
        {curation.id ? <code className="dim">{curation.id.slice(0, 12)}</code> : null}
      </div>
      {curation.error ? <LongText className="bad small" text={curation.error} /> : null}
      {curation.validation_errors.length ? <ul className="plain">{curation.validation_errors.map((line, i) => <li key={i} className="bad small">{line}</li>)}</ul> : null}
      {curation.understanding ? <Clamp long={curation.understanding.length > 1200}><Markdown className="under" text={curation.understanding} /></Clamp> : null}
      {curation.design ? <Fold className="fold small" summary="The Curator's technical design">{() => <Markdown className="small" text={curation.design!} />}</Fold> : null}
      {curation.changes.length ? (
        <ul className="plain">
          {curation.changes.map((change, i) => {
            const facet = facetOf(change.target, change.facet)
            return (
              <li key={i} className="cchange">
                <div className="change-hd"><code>{change.target}</code><span className={`facet ${facet}`}>{facet}</span></div>
                {change.reason ? <Markdown className="small" text={change.reason} /> : null}
              </li>
            )
          })}
        </ul>
      ) : null}
      {curation.artifact_diff.length ? (
        <Fold className="fold small" summary={`File diffs (${curation.artifact_diff.length})`}>
          {() => <>{curation.artifact_diff.map((diff, i) => <Diff key={`${diff.path}-${i}`} diff={diff} />)}</>}
        </Fold>
      ) : null}
    </div>
  )
}

function Curations({ record }: { record: CultivationRecord }): JSX.Element {
  const groups = useMemo(() => groupCurations(record.curations), [record])
  if (!groups.length) return <p className="quiet">The record holds no curation.</p>
  return (
    <div className="cgroups">
      {groups.map((group) => (
        <Fold key={group.round ?? 0} className="fold cgroup" summary={<>{group.round === null ? 'Onboarding' : `After round ${group.round}`} <span className="dim">· {group.scopes.map((scope) => `${scopeLabel(scope.scope)} ${scope.curations.length}`).join(' · ')}</span></>}>
          {() => (
            <>
              {group.scopes.map((scope) => (
                <div key={scope.scope} className="cscope">
                  <p className="cscope-hd"><span className="harness-chip">{scopeLabel(scope.scope)}</span></p>
                  {scope.curations.map((curation, i) => <CurationCard key={curation.id || i} curation={curation} />)}
                </div>
              ))}
            </>
          )}
        </Fold>
      ))}
    </div>
  )
}

function Inputs({ record }: { record: CultivationRecord }): JSX.Element {
  const { inputs, run } = record
  const settings = Object.entries(run.settings).filter(([key]) => key !== 'baseline')
  const baseline = Object.entries(inputs.baseline)
  const given = (item: Material): string =>
    item.given === 'opening' ? 'at onboarding' : item.given === 'handed_over' ? (item.round ? `after round ${item.round}` : 'handed over') : typeof item.given === 'string' ? item.given : ''
  return (
    <div className="inputs">
      {inputs.materials.length ? (
        <div className="table">
          <table className="plain-table">
            <thead><tr><th>Material</th><th>Given</th><th>SHA-256</th></tr></thead>
            <tbody>
              {inputs.materials.map((item) => (
                <tr key={item.name}><td><code>{item.name}</code></td><td className="small">{given(item)}</td><td className="hash" title={item.sha256}>{item.sha256?.slice(0, 16) ?? ''}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <p className="quiet small">No material is listed.</p>}
      {inputs.cards.length ? (
        <p className="rline"><span className="k">cards</span>{inputs.cards.map((card) => <code key={card.name} title={card.sha256}>{card.name}</code>)}</p>
      ) : null}
      {inputs.onboarding ? <Fold className="fold" summary="The owner's onboarding message">{() => <Markdown text={inputs.onboarding!} />}</Fold> : null}
      {inputs.profile ? <Fold className="fold" summary="The agency profile">{() => <Markdown text={inputs.profile!} />}</Fold> : null}
      {run.reproduce ? <Fold className="fold" summary="Reproduce this run's setup">{() => <pre>{run.reproduce}</pre>}</Fold> : null}
      {settings.length ? (
        <Fold className="fold" summary="Run settings">
          {() => <pre>{JSON.stringify(Object.fromEntries(settings), null, 2)}</pre>}
        </Fold>
      ) : null}
      {baseline.length ? (
        <Fold className="fold" summary={`Starting agent home fingerprint (${plural(baseline.length, 'file')})`}>
          {() => <ul className="plain mono-list">{baseline.map(([path, sha]) => <li key={path}><span>{path}</span> <span className="hash">{sha.slice(0, 16)}</span></li>)}</ul>}
        </Fold>
      ) : null}
    </div>
  )
}

const VERDICT_TONE: Record<string, string> = { qualifies: 'pass', partial: 'unknown', none: 'fail' }
const roundList = (rounds: number[]): string => (rounds.length ? rounds.join(', ') : '-')

function CaseRows({ cases, onSelect }: { cases: ValueCase[]; onSelect: (place: Place) => void }): JSX.Element {
  return (
    <div className="table">
      <table className="cases">
        <thead>
          <tr><th>Rule</th><th>Where</th><th>Sedimented</th><th>Failed in</th><th>Held in</th><th>Mechanism</th></tr>
        </thead>
        <tbody>
          {cases.map((item) => {
            const round = item.held_in[0] ?? item.sedimented.round ?? 0
            return (
              <tr key={item.criterion}>
                <td>
                  <button className="link" onClick={() => onSelect({ criterion: item.criterion, round })} title="Open this rule's chain of evidence in the first round it held">{item.criterion}</button>
                  {item.severity === 'red_line' ? <RedLine /> : null}
                  {item.rule ? <span className="rt" title={item.rule}>{item.rule}</span> : null}
                </td>
                <td><span className="sc">{scopeLabel(item.sedimented.scope)}</span> <code>{item.targets.join(', ')}</code></td>
                <td>{item.sedimented.round === 0 ? 'at onboarding' : `after round ${item.sedimented.round}`}</td>
                <td>{roundList(item.failed_in)}</td>
                <td>{roundList(item.held_in)}</td>
                <td>{plural(item.mechanism_rows, 'row')}{item.interventions ? <span className="mk int">{item.interventions} intervention{item.interventions === 1 ? '' : 's'}</span> : null}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function Verdict({ value, onSelect }: { value: ValueVerdict; onSelect: (place: Place) => void }): JSX.Element {
  return (
    <div className="verdict">
      <p className="rline">
        <span className="k">verdict</span>
        <span className={`chip ${VERDICT_TONE[value.verdict] ?? ''}`}>{VERDICT_LABEL[value.verdict] ?? value.verdict}</span>
        <span className="dim">score {value.score}</span>
      </p>
      <ul className="plain checks">
        {value.checks.map((check) => (
          <li key={check.name}>
            <span className={`chip ${check.ok ? 'pass' : 'fail'}`}>{check.ok ? 'met' : 'not met'}</span>
            <code>{check.name}</code>
            <span className="small">{check.detail}</span>
          </li>
        ))}
      </ul>
      {value.cases.length ? <CaseRows cases={value.cases} onSelect={onSelect} /> : null}
      {value.held_cases.length ? (
        <>
          <p className="quiet small">Weaker: planning or action installed at onboarding that intervened and held, with no earlier failure to compare with.</p>
          <CaseRows cases={value.held_cases} onSelect={onSelect} />
        </>
      ) : null}
      {!value.cases.length && !value.held_cases.length ? <p className="quiet small">No rule has gone from failing to holding under a planning or action mechanism of its own yet.</p> : null}
    </div>
  )
}

function planLabel(plan: string[]): string {
  const at = plan.indexOf('--partition')
  if (at < 0) return plan.join(' ')
  try {
    const steps = JSON.parse(plan[at + 1] ?? '') as string[][]
    return steps.map((step, i) => `${i === 0 ? 'onboarding' : `after round ${i}`}: ${step.join(', ')}`).join(' · ')
  } catch {
    return plan.join(' ')
  }
}

function Mining({ name, onOpenRun }: { name: string; onOpenRun?: (name: string) => void }): JSX.Element | null {
  const [sessions, setSessions] = useState<MiningSession[]>([])
  useEffect(() => {
    let alive = true
    loadMining().then((value) => { if (alive) setSessions(value) })
    return () => { alive = false }
  }, [name])
  const mine = sessions.filter((session) => session.ranking.some((item) => item.name === name))
  if (!mine.length) return null
  return (
    <section className="sec">
      <h3>Mining <span className="cnt">{plural(mine.length, 'session')} ranked this run</span></h3>
      {mine.map((session) => (
        <div key={session.file} className="mining">
          <p className="rline">
            <span className="k">session</span><code>{session.file}</code>
            {typeof session.spend === 'number' ? <span className="dim">{costLabel(session.spend)} in all</span> : null}
            <span className="dim">{when(session.modified)}</span>
          </p>
          <div className="table">
            <table>
              <thead>
                <tr><th>#</th><th>Plan</th><th>Verdict</th><th>Score</th><th>Cases</th><th>Rounds</th><th>Spend</th><th>Run</th></tr>
              </thead>
              <tbody>
                {session.ranking.map((item, i) => (
                  <tr key={item.name} className={item.name === name ? 'this' : ''}>
                    <td>{i + 1}</td>
                    <td><code title={planLabel(item.plan)}>{item.label}</code></td>
                    <td>{item.value?.verdict ? <span className={`chip ${VERDICT_TONE[item.value.verdict] ?? ''}`}>{VERDICT_LABEL[item.value.verdict] ?? item.value.verdict}</span> : <span className="dim">not judged</span>}</td>
                    <td>{item.value?.score ?? ''}</td>
                    <td>{item.value?.cases ?? ''}</td>
                    <td>{item.rounds ?? ''}</td>
                    <td>{typeof item.spend === 'number' ? costLabel(item.spend) : ''}</td>
                    <td>
                      {item.name === name || !onOpenRun ? <span className="dim">{item.name}</span> : <button className="link" onClick={() => onOpenRun(item.name)}>{item.name}</button>}
                      {item.stopped ? <span className="dim small"> · {item.stopped}</span> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </section>
  )
}

export function RecordView({
  runId, entry, live, onTrial, onRemark, onOpenRun,
}: { runId: string; entry?: RunEntry; live: boolean; onTrial: (round: number) => void; onRemark: (round: number) => void; onOpenRun?: (name: string) => void }): JSX.Element {
  const [reply, setReply] = useState<RecordReply | null>(null)
  const [bundle, setBundle] = useState<{ folder: string; bundle: Bundle | null } | null>(null)
  const [place, setPlace] = useState<Place | null>(null)
  const [failed, setFailed] = useState('')

  useEffect(() => {
    let alive = true
    setReply(null)
    setPlace(null)
    setFailed('')
    const load = () => {
      loadRecord(runId)
        .then((value) => { if (alive) setReply(value) })
        .catch((e: Error) => { if (alive) setFailed(e.message) })
      loadBundle(runId).then((value) => { if (alive) setBundle(value) })
    }
    load()
    const timer = live ? setInterval(load, REFRESH) : null
    return () => {
      alive = false
      if (timer) clearInterval(timer)
    }
  }, [runId, live])

  const record = reply?.ok ? reply.record : null
  const summaries = useMemo(() => (record ? roundSummaries(record) : []), [record])
  const select = (next: Place | null): void => {
    setPlace(next)
    if (next) requestAnimationFrame(() => document.getElementById('evidence-chain')?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' }))
  }

  if (failed) return <div className="record"><p className="bad">Could not read the record: {failed}</p></div>
  if (!reply) return <div className="record"><p className="quiet">Building the cultivation record...</p></div>
  if (!reply.ok) {
    return (
      <div className="record">
        <div className="task">
          <span className="eyebrow">Record</span>
          <h2>{entry?.name ?? runId}</h2>
        </div>
        <div className="rmissing">
          <p className={reply.error === RECORD_UNAVAILABLE ? 'warn' : 'bad'}>
            {reply.error === RECORD_UNAVAILABLE ? 'The record builder is not available on this server.' : reply.status === 404 ? 'The server knows no such run.' : `The record could not be built: ${reply.error}`}
          </p>
          {reply.detail ? <p className="quiet small">{reply.detail}</p> : null}
          {reply.error === RECORD_UNAVAILABLE ? <p className="quiet small">It lands as experimental/simulation/record.py; the view reads it as soon as the server can import it.</p> : null}
        </div>
      </div>
    )
  }
  const { record: data } = reply
  return (
    <div className="record">
      <Header record={data} entry={entry} bundle={bundle} />
      {data.value ? (
        <section className="sec">
          <h3>Value verdict</h3>
          <Verdict value={data.value} onSelect={select} />
        </section>
      ) : null}
      <section className="sec">
        <h3>Knowledge-sedimentation ledger</h3>
        <Ledger record={data} selected={place} onSelect={select} />
        {place ? <Chain record={data} place={place} onClose={() => setPlace(null)} onTrial={onTrial} onRemark={onRemark} /> : data.ledger.length ? <p className="quiet small">Click a cell to open its chain of evidence: the failing drill, the Analyst's requirement, the Curator's change with its diff, and the mechanism events.</p> : null}
      </section>
      <section className="sec">
        <h3>Rounds <span className="cnt">{plural(data.rounds.length, 'round')}</span></h3>
        {summaries.length ? <ol className="rlines">{summaries.map((item) => <RoundLine key={item.round ?? 0} item={item} onTrial={onTrial} onRemark={onRemark} />)}</ol> : <p className="quiet">No round has been recorded yet.</p>}
      </section>
      <section className="sec">
        <h3>Curations by harness <span className="cnt">{plural(data.curations.length, 'curation')}</span></h3>
        <Curations record={data} />
      </section>
      <section className="sec">
        <h3>Inputs</h3>
        <Inputs record={data} />
      </section>
      <Mining name={data.run.name || runId.split('/')[0]} onOpenRun={onOpenRun} />
    </div>
  )
}
