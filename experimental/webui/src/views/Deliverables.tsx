import { fileUrl } from '../api'
import { fileName } from '../derive'

import type { JSX } from 'react'

/* The files a turn handed over: an HTML page is shown as the traveller would
   open it, in a sandboxed frame; anything else is a link. */
export function Deliverables({ paths }: { paths: string[] }): JSX.Element | null {
  if (!paths.length) return null
  return (
    <div className="deliverables">
      {paths.map((path) => (
        <figure key={path} className="deliverable">
          <figcaption>
            <span className="tag">Delivered</span>
            <span className="n">{fileName(path)}</span>
            <a href={fileUrl(path)} target="_blank" rel="noreferrer">open</a>
          </figcaption>
          {/\.html?$/i.test(path) ? <iframe src={fileUrl(path)} sandbox="" title={fileName(path)} loading="lazy" /> : null}
        </figure>
      ))}
    </div>
  )
}
