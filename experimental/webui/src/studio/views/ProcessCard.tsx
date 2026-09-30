/* The background card that answers one change request: the Analyst's
   requirements and decision, then (when it curates) the Curator's diagnosis
   of every input, the selection it grounded on those diagnoses, its stages
   and what it read, the plan of every scope it changed, what preparation did,
   the Harness map before and after and the playbooks planning prepared, and a
   footer saying what happens next. While a live curation runs it has left no
   record yet, so the card shows its progress: the stage under way and what it
   has spent. */

import { useState } from 'react'

import { grounded, identityLine } from '../../attribution'
import { hooks } from '../../mechanism'
import { T } from '../copy'
import { STAGES, liveStages } from '../curation'
import { artifactOf, harnessMap, layers } from '../harness'
import { Fold, Icon, Markdown, StateChip, Target } from './bits'

import type { JSX } from 'react'
import type { AttributionView } from '../../attribution'
import type { Requirement, Selection } from '../../model'
import type { Playbook } from '../harness'
import type { CurationProgress, CurationView, Footer, Observed, ProcessEntry, Read, Scope, Stage } from '../types'

export interface CardActions {
  onDiff: (card: string, scope: string, root: boolean, target: string) => void
  onInspect: (card: string) => void
  onRaw: (card: string, scope: string) => void
  /** The card and scope whose raw output the side pane shows, as `card:scope`. */
  rawOpen?: string | null
  onEvidence?: (text: string, round: number) => void
  onOpenTrial?: () => void
  onArchive?: () => void
  onAttach?: () => void
}

function curateCrumb(card: ProcessEntry): string {
  const view = card.curation
  if (view?.paused) return T.stepPaused(view.paused.stage ? T.stages[view.paused.stage] : null, view.paused.scope)
  if (view && !view.deployed) return T.stepKept
  return T.stepCurate(view?.to ?? (card.footer.kind === 'curating' ? card.footer.version : ''))
}

function Crumbs({ card }: { card: ProcessEntry }): JSX.Element {
  const curating = card.curationState !== 'none'
  return (
    <span className="st-crumbs">
      {!card.onboarding && (
        <>
          <span data-state={card.analysis}>{card.analysis === 'running' ? <i className="dot run" /> : <Icon name="check" size={12} />}{T.stepAnalyst}</span>
          <Icon name="chevron" size={11} className="st-sep" />
          <span data-state={card.feedback ? 'done' : 'todo'}>{T.stepDecide}</span>
          <Icon name="chevron" size={11} className="st-sep" />
        </>
      )}
      <span data-state={card.curationState === 'running' ? 'running' : curating ? 'done' : 'off'}>
        {card.curationState === 'running' && <i className="dot run" />}
        {curating ? curateCrumb(card) : T.stepNoCurate}
      </span>
    </span>
  )
}

function RequirementRow({ requirement, held, onEvidence }: { requirement: Requirement; held: boolean | null | undefined; onEvidence?: (text: string) => void }): JSX.Element {
  const strength = requirement.strength ?? 'should'
  return (
    <div className="st-req">
      <div className="st-reqmarks">
        {requirement.id && <span className="st-rid">{requirement.id}</span>}
        <span className={`st-chip ${strength === 'must_hold' ? 'must' : 'should'}`}>{T.strength[strength]}</span>
      </div>
      <div>
        <p className="b">
          {requirement.behavior}
          {requirement.repeats && <span className="st-repeat">{T.repeats(requirement.repeats)}</span>}
          {held !== undefined && <span className="st-held" data-held={String(held)} title={T.heldHint}>{T.held[String(held)]}</span>}
        </p>
        {requirement.situation && (
          <p className="m"><span className="k">{T.situation}</span>{requirement.situation}</p>
        )}
        <p className="m">
          <span className="k">{T.observed}</span>{requirement.observed}
        </p>
        {requirement.evidence.length > 0 && (
          <p className="m">
            <span className="k">{T.evidence}</span>
            {requirement.evidence.map((text, i) => (
              <button type="button" key={i} className="st-ev" onClick={() => onEvidence?.(text)} title={text}>
                {text.length > 60 ? `${text.slice(0, 60)}…` : text}
              </button>
            ))}
          </p>
        )}
        <p className="m">
          <span className="k">{T.acceptance}</span>{requirement.acceptance}
          <span className="st-meta">
            {T.expectation[requirement.expectation] ?? requirement.expectation}
            {typeof requirement.recurrence === 'number' && requirement.recurrence > 0 ? ` · ${T.recurrence(requirement.recurrence)}` : ''}
          </span>
        </p>
        {(requirement.materials ?? []).length > 0 && (
          <p className="m"><span className="k">{T.materials}</span>{requirement.materials!.map((name) => <code key={name} className="st-mat">{name}</code>)}</p>
        )}
      </div>
    </div>
  )
}

