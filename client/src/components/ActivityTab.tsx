import { useCallback, useEffect, useState } from 'react'
import { getActivity } from '../api'
import { useStore } from '../store'
import type { DbHealth, ProbeStatus } from '../types'

const VERDICT_STYLES: Record<string, string> = {
  pass: 'bg-pass/15 text-pass border-pass/30',
  fail_denied: 'bg-lava/15 text-lava border-lava/30',
  grant_failed: 'bg-warn/15 text-warn border-warn/30',
  bad_input: 'bg-warn/15 text-warn border-warn/30',
  error: 'bg-lava/15 text-lava border-lava/30',
}

function verdictBadge(v?: string | null) {
  if (!v) return <span className="text-ink-faint">—</span>
  return (
    <span
      className={
        'inline-block rounded border px-2 py-0.5 font-mono text-[10px] uppercase ' +
        (VERDICT_STYLES[v as ProbeStatus] ?? 'bg-surface-2 text-ink-dim border-line')
      }
    >
      {v}
    </span>
  )
}

export function ActivityTab() {
  const { activityRows, setActivityRows } = useStore()
  const [db, setDb] = useState<DbHealth | null>(null)
  const [loading, setLoading] = useState(true)
  const [verdict, setVerdict] = useState('')
  const [securable, setSecurable] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    getActivity({
      verdict: verdict || undefined,
      securable: securable || undefined,
      limit: 200,
    })
      .then((r) => {
        setActivityRows(r.events)
        setDb(r.db)
      })
      .catch(() => {
        setActivityRows([])
        setDb({ ok: false, error: 'request failed' })
      })
      .finally(() => setLoading(false))
  }, [verdict, securable, setActivityRows])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-line bg-surface p-4">
        <div>
          <label className="mb-1 block font-mono text-[11px] uppercase text-ink-faint">
            Verdict
          </label>
          <select
            value={verdict}
            onChange={(e) => setVerdict(e.target.value)}
            className="rounded-md border border-line bg-base px-2 py-2 text-sm text-ink focus:border-lava focus:outline-none"
          >
            <option value="">all</option>
            <option value="pass">pass</option>
            <option value="fail_denied">fail_denied</option>
            <option value="grant_failed">grant_failed</option>
            <option value="error">error</option>
          </select>
        </div>
        <div className="min-w-[220px] flex-1">
          <label className="mb-1 block font-mono text-[11px] uppercase text-ink-faint">
            Securable contains
          </label>
          <input
            value={securable}
            onChange={(e) => setSecurable(e.target.value)}
            placeholder="catalog.schema…"
            className="w-full rounded-md border border-line bg-base px-3 py-2 font-mono text-sm text-ink placeholder:text-ink-faint focus:border-lava focus:outline-none"
          />
        </div>
        <button
          onClick={load}
          className="rounded-md border border-line bg-surface-2 px-4 py-2 text-sm font-medium text-ink hover:border-ink-faint"
        >
          Refresh
        </button>
      </div>

      {db && !db.ok && (
        <p className="rounded-md border border-warn/30 bg-warn/10 px-3 py-2 text-xs text-warn">
          Activity database not connected ({db.error}). History is unavailable until Lakebase is
          wired. The in-session activity view on the test tabs still works.
        </p>
      )}

      <div className="rounded-lg border border-line bg-surface p-5">
        <h3 className="mb-3 text-sm font-semibold text-ink">Activity history</h3>
        {loading ? (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-6 animate-pulse rounded bg-surface-2" />
            ))}
          </div>
        ) : activityRows.length === 0 ? (
          <p className="text-xs text-ink-faint">No activity recorded.</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-line font-mono text-[11px] uppercase text-ink-faint">
                <th className="py-2">Time</th>
                <th className="py-2">Admin</th>
                <th className="py-2">Event</th>
                <th className="py-2">Action</th>
                <th className="py-2">Securable</th>
                <th className="py-2">Verdict</th>
              </tr>
            </thead>
            <tbody>
              {activityRows.map((r) => (
                <tr key={r.id} className="border-b border-line/50 align-top">
                  <td className="py-2 pr-3 font-mono text-[11px] text-ink-faint">
                    {r.ts ? String(r.ts).slice(0, 19).replace('T', ' ') : '—'}
                  </td>
                  <td className="py-2 pr-3 text-xs text-ink-dim">{r.admin_email || '—'}</td>
                  <td className="py-2 pr-3 font-mono text-[11px] uppercase text-lava">
                    {r.event_type}
                  </td>
                  <td className="py-2 pr-3 font-mono text-xs text-ink-dim">{r.action_id}</td>
                  <td className="py-2 pr-3 font-mono text-xs text-ink-faint break-all">
                    {r.securable}
                  </td>
                  <td className="py-2">{verdictBadge(r.verdict)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
