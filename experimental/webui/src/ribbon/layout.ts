/* Where every mark of the ribbon route goes in a column of a given width.
   The ribbon is as wide as its version's commitment list, split into one strand
   per strategy surface. A curation that installs a new version turns the ribbon
   over at the turn where the leg ends, through a clasp; one that settled
   without new code cinches it there; one under way turns it edge-on and leaves
   a dotted thread ahead. A finished run trails off. Trials are beads on the
   ribbon's edge, the Analyst's decision a flag after them. */

import { hash, pointAt, profile, spine, strands as strandPaths, thread, twist } from './geometry'

import type { Spine } from './geometry'
import type { Leg, Route } from './route'
import type { Body } from './silk'

export interface Bead {
  key: string
  x: number
  y: number
  live: boolean
  title: string
}

export interface LegShape {
  index: number
  key: string
  /** The stretch of spine the leg covers. */
  from: number
  to: number
  /** One outline per strand, in the order of the leg's strands, as the ribbon shows from above. */
  strands: { surface: string; count: number; path: string }[]
  /** The bare spine where the leg has no strands. */
  bare: string | null
  label: { x: number; y: number; text: string; sub: string } | null
  opening: { x: number; y: number } | null
  beads: Bead[]
  /** Several trials folded into one bead when they would crowd the edge. */
  folded: { x: number; y: number; count: number; live: boolean } | null
  flag: { x: number; y: number; tx: number; ty: number; text: string } | null
  /** Where the curation that ends the leg holds the ribbon. */
  clasp: { x: number; y: number } | null
  /** The stretch of spine around the clasp, drawn wide and clear so the whole turn takes a click. */
  waist: string | null
  end: Leg['end']
}

export interface Layout {
  width: number
  height: number
  body: Body
  legs: LegShape[]
  /** The road not yet taken: a dotted thread from the head, and where the head is. */
  ahead: { path: string; head: { x: number; y: number } } | null
  order: string[]
}

const DECISIONS: Record<string, string> = { curate: '改造', continue: '继续', stop: '停止', supplement: '补充', clarify: '澄清' }
const THREAD = 2.4
const BEADS = 6

export const legKey = (index: number) => `leg-${index}`
export const waistKey = (index: number) => `waist-${index}`
export const flagKey = (index: number) => `flag-${index}`
export const trialKey = (id: string) => `trial-${id}`
export const foldKey = (index: number) => `trial-fold-${index}`

function heightOf(leg: Leg): number {
  if (leg.opening) return 64
  return 78 + Math.min(leg.trials.length, BEADS) * 5
}

function count(leg: Leg): number {
  return leg.strands.reduce((sum, strand) => sum + strand.count, 0)
}