function Analysis({ card, actions }: { card: ProcessEntry; actions: CardActions }): JSX.Element | null {
  if (card.onboarding) return <p className="st-quiet">{T.onboardingSkipsAnalyst}</p>
  if (card.analysis === 'running') return <p className="st-quiet"><i className="dot run" /> {T.analysing}</p>
  if (!card.feedback) return <p className="st-bad">{T.analysisFailed}</p>
  const feedback = card.feedback
  return (
    <div className="st-seg st-analysis">
      <div className="st-decision">
        <span className={`st-chip ${feedback.decision}`}>{T.decision[feedback.decision] ?? feedback.decision}</span>
        {card.handover && <span className="st-chip curate">{T.handoverChip}</span>}
        <span className="st-reason">{feedback.reason}</span>
      </div>
      {card.handover && <p className="st-quiet">{T.handoverNote}</p>}
      {feedback.requirements.length > 0 && (
        <div className="st-reqs">
          {feedback.requirements.map((requirement, i) => (
            <RequirementRow
              key={i}
              requirement={requirement}
              held={requirement.id && requirement.id in card.held ? card.held[requirement.id] : undefined}
              onEvidence={(text) => actions.onEvidence?.(text, card.round)}
            />
          ))}
        </div>
      )}
      {feedback.filtered.length > 0 && (
        <Fold summary={T.filtered(feedback.filtered.length)}>
          <ul className="st-list">{feedback.filtered.map((text, i) => <li key={i}>{text}</li>)}</ul>
        </Fold>
      )}
    </div>
  )
}

function Stages({ stages }: { stages: Stage[] }): JSX.Element {
  return (
    <div className="st-stages">
      {stages.map((stage, i) => (
        <span key={stage.id} className="st-stagewrap">
          {i > 0 && <i className="st-stage-sep" />}
          <span className="st-stage" data-state={stage.state}>
            <i className="d" />
            {T.stages[stage.id]}
            {(stage.calls > 0 || stage.queries > 0) && <span className="n">{T.stageCounts(stage.calls, stage.queries)}</span>}
          </span>
        </span>
      ))}
    </div>
  )
}

/* Every input the curation took, placed against the Harness before anything
   was chosen; the targets the selection grounded on each follow it. */
function Diagnoses({ attribution, selection, onTarget }: { attribution: AttributionView; selection: Selection | null; onTarget?: (target: string) => void }): JSX.Element {
  const by = grounded(selection).by
  const spent = T.attributorSpent(attribution.calls, attribution.queries)
  return (
    <div className="st-diags">
      <div className="st-diaghead">
        <p className="st-label">{T.diagnosis} · {T.diagnosed(attribution.diagnoses.length)}</p>
        {identityLine(attribution.identity) && <code className="st-who-attr" title={JSON.stringify(attribution.identity)}>{identityLine(attribution.identity)}</code>}
        {spent && <span className="st-meta">{spent}</span>}
      </div>
      {attribution.paused && <p className="st-warn">{T.attributionPaused(attribution.paused)}</p>}
      {attribution.error && <p className="st-bad">{T.attributionFailed(attribution.error)}</p>}
      {attribution.diagnoses.map((diagnosis) => {
        const targets = by[diagnosis.about] ?? []
        return (
          <div key={diagnosis.about} className="st-diag">
            <div className="st-diagline">
              <span className="st-about" title={diagnosis.about}>{T.about(diagnosis.about)}</span>
              <StateChip state={diagnosis.state} />
              {diagnosis.mechanism && <span className="st-mech" title={diagnosis.mechanism}>{diagnosis.mechanism}</span>}
            </div>
            {(targets.length > 0 || selection) && (
              <div className="st-diagtargets">
                <span className="k">{T.grounds}</span>
                {targets.length ? targets.map((target) => <Target key={target} name={target} onClick={onTarget ? () => onTarget(target) : undefined} />) : <span className="st-none">{T.ungrounded}</span>}
              </div>
            )}
            {(diagnosis.placement || diagnosis.earlier || (diagnosis.evidence ?? []).length > 0) && (
              <Fold summary={<span className="st-meta">{T.diagEvidence}{diagnosis.placement ? ` · ${T.diagPlacement}` : ''}{diagnosis.earlier ? ` · ${T.diagEarlier}` : ''}</span>}>
                <dl className="st-kv">
                  {diagnosis.placement && <><dt>{T.diagPlacement}</dt><dd>{diagnosis.placement}</dd></>}
                  {diagnosis.earlier && <><dt>{T.diagEarlier}</dt><dd>{diagnosis.earlier}</dd></>}
                  {(diagnosis.evidence ?? []).length > 0 && (
                    <><dt>{T.diagEvidence}</dt><dd><ul className="st-list">{diagnosis.evidence!.map((line, i) => <li key={i}>{line}</li>)}</ul></dd></>
                  )}
                </dl>
              </Fold>
            )}
          </div>
        )
      })}
    </div>
  )
}

