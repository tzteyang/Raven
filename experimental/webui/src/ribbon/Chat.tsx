/* The run told as a conversation under the route. Each version opens with a
   divider, the way a chat marks a new day; then come the trials played on it,
   what the owner and the reviewers said, the Analyst's decision and the
   Curator's revision. The owner writes on the right, as the person in a chat
   does; every stage answers on the left as one line beside its icon, and opens
   into a card in place. Opening a message chooses its mark on the route, and
   choosing a mark on the route opens its message. The stage chosen is what the
   right-hand panel introduces with its Raven. */

import { useEffect, useRef, useState } from 'react'

import { Markdown } from '../studio/views/bits'
import { CAST, RoleIcon } from './cast'
import { flagKey, foldKey, legKey, trialKey, waistKey } from './layout'
import { active } from './route'

import type { JSX, ReactNode } from 'react'
import type { Role } from './cast'
import type { Tab } from './layout'
import type { Leg, Mark, Route } from './route'

export interface Message {
  key: string
  /** The route mark this message stands for. */
  mark: string
  leg: number
  role: Role
  summary: string
  live: boolean
  body: (onSelect: (key: string) => void) => ReactNode
}

const DECISIONS: Record<string, string> = { curate: '改造', continue: '继续', stop: '停止', supplement: '补充材料', clarify: '澄清' }
const STAGES: [string, string][] = [
  ['diagnose', '归因'],
  ['select', '选面'],
  ['design', '设计'],
  ['implement', '实现'],
  ['validate', '校验'],
  ['repair', '修复'],
  ['install', '安装'],
]
const MARKS: Record<Mark, string> = { add: '增', modify: '改', move: '换面', retire: '撤' }

/* The thread names a reviewer by its whole description; the page needs only which role it is. */
export function roleOf(speaker: string): Role {
  if (/own work|self|自评/i.test(speaker)) return 'self'
  if (/standard|标准/i.test(speaker)) return 'standard'
  return 'owner'
}

function line(text: string, size = 46): string {
  const flat = text.replace(/^\[session-[^\]]*\]\s*own verdict:\s*/i, '').replace(/\s+/g, ' ').trim()
  return flat.length > size ? `${flat.slice(0, size)}…` : flat
}

function curationSummary(leg: Leg, next: Leg | undefined): string {
  if (leg.end === 'curating') return '正在改造…'
  if (leg.end === 'failed') return '这次改造没有装上'
  if (leg.end === 'knot') return '改造完成，代码未变'
  if (leg.end !== 'waist' || !next) return ''
  const counts: Partial<Record<Mark, number>> = {}
  for (const mark of Object.values(next.marks)) counts[mark] = (counts[mark] ?? 0) + 1
  const parts = (Object.keys(MARKS) as Mark[]).filter((mark) => counts[mark]).map((mark) => `${MARKS[mark]} ${counts[mark]}`)
  return `改造为 ${next.version}${parts.length ? ` · 条目${parts.join(' ')}` : ''}`
}

