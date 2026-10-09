/* The ribbon route's geometry: a meander down a narrow column, one sweep per
   leg of the run, sampled into a polyline that knows its arc length, and the
   strand outlines of a ribbon whose width changes along it. Everything here is
   plain arithmetic, so the layout is the same in a browser and in a test. */

export interface Point {
  x: number
  y: number
}

/** A point of the sampled spine: its arc length from the start and the unit normal to its left. */
export interface Sample extends Point {
  s: number
  nx: number
  ny: number
}

export interface Spine {
  samples: Sample[]
  /** Arc length at the start of each leg, and at the end of the last one. */
  bounds: number[]
  length: number
  height: number
}

/** A stable value in [-1, 1] for `seed` and `index`, so a run keeps its shape between visits. */
export function jitter(seed: number, index: number): number {
  let h = (seed ^ Math.imul(index + 1, 0x9e3779b1)) >>> 0
  h = Math.imul(h ^ (h >>> 16), 0x85ebca6b) >>> 0
  h = Math.imul(h ^ (h >>> 13), 0xc2b2ae35) >>> 0
  return ((h ^ (h >>> 16)) >>> 0) / 0xffffffff * 2 - 1
}

export function hash(text: string): number {
  let h = 2166136261
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619)
  return h >>> 0
}

type Cubic = [Point, Point, Point, Point]

/* Each leg sweeps across the column from one side to the other. Every turn is
   passed heading straight down, so the leg arriving and the leg leaving share
   one tangent there and the ribbon rounds the turn like the crest of a wave
   instead of folding at a corner. The first leg leaves the top corner flat and
   bends down into the first turn. Each sweep's depth and reach vary a little
   with the run's seed, so no two turns are the same. */
function legs(width: number, heights: number[], seed: number, margin: number): Cubic[] {
  const out: Cubic[] = []
  let a: Point = { x: margin, y: 26 }
  heights.forEach((h, i) => {
    const right = i % 2 === 0
    const reach = jitter(seed, i) * 12
    const b: Point = { x: right ? width - margin - reach : margin + reach, y: a.y + h }
    const pull = h * (0.62 + jitter(seed, i + 101) * 0.08)
    const c1: Point = i === 0 ? { x: a.x + Math.abs(b.x - a.x) * 0.55, y: a.y } : { x: a.x, y: a.y + pull }
    const c2: Point = { x: b.x, y: b.y - pull * (i === 0 ? 0.9 : 1) }
    out.push([a, c1, c2, b])
    a = b
  })
  return out
}

function at([p0, p1, p2, p3]: Cubic, t: number): Point {
  const u = 1 - t
  return {
    x: u * u * u * p0.x + 3 * u * u * t * p1.x + 3 * u * t * t * p2.x + t * t * t * p3.x,
    y: u * u * u * p0.y + 3 * u * u * t * p1.y + 3 * u * t * t * p2.y + t * t * t * p3.y,
  }
}

/** The spine of a route of `heights.length` legs in a column `width` wide; each leg is `heights[i]` tall. */
export function spine(width: number, heights: number[], seed: number, margin = 46, steps = 72): Spine {
  const points: Point[] = []
  const starts: number[] = []
  for (const curve of legs(width, heights, seed, margin)) {
    starts.push(points.length ? points.length - 1 : 0)
    for (let k = points.length ? 1 : 0; k <= steps; k++) points.push(at(curve, k / steps))
  }
  const samples: Sample[] = []
  let s = 0
  points.forEach((p, i) => {
    if (i) s += Math.hypot(p.x - points[i - 1].x, p.y - points[i - 1].y)
    const prev = points[Math.max(0, i - 1)]
    const next = points[Math.min(points.length - 1, i + 1)]
    const dx = next.x - prev.x
    const dy = next.y - prev.y
    const m = Math.hypot(dx, dy) || 1
    samples.push({ ...p, s, nx: -dy / m, ny: dx / m })
  })
  const bounds = [...starts.map((index) => samples[index]?.s ?? 0), s]
  const height = Math.max(...points.map((p) => p.y), 0) + 34
  return { samples, bounds, length: s, height }
}

