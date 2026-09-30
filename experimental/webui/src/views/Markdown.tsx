/* Model-written text (replies, remarks, requirements, plans) rendered as Markdown with tables.
   Raw HTML in the text is shown as text, never rendered; links open outside the page. */

import type { JSX } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export function Markdown({ text, className = '' }: { text: string; className?: string }): JSX.Element {
  return (
    <div className={`md ${className}`.trim()}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer">{children}</a>,
          table: ({ children }) => <div className="md-table"><table>{children}</table></div>,
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}
