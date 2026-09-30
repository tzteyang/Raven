/* The main view: the travel agency and the Curator side in conversation, round
   by round. The owner's messages sit on the reader's side, with the materials
   they hand over and, for the automatic standard assessor, its scorecard; each
   Curator reply starts from its diagnosis of every input and is a Harness
   revision grounded on those diagnoses, with what it changed in which strategy
   and the generated code and its bindings behind a fold. Each round's trial is
   a card in the conversation, just before the owner's remark on it; opening
   the card draws the trial out in the panel on the right. */

import { Fragment, useEffect, useMemo, useRef, useState } from 'react'

import { fileUrl, thumbsUrl } from '../api'
import { identityLine } from '../attribution'
import { splitRemark, timeline, unwrap } from '../cultivation'
import { fileName, roundVersions, tone } from '../derive'
import { OWNS, STRATEGIES } from '../mechanism'
import { opened, trialSummary } from '../trial'
import { AttachmentChips, AttachmentView } from './Attachments'
import { BasisBadge, Clamp, Fold, HeldBadge, RedLine, RequirementBadges, StateChip, StrategyBadge, TreatmentBadge } from './Badges'
import { Markdown } from './Markdown'
import { TrialTally } from './TrialPanel'
import { useThumbs } from './Trials'

import type { AttributionView } from '../attribution'
import type { ChangeView, Entry, Reply } from '../cultivation'
import type { Revision } from '../derive'
import type { Feedback, Run, Scenario, Signal } from '../model'
import type { TrialSummary } from '../trial'
import type { JSX, RefObject } from 'react'

const pretty = (value: unknown): string => (typeof value === 'string' ? value : JSON.stringify(value, null, 2))

/* Every change is code run as one of the four strategies; the legend says what each owns. */
function Legend(): JSX.Element {
  return (
    <p className="legend">
      {STRATEGIES.map((name) => (
        <span key={name} title={OWNS[name]}><StrategyBadge strategy={name} /> {OWNS[name].split(':')[0].toLowerCase()}</span>
      ))}
    </p>
  )
}

/* With an opening the owner's own onboarding message and its uploads lead the
   conversation; older runs show the task statement and the scenario's plan. */
function Onboarding({ runId, task: raw, opening, materials, origins }: { runId: string; task: string; opening: Signal[]; materials: string[]; origins: Run['origins'] }): JSX.Element {
  const [open, setOpen] = useState<string | null>(null)
  const handed = opening.flatMap((signal) => signal.attachments ?? [])
  const task = unwrap(raw)
  return (
    <>
      <div className="say owner">
        <span className="who">travel agency · onboarding</span>
        <div className="me">
          {opening.length ? (
            <>
              {opening.map((signal, i) => <Clamp key={i} long={signal.text.length > 1400}><Markdown text={signal.text} /></Clamp>)}
              <AttachmentChips materials={handed} open={open} onOpen={setOpen} origins={origins} />
              <Fold className="pasted" summary="The task statement the employee works under">{() => <Markdown text={task} />}</Fold>
            </>
          ) : (
            <>
              <Clamp long={task.length > 1400}><Markdown text={task} /></Clamp>
              {materials.length ? (
                <p className="mats"><span className="k">Opening materials in the scenario's staged plan</span>{materials.map((name) => <code key={name}>{name}</code>)}</p>
              ) : null}
            </>
          )}
        </div>
      </div>
      <AttachmentView run={runId} path={open} onClose={() => setOpen(null)} />
    </>
  )
}

function tally(signals: Signal[], red: Set<string>): { failed: number; redFailed: number; passed: number } {
  const items = signals.flatMap((signal) => signal.items)
  return {
    failed: items.filter((item) => tone(item.result) === 'fail').length,
    redFailed: items.filter((item) => tone(item.result) === 'fail' && red.has(item.id)).length,
    passed: items.filter((item) => tone(item.result) === 'pass').length,
  }
}

const rate = (value: number | undefined): string => (typeof value === 'number' ? `${Math.round(value * 100)}%` : '—')

/* The automatic standard assessor has no voice of its own: its signal is a
   scorecard against the declared, derived and sedimented criteria. */
