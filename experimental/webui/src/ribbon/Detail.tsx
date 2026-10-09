/* The right-hand panel: what the chosen mark of the route is about, in four
   tabs. Harness is the version's commitment list, grouped by strategy surface
   and marked against the version before, with the code it was built from;
   Process is the card of the Analyst's decision and the curation that closed
   the leg; Trials are the drills played on the version; Review is what was
   heard and decided. Above the tabs the stage chosen introduces itself: its
   Raven, its icon and one line of what it did. The deeper views open inside
   the panel: a target's before-and-after, a curation's input inspector or raw
   output, a trial. */

import { useEffect, useState } from 'react'

import { DiffPane, InspectorPane, RawOutputPane } from '../studio/views/Panes'
import { ProcessCard } from '../studio/views/ProcessCard'
import { TrialPane, TrialRow } from '../studio/views/Trials'
import { Markdown } from '../studio/views/bits'
import { CAST, Emblem, RoleIcon } from './cast'
import { active, SURFACES } from './route'

import type { JSX } from 'react'
import type { CardActions } from '../studio/views/ProcessCard'
import type { CurationView, ProcessEntry } from '../studio/types'
import type { Stage } from './Chat'
import type { Tab } from './layout'
import type { Commitment, Leg, Mark, Route } from './route'

type Sub =
  | { kind: 'diff'; view: CurationView; scope: string; root: boolean; target: string }
  | { kind: 'inspect'; card: ProcessEntry }
  | { kind: 'raw'; card: ProcessEntry; scope: string }
  | null

const TABS: [Tab, string][] = [
  ['harness', 'Harness'],
  ['process', '过程'],
  ['trials', '试用'],
  ['review', '评估'],
]

const MARKS: Record<Mark, string> = { add: '新增', modify: '修改', move: '换面', retire: '撤销' }
const DECISIONS: Record<string, string> = { curate: '改造', continue: '继续', stop: '停止', supplement: '补充材料', clarify: '澄清' }

/** A served input as a short tag: a requirement id stays, a material loses its prefix, a versioned key its digest. */
export function served(value: string): string {
  if (value === 'task') return '任务'
  if (value.startsWith('information:')) return `资料 ${value.split(':').pop()!.slice(0, 6)}`
  if (value.startsWith('material:')) return value.slice('material:'.length)
  if (value.startsWith('expectation:')) return value.slice('expectation:'.length)
  return value
}

const surfaceName = (surface: string) => surface.replace('.strategy', '')

function CommitmentRow({ item, mark }: { item: Commitment; mark: Mark | undefined }): JSX.Element {
  const [open, setOpen] = useState(false)
  return (
    <li className="rb-cm" data-mark={mark ?? ''}>
      <div className="rb-cm-h">
        <code className="rb-cm-id">{item.id}</code>
        {mark && <span className={`rb-mark rb-mark-${mark}`}>{MARKS[mark]}</span>}
      </div>
      <p className={`rb-cm-text${open ? ' rb-open-text' : ''}`} onClick={() => setOpen(!open)}>
        {item.statement}
      </p>
      <div className="rb-serves">
        {item.serves.map((value) => (
          <span key={value} className="rb-chip" title={value}>{served(value)}</span>
        ))}
      </div>
    </li>
  )
}

