/* Small marks shared by the views: the strategy a change binds and how it
   treats the diagnosed mechanism, a diagnosis state, a requirement's id,
   strength, recurrence and whether it held, where a verdict's criterion comes
   from, a red line, and a fold whose body renders only once opened. */

import { useState } from 'react'

import { OWNS } from '../mechanism'

import type { Strategy } from '../mechanism'
import type { Item, Requirement, Treatment } from '../model'
import type { JSX, ReactNode } from 'react'

export function StrategyBadge({ strategy }: { strategy: Strategy | null }): JSX.Element | null {
  if (!strategy) return null
  return <span className={`cls ${strategy}`} title={OWNS[strategy]}>{strategy}</span>
}

const TREATMENT_HINT: Record<Treatment, string> = {
  modify: 'Modifies the diagnosed mechanism',
  replace: 'Replaces the diagnosed mechanism',
  add: 'Adds a mechanism beside the diagnosed one',
}

export function TreatmentBadge({ treatment }: { treatment: Treatment | null | undefined }): JSX.Element | null {
  if (!treatment) return null
  return <span className={`treat ${treatment}`} title={TREATMENT_HINT[treatment]}>{treatment}</span>
}

const STATE_HINT: Record<string, string> = {
  absent: 'No mechanism covers it',
  not_exposed: 'A mechanism exists but the model never sees it',
  not_triggered: 'It exists but its trigger did not fire',
  not_consumed: 'It fired but its result was not used',
  wrong_logic: 'It ran and decided wrongly',
  blocked: 'The host or a permission stopped it',
  model_ignored: 'The information was present and the model did not follow it',
  uncovered: 'The mechanism exists but does not reach this situation',
}

export function StateChip({ state }: { state: string | null | undefined }): JSX.Element {
  return <span className={`dstate ${state ?? 'none'}`} title={state ? STATE_HINT[state] ?? state : 'Not diagnosed'}>{state ? state.replace(/_/g, ' ') : 'not diagnosed'}</span>
}

export function HeldBadge({ held }: { held: boolean | null | undefined }): JSX.Element | null {
  if (held === undefined) return null
  if (held === null) return <span className="held open" title="Judged once the round after its revision is analysed">held: not yet judged</span>
  return <span className={`held ${held ? 'yes' : 'no'}`} title="Whether it held in the round after its revision">{held ? 'held next round' : 'did not hold'}</span>
}

export function RequirementBadges({ requirement }: { requirement: Requirement }): JSX.Element {
  return (
    <>
      {requirement.id ? <span className="rid">{requirement.id}</span> : null}
      {requirement.repeats ? <span className="recur" title={`Raised again: it repeats ${requirement.repeats}`}>repeats {requirement.repeats}</span> : null}
      <span className={`strength ${requirement.strength}`} title="How the owner or the materials state it">
        {requirement.strength === 'must_hold' ? 'must hold' : 'should'}
      </span>
      {requirement.recurrence ? (
        <span className="recur" title="Earlier rounds that already showed this behavior failing">
          recurred ×{requirement.recurrence}
        </span>
      ) : null}
    </>
  )
}

const BASIS: Record<string, [string, string]> = {
  check: ['check', "A party's own check"],
  case: ['case', 'A dataset case'],
  requirement: ['regression', 'An earlier requirement held as a regression check; its wording restates what the Curator already holds'],
  material: ['from material', 'Drawn from a handed-over material; its wording restates what the Curator already holds'],
}

export function BasisBadge({ basis }: { basis: Item['basis'] }): JSX.Element | null {
  if (!basis) return null
  const [label, hint] = BASIS[basis] ?? [basis, basis]
  return <span className={`basis ${basis}`} title={hint}>{label}</span>
}

export function RedLine(): JSX.Element {
  return <span className="redline" title="A red line: the owner never tolerates it missing">red line</span>
}

/* Long model text (a legacy understanding, a task statement) is shown cut to a
   few screens' worth until the reader asks for all of it. */
export function Clamp({ children, long }: { children: ReactNode; long: boolean }): JSX.Element {
  const [open, setOpen] = useState(false)
  if (!long) return <>{children}</>
  return (
    <div className={`clamp${open ? '' : ' closed'}`}>
      <div className="clamp-body">{children}</div>
      <button className="clamp-toggle" onClick={() => setOpen(!open)}>{open ? 'Show less' : 'Show all'}</button>
    </div>
  )
}

/* Records and generated code can be large; the body is built only when the
   reader opens the fold, and kept once built. */
export function Fold({
  summary, children, className = '', open = false,
}: { summary: ReactNode; children: () => ReactNode; className?: string; open?: boolean }): JSX.Element {
  const [shown, setShown] = useState(open)
  return (
    <details className={className} open={open} onToggle={(e) => { if ((e.currentTarget as HTMLDetailsElement).open) setShown(true) }}>
      <summary>{summary}</summary>
      {shown ? children() : null}
    </details>
  )
}
