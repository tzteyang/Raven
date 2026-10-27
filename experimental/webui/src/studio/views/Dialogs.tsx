/* The dialogs of a live session: start one (its name and the task the
   employee is hired on, or a saved version to start from, over the settings
   the server's live configuration fixes, with the employee and the model roles
   on models of the services registered here when the person picks them), pick
   the scenario's scripts to play as trials, and archive the current agent
   under a name. */

import { useState } from 'react'

import { deleteEndpoint, deleteSearch, saveEndpoint, saveSearch, testEndpoint, testSearch } from '../api'
import { T } from '../copy'

import type { JSX } from 'react'
import type { EndpointProbe, LiveEndpoint, LiveInfo, LiveScenario, LiveScript, LiveSearch, ModelChoice, ScenarioDraft } from '../api'

export interface NewSessionInput {
  title: string
  task: string
  version?: string
  /** A scenario built on the page; absent for the configured one. */
  scenario?: string
  /** The employee (`partner`) and the model roles put on a registered service's model; a role not named keeps the
      configured one. */
  models?: Record<string, ModelChoice>
}

const lines = (text: string): string[] => text.split('\n').map((line) => line.trim()).filter(Boolean)

/** The roles a new session may put on a service's model, the employee first (live.py's ENDPOINT_ROLES). */
const MODEL_ROLES = ['partner', 'curator', 'attribution', 'analyst', 'assessor'] as const
const EFFORTS = ['low', 'medium', 'high'] as const
/** The wire protocols a service may speak, by the names their vendors give them. */
const PROTOCOLS: Record<string, string> = { chat: 'OpenAI Chat Completions', responses: 'OpenAI Responses', anthropic: 'Anthropic Messages' }

/* The model services registered on the page: each an address, a key the page never sees whole, the wire protocol and
   the model names it serves, with one test request to see its first model answer. */
