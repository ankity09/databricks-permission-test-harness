import { useState } from 'react'
import { checkSqlAsSp } from '../api'
import { cn } from '../lib/cn'
import { useStore } from '../store'
import type { SqlCheckResult, SqlCheckVerdict } from '../types'

const FALLBACK_TABLE = 'main.sandbox.orders'
const READ_WORDS = ['SELECT', 'WITH', 'SHOW', 'DESCRIBE', 'DESC', 'EXPLAIN']

const VERDICT: Record<SqlCheckVerdict, { label: string; tone: string }> = {
  allowed: { label: 'Allowed', tone: 'border-pass/50 text-pass' },
  denied: { label: 'Denied', tone: 'border-fail/50 text-fail' },
  invalid: { label: 'Invalid', tone: 'border-warn/50 text-warn' },
  not_checkable: { label: 'Not checkable', tone: 'border-line text-ink-dim' },
}

function examples(table: string): { label: string; sql: string }[] {
  const t = table.split('.').filter(Boolean).length === 3 ? table : FALLBACK_TABLE
  return [
    { label: 'SELECT', sql: `SELECT * FROM ${t} LIMIT 50` },
    { label: 'INSERT', sql: `INSERT INTO ${t} SELECT * FROM ${t} LIMIT 1` },
    { label: 'UPDATE', sql: `UPDATE ${t} SET <column> = <value> WHERE <condition>` },
    { label: 'DELETE', sql: `DELETE FROM ${t} WHERE <condition>` },
    {
      label: 'MERGE',
      sql: `MERGE INTO ${t} AS target\nUSING ${t} AS source ON target.<key> = source.<key>\nWHEN MATCHED THEN UPDATE SET *`,
    },
    { label: 'CREATE TABLE AS SELECT', sql: `CREATE TABLE ${t}_copy AS SELECT * FROM ${t}` },
    { label: 'CREATE VIEW', sql: `CREATE VIEW ${t}_view AS SELECT * FROM ${t}` },
  ]
}

function errMsg(e: unknown): string {
  if (e && typeof e === 'object' && 'response' in e) {
    const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
    if (typeof detail === 'string') return detail
  }
  return e instanceof Error ? e.message : 'The check failed.'
}

/**
 * Check one SQL statement as the app's service principal. Read-only statements
 * run and return rows; any other statement is sent only as EXPLAIN, so Unity
 * Catalog checks its privileges and nothing changes.
 */
