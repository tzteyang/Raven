/* The ribbon page's entry. Like the Studio it wears ui-web's Ink & Amber sheet
   and the Studio's own sheet, whose cards and panes it reuses; ribbon.css adds
   the route and the panel. */

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import '../../../../ui-web/src/styles/page.css'
import '../../../../ui-web/src/features/tasks/styles.css'
import '../studio/studio.css'
import './ribbon.css'
import { Crash } from '../studio/Crash'
import { Ribbon } from './Ribbon'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Crash>
      <Ribbon />
    </Crash>
  </StrictMode>,
)
