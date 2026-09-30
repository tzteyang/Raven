/* The RSI Studio's entry. It wears ui-web's own stylesheets -- the Ink & Amber
   sheet and the tasks domain's, which draws the trial pill and rows -- so the
   Studio reads as a Raven surface; studio.css adds only what Raven has no
   element for. */

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import '../../../../ui-web/src/styles/page.css'
import '../../../../ui-web/src/features/tasks/styles.css'
import './studio.css'
import { Crash } from './Crash'
import { Studio } from './Studio'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Crash>
      <Studio />
    </Crash>
  </StrictMode>,
)
