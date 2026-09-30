/* Materials the owner handed over with a message: one row per material in
   the owner's bubble, its kind and its files as chips, and, for the file the
   reader opens, its text or its deck pages in a card below. Only files under
   the run's home/uploads are served. */

import { useEffect, useState } from 'react'

import { fileUrl, loadText, uploadThumbsUrl, uploadUrl } from '../api'
import { fileName } from '../derive'
import { Markdown } from './Markdown'
import { useThumbs } from './Trials'

import type { Handover, MaterialOrigin } from '../model'
import type { JSX } from 'react'

export type AttachmentKind = 'text' | 'deck' | 'other'

export function attachmentKind(path: string): AttachmentKind {
  if (/\.(md|markdown|txt|csv|json|ya?ml)$/i.test(path)) return 'text'
  if (/\.(pptx|ppt|odp|pdf)$/i.test(path)) return 'deck'
  return 'other'
}

/** Only files the server's upload endpoint can reach are openable. */
export const openable = (path: string): boolean => path.startsWith('uploads/') && attachmentKind(path) !== 'other'

/** A material's files as the reader tells them apart: the path under the material's own folder. */
const inside = (item: Handover, path: string): string => path.split(`uploads/${item.name}/`)[1] ?? fileName(path)

const ORIGIN_HINT = (origin: MaterialOrigin): string =>
  `${origin.origin === 'researched' ? 'Researched before the cultivation' : 'Induced before the cultivation from what the party handed over'}${origin.items.length ? ` (${origin.items.join(', ')})` : ''}; ${origin.confirmed ? 'the party confirmed it' : 'the party has not confirmed it, so no one judges by it'}`

export function AttachmentChips({
  materials, open, onOpen, origins = {},
}: { materials: Handover[]; open: string | null; onOpen: (path: string | null) => void; origins?: Record<string, MaterialOrigin> }): JSX.Element | null {
  if (!materials.length) return null
  return (
    <div className="mats att">
      {materials.map((item) => (
        <p key={item.name} className="att-row">
          <span className="k">Attached</span>
          <b className="att-name">{item.name}</b>
          <span className={`att-kind ${item.kind}`}>{item.kind}</span>
          {origins[item.name] && origins[item.name].origin !== 'given' ? (
            <span className={`att-origin${origins[item.name].confirmed ? '' : ' open'}`} title={ORIGIN_HINT(origins[item.name])}>
              {origins[item.name].origin} · {origins[item.name].confirmed ? 'confirmed' : 'unconfirmed'}
            </span>
          ) : null}
          {item.files.map((path) =>
            openable(path) ? (
              <button
                key={path}
                className={`att-chip ${attachmentKind(path)}${open === path ? ' on' : ''}`}
                title={path}
                aria-expanded={open === path}
                onClick={() => onOpen(open === path ? null : path)}
              >
                {inside(item, path)}
              </button>
            ) : (
              <code key={path} title={`${path}: not viewable here`}>{inside(item, path)}</code>
            ),
          )}
          {item.files.length === 0 ? <span className="dim">no files</span> : null}
        </p>
      ))}
    </div>
  )
}

function Text({ url, markdown }: { url: string; markdown: boolean }): JSX.Element {
  const [text, setText] = useState<string | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let live = true
    setText(null)
    setError('')
    loadText(url).then((body) => { if (live) setText(body) }).catch((e: Error) => { if (live) setError(e.message) })
    return () => { live = false }
  }, [url])
  if (error) return <p className="bad">Could not open the file: {error}</p>
  if (text === null) return <p className="quiet">Opening...</p>
  return markdown ? <Markdown text={text} /> : <pre>{text}</pre>
}

function Deck({ run, path }: { run: string; path: string }): JSX.Element {
  const thumbs = useThumbs(uploadThumbsUrl(run, path))
  if (thumbs.loading) return <p className="quiet">Rendering pages...</p>
  if (thumbs.error) return <p className="bad" title={thumbs.error}>Thumbnails unavailable.</p>
  return (
    <div className="att-pages">
      {thumbs.pages.map((page, i) => (
        <figure key={page}>
          <img src={fileUrl(page)} alt={`${fileName(path)} page ${i + 1}`} loading="lazy" />
          <figcaption>{i + 1}</figcaption>
        </figure>
      ))}
    </div>
  )
}

export function AttachmentView({ run, path, onClose }: { run: string; path: string | null; onClose: () => void }): JSX.Element | null {
  if (!path) return null
  const kind = attachmentKind(path)
  return (
    <div className="att-view">
      <div className="att-hd">
        <code>{path}</code>
        <a href={uploadUrl(run, path)} target="_blank" rel="noreferrer">open raw</a>
        <button className="link" onClick={onClose}>close</button>
      </div>
      {kind === 'deck' ? <Deck run={run} path={path} /> : <Text url={uploadUrl(run, path)} markdown={/\.(md|markdown)$/i.test(path)} />}
    </div>
  )
}
