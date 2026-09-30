import { trialsOf } from '../derive'
import { STRATEGIES, strategyOf } from '../mechanism'
import { StrategyBadge } from './Badges'

import type { Revision } from '../derive'
import type { JSX } from 'react'

/* The employee's versions left to right: v0 when a round tried the baseline,
   then every revision, a failed one marked as keeping the version before it.
   The connector says which round's remark led to the revision. */
export function RevisionRail({
  revisions, versions, shown, onOpen,
}: { revisions: Revision[]; versions: string[]; shown: string | null; onOpen: (revision: Revision | null) => void }): JSX.Element {
  const active = [...revisions].reverse().find((rev) => rev.deployed)?.label ?? 'v0'
  const tried = (label: string) => {
    const rounds = trialsOf(label, versions)
    return rounds.length ? `tried in round ${rounds.join(', ')}` : 'not yet tried'
  }
  return (
    <nav className="rail" aria-label="Employee versions">
      <span className="lbl">Employee versions</span>
      <div className="rail-in">
        {versions.includes('v0') || revisions.length === 0 ? (
          <span className="rail-step">
            <button className={`rn${shown === 'v0' ? ' sel' : ''}${active === 'v0' ? ' live' : ''}`} onClick={() => onOpen(null)}>
              <span className="row"><span className="dot" /><span className="v">v0</span></span>
              <span className="d">baseline · {tried('v0')}</span>
            </button>
          </span>
        ) : null}
        {revisions.map((rev, i) => {
          const changes = [
            ...(rev.curation.generated?.candidate.plan.changes ?? []),
            ...Object.values(rev.curation.child_changes ?? {}).flatMap((child) => child.candidate.plan.changes),
          ]
          const strategies = STRATEGIES.filter((name) => changes.some((change) => strategyOf(change.target) === name))
          return (
            <span key={rev.key} className="rail-step">
              {i > 0 || versions.includes('v0') ? <span className="re"><span>{rev.round ? `after round ${rev.round}` : 'onboarding'}</span></span> : null}
              <button
                className={`rn${rev.label === shown && rev.deployed ? ' sel' : ''}${rev.deployed && rev.label === active ? ' live' : ''}${rev.deployed ? '' : ' kept'}`}
                onClick={() => onOpen(rev)}
                title={rev.curation.generated?.candidate.plan.understanding ?? rev.curation.error ?? ''}
              >
                <span className="row">
                  <span className="dot" />
                  <span className="v">{rev.deployed ? rev.label : `failed · stays ${rev.label}`}</span>
                  {strategies.map((name) => <StrategyBadge key={name} strategy={name} />)}
                </span>
                <span className="d">
                  {rev.deployed ? `${changes.length} change${changes.length === 1 ? '' : 's'} · ${tried(rev.label)}` : rev.round ? `revision after round ${rev.round}` : 'onboarding revision'}
                </span>
              </button>
            </span>
          )
        })}
      </div>
    </nav>
  )
}
