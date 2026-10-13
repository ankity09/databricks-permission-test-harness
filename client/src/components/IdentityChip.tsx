import { useState } from 'react'
import type { MeResponse } from '../types'

interface IdentityChipProps {
  me: MeResponse | null
  error: string | null
}

/**
 * Compact identity indicator for the top bar. Healthy = a lava pulse dot plus
 * grantor/tester names; expands on click. Unhealthy (OBO error) = a fail dot
 * that expands into the full diagnostic that used to be the big banner.
 */
export function IdentityChip({ me, error }: IdentityChipProps) {
  const [open, setOpen] = useState(false)

  if (error) {
    return (
      <div className="relative">
        <button
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="flex items-center gap-2 rounded-md border border-fail/50 bg-fail/10 px-3 py-1.5 text-xs font-medium text-fail hover:bg-fail/15"
        >
          <span className="h-1.5 w-1.5 rounded-full bg-fail" />
          OBO not working
        </button>
        {open && (
          <div className="absolute right-0 top-full z-40 mt-2 w-96 rounded-lg border border-fail/40 bg-surface p-3 text-xs text-ink-dim shadow-xl">
            <p className="mb-1 font-semibold text-fail">On-behalf-of auth failed</p>
            <p className="mb-2">{error}</p>
            <p className="text-ink-faint">
              User authorization may not be enabled, or the app.yaml scopes are wrong. Grants and
              reads will fail until this is fixed.
            </p>
          </div>
        )}
      </div>
    )
  }

  if (!me) {
    return <div className="h-8 w-52 animate-pulse rounded-md border border-line bg-surface-2" />
  }

  const spName =
    'error' in me.app_sp ? me.app_sp.error : me.app_sp.user_name ?? me.configured_sp_application_id
  const admin = me.admin.user_name ?? '—'

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex items-center gap-2 rounded-md border border-line bg-surface px-3 py-1.5 text-xs hover:border-ink-faint"
      >
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-pass opacity-60 motion-reduce:hidden" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-pass" />
        </span>
        <span className="text-ink-dim">OBO</span>
        <span className="font-mono text-ink">{admin}</span>
      </button>
      {open && (
        <div className="absolute right-0 top-full z-40 mt-2 w-80 rounded-lg border border-line bg-surface p-3 text-xs shadow-xl">
          <div className="mb-2 flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-pass" />
            <span className="font-semibold text-ink">Identity split</span>
          </div>
          <dl className="space-y-1.5">
            <div className="flex justify-between gap-3">
              <dt className="text-ink-faint">Grantor (OBO admin)</dt>
              <dd className="font-mono text-ink">{admin}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-ink-faint">Tester (app SP)</dt>
              <dd className="truncate font-mono text-ink">{spName}</dd>
            </div>
          </dl>
        </div>
      )}
    </div>
  )
}