function Scorecard({ signal, held }: { signal: Signal; held?: boolean }): JSX.Element {
  const passed = signal.items.filter((item) => tone(item.result) === 'pass').length
  const failed = signal.items.filter((item) => tone(item.result) === 'fail')
  return (
    <div className={`scorecard${held ? ' heldout' : ''}`}>
      <p className="sc-hd">
        <span className="src">{signal.source}</span>
        {held ? <span className="heldout-tag" title="Held out: never read by the Analyst nor cited to the Curator">held out</span> : null}
        <span>{signal.satisfied === null ? 'does not judge' : signal.satisfied ? 'satisfied' : 'not satisfied'}</span>
        {'must_hold_pass_rate' in signal.metrics ? <span>must hold {rate(signal.metrics.must_hold_pass_rate)}</span> : null}
        {'should_pass_rate' in signal.metrics ? <span>should {rate(signal.metrics.should_pass_rate)}</span> : null}
        <span className="dim">{passed} passed · {failed.length} failed of {signal.items.length}</span>
      </p>
      {failed.length ? (
        <ul className="sc-fails">
          {failed.map((item) => <li key={item.id}><code>{item.id}</code><BasisBadge basis={item.basis} /> {item.expected}{item.note ? <span className="dim"> — {item.note}</span> : null}</li>)}
        </ul>
      ) : null}
    </div>
  )
}

function Remark({
  runId, round, version, signals, holdout, heldOut, red, fresh, origins,
}: { runId: string; round: number; version: string; signals: Signal[]; holdout: Signal[]; heldOut: string[]; red: Set<string>; fresh: string[]; origins: Run['origins'] }): JSX.Element {
  const [open, setOpen] = useState<string | null>(null)
  const count = tally(signals, red)
  const spoken = signals.filter((signal) => signal.source !== 'standard' && (signal.text || signal.attachments?.length))
  const scored = signals.filter((signal) => signal.source === 'standard')
  return (
    <>
    <div className="say owner" id={`remark-${round}`}>
      <span className="who">travel agency · on the round {round} trial of {version}</span>
      <div className="me">
        {spoken.length === 0 ? <p className="dim">The owner left no remark this round.</p> : null}
        {spoken.map((signal, i) => {
          const { remark, pasted } = signal.source === 'agency' ? splitRemark(signal.text) : { remark: signal.text, pasted: [] }
          return (
            <div key={i}>
              {signal.source !== 'agency' ? <span className="src">{signal.source}</span> : null}
              <Markdown text={remark} />
              {pasted.map((item, j) => (
                <Fold key={j} className="pasted" summary={<><span className="k">Pasted material</span> <span className="ttl">{item.title}</span></>}>
                  {() => <Markdown text={item.text} />}
                </Fold>
              ))}
              <AttachmentChips materials={signal.attachments ?? []} open={open} onOpen={setOpen} origins={origins} />
            </div>
          )
        })}
        {scored.map((signal, i) => <Scorecard key={i} signal={signal} />)}
        <p className="tally">
          {count.failed ? <span className="f">{count.failed} failed</span> : null}
          {count.redFailed ? <span className="f">{count.redFailed} red line{count.redFailed === 1 ? '' : 's'} broken</span> : null}
          <span>{count.passed} passed</span>
        </p>
        {heldOut.length || holdout.length ? (
          <div className="heldout-block">
            <p className="mats"><span className="k">Held-out trial, never seen by the Analyst or the Curator</span>{heldOut.map((name) => <code key={name}>{name}</code>)}</p>
            {holdout.map((signal, i) => <Scorecard key={i} signal={signal} held />)}
          </div>
        ) : null}
        {fresh.length ? (
          <p className="mats"><span className="k">First opened in the next trial</span>{fresh.map((name) => <code key={name}>{name}</code>)}</p>
        ) : null}
      </div>
    </div>
    <AttachmentView run={runId} path={open} onClose={() => setOpen(null)} />
    </>
  )
}

