/* The conversation column: the session head, each change request as the
   reader's own bubble (the assessor's, in a replay) with the materials it
   handed over, the automatic standard assessor's scorecard, the process card
   that answers a round, the trials of each version (held-out and in-progress
   ones marked as such), and the quiet rows that record a choice or the end of
   a run. */

import { T } from '../copy'
import { speaker } from '../replay'
import { Fold, HandoverChip, Icon, Markdown } from './bits'
import { ProcessCard } from './ProcessCard'
import { TrialsCard } from './Trials'

import type { JSX } from 'react'
import type { Item } from '../../model'
import type { CardActions } from './ProcessCard'
import type { Entry, HeadEntry, RequestEntry, ScoreEntry, Thread } from '../types'

function Head({ entry }: { entry: HeadEntry }): JSX.Element {
  const models = Object.entries(entry.models)
  return (
    <section className="st-card st-head" id="card-head">
      <header className="st-card-h"><Icon name="chat" size={13} /><span className="st-kicker">{T.headTask}</span></header>
      <Markdown text={entry.task} className="st-task" />
      <dl className="st-kv">
        <dt>{T.headBaseline}</dt><dd>{entry.baseline}</dd>
        {models.length > 0 && (
          <>
            <dt>{T.headModels}</dt>
            <dd className="st-models">{models.map(([role, model]) => <code key={role}>{role} · {model}</code>)}</dd>
          </>
        )}
      </dl>
      {entry.note && <p className="st-note-in">{entry.note}</p>}
    </section>
  )
}

function Request({ entry, origins }: { entry: RequestEntry; origins: Thread['origins'] }): JSX.Element {
  return (
    <div className="st-me" id={`req-${entry.key}`}>
      <span className="st-who">
        {entry.speaker} · {entry.onboarding ? T.onboardingTag : T.requestTag}
      </span>
      {entry.text && <div className="msg me">{entry.text}</div>}
      {entry.attachments.length > 0 && (
        <div className="st-atts">
          {entry.attachments.map((material) => <HandoverChip key={material.name} material={material} origin={origins?.[material.name]} />)}
        </div>
      )}
    </div>
  )
}

const percent = (rate: number | undefined): string => (typeof rate === 'number' ? `${Math.round(rate * 100)}%` : '—')
const outcome = (result: Item['result']): string => (typeof result === 'number' ? 'score' : result)

/* The standard assessor has no voice: its signal is one verdict per criterion,
   joined here with the criterion's source and strength when standard.json has
   them. A held-out signal, from any assessor, is marked as never read by the
   Analyst or the Curator. */
function Score({ entry }: { entry: ScoreEntry }): JSX.Element {
  const { signal } = entry
  const criteria = new Map(entry.criteria.map((criterion) => [criterion.id, criterion]))
  const items = signal.items ?? []
  const pass = items.filter((item) => item.result === 'pass').length
  const fail = items.filter((item) => item.result === 'fail').length
  const who = signal.source === 'standard' ? T.scoreTitle : speaker(signal.source).name
  const text = signal.text?.trim() ?? ''
  return (
    <section className="st-card st-score" data-holdout={entry.holdout || undefined} id={`card-${entry.key}`}>
      <header className="st-card-h">
        <Icon name={entry.holdout ? 'shield' : 'check'} size={13} />
        <span className="st-kicker">{entry.holdout ? `${T.scoreHeldOut} · ${who}` : who}</span>
        <span className="grow" />
        <span className="st-sat" data-sat={String(signal.satisfied)}>{T.scoreSatisfied[String(signal.satisfied)]}</span>
      </header>
      <p className="st-quiet">{entry.holdout ? T.heldOutNote : T.scoreNote}</p>
      {text && (
        <Fold summary={<><b>{T.scoreRemark}</b><span className="st-peek">{text.split('\n').find((line) => line.trim())?.replace(/[*#]/g, '').slice(0, 60)}</span></>}>
          <Markdown text={text} />
        </Fold>
      )}
      {items.length > 0 && (
        <>
          <p className="st-scoreline">
            <span><span className="k">{T.scoreMust}</span>{percent(signal.metrics?.must_hold_pass_rate)}</span>
            <span><span className="k">{T.scoreShould}</span>{percent(signal.metrics?.should_pass_rate)}</span>
            <span className="st-meta">{T.scoreCounts(pass, fail, items.length)}</span>
          </p>
          <div className="st-scorerows">
            {items.map((item) => {
              const criterion = criteria.get(item.id)
              return (
                <div key={item.id} className="st-scorerow" data-result={outcome(item.result)}>
                  <span className="st-rid">{item.id}</span>
                  <span className="st-verdict" data-result={outcome(item.result)}>{typeof item.result === 'number' ? item.result.toFixed(2) : T.verdicts[item.result] ?? item.result}</span>
                  <div className="st-scorebody">
                    <p className="b">{item.expected || criterion?.text}</p>
                    {(item.actual || item.note) && <p className="m">{[item.actual, item.note].filter(Boolean).join(' · ')}</p>}
                    <p className="m">
                      {criterion && <span className="st-chip src" title={T.scoreSourceHint[criterion.source] ?? criterion.source}>{T.scoreSources[criterion.source] ?? criterion.source}</span>}
                      {!criterion && item.basis && <span className="st-chip src" title={T.basisHint[item.basis] ?? item.basis}>{T.basis[item.basis] ?? item.basis}</span>}
                      {criterion && <span className={`st-chip ${criterion.strength === 'must_hold' ? 'must' : 'should'}`}>{T.strength[criterion.strength] ?? criterion.strength}</span>}
                      {criterion?.provenance && <code title={criterion.provenance}>{criterion.provenance}</code>}
                      {item.session && <code>{item.session}</code>}
                    </p>
                  </div>
                </div>
              )
            })}
          </div>
        </>
      )}
    </section>
  )
}

export interface ThreadActions extends CardActions {
  activeTrial: string | null
  onTrial: (id: string) => void
  onNewTrial?: () => void
}

export function ThreadView({ thread, actions }: { thread: Thread; actions: ThreadActions }): JSX.Element {
  const live = thread.mode === 'live'
  const last = [...thread.entries].reverse().find((entry) => entry.kind === 'process')?.key
  const render = (entry: Entry): JSX.Element => {
    switch (entry.kind) {
      case 'head':
        return <Head key={entry.key} entry={entry} />
      case 'request':
        return <Request key={entry.key} entry={entry} origins={thread.origins} />
      case 'score':
        return <Score key={entry.key} entry={entry} />
      case 'process':
        return <ProcessCard key={entry.key} card={entry} mode={thread.mode} latest={entry.key === last && !thread.archived} actions={actions} />
      case 'trials':
        return (
          <TrialsCard
            key={entry.key}
            entry={entry}
            live={live && !thread.archived}
            current={thread.current}
            activeTrial={actions.activeTrial}
            onOpen={actions.onTrial}
            onNew={actions.onNewTrial}
          />
        )
      case 'note':
        return <p key={entry.key} className="st-note" data-tone={entry.tone}><span>{entry.text}</span></p>
    }
  }
  return <>{thread.entries.map(render)}</>
}
