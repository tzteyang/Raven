/* The RSI Studio: ui-web's shell (rail, conversation on the wash, floating
   dock, a side pane) around one thread, which is either a live session the
   person steps from the dock or a recorded automated run shown read-only.
   Live sessions exist only when the server was started with a live
   configuration, and each of the person's actions there is one of the loop's
   Session steps (useLive.ts, live.ts). Trials open in two levels: the list
   from the pill above the composer or the transcript, then a trial's process
   in the side pane, which also shows a target's before-and-after, the input
   inspector, the ledger and the compartment audit. */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { exportLive, listRuns, loadStudioRun } from './api'
import { T } from './copy'
import { detail } from './detail'
import { closeRound, lastFooter, livePhase, marksOf, openTrials, processes, sendRemark, trialsOf } from './live'
import { replayThread } from './replay'
import { useVersionSpy } from './spy'
import { useLive } from './useLive'
import { Icon } from './views/bits'
import { ArchiveDialog, NewSessionDialog, ScriptsDialog } from './views/Dialogs'
import { Composer, ReplayBar, StepBar, TrialPill } from './views/Dock'
import { AuditPane, DiffPane, InspectorPane, LedgerPane, RawOutputPane } from './views/Panes'
import { Rail } from './views/Rail'
import { ThreadView } from './views/Thread'
import { ExamCompare, examName, examTakes } from './views/Compare'
import { CollectorAsk, Proposals } from './views/Proposals'
import { TrialList, TrialPane } from './views/Trials'

import type { JSX } from 'react'
import type { Run, RunEntry } from '../model'
import type { LiveMaterial, StepReply } from './api'
import type { LiveSession, Phase } from './live'
import type { NewSessionInput } from './views/Dialogs'
import type { StepAction } from './views/Dock'
import type { Selected } from './views/Rail'
import type { ProcessEntry, Thread } from './types'

type Pane =
  | { kind: 'trial'; id: string }
  | { kind: 'diff'; card: string; scope: string; root: boolean; target: string }
  | { kind: 'inspect'; card: string }
  | { kind: 'raw'; card: string; scope: string }
  | { kind: 'ledger' }
  | { kind: 'audit' }
  | { kind: 'compare'; name: string }
  | null

interface Loaded {
  run?: Run
  thread?: Thread
  error?: string
}

const SHOWCASE = /^s0925c-/
const OPEN = new Set<Phase['kind']>(['onboard', 'between', 'round'])

function placeholder(session: LiveSession, phase: Phase): string {
  const footer = lastFooter(session)
  const between = () => {
    if (footer?.kind === 'supplement') return T.composerSupplement
    if (footer?.kind === 'clarify') return T.composerClarify(footer.question.length > 30 ? `${footer.question.slice(0, 30)}…` : footer.question)
    return T.composerBetween
  }
  switch (phase.kind) {
    case 'onboard':
      return T.composerFirst
    case 'between':
      return between()
    case 'round':
      return phase.trials ? T.composerNext : between()
    case 'trial':
      return T.composerTrials(1)
    case 'busy':
      return T.composerBusy[phase.step] ?? T.liveSteps[phase.step] ?? phase.step
    case 'review':
      return T.composerReview
    case 'paused':
      return T.composerPaused
    case 'starting':
      return T.dockStarting
    default:
      return ''
  }
}

