import { useState } from 'react'

import { fileUrl } from '../api'
import { arm, pages, progress, revisions, roundVersions, tone, verdict } from '../derive'

import type { Item, Run } from '../model'
import type { JSX } from 'react'

function passes(run: Run): number[] {
  return run.rounds.map((round) =>
    round.signals.flatMap((signal) => signal.items).filter((item) => tone(item.result) === 'pass').length,
  )
}

function Cells({ results }: { results: (Item['result'] | null)[] }): JSX.Element {
  return (
    <>
      {results.map((result, i) => (
        <td key={i} className={`cell ${result === null ? 'none' : tone(result)}`}>{result === null ? '·' : verdict(result)}</td>
      ))}
    </>
  )
}

/* The take-away page one traveller received in every round of both arms, so
   the deliverable itself shows what each Harness revision changed. */
function Pages({ arms, versions }: { arms: Run[]; versions: string[][] }): JSX.Element | null {
  const names = [...new Set(arms.flatMap((run) => run.rounds.flatMap((round) => Object.keys(round.sessions))))]
    .filter((name) => arms.some((run) => pages(run, name).some(Boolean)))
  const [chosen, setChosen] = useState('')
  const session = names.includes(chosen) ? chosen : names[0]
  if (!session) return null
  return (
    <div className="pages">
      <div className="chips">
        <span className="eyebrow">Take-away pages</span>
        <select value={session} onChange={(e) => setChosen(e.target.value)}>
          {names.map((name) => <option key={name} value={name}>{name}</option>)}
        </select>
      </div>
      {arms.map((run, a) => (
        <div key={a} className="page-row">
          <span className="arm-label">{arm(run)}</span>
          <div className="thumbs">
            {pages(run, session).map((path, i) => (
              <figure key={i} className="thumb">
                <figcaption>R{i + 1} · {versions[a][i]}</figcaption>
                {path ? (
                  <a href={fileUrl(path)} target="_blank" rel="noreferrer" className="frame">
                    <iframe src={fileUrl(path)} sandbox="" title={`R${i + 1}`} loading="lazy" tabIndex={-1} />
                  </a>
                ) : (
                  <span className="frame empty">no page</span>
                )}
              </figure>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

/* Two runs of the same scenario side by side, round for round: what the
   control arm settled at, and what each Harness revision changed. */
export function Compare({ left, right }: { left: Run; right: Run }): JSX.Element {
  const arms = [left, right]
  const reports = arms.map(progress)
  const versions = arms.map((run) => roundVersions(run, revisions(run)))
  const total = arms.map((run) => run.rounds[0]?.signals.flatMap((signal) => signal.items).length ?? 0)
  const keys = [...new Set(reports.flatMap((report) => Object.keys(report.matrix)))]
  const finalOf = (report: ReturnType<typeof progress>, key: string): string => {
    const results = (report.matrix[key] ?? []).filter((r) => r !== null)
    return results.length ? tone(results[results.length - 1] as Item['result']) : 'none'
  }
  return (
    <div className="compare">
      <div className="chips">
        <span className="eyebrow">Comparison</span>
        <span className="quiet">same scenario, travellers and agency; only the Curator differs</span>
      </div>
      <div className="table">
        <table>
          <thead>
            <tr>
              <th rowSpan={2}>Criterion</th>
              {arms.map((run, a) => (
                <th key={a} colSpan={run.rounds.length} className={`arm${a ? ' right' : ''}`}>
                  {arm(run)} · {passes(run).map((n) => `${n}/${total[a]}`).join(' → ')}
                </th>
              ))}
            </tr>
            <tr>
              {arms.map((run, a) =>
                run.rounds.map((_, i) => (
                  <th key={`${a}-${i}`} className={a && i === 0 ? 'right' : ''}>
                    R{i + 1}<small>{versions[a][i]}</small>
                  </th>
                )),
              )}
            </tr>
          </thead>
          <tbody>
            {keys.map((key) => {
              const gain = finalOf(reports[0], key) !== 'pass' && finalOf(reports[1], key) === 'pass'
              return (
                <tr key={key} className={gain ? 'gain' : ''}>
                  <td><span className="n">{key.split('/').slice(1).join('/')}</span></td>
                  {arms.map((run, a) => (
                    <Cells key={a} results={reports[a].matrix[key] ?? run.rounds.map(() => null)} />
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <Pages arms={arms} versions={versions} />
      <ol className="chain">
        {revisions(right).map((rev) => (
          <li key={rev.label}>
            <code>{rev.label}</code>
            <span>
              {rev.round ? `after round ${rev.round}: ` : 'on hire: '}
              {(rev.curation.generated?.candidate.plan.changes ?? []).map((change) => `${change.target} — ${change.expected}`).join(' · ') || (rev.curation.error ? `failed: ${rev.curation.error}` : 'baseline kept')}
            </span>
          </li>
        ))}
      </ol>
    </div>
  )
}