export function SqlSection() {
  const prefill = useStore((s) => s.sqlPrefill)
  const [sql, setSql] = useState(() => prefill?.sql ?? '')
  const [table, setTable] = useState(() => prefill?.table ?? '')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<SqlCheckResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const firstWord = sql.trim().split(/[\s(;]/)[0]?.toUpperCase() ?? ''
  const readOnly = READ_WORDS.includes(firstWord)
  const ready = sql.trim().length > 0 && !busy

  async function check() {
    if (!ready) return
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      setResult(await checkSqlAsSp(sql.trim(), table.trim() || undefined))
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setBusy(false)
    }
  }

  const masked = new Set(result?.governance?.masked_columns ?? [])

  return (
    <div className="space-y-5">
      <header className="rounded-lg border border-line bg-surface p-6">
        <h2 className="text-xl font-semibold text-ink">SQL as the app's service principal</h2>
        <p className="mt-2 max-w-3xl text-sm text-ink-dim">
          Check whether the app's service principal could run a statement. Read-only statements
          run and return rows. Anything else is never run: Unity Catalog plans it with{' '}
          <code className="font-mono">EXPLAIN</code> as the app SP, and the harness reads the app SP's
          effective permissions for the write itself.
        </p>
      </header>

      <section className="space-y-3 rounded-lg border border-line bg-surface p-5" aria-label="SQL statement">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 font-mono text-[11px] uppercase tracking-wide text-ink-faint">Examples</span>
          {examples(table.trim()).map((ex) => (
            <button
              key={ex.label}
              type="button"
              onClick={() => setSql(ex.sql)}
              className="rounded border border-line bg-base px-2 py-0.5 font-mono text-[11px] text-ink-dim hover:border-ink-faint hover:text-ink focus-visible:outline focus-visible:outline-1 focus-visible:outline-lava"
            >
              {ex.label}
            </button>
          ))}
        </div>

        <label htmlFor="sql-statement" className="sr-only">SQL statement</label>
        <textarea
          id="sql-statement"
          value={sql}
          onChange={(e) => setSql(e.target.value)}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
              e.preventDefault()
              void check()
            }
          }}
          rows={10}
          spellCheck={false}
          placeholder={`UPDATE ${FALLBACK_TABLE} SET status = 'shipped' WHERE id = 1`}
          className="w-full resize-y rounded-md border border-line bg-base px-3 py-2 font-mono text-[13px] leading-relaxed text-ink placeholder:text-ink-faint focus:border-ink-faint focus:outline-none"
        />

        <div className="flex flex-wrap items-center gap-3">
          <p className="font-mono text-[11px] text-ink-faint" aria-live="polite">
            {sql.trim()
              ? readOnly
                ? 'Read-only: runs as the app SP and returns rows'
                : 'Permission check: nothing runs'
              : 'Cmd or Ctrl + Enter to check'}
          </p>
          <label className="ml-auto flex items-center gap-2 font-mono text-[11px] text-ink-faint">
            Table
            <input
              type="text"
              value={table}
              onChange={(e) => setTable(e.target.value)}
              placeholder="catalog.schema.table (optional)"
              className="w-64 rounded-md border border-line bg-base px-2 py-1 text-ink placeholder:text-ink-faint focus:border-ink-faint focus:outline-none"
            />
          </label>
          <button
            type="button"
            onClick={() => void check()}
            disabled={!ready}
            className={cn(
              'rounded-md px-3 py-1.5 font-mono text-xs font-semibold focus-visible:outline focus-visible:outline-1 focus-visible:outline-lava',
              ready ? 'bg-lava text-white hover:bg-lava-dim' : 'cursor-not-allowed bg-surface-2 text-ink-faint',
            )}
          >
            Check as app SP
          </button>
        </div>
      </section>

      {busy && (
        <div className="space-y-2 rounded-lg border border-line bg-surface p-5" aria-busy="true">
          <div className="h-6 w-40 rounded bg-surface-2 motion-safe:animate-pulse" />
          <div className="h-16 rounded bg-surface-2 motion-safe:animate-pulse" />
        </div>
      )}

      {error && (
        <div role="alert" className="rounded-lg border border-fail/40 bg-fail/5 p-4 font-mono text-xs text-fail">
          {error}
        </div>
      )}

      {result && (
        <section className="space-y-4 rounded-lg border border-line bg-surface p-5" aria-label="Result">
          <div className="flex flex-wrap items-center gap-3">
            <span className={cn('rounded border px-2.5 py-1 font-mono text-xs font-bold uppercase tracking-wider', VERDICT[result.verdict].tone)}>
              {VERDICT[result.verdict].label}
            </span>
            <span className="font-mono text-xs text-ink-dim">{result.statement_kind}</span>
            <span className="ml-auto font-mono text-[11px] text-ink-faint">
              {result.executed ? 'Ran as the app SP' : 'Nothing was run'}
            </span>
          </div>

          {result.message && (
            <pre className="whitespace-pre-wrap break-words rounded-md border border-line bg-base p-3 font-mono text-xs text-ink-dim">
              {result.message}
            </pre>
          )}

          {result.privileges.length > 0 && (
            <ul className="space-y-1 font-mono text-[11px]" aria-label="Privileges checked">
              {result.privileges.map((p) => (
                <li key={`${p.securable_type}:${p.full_name}`} className="flex flex-wrap gap-x-2">
                  <span className={p.missing.length ? 'text-fail' : 'text-pass'}>
                    {p.missing.length ? 'missing' : p.owner ? 'owner' : 'held'}
                  </span>
                  <span className="text-ink-dim">
                    {(p.missing.length ? p.missing : p.needed).map((n) => n.replace(/_/g, ' ')).join(', ')}
                  </span>
                  <span className="text-ink-faint">
                    on {p.securable_type} {p.full_name}
                  </span>
                </li>
              ))}
            </ul>
          )}

          {result.statement_run && result.kind === 'check' && (
            <p className="font-mono text-[11px] text-ink-faint">
              Sent: <span className="text-ink-dim">{result.statement_run}</span>
            </p>
          )}

          {result.plan && (
            <details className="rounded-md border border-line bg-base">
              <summary className="cursor-pointer px-3 py-2 font-mono text-xs text-ink-dim hover:text-ink">Plan</summary>
              <pre className="max-h-96 overflow-auto whitespace-pre px-3 pb-3 font-mono text-[11px] text-ink-faint">{result.plan}</pre>
            </details>
          )}

          {result.governance?.row_filter && (
            <p className="rounded-md border border-warn/40 bg-warn/5 px-3 py-2 font-mono text-[11px] text-warn">
              A row filter applies to this table: the rows below are the ones the app SP can see.
            </p>
          )}

          {result.columns.length > 0 && (
            <div className="overflow-auto rounded-md border border-line">
              <table className="w-full border-collapse font-mono text-[11px]">
                <thead className="bg-surface-2 text-ink-dim">
                  <tr>
                    {result.columns.map((col) => (
                      <th key={col} scope="col" className="whitespace-nowrap px-3 py-1.5 text-left font-semibold">
                        {col}
                        {masked.has(col) && (
                          <span className="ml-1.5 rounded bg-warn/15 px-1 text-[9px] uppercase text-warn">masked</span>
                        )}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="text-ink">
                  {result.rows.map((row, i) => (
                    <tr key={i} className="border-t border-line">
                      {row.map((cell, j) => (
                        <td key={j} className="whitespace-nowrap px-3 py-1">
                          {cell === null ? <span className="text-ink-faint">null</span> : String(cell)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="border-t border-line px-3 py-1.5 font-mono text-[10px] text-ink-faint">
                {result.rows.length} row{result.rows.length === 1 ? '' : 's'}
                {result.truncated && ' (first rows only)'}
              </p>
            </div>
          )}
        </section>
      )}
    </div>
  )
}