export function Studio(): JSX.Element {
  const [runs, setRuns] = useState<RunEntry[]>([])
  const [runsLoaded, setRunsLoaded] = useState(false)
  const [loaded, setLoaded] = useState<Record<string, Loaded>>({})
  const [selected, setSelected] = useState<Selected>(null)
  const [pane, setPane] = useState<Pane>(null)
  const [full, setFull] = useState(false)
  const [list, setList] = useState(false)
  const [pick, setPick] = useState(false)
  const [dialog, setDialog] = useState<'new' | 'archive' | 'scripts' | null>(null)
  const [refusal, setRefusal] = useState<string | null>(null)
  const [creating, setCreating] = useState<string | null>(null)
  const [waiting, setWaiting] = useState(false)
  const [exporting, setExporting] = useState<string | null>(null)
  const [exported, setExported] = useState<string | null>(null)
  const live = useLive(selected?.kind === 'live' ? selected.id : null)

  useEffect(() => {
    let alive = true
    const load = () =>
      listRuns().then(
        (rows) => {
          if (!alive) return
          setRuns(rows)
          setRunsLoaded(true)
        },
        () => alive && setRunsLoaded(true),
      )
    load()
    const timer = window.setInterval(load, 20000)
    return () => {
      alive = false
      window.clearInterval(timer)
    }
  }, [])

  const ensure = useCallback(
    (id: string): Promise<Run> => {
      const hit = loaded[id]?.run
      if (hit) return Promise.resolve(hit)
      return loadStudioRun(id).then(
        (run) => {
          setLoaded((prev) => ({ ...prev, [id]: { run, thread: replayThread(id, run, runs.find((row) => row.id === id)) } }))
          return run
        },
        (error: Error) => {
          setLoaded((prev) => ({ ...prev, [id]: { error: error.message } }))
          throw error
        },
      )
    },
    [loaded, runs],
  )

  useEffect(() => {
    if (selected?.kind === 'run' && !loaded[selected.id]) ensure(selected.id).catch(() => undefined)
  }, [selected, loaded, ensure])

  useEffect(() => {
    if (!selected && runs.length) {
      const first = runs.find((run) => SHOWCASE.test(run.id)) ?? runs[0]
      setSelected({ kind: 'run', id: first.id })
    }
  }, [runs, selected])

  const session = selected?.kind === 'live' ? live.sessions.find((item) => item.id === selected.id) ?? null : null
  const thread: Thread | null = session ?? (selected?.kind === 'run' ? loaded[selected.id]?.thread ?? null : null)
  const loadError = selected?.kind === 'run' ? loaded[selected.id]?.error : undefined

  useEffect(() => {
    setPane(null)
    setList(false)
    setPick(false)
    setRefusal(null)
    setExported(null)
  }, [selected])

  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !dialog) {
        if (full) setFull(false)
        else setPane(null)
      }
    }
    document.addEventListener('keydown', key)
    return () => document.removeEventListener('keydown', key)
  }, [dialog, full])

  const trials = useMemo(() => (thread ? trialsOf(thread) : []), [thread])
  const scroller = useRef<HTMLDivElement>(null)
  const tail = session
    ? `${session.entries.length}:${lastFooter(session)?.kind ?? ''}:${session.state?.step ?? ''}:${session.state?.pending?.signals ?? ''}`
    : ''
  useEffect(() => {
    const node = scroller.current
    if (node && tail) node.scrollTo({ top: node.scrollHeight, behavior: 'smooth' })
  }, [tail])
  const running = thread ? openTrials(thread).length : 0
  const cardOf = (key: string): ProcessEntry | undefined => (thread ? processes(thread).find((card) => card.key === key) : undefined)
  const phase: Phase | null = session ? livePhase(session) : null
  const exportBusy = waiting || !!session?.busy || !!session?.state?.step || !!session?.state?.trial || phase?.kind === 'starting'
  const exportDisabled = !session?.summary.exportable || exportBusy || exporting !== null
  const exportHint = exportBusy ? T.exportBusy : !session?.summary.exportable ? T.exportUnsaved : T.exportHint

  const download = async () => {
    if (!session || exportDisabled) return
    const id = session.id
    setExporting(id)
    setExported(null)
    setRefusal(null)
    try {
      await exportLive(id)
      setExported(id)
    } catch (error) {
      setRefusal((error as Error).message)
    } finally {
      setExporting(null)
    }
  }

  /* One of the Session's steps for this session; a refusal or a failed request is shown above the dock. */
  const stepper = (id: string) => async (op: string, body: Record<string, unknown> = {}): Promise<StepReply> => {
    try {
      const reply = await live.take(id, op, body)
      if (reply.ok === false) setRefusal(reply.error ?? op)
      return reply
    } catch (error) {
      const message = (error as Error).message
      setRefusal(message)
      return { ok: false, error: message }
    }
  }
  const act = (work: () => Promise<unknown>) => {
    setWaiting(true)
    setRefusal(null)
    work().finally(() => setWaiting(false))
  }
  const assess = !!session?.state?.assessor && !session.state.assessed
  const offered = (live.info?.scenarios ?? []).find((item) => item.name === (session?.summary.scenario ?? live.info?.scenario))
  const practice = (offered?.scripts ?? live.info?.scripts ?? []).filter((script) => !script.exam)
  const exams = (offered?.scripts ?? live.info?.scripts ?? []).filter((script) => script.exam)

  const openTrial = (id: string) => {
    setPane({ kind: 'trial', id })
    setList(false)
  }

  const newTrial = () => {
    if (!session) return
    const id = session.id
    const round = (session.run?.rounds.length ?? 0) + 1
    act(async () => {
      const reply = await stepper(id)('trial')
      const name = reply.state?.trial?.name
      if (reply.ok && name) openTrial(`${round}:${name}`)
    })
  }

  const send = (text: string, attachments: LiveMaterial[]) => {
    if (!session) return
    const id = session.id
    const message = {
      text,
      materials: attachments.map((material) => material.name),
      onboarded: !!session.state?.onboarded,
      assess,
      reviewing: phase?.kind === 'review',
    }
    setPick(false)
    act(() => sendRemark(stepper(id), () => live.settle(id), message))
  }

  const evidence = (text: string, round: number) => {
    const hit = trials.find((trial) => {
      const key = trial.id.split(':').slice(1).join(':')
      return key && text.startsWith(key) && trial.id.startsWith(`${round}:`)
    })
    if (hit) openTrial(hit.id)
  }

  const [seen, jump] = useVersionSpy(scroller, thread)

  const bar = (() => {
    if (!session || !phase) return null
    const id = session.id
    const version = session.current
    const take = stepper(id)
    const state = session.state
    const score = state?.exam?.current
    const examText = score ? ` ${T.examLine(score, state?.exam?.previous ?? null)}${state?.exam?.previous && score.failed > state.exam.previous.failed ? ` ${T.examWorse}` : ''}` : ''
    const more: StepAction[] = [
      ...(practice.length ? [{ label: T.playScripts, icon: 'flask', disabled: waiting, onClick: () => setDialog('scripts') }] : []),
      ...(exams.length && state?.assessor && !score ? [{ label: T.examAction, icon: 'shield', disabled: waiting, title: T.examHint, onClick: () => act(() => take('exam')) }] : []),
      ...(state?.revertible ? [{ label: T.revertAction, icon: 'chevron', disabled: waiting, title: T.revertHint, onClick: () => act(() => take('revert')) }] : []),
    ]
    switch (phase.kind) {
      case 'between': {
        const stop = lastFooter(session)?.kind === 'stop'
        return (
          <StepBar
            icon={stop ? 'check' : 'spark'}
            tone={stop ? 'ok' : 'amber'}
            text={(stop ? T.dockStopAsk(version) : T.dockAsk(version)) + examText}
            actions={[
              { label: T.openTrial, icon: 'flask', primary: !stop, disabled: waiting, onClick: newTrial },
              ...more,
              { label: T.dockArchive(version), icon: 'archive', primary: stop, disabled: waiting || version === 'v0', onClick: () => setDialog('archive') },
            ]}
          />
        )
      }
      case 'busy':
        if (phase.step !== 'script' && phase.step !== 'exam') return null
        return (
          <StepBar
            icon={phase.step === 'exam' ? 'shield' : 'flask'}
            text={`${T.liveSteps[phase.step]}${T.colon}${T.scriptsProgress(state?.scripts ?? [])}`}
            actions={
              (state?.scripts ?? []).some((row) => row.done < row.steps)
                ? [{ label: T.scriptsStop, disabled: waiting, onClick: () => act(() => take('close')) }]
                : []
            }
          />
        )
      case 'round':
        return (
          <StepBar
            icon="flask"
            text={T.dockRound(phase.trials, phase.remarks) + examText}
            actions={[
              { label: T.openTrial, icon: 'flask', disabled: waiting, onClick: newTrial },
              ...more,
              {
                label: T.proposeAction,
                icon: 'spark',
                title: T.proposeHint,
                disabled: waiting || !phase.trials || !!state?.proposals?.busy,
                onClick: () => act(() => take('propose')),
              },
              {
                label: T.dockAnalyse,
                icon: 'spark',
                primary: true,
                disabled: waiting || !phase.trials,
                title: phase.trials ? undefined : T.dockNeedsTrial,
                onClick: () => act(() => closeRound(take, () => live.settle(id), assess)),
              },
            ]}
          />
        )
      case 'review':
        return (
          <StepBar
            icon="spark"
            text={T.dockReview(processes(session).at(-1)?.feedback?.requirements.length ?? 0)}
            actions={[
              { label: T.dockCurate, icon: 'spark', primary: true, disabled: waiting, onClick: () => act(() => take('curate')) },
              { label: T.dockSkip, disabled: waiting, onClick: () => act(() => take('skip')) },
            ]}
          />
        )
      case 'paused':
        return (
          <StepBar
            icon="alert"
            text={T.dockPaused(phase.step)}
            actions={[{ label: T.dockResume, icon: 'spark', primary: true, disabled: waiting, onClick: () => act(() => take(phase.step)) }]}
          />
        )
      case 'detached':
        return (
          <StepBar
            icon="alert"
            text={T.liveDetached}
            actions={[{ label: T.dockReattach, disabled: waiting, onClick: () => act(() => take('resume')) }]}
          />
        )
      case 'unstarted':
        return (
          <StepBar
            icon="alert"
            text={T.liveStartFailed(phase.error)}
            actions={session.summary.attached ? [{ label: T.dockClose, disabled: waiting, onClick: () => act(() => take('finish')) }] : []}
          />
        )
      default:
        return null
    }
  })()
  const composing = !!session && !!phase && (OPEN.has(phase.kind) || ['trial', 'busy', 'review', 'paused', 'starting'].includes(phase.kind))
  const readOnly = session && phase && (phase.kind === 'archived' || phase.kind === 'ended') ? (phase.kind === 'archived' ? T.archivedBar : T.dockEnded) : null

  const ledgered = !!thread && (!!thread.ledger || (thread.history ?? []).length > 0 || (thread.questions ?? []).length > 0)
  const violations = thread?.boundaries?.violations.length ?? 0

  const paneTrial = pane?.kind === 'trial' ? trials.find((trial) => trial.id === pane.id) ?? null : null
  const paneCard = pane && 'card' in pane ? cardOf(pane.card) : undefined
  const paneScope = pane?.kind === 'raw' ? paneCard?.curation?.scopes.find((scope) => scope.name === pane.scope) : undefined
  const paneTitle = (() => {
    if (!pane) return ''
    if (pane.kind === 'trial') return paneTrial ? `${paneTrial.title}` : ''
    if (pane.kind === 'diff') return T.diffTitle(pane.root ? T.scopeRoot : pane.scope, pane.target)
    if (pane.kind === 'raw') return T.rawOutputTitle(pane.scope || T.scopeRoot)
    if (pane.kind === 'ledger') return T.ledgerTitle
    if (pane.kind === 'audit') return T.auditTitle
    if (pane.kind === 'compare') return T.compareTitle(pane.name)
    return T.inspectorTitle(paneCard?.onboarding ? T.onboardingLabel : T.roundLabel(paneCard?.round ?? 0))
  })()
  const holding = !!session && paneTrial?.source === 'live' && paneTrial.status === 'running'
  const pendingRound = (session?.run?.rounds.length ?? 0) + 1
  const paneSession = paneTrial ? paneTrial.id.split(':').slice(1).join(':') : ''
  const paneExam = paneTrial ? examName(paneTrial) : null
  const markable =
    !!session && !!paneTrial && !paneTrial.holdout && paneTrial.status !== 'running' && paneTrial.id.startsWith(`${pendingRound}:`) && !!phase && ['between', 'round'].includes(phase.kind)

  return (
    <div className="app st-app" data-pane={pane ? (full ? 'full' : 'open') : 'off'}>
      <Rail
        live={live.info ? live.sessions : null}
        runs={runs}
        loading={!runsLoaded}
        selected={selected}
        onSelect={setSelected}
        onNew={() => {
          setCreating(null)
          setDialog('new')
        }}
      />
      <div className="main">
        <div className="chat">
          <div className="top">
            <h1 id="title">{thread?.title ?? T.product}</h1>
            {thread && (
              <span className="st-tags">
                <span className={`st-tag ${thread.mode}`}>{thread.mode === 'live' ? T.modeLive : T.modeReplay}</span>
                {thread.archived && <span className="st-tag">{T.archivedTag}</span>}
              </span>
            )}
            {thread && (
              <span className="st-vers" aria-label={T.versions}>
                {thread.versions.map((version, i) => (
                  <span key={version} className="st-verwrap">
                    {i > 0 && <Icon name="chevron" size={10} className="st-vsep" />}
                    <button
                      type="button"
                      className="st-ver"
                      data-on={version === (seen ?? thread.current)}
                      data-latest={version === thread.current || undefined}
                      aria-current={version === (seen ?? thread.current) ? 'location' : undefined}
                      title={version === thread.current ? T.latestVersion : undefined}
                      onClick={() => jump(version)}
                    >
                      {version}
                    </button>
                  </span>
                ))}
              </span>
            )}
            <span className="spacer grow" />
            {session && (
              <span className="st-export" title={exportHint}>
                <button type="button" className="st-btn" title={exportHint} disabled={exportDisabled} aria-busy={exporting === session.id} onClick={() => void download()}>
                  <Icon name="download" size={14} />
                  {exporting === session.id ? T.exporting : T.exportEmployee}
                </button>
              </span>
            )}
            {ledgered && detail === 'full' && (
              <button type="button" className="ghost-ic st-tbtn" aria-label={T.ledger} title={T.ledgerTitle} aria-pressed={pane?.kind === 'ledger'} onClick={() => setPane(pane?.kind === 'ledger' ? null : { kind: 'ledger' })}>
                <Icon name="book" />
                {(thread?.questions ?? []).length > 0 && <span className="st-count st-count-warn">{thread?.questions?.length}</span>}
              </button>
            )}
            {thread?.boundaries && detail === 'full' && (
              <button type="button" className="ghost-ic st-tbtn" aria-label={T.audit} title={violations ? T.auditViolations(violations) : T.auditTitle} aria-pressed={pane?.kind === 'audit'} onClick={() => setPane(pane?.kind === 'audit' ? null : { kind: 'audit' })}>
                <Icon name="shield" />
                {violations > 0 && <span className="st-count st-count-bad">{violations}</span>}
              </button>
            )}
            {session && (
              <button
                type="button"
                className="ghost-ic st-tbtn"
                aria-label={T.deleteSession}
                title={T.deleteSession}
                disabled={waiting}
                onClick={() => {
                  if (!window.confirm(T.deleteConfirm(session.title))) return
                  const id = session.id
                  act(async () => {
                    const reply = await stepper(id)('delete')
                    if (reply.ok) {
                      setSelected(null)
                      live.forget(id)
                    }
                  })
                }}
              >
                <Icon name="trash" />
              </button>
            )}
            {thread && (
              <button type="button" className="ghost-ic st-tbtn" data-trial-toggle aria-label={T.trialsAll(trials.length)} onClick={() => setList(!list)}>
                <Icon name="flask" />
                {trials.length > 0 && <span className="st-count">{trials.length}</span>}
              </button>
            )}
          </div>
          <div className="scroll" ref={scroller} style={{ ['--lift' as string]: bar ? '260px' : composing ? '210px' : '150px' }}>
            <div className="col" id="stage">
              {!thread && !loadError && <p className="st-quiet st-center">{selected ? T.loadingRun : T.pickSomething}</p>}
              {loadError && <p className="st-bad st-center">{T.loadFailed}{T.colon}{loadError}</p>}
              {thread && (
                <ThreadView
                  thread={thread}
                  actions={{
                    activeTrial: pane?.kind === 'trial' ? pane.id : null,
                    onTrial: openTrial,
                    onNewTrial: phase && ['between', 'round'].includes(phase.kind) ? newTrial : undefined,
                    onDiff: (card, scope, root, target) => setPane({ kind: 'diff', card, scope, root, target }),
                    onInspect: (card) => setPane({ kind: 'inspect', card }),
                    onRaw: (card, scope) => setPane({ kind: 'raw', card, scope }),
                    rawOpen: pane?.kind === 'raw' ? `${pane.card}:${pane.scope}` : null,
                    onEvidence: evidence,
                    onOpenTrial: phase && ['between', 'round'].includes(phase.kind) ? newTrial : undefined,
                    onArchive: phase?.kind === 'between' ? () => setDialog('archive') : undefined,
                    onAttach: phase && OPEN.has(phase.kind) ? () => setPick(true) : undefined,
                    inquiries: session?.state?.inquiries ?? [],
                    onInquire:
                      session && session.summary.attached && phase && !['archived', 'ended'].includes(phase.kind)
                        ? (round, role, question) => act(() => stepper(session.id)('inquire', { round, role, question }))
                        : undefined,
                  }}
                />
              )}
            </div>
          </div>
          {thread && (
            <div className="dock">
              <TrialPill running={running} total={trials.length} onToggle={() => setList(!list)} />
              {refusal && <p className="st-bad st-refusal">{T.liveRefused(refusal)}</p>}
              {exported === session?.id && <p className="st-good st-refusal" role="status">{T.exportDone}</p>}
              {session?.busy && <p className="st-quiet st-refusal">{T.liveUnreachable}</p>}
              {session && phase && (phase.kind === 'between' || phase.kind === 'round') && (
                <Proposals
                  proposals={session.state?.proposals ?? null}
                  adopted={session.state?.adopted ?? []}
                  onAdopt={waiting ? undefined : (index, choice) => act(() => stepper(session.id)('adopt', { index, ...choice }))}
                />
              )}
              {!!session?.state?.information?.questions?.length && (
                <CollectorAsk
                  questions={session.state.information.questions}
                  onAnswer={waiting ? undefined : (id, answer) => act(() => stepper(session.id)('answer', { id, ...answer }))}
                />
              )}
              {bar}
              {session && phase && composing && (
                <Composer
                  placeholder={placeholder(session, phase)}
                  disabled={waiting || !(OPEN.has(phase.kind) || phase.kind === 'review')}
                  materials={offered?.materials ?? live.info?.materials ?? []}
                  curator={session.summary.models.curator ?? live.info?.settings.curator ?? ''}
                  tag={session.state?.onboarded ? T.requestTag : T.onboardingTag}
                  pickOpen={pick}
                  onPick={setPick}
                  onSend={send}
                  hint={T.composerHint}
                />
              )}
              {!session && <ReplayBar text={T.replayBar} archived={false} />}
              {readOnly && <ReplayBar text={readOnly} archived={phase?.kind === 'archived'} />}
            </div>
          )}
        </div>
        {list && thread && <TrialList trials={trials} activeTrial={pane?.kind === 'trial' ? pane.id : null} onOpen={openTrial} onClose={() => setList(false)} />}
        {pane && thread && (
          <section className="desk-pane st-pane" data-full={full} aria-label={paneTitle}>
            <header>
              <Icon name={{ trial: 'flask', diff: 'layers', raw: 'braces', ledger: 'book', audit: 'shield', inspect: 'eye', compare: 'layers' }[pane.kind]} size={15} />
              <b title={paneTitle}>{paneTitle}</b>
              {pane.kind === 'trial' && paneTrial && <code className="st-vtag">{paneTrial.version}</code>}
              {pane.kind === 'trial' && thread && paneExam && examTakes(thread, paneExam).length > 1 && (
                <button type="button" className="st-btn" onClick={() => setPane({ kind: 'compare', name: paneExam })}>{T.compareAction}</button>
              )}
              <span className="pane-spacer grow" />
              <button type="button" className="pane-fullscreen" aria-label={full ? T.shrink : T.expand} title={full ? T.shrink : T.expand} onClick={() => setFull(!full)}>
                <Icon name={full ? 'shrink' : 'expand'} size={14} />
              </button>
              <button type="button" aria-label={T.close} onClick={() => setPane(null)}><Icon name="x" size={14} /></button>
            </header>
            <div className="desk-pane-body st-pane-body" key={JSON.stringify(pane)}>
              {pane.kind === 'trial' && paneTrial && (
                <TrialPane
                  trial={paneTrial}
                  run={thread.source ?? null}
                  onSay={holding && session ? (text) => void stepper(session.id)('say', { text }) : undefined}
                  question={
                    holding && session && session.state?.trial?.name === paneSession
                      ? { state: session.state?.question ?? null, onAsk: () => void stepper(session.id)('question') }
                      : undefined
                  }
                  onEnd={holding && session ? () => void stepper(session.id)('close') : undefined}
                  marking={
                    markable && session
                      ? {
                          given: marksOf(session.run?.pending?.signals ?? [], paneSession),
                          onMark: (turn, kind, note) =>
                            act(() =>
                              stepper(session.id)('signal', {
                                text: T.markText(paneTrial.title, turn + 1, kind, note),
                                marks: [{ session: paneSession, turn, kind, note }],
                              }),
                            ),
                        }
                      : undefined
                  }
                />
              )}
              {pane.kind === 'diff' && paneCard?.curation && <DiffPane view={paneCard.curation} scope={pane.scope} root={pane.root} target={pane.target} />}
              {pane.kind === 'inspect' && paneCard && <InspectorPane card={paneCard} />}
              {pane.kind === 'raw' && paneScope && <RawOutputPane key={`${pane.card}:${pane.scope}`} scope={paneScope} />}
              {pane.kind === 'ledger' && <LedgerPane thread={thread} />}
              {pane.kind === 'audit' && <AuditPane boundaries={thread.boundaries} />}
              {pane.kind === 'compare' && <ExamCompare takes={examTakes(thread, pane.name)} />}
            </div>
          </section>
        )}
      </div>
      {dialog === 'new' && live.info && (
        <NewSessionDialog
          info={live.info}
          error={creating}
          onCreate={(input: NewSessionInput) => {
            setCreating(null)
            live.create(input.title, input.task, input.version, input.scenario).then(
              (id) => {
                setSelected({ kind: 'live', id })
                setDialog(null)
              },
              (error: Error) => setCreating(error.message),
            )
          }}
          onBuild={(draft) => live.build(draft)}
          onCancel={() => setDialog(null)}
        />
      )}
      {dialog === 'scripts' && session && (
        <ScriptsDialog
          scripts={practice}
          onPlay={(names) => {
            const id = session.id
            setDialog(null)
            act(() => stepper(id)('script', { names }))
          }}
          onCancel={() => setDialog(null)}
        />
      )}
      {dialog === 'archive' && session && (
        <ArchiveDialog
          version={session.current}
          suggestion={`${session.title} ${session.current}`}
          onArchive={(name) => {
            const id = session.id
            const version = session.current
            setDialog(null)
            act(() => stepper(id)('archive', { name, version }))
          }}
          onCancel={() => setDialog(null)}
        />
      )}
    </div>
  )
}
