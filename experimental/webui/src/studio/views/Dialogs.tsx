/* The two dialogs of a live session: start one (its name and the task the
   employee is hired on, over the settings the server's live configuration
   fixes) and archive the current agent under a name. */

import { useState } from 'react'

import { T } from '../copy'

import type { JSX } from 'react'
import type { LiveInfo } from '../api'

export interface NewSessionInput {
  title: string
  task: string
}

export function NewSessionDialog({ info, error, onCreate, onCancel }: {
  info: LiveInfo
  error: string | null
  onCreate: (input: NewSessionInput) => void
  onCancel: () => void
}): JSX.Element {
  const [task, setTask] = useState(info.task)
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  return (
    <div className="st-veil" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onCancel()}>
      <form
        className="st-dialog"
        role="dialog"
        aria-label={T.newTitle}
        onSubmit={(event) => {
          event.preventDefault()
          if (!task.trim() || busy) return
          setBusy(true)
          onCreate({ title: title.trim() || T.titleFrom(task), task: task.trim() })
        }}
      >
        <h3>{T.newTitle}</h3>
        <label className="st-field">
          <span>{T.newName}</span>
          <input value={title} placeholder={T.titleFrom(task)} onChange={(event) => setTitle(event.target.value)} />
        </label>
        <label className="st-field">
          <span>{T.newTask}</span>
          <textarea rows={6} value={task} placeholder={T.newTaskPlaceholder} onChange={(event) => setTask(event.target.value)} />
        </label>
        <p className="st-meta">{T.newSettings(info.scenario, info.settings.curator, info.settings.rounds)}</p>
        {error && <p className="st-bad">{T.newFailed(error)}</p>}
        <div className="st-acts-row">
          <button type="button" className="st-btn" onClick={onCancel}>{T.cancel}</button>
          <button type="submit" className="st-btn primary" disabled={!task.trim() || (busy && !error)}>{T.create}</button>
        </div>
      </form>
    </div>
  )
}

export function ArchiveDialog({ version, suggestion, onArchive, onCancel }: { version: string; suggestion: string; onArchive: (name: string) => void; onCancel: () => void }): JSX.Element {
  const [name, setName] = useState(suggestion)
  return (
    <div className="st-veil" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onCancel()}>
      <form
        className="st-dialog"
        role="dialog"
        aria-label={T.archiveTitle}
        onSubmit={(event) => {
          event.preventDefault()
          if (name.trim()) onArchive(name.trim())
        }}
      >
        <h3>{T.archiveTitle}</h3>
        <p className="st-meta">{T.archiveBody(version)}</p>
        <label className="st-field">
          <span>{T.archiveName}</span>
          <input value={name} autoFocus onChange={(event) => setName(event.target.value)} />
        </label>
        <div className="st-acts-row">
          <button type="button" className="st-btn" onClick={onCancel}>{T.cancel}</button>
          <button type="submit" className="st-btn primary" disabled={!name.trim()}>{T.archiveDo}</button>
        </div>
      </form>
    </div>
  )
}
