import { describe, expect, it } from 'vitest'

import { hooks, looseFiles, referenced, strategyOf, targetFiles } from './mechanism'

import type { Artifact } from './model'

describe('strategy of a target', () => {
  it('reads the four strategies from the target and nothing else', () => {
    expect(['memory.strategy', 'planning.strategy', 'capability.strategy', 'action.strategy'].map(strategyOf)).toEqual(['memory', 'planning', 'capability', 'action'])
    expect(strategyOf('files')).toBeNull()
    expect(strategyOf('delivery.strategy')).toBeNull()
  })
})

describe('binding hooks', () => {
  it('names the factory and the host consumers an action binding switches on', () => {
    expect(hooks('action.strategy', { factory: 'action_impl:create', events: ['progress', 'proposal'], dispatch: false })).toEqual([
      { name: 'factory', value: 'action_impl:create' },
      { name: 'events', value: 'progress, proposal' },
    ])
    expect(hooks('action.strategy', { factory: 'a:b', tool: { name: 'ask_action' }, requests: true, dispatch: true }).map((hook) => hook.name)).toEqual(['factory', 'tool', 'requests', 'events', 'dispatch'])
  })

  it('reads the planning and memory consumers in their own terms and a capability binding as its factory', () => {
    expect(hooks('planning.strategy', { factory: 'p:c', context: true, observe: ['after_tool'] })).toEqual([
      { name: 'factory', value: 'p:c' },
      { name: 'context', value: 'guidance before model calls' },
      { name: 'observe', value: 'after_tool' },
    ])
    expect(hooks('memory.strategy', { factory: 'm:c', observe: true, intake: true, archive: true, compact: ['before_model'], require_sources: false }).map((hook) => hook.name)).toEqual(['factory', 'observe', 'intake', 'archive', 'compact', 'sources'])
    expect(hooks('capability.strategy', { factory: 'c:c', observe: true })).toEqual([{ name: 'factory', value: 'c:c' }])
    expect(hooks('memory.strategy', undefined)).toEqual([])
  })
})

describe('target files', () => {
  const artifact: Artifact = {
    values: { 'memory.strategy': { factory: 'memory_impl:create' }, 'action.strategy': { factory: 'pkg.action:create' } },
    files: {
      'memory_impl.py': 'PROFILE = "memory_profile/agent.md"',
      'memory_profile/agent.md': 'rules',
      'pkg/action/__init__.py': 'def create(): ...',
      'prompts/review.md': 'review',
    },
  }

  it('finds generated modules named as module:symbol entry points', () => {
    expect(referenced({ factory: 'memory_impl:create' }, artifact.files)).toEqual(['memory_impl.py'])
    expect(referenced({ factory: 'pkg.action:create' }, artifact.files)).toEqual(['pkg/action/__init__.py'])
    expect(referenced({ factory: 'elsewhere:thing' }, artifact.files)).toEqual([])
  })

  it('gives a target its modules and the files they name, and leaves the files no code names loose', () => {
    expect(targetFiles('memory.strategy', artifact)).toEqual(['memory_impl.py', 'memory_profile/agent.md'])
    expect(targetFiles('action.strategy', artifact)).toEqual(['pkg/action/__init__.py'])
    expect(targetFiles('planning.strategy', artifact)).toEqual([])
    expect(looseFiles(artifact)).toEqual(['prompts/review.md'])
  })
})