function Stages({ leg }: { leg: Leg }): JSX.Element | null {
  const root = leg.process?.curation?.scopes.find((scope) => scope.root)
  if (!root) return null
  const shown = STAGES.filter(([id]) => root.stages.some((stage) => stage.id === id && stage.state !== 'skipped'))
  const done = root.stages.filter((stage) => stage.state === 'done').length
  return (
    <div className="rb-todo">
      <div className="rb-todo-h">改造步骤 <span>{done} / {shown.length}</span></div>
      <ul>
        {shown.map(([id, label]) => {
          const stage = root.stages.find((item) => item.id === id)!
          return (
            <li key={id} data-state={stage.state}>
              <i className={`rb-tick${stage.state === 'current' ? ' rb-live' : ''}`} />
              <span>{label}</span>
              {stage.calls > 0 && <s>{stage.calls} 次调用</s>}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export function messagesOf(route: Route): Message[] {
  const out: Message[] = []
  route.legs.forEach((leg, i) => {
    const next = route.legs[i + 1]
    const count = leg.commitments ? active(leg.commitments).length : null
    out.push({
      key: `div-${i}`,
      mark: legKey(i),
      leg: i,
      role: 'version',
      summary: leg.opening ? `${leg.version} · 开场` : `${leg.version}${count !== null ? ` · ${count} 条条目` : ''}`,
      live: false,
      body: () => null,
    })
    if (leg.trials.length) {
      out.push({
        key: `trials-${i}`,
        mark: foldKey(i),
        leg: i,
        role: 'trial',
        summary: `在 ${leg.version} 上试用 ${leg.trials.length} 场${leg.playing ? '，进行中' : ''}`,
        live: leg.playing,
        body: (onSelect) => (
          <ul className="rb-trial-list">
            {leg.trials.map((trial) => (
              <li key={trial.id} onClick={(event) => { event.stopPropagation(); onSelect(trialKey(trial.id)) }}>
                <i className={`rb-dot${trial.status === 'running' ? ' rb-live' : ''}`} />
                <b>{trial.title}</b>
                <span>{line(trial.exchanges[0]?.user ?? '', 30)}</span>
                <s>{trial.exchanges.length} 轮</s>
              </li>
            ))}
          </ul>
        ),
      })
    }
    for (const request of leg.requests) {
      out.push({
        key: `req-${request.key}`,
        mark: `heard-${i}-${request.key}`,
        leg: i,
        role: roleOf(request.speaker),
        summary: line(request.text, 90),
        live: false,
        body: () => (
          <>
            <Markdown text={request.text} />
            {request.attachments.length > 0 && (
              <div className="rb-serves">
                {request.attachments.map((item) => <span key={item.name} className="rb-chip">{item.name}</span>)}
              </div>
            )}
          </>
        ),
      })
    }
    const feedback = leg.process?.feedback
    if (feedback) {
      out.push({
        key: `ana-${i}`,
        mark: flagKey(i),
        leg: i,
        role: 'analyst',
        summary: `判断：${DECISIONS[feedback.decision] ?? feedback.decision}${feedback.requirements.length ? ` · ${feedback.requirements.length} 条需求` : ''}`,
        live: false,
        body: () => (
          <>
            <p className="rb-said">{feedback.reason}</p>
            <ul className="rb-reqs">
              {feedback.requirements.map((requirement, k) => (
                <li key={requirement.id ?? k}>
                  <code>{requirement.id}</code>
                  <span className={`rb-strength rb-${requirement.strength}`}>{requirement.strength === 'must_hold' ? '必须' : '应当'}</span>
                  <span>{line(requirement.behavior, 60)}</span>
                </li>
              ))}
            </ul>
          </>
        ),
      })
    }
    const done = curationSummary(leg, next)
    if (done) {
      out.push({
        key: `cur-${i}`,
        mark: waistKey(i),
        leg: i,
        role: 'curator',
        summary: done,
        live: leg.end === 'curating',
        body: () => (
          <>
            <Stages leg={leg} />
            {next && Object.keys(next.marks).length > 0 && (
              <div className="rb-ops">
                {Object.entries(next.marks).map(([id, mark]) => (
                  <span key={id} className={`rb-mark rb-mark-${mark}`}>{id} {MARKS[mark]}</span>
                ))}
              </div>
            )}
          </>
        ),
      })
    }
  })
  return out
}

export interface Stage {
  role: Role
  line: string
}

const TAB_ROLE: Record<Tab, Role> = { harness: 'version', process: 'curator', trials: 'trial', review: 'analyst' }

/** The stage the right-hand panel introduces: the chosen message's when a mark is chosen and its tab is shown,
    otherwise the stage of the tab on show. */
export function stageOf(route: Route, messages: Message[], selected: string | null, tab: Tab, index: number): Stage {
  const leg = route.legs[Math.min(index, route.legs.length - 1)]
  if (selected) {
    const trial = selected.startsWith('trial-') && !selected.startsWith('trial-fold-')
      ? leg.trials.find((item) => trialKey(item.id) === selected)
      : undefined
    if (trial) return { role: 'trial', line: `${trial.title} · ${trial.exchanges.length} 轮` }
    const hit = messages.find((message) => message.mark === selected)
    if (hit && hit.role !== 'version') return { role: hit.role, line: hit.summary }
    if (hit) return stageOf(route, messages, null, 'harness', index)
  }
  const role = TAB_ROLE[tab]
  if (role === 'version') {
    const counts: Partial<Record<Mark, number>> = {}
    for (const mark of Object.values(leg.marks)) counts[mark] = (counts[mark] ?? 0) + 1
    const parts = (Object.keys(MARKS) as Mark[]).filter((mark) => counts[mark]).map((mark) => `${MARKS[mark]} ${counts[mark]}`)
    const live = leg.commitments ? active(leg.commitments).length : 0
    return { role, line: `${live} 条现行条目${parts.length ? `，较上一版${parts.join(' ')}` : ''}` }
  }
  const own = messages.find((message) => message.leg === leg.index && message.role === role)
  if (own) return { role, line: own.summary }
  if (role === 'curator') return { role, line: '这一段没有改造' }
  if (role === 'trial') return { role, line: `${leg.version} 还没有试用` }
  return { role, line: '这一段还没有判断' }
}

export function Chat({ messages, route, focus, selected, onSelect }: {
  messages: Message[]
  route: Route
  focus: number | null
  selected: string | null
  onSelect: (key: string | null) => void
}): JSX.Element {
  const [open, setOpen] = useState<Set<string>>(new Set())
  const nodes = useRef<Record<string, HTMLLIElement | null>>({})
  useEffect(() => {
    if (!selected) return
    const hit = messages.find((message) => message.mark === selected) ??
      (selected.startsWith('trial-') && !selected.startsWith('trial-fold-')
        ? messages.find((message) => message.role === 'trial' && route.legs[message.leg].trials.some((trial) => trialKey(trial.id) === selected))
        : undefined)
    if (!hit) return
    setOpen((prev) => (prev.has(hit.key) ? prev : new Set(prev).add(hit.key)))
    nodes.current[hit.key]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [selected, messages, route])
  const toggle = (message: Message) => {
    const opening = !open.has(message.key)
    setOpen((prev) => {
      const next = new Set(prev)
      if (opening) next.add(message.key)
      else next.delete(message.key)
      return next
    })
    if (opening) onSelect(message.mark)
  }
  return (
    <ol className="rb-chat">
      {messages.map((message) => {
        const dim = focus !== null && focus !== message.leg
        const chosen = selected === message.mark
        const ref = (node: HTMLLIElement | null) => { nodes.current[message.key] = node }
        if (message.role === 'version') {
          return (
            <li key={message.key} ref={ref} className={`rb-divider${dim ? ' rb-dim' : ''}${chosen ? ' on' : ''}`} onClick={() => onSelect(message.mark)}>
              <span><RoleIcon role="version" size={12} />{message.summary}</span>
            </li>
          )
        }
        const unfolded = open.has(message.key)
        const state = `${unfolded ? ' rb-unfolded' : ''}${dim ? ' rb-dim' : ''}${chosen ? ' on' : ''}`
        if (message.role === 'owner') {
          return (
            <li key={message.key} ref={ref} className={`rb-msg rb-mine${state}`}>
              <div className="rb-say" onClick={() => toggle(message)}>
                <div className="rb-say-h"><RoleIcon role="owner" size={11} />{CAST.owner.name}</div>
                {unfolded ? (
                  <div className="rb-msg-b" onClick={(event) => event.stopPropagation()}>{message.body(onSelect)}</div>
                ) : (
                  <p className="rb-clamp">{message.summary}</p>
                )}
              </div>
            </li>
          )
        }
        return (
          <li key={message.key} ref={ref} className={`rb-msg rb-role-${message.role}${state}`}>
            <i className={`rb-tile${message.live ? ' rb-live' : ''}`}><RoleIcon role={message.role} /></i>
            <div className="rb-msg-main">
              <button type="button" className="rb-msg-h" onClick={() => toggle(message)} aria-expanded={unfolded}>
                <b>{CAST[message.role].name}</b>
                <span>{message.summary}</span>
              </button>
              {unfolded && <div className="rb-msg-card">{message.body(onSelect)}</div>}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
