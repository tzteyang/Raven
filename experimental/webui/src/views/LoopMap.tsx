/* The cultivation loop as a canvas of boards above the conversation: onboarding on a board of its own as an open
   line, every round on one around a closed track (the trial side along the top, the Curator's side back along the
   bottom), and each board handing the version it made to the next. The canvas (React Flow) pans and zooms, opens with
   every board in view when they fit and keeps the board the reader is at in view. The station read or pointed at in
   the conversation is marked; picking a station is how the conversation is told to go there, and what a station
   holds shows under the canvas while it is pointed at. Stations near the pointer swell and lean toward it while a
   light follows it across the board. The station a running run is at pulses, with the track into it flowing.
   Nothing moves for a reader who asks for less motion. */

import { Background, BackgroundVariant, Controls, Handle, MiniMap, Position, ReactFlow, ReactFlowProvider, useReactFlow, useStore } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react'

import { loadPhase } from '../api'
import { summaryOf } from '../loop'

import type { Lap, Phase, Station, StationId } from '../loop'
import type { Edge, Node, NodeProps } from '@xyflow/react'
import type { JSX, PointerEvent as ReactPointerEvent } from 'react'

export interface Picked {
  round: number
  station: StationId
}

const PHASE_POLL = 5000

/** The phase of a running run, re-read while it runs; null for a run that is not running or before the first answer. */
export function usePhase(runId: string | null, running: boolean): Phase | null {
  const [phase, setPhase] = useState<Phase | null>(null)
  useEffect(() => {
    setPhase(null)
    if (!running || !runId) return
    let live = true
    const read = () => loadPhase(runId).then((reply) => live && setPhase(reply.phase ?? null)).catch(() => undefined)
    read()
    const timer = setInterval(read, PHASE_POLL)
    return () => {
      live = false
      clearInterval(timer)
    }
  }, [runId, running])
  return phase
}

/** The key a station goes by on the canvas and on the conversation block that tells it (`data-station`). */
export const stationKey = (round: number, id: StationId): string => `${round}:${id}`

const SHORT: Record<StationId, string> = { handover: 'Handover', version: 'Version', trial: 'Trial', assess: 'Assess', analyse: 'Analyse', diagnose: 'Diagnose', design: 'Design', implement: 'Implement' }

/* Board geometry in canvas units. A round's track is a stadium: TOP and BOTTOM are its straights, LEFT and RIGHT the
   centres of its turns; onboarding's line runs at MIDDLE. */
const HEIGHT = 124
const ROUND_WIDTH = 256
const OPEN_WIDTH = 232
const GAP = 56
const TOP = 52
const BOTTOM = 96
const MIDDLE = 74
const LEFT = 46
const RIGHT = 210
const TURN = (BOTTOM - TOP) / 2
const CANVAS = 156
const SIDE = 46
const MIN_ZOOM = 0.55
const REACH = 44
const PULL = 3
const FOLLOW = 420
const TIP_HALF = 240

interface Spot {
  x: number
  y: number
  below: boolean
}

const step = (RIGHT - LEFT) / 3
const RING: Record<string, Spot> = {
  version: { x: LEFT, y: TOP, below: false },
  trial: { x: LEFT + step, y: TOP, below: false },
  assess: { x: LEFT + step * 2, y: TOP, below: false },
  analyse: { x: RIGHT, y: TOP, below: false },
  diagnose: { x: RIGHT, y: BOTTOM, below: true },
  design: { x: (LEFT + RIGHT) / 2, y: BOTTOM, below: true },
  implement: { x: LEFT, y: BOTTOM, below: true },
}
const OPEN: Record<string, Spot> = Object.fromEntries(
  ['handover', 'diagnose', 'design', 'implement'].map((id, i) => [id, { x: 38 + i * 52, y: MIDDLE, below: i % 2 === 1 }]),
)

const widthOf = (lap: Lap): number => (lap.round === 0 ? OPEN_WIDTH : ROUND_WIDTH)
const spotOf = (lap: Lap, id: StationId): Spot => (lap.round === 0 ? OPEN : RING)[id]

