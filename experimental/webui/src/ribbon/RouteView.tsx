/* The ribbon route drawn. The ribbon's body is silk painted in WebGL on a
   canvas under the SVG; the SVG holds every label, mark and click, with each
   strand's outline kept as a clear shape that takes the leg's clicks (and is
   filled instead where the browser has no WebGL). Every mark is a focusable
   group: choosing one fades and softens the rest and lifts the chosen one, and
   the arrow keys walk the marks in the order the run took them. The column's
   width is measured, so the meander refolds when the column changes. */

import { useEffect, useMemo, useRef, useState } from 'react'

import { flagKey, focusOf, foldKey, layout, waistKey } from './layout'
import { Silk } from './silk'

import type { JSX, KeyboardEvent } from 'react'
import type { Route } from './route'
import type { Palette } from './silk'

const SURFACE_CLASS: Record<string, string> = {
  'memory.strategy': 'memory',
  'planning.strategy': 'planning',
  'capability.strategy': 'capability',
  'action.strategy': 'action',
  native: 'native',
}

export function RouteView({ route, seed, selected, onSelect }: {
  route: Route
  seed: string
  selected: string | null
  onSelect: (key: string | null) => void
}): JSX.Element {
  const box = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(400)
  useEffect(() => {
    const node = box.current
    if (!node || typeof ResizeObserver === 'undefined') return
    const watch = new ResizeObserver(([entry]) => setWidth(Math.max(300, Math.round(entry.contentRect.width))))
    watch.observe(node)
    return () => watch.disconnect()
  }, [])
  const shape = useMemo(() => layout(route, width, seed), [route, width, seed])
  const canvas = useRef<HTMLCanvasElement>(null)
  const swatches = useRef<HTMLSpanElement>(null)
  const silk = useRef<Silk | null>(null)
  const [painted, setPainted] = useState(false)
  useEffect(() => {
    try {
      silk.current = new Silk(canvas.current!)
      setPainted(true)
    } catch {
      silk.current = null
    }
    return () => {
      silk.current?.dispose()
      silk.current = null
    }
  }, [])
  useEffect(() => {
    if (!silk.current || !swatches.current) return
    const palette: Palette = {}
    for (const node of Array.from(swatches.current.children) as HTMLElement[]) {
      const surface = node.dataset.surface!
      palette[surface] = { color: getComputedStyle(node).backgroundColor, alpha: surface === 'native' ? 0.72 : 1 }
    }
    silk.current.draw(shape.body, shape.legs.map((leg) => ({ from: leg.from, to: leg.to, strands: leg.strands })), palette, width, shape.height)
  }, [shape, width, painted])
  const focus = selected ? focusOf(route, selected).leg : null
  useEffect(() => { silk.current?.focus(focus) }, [focus, shape, painted])
  const group = (key: string, small: boolean) => ({
    className: `rb-g${small ? ' rb-small' : ''}${selected === key ? ' rb-sel' : ''}`,
    'data-k': key,
    onClick: (event: { stopPropagation: () => void }) => {
      event.stopPropagation()
      onSelect(selected === key ? null : key)
    },
  })
  const walk = (event: KeyboardEvent<SVGSVGElement>) => {
    const forward = event.key === 'ArrowDown' || event.key === 'ArrowRight'
    const back = event.key === 'ArrowUp' || event.key === 'ArrowLeft'
    if (event.key === 'Escape') onSelect(null)
    if (!forward && !back) return
    event.preventDefault()
    const at = selected ? shape.order.indexOf(selected) : -1
    const next = forward ? Math.min(shape.order.length - 1, at + 1) : Math.max(0, at - 1)
    onSelect(shape.order[next] ?? null)
  }
  return (
    <div className="rb-route" ref={box}>
      <canvas ref={canvas} className="rb-silk" style={{ width, height: shape.height }} aria-hidden="true" />
      <span ref={swatches} className="rb-swatches" aria-hidden="true">
        {[...Object.keys(SURFACE_CLASS), 'other'].map((surface) => (
          <span key={surface} data-surface={surface} className={`rb-${SURFACE_CLASS[surface] ?? 'other'}`} />
        ))}
      </span>
      <svg
        className={`rb-svg${selected ? ' rb-focus' : ''}${painted ? ' rb-painted' : ''}`}
        viewBox={`0 0 ${width} ${shape.height}`}
        width="100%"
        height={shape.height}
        tabIndex={0}
        role="img"
        aria-label="迭代路线"
        onClick={() => onSelect(null)}
        onKeyDown={walk}
      >
        {shape.legs.map((leg) => (
          <g key={leg.key} {...group(leg.key, false)} data-near={leg.index === focus || undefined}>
            {leg.bare && <path className="rb-bare" d={leg.bare} />}
            {leg.strands.map((strand) => (
              <path key={strand.surface} className={`rb-strand rb-${SURFACE_CLASS[strand.surface] ?? 'other'}`} d={strand.path} />
            ))}
            {leg.label && (
              <>
                <text className="rb-ver" x={leg.label.x} y={leg.label.y + 5}>{leg.label.text}</text>
                <text className="rb-sub" x={leg.label.x} y={leg.label.y + 19}>{leg.label.sub}</text>
              </>
            )}
            {leg.opening && <rect className="rb-open" x={leg.opening.x - 6} y={leg.opening.y - 6} width={12} height={12} rx={3} />}
          </g>
        ))}
        {shape.legs.map((leg) => (
          <g key={`${leg.key}-marks`} className={leg.index === focus ? 'rb-near' : undefined}>
            {leg.clasp && (
              <g {...group(waistKey(leg.index), true)}>
                {leg.waist && <path className="rb-hit" d={leg.waist} />}
                <circle className={`rb-clasp rb-${leg.end}${leg.end === 'curating' ? ' rb-live' : ''}`} cx={leg.clasp.x} cy={leg.clasp.y} r={4.6} />
              </g>
            )}
            {leg.beads.map((bead) => (
              <g key={bead.key} {...group(bead.key, true)}>
                <title>{bead.title}</title>
                <circle className={`rb-bead${bead.live ? ' rb-live' : ''}`} cx={bead.x} cy={bead.y} r={4.6} />
              </g>
            ))}
            {leg.folded && (
              <g {...group(foldKey(leg.index), true)}>
                <circle className={`rb-bead rb-fold${leg.folded.live ? ' rb-live' : ''}`} cx={leg.folded.x} cy={leg.folded.y} r={9} />
                <text className="rb-fold-n" x={leg.folded.x} y={leg.folded.y + 3.5}>{leg.folded.count}</text>
              </g>
            )}
            {leg.flag && (
              <g {...group(flagKey(leg.index), true)}>
                <line className="rb-flag-pole" x1={leg.flag.x} y1={leg.flag.y} x2={leg.flag.tx} y2={leg.flag.ty} />
                <circle className="rb-flag-head" cx={leg.flag.tx} cy={leg.flag.ty} r={3} />
                <text className="rb-flag-t" x={leg.flag.tx + (leg.flag.tx - leg.flag.x) * 0.6} y={leg.flag.ty + (leg.flag.ty - leg.flag.y) * 0.6 + 3.5}>
                  {leg.flag.text}
                </text>
              </g>
            )}
          </g>
        ))}
        {shape.ahead && (
          <g className="rb-g rb-ahead">
            <path className="rb-ahead-path" d={shape.ahead.path} />
            <circle className="rb-head rb-live" cx={shape.ahead.head.x} cy={shape.ahead.head.y} r={4.4} />
          </g>
        )}
      </svg>
    </div>
  )
}
