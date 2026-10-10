/* Who speaks on the ribbon page. Every stage of the loop has one icon, from
   the icon set ui-web uses, shown beside its messages in the conversation on
   the left; and every stage but the owner's has one of ui-web's Raven poses,
   shown large on the right when that stage is the one chosen. The owner is not
   a Raven: it is the conversation the Harness is grown from, so it wears a
   sprout, and on the right a sprout growing in a speech bubble. */

import { HugeiconsIcon } from '@hugeicons/react'
import {
  Analytics01Icon,
  CheckListIcon,
  Layers01Icon,
  PlayCircleIcon,
  Search01Icon,
  SourceCodeIcon,
  SparklesIcon,
  SproutIcon,
} from '@hugeicons/core-free-icons'

import coding from '../../../../ui-web/src/assets/ravens/coding.webp'
import content from '../../../../ui-web/src/assets/ravens/content.webp'
import data from '../../../../ui-web/src/assets/ravens/data.webp'
import agent from '../../../../ui-web/src/assets/ravens/main-agent.webp'
import research from '../../../../ui-web/src/assets/ravens/research.webp'

import type { IconSvgElement } from '@hugeicons/react'
import type { JSX } from 'react'

export type Role = 'owner' | 'self' | 'standard' | 'trial' | 'analyst' | 'curator' | 'version'

export const CAST: Record<Role, { name: string; icon: IconSvgElement; raven: string | null }> = {
  version: { name: 'Harness', icon: Layers01Icon, raven: agent },
  trial: { name: 'Trial', icon: PlayCircleIcon, raven: content },
  owner: { name: 'Owner', icon: SproutIcon, raven: null },
  self: { name: 'Self review', icon: CheckListIcon, raven: agent },
  standard: { name: 'Standard', icon: Analytics01Icon, raven: data },
  analyst: { name: 'Analyst', icon: Search01Icon, raven: research },
  curator: { name: 'Curator', icon: SourceCodeIcon, raven: coding },
}

export function RoleIcon({ role, size = 15 }: { role: Role; size?: number }): JSX.Element {
  return <HugeiconsIcon icon={CAST[role].icon} size={size} strokeWidth={1.7} aria-hidden="true" />
}

/** The owner's figure on the right: the Harness sprouting from what the owner said, a spark of what it makes. */
export function Emblem(): JSX.Element {
  return (
    <span className="rb-emblem" aria-hidden="true">
      <span className="rb-emblem-bubble"><HugeiconsIcon icon={SproutIcon} size={40} strokeWidth={1.5} /></span>
      <span className="rb-emblem-spark"><HugeiconsIcon icon={SparklesIcon} size={17} strokeWidth={1.6} /></span>
    </span>
  )
}
