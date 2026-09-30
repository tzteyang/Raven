/* Which version the reader is looking at. A version's part of the thread
   starts at the card that installed it (the first version's at the head), so
   the version shown is the last one whose start has passed a reading line a
   third of the way down the transcript; at the very end it is the last
   version. Picking a version scrolls to its start and holds it until the
   reader scrolls again, so a start the transcript cannot bring up to the line
   still shows the version picked. */

import { useCallback, useEffect, useRef, useState } from 'react'

import { processes } from './live'

import type { RefObject } from 'react'
import type { Thread } from './types'

const LINE = 0.35
// How long a picked version holds when the browser never reports the end of its smooth scroll.
const HOLD_MS = 1200

export function startOf(thread: Thread, version: string): string {
  const card = processes(thread).find((item) => item.curation?.to === version && item.curation.deployed)
  return card ? `card-${card.key}` : 'card-head'
}

/** The version whose part of the thread holds `line`, given where each version's start sits (null when absent). */
export function versionAt(versions: string[], tops: (number | null)[], line: number, atEnd: boolean): string | null {
  if (!versions.length) return null
  if (atEnd) return versions[versions.length - 1]
  let seen = versions[0]
  tops.forEach((top, i) => {
    if (top !== null && top <= line) seen = versions[i]
  })
  return seen
}

export function useVersionSpy(scroller: RefObject<HTMLDivElement | null>, thread: Thread | null): [string | null, (version: string) => void] {
  const [seen, setSeen] = useState<string | null>(null)
  const held = useRef(false)

  useEffect(() => {
    const node = scroller.current
    if (!node || !thread) {
      setSeen(null)
      return
    }
    let frame = 0
    const measure = () => {
      frame = 0
      if (held.current) return
      const box = node.getBoundingClientRect()
      const tops = thread.versions.map((version) => document.getElementById(startOf(thread, version))?.getBoundingClientRect().top ?? null)
      const atEnd = node.scrollHeight > node.clientHeight && node.scrollTop + node.clientHeight >= node.scrollHeight - 4
      setSeen(versionAt(thread.versions, tops, box.top + box.height * LINE, atEnd))
    }
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(measure)
    }
    const onWheel = () => {
      held.current = false
    }
    measure()
    node.addEventListener('scroll', onScroll, { passive: true })
    node.addEventListener('wheel', onWheel, { passive: true })
    node.addEventListener('touchmove', onWheel, { passive: true })
    node.addEventListener('keydown', onWheel)
    return () => {
      node.removeEventListener('scroll', onScroll)
      node.removeEventListener('wheel', onWheel)
      node.removeEventListener('touchmove', onWheel)
      node.removeEventListener('keydown', onWheel)
      if (frame) cancelAnimationFrame(frame)
    }
  }, [scroller, thread])

  const jump = useCallback(
    (version: string) => {
      if (!thread) return
      held.current = true
      setSeen(version)
      document.getElementById(startOf(thread, version))?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      window.setTimeout(() => {
        held.current = false
      }, HOLD_MS)
    },
    [thread],
  )

  return [seen, jump]
}
