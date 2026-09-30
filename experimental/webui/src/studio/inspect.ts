/* The input inspector's reading of one process card: what the assessor kept
   for itself, what the Analyst was given, and what the Curator was handed --
   and whether any per-item verdict id the Analyst saw turns up in the
   Curator's input, which experimental/iteration/hearing.py is meant to rule
   out. */

import type { Signal } from '../model'
import type { ProcessEntry } from './types'

export interface Leak {
  id: string
  /** The key path in the Curator's input where the id was found. */
  at: string
}

export function itemIds(signals: Signal[]): string[] {
  return [...new Set(signals.flatMap((signal) => signal.items.map((item) => item.id)).filter((id) => id.length >= 3))]
}

/** Every place an item id appears as a key or as a whole value in the Curator's input. */
export function leaks(signals: Signal[], input: unknown): Leak[] {
  const ids = new Set(itemIds(signals))
  if (!ids.size || input == null) return []
  const out: Leak[] = []
  const visit = (node: unknown, path: string) => {
    if (typeof node === 'string') {
      if (ids.has(node)) out.push({ id: node, at: path })
      return
    }
    if (Array.isArray(node)) {
      node.forEach((child, i) => visit(child, `${path}[${i}]`))
      return
    }
    if (node && typeof node === 'object') {
      for (const [key, child] of Object.entries(node)) {
        if (ids.has(key)) out.push({ id: key, at: `${path}.${key}` })
        visit(child, `${path}.${key}`)
      }
    }
  }
  visit(input, 'feedback')
  return out
}

export interface Columns {
  assessor: unknown[]
  analyst: Signal[]
  curator: unknown
  leaks: Leak[]
}

export function columns(card: ProcessEntry): Columns {
  const curator = card.curation?.input ?? null
  return { assessor: card.assessor, analyst: card.signals, curator, leaks: leaks(card.signals, curator) }
}
