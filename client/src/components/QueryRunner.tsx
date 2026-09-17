import { useState } from 'react'
import { runQuery } from '../api'
import type { QueryResult } from '../types'

function errMsg(e: unknown): string {
  if (e && typeof e === 'object' && 'response' in e) {
    const anyE = e as { response?: { data?: { detail?: string } }; message?: string }
    return anyE.response?.data?.detail ?? anyE.message ?? 'Request failed'
  }
  return e instanceof Error ? e.message : 'Request failed'
}

interface Props {
  securable: string
}

/**
 * Feature 1: run a read-only query AS THE APP SP and see the actual rows, so
 * column masks and row filters are directly observable. Guided one-click (uses
 * the selected table) + an advanced read-only SQL box.
 */
export function QueryRunner({ securable }: Props) {
  const [mode, setMode] = useState<'guided' | 'sql'>('guided')
  const [sql, setSql] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<QueryResult | null>(null)
  const [blocked, setBlocked] = useState<string | null>(null)

  const guidedReady = securable.trim().split('.').filter(Boolean).length === 3

  async function run() {
    setBusy(true)
    setBlocked(null)
    setResult(null)
    try {
      const body =
        mode === 'guided'
          ? { table: securable.trim(), limit: 50 }
          : { sql, table: securable.trim() || undefined, limit: 50 }
      const r = await runQuery(body)
      setResult(r)
    } catch (e) {
      // 400 = blocked by the read-only guard (or bad input). Show it inline.
      setBlocked(errMsg(e))
    } finally {
      setBusy(false)
    }
  }

  const g = result?.governance
  const maskedSet = new Set(g?.masked_columns ?? [])

  return (
    <div className="space-y-4 rounded-lg border border-line bg-surface p-5">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold text-ink">Run query as SP</h3>
        <span className="rounded bg-base px-1.5 py-0.5 font-mono text-[10px] text-ink-faint">
          see what the SP sees
        </span>
        <div className="ml-auto flex rounded-md border border-line bg-base p-0.5 text-xs">
          <button
            onClick={() => setMode('guided')}
            className={`rounded px-2.5 py-1 font-medium ${
              mode === 'guided' ? 'bg-surface-2 text-ink' : 'text-ink-faint hover:text-ink'
            }`}
          >
            Guided
          </button>
          <button
            onClick={() => setMode('sql')}
            className={`rounded px-2.5 py-1 font-medium ${
              mode === 'sql' ? 'bg-surface-2 text-ink' : 'text-ink-faint hover:text-ink'
            }`}
          >
            SQL
          </button>
        </div>
      </div>

      {mode === 'guided' ? (
        <p className="font-mono text-xs text-ink-faint">
          {guidedReady
            ? `SELECT * FROM ${securable.trim()} LIMIT 50`
            : 'Enter a 3-part table name above (catalog.schema.table).'}
        </p>
      ) : (
        <div className="space-y-1.5">
          <textarea
            value={sql}
            onChange={(e) => setSql(e.target.value)}
            rows={3}
            spellCheck={false}
            placeholder="SELECT col FROM catalog.schema.table WHERE ... LIMIT 50"
            className="w-full rounded-md border border-line bg-base px-3 py-2 font-mono text-xs text-ink placeholder:text-ink-faint focus:border-ink-faint focus:outline-none"
          />
          <p className="text-[11px] text-ink-faint">
            Read-only: only SELECT / SHOW / DESCRIBE / EXPLAIN are allowed.
          </p>
        </div>
      )}

      <button
        onClick={run}
        disabled={busy || (mode === 'guided' ? !guidedReady : !sql.trim())}
        className="rounded-md bg-lava px-4 py-2 text-sm font-semibold text-white hover:bg-lava-dim disabled:opacity-40"
      >
        {busy ? 'Running…' : 'Run query as SP'}
      </button>

      {blocked && (
        <div className="rounded-md border border-lava/40 bg-lava/5 px-3 py-2 text-xs text-ink">
          <span className="font-semibold text-lava">Blocked</span> · {blocked}
        </div>
      )}

      {result?.error && (
        <div className="rounded-md border border-lava/40 bg-lava/5 px-3 py-2">
          <p className="mb-1 text-xs font-semibold text-lava">SP denied / query error</p>
          <pre className="whitespace-pre-wrap break-all font-mono text-[11px] text-ink-dim">
            {result.error}
          </pre>
        </div>
      )}

      {result && !result.error && (
        <div className="space-y-2">
          {g && (g.masked_columns.length > 0 || g.row_filter) && (
            <div className="rounded-md border border-line bg-base px-3 py-2 text-[11px] text-ink-dim">
              🛡 Governance:{' '}
              {g.masked_columns.length > 0 && (
                <span>
                  masked column(s):{' '}
                  <span className="font-mono text-ink">{g.masked_columns.join(', ')}</span>
                </span>
              )}
              {g.masked_columns.length > 0 && g.row_filter && ' · '}
              {g.row_filter && <span>row filter active (rows are policy-filtered)</span>}
            </div>
          )}
          <div className="overflow-auto rounded-md border border-line">
            <table className="w-full border-collapse text-left font-mono text-[11px]">
              <thead>
                <tr className="bg-base">
                  {result.columns.map((c) => (
                    <th key={c} className="border-b border-line px-2.5 py-1.5 font-semibold text-ink">
                      {c}
                      {maskedSet.has(c) && (
                        <span
                          title="Column mask applied by Unity Catalog"
                          className="ml-1 rounded bg-lava/15 px-1 py-0.5 text-[9px] font-medium text-lava"
                        >
                          🛡 masked
                        </span>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row, ri) => (
                  <tr key={ri} className="odd:bg-surface even:bg-surface-2">
                    {(Array.isArray(row) ? row : [row]).map((cell, ci) => (
                      <td key={ci} className="border-b border-line px-2.5 py-1.5 text-ink-dim">
                        {String(cell)}
                      </td>
                    ))}
                  </tr>
                ))}
                {result.rows.length === 0 && (
                  <tr>
                    <td className="px-2.5 py-2 text-ink-faint" colSpan={Math.max(1, result.columns.length)}>
                      No rows returned (the SP may see zero rows after row filtering).
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          {result.truncated && (
            <p className="text-[11px] text-ink-faint">Showing first 50 rows (truncated).</p>
          )}
        </div>
      )}
    </div>
  )
}