/** The spine point at arc length `s`, its normal interpolated. */
export function pointAt(spine: Spine, s: number): Sample {
  const { samples } = spine
  const target = Math.max(0, Math.min(spine.length, s))
  let lo = 0
  let hi = samples.length - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (samples[mid].s <= target) lo = mid
    else hi = mid
  }
  const a = samples[lo]
  const b = samples[hi]
  const f = b.s > a.s ? (target - a.s) / (b.s - a.s) : 0
  const nx = a.nx + (b.nx - a.nx) * f
  const ny = a.ny + (b.ny - a.ny) * f
  const m = Math.hypot(nx, ny) || 1
  return { x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f, s: target, nx: nx / m, ny: ny / m }
}

/** A width that eases between `keys` (arc length, width), held flat before the first and after the last. */
export function profile(keys: [number, number][]): (s: number) => number {
  const sorted = [...keys].sort((a, b) => a[0] - b[0])
  return (s: number) => {
    if (!sorted.length) return 0
    if (s <= sorted[0][0]) return sorted[0][1]
    for (let i = 1; i < sorted.length; i++) {
      const [s1, w1] = sorted[i]
      if (s <= s1) {
        const [s0, w0] = sorted[i - 1]
        const t = s1 > s0 ? (s - s0) / (s1 - s0) : 1
        return w0 + (w1 - w0) * t * t * (3 - 2 * t)
      }
    }
    return sorted[sorted.length - 1][1]
  }
}

/** How far the ribbon has rolled about its spine at arc length `s`, for a half twist over each `[centre, half]`
    window: 0 before the first, a quarter turn (edge-on) at each centre, half a turn more after each. The roll
    eases in and out of every window, so the ribbon never creases. Seen from above a ribbon of width w shows
    w·cos(angle), so its strands cross and swap sides at every centre. */
export function twist(windows: [number, number][]): (s: number) => number {
  const sorted = [...windows].sort((a, b) => a[0] - b[0])
  return (s: number) => {
    let angle = 0
    for (const [centre, half] of sorted) {
      if (s < centre - half) return angle
      if (s <= centre + half) {
        const u = (s - centre + half) / (2 * half)
        return angle + Math.PI * u * u * (3 - 2 * u)
      }
      angle += Math.PI
    }
    return angle
  }
}

/** The outline of each strand of the ribbon between arc lengths `from` and `to`: strand i of `counts` takes its
    share of the width, the strands laid side by side across the spine. A negative width lays them the other way. */
export function strands(spine: Spine, from: number, to: number, width: (s: number) => number, counts: number[], step = 3): string[] {
  const total = counts.reduce((sum, n) => sum + n, 0)
  if (!total || to <= from) return []
  const stops: number[] = []
  for (let s = from; s < to; s += step) stops.push(s)
  stops.push(to)
  const points = stops.map((s) => pointAt(spine, s))
  let before = 0
  return counts.map((n) => {
    const lo = before / total
    const hi = (before + n) / total
    before += n
    const edge = (f: number) =>
      points.map((p) => {
        const w = width(p.s)
        const d = -w / 2 + w * f
        return `${(p.x + p.nx * d).toFixed(1)} ${(p.y + p.ny * d).toFixed(1)}`
      })
    return `M ${edge(lo).join(' L ')} L ${edge(hi).reverse().join(' L ')} Z`
  })
}

/** The spine itself between two arc lengths, as a path. */
export function thread(spine: Spine, from: number, to: number, step = 4): string {
  const stops: number[] = []
  for (let s = from; s < to; s += step) stops.push(s)
  stops.push(to)
  return 'M ' + stops.map((s) => {
    const p = pointAt(spine, s)
    return `${p.x.toFixed(1)} ${p.y.toFixed(1)}`
  }).join(' L ')
}
