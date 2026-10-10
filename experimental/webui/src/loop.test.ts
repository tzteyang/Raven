/* The loop map's rows and stations, read from a cultivated run and a running run's phase. */

import { describe, expect, it } from 'vitest'

import { revisions, roundVersions } from './derive'
import { ONBOARDING, ROUND, at, loopOf, summaryOf } from './loop'
import { cultivated } from './run.fixture'

import type { Lap, Phase } from './loop'
import type { Item, Run } from './model'

const laps = (run: Run, phase: Phase | null = null): Lap[] => {
  const all = revisions(run)
  return loopOf(run, all, roundVersions(run, all), new Set(), phase)
}
const states = (lap: Lap): string[] => lap.stations.map((station) => `${station.id}:${station.state}`)

describe('the loop map', () => {
  it('lays out onboarding and every round as fixed rows of stations, read from the timeline', () => {
    const map = laps({ ...cultivated(), status: 'finished' })
    expect(map.map((lap) => lap.round)).toEqual([0, 1, 2, 3])
    expect(map[0].stations.map((station) => station.id)).toEqual(ONBOARDING)
    expect(map.slice(1).every((lap) => lap.stations.map((station) => station.id).join() === ROUND.join())).toBe(true)
    expect(map[0].stations.find((station) => station.id === 'implement')!.facts).toEqual(['installed v1', '1 file'])
    const first = map[1].stations
    expect(first.find((station) => station.id === 'version')!.facts).toEqual(['v1', '1 change'])
    expect(first.find((station) => station.id === 'trial')!.facts).toEqual(['1 drill · 1 turn'])
    expect(first.find((station) => station.id === 'analyse')!.facts).toEqual(['1 requirement', 'decision: curate'])
    expect(first.find((station) => station.id === 'diagnose')!.facts).toEqual(['1 input', '1 not triggered'])
    expect(first.find((station) => station.id === 'design')!.facts[0]).toBe('2 targets')
  })

  it('says the owner only measured when its verdicts never reached the loop', () => {
    const run = cultivated()
    const item: Item = { id: 'files-delivered', result: 'fail', session: 'drill', expected: '', actual: '', note: '' }
    const judged = { ...run.rounds[0], signals: [{ ...run.rounds[0].signals[0], items: [item] }] }
    const facts = (measuring?: string[]) =>
      laps({ ...run, status: 'finished', measuring, rounds: [judged, ...run.rounds.slice(1)] })[1].stations.find((station) => station.id === 'assess')!.facts
    expect(facts(['agency'])).toEqual(['0 pass · 1 fail', 'no red line missed', 'owner verdicts: measurement only'])
    expect(facts()).toEqual(['0 pass · 1 fail', 'no red line missed'])
  })

  it('marks a failed revision and gives a skipped Curator step the reason the conversation gives', () => {
    const map = laps({ ...cultivated(), status: 'finished' })
    const third = map[3].stations.find((station) => station.id === 'implement')!
    expect(third.state).toBe('failed')
    expect(third.note).toContain('budget exhausted')
    const second = map[2].stations.find((station) => station.id === 'diagnose')!
    expect(second.state).toBe('skipped')
    expect(second.note).toContain('kept the employee as it is')
  })

  it('puts a running run at the station its phase names and adds the round it is trying', () => {
    const run = { ...cultivated(), status: 'running' as const }
    const map = laps(run, { name: 'trial', round: 4, stage: null, basis: 'a turn is in progress' })
    const tried = map[4]
    expect(tried.round).toBe(4)
    expect(states(tried).slice(0, 3)).toEqual(['version:done', 'trial:current', 'assess:ahead'])
    expect(tried.stations[0].facts[0]).toBe('v2')
    expect(tried.stations[1].note).toBe('a turn is in progress')
    const curating = laps(run, { name: 'curating', round: 3, stage: 'implement' })[3]
    expect(states(curating).slice(4)).toEqual(['diagnose:done', 'design:done', 'implement:current'])
    const onboarding = laps({ ...run, initial_curation: [], rounds: [] }, { name: 'curating', round: 0, stage: 'design' })[0]
    expect(states(onboarding)).toEqual(['handover:done', 'diagnose:done', 'design:current', 'implement:ahead'])
    expect(onboarding.stations[1].note).toBe('done; its record is written with the revision')
  })

  it('fails the first step an errored run never recorded and leaves the rest unreached', () => {
    const run = cultivated()
    const errored: Run = { ...run, status: 'error', error: 'agency: submission budget exhausted', rounds: [{ ...run.rounds[0], signals: [], feedback: null, curated: false, curation: [] }] }
    const lap = laps(errored)[1]
    expect(states(lap).slice(0, 4)).toEqual(['version:done', 'trial:done', 'assess:failed', 'analyse:skipped'])
    expect(lap.stations[2].note).toBe('agency: submission budget exhausted')
  })

  it('names no station for a phase that is not a step of the loop', () => {
    expect(at({ name: 'stalled or stopped', round: 2, stage: null })).toBeNull()
    expect(at({ name: 'researching', round: 0, stage: 'plan' })).toEqual({ round: 0, station: 'handover' })
    expect(at({ name: 'curating', round: 1, stage: 'repair' })).toEqual({ round: 1, station: 'implement' })
    expect(at({ name: 'judging or analysing', round: 2, stage: null })).toEqual({ round: 2, station: 'assess' })
  })

  it('folds a lap into how its trial was judged and what the Curator made of it', () => {
    const map = laps({ ...cultivated(), status: 'finished' })
    expect(summaryOf(map[0])).toEqual({ judged: [], made: 'installed v1' })
    expect(summaryOf(map[1]).judged).toEqual(map[1].stations.find((station) => station.id === 'assess')!.facts)
    expect(summaryOf(map[3]).made).toBe('failed · stays v2')
    const trying = laps({ ...cultivated(), status: 'running' }, { name: 'trial', round: 4, stage: null })
    expect(summaryOf(trying[4])).toEqual({ judged: [], made: '' })
    const judging = laps({ ...cultivated(), status: 'running' }, { name: 'judging or analysing', round: 4, stage: null })
    expect(summaryOf(judging[4])).toEqual({ judged: ['assess now'], made: '' })
  })
})

