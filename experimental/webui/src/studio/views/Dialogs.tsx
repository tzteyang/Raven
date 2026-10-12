/* The dialogs of a live session: start one (its name and the task the
   employee is hired on, or a saved version to start from, over the settings
   the server's live configuration fixes), pick the scenario's scripts to play
   as trials, and archive the current agent under a name. */

import { useState } from 'react'

import { T } from '../copy'

import type { JSX } from 'react'
import type { LiveInfo, LiveScenario, LiveScript, ScenarioDraft } from '../api'

export interface NewSessionInput {
  title: string
  task: string
  version?: string
  /** A scenario built on the page; absent for the configured one. */
  scenario?: string
}

const lines = (text: string): string[] => text.split('\n').map((line) => line.trim()).filter(Boolean)

/* A scenario built from what the person gives: a name, the job in their words, text files handed over, the requests to
   practise on and those kept for the exam, and the checks the work is judged by, each one per line. */
function BuildScenario({ onBuild, onBuilt, onCancel }: {
  onBuild: (draft: ScenarioDraft) => Promise<LiveScenario>
  onBuilt: (built: LiveScenario) => void
  onCancel: () => void
}): JSX.Element {
  const [title, setTitle] = useState('')
  const [profile, setProfile] = useState('')
  const [files, setFiles] = useState<{ name: string; text: string }[]>([])
  const [practice, setPractice] = useState('')
  const [exam, setExam] = useState('')
  const [checks, setChecks] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const ready = !!title.trim() && !!profile.trim() && !busy
  return (
    <div className="st-build">
      <h3>{T.buildTitle}</h3>
      <label className="st-field">
        <span>{T.buildName}</span>
        <input value={title} maxLength={80} onChange={(event) => setTitle(event.target.value)} />
      </label>
      <label className="st-field">
        <span>{T.buildProfile}</span>
        <textarea rows={5} value={profile} placeholder={T.buildProfileHint} onChange={(event) => setProfile(event.target.value)} />
      </label>
      <label className="st-field">
        <span>{T.buildFiles}</span>
        <input
          type="file"
          multiple
          accept=".md,.txt,.csv"
          onChange={async (event) => setFiles(await Promise.all([...(event.target.files ?? [])].map(async (file) => ({ name: file.name, text: await file.text() }))))}
        />
      </label>
      {files.length > 0 && <p className="st-meta">{T.buildFilesPicked(files.map((file) => file.name).join(', '))}</p>}
      <label className="st-field">
        <span>{T.buildPractice}</span>
        <textarea rows={4} value={practice} onChange={(event) => setPractice(event.target.value)} />
      </label>
      <label className="st-field">
        <span>{T.buildExam}</span>
        <textarea rows={3} value={exam} onChange={(event) => setExam(event.target.value)} />
      </label>
      <label className="st-field">
        <span>{T.buildChecks}</span>
        <textarea rows={3} value={checks} onChange={(event) => setChecks(event.target.value)} />
      </label>
      {error && <p className="st-bad">{T.buildFailed(error)}</p>}
      <div className="st-acts-row">
        <button type="button" className="st-btn" onClick={onCancel}>{T.cancel}</button>
        <button
          type="button"
          className="st-btn primary"
          disabled={!ready}
          onClick={() => {
            setBusy(true)
            setError(null)
            onBuild({ title: title.trim(), profile: profile.trim(), files, practice: lines(practice), exam: lines(exam), checks: lines(checks) }).then(
              onBuilt,
              (failure: Error) => {
                setError(failure.message)
                setBusy(false)
              },
            )
          }}
        >
          {T.buildDo}
        </button>
      </div>
    </div>
  )
}

