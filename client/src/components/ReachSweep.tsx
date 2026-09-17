import { useState } from 'react'
import { runSweep } from '../api'
import type { SweepCell, SweepResult } from '../types'

function errMsg(e: unknown): string {
  if (e && typeof e === 'object' && 'response' in e) {
    const anyE = e as { response?: { data?: { detail?: string } }; message?: string }
    return anyE.response?.data?.detail ?? anyE.message ?? 'Request failed'
  }
  return e instanceof Error ? e.message : 'Request failed'
}

const CELL_STYLE: Record<SweepCell, string> = {
  hold: 'text-emerald-500',
  hole: 'text-lava',
  error: 'text-ink-faint',
}

const CELL_LABEL: Record<SweepCell, string> = {
  hold: '● boundary holds',
  hole: '● HOLE',
  error: '● error',
}

const ACTION_LABEL: Record<string, string> = {
  use_catalog: 'USE CATALOG',
  use_schema: 'USE SCHEMA',
  select: 'SELECT',
}

interface Props {
  securable: string
}

/**
 * Feature 2: adversarial read-only reach sweep. Auto-enumerates adjacent
 * objects (siblings + parents) and checks whether the SP can READ things it was
 * not granted. DENIED = green (boundary holds), unexpected SUCCESS = red (hole).
 * Read-only only: makes no claim about write/escalation boundaries.
 */
export function ReachSweep({ securable }: Props) {
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<SweepResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const ready = securable.trim().split('.').filter(Boolean).length >= 2

  async function run() {
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      setResult(await runSweep(securable.trim()))
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setBusy(false)
    }
  }

  const v = result?.verdict
  return (
    <div className="space-y-4 rounded-lg border border-line bg-surface p-5">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold text-ink">Adversarial reach sweep</h3>
        <span className="rounded bg-base px-1.5 py-0.5 font-mono text-[10px] text-ink-faint">
          can the SP snoop the neighbors?
        </span>
      </div>

      <p className="text-[11px] text-ink-faint">
        Auto-checks same-schema siblings + parent containers. The SP attempts a harmless
        read against each; a denial is the expected, healthy result.
      </p>

      <button
        onClick={run}
        disabled={busy || !ready}
        className="rounded-md bg-lava px-4 py-2 text-sm font-semibold text-white hover:bg-lava-dim disabled:opacity-40"
      >
        {busy ? 'Sweeping…' : 'Run reach sweep'}
      </button>
      {!ready && (
        <p className="text-[11px] text-ink-faint">
          Enter at least a catalog.schema (or catalog.schema.table) above.
        </p>
      )}

      {error && (
        <div className="rounded-md border border-lava/40 bg-lava/5 px-3 py-2 text-xs text-ink">
          <span className="font-semibold text-lava">Error</span> · {error}
        </div>
      )}

      {v && (
        <div
          className={`rounded-md border px-3 py-2 text-sm font-semibold ${
            v.status === 'holes_found'
              ? 'border-lava/40 bg-lava/5 text-lava'
              : 'border-emerald-500/40 bg-emerald-500/5 text-emerald-500'
          }`}
        >
          {v.status === 'holes_found'
            ? `${v.holes} hole(s) found across ${v.checked} checks`
            : `Boundaries hold — ${v.checked} adjacent objects, none readable`}
        </div>
      )}

      {result && (
        <div className="overflow-auto rounded-md border border-line">
          <table className="w-full border-collapse text-left font-mono text-[11px]">
            <thead>
              <tr className="bg-base">
                <th className="border-b border-line px-2.5 py-1.5 font-semibold text-ink">Object</th>
                <th className="border-b border-line px-2.5 py-1.5 font-semibold text-ink">Read</th>
                <th className="border-b border-line px-2.5 py-1.5 font-semibold text-ink">Result</th>
              </tr>
            </thead>
            <tbody>
              {result.matrix.map((row, i) => (
                <tr key={i} className="odd:bg-surface even:bg-surface-2">
                  <td className="border-b border-line px-2.5 py-1.5 text-ink-dim break-all">
                    {row.object}
                  </td>
                  <td className="border-b border-line px-2.5 py-1.5 text-ink-faint">
                    {ACTION_LABEL[row.action] ?? row.action}
                  </td>
                  <td className={`border-b border-line px-2.5 py-1.5 font-semibold ${CELL_STYLE[row.result]}`}>
                    {CELL_LABEL[row.result]}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {result && (
        <p className="rounded-md border border-line bg-base px-3 py-2 text-[11px] text-ink-faint">
          {result.scope_note}
        </p>
      )}
    </div>
  )
}
