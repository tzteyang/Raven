/* The harness view: what each harness of the employee (the root and each
   child Harness) changed in each version, in which strategy, and when it
   stopped changing; the red lines by version beside the strategies the
   revision before each changed; and what each housed sub-harness reads now. */

import { useEffect, useMemo, useState } from 'react'

import { loadSubharnesses } from '../api'
import { deployed } from '../derive'
import { cellTone, harnessRows, readBySubharness, redLines } from '../harness'
import { Fold, RedLine, StrategyBadge, TreatmentBadge } from './Badges'
import { Markdown } from './Markdown'

import type { Revision } from '../derive'
import type { Cell, HomeFile, HousedHome, Matrix } from '../harness'
import type { Run, Scenario } from '../model'
import type { JSX } from 'react'

const cellText = (cell: Cell | null): string => {
  if (cell === null) return '·'
  const judged = cell.pass + cell.fail
  if (judged > 1) return cell.fail ? `${cell.fail}/${judged} fail` : 'pass'
  return cell.fail ? 'fail' : cell.pass ? 'pass' : 'unknown'
}

function VerdictTable({ matrix, rows, red }: { matrix: Matrix; rows: Matrix['rows']; red: boolean }): JSX.Element {
  return (
    <div className="table">
      <table className="matrix">
        <thead>
          <tr>
            <th>Criterion</th>
            {matrix.columns.map((column) => (
              <th key={column.round} className="col">
                <span className="v">{column.version}</span>
                <small>round {column.round}{column.fresh ? '' : ' · repeat'}</small>
                <span className="klasses">
                  {column.strategies.length ? column.strategies.map((name) => <StrategyBadge key={name} strategy={name} />) : <span className="dim">{column.version === 'v0' ? 'baseline' : column.fresh ? 'no change' : ''}</span>}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(({ criterion, cells }) => (
            <tr key={criterion.id}>
              <td title={criterion.check}>
                <span className="n">{criterion.id}</span>
                {red ? <RedLine /> : null}
              </td>
              {cells.map((cell, i) => <td key={i} className={`cell ${cellTone(cell)}`}>{cellText(cell)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function HomeFileRow({ file }: { file: HomeFile }): JSX.Element {
  return (
    <Fold
      className="sbf default"
      summary={
        <>
          <code className="p">{file.path}</code>
          {readBySubharness(file.path) ? <span className="reads" title="The sub-harness reads this file on its next turn">read</span> : null}
          <span className="sz">{file.size ? `${file.size.toLocaleString('en-US')} B` : 'empty'}</span>
        </>
      }
    >
      {() =>
        typeof file.text === 'string' ? (
          file.text.trim() ? (
            <div className="sbf-body">
              {file.path.endsWith('.md') ? <Markdown text={file.text} /> : <pre>{file.text}</pre>}
              {file.truncated ? <p className="quiet small">Cut to the first 64,000 characters.</p> : null}
            </div>
          ) : <p className="quiet small">The file is empty.</p>
        ) : <p className="quiet small">Only prose and config text is shown; this file is listed by name.</p>
      }
    </Fold>
  )
}

/* Each housed sub-harness home as the record keeps it now. A child Harness's
   own strategies prepare what it reads there, so the Curator's changes to it
   are its rows in the table above, not these files. */
function SubharnessHomes({ runId, revisions }: { runId: string; revisions: Revision[] }): JSX.Element {
  const [homes, setHomes] = useState<HousedHome[] | null>(null)
  const [error, setError] = useState('')
  const labels = deployed(revisions).map((rev) => rev.label).join(',')
  useEffect(() => {
    let alive = true
    setError('')
    loadSubharnesses(runId)
      .then((rows) => { if (alive) setHomes(rows) })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [runId, labels])
  if (error) return <p className="quiet">The server did not answer /api/subharnesses ({error}); a server started before this view existed needs a restart.</p>
  if (!homes) return <p className="quiet">Reading the sub-harness homes...</p>
  if (!homes.length) return <p className="quiet">This run houses no sub-harness home in its record.</p>
  return (
    <>
      {homes.map((home) => (
        <div key={home.name} className="sbh">
          <div className="sbh-hd">
            <span className="nm">{home.name}</span>
            <span className="quiet">{home.files.length} file{home.files.length === 1 ? '' : 's'} · {home.files.filter((file) => readBySubharness(file.path)).length} read on its next turn</span>
          </div>
          <div className="sbh-files">{home.files.map((file) => <HomeFileRow key={file.path} file={file} />)}</div>
        </div>
      ))}
    </>
  )
}

export function HarnessView({ run, runId, revisions, scenario }: { run: Run; runId?: string; revisions: Revision[]; scenario: Scenario }): JSX.Element {
  const rows = useMemo(() => harnessRows(run, revisions), [run, revisions])
  const matrix = useMemo(() => redLines(run, revisions, scenario.criteria), [run, revisions, scenario])
  const labels = deployed(revisions).map((rev) => rev.label)
  const latest = labels[labels.length - 1]
  return (
    <div className="harness-view">
      <div className="task">
        <span className="eyebrow">Harness</span>
        <h2>What each harness changed, version by version</h2>
        <p className="quiet">The employee is the root Harness and the child Harnesses its playbooks' nodes run on; each has four strategies (memory, planning, capability, action). A row appears for every child a revision changed or a playbook node ran.</p>
      </div>
      <section className="sec">
        <h3>Changes by harness <span className="cnt">{labels.length} version{labels.length === 1 ? '' : 's'} after v0</span></h3>
        {labels.length === 0 ? <p className="quiet">No revision was deployed in this run, so every harness stayed on its baseline.</p> : (
          <div className="table">
            <table className="hx">
              <thead>
                <tr><th>Harness</th>{labels.map((label) => <th key={label}>{label}</th>)}<th>Settled</th></tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.harness}>
                    <td className="h">{row.harness}</td>
                    {labels.map((label) => (
                      <td key={label}>
                        {(row.changes[label] ?? []).map((change, i) => (
                          <div key={i} className="hc" title={change.expected}>
                            <code>{change.target}</code>
                            <StrategyBadge strategy={change.strategy} />
                            <TreatmentBadge treatment={change.treatment} />
                            {change.files.length ? <span className="files">{change.files.join(', ')}</span> : null}
                          </div>
                        ))}
                        {row.changes[label] ? null : <span className="dim">·</span>}
                      </td>
                    ))}
                    <td className="settle">
                      {row.last === null ? <span className="dim">never changed</span> : row.last === latest ? <span>changed in the latest version</span> : <span className="good">unchanged since {row.last}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {deployed(revisions).some((rev) => rev.curation.revision) ? (
        <section className="sec">
          <h3>Child strategy implementations</h3>
          {deployed(revisions).filter((rev) => rev.curation.revision).map((rev) => (
            <Fold key={rev.key} className="fold" summary={`${rev.label} · child plans and active code`}>
              {() => <>
                {Object.keys(rev.curation.generated?.candidate.plan.node_reasons ?? {}).length ? (
                  <Fold className="fold" summary="Root node decisions">
                    {() => <pre>{JSON.stringify(rev.curation.generated?.candidate.plan.node_reasons, null, 2)}</pre>}
                  </Fold>
                ) : null}
                {Object.entries(rev.curation.revision!.children).map(([name, child]) => (
                <Fold key={name} className="fold" summary={name}>
                  {() => <>
                    {child.plan ? <Markdown text={`${child.plan.understanding}\n\n${child.plan.design ?? ''}`} /> : null}
                    <pre>{JSON.stringify(child.artifact.values, null, 2)}</pre>
                    {Object.entries(child.artifact.files).map(([path, text]) => (
                      <Fold key={path} className="fold" summary={path}>{() => <pre>{text}</pre>}</Fold>
                    ))}
                  </>}
                </Fold>
              ))}</>}
            </Fold>
          ))}
        </section>
      ) : null}
      {runId ? (
        <section className="sec">
          <h3>Sub-harness homes</h3>
          <p className="quiet small">What each housed sub-harness reads now, from its home in the record.</p>
          <SubharnessHomes runId={runId} revisions={revisions} />
        </section>
      ) : null}
      <section className="sec">
        <h3>{matrix.marked ? 'Red lines by version' : 'Criteria by version'} <span className="cnt">{matrix.rows.length}</span></h3>
        {run.rounds.length === 0 ? <p className="quiet">No trial has run yet.</p> : (
          <>
            <VerdictTable matrix={matrix} rows={matrix.rows} red={matrix.marked} />
            <p className="note">
              {matrix.marked ? null : 'No red line of the scenario was judged in this run, so every judged criterion is listed. '}
              Each column head shows the strategies changed by the revision that produced that version. They say what changed before the trial, not what caused a verdict.
            </p>
            {matrix.others.length ? (
              <Fold className="fold" summary={`Other criteria (${matrix.others.length})`}>
                {() => <VerdictTable matrix={matrix} rows={matrix.others} red={false} />}
              </Fold>
            ) : null}
          </>
        )}
      </section>
    </div>
  )
}
