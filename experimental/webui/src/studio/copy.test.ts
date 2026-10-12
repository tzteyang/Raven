/* The Studio's Chinese words (i18n/messages.json, section `studio`) held
   against its English (copy.ts): every word names an English entry of the same
   shape, a template fills only arguments its function takes, every English
   entry has its words unless it only picks between other entries, and a page
   loaded in Chinese speaks them, the picking functions included. */

import { describe, expect, it, vi } from 'vitest'

import { studio } from '../../../../i18n/messages.json'
import { T } from './copy'

/* Functions that carry no words of their own: they pick between other entries
   (or only rearrange what they are given), so their wording is those entries'. */
const PICKERS = new Set([
  'stepPaused', 'examples', 'recurrence', 'stageCounts', 'progressScope', 'progressSpent', 'readObserved', 'attributorSpent',
  'about', 'budget', 'footer.paused', 'turnTimedOut', 'tools', 'childRuns', 'selectedTools', 'selectedSkills', 'contextTokens',
  'dockPaused', 'runFailed', 'auditShown', 'originMark', 'originHint', 'scriptsProgress', 'examLine', 'markText', 'titleFrom',
  'newSettings', 'diffTitle', 'childScope', 'diffVersions',
])

const words = studio as Record<string, { zh: string }>

const flat = (node: object, prefix = ''): [string, unknown][] =>
  Object.entries(node).flatMap(([key, value]): [string, unknown][] =>
    value && typeof value === 'object' ? flat(value, `${prefix}${key}.`) : [[`${prefix}${key}`, value]],
  )

const english = new Map(flat(T))
const fill = (key: string, ...args: unknown[]) => words[key].zh.replace(/\{(\d+)\}/g, (_, i: string) => String(args[Number(i)]))

describe('the Chinese words of the Studio', () => {
  it('each names an English entry of its shape, filling only arguments its function takes', () => {
    for (const [key, { zh }] of Object.entries(words)) {
      const en = english.get(key)
      expect(en, key).toBeDefined()
      expect(typeof zh, key).toBe('string')
      const used = [...zh.matchAll(/\{(\d+)\}/g)].map((match) => Number(match[1]))
      if (typeof en === 'function') expect(Math.max(-1, ...used), key).toBeLessThan(en.length)
      else expect(used, key).toEqual([])
    }
  })

  it('cover every English entry but the ones that only pick between others', () => {
    for (const key of english.keys()) expect(key in words, key).toBe(!PICKERS.has(key))
  })

  it('are what a page loaded in Chinese says, through the picking functions too', async () => {
    vi.resetModules()
    localStorage.setItem('studio.lang', 'zh')
    const { T: zh, lang } = await import('./copy')
    localStorage.removeItem('studio.lang')
    expect(lang).toBe('zh')
    expect(zh.decision.curate).toBe(fill('decision.curate'))
    expect(zh.dockAsk('v2')).toBe(fill('dockAsk', 'v2'))
    expect(zh.trialsOn('v1', 3)).toBe(fill('trialsOn', 'v1', 3))
    expect(zh.footer.kept('v1')).toBe(fill('footer.kept', 'v1'))
    expect(zh.examLine({ failed: 31, judged: 78 }, { failed: 36, judged: 78 })).toBe(fill('examNow', 31, 78) + fill('examThen', 36, 78))
    expect(zh.stepPaused(zh.stages.design, 'child/Raven-PPT')).toBe(fill('pausedInAt', fill('pausedChild', 'Raven-PPT'), fill('stages.design')))
    expect(zh.newSettings('duty', null, 12)).toBe(fill('settings', 'duty', fill('curatorDefault'), 12))
  })
})
