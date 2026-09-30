/* Small pieces every Studio view uses: the stroke icons (drawn like ui-web's,
   16px on a 24 grid), Markdown in ui-web's prose style, a strategy target
   tag, a diagnosis state chip, a handed-over material, a JSON block, and the
   Raven mark. */

import { useId } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { T } from '../copy'
import { LOOSE, surfaceOf } from '../harness'

import type { JSX, ReactNode } from 'react'
import type { Handover, MaterialOrigin } from '../../model'

const PATHS: Record<string, string> = {
  plus: 'M12 5v14M5 12h14',
  clip: 'M21 11.5 12.6 19.9a5.5 5.5 0 0 1-7.8-7.8l8.5-8.5a3.7 3.7 0 0 1 5.2 5.2l-8.5 8.5a1.8 1.8 0 0 1-2.6-2.6l7.8-7.8',
  up: 'M12 19V5M5 12l7-7 7 7',
  flask: 'M9 3h6M10 3v6L4.5 18.5A1.8 1.8 0 0 0 6 21h12a1.8 1.8 0 0 0 1.5-2.5L14 9V3M7 15h10',
  x: 'M6 6l12 12M18 6 6 18',
  expand: 'M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7',
  shrink: 'M4 14h6v6M20 10h-6V4M14 10l7-7M3 21l7-7',
  eye: 'M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
  archive: 'M3 4h18v4H3zM5 8v12h14V8M10 12h4',
  check: 'M5 12.5 10 17l9-10',
  chevron: 'M9 6l6 6-6 6',
  down: 'M6 9l6 6 6-6',
  file: 'M14 3H6v18h12V7zM14 3v4h4',
  tool: 'M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-.6-.6-2.4z',
  shield: 'M12 3 4 6v6c0 5 3.4 8.3 8 9 4.6-.7 8-4 8-9V6z',
  graph: 'M6 5h4v4H6zM14 15h4v4h-4zM6 15h4v4H6zM8 9v6M10 17h4M8 9l8 6',
  spark: 'M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6',
  chat: 'M4 5h16v11H9l-5 4z',
  cpu: 'M7 7h10v10H7zM10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4',
  layers: 'M12 3 3 8l9 5 9-5zM3 13l9 5 9-5',
  link: 'M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1',
  alert: 'M12 3 2 20h20zM12 10v4M12 17v.5',
  braces: 'M8 4H7a2 2 0 0 0-2 2v4a2 2 0 0 1-2 2 2 2 0 0 1 2 2v4a2 2 0 0 0 2 2h1M16 4h1a2 2 0 0 1 2 2v4a2 2 0 0 0 2 2 2 2 0 0 0-2 2v4a2 2 0 0 1-2 2h-1',
  book: 'M5 4h9a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3zM17 20h2V6',
}

export function Icon({ name, size = 16, className }: { name: keyof typeof PATHS | string; size?: number; className?: string }): JSX.Element {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name] ?? PATHS.spark} />
    </svg>
  )
}

/* ui-web/src/components/RavenMark.tsx, redrawn here so the island does not
   import a second copy of React from ui-web's own node_modules. */
export function RavenMark({ size = 22 }: { size?: number }): JSX.Element {
  const id = 'st' + useId().replace(/[^\w-]/g, '')
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id={`${id}g`} x1="0" y1="0" x2="24" y2="24" gradientUnits="userSpaceOnUse">
          <stop stopColor="#dfe7f5" />
          <stop offset="1" stopColor="#f6ecd6" />
        </linearGradient>
        <clipPath id={`${id}c`}>
          <rect width="24" height="24" rx="6.46" />
        </clipPath>
      </defs>
      <g clipPath={`url(#${id}c)`}>
        <rect width="24" height="24" rx="6.46" fill={`url(#${id}g)`} />
        <rect x="3" y="8.42" width="18.34" height="16.93" rx="4.23" fill="black" />
        <path d="M13.03 2.78c.92 1.02 1.5 2.48 1.52 4.1.53-.76.92-1.62 1.16-2.55.87.91 1.42 2.25 1.42 3.75l-.01.35H8.65c2.17-.82 3.85-2.97 4.38-5.65z" fill="black" />
        <circle cx="9.26" cy="13.27" r="3.43" fill="white" />
        <circle cx="8.95" cy="12.97" r="1.72" fill="black" />
        <circle cx="17.72" cy="13.27" r="3.43" fill="white" />
        <circle cx="17.42" cy="12.97" r="1.72" fill="black" />
      </g>
    </svg>
  )
}

export function Markdown({ text, className = '' }: { text: string; className?: string }): JSX.Element {
  return (
    <div className={`prose st-md ${className}`.trim()}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer">{children}</a>,
          table: ({ children }) => <div className="tw"><table>{children}</table></div>,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}

/** A strategy target, marked with its strategy; the artifact's supporting files read as such. */
export function Target({ name, onClick }: { name: string; onClick?: () => void }): JSX.Element {
  const surface = surfaceOf(name)
  const body = (
    <>
      <i className="st-sd" data-surface={surface} />
      <span>{name === LOOSE ? T.looseFiles : name}</span>
      <em>{T.surfaces[surface]}</em>
    </>
  )
  return onClick ? (
    <button type="button" className="st-target" data-surface={surface} onClick={onClick}>{body}</button>
  ) : (
    <span className="st-target" data-surface={surface}>{body}</span>
  )
}

/** A diagnosis state from the attribution's closed set. */
export function StateChip({ state }: { state: string | null | undefined }): JSX.Element {
  return (
    <span className="st-state" data-state={state ?? 'none'} title={state ? T.stateHints[state] ?? state : ''}>
      {state ? T.states[state] ?? state : '—'}
    </span>
  )
}

/** A material handed over with a request: its kind in the scenario's terms, its name and how many files it holds. */
export function HandoverChip({ material, origin, children }: { material: Handover; origin?: MaterialOrigin; children?: ReactNode }): JSX.Element {
  return (
    <span className="wchip st-handover" title={material.files.join('\n')}>
      <Icon name="file" size={13} />
      <em data-kind={material.kind}>{T.kinds[material.kind] ?? material.kind}</em>
      <span>{material.name}</span>
      {origin && origin.origin !== 'given' && (
        <small className="st-origin" data-confirmed={origin.confirmed} title={T.originHint(origin.origin, origin.items, origin.confirmed)}>{T.originMark(origin.origin, origin.confirmed)}</small>
      )}
      <small>{T.materialFiles(material.files.length)}</small>
      {children}
    </span>
  )
}

export function Json({ value, max }: { value: unknown; max?: number }): JSX.Element {
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2)
  return <pre className="st-json" style={max ? { maxHeight: max } : undefined}>{text}</pre>
}

export function Fold({ summary, children, open = false }: { summary: ReactNode; children: ReactNode; open?: boolean }): JSX.Element {
  return (
    <details className="st-fold" open={open}>
      <summary><Icon name="chevron" size={12} className="st-car" />{summary}</summary>
      <div className="st-fold-b">{children}</div>
    </details>
  )
}

export const fileName = (path: string): string => path.split('/').pop() ?? path
