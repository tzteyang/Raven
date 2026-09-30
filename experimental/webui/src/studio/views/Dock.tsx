/* What sits at the foot of the conversation, on ui-web's dock: the pill that
   opens the trial list, the bar offering a live session's next steps, and the
   composer that sends the person's words -- or, for a recorded run or a
   session that can take no more steps, a bar saying why it is read-only. */

import { useEffect, useRef, useState } from 'react'

import { T } from '../copy'
import { HandoverChip, Icon } from './bits'

import type { JSX } from 'react'
import type { LiveMaterial } from '../api'

export function TrialPill({ running, total, onToggle }: { running: number; total: number; onToggle: () => void }): JSX.Element | null {
  if (!total) return null
  return (
    <div className="tkruns">
      <button type="button" className="tkrunhint" data-trial-toggle onClick={onToggle}>
        {running > 0 ? <span className="tkrundot" /> : <Icon name="flask" size={12} />}
        <span>{running > 0 ? T.trialsRunning(running) : T.trialsAll(total)}</span>
      </button>
    </div>
  )
}

export interface StepAction {
  label: string
  icon?: string
  primary?: boolean
  disabled?: boolean
  title?: string
  onClick: () => void
}

/** One of a live session's decision points: what stands, and the steps the person may take from there. */
export function StepBar({ icon, tone, text, actions }: { icon: string; tone?: 'ok' | 'amber'; text: string; actions: StepAction[] }): JSX.Element {
  return (
    <div className="st-dockbar" role="group">
      <Icon name={icon} size={15} className={tone === 'ok' ? 'st-ok' : 'st-amber'} />
      <span className="grow">{text}</span>
      {actions.map((action) => (
        <button key={action.label} type="button" className={action.primary ? 'st-btn primary' : 'st-btn'} disabled={action.disabled} title={action.title} onClick={action.onClick}>
          {action.icon && <Icon name={action.icon} size={13} />}
          {action.label}
        </button>
      ))}
    </div>
  )
}

export function ReplayBar({ text, archived }: { text: string; archived: boolean }): JSX.Element {
  return (
    <div className="dock-in st-replaybar">
      <Icon name={archived ? 'archive' : 'eye'} size={15} />
      <span className="grow">{text}</span>
    </div>
  )
}

export interface ComposerProps {
  placeholder: string
  disabled: boolean
  /** The materials the person may hand over. */
  materials: LiveMaterial[]
  curator: string
  /** What the message is to the loop: the onboarding, or a change request. */
  tag: string
  pickOpen: boolean
  onPick: (open: boolean) => void
  onSend: (text: string, attachments: LiveMaterial[]) => void
  hint?: string
}

export function Composer({ placeholder, disabled, materials, curator, tag, pickOpen, onPick, onSend, hint }: ComposerProps): JSX.Element {
  const [text, setText] = useState('')
  const [attached, setAttached] = useState<LiveMaterial[]>([])
  const area = useRef<HTMLTextAreaElement>(null)
  useEffect(() => {
    const node = area.current
    if (!node) return
    node.style.height = 'auto'
    node.style.height = `${Math.min(200, Math.max(46, node.scrollHeight))}px`
  }, [text])
  const ready = !disabled && (text.trim().length > 0 || attached.length > 0)
  const send = () => {
    if (!ready) return
    onSend(text.trim(), attached)
    setText('')
    setAttached([])
  }
  return (
    <>
      <div className="dock-in" data-disabled={disabled}>
        {attached.length > 0 && (
          <div className="st-atts">
            {attached.map((material) => (
              <HandoverChip key={material.name} material={material} origin={material.origin}>
                <button type="button" aria-label={T.close} onClick={() => setAttached(attached.filter((item) => item.name !== material.name))}><Icon name="x" size={11} /></button>
              </HandoverChip>
            ))}
          </div>
        )}
        <div className="field">
          <textarea
            ref={area}
            rows={1}
            value={text}
            disabled={disabled}
            placeholder={placeholder}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault()
                send()
              }
            }}
          />
        </div>
        <div className="under">
          <button type="button" className="tool-btn" aria-label={T.attach} disabled={disabled || !materials.length} onClick={() => onPick(!pickOpen)}><Icon name="clip" size={16} /></button>
          <span className="chip st-reqchip"><Icon name="spark" size={12} />{tag}</span>
          <span className="grow" />
          <span className="chip" title={T.curatorModel}>{T.curatorModel} · {curator}</span>
          <button type="button" className="go" disabled={!ready} onClick={send} aria-label={T.send}><Icon name="up" size={15} /></button>
        </div>
        {pickOpen && !disabled && (
          <div className="st-pick" role="listbox" aria-label={T.pickMaterial}>
            <p className="wsgrp">{T.pickMaterial}</p>
            {materials.map((material) => {
              const on = attached.some((item) => item.name === material.name)
              const origin = material.origin && material.origin.origin !== 'given' ? T.originMark(material.origin.origin, material.origin.confirmed) : ''
              return (
                <button
                  type="button"
                  key={material.name}
                  role="option"
                  aria-selected={on}
                  className="st-pickrow"
                  onClick={() => setAttached(on ? attached.filter((item) => item.name !== material.name) : [...attached, material])}
                >
                  <Icon name={on ? 'check' : 'file'} size={13} />
                  <span>{material.name}</span>
                  <small>{[T.kinds[material.kind] ?? material.kind, origin, T.materialFiles(material.files.length), ...material.files.slice(0, 2)].filter(Boolean).join(' · ')}</small>
                </button>
              )
            })}
          </div>
        )}
      </div>
      {hint && <p className="st-hint">{hint}</p>}
    </>
  )
}