function SelectionView({ selection }: { selection: Selection }): JSX.Element {
  return (
    <Fold summary={<><b>{T.selection}</b><span className="st-peek">{firstLine(selection.understanding)}</span></>}>
      <p className="st-meta">{T.selectionWhy}</p>
      <Markdown text={selection.understanding} />
    </Fold>
  )
}

function PlanView({ scope, view, onTarget }: { scope: Scope; view: CurationView; onTarget: (target: string) => void }): JSX.Element | null {
  const plan = scope.plan
  if (!plan) return null
  const grounds = grounded(scope.selection).targets
  const after = artifactOf(view.after, scope.name, scope.root)
  const reasons = Object.entries(plan.node_reasons ?? {})
  return (
    <div className="st-plan">
      {plan.understanding && (
        <Fold summary={<><b>{T.understanding}</b><span className="st-peek">{firstLine(plan.understanding)}</span></>}>
          <Markdown text={plan.understanding} />
        </Fold>
      )}
      {plan.design && (
        <Fold summary={<><b>{T.design}</b><span className="st-peek">{firstLine(plan.design)}</span></>}>
          <Markdown text={plan.design} />
        </Fold>
      )}
      <div className="st-changes">
        <p className="st-label">{T.changes(plan.changes.length)}</p>
        {plan.changes.map((change, i) => {
          const bound = hooks(change.target, after.values[change.target])
          return (
            <div key={i} className="st-change">
              <div className="st-changehead">
                <Target name={change.target} onClick={() => onTarget(change.target)} />
                {change.treatment && <span className="st-treat" data-treatment={change.treatment} title={T.treatmentHint}>{T.treatment[change.treatment] ?? change.treatment}</span>}
                {(grounds[change.target] ?? []).map((about) => <span key={about} className="st-aboutchip" title={about}>{T.about(about)}</span>)}
              </div>
              <p><span className="k">{T.reason}</span>{change.reason}</p>
              <p><span className="k">{T.expected}</span>{change.expected}</p>
              <p className="m"><span className="k">{T.verification}</span>{change.verification}</p>
              {bound.length > 0 && (
                <p className="m st-hooks">
                  {bound.map((hook) => <span key={hook.name} className="st-hook"><span className="k">{T.hooks[hook.name] ?? hook.name}</span><code>{hook.value}</code></span>)}
                </p>
              )}
            </div>
          )
        })}
      </div>
      {reasons.length > 0 && (
        <Fold summary={<><b>{T.nodeReasons}</b><span className="st-peek">{reasons.length}</span></>}>
          <dl className="st-kv">{reasons.map(([node, reason]) => <><dt key={`${node}-k`}><code>{node}</code></dt><dd key={`${node}-v`}>{reason}</dd></>)}</dl>
        </Fold>
      )}
    </div>
  )
}

