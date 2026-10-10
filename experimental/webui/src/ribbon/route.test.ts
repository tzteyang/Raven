import { describe, expect, it } from 'vitest'

import { pointAt, profile, spine, strands, twist } from './geometry'
import { flagKey, focusOf, foldKey, layout, legKey, trialKey, waistKey } from './layout'
import { apply, routeOf } from './route'

import type { ProcessEntry, Thread, TrialView } from '../studio/types'
import type { CommitmentOp } from './route'

function process(round: number, opts: { to?: string; ops?: CommitmentOp[]; decision?: string; error?: string; targets?: string[]; running?: boolean }): ProcessEntry {
  const values = Object.fromEntries((opts.targets ?? []).map((target) => [target, {}]))
  const curation = opts.to || opts.error
    ? {
        from: 'v',
        to: opts.to ?? 'v',
        deployed: !!opts.to,
        error: opts.error ?? null,
        scopes: [{ name: '', root: true, plan: { understanding: '', changes: [], ...(opts.ops ? { commitments: opts.ops } : {}) } }],
        before: { root: { values: {} }, children: {} },
        after: { root: { values }, children: {} },
        paused: null,
      }
    : null
  return {
    kind: 'process',
    key: `proc-${round}`,
    round,
    onboarding: round === 0,
    feedback: opts.decision ? { decision: opts.decision, reason: '', requirements: [], filtered: [], task_updates: [] } : null,
    curation,
    curationState: opts.running ? 'running' : curation ? (opts.to ? 'done' : 'failed') : 'none',
  } as unknown as ProcessEntry
}

const trial = (id: string, status: 'running' | 'done' = 'done') => ({ id, title: id, status }) as unknown as TrialView

function thread(entries: unknown[], status = 'finished'): Thread {
  return { id: 'run', title: 'run', mode: 'replay', entries, versions: ['v0'], current: 'v0', status } as unknown as Thread
}

const add = (id: string, surface: string, serves = ['task']): CommitmentOp => ({ action: 'add', id, surface, statement: `${id} on ${surface}`, serves })

describe('commitments replayed from plans', () => {
  it('applies operations the way the host does', () => {
    const one = apply([], [add('H1', 'capability.strategy'), add('H2', 'action.strategy')])
    const two = apply(one, [
      { action: 'modify', id: 'H1', surface: 'action.strategy', reason: 'moved' },
      { action: 'retire', id: 'H2', reason: 'stopped good deliveries' },
      { action: 'modify', id: 'H9', reason: 'no such entry' },
    ])
    expect(two.map((item) => [item.id, item.surface, item.retired ?? ''])).toEqual([
      ['H1', 'action.strategy', ''],
      ['H2', 'action.strategy', 'stopped good deliveries'],
    ])
    expect(two[0].statement).toBe('H1 on capability.strategy')
  })
})