export function layout(route: Route, width: number, seed: string): Layout {
  const heights = route.legs.map(heightOf)
  if (route.live) heights.push(44)
  const path: Spine = spine(width, heights, hash(seed))
  const most = Math.max(1, ...route.legs.map(count))
  const unit = Math.min(7, 40 / most)
  const widthOf = (leg: Leg) => Math.max(THREAD, count(leg) * unit)
  const keys: [number, number][] = []
  const windows: [number, number][] = []
  let fade: [number, number] | null = null
  route.legs.forEach((leg, i) => {
    const a = path.bounds[i]
    const b = path.bounds[i + 1]
    const len = b - a
    const w = widthOf(leg)
    keys.push([a + len * 0.3, w], [b - len * 0.3, w])
    const next = route.legs[i + 1]
    /* A half twist spans a quarter of the shorter leg on each side of the turn; the ribbon is edge-on at the turn
       itself, where the two legs meet with one tangent. */
    if (leg.end === 'waist' && next) windows.push([b, Math.min(len, path.bounds[i + 2] - b) * 0.26])
    else if (leg.end === 'curating') windows.push([b, len * 0.26])
    else if (leg.end === 'knot' || leg.end === 'failed') keys.push([b, Math.max(THREAD, w * 0.55)])
    else if (!next && !route.live) fade = [b - Math.min(90, len * 0.34), b]
  })
  const full = profile(keys)
  const roll = twist(windows)
  const seen = (s: number) => full(s) * Math.cos(roll(s))
  const tail = fade as [number, number] | null
  const alpha = (s: number) => {
    if (!tail || s <= tail[0]) return 1
    const t = Math.min(1, (s - tail[0]) / (tail[1] - tail[0]))
    return 1 - t * t * (3 - 2 * t)
  }
  const order: string[] = []
  const legs = route.legs.map((leg, i): LegShape => {
    const a = path.bounds[i]
    const b = path.bounds[i + 1]
    const len = b - a
    const at = (f: number, side: number, offset: number) => {
      const p = pointAt(path, a + len * f)
      const o = side * (Math.abs(seen(p.s)) / 2 + offset)
      return { x: p.x + p.nx * o, y: p.y + p.ny * o }
    }
    const shape: LegShape = {
      index: i,
      key: legKey(i),
      from: a,
      to: b,
      strands: [],
      bare: null,
      label: null,
      opening: null,
      beads: [],
      folded: null,
      flag: null,
      clasp: null,
      waist: null,
      end: leg.end,
    }
    order.push(legKey(i))
    const total = count(leg)
    if (total) {
      const outlines = strandPaths(path, a, b, seen, leg.strands.map((strand) => strand.count))
      shape.strands = leg.strands.map((strand, k) => ({ surface: strand.surface, count: strand.count, path: outlines[k] }))
    } else shape.bare = thread(path, a, b)
    /* A version's label stands outside the turn it emerges from, beside the waist that made it; the bare start is
       labelled under its first point. */
    const same = i > 0 && route.legs[i - 1].version === leg.version
    const start = pointAt(path, a)
    const outward = i === 0 ? 0 : (i - 1) % 2 === 0 ? 1 : -1
    shape.label = {
      x: start.x + outward * 26,
      y: i === 0 ? start.y + 22 : start.y + 2,
      text: same ? `${leg.version}′` : leg.version,
      sub: route.recorded ? `${leg.commitments ? leg.commitments.filter((item) => !item.retired).length : 0} 条` : `${total} 个面`,
    }
    if (leg.opening && leg.requests.length) {
      const p = at(0.42, 0, 0)
      shape.opening = { x: p.x, y: p.y }
    }
    if (leg.trials.length > BEADS) {
      const p = at(0.45, -1, 10)
      shape.folded = { x: p.x, y: p.y, count: leg.trials.length, live: leg.playing }
      order.push(foldKey(i))
    } else {
      leg.trials.forEach((trial, j) => {
        const f = leg.trials.length === 1 ? 0.45 : 0.3 + (0.32 * j) / (leg.trials.length - 1)
        const p = at(f, -1, 5.5)
        shape.beads.push({ key: trialKey(trial.id), x: p.x, y: p.y, live: trial.status === 'running', title: trial.title })
        order.push(trialKey(trial.id))
      })
    }
    const decision = leg.process?.feedback?.decision
    if (decision) {
      const base = at(0.8, -1, 3)
      const tip = at(0.8, -1, 21)
      shape.flag = { x: base.x, y: base.y, tx: tip.x, ty: tip.y, text: DECISIONS[decision] ?? decision }
      order.push(flagKey(i))
    }
    if (leg.end === 'waist' || leg.end === 'curating' || leg.end === 'knot' || leg.end === 'failed') {
      const span = Math.min(30, len * 0.12)
      const p = pointAt(path, b)
      shape.clasp = { x: p.x, y: p.y }
      shape.waist = thread(path, b - span, Math.min(path.length, b + span))
      order.push(waistKey(i))
    }
    return shape
  })
  let ahead: Layout['ahead'] = null
  if (route.live) {
    const from = path.bounds[route.legs.length]
    const head = pointAt(path, from)
    ahead = { path: thread(path, from, path.length), head: { x: head.x, y: head.y } }
  }
  return { width, height: path.height, body: { spine: path, width: full, roll, alpha }, legs, ahead, order }
}

export type Tab = 'harness' | 'process' | 'trials' | 'review'

/** What a chosen mark opens on the right: the leg it belongs to, the tab that shows it and, for a bead, its trial. */
export function focusOf(route: Route, key: string | null): { leg: number; tab: Tab; trial: string | null } {
  const head = Math.max(0, route.legs.length - 1)
  if (!key) return { leg: head, tab: 'harness', trial: null }
  const number = (prefix: string) => Number(key.slice(prefix.length))
  if (key.startsWith('leg-')) return { leg: number('leg-'), tab: 'harness', trial: null }
  if (key.startsWith('waist-')) return { leg: number('waist-'), tab: 'process', trial: null }
  if (key.startsWith('flag-')) return { leg: number('flag-'), tab: 'review', trial: null }
  if (key.startsWith('heard-')) return { leg: Number(key.split('-')[1]), tab: 'review', trial: null }
  if (key.startsWith('trial-fold-')) return { leg: number('trial-fold-'), tab: 'trials', trial: null }
  if (key.startsWith('trial-')) {
    const id = key.slice('trial-'.length)
    const leg = route.legs.findIndex((item) => item.trials.some((trial) => trial.id === id))
    return { leg: leg < 0 ? head : leg, tab: 'trials', trial: id }
  }
  return { leg: head, tab: 'harness', trial: null }
}