/* The track from station i to the next; a round's last part turns back to its first station, the loop going round. */
function track(lap: Lap, i: number): string {
  const from = spotOf(lap, lap.stations[i].id)
  if (lap.round > 0 && i === lap.stations.length - 1) return `M${LEFT} ${BOTTOM} A${TURN} ${TURN} 0 0 1 ${LEFT} ${TOP}`
  const to = spotOf(lap, lap.stations[i + 1].id)
  if (from.y !== to.y) return `M${from.x} ${from.y} A${TURN} ${TURN} 0 0 1 ${to.x} ${to.y}`
  return `M${from.x} ${from.y} L${to.x} ${to.y}`
}

const lapName = (round: number): string => (round === 0 ? 'onboarding' : `round ${round}`)
const said = (station: Station): string => [station.facts.join(' · '), station.state === 'done' ? '' : station.note].filter(Boolean).join(' — ')
const still = (): boolean => typeof window !== 'undefined' && Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)

interface Marks {
  marked: Set<string>
  active: string | null
  pick: (picked: Picked) => void
  point: (key: string | null, at?: DOMRect) => void
}

const MarksContext = createContext<Marks>({ marked: new Set(), active: null, pick: () => undefined, point: () => undefined })

type Board = Node<{ lap: Lap }, 'lap'>

/* The pointer's pull on a board: each station's weight falls off with its distance from the pointer, and the light
   sits under it. Written to CSS variables, so a pointer move renders nothing. */
function lean(board: HTMLDivElement, event: ReactPointerEvent): void {
  const box = board.getBoundingClientRect()
  if (box.width) {
    board.style.setProperty('--mx', `${((event.clientX - box.left) / box.width) * board.offsetWidth}px`)
    board.style.setProperty('--my', `${((event.clientY - box.top) / box.height) * board.offsetHeight}px`)
  }
  if (still()) return
  for (const stop of board.querySelectorAll<HTMLElement>('.lb-stop')) {
    const at = stop.getBoundingClientRect()
    const dx = event.clientX - (at.left + at.width / 2)
    const dy = event.clientY - (at.top + at.height / 2)
    const distance = Math.hypot(dx, dy)
    const weight = Math.exp(-((distance / REACH) ** 2))
    stop.style.setProperty('--w', weight.toFixed(3))
    stop.style.setProperty('--dx', `${distance ? ((dx / distance) * PULL * weight).toFixed(2) : 0}px`)
    stop.style.setProperty('--dy', `${distance ? ((dy / distance) * PULL * weight).toFixed(2) : 0}px`)
  }
}

function settle(board: HTMLDivElement): void {
  board.style.removeProperty('--mx')
  board.style.removeProperty('--my')
  for (const stop of board.querySelectorAll<HTMLElement>('.lb-stop')) {
    stop.style.removeProperty('--w')
    stop.style.removeProperty('--dx')
    stop.style.removeProperty('--dy')
  }
}

