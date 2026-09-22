import { useSyncExternalStore } from 'react'

import { t } from '../../shell/bridge'
import * as store from './store'

import type { PersonaRow } from './types'
import type { JSX } from 'react'

/* One Persona. The card says what it is and who it can hand work to, and its
   only action starts a conversation on it -- there is no "preview" or "open",
   because a Persona is a thing to talk to and reading its fields is what the
   playbook page is for. */
function Card({ row }: { row: PersonaRow }): JSX.Element {
  const workers = row.workers || []
  return (
    <article className="card persona-card">
      <header>
        <h3>{row.name}</h3>
        {row.disabled ? <span className="chip muted">{t('gui.persona.disabled')}</span> : null}
      </header>
      <p className="desc">{row.description || t('gui.persona.no_description')}</p>
      {workers.length ? (
        <ul className="persona-workers">
          {workers.map(w => (
            <li key={w.label} className="chip" title={w.agent}>
              {w.label}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">{t('gui.persona.no_workers')}</p>
      )}
      <footer>
        <button className="primary" disabled={row.disabled} onClick={() => store.start(row.name)}>
          {t('gui.persona.start')}
        </button>
      </footer>
    </article>
  )
}

export function PersonaApp(): JSX.Element {
  const s = useSyncExternalStore(store.subscribe, store.getState)
  const rows = store.visible()

  if (s.err) return <p className="err">{s.err}</p>
  /* Not yet read is not the same as empty: one is a wait, the other is an
     answer, and drawing "no personas" during the read tells the reader
     something untrue for as long as the round trip takes. */
  if (s.rows === null) return <p className="muted">{t('gui.persona.loading')}</p>

  return (
    <>
      <div className="toolbar">
        <input
          type="search"
          value={s.query}
          placeholder={t('gui.persona.search')}
          aria-label={t('gui.persona.search')}
          onChange={e => store.search(e.target.value)}
        />
      </div>
      {rows.length === 0 ? (
        <p className="muted">{s.rows.length === 0 ? t('gui.persona.empty') : t('gui.persona.no_match')}</p>
      ) : (
        <div className="cards persona-wall">
          {rows.map(r => (
            <Card key={r.name} row={r} />
          ))}
        </div>
      )}
    </>
  )
}