function Endpoints({ endpoints, onChange }: { endpoints: LiveEndpoint[]; onChange: (endpoints: LiveEndpoint[]) => void }): JSX.Element {
  const blank = { name: '', base: '', key: '', protocol: 'chat', models: '' }
  const [form, setForm] = useState(blank)
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [probes, setProbes] = useState<Record<string, EndpointProbe | 'busy'>>({})
  const field = (key: keyof typeof blank) => (event: { target: { value: string } }) => setForm({ ...form, [key]: event.target.value })
  const reset = () => {
    setForm(blank)
    setEditing(false)
  }
  const ready = !!form.name.trim() && !!form.base.trim() && (editing || !!form.key.trim()) && !busy
  const save = () => {
    setBusy(true)
    setError(null)
    saveEndpoint({
      name: form.name.trim(),
      base: form.base.trim(),
      protocol: form.protocol,
      models: form.models.split(/[\n,]/).map((name) => name.trim()).filter(Boolean),
      ...(form.key.trim() ? { key: form.key.trim() } : {}),
    }).then(
      (reply) => {
        onChange(reply.endpoints)
        setProbes(({ [form.name.trim()]: _stale, ...rest }) => rest)
        reset()
        setBusy(false)
      },
      (failure: Error) => {
        setError(failure.message)
        setBusy(false)
      },
    )
  }
  const remove = (name: string) => {
    if (!window.confirm(T.endpointDeleteAsk(name))) return
    setError(null)
    deleteEndpoint(name).then(
      (reply) => {
        onChange(reply.endpoints)
        if (editing && form.name === name) reset()
      },
      (failure: Error) => setError(failure.message),
    )
  }
  const probe = (name: string) => {
    setProbes((known) => ({ ...known, [name]: 'busy' }))
    testEndpoint(name).then(
      (result) => setProbes((known) => ({ ...known, [name]: result })),
      (failure: Error) => setProbes((known) => ({ ...known, [name]: { ok: false, seconds: 0, error: failure.message } })),
    )
  }
  return (
    <div className="st-build">
      <h3>{T.endpointsTitle}</h3>
      <p className="st-meta">{T.endpointsNote}</p>
      {endpoints.length === 0 && <p className="st-meta">{T.endpointsNone}</p>}
      {endpoints.map((endpoint) => {
        const result = probes[endpoint.name]
        return (
          <div key={endpoint.name} className="st-endpoint">
            <div className="st-endpoint-head">
              <b>{endpoint.name}</b>
              <span className="st-meta grow">{`${endpoint.base} · ${PROTOCOLS[endpoint.protocol] ?? endpoint.protocol} · ${T.endpointKeyTail(endpoint.key)}`}</span>
              <button type="button" className="st-btn" disabled={result === 'busy'} onClick={() => probe(endpoint.name)}>
                {result === 'busy' ? T.endpointTesting : T.endpointTest}
              </button>
              <button
                type="button"
                className="st-btn"
                onClick={() => {
                  setForm({ name: endpoint.name, base: endpoint.base, key: '', protocol: endpoint.protocol, models: endpoint.models.join('\n') })
                  setEditing(true)
                  setError(null)
                }}
              >
                {T.endpointEdit}
              </button>
              <button type="button" className="st-btn" onClick={() => remove(endpoint.name)}>{T.endpointDelete}</button>
            </div>
            <span className="st-meta">{endpoint.models.join(', ') || T.endpointNoModels}</span>
            {result && result !== 'busy' && (
              <p className={result.ok ? 'st-good' : 'st-bad'}>
                {result.ok ? T.endpointOk(endpoint.models[0] ?? '', result.seconds, result.reply ?? '') : T.endpointFailed(result.error ?? '')}
              </p>
            )}
          </div>
        )
      })}
      <h3>{editing ? T.endpointEditing(form.name) : T.endpointAdd}</h3>
      <label className="st-field">
        <span>{T.endpointName}</span>
        <input value={form.name} readOnly={editing} maxLength={40} placeholder="my-gateway" onChange={field('name')} />
      </label>
      <label className="st-field">
        <span>{T.endpointBase}</span>
        <input value={form.base} placeholder="https://api.example.com/v1" onChange={field('base')} />
      </label>
      <label className="st-field">
        <span>{T.endpointKey}</span>
        <input type="password" autoComplete="off" value={form.key} placeholder={editing ? T.endpointKeyKeep : ''} onChange={field('key')} />
      </label>
      <label className="st-field">
        <span>{T.endpointProtocol}</span>
        <select value={form.protocol} onChange={field('protocol')}>
          {Object.entries(PROTOCOLS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <label className="st-field">
        <span>{T.endpointModels}</span>
        <textarea rows={3} value={form.models} placeholder="gpt-5.1" onChange={field('models')} />
      </label>
      {error && <p className="st-bad">{T.endpointError(error)}</p>}
      <div className="st-acts-row">
        {editing && <button type="button" className="st-btn" onClick={reset}>{T.endpointCancelEdit}</button>}
        <button type="button" className="st-btn primary" disabled={!ready} onClick={save}>{T.endpointSave}</button>
      </div>
    </div>
  )
}

/* The web search service every session's employee and its research colleague search with: one vendor and its key,
   with one real search to see it answer. */
function SearchSetting({ vendors, service, onChange }: {
  vendors: string[]
  service: LiveSearch | null
  onChange: (service: LiveSearch | null) => void
}): JSX.Element {
  const [provider, setProvider] = useState(service?.provider ?? vendors[0] ?? 'serper')
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [probe, setProbe] = useState<EndpointProbe | 'busy' | null>(null)
  const settle = (call: Promise<{ search: LiveSearch | null }>) => {
    setBusy(true)
    setError(null)
    setProbe(null)
    call.then(
      (reply) => {
        onChange(reply.search)
        setKey('')
        setBusy(false)
      },
      (failure: Error) => {
        setError(failure.message)
        setBusy(false)
      },
    )
  }
  return (
    <div className="st-build">
      <h3>{T.searchTitle}</h3>
      <p className="st-meta">{T.searchNote}</p>
      {service && (
        <div className="st-endpoint">
          <div className="st-endpoint-head">
            <b>{service.provider}</b>
            <span className="st-meta grow">{T.endpointKeyTail(service.key)}</span>
            <button
              type="button"
              className="st-btn"
              disabled={probe === 'busy'}
              onClick={() => {
                setProbe('busy')
                testSearch().then(setProbe, (failure: Error) => setProbe({ ok: false, seconds: 0, error: failure.message }))
              }}
            >
              {probe === 'busy' ? T.endpointTesting : T.searchTest}
            </button>
            <button type="button" className="st-btn" onClick={() => window.confirm(T.searchDeleteAsk) && settle(deleteSearch())}>
              {T.searchDelete}
            </button>
          </div>
          {probe && probe !== 'busy' && (
            <p className={probe.ok ? 'st-good' : 'st-bad'}>
              {probe.ok ? T.endpointOk(service.provider, probe.seconds, probe.reply ?? '') : T.endpointFailed(probe.error ?? '')}
            </p>
          )}
        </div>
      )}
      <div className="st-search-row">
        <label className="st-field">
          <span>{T.searchProvider}</span>
          <select value={provider} onChange={(event) => setProvider(event.target.value)}>
            {vendors.map((vendor) => <option key={vendor} value={vendor}>{vendor}</option>)}
          </select>
        </label>
        <label className="st-field">
          <span>{T.searchKey}</span>
          <input
            type="password"
            autoComplete="off"
            value={key}
            placeholder={service?.provider === provider ? T.endpointKeyKeep : ''}
            onChange={(event) => setKey(event.target.value)}
          />
        </label>
      </div>
      {error && <p className="st-bad">{T.endpointError(error)}</p>}
      <div className="st-acts-row">
        <button type="button" className="st-btn primary" disabled={busy || !key.trim()} onClick={() => settle(saveSearch(provider, key.trim()))}>
          {T.searchSave}
        </button>
      </div>
    </div>
  )
}

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
  const [endpoints, setEndpoints] = useState(info.endpoints ?? [])
  const [search, setSearch] = useState(info.search?.service ?? null)
  const [models, setModels] = useState<Record<string, ModelChoice>>({})
  const [managing, setManaging] = useState(false)
  const choose = (role: string, choice: ModelChoice | null) => {
    const { [role]: _gone, ...rest } = models
    setModels(choice ? { ...rest, [role]: choice } : rest)
  }
  const unnamed = Object.values(models).some((choice) => !choice.model.trim())
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
  if (managing) {
    return (
      <div className="st-veil" role="presentation">
        <div className="st-dialog st-dialog-wide" role="dialog" aria-label={T.servicesTitle}>
          <Endpoints
            endpoints={endpoints}
            onChange={(next) => {
              setEndpoints(next)
              setModels(Object.fromEntries(Object.entries(models).filter(([, choice]) => next.some((item) => item.name === choice.endpoint))))
            }}
          />
          {info.search && <SearchSetting vendors={info.search.vendors} service={search} onChange={setSearch} />}
          <div className="st-acts-row">
            <button type="button" className="st-btn" onClick={() => setManaging(false)}>{T.endpointBack}</button>
          </div>
        </div>
      </div>
    )
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
        className="st-dialog st-dialog-wide"
        role="dialog"
        aria-label={T.newTitle}
        onSubmit={(event) => {
          event.preventDefault()
          if (!task.trim() || busy || unnamed) return
          setBusy(true)
          onCreate({
            title: title.trim() || T.titleFrom(task),
            task: task.trim(),
            ...(version ? { version } : {}),
            ...(picked?.built ? { scenario: picked.name } : {}),
            ...(Object.keys(models).length
              ? { models: Object.fromEntries(Object.entries(models).map(([role, choice]) => [role, { ...choice, model: choice.model.trim() }])) }
              : {}),
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
        {info.endpoints && (
          <div className="st-field st-models">
            <div className="st-scenario-row">
              <span className="grow">{T.newModels}</span>
              <button type="button" className="st-btn" onClick={() => setManaging(true)}>{T.newModelsManage}</button>
            </div>
            {endpoints.length === 0 && <p className="st-meta">{T.newModelsNone}</p>}
            {endpoints.length > 0 &&
              MODEL_ROLES.map((role) => {
                const choice = models[role]
                const served = endpoints.find((item) => item.name === choice?.endpoint)?.models ?? []
                const label = T.modelRoles[role]
                return (
                  <div key={role} className="st-model-row">
                    <span>{label}</span>
                    <select
                      aria-label={`${label} · ${T.modelEndpoint}`}
                      value={choice?.endpoint ?? ''}
                      onChange={(event) => {
                        const next = endpoints.find((item) => item.name === event.target.value)
                        choose(role, next ? { endpoint: next.name, model: next.models[0] ?? '', ...(choice?.effort ? { effort: choice.effort } : {}) } : null)
                      }}
                    >
                      <option value="">{role === 'partner' ? T.modelKept : T.modelKeptOf(info.roles?.[role] ?? T.curatorDefault)}</option>
                      {endpoints.map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}
                    </select>
                    {choice && (
                      <>
                        <input
                          list={`st-served-${role}`}
                          value={choice.model}
                          placeholder={T.modelName}
                          aria-label={`${label} · ${T.modelName}`}
                          onChange={(event) => choose(role, { ...choice, model: event.target.value })}
                        />
                        <datalist id={`st-served-${role}`}>{served.map((name) => <option key={name} value={name} />)}</datalist>
                        <select
                          aria-label={`${label} · ${T.modelEffort}`}
                          value={choice.effort ?? ''}
                          onChange={(event) => {
                            const { effort: _old, ...rest } = choice
                            choose(role, event.target.value ? { ...rest, effort: event.target.value } : rest)
                          }}
                        >
                          <option value="">{T.modelEffortKept}</option>
                          {EFFORTS.map((effort) => <option key={effort} value={effort}>{T.efforts[effort]}</option>)}
                        </select>
                      </>
                    )}
                  </div>
                )
              })}
            {info.search && <p className="st-meta">{search ? T.newSearch(search.provider) : T.newSearchNone}</p>}
          </div>
        )}
        <p className="st-meta">{T.newSettings(picked?.title ?? info.scenario, models.curator?.model || info.settings.curator, info.settings.rounds)}</p>
        {error && <p className="st-bad">{T.newFailed(error)}</p>}
        <div className="st-acts-row">
          <button type="button" className="st-btn" onClick={onCancel}>{T.cancel}</button>
          <button type="submit" className="st-btn primary" disabled={!task.trim() || unnamed || (busy && !error)}>{T.create}</button>
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
