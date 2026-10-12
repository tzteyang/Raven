/* One exam question across the versions that sat it, side by side: what was asked once, then each chosen version's
   replies with the verdicts its exam gave them, so a reader sees in seconds whether the later version answers better.
   `examTakes` gathers the takes from a thread: the held-out trial of each round that played the question, and the
   held-out score of that round on it. */

import { useState } from 'react'

import { replyText } from '../../trial'
import { T } from '../copy'
import { Markdown } from './bits'

import type { JSX } from 'react'
import type { Item } from '../../model'
import type { Thread, TrialView } from '../types'

export interface ExamTake {
  round: number
  trial: TrialView
  items: Item[]
}

/** The exam question a held-out trial played, or null for any other trial. */
export const examName = (trial: TrialView): string | null => /^\d+:holdout:(.+)$/.exec(trial.id)?.[1] ?? null

export function examTakes(thread: Thread, name: string): ExamTake[] {
  const takes: ExamTake[] = []
  for (const entry of thread.entries) {
    if (entry.kind !== 'trials' || !entry.holdout) continue
    for (const trial of entry.trials) if (trial.id === `${entry.round}:holdout:${name}`) takes.push({ round: entry.round, trial, items: [] })
  }
  for (const entry of thread.entries) {
    if (entry.kind !== 'score' || !entry.holdout) continue
    const take = takes.find((item) => item.round === entry.round)
    if (take) take.items.push(...entry.signal.items.filter((item) => item.session === name))
  }
  return takes.sort((a, b) => a.round - b.round)
}

function Take({ take, takes, pick }: { take: ExamTake; takes: ExamTake[]; pick: (index: number) => void }): JSX.Element {
  const failed = take.items.filter((item) => item.result === 'fail')
  return (
    <div className="st-compare-col">
      <label className="st-compare-pick">
        <select value={takes.indexOf(take)} aria-label={T.compareVersion} onChange={(event) => pick(Number(event.target.value))}>
          {takes.map((item, i) => <option key={item.round} value={i}>{item.trial.version}</option>)}
        </select>
        <span className={failed.length ? 'st-bad' : 'st-quiet'}>{take.items.length ? T.compareFailed(failed.length, take.items.length) : T.compareUnscored}</span>
      </label>
      {failed.length > 0 && (
        <ul className="st-compare-fails">
          {failed.map((item) => <li key={item.id}><b>{item.id.split(':')[0]}</b> {item.note.split('\n')[0]}</li>)}
        </ul>
      )}
      {take.trial.exchanges.map((exchange, i) => (
        <div key={i} className="st-compare-reply">
          {take.trial.exchanges.length > 1 && <p className="st-label">{T.trialTurns(i + 1)}</p>}
          <Markdown text={replyText(exchange.execution) || '—'} />
        </div>
      ))}
    </div>
  )
}

export function ExamCompare({ takes }: { takes: ExamTake[] }): JSX.Element {
  const [left, setLeft] = useState(0)
  const [right, setRight] = useState(Math.max(0, takes.length - 1))
  if (!takes.length) return <p className="st-quiet">{T.compareNone}</p>
  const asked = takes[0].trial.exchanges[0]?.user ?? ''
  return (
    <div className="st-compare">
      <div className="st-compare-ask">
        <p className="st-label">{T.compareAsk}</p>
        <Markdown text={asked} />
      </div>
      <div className="st-compare-cols">
        <Take take={takes[Math.min(left, takes.length - 1)]} takes={takes} pick={setLeft} />
        <Take take={takes[Math.min(right, takes.length - 1)]} takes={takes} pick={setRight} />
      </div>
    </div>
  )
}
