/* Rubric construction, evidence, learning and independent promotion in the run record. */

import { Fold } from './Badges'
import type { StandardCriterion, StandardRecord, StandardRevision, Promotion } from '../model'
import type { JSX } from 'react'

const OPS: Record<string, string> = { add: 'added', rewrite: 'rewritten', remove: 'removed' }

function treeRows(criteria: StandardCriterion[]): { criterion: StandardCriterion; depth: number }[] {
  const ids = new Set(criteria.map((criterion) => criterion.id))
  const children = new Map<string, StandardCriterion[]>()
  for (const criterion of criteria) {
    if (criterion.parent_id) children.set(criterion.parent_id, [...(children.get(criterion.parent_id) ?? []), criterion])
  }
  const roots = criteria.filter((criterion) => !criterion.parent_id || !ids.has(criterion.parent_id))
  const seen = new Set<string>()
  const rows: { criterion: StandardCriterion; depth: number }[] = []
  for (const root of [...roots, ...criteria]) {
    const stack = [{ criterion: root, depth: 0 }]
    while (stack.length) {
      const row = stack.pop()!
      if (seen.has(row.criterion.id)) continue
      seen.add(row.criterion.id)
      rows.push(row)
      stack.push(...(children.get(row.criterion.id) ?? []).slice().reverse().map((criterion) => ({ criterion, depth: row.depth + 1 })))
    }
  }
  return rows
}

function revisionSummary(revision: StandardRevision): string {
  const counts = Object.entries(OPS)
    .map(([op, word]) => [revision.changes.filter((change) => change.op === op).length, word] as const)
    .filter(([count]) => count > 0)
    .map(([count, word]) => `${count} ${word}`)
  const fresh = revision.new_norms.length ? ` · new: ${revision.new_norms.join(', ')}` : ''
  return `Revision ${revision.version}: ${counts.length ? counts.join(', ') : 'no change'}${fresh}`
}

/* The standard the automatic assessor held the rounds to, as written when the run ended, and how the rubric builder
   wrote its derived criteria: every numbered revision with its changes, their reasons and quoted passages, and the
   passages it found nothing checkable in. A revision is not tied to a round here: the rubric builder revises before each
   assessment that has norms to read, which is not every round of every run. */
