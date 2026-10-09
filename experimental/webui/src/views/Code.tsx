/* Source shown the way a reader expects it: highlighted by its language, with line numbers, its path, language and
   length in a header and a copy button. The language comes from the path's extension, else from the text itself.
   Prose (a plan, an understanding) keeps its Markdown source, highlighted and wrapped, without line numbers. */

import hljs from 'highlight.js/lib/core'
import bash from 'highlight.js/lib/languages/bash'
import ini from 'highlight.js/lib/languages/ini'
import javascript from 'highlight.js/lib/languages/javascript'
import json from 'highlight.js/lib/languages/json'
import markdown from 'highlight.js/lib/languages/markdown'
import python from 'highlight.js/lib/languages/python'
import typescript from 'highlight.js/lib/languages/typescript'
import yaml from 'highlight.js/lib/languages/yaml'
import { useMemo, useState } from 'react'

import type { JSX, ReactNode } from 'react'

const GRAMMARS = { bash, ini, javascript, json, markdown, python, typescript, yaml }
for (const [name, grammar] of Object.entries(GRAMMARS)) hljs.registerLanguage(name, grammar)

const EXTENSIONS: Record<string, string> = {
  py: 'python', json: 'json', jsonl: 'json', md: 'markdown', yaml: 'yaml', yml: 'yaml', sh: 'bash',
  ts: 'typescript', tsx: 'typescript', js: 'javascript', mjs: 'javascript', toml: 'ini', ini: 'ini', cfg: 'ini',
}
const LABELS: Record<string, string> = {
  python: 'Python', json: 'JSON', markdown: 'Markdown', yaml: 'YAML', bash: 'Shell', typescript: 'TypeScript',
  javascript: 'JavaScript', ini: 'TOML', plaintext: 'text',
}
// Past this length highlighting costs the page more than it shows; the text stays plain.
const HIGHLIGHT_LIMIT = 300_000

export function languageOf(path: string | undefined, text: string): string {
  const name = path?.split('/').pop() ?? ''
  const extension = name.includes('.') ? name.split('.').pop()!.toLowerCase() : ''
  if (extension in EXTENSIONS) return EXTENSIONS[extension]
  if (path) return 'plaintext'
  if (/^\s*[[{]/.test(text)) {
    try {
      JSON.parse(text)
      return 'json'
    } catch {
      return 'plaintext'
    }
  }
  return 'plaintext'
}

const escape = (text: string): string => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

/** The text as highlighted HTML; highlight.js escapes what it does not mark, and plain text is escaped here. */
export function highlighted(text: string, language: string): string {
  if (language === 'plaintext' || text.length > HIGHLIGHT_LIMIT || !hljs.getLanguage(language)) return escape(text)
  return hljs.highlight(text, { language, ignoreIllegals: true }).value
}

/** Highlighted HTML split into lines, each closing the spans still open at its end and reopening them on the next,
    so a token that runs over several lines (a docstring) keeps its colour on every row. */
export function lines(html: string): string[] {
  const out: string[] = []
  let open: string[] = []
  for (const line of html.split('\n')) {
    const carried = open.join('')
    const next = [...open]
    for (const tag of line.matchAll(/<span[^>]*>|<\/span>/g)) {
      if (tag[0].startsWith('</')) next.pop()
      else next.push(tag[0])
    }
    out.push(carried + line + '</span>'.repeat(next.length))
    open = next
  }
  return out
}

export function copyText(text: string): Promise<void> {
  if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text)
  // A page served over plain HTTP from another machine has no clipboard API; a selected text area still copies.
  const area = document.createElement('textarea')
  area.value = text
  area.style.position = 'fixed'
  area.style.opacity = '0'
  document.body.appendChild(area)
  area.select()
  document.execCommand('copy')
  area.remove()
  return Promise.resolve()
}

/* `wrap` folds long lines inside the block and numbers each source line, the way a reader takes JSON whose strings
   carry sentences; code keeps its lines and scrolls sideways. JSON wraps unless told otherwise. */
export function CodeBlock({
  text, path, language, title, prose = false, wrap,
}: { text: string; path?: string; language?: string; title?: ReactNode; prose?: boolean; wrap?: boolean }): JSX.Element {
  const lang = language ?? (prose ? 'markdown' : languageOf(path, text))
  const html = useMemo(() => highlighted(text, lang), [text, lang])
  const rows = useMemo(() => (wrap ?? lang === 'json') && !prose ? lines(html.replace(/\n$/, '')) : null, [html, wrap, lang, prose])
  const count = text.replace(/\n$/, '').split('\n').length
  const [copied, setCopied] = useState(false)
  const copy = () => {
    void copyText(text).then(() => {
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1200)
    })
  }
  return (
    <figure className="codeblock" data-language={lang} data-prose={prose || undefined}>
      <figcaption>
        <span className="cb-title">{title ?? (path ? <code>{path}</code> : null)}</span>
        <span className="cb-lang">{LABELS[lang] ?? lang}</span>
        <span className="cb-lines">{count} line{count === 1 ? '' : 's'}</span>
        <button className="cb-copy" onClick={copy}>{copied ? 'copied' : 'copy'}</button>
      </figcaption>
      {rows ? (
        <div className="cb-body" data-wrap="">
          <pre className="cb-code"><code className={`hljs language-${lang}`}>
            {rows.map((row, i) => <span key={i} className="cb-row"><span className="cb-n" aria-hidden="true">{i + 1}</span><span className="cb-l" dangerouslySetInnerHTML={{ __html: row || ' ' }} /></span>)}
          </code></pre>
        </div>
      ) : (
        <div className="cb-body">
          {prose ? null : <pre className="cb-gutter" aria-hidden="true">{Array.from({ length: count }, (_, i) => i + 1).join('\n')}</pre>}
          <pre className="cb-code"><code className={`hljs language-${lang}`} dangerouslySetInnerHTML={{ __html: html }} /></pre>
        </div>
      )}
    </figure>
  )
}