function HarnessTab({ route, leg, onDiff }: { route: Route; leg: Leg; onDiff: (view: CurationView, target: string) => void }): JSX.Element {
  const made = leg.index > 0 ? route.legs[leg.index - 1].process?.curation ?? null : null
  const targets = made?.deployed ? Object.keys(made.after.root.values ?? {}) : []
  if (!leg.commitments) {
    return (
      <div className="rb-doc">
        <p className="rb-quiet">这次运行早于承诺条目的记录，带子按已安装的策略面显示。</p>
        <Code targets={targets} view={made} onDiff={onDiff} />
      </div>
    )
  }
  const current = active(leg.commitments)
  if (!current.length && !leg.retired.length) {
    return <div className="rb-doc"><p className="rb-quiet">{leg.version} 还没有 authored 代码，也没有承诺条目。</p></div>
  }
  const order = [...SURFACES, ...new Set(current.map((item) => item.surface).filter((surface) => !SURFACES.includes(surface)))]
  return (
    <div className="rb-doc">
      <h2 className="rb-doc-t">{leg.version}<span>{current.length} 条现行条目</span></h2>
      {order.map((surface) => {
        const items = current.filter((item) => item.surface === surface)
        if (!items.length) return null
        return (
          <section key={surface} className="rb-surface">
            <h3><i className={`rb-sw rb-${surfaceName(surface)}`} />{surfaceName(surface)}</h3>
            <ul>{items.map((item) => <CommitmentRow key={item.id} item={item} mark={leg.marks[item.id]} />)}</ul>
          </section>
        )
      })}
      {leg.retired.length > 0 && (
        <section className="rb-surface rb-retired">
          <h3>本版撤销</h3>
          <ul>
            {leg.retired.map((item) => (
              <li key={item.id} className="rb-cm">
                <div className="rb-cm-h"><code className="rb-cm-id">{item.id}</code><span className="rb-mark rb-mark-retire">撤销</span></div>
                <p className="rb-cm-text">{item.statement}</p>
                <p className="rb-reason">{item.retired}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
      <Code targets={targets} view={made} onDiff={onDiff} />
    </div>
  )
}

function Code({ targets, view, onDiff }: { targets: string[]; view: CurationView | null; onDiff: (view: CurationView, target: string) => void }): JSX.Element | null {
  if (!view || !targets.length) return null
  return (
    <section className="rb-code">
      <h3>本版代码</h3>
      <div>
        {targets.map((target) => (
          <button key={target} type="button" className="rb-chip rb-btn" onClick={() => onDiff(view, target)}>
            {surfaceName(target)} · 改前改后
          </button>
        ))}
      </div>
    </section>
  )
}

function ReviewTab({ leg }: { leg: Leg }): JSX.Element {
  const feedback = leg.process?.feedback
  return (
    <div className="rb-doc">
      {leg.requests.map((request) => (
        <section key={request.key} className="rb-heard">
          <h3>{request.speaker}</h3>
          <Markdown text={request.text} />
        </section>
      ))}
      {feedback ? (
        <section className="rb-heard">
          <h3>Analyst · {DECISIONS[feedback.decision] ?? feedback.decision}</h3>
          <p className="rb-quiet">{feedback.reason}</p>
          <ul className="rb-reqs">
            {feedback.requirements.map((requirement, k) => (
              <li key={requirement.id ?? k}>
                <code>{requirement.id}</code>
                <span className={`rb-strength rb-${requirement.strength}`}>{requirement.strength === 'must_hold' ? '必须' : '应当'}</span>
                <span>{requirement.behavior}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : (
        !leg.requests.length && <p className="rb-quiet">这一段还没有评审与判断。</p>
      )}
    </div>
  )
}

function Hero({ stage, version }: { stage: Stage; version: string }): JSX.Element {
  const cast = CAST[stage.role]
  return (
    <header className={`rb-hero rb-role-${stage.role}`} key={`${stage.role}-${version}`}>
      {cast.raven ? (
        <img className="rb-raven" src={cast.raven} alt="" />
      ) : (
        <Emblem />
      )}
      <div className="rb-hero-t">
        <div className="rb-hero-h">
          <i className="rb-tile"><RoleIcon role={stage.role} size={14} /></i>
          <b>{cast.name}</b>
          <span>{version}</span>
        </div>
        <p>{stage.line}</p>
      </div>
    </header>
  )
}

export function Detail({ route, run, leg: index, tab, trial, stage, onTab }: {
  route: Route
  run: string
  leg: number
  tab: Tab
  trial: string | null
  stage: Stage
  onTab: (tab: Tab) => void
}): JSX.Element {
  const leg = route.legs[Math.min(index, route.legs.length - 1)]
  const [sub, setSub] = useState<Sub>(null)
  const [openTrial, setOpenTrial] = useState<string | null>(trial)
  useEffect(() => {
    setSub(null)
    setOpenTrial(trial)
  }, [index, tab, trial])
  const actions: CardActions = {
    onDiff: (key, scope, root, target) => {
      const card = leg.process
      if (card?.curation && card.key === key) setSub({ kind: 'diff', view: card.curation, scope, root, target })
    },
    onInspect: () => leg.process && setSub({ kind: 'inspect', card: leg.process }),
    onRaw: (_key, scope) => leg.process && setSub({ kind: 'raw', card: leg.process, scope }),
  }
  const shown = leg.trials.find((item) => item.id === openTrial) ?? null
  const rawScope = sub?.kind === 'raw' ? sub.card.curation?.scopes.find((scope) => scope.name === sub.scope) ?? null : null
  return (
    <aside className="rb-detail">
      <Hero stage={stage} version={`${leg.version}${leg.opening ? ' · 开场' : ''}`} />
      <nav className="rb-tabs">
        {TABS.map(([key, label]) => (
          <button key={key} type="button" className={key === tab ? 'on' : ''} onClick={() => onTab(key)}>
            {label}
          </button>
        ))}
      </nav>
      <div className="rb-body">
        {sub ? (
          <div className="rb-sub">
            <button type="button" className="rb-back" onClick={() => setSub(null)}>← 返回</button>
            {sub.kind === 'diff' && <DiffPane view={sub.view} scope={sub.scope} root={sub.root} target={sub.target} />}
            {sub.kind === 'inspect' && <InspectorPane card={sub.card} />}
            {sub.kind === 'raw' && rawScope && <RawOutputPane scope={rawScope} />}
          </div>
        ) : tab === 'harness' ? (
          <HarnessTab route={route} leg={leg} onDiff={(view, target) => setSub({ kind: 'diff', view, scope: '', root: true, target })} />
        ) : tab === 'process' ? (
          leg.process ? (
            <ProcessCard card={leg.process} mode="replay" latest={leg.index === route.legs.length - 1} actions={actions} />
          ) : (
            <p className="rb-quiet rb-pad">这一段还没有判断与策展。</p>
          )
        ) : tab === 'trials' ? (
          shown ? (
            <div className="rb-sub">
              <button type="button" className="rb-back" onClick={() => setOpenTrial(null)}>← 全部试用</button>
              <TrialPane trial={shown} run={run} />
            </div>
          ) : leg.trials.length ? (
            <div className="rb-trials">
              {leg.trials.map((item) => (
                <TrialRow key={item.id} trial={item} active={false} onOpen={() => setOpenTrial(item.id)} />
              ))}
            </div>
          ) : (
            <p className="rb-quiet rb-pad">这一版还没有试用。</p>
          )
        ) : (
          <ReviewTab leg={leg} />
        )}
      </div>
    </aside>
  )
}