describe('a run as a route', () => {
  const run = thread(
    [
      { kind: 'request', key: 'r0', round: 0, speaker: 'owner', text: 'Here are the norms' },
      process(0, { to: 'v1', ops: [add('H1', 'capability.strategy'), add('H2', 'memory.strategy'), add('H3', 'native')] }),
      { kind: 'trials', key: 't1', round: 1, version: 'v1', trials: [trial('a'), trial('b')] },
      process(1, {
        to: 'v2',
        decision: 'curate',
        ops: [
          { action: 'modify', id: 'H1', statement: 'Supply five norms', reason: 'two more' },
          { action: 'modify', id: 'H3', surface: 'action.strategy', reason: 'gate before delivery' },
          { action: 'retire', id: 'H2', reason: 'brief no longer needed' },
          add('H4', 'planning.strategy'),
        ],
      }),
      { kind: 'trials', key: 't2', round: 2, version: 'v2', trials: [trial('c', 'running')], pending: true },
    ],
    'running',
  )

  it('has one leg per version, with strands per surface and marks against the version before', () => {
    const route = routeOf(run)
    expect(route.recorded).toBe(true)
    expect(route.live).toBe(true)
    expect(route.legs.map((leg) => [leg.version, leg.end, leg.trials.length])).toEqual([
      ['v0', 'waist', 0],
      ['v1', 'waist', 2],
      ['v2', 'open', 1],
    ])
    expect(route.legs[0].strands).toEqual([])
    expect(route.legs[1].strands).toEqual([
      { surface: 'memory.strategy', count: 1 },
      { surface: 'capability.strategy', count: 1 },
      { surface: 'native', count: 1 },
    ])
    expect(route.legs[2].strands).toEqual([
      { surface: 'planning.strategy', count: 1 },
      { surface: 'capability.strategy', count: 1 },
      { surface: 'action.strategy', count: 1 },
    ])
    expect(route.legs[2].marks).toEqual({ H1: 'modify', H3: 'move', H2: 'retire', H4: 'add' })
    expect(route.legs[2].retired.map((item) => item.id)).toEqual(['H2'])
    expect(route.legs[1].requests).toEqual([])
    expect(route.legs[0].requests).toHaveLength(1)
  })

  it('opens a leg for a round that kept its version, and none after a run that ended', () => {
    const kept = routeOf(
      thread([
        process(0, { to: 'v1', ops: [add('H1', 'action.strategy')] }),
        { kind: 'trials', key: 't1', round: 1, version: 'v1', trials: [trial('a')] },
        process(1, { decision: 'continue' }),
        { kind: 'trials', key: 't2', round: 2, version: 'v1', trials: [trial('b')] },
        process(2, { decision: 'stop' }),
      ]),
    )
    expect(kept.legs.map((leg) => [leg.version, leg.end])).toEqual([
      ['v0', 'waist'],
      ['v1', 'open'],
      ['v1', 'open'],
    ])
    expect(kept.legs[2].commitments?.map((item) => item.id)).toEqual(['H1'])
    expect(kept.live).toBe(false)
  })

  it('settles the commitments of a curation that changed no code, and ties a knot', () => {
    const knot = routeOf(
      thread([
        process(0, { to: 'v1', ops: [add('H1', 'action.strategy')] }),
        { kind: 'trials', key: 't1', round: 1, version: 'v1', trials: [trial('a')] },
        process(1, { decision: 'curate', error: 'unchanged', ops: [add('H2', 'native')] }),
        { kind: 'trials', key: 't2', round: 2, version: 'v1', trials: [trial('b')] },
      ]),
    )
    expect(knot.legs[1].end).toBe('knot')
    expect(knot.legs[2].version).toBe('v1')
    expect(knot.legs[2].marks).toEqual({ H2: 'add' })
  })

  it('falls back to the installed targets for a run recorded before commitments', () => {
    const old = routeOf(
      thread([process(0, { to: 'v1', targets: ['capability.strategy', 'action.strategy'] }), { kind: 'trials', key: 't', round: 1, version: 'v1', trials: [] }]),
    )
    expect(old.recorded).toBe(false)
    expect(old.legs[1].commitments).toBeNull()
    expect(old.legs[1].strands.map((strand) => strand.surface)).toEqual(['capability.strategy', 'action.strategy'])
  })

  it('lays out every mark in run order and maps each choice to its tab', () => {
    const route = routeOf(run)
    const shape = layout(route, 400, 'run')
    expect(shape.order).toEqual([
      legKey(0), waistKey(0),
      legKey(1), trialKey('a'), trialKey('b'), flagKey(1), waistKey(1),
      legKey(2), trialKey('c'),
    ])
    expect(shape.legs[1].strands).toHaveLength(3)
    expect(shape.legs[0].bare).not.toBeNull()
    expect(shape.ahead).not.toBeNull()
    expect(focusOf(route, null)).toEqual({ leg: 2, tab: 'harness', trial: null })
    expect(focusOf(route, waistKey(1))).toEqual({ leg: 1, tab: 'process', trial: null })
    expect(focusOf(route, trialKey('b'))).toEqual({ leg: 1, tab: 'trials', trial: 'b' })
    expect(focusOf(route, flagKey(1))).toEqual({ leg: 1, tab: 'review', trial: null })
    expect(focusOf(route, foldKey(2))).toEqual({ leg: 2, tab: 'trials', trial: null })
    expect(focusOf(route, 'heard-0-r0')).toEqual({ leg: 0, tab: 'review', trial: null })
  })

  it('turns the ribbon over at every installed curation and leaves it whole elsewhere', () => {
    const shape = layout(routeOf(run), 400, 'run')
    const { roll } = shape.body
    const [first, second] = [shape.legs[0].to, shape.legs[1].to]
    expect(roll(shape.legs[0].from)).toBe(0)
    expect(roll(first)).toBeCloseTo(Math.PI / 2)
    expect(roll((first + second) / 2)).toBeCloseTo(Math.PI)
    expect(roll(second)).toBeCloseTo(Math.PI * 1.5)
    expect(shape.legs[1].clasp).not.toBeNull()
    expect(shape.body.alpha(shape.legs[2].to)).toBe(1)
  })
})

describe('geometry', () => {
  it('samples a meander whose legs follow one another down the column', () => {
    const path = spine(400, [64, 90, 90], 7)
    expect(path.bounds).toHaveLength(4)
    expect(path.bounds.every((s, i) => i === 0 || s > path.bounds[i - 1])).toBe(true)
    expect(path.bounds[3]).toBeCloseTo(path.length)
    const p = pointAt(path, path.length / 2)
    expect(Math.hypot(p.nx, p.ny)).toBeCloseTo(1)
    expect(Math.max(...path.samples.map((point) => point.x))).toBeLessThanOrEqual(400)
  })

  it('eases between widths and splits the ribbon into one closed outline per strand', () => {
    const width = profile([[0, 2], [10, 20]])
    expect(width(-5)).toBe(2)
    expect(width(5)).toBeCloseTo(11)
    expect(width(50)).toBe(20)
    const outlines = strands(spine(400, [80], 1), 0, 60, () => 12, [1, 2])
    expect(outlines).toHaveLength(2)
    expect(outlines.every((d) => d.startsWith('M ') && d.endsWith(' Z'))).toBe(true)
  })

  it('rolls half a turn over each twist window, edge-on at its centre and eased at its ends', () => {
    const roll = twist([[100, 20], [40, 10]])
    expect(roll(0)).toBe(0)
    expect(roll(40)).toBeCloseTo(Math.PI / 2)
    expect(roll(70)).toBeCloseTo(Math.PI)
    expect(roll(100)).toBeCloseTo(Math.PI * 1.5)
    expect(roll(200)).toBeCloseTo(Math.PI * 2)
    expect(roll(81) - roll(80)).toBeLessThan(0.01)
  })
})
