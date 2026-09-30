/* The Studio's live sessions as the server keeps them (experimental/webui/
   live.py): what a new session starts from and the sessions kept, refreshed
   every little while, and the selected session polled -- its slim record only
   when the record changed, with the state its process reports -- faster while
   a step or a trial is under way. Each action is one of the Session's steps,
   after which the session is read again at once. */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { createLive, liveInfo, liveSnapshot, liveStep } from './api'
import { liveThread } from './live'

import type { Run } from '../model'
import type { LiveInfo, LiveSnapshot, LiveState, StepReply } from './api'
import type { LiveSession } from './live'

export const PACE = { info: 15000, active: 1000, idle: 4000, still: 20000 }
// How long a chained step waits for the one before it to end.
const SETTLE_LIMIT = 60 * 60 * 1000

interface Kept {
  snapshot: LiveSnapshot
  run: Run | null
}

export interface Live {
  /** What a new session starts from; null when the server serves recorded runs only, undefined while it is asked. */
  info: LiveInfo | null | undefined
  sessions: LiveSession[]
  create: (title: string, task: string) => Promise<string>
  take: (id: string, op: string, body?: Record<string, unknown>) => Promise<StepReply>
  /** Wait until the step under way in a session has ended, and give the state it ended in. */
  settle: (id: string) => Promise<LiveState | null>
  reload: () => void
}

const pace = (kept: Kept | undefined): number => {
  const snapshot = kept?.snapshot
  if (!snapshot?.attached) return PACE.still
  return snapshot.state?.step || snapshot.state?.trial || !snapshot.state ? PACE.active : PACE.idle
}

export function useLive(selected: string | null): Live {
  const [info, setInfo] = useState<LiveInfo | null | undefined>(undefined)
  const [kept, setKept] = useState<Record<string, Kept>>({})
  const current = useRef(kept)
  current.current = kept

  const reload = useCallback(() => {
    liveInfo().then(setInfo, () => setInfo((prev) => prev ?? null))
  }, [])

  useEffect(() => {
    reload()
    const timer = window.setInterval(reload, PACE.info)
    return () => window.clearInterval(timer)
  }, [reload])

  const refresh = useCallback(async (id: string): Promise<Kept | null> => {
    const before = current.current[id]
    try {
      const snapshot = await liveSnapshot(id, before?.run ? before.snapshot.stamp : null)
      const next = { snapshot, run: snapshot.record ?? before?.run ?? null }
      current.current = { ...current.current, [id]: next }
      setKept((prev) => ({ ...prev, [id]: next }))
      return next
    } catch {
      return null
    }
  }, [])

  useEffect(() => {
    if (!selected) return
    let alive = true
    let timer = 0
    const tick = async () => {
      const next = await refresh(selected)
      if (alive) timer = window.setTimeout(tick, pace(next ?? current.current[selected]))
    }
    tick()
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
  }, [selected, refresh])

  const take = useCallback(
    async (id: string, op: string, body: Record<string, unknown> = {}) => {
      const reply = await liveStep(id, op, body)
      await refresh(id)
      return reply
    },
    [refresh],
  )

  const settle = useCallback(
    async (id: string) => {
      const deadline = Date.now() + SETTLE_LIMIT
      while (Date.now() < deadline) {
        const next = await refresh(id)
        const state = next?.snapshot.state ?? null
        if (!next?.snapshot.attached || (state && !state.step)) return state
        await new Promise((resolve) => window.setTimeout(resolve, PACE.active))
      }
      return current.current[id]?.snapshot.state ?? null
    },
    [refresh],
  )

  const create = useCallback(
    async (title: string, task: string) => {
      const summary = await createLive(title, task)
      reload()
      await refresh(summary.id)
      return summary.id
    },
    [reload, refresh],
  )

  const sessions = useMemo(() => {
    const listed = info?.sessions ?? []
    const known = new Set(listed.map((row) => row.id))
    const extra = Object.values(kept)
      .map((item) => item.snapshot)
      .filter((snapshot) => !known.has(snapshot.id))
    return [...extra, ...listed].map((row) => {
      const hit = kept[row.id]
      const snapshot: LiveSnapshot = hit?.snapshot ?? { ...row, state: null, busy: false, stamp: '', progress: { curation: null, paused: null } }
      return liveThread({ ...snapshot, ...(hit ? {} : row) }, hit?.run ?? null)
    })
  }, [info, kept])

  return { info, sessions, create, take, settle, reload }
}