function LapBoard({ data }: NodeProps<Board>): JSX.Element {
  const { lap } = data
  const { marked, active, pick, point } = useContext(MarksContext)
  const board = useRef<HTMLDivElement>(null)
  const keys = lap.stations.map((station) => stationKey(lap.round, station.id))
  const live = lap.stations.some((station) => station.state === 'current')
  const here = keys.some((key) => key === active)
  const { judged, made } = summaryOf(lap)
  const parts = lap.round === 0 ? lap.stations.length - 1 : lap.stations.length
  return (
    <div
      ref={board}
      className="lb"
      data-here={here || undefined}
      data-live={live || undefined}
      style={{ width: widthOf(lap), height: HEIGHT }}
      onPointerMove={(event) => board.current && lean(board.current, event)}
      onPointerLeave={() => board.current && settle(board.current)}
    >
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <div className="lb-head">
        <span className="lb-name">{lapName(lap.round)}</span>
        {made ? <span className="lb-made">{made}</span> : null}
      </div>
      {lap.round > 0 && judged.length ? (
        <div className="lb-judged">
          {judged.map((line) => <span key={line}>{line}</span>)}
        </div>
      ) : null}
      <svg className="lb-track" width={widthOf(lap)} height={HEIGHT} aria-hidden="true">
        {Array.from({ length: parts }, (_, i) => {
          const next = lap.stations[(i + 1) % lap.stations.length]
          const again = i === lap.stations.length - 1
          const part = again ? 'again' : next.state === 'ahead' ? 'ahead' : next.state === 'current' ? 'flow' : undefined
          return <path key={i} className="lb-seg" data-actor={again ? undefined : next.actor} data-part={part} d={track(lap, i)} />
        })}
      </svg>
      {lap.stations.map((station, i) => {
        const spot = spotOf(lap, station.id)
        const key = keys[i]
        return (
          <button
            key={key}
            type="button"
            className="lb-stop nopan"
            data-actor={station.actor}
            data-state={station.state}
            data-on={marked.has(key) || undefined}
            data-below={spot.below || undefined}
            style={{ left: spot.x, top: spot.y }}
            aria-label={`${lapName(lap.round)}, ${station.label}${said(station) ? `: ${said(station)}` : ''}`}
            aria-current={key === active ? 'location' : undefined}
            onClick={() => pick({ round: lap.round, station: station.id })}
            onPointerEnter={(event) => point(key, event.currentTarget.getBoundingClientRect())}
            onPointerLeave={() => point(null)}
            onFocus={(event) => point(key, event.currentTarget.getBoundingClientRect())}
            onBlur={() => point(null)}
          >
            <i className="lb-dot" />
            <span className="lb-label">{SHORT[station.id]}</span>
          </button>
        )
      })}
      <Handle type="source" position={Position.Right} isConnectable={false} />
    </div>
  )
}

const NODE_TYPES = { lap: LapBoard }

/* Where each board starts along the canvas, and the canvas width they span. */
function lay(laps: Lap[]): { starts: number[]; span: number } {
  const starts: number[] = []
  let edge = 0
  for (const lap of laps) {
    starts.push(edge)
    edge += widthOf(lap) + GAP
  }
  return { starts, span: Math.max(0, edge - GAP) }
}

const HANDLES = (width: number) => [
  { type: 'target' as const, position: Position.Left, x: 0, y: HEIGHT / 2 - 4, width: 1, height: 8 },
  { type: 'source' as const, position: Position.Right, x: width - 1, y: HEIGHT / 2 - 4, width: 1, height: 8 },
]

/* The camera: every board in view when they fit at a zoom no smaller than MIN_ZOOM, else the board in focus; and
   when the reader moves to a board outside the view, a glide to it at the zoom the reader has. */
function Camera({ laps, focus, starts, span }: { laps: Lap[]; focus: number | null; starts: number[]; span: number }): null {
  const flow = useReactFlow()
  const width = useStore((state) => state.width)
  const height = useStore((state) => state.height)
  const centre = (round: number): number => {
    const index = laps.findIndex((lap) => lap.round === round)
    return index < 0 ? span / 2 : starts[index] + widthOf(laps[index]) / 2
  }
  const place = (zoom: number, x: number, duration: number) =>
    void flow.setViewport({ x: width / 2 - x * zoom, y: (height - HEIGHT * zoom) / 2, zoom }, { duration })
  useEffect(() => {
    if (!width || !height) return
    const zoom = Math.max(MIN_ZOOM, Math.min(1, (width - SIDE * 2) / span, (height - 16) / HEIGHT))
    const fits = span * zoom <= width - SIDE * 2
    place(zoom, fits ? span / 2 : centre(focus ?? laps[laps.length - 1]?.round ?? 0), 0)
  }, [laps.length, width, height])
  useEffect(() => {
    if (!width || focus === null) return
    const { x, zoom } = flow.getViewport()
    const index = laps.findIndex((lap) => lap.round === focus)
    if (index < 0) return
    const left = starts[index] * zoom + x
    const right = (starts[index] + widthOf(laps[index])) * zoom + x
    if (left >= 0 && right <= width) return
    place(zoom, centre(focus), still() ? 0 : FOLLOW)
  }, [focus])
  return null
}