function PreparedList({ scope }: { scope: Scope }): JSX.Element | null {
  if (!scope.prepared.length) return null
  return (
    <div className="st-prepared">
      <p className="st-label" title={T.preparedNote}>{T.prepared}</p>
      {scope.prepared.map((row, i) => (
        <p key={i} className="st-prep">
          <i className="st-sd" data-surface={row.owner} />
          <b>{T.surfaces[row.owner] ?? row.owner}</b>
          <span className="st-meta">{T.preparedOp[row.operation] ?? row.operation}</span>
          <code>{row.summary}</code>
        </p>
      ))}
    </div>
  )
}

const firstLine = (text: string): string => {
  const line = text.split('\n').map((row) => row.replace(/^#+\s*/, '').trim()).find((row) => row.length > 0) ?? ''
  return line.length > 48 ? `${line.slice(0, 48)}…` : line
}

function HarnessMap({ view, onCell }: { view: CurationView; onCell: (scope: string, root: boolean, target: string) => void }): JSX.Element {
  const rows = harnessMap(view.before, view.after, T.scopeRoot).filter((row) => Object.values(row.cells).some((cells) => cells.length))
  const loose = rows.some((row) => row.cells.other.length > 0)
  const surfaces = ['memory', 'planning', 'capability', 'action', ...(loose ? ['other' as const] : [])] as const
  return (
    <div className="st-mapwrap">
      <div className="st-maphead">
        <p className="st-label">{T.mapTitle} · {view.from} → {view.to}</p>
        <span className="st-legend">
          <i data-state="changed" />{T.mapLegendChanged}
          <i data-state="new" />{T.mapLegendNew}
          <i data-state="kept" />{T.mapLegendKept}
        </span>
      </div>
      <div className="st-map" role="table" data-cols={surfaces.length}>
        <div className="st-mh" />
        {surfaces.map((surface) => <div key={surface} className="st-mh"><i className="st-sd" data-surface={surface} />{T.surfaces[surface]} <small>{surface === 'other' ? T.looseFiles : surface}</small></div>)}
        {rows.map((row) => (
          <div key={row.scope} className="st-mrow" style={{ display: 'contents' }}>
            <div className="st-rowh">
              <span>{row.scope}</span>
              {row.changed > 0 && <small>{T.changes(row.changed)}</small>}
            </div>
            {surfaces.map((surface) => (
              <div key={surface} className="st-mc">
                {row.cells[surface].length === 0 && <span className="st-none">{T.mapEmpty}</span>}
                {row.cells[surface].map((cell) => (
                  <button type="button" key={cell.target} className="st-cell" data-state={cell.state} title={cell.target} onClick={() => onCell(row.root ? '' : row.scope, row.root, cell.target)}>
                    {surface === 'other' ? T.looseFiles : cell.target.split('.').slice(1).join('.') || cell.target}
                  </button>
                ))}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

function Graph({ book }: { book: Playbook }): JSX.Element {
  return (
    <div className="st-pb">
      <p className="st-pb-h">{book.name}</p>
      {layers(book.nodes).map((layer, i) => (
        <div key={i} className="st-pb-layerwrap">
          {i > 0 && <div className="st-pb-arrow">↓</div>}
          <div className="st-pb-layer">
            {layer.map((node) => (
              <div key={node.id} className="st-pb-node" data-state="kept" title={node.summary}>
                <span>{node.summary || node.id}</span>
                <small>{node.subagent || '—'}</small>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

/* The playbooks this scope's planning strategy compiled at prepare, as the host check recorded their specs. */
function Playbooks({ books }: { books: Playbook[] }): JSX.Element | null {
  if (!books.length) return null
  return (
    <div className="st-pbs">
      <p className="st-label">{T.playbookTitle}</p>
      <div className="st-pbgrid">{books.map((book) => <Graph key={book.name} book={book} />)}</div>
    </div>
  )
}

function Reads({ reads, onObserved }: { reads: Read[]; onObserved?: (observed: Observed) => void }): JSX.Element | null {
  if (!reads.length) return null
  const counts = new Map<string, number>()
  for (const read of reads) counts.set(read.tool, (counts.get(read.tool) ?? 0) + 1)
  const summary = [...counts].map(([tool, n]) => `${T.readTool[tool] ?? tool} ${n}`).join(' · ')
  return (
    <Fold summary={<><Icon name="book" size={13} />{T.reads(reads.length, summary)}</>}>
      {counts.has('read_observation') && <p className="st-quiet st-readsnote">{T.readsNote}</p>}
      <div className="st-reads">
        {reads.map((read, i) => (
          <div key={i} className="st-read" data-failed={read.failed || undefined}>
            <p className="h">
              <span className="st-rstage">{T.stages[read.stage] ?? read.stage}</span>
              <b>{T.readTool[read.tool] ?? read.tool}</b>
              <code>{read.target}</code>
              {read.observed && (
                <button type="button" className="st-ev" onClick={() => onObserved?.(read.observed!)}>{T.readObserved(read.observed)}</button>
              )}
              {read.failed && <em className="st-bad">{T.readFailed}</em>}
            </p>
            {read.preview && <p className="p">{read.preview}</p>}
          </div>
        ))}
      </div>
    </Fold>
  )
}

/* A curation under way: every stage before the Curator's current one done,
   and what it has spent so far, which the progress file counts for the
   attribution while it diagnoses and for the generation after. */
function Progress({ progress }: { progress: CurationProgress }): JSX.Element {
  const blank: Stage[] = STAGES.map((id) => ({ id, state: 'todo', calls: 0, queries: 0 }))
  const spent = T.progressSpent(progress.stage === 'diagnose', progress.calls, progress.queries)
  return (
    <div className="st-seg st-curation">
      <p className="st-quiet">{progress.scope ? `${T.progressScope(progress.scope)} · ${spent}` : spent}</p>
      <Stages stages={liveStages(blank, STAGES.indexOf(progress.stage))} />
    </div>
  )
}

function Curation({ card, actions }: { card: ProcessEntry; actions: CardActions }): JSX.Element | null {
  const view = card.curation
  const [tab, setTab] = useState(0)
  if (!view) {
    if (card.curationState === 'running' && card.progress) return <Progress progress={card.progress} />
    return card.attribution ? <div className="st-seg st-curation"><Diagnoses attribution={card.attribution} selection={null} /></div> : null
  }
  const scope = view.scopes[Math.min(tab, view.scopes.length - 1)]
  const onTarget = (target: string) => actions.onDiff(card.key, scope.name, scope.root, target)
  const budget = view.budget ? T.budget(view.budget.generation, view.budget.attribution) : ''
  const mapped = view.deployed || harnessMap(view.before, view.after, T.scopeRoot).some((row) => Object.values(row.cells).some((cells) => cells.length))
  return (
    <div className="st-seg st-curation">
      <div className="st-scopebar">
        {view.scopes.length > 1 && (
          <div className="st-tabs" role="tablist">
            {view.scopes.map((item, i) => (
              <button type="button" role="tab" key={item.name || 'root'} aria-selected={i === tab} onClick={() => setTab(i)}>
                {item.root ? T.scopeRoot : item.name}
              </button>
            ))}
          </div>
        )}
        <span className="grow" />
        {scope.outputs.length > 0 && (
          <button
            type="button"
            className="st-btn st-rawbtn"
            aria-pressed={actions.rawOpen === `${card.key}:${scope.name}`}
            onClick={() => actions.onRaw(card.key, scope.name)}
            title={T.rawOutputHint}
          >
            <Icon name="braces" size={14} />
            {T.rawOutput}
            <span className="n">{scope.outputs.length}</span>
          </button>
        )}
      </div>
      <Stages stages={scope.stages} />
      {scope.attribution && <Diagnoses attribution={scope.attribution} selection={scope.selection} onTarget={onTarget} />}
      {scope.selection && <SelectionView selection={scope.selection} />}
      <Reads reads={scope.reads} onObserved={(observed) => actions.onEvidence?.(observed.session, card.round)} />
      <PlanView scope={scope} view={view} onTarget={onTarget} />
      <PreparedList scope={scope} />
      {mapped && <HarnessMap view={view} onCell={(name, root, target) => actions.onDiff(card.key, name, root, target)} />}
      <Playbooks books={scope.playbooks} />
      {view.paused && budget && <p className="st-quiet">{budget}</p>}
      {!view.paused && (
        <p className={view.validation.errors.length ? 'st-bad' : 'st-quiet'}>
          {view.validation.errors.length ? T.validationFailed(view.validation.errors.length) : T.validationOk(view.validation.observations)}
          {!view.deployed && view.error ? ` · ${T.curationFailed}` : ''}
          {budget ? ` · ${budget}` : ''}
        </p>
      )}
    </div>
  )
}

function FooterRow({ footer, mode, latest, actions }: { footer: Footer; mode: 'live' | 'replay'; latest: boolean; actions: CardActions }): JSX.Element | null {
  const live = mode === 'live' && latest
  switch (footer.kind) {
    case 'analysing':
      return null
    case 'curating':
      return <p className="st-foot"><i className="dot run" />{T.footer.curating(footer.version)}</p>
    case 'review':
      return (
        <div className="st-foot st-askedfoot">
          <Icon name="spark" size={14} className="st-amber" />
          <span>{T.footer.review(footer.version)}</span>
        </div>
      )
    case 'interrupted':
      return <p className="st-foot st-warn">{T.footer.interrupted(footer.version)}</p>
    case 'deployed':
      return (
        <div className="st-foot">
          <Icon name="check" size={14} className="st-ok" />
          <span>{live ? T.footer.deployed(footer.version) : mode === 'live' ? T.footer.deployedPast(footer.version) : T.footer.deployedReplay(footer.version)}</span>
          {live && actions.onOpenTrial && <button type="button" className="st-btn" onClick={actions.onOpenTrial}><Icon name="flask" size={13} />{T.openTrial}</button>}
        </div>
      )
    case 'kept':
      return <p className="st-foot st-bad">{footer.reason === T.noCurationRecord ? footer.reason : T.curationFailed}. {T.footer.kept(footer.version)}</p>
    case 'asked':
      return (
        <div className="st-foot st-askedfoot">
          <Icon name="alert" size={14} className="st-amber" />
          <span>{T.footer.asked(T.stages[footer.stage] ?? footer.stage, footer.question)} {T.footer.kept(footer.version)}</span>
        </div>
      )
    case 'paused':
      return <p className="st-foot st-warn">{T.footer.paused(footer.stage ? T.stages[footer.stage] ?? footer.stage : null, footer.scope, footer.reason)} {T.footer.kept(footer.version)}</p>
    case 'failed':
      return <p className="st-foot st-bad">{T.footer.failed(footer.error)} {T.footer.kept(footer.version)}</p>
    case 'continue':
      return (
        <div className="st-foot">
          <span>{T.footer.noChange(footer.version)}</span>
          {live && actions.onOpenTrial && <button type="button" className="st-btn" onClick={actions.onOpenTrial}>{T.openTrial}</button>}
          {live && actions.onArchive && footer.version !== 'v0' && <button type="button" className="st-btn" onClick={actions.onArchive}>{T.archiveVersion(footer.version)}</button>}
        </div>
      )
    case 'supplement':
      return (
        <div className="st-foot">
          <span><b>{T.need}</b>: {footer.need} {T.footer.supplement}</span>
          {live && actions.onAttach && <button type="button" className="st-btn" onClick={actions.onAttach}><Icon name="clip" size={13} />{T.attachMaterial}</button>}
        </div>
      )
    case 'clarify':
      return <p className="st-foot"><span><b>{T.question}</b>: {footer.question} {T.footer.clarify}</span></p>
    case 'stop':
      return <p className="st-foot">{T.footer.stop}{footer.handoverUnused ? ` ${T.stopBeatsHandover}` : ''}</p>
    case 'last-round':
      return <p className="st-foot">{T.footer.lastRound}</p>
    case 'analysis-failed':
      return <p className="st-foot st-bad">{T.footer.analysisFailed}{footer.error ? ` ${footer.error}` : ''}</p>
  }
}

export function ProcessCard({ card, mode, latest, actions }: { card: ProcessEntry; mode: 'live' | 'replay'; latest: boolean; actions: CardActions }): JSX.Element {
  return (
    <section className="st-card st-process" id={`card-${card.key}`}>
      <header className="st-card-h">
        <span className="st-kicker">{card.onboarding ? T.onboardingLabel : T.roundLabel(card.round)}</span>
        <Crumbs card={card} />
        <span className="grow" />
        <button type="button" className="st-link" onClick={() => actions.onInspect(card.key)}><Icon name="eye" size={13} />{T.inspector}</button>
      </header>
      <Analysis card={card} actions={actions} />
      <Curation card={card} actions={actions} />
      <FooterRow footer={card.footer} mode={mode} latest={latest} actions={actions} />
    </section>
  )
}