export function NewSessionDialog({ info, error, onCreate, onBuild, onCancel }: {
  info: LiveInfo
  error: string | null
  onCreate: (input: NewSessionInput) => void
  /** Build a scenario on the page; absent where scenarios cannot be built. */
  onBuild?: (draft: ScenarioDraft) => Promise<LiveScenario>
  onCancel: () => void
}): JSX.Element {
  const [written, setTask] = useState(info.task)
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [version, setVersion] = useState('')
  const [building, setBuilding] = useState(false)
  const [extra, setExtra] = useState<LiveScenario[]>([])
  const offered = [...(info.scenarios ?? []), ...extra.filter((item) => !(info.scenarios ?? []).some((known) => known.name === item.name))]
  const [scenario, setScenario] = useState(info.scenario)
  const picked = offered.find((item) => item.name === scenario)
  const versions = info.versions ?? []
  const task = versions.find((item) => item.name === version)?.task ?? written
  const pick = (name: string) => {
    setScenario(name)
    const chosen = offered.find((item) => item.name === name)
    if (chosen) setTask(chosen.task)
  }
  if (building && onBuild) {
    return (
      <div className="st-veil" role="presentation">
        <div className="st-dialog st-dialog-wide" role="dialog" aria-label={T.buildTitle}>
          <BuildScenario
            onBuild={onBuild}
            onBuilt={(built) => {
              setExtra([...extra, built])
              setScenario(built.name)
              setTask(built.task)
              setBuilding(false)
            }}
            onCancel={() => setBuilding(false)}
          />
        </div>
      </div>
    )
  }
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
          onCreate({
            title: title.trim() || T.titleFrom(task),
            task: task.trim(),
            ...(version ? { version } : {}),
            ...(picked?.built ? { scenario: picked.name } : {}),
          })
        }}
      >
        <h3>{T.newTitle}</h3>
        <label className="st-field">
          <span>{T.newName}</span>
          <input value={title} placeholder={T.titleFrom(task)} onChange={(event) => setTitle(event.target.value)} />
        </label>
        {offered.length > 0 && (offered.length > 1 || onBuild) && (
          <div className="st-field">
            <span>{T.newScenario}</span>
            <div className="st-scenario-row">
              <select value={scenario} aria-label={T.newScenario} onChange={(event) => pick(event.target.value)}>
                {offered.map((item) => <option key={item.name} value={item.name}>{item.title}</option>)}
              </select>
              {onBuild && <button type="button" className="st-btn" onClick={() => setBuilding(true)}>{T.newScenarioBuild}</button>}
            </div>
          </div>
        )}
        {versions.length > 0 && (
          <label className="st-field">
            <span>{T.newFrom}</span>
            <select value={version} onChange={(event) => setVersion(event.target.value)}>
              <option value="">{T.newFromPlain}</option>
              {versions.map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}
            </select>
          </label>
        )}
        <label className="st-field">
          <span>{version ? T.newFromTask : T.newTask}</span>
          <textarea rows={6} value={task} readOnly={!!version} placeholder={T.newTaskPlaceholder} onChange={(event) => setTask(event.target.value)} />
        </label>
        <p className="st-meta">{T.newSettings(picked?.title ?? info.scenario, info.settings.curator, info.settings.rounds)}</p>
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

export function ScriptsDialog({ scripts, onPlay, onCancel }: { scripts: LiveScript[]; onPlay: (names: string[]) => void; onCancel: () => void }): JSX.Element {
  const [picked, setPicked] = useState<string[]>([])
  const toggle = (name: string) => setPicked(picked.includes(name) ? picked.filter((item) => item !== name) : [...picked, name])
  return (
    <div className="st-veil" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onCancel()}>
      <form
        className="st-dialog"
        role="dialog"
        aria-label={T.scriptsTitle}
        onSubmit={(event) => {
          event.preventDefault()
          if (picked.length) onPlay(picked)
        }}
      >
        <h3>{T.scriptsTitle}</h3>
        <p className="st-meta">{T.scriptsNote}</p>
        <div className="st-scripts">
          {scripts.map((script) => (
            <label key={script.name} className="st-pickrow">
              <input type="checkbox" checked={picked.includes(script.name)} onChange={() => toggle(script.name)} />
              <span>{script.title}</span>
              <small>{T.scriptSteps(script.steps)}</small>
            </label>
          ))}
        </div>
        <div className="st-acts-row">
          <button type="button" className="st-btn" onClick={onCancel}>{T.cancel}</button>
          <button type="submit" className="st-btn primary" disabled={!picked.length}>{T.playN(picked.length)}</button>
        </div>
      </form>
    </div>
  )
}