function Requirements({ feedback, held }: { feedback: Feedback; held: Record<string, boolean | null> }): JSX.Element {
  return (
    <div className="analyst">
      <div className="analyst-hd">
        <span className="ico" />
        <span className="nm">Analyst</span>
        <span className={`chip ${feedback.decision}`}>{feedback.decision}</span>
        <span className="quiet">
          {feedback.requirements.length ? `${feedback.requirements.length} requirement${feedback.requirements.length === 1 ? '' : 's'}` : feedback.reason}
        </span>
      </div>
      {feedback.requirements.length ? (
        <ul className="reqs">
          {feedback.requirements.map((item, i) => (
            <li key={i}>
              <span className="marks">
                <RequirementBadges requirement={item} />
                {item.expectation !== 'new' ? <span className={`chip ${item.expectation}`}>{item.expectation.replace(/_/g, ' ')}</span> : null}
                <HeldBadge held={item.id ? held[item.id] : undefined} />
              </span>
              <Fold className="req" summary={<Markdown className="beh" text={item.behavior} />}>
                {() => (
                  <dl>
                    {item.situation ? <><dt>when</dt><dd>{item.situation}</dd></> : null}
                    <dt>observed</dt><dd><Markdown text={item.observed} /></dd>
                    <dt>accept</dt><dd><Markdown text={item.acceptance} /></dd>
                    {item.evidence.length ? <><dt>evidence</dt><dd className="ev">{item.evidence.join(' · ')}</dd></> : null}
                    {item.materials?.length ? <><dt>materials</dt><dd>{item.materials.map((name) => <code key={name}>{name}</code>)}</dd></> : null}
                    {item.grounds?.length ? <><dt>grounds</dt><dd className="ev">{item.grounds.join(' · ')}</dd></> : null}
                  </dl>
                )}
              </Fold>
            </li>
          ))}
        </ul>
      ) : null}
      {feedback.requirements.length && feedback.reason ? (
        <Fold className="why" summary="The Analyst's reason">{() => <Markdown text={feedback.reason} />}</Fold>
      ) : null}
    </div>
  )
}

/* One line per change until the reader opens it: the target, its strategy,
   how it treats the diagnosed mechanism, the inputs it addresses and the first
   lines of why; open, the whole why and what the Curator expects to see. */
function Change({ change }: { change: ChangeView }): JSX.Element {
  return (
    <details className="change">
      <summary>
        <span className="change-hd">
          <code>{change.target}</code>
          <StrategyBadge strategy={change.strategy} />
          <TreatmentBadge treatment={change.treatment} />
          {change.addresses.map((about) => <span key={about} className="about" title="An input the selection grounded this target on">{about}</span>)}
          <span className="chev" />
        </span>
        {change.reason ? <Markdown className="why" text={change.reason} /> : null}
      </summary>
      {change.expected ? <dl><dt>expect</dt><dd><Markdown text={change.expected} /></dd></dl> : null}
    </details>
  )
}

/* Before it changed anything the Curator placed every input against the
   Harness: its mechanism, the state of that mechanism and the evidence. */