/* The minimap, for when the boards are too many to show at once. */
function Overview({ span }: { span: number }): JSX.Element | null {
  const width = useStore((state) => state.width)
  if (!width || span * MIN_ZOOM <= width - SIDE * 2) return null
  return <MiniMap position="bottom-right" pannable nodeBorderRadius={6} ariaLabel="Where the view is among the boards" />
}

export function LoopMap({ laps, active, hot, onPick }: { laps: Lap[]; active: string | null; hot: string | null; onPick: (picked: Picked) => void }): JSX.Element {
  const frame = useRef<HTMLDivElement>(null)
  const { starts, span } = useMemo(() => lay(laps), [laps])
  const nodes = useMemo<Board[]>(
    () => laps.map((lap, i) => ({
      id: `lap-${lap.round}`,
      type: 'lap',
      position: { x: starts[i], y: 0 },
      data: { lap },
      width: widthOf(lap),
      height: HEIGHT,
      handles: HANDLES(widthOf(lap)),
      draggable: false,
      selectable: false,
      ariaLabel: lapName(lap.round),
    })),
    [laps, starts],
  )
  const edges = useMemo<Edge[]>(
    () => laps.slice(1).map((lap, i) => ({
      id: `carry-${lap.round}`,
      source: `lap-${laps[i].round}`,
      target: `lap-${lap.round}`,
      type: 'straight',
      className: 'lb-carry',
      label: lap.stations.find((station) => station.id === 'version')?.facts[0] ?? '',
      animated: lap.stations.some((station) => station.state === 'current'),
      focusable: false,
      selectable: false,
    })),
    [laps],
  )
  const [tip, setTip] = useState<{ key: string; left: number; top: number } | null>(null)
  const marks = useMemo<Marks>(
    () => ({
      marked: new Set([active, hot].filter((key): key is string => Boolean(key))),
      active,
      pick: onPick,
      point: (key, at) => {
        const box = frame.current?.getBoundingClientRect()
        const pane = frame.current?.querySelector('.lc-pane')?.getBoundingClientRect()
        if (!key || !at || !box || !pane) return setTip(null)
        const centre = at.left + at.width / 2 - box.left
        setTip({ key, left: Math.max(TIP_HALF, Math.min(centre, box.width - TIP_HALF)), top: pane.bottom - box.top + 6 })
      },
    }),
    [active, hot, onPick],
  )
  const focus = active ? Number(active.split(':')[0]) : null
  const pointed = tip ? laps.flatMap((lap) => lap.stations.map((station) => ({ round: lap.round, station }))).find((stop) => stationKey(stop.round, stop.station.id) === tip.key) : null
  return (
    <div className="loopcanvas" ref={frame} role="group" aria-label="The cultivation loop">
      <MarksContext.Provider value={marks}>
        <ReactFlowProvider>
          <div className="lc-pane" style={{ height: CANVAS }}>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={NODE_TYPES}
              nodesDraggable={false}
              nodesConnectable={false}
              nodesFocusable={false}
              edgesFocusable={false}
              elementsSelectable={false}
              zoomOnScroll={false}
              zoomOnDoubleClick={false}
              preventScrolling={false}
              minZoom={0.35}
              maxZoom={1.6}
              fitViewOptions={{ padding: 0.06, maxZoom: 1, minZoom: MIN_ZOOM }}
              proOptions={{ hideAttribution: true }}
            >
              <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
              <Controls position="top-left" showInteractive={false} />
              <Overview span={span} />
              <Camera laps={laps} focus={focus} starts={starts} span={span} />
            </ReactFlow>
          </div>
        </ReactFlowProvider>
      </MarksContext.Provider>
      {tip && pointed ? (
        <div className="lc-tip" role="tooltip" style={{ left: tip.left, top: tip.top }}>
          <span className="dim">{lapName(pointed.round)}</span> <b>{pointed.station.label}</b> {said(pointed.station)}
        </div>
      ) : null}
    </div>
  )
}
