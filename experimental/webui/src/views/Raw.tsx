/* Every rendered part of the cultivation conversation can be read as its own source. `useShowAs` gives a part its
   switch, a two-way segment (rendered, raw) the part places in its header or floats in its corner, and `RawPanel`
   shows the part's slices of the record (see `sources.ts`) in place of the rendering, each under the path it sits at:
   JSON highlighted, Markdown as its source, a generated module as highlighted code. */

import { useState } from 'react'

import { Fold } from './Badges'
import { CodeBlock } from './Code'

import type { RawPart } from '../sources'
import type { JSX, MouseEvent } from 'react'

export function Braces(): JSX.Element {
  return (
    <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M8 4H7a2 2 0 0 0-2 2v4a2 2 0 0 1-2 2 2 2 0 0 1 2 2v4a2 2 0 0 0 2 2h1M16 4h1a2 2 0 0 1 2 2v4a2 2 0 0 0 2 2 2 2 0 0 0-2 2v4a2 2 0 0 1-2 2h-1" />
    </svg>
  )
}

/* Inside a <summary> a click would also open or close the part; the switch keeps its clicks to itself. */
const own = (event: MouseEvent, then: () => void) => {
  event.preventDefault()
  event.stopPropagation()
  then()
}

export function ShowAs({ raw, onRaw, name, float = false }: { raw: boolean; onRaw: (raw: boolean) => void; name: string; float?: boolean }): JSX.Element {
  return (
    <span className={`showas${float ? ' float' : ''}`} role="group" aria-label={`Show the ${name} as`}>
      <button type="button" aria-pressed={!raw} onClick={(event) => own(event, () => onRaw(false))}>rendered</button>
      <button type="button" className="raw" aria-pressed={raw} title={`The ${name} as the record keeps it`} onClick={(event) => own(event, () => onRaw(true))}><Braces />raw</button>
    </span>
  )
}

/** A part's switch state and the switch itself, to place where the part wants it. */
export function useShowAs(name: string, float = false): [boolean, JSX.Element] {
  const [raw, setRaw] = useState(false)
  return [raw, <ShowAs raw={raw} onRaw={setRaw} name={name} float={float} />]
}

function Slice({ part }: { part: RawPart }): JSX.Element {
  if (part.as === 'prose') return typeof part.value === 'string' && part.value ? <CodeBlock text={part.value} prose /> : <p className="dim small">empty</p>
  if (part.as === 'code') return <CodeBlock text={String(part.value ?? '')} path={part.file} />
  return <CodeBlock text={JSON.stringify(part.value ?? null, null, 2)} language="json" />
}

export function RawPanel({ file, parts }: { file?: string; parts: RawPart[] }): JSX.Element {
  return (
    <div className="rawpanel">
      <p className="rp-hd"><Braces /><span>raw</span><span className="rp-src">{file ? <>from <code>{file}</code></> : 'from the run record'}</span></p>
      {parts.length ? parts.map((part, i) => (
        <section key={i} className="rp-part">
          {part.folded ? (
            <Fold className="rp-fold" summary={<><span className="rp-path">{part.path}</span><span className="dim">imported module</span></>}>{() => <Slice part={part} />}</Fold>
          ) : (
            <>
              <p className="rp-path">{part.path}</p>
              <Slice part={part} />
            </>
          )}
        </section>
      )) : <p className="dim small">The record holds nothing behind this part.</p>}
    </div>
  )
}