function Diagnoses({ attribution }: { attribution: AttributionView }): JSX.Element {
  const spent = [attribution.calls !== null ? `${attribution.calls} call${attribution.calls === 1 ? '' : 's'}` : '', attribution.queries !== null ? `${attribution.queries} quer${attribution.queries === 1 ? 'y' : 'ies'}` : ''].filter(Boolean).join(' · ')
  return (
    <div className="diagnoses">
      <p className="diag-hd">
        <span className="k">Diagnosis</span>
        <span>{attribution.diagnoses.length} input{attribution.diagnoses.length === 1 ? '' : 's'}</span>
        {identityLine(attribution.identity) ? <code title="The attributor: model, implementation and prompts digest">{identityLine(attribution.identity)}</code> : null}
        {spent ? <span className="dim">{spent}</span> : null}
      </p>
      {attribution.paused ? <p className="warn small">The attribution paused: {attribution.paused}</p> : null}
      {attribution.error ? <p className="bad small">The attribution failed: {attribution.error}</p> : null}
      <ul className="diag-list">
        {attribution.diagnoses.map((diagnosis) => (
          <li key={diagnosis.about}>
            <span className="about">{diagnosis.about}</span>
            <StateChip state={diagnosis.state} />
            {diagnosis.mechanism ? <span className="mech">{diagnosis.mechanism}</span> : null}
            {diagnosis.placement || diagnosis.earlier || diagnosis.evidence?.length ? (
              <Fold className="fold small" summary="evidence">
                {() => (
                  <dl>
                    {diagnosis.placement ? <><dt>lands</dt><dd>{diagnosis.placement}</dd></> : null}
                    {diagnosis.earlier ? <><dt>earlier</dt><dd>{diagnosis.earlier}</dd></> : null}
                    {diagnosis.evidence?.length ? <><dt>evidence</dt><dd className="ev">{diagnosis.evidence.join(' · ')}</dd></> : null}
                  </dl>
                )}
              </Fold>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  )
}

function evidenceText(reply: Reply, change: ChangeView, version: string): string {
  if (!reply.revision.deployed) return 'Not deployed.'
  if (!reply.trial || !change.evidence) return `Not yet tried: no later round ran ${version}.`
  const where = `Round ${reply.trial} trial of ${version}`
  const { calls, errors, note } = change.evidence
  if (calls === null) return `${where}: ${note}.`
  const failed = errors ? `, ${errors} error${errors === 1 ? '' : 's'}` : ''
  return calls
    ? `${where}: called ${calls} time${calls === 1 ? '' : 's'}${failed} (${note}).`
    : `${where}: no call recorded${failed} (${note}).`
}

function Assembled({ reply, change }: { reply: Reply; change: ChangeView }): JSX.Element {
  return (
    <div className="asm">
      <div className="asm-hd"><code>{change.target}</code><StrategyBadge strategy={change.strategy} /><TreatmentBadge treatment={change.treatment} /></div>
      <dl>
        {change.strategy ? <><dt>owns</dt><dd>{OWNS[change.strategy]}</dd></> : null}
        {change.hooks.map((hook) => <Fragment key={hook.name}><dt>{hook.name}</dt><dd><code>{hook.value}</code></dd></Fragment>)}
        <dt>check</dt><dd>{change.bound ? 'Bound by the host check before deployment.' : 'Not listed as bound by the host check.'}</dd>
        <dt>trial</dt><dd className={change.evidence?.calls === 0 ? 'warn' : ''}>{evidenceText(reply, change, reply.revision.label)}</dd>
        {change.verification ? <><dt>verify</dt><dd>{change.verification}</dd></> : null}
        {change.files.length ? <><dt>code</dt><dd>{change.files.map((path) => <code key={path} className="ref">{path}</code>)}</dd></> : null}
      </dl>
      {change.value === undefined ? null : <Fold className="fold src" summary="binding value">{() => <pre>{pretty(change.value)}</pre>}</Fold>}
    </div>
  )
}

function CodeLayer({ reply }: { reply: Reply }): JSX.Element {
  const files = Object.entries(reply.files)
  const validation = reply.revision.curation.generated?.validation
  return (
    <div className="code-layer">
      {reply.changes.length ? (
        <section><h4>Bindings</h4>{reply.changes.map((change, i) => <Assembled key={i} reply={reply} change={change} />)}</section>
      ) : null}
      {reply.design ? (
        <section>
          <h4>Design</h4>
          <Fold className="fold src" summary="the Curator's technical design">{() => <Markdown className="design" text={reply.design} />}</Fold>
        </section>
      ) : null}
      {files.length ? (
        <section>
          <h4>Generated files <span className="cnt">{files.length}</span></h4>
          {files.map(([path, text]) => (
            <Fold key={path} className="fold src" summary={<><code>{path}</code> · {text.length} chars</>}>{() => <pre>{text}</pre>}</Fold>
          ))}
        </section>
      ) : null}
      {validation ? (
        <section>
          <h4>Host check</h4>
          {validation.errors.length
            ? <ul className="plain">{validation.errors.map((line, i) => <li key={i} className="bad">{line}</li>)}</ul>
            : <p className="quiet">Passed with {validation.observations.length} observation{validation.observations.length === 1 ? '' : 's'}.</p>}
        </section>
      ) : null}
    </div>
  )
}

/* What this revision did with each material handed over just before it: where
   the diagnosis says its content lands, and the targets grounded on it. */
function Intake({ reply }: { reply: Reply }): JSX.Element {
  return (
    <div className="intake">
      {reply.handover.map((item) => (
        <p key={item.name}>
          <span className="k">Handed over</span>
          <code>{item.name}</code>
          <span className={`att-kind ${item.kind}`}>{item.kind}</span>
          <StateChip state={item.diagnosis?.state} />
          {item.targets.length ? item.targets.map((target) => <code key={target} className="hardt">{target}</code>) : <span className="dim">no target grounded on it</span>}
          {item.diagnosis?.placement ? <span className="place">{item.diagnosis.placement}</span> : null}
        </p>
      ))}
      {reply.pasted.length ? <p><span className="k">Pasted</span>{reply.pasted.map((title) => <code key={title}>{title}</code>)}</p> : null}
    </div>
  )
}

/* What the Curator returned, as the curation record keeps it: the candidate it
   generated (plan and artifact), or the whole record when no candidate came out. */
function rawOutput(reply: Reply): { source: string; text: string } {
  const { curation } = reply.revision
  const candidate = curation.generated?.candidate
  return {
    source: `${candidate ? 'generated candidate' : 'curation record'}${curation.file ? ` in ${curation.file}` : ''}`,
    text: JSON.stringify(candidate ?? curation, null, 2),
  }
}

function ReplyView({ reply, onTrial }: { reply: Reply; onTrial: (round: number) => void }): JSX.Element {
  const { revision } = reply
  const [raw, setRaw] = useState(false)
  const strategies = STRATEGIES.filter((name) => reply.changes.some((change) => change.strategy === name))
  return (
    <div className="say curator" id={`reply-${revision.key}`}>
      <span className="who">
        <span className="cd" />Curator
        <code className={revision.deployed ? 'ver' : 'ver kept'}>{revision.label}</code>
        {revision.deployed ? <span>{reply.from} → {revision.label}</span> : <span>stays on {revision.label}</span>}
        {strategies.map((name) => <StrategyBadge key={name} strategy={name} />)}
        {reply.trial ? <button className="link" onClick={() => onTrial(reply.trial!)}>tried in round {reply.trial}</button> : revision.deployed ? <span className="dim">not yet tried</span> : null}
        <button className="link raw-toggle" aria-pressed={raw} title="Show what the Curator returned, unrendered" onClick={() => setRaw(!raw)}>{raw ? 'rendered' : 'raw'}</button>
      </span>
      {raw ? (
        <div className="ai reply raw">
          <p className="quiet small">{rawOutput(reply).source}</p>
          <pre className="raw">{rawOutput(reply).text}</pre>
        </div>
      ) : (
      <div className="ai reply">
        {reply.failure ? (
          <div className="failed">
            <p>This revision failed, so the employee stays on {revision.label}.</p>
            <Markdown text={reply.failure} />
          </div>
        ) : null}
        {reply.attribution ? <Diagnoses attribution={reply.attribution} /> : null}
        {reply.understanding ? <Clamp long={reply.understanding.length > 1600}><Markdown className="under" text={reply.understanding} /></Clamp> : null}
        {reply.selection?.understanding ? (
          <Fold className="why" summary="Why these targets (the selection)">{() => <Markdown text={reply.selection!.understanding} />}</Fold>
        ) : null}
        {reply.handover.length || reply.pasted.length ? <Intake reply={reply} /> : null}
        {reply.changes.length ? (
          <div className="changes">{reply.changes.map((change, i) => <Change key={i} change={change} />)}</div>
        ) : !reply.failure ? <p className="dim">No change: the Harness stays as it was.</p> : null}
        {reply.changes.length || Object.keys(reply.files).length || reply.design ? (
          <Fold className="code" summary={<>Generated code and bindings{Object.keys(reply.files).length ? ` · ${Object.keys(reply.files).length} files` : ''}</>}>
            {() => <CodeLayer reply={reply} />}
          </Fold>
        ) : null}
      </div>
      )}
    </div>
  )
}

/** True once the element has come near the viewport; never where the browser cannot tell. */
function useSeen(ref: RefObject<Element | null>): boolean {
  const [seen, setSeen] = useState(false)
  useEffect(() => {
    const node = ref.current
    if (seen || !node || typeof IntersectionObserver === 'undefined') return
    const watch = new IntersectionObserver((rows) => {
      if (rows.some((row) => row.isIntersecting)) setSeen(true)
    }, { rootMargin: '200px' })
    watch.observe(node)
    return () => watch.disconnect()
  }, [ref, seen])
  return seen
}

function DeckTile({ path, drill, seen, onOpen }: { path: string; drill: string; seen: boolean; onOpen: () => void }): JSX.Element {
  const thumbs = useThumbs(seen ? thumbsUrl(path) : null)
  return (
    <button className="dtile" title={`${drill}: ${fileName(path)}`} onClick={onOpen}>
      {thumbs.pages[0] ? <img src={fileUrl(thumbs.pages[0])} alt={`${drill} deck, first page`} loading="lazy" /> : <span className="ph">{thumbs.loading ? 'rendering' : 'deck'}</span>}
      <span className="cap">{drill}</span>
    </button>
  )
}

/* A round's trial in the conversation: what ran against which version and how
   the owner judged it, with a way in to each drill. The whole card opens the
   trial panel; while that panel shows this round the card says so. */
function TrialCard({ summary, open, onOpen }: { summary: TrialSummary; open: boolean; onOpen: (drill?: string) => void }): JSX.Element {
  const ref = useRef<HTMLDivElement>(null)
  const seen = useSeen(ref)
  const delivered = summary.drills.filter((drill) => drill.deck)
  return (
    <div ref={ref} className={`trialcard${open ? ' on' : ''}`} id={`trial-${summary.round}`}>
      <button className="tc-main" onClick={() => onOpen()} aria-expanded={open} aria-label={`Open the round ${summary.round} trial`}>
        <span className="tc-ic" aria-hidden="true">
          <svg viewBox="0 0 16 16" width="14" height="14"><path d="M5 3.2v9.6L12.6 8z" fill="currentColor" /></svg>
        </span>
        <span className="tc-t">Round {summary.round} trial</span>
        <span className="tc-on">on <code className="ver">{summary.version}</code></span>
        <TrialTally summary={summary} />
        <span className="tc-go">{open ? 'showing' : 'open'}<svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true"><path d="M6 3.5 10.5 8 6 12.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg></span>
      </button>
      <div className="tc-meta">
        <span>{summary.drills.length} drill{summary.drills.length === 1 ? '' : 's'}</span>
        {summary.interceptions ? <span className="hard">{summary.interceptions} interception{summary.interceptions === 1 ? '' : 's'}</span> : null}
        {summary.graphs ? <span>{summary.graphs} playbook run{summary.graphs === 1 ? '' : 's'}</span> : null}
        {delivered.length ? <span className="good">{delivered.length} deck{delivered.length === 1 ? '' : 's'}</span> : null}
      </div>
      {summary.drills.length ? (
        <div className="tc-drills">
          {summary.drills.map((drill) => (
            <button key={drill.name} className="tc-drill" onClick={() => onOpen(drill.name)} title={`Open the ${drill.name} conversation`}>
              <span className="nm">{drill.name}</span>
              <span className="m">{drill.turns} turn{drill.turns === 1 ? '' : 's'}</span>
              {drill.interceptions ? <span className="hard" title="Interceptions by the Harness">{drill.interceptions}</span> : null}
            </button>
          ))}
        </div>
      ) : null}
      {delivered.length ? (
        <div className="tc-decks">
          {delivered.map((drill) => <DeckTile key={drill.name} path={drill.deck!} drill={drill.name} seen={seen} onOpen={() => onOpen(drill.name)} />)}
        </div>
      ) : null}
    </div>
  )
}

export function Cultivation({
  run, runId, name, revisions, scenario, trial, onTrial,
}: { run: Run; runId: string; name: string; revisions: Revision[]; scenario: Scenario; trial: number | null; onTrial: (round: number, drill?: string) => void }): JSX.Element {
  const entries = useMemo(() => timeline(run, revisions), [run, revisions])
  const versions = useMemo(() => roundVersions(run, revisions), [run, revisions])
  const red = new Set(scenario.criteria.filter((row) => row.severity === 'red_line').map((row) => row.id))
  const summary = (round: number): TrialSummary | null => trialSummary(run, round - 1, versions[round - 1] ?? 'v0', red)
  const fresh = (round: number): string[] => {
    const seen = new Set(run.rounds.slice(0, round).flatMap((item) => opened(item, scenario.materials)))
    return opened(run.rounds[round], scenario.materials).filter((material) => !seen.has(material))
  }
  const view = (entry: Entry, i: number): JSX.Element => {
    switch (entry.kind) {
      case 'onboarding':
        return <Onboarding key={i} runId={runId} task={entry.task} opening={entry.opening} materials={scenario.initial} origins={run.origins} />
      case 'remark': {
        const card = summary(entry.round)
        return (
          <div key={i} className="round-block">
            {card ? <TrialCard summary={card} open={trial === entry.round} onOpen={(drill) => onTrial(entry.round, drill)} /> : null}
            <Remark runId={runId} round={entry.round} version={entry.version} signals={entry.signals} holdout={entry.holdout} heldOut={entry.heldOut} red={red} fresh={fresh(entry.round)} origins={run.origins} />
          </div>
        )
      }
      case 'requirements':
        return <Requirements key={i} feedback={entry.feedback} held={entry.held} />
      case 'reply':
        return <ReplyView key={i} reply={entry.reply} onTrial={onTrial} />
      case 'silence':
        return <p key={i} className="silence">{entry.text}</p>
    }
  }
  return (
    <div className="convo">
      <div className="task">
        <span className="eyebrow">Cultivation</span>
        <h2>{name}</h2>
        <p className="quiet">
          The owner speaks to the Curator side after each trial; every Curator reply is a revision of the employee's Harness.
          {red.size ? <> Criteria marked <RedLine /> are ones the owner never tolerates missing.</> : null}
        </p>
        <Legend />
        {run.error ? <p className="runerr"><span className="k">ended with an error</span>{run.error}</p> : null}
      </div>
      {entries.map(view)}
    </div>
  )
}
