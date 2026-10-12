/* The acceptance checks the AI proposes for what the person has not settled yet: each a question with two answers,
   how a reply would read and the rule that answer stands for. The person picks one or writes their own; the rules
   settled so far are listed, since every automatic assessment from then on holds the trials to them. */

import { useState } from 'react'

import { T } from '../copy'
import { Icon } from './bits'

import type { JSX } from 'react'
import type { CollectorQuestion, LiveProposals } from '../api'

export type Choice = { option: number } | { rule: string }

export function Proposals({ proposals, adopted, onAdopt }: {
  proposals: LiveProposals | null
  adopted: string[]
  /** Settle a proposal; absent while the session cannot take a step. */
  onAdopt?: (index: number, choice: Choice) => void
}): JSX.Element | null {
  const [own, setOwn] = useState<Record<number, string>>({})
  if (!proposals && !adopted.length) return null
  const items = proposals?.items ?? []
  return (
    <div className="st-proposals">
      {proposals?.busy && <p className="st-quiet"><Icon name="spark" size={13} />{T.proposeBusy}</p>}
      {proposals?.error && <p className="st-bad">{T.proposeFailed(proposals.error)}</p>}
      {proposals?.items && !items.length && <p className="st-quiet">{T.proposeNone}</p>}
      {items.map((item, i) => (
        <div key={i} className="st-proposal">
          <p className="st-proposal-q"><b>{item.topic}</b><span>{item.why}</span></p>
          {item.chosen ? (
            <p className="st-proposal-done"><Icon name="check" size={13} />{T.proposeChosen(item.chosen.rule)}</p>
          ) : (
            <>
              <div className="st-options">
                {item.options.map((option, k) => (
                  <div key={k} className="st-option">
                    <blockquote>{option.example}</blockquote>
                    <p>{option.rule}</p>
                    <button type="button" className="st-btn" disabled={!onAdopt} onClick={() => onAdopt?.(i, { option: k })}>{T.proposePick}</button>
                  </div>
                ))}
              </div>
              <div className="st-ownrule">
                <input value={own[i] ?? ''} placeholder={T.proposeOwn} onChange={(event) => setOwn({ ...own, [i]: event.target.value })} />
                <button
                  type="button"
                  className="st-btn"
                  disabled={!onAdopt || !(own[i] ?? '').trim()}
                  onClick={() => onAdopt?.(i, { rule: (own[i] ?? '').trim() })}
                >
                  {T.proposeUseOwn}
                </button>
              </div>
            </>
          )}
        </div>
      ))}
      {adopted.length > 0 && (
        <div className="st-adopted">
          <p className="st-label">{T.adoptedTitle}</p>
          <ul>{adopted.map((rule) => <li key={rule}>{rule}</li>)}</ul>
        </div>
      )}
    </div>
  )
}

/** The questions the information preparation waits on before the onboarding, all at once: each answered, in any
    order, or skipped to keep the assumption the AI stated. */
export function CollectorAsk({ questions, onAnswer }: {
  questions: CollectorQuestion[]
  /** Absent while the session cannot take a step. */
  onAnswer?: (id: string, answer: { text: string } | { skip: true }) => void
}): JSX.Element {
  return (
    <div className="st-proposals st-collector">
      <p className="st-proposal-q"><b>{T.collectorTitle}</b></p>
      {questions.map((question) => (
        <Asked key={question.id} question={question} onAnswer={onAnswer && ((answer) => onAnswer(question.id, answer))} />
      ))}
    </div>
  )
}

function Asked({ question, onAnswer }: {
  question: CollectorQuestion
  onAnswer?: (answer: { text: string } | { skip: true }) => void
}): JSX.Element {
  const [text, setText] = useState('')
  return (
    <div className="st-proposal">
      <p className="st-proposal-q"><span className="st-collector-q">{question.question}</span><span>{question.reason}</span></p>
      {question.proposal && <p className="st-quiet">{T.collectorProposal(question.proposal)}</p>}
      <div className="st-ownrule">
        <input value={text} placeholder={T.collectorPlaceholder} aria-label={question.question} onChange={(event) => setText(event.target.value)} />
        <button type="button" className="st-btn" disabled={!onAnswer || !text.trim()} onClick={() => onAnswer?.({ text: text.trim() })}>{T.collectorAnswer}</button>
        <button type="button" className="st-btn" disabled={!onAnswer} onClick={() => onAnswer?.({ skip: true })}>{T.collectorSkip}</button>
      </div>
      {question.assumption && <p className="st-quiet">{T.collectorAssumption(question.assumption)}</p>}
    </div>
  )
}