export function StandardBlock({ standard }: { standard: StandardRecord }): JSX.Element {
  const derived = standard.criteria.filter((criterion) => criterion.source === 'derived')
  const revisions = (standard.revisions ?? []).map((revision) => ({
    ...revision,
    changes: revision.changes.map((change) => change.op === 'retire' ? { ...change, op: 'remove' } : change),
  }))
  return (
    <div className="say assessor standard-block">
      <span className="who">Evaluation rubric · latest recorded state</span>
      <div className="ai reply">
        <p className="sc-hd">
          <span className="src">rubric</span>
          <span>{standard.criteria.length} criteria</span>
          {derived.length ? <span className="dim">{derived.length} written by the rubric builder from {standard.derived_from.join(', ')}</span> : null}
          {revisions.length ? <span className="dim">{revisions.length} revision{revisions.length === 1 ? '' : 's'}</span> : null}
        </p>
        {standard.error ? <p className="runerr"><span className="k">standard.json</span>{standard.error}</p> : null}
        {standard.criteria.length ? (
          <Fold className="fold" summary={`Evaluation criteria (${standard.criteria.length})`}>
            {() => (
              <ul className="sc-fails">
                {treeRows(standard.criteria).map(({ criterion, depth }) => (
                  <li key={criterion.id} style={{ marginInlineStart: Math.min(depth, 4) * 12 }}>
                    <code>{criterion.id}</code> {criterion.text}
                    {criterion.parent_id ? <div className="dim">Refines: {criterion.parent_id}</div> : null}
                    {criterion.subject ? <div>Subject: {criterion.subject}</div> : null}
                    {criterion.situation ? <span className="dim"> · when {criterion.situation}</span> : null}
                    <span className="dim"> · {criterion.kind || criterion.strength} · {criterion.authority === 'external' ? 'protected external requirement' : criterion.authority === 'model' ? 'model generated' : 'authority not recorded'} · {criterion.provenance}</span>
                    {criterion.checks?.map((check, i) => <div key={i} className="dim">{check.role === 'decision' ? 'Whole criterion · ' : check.role === 'required' ? 'Necessary local check · ' : ''}{check.method === 'missing' ? 'Decision unavailable' : check.method === 'program' ? 'Program verification' : 'Model judgment'}{check.spec ? `: ${check.spec}` : ''}</div>)}
                    {criterion.evidence_requirements?.map((need, i) => <div key={`e${i}`}>Required evidence: {need.kind.replace(/_/g, ' ')}{need.reference ? ` · ${need.reference}` : ''}</div>)}
                    {criterion.derivation ? <p>Derivation: {criterion.derivation}</p> : null}
                    {criterion.quote ? <blockquote className="quote">{criterion.quote}</blockquote> : null}
                  </li>
                ))}
              </ul>
            )}
          </Fold>
        ) : null}
        {standard.construction?.length ? <Fold className="fold" summary={`Rubric construction (${standard.construction.length})`}>
          {() => <>
            {standard.construction?.map((run, i) => <div key={i}>
              <strong>{run.status.replace(/_/g, ' ')}</strong> · {run.calls ?? 0} calls · {run.added ?? 0} additions
              {run.steps?.map((step, j) => <p key={j}>{step.target || 'Task scope'} · {step.status}: {step.note}</p>)}
              {run.reason ? <p className="dim">{run.reason}</p> : null}
              {run.error ? <p className="runerr">{run.error}</p> : null}
            </div>)}
            {standard.pending?.map((work, i) => <p key={i}><strong>Pending</strong> · {work.target || 'Task scope'}: {work.reason}</p>)}
          </>}
        </Fold> : null}
        {revisions.map((revision) => (
          <Fold key={revision.version} className="fold" summary={revisionSummary(revision)}>
            {() => (
              <ul className="sc-fails">
                {revision.changes.map((change, i) => (
                  <li key={i}>
                    <code>{change.id}</code> <span className="k">{OPS[change.op] ?? change.op}</span> <span className="dim">({change.reason})</span> {change.explanation}
                    {change.before ? <div className="dim">before: {change.before}</div> : null}
                    {change.parent_id ? <div className="dim">Parent: {change.parent_id}</div> : null}
                    {change.text ? <div>now: {change.text}</div> : null}
                    {change.quote ? <blockquote className="quote">{change.material}: {change.quote}</blockquote> : null}
                  </li>
                ))}
                {revision.unchecked.map((item, i) => (
                  <li key={`u${i}`} className="dim">not checkable: {item.material}{item.section ? ` ${item.section}` : ''}, {item.reason}</li>
                ))}
              </ul>
            )}
          </Fold>
        ))}
        {standard.assessments?.map((assessment) => (
          <Fold key={assessment.id} className="fold" summary={`Assessment ${assessment.version} · evidence and review`}>
            {() => <>
              {assessment.repair_status ? <p>Rubric repair · {assessment.repair_status}</p> : null}
              {Object.entries(assessment.repair_validation ?? {}).map(([id, validation]) => <p key={id}>
                {id || 'Task scope'} · {validation.kind === 'equivalent_duplicate_removal' ? 'Equivalent condition retained after duplicate removal' : validation.accepted ? 'Repair independently validated' : 'Repair remains unvalidated'}{validation.error ? `: ${validation.error}` : ''}
              </p>)}
              {assessment.evidence_restored?.map((id) => <p key={id}>Required evidence now available · {id}</p>)}
              {assessment.repair_rejected ? <p className="runerr">{assessment.repair_rejected}</p> : null}
              <ul className="sc-fails">{assessment.checks.map((check, i) => <li key={i}>
                <code>{check.criterion}</code> · {check.method} · <strong>{check.result}</strong>
                {check.actual ? <blockquote className="quote">{check.actual}</blockquote> : null}
                {check.note ? <p>{check.note}</p> : null}
              </li>)}</ul>
              {assessment.review?.issues.map((issue, i) => <p key={i}><strong>Evaluation correction</strong> · {issue.criterion || 'coverage'}: {issue.evidence} {issue.correction}</p>)}
              {Object.values(assessment.unresolved ?? {}).map((reason, i) => <p key={i}>Unresolved: {reason}</p>)}
              {[assessment.review_error, assessment.repair_error, assessment.learning_error].filter(Boolean).map((error, i) => <p className="runerr" key={i}>{error}</p>)}
            </>}
          </Fold>
        ))}
        {standard.guidance?.entries.length ? <Fold className="fold" summary={`Construction guidance (${standard.guidance.entries.length})`}>
          {() => <>
            <p>Only independently validated guidance is used in later rubric construction.</p>
            <ul className="sc-fails">{standard.guidance?.entries.map((entry) => <li key={entry.id}>
              <strong>{entry.kind} · {entry.state}</strong> · {entry.scope === '*' ? 'across tasks' : 'this task'}
              <p>{entry.text}</p>
              <span className="dim">{entry.episodes.length} source episode{entry.episodes.length === 1 ? '' : 's'}</span>
              {standard.guidance?.history.filter((row) => row.candidate === entry.id || row.rollback === entry.id).map((row, i) => <div key={i}>
                {row.rollback ? 'Rolled back' : row.accepted ? 'Adopted after independent comparison' : 'Kept as a candidate'}
                {row.error ? `: ${row.error}` : ''}
                {row.comparisons?.map((comparison) => <p className="dim" key={comparison.case}>
                  Independent result: {comparison.oracle.result}; before: {String(comparison.before ?? 'unknown')}; after: {String(comparison.after ?? 'unknown')}. {comparison.oracle.actual}
                </p>)}
              </div>)}
            </li>)}</ul>
          </>}
        </Fold> : null}
      </div>
    </div>
  )
}

export function PromotionStatus({ promotion, stable }: { promotion?: Promotion; stable?: Promotion }): JSX.Element | null {
  if (!promotion) return null
  return <div className="say assessor">
    <span className="who">Harness verification · {promotion.status}</span>
    <p>{promotion.reason}</p>
    {promotion.witnesses?.map((witness, i) => <p key={i} className="dim">{witness.policy.kind}: {witness.error || (witness.satisfied === true ? 'passed' : witness.satisfied === false ? 'failed' : 'unresolved')}</p>)}
    {stable?.revision && stable.revision !== promotion.revision ? <p className="dim">A previously verified revision is retained.</p> : null}
  </div>
}
