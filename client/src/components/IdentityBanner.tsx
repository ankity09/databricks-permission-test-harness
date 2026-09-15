import type { MeResponse } from '../types'

interface IdentityBannerProps {
  me: MeResponse | null
  error: string | null
}

export function IdentityBanner({ me, error }: IdentityBannerProps) {
  if (error) {
    return (
      <div className="rounded-lg border border-fail/50 bg-fail/10 px-4 py-2.5 text-sm text-fail">
        <span className="font-semibold">OBO not working.</span> {error} — user authorization may
        not be enabled, or the app.yaml scopes are wrong. Grants and reads will fail until this is
        fixed.
      </div>
    )
  }
  if (!me) {
    return (
      <div className="h-10 animate-pulse rounded-lg border border-line bg-surface" />
    )
  }

  const spName =
    'error' in me.app_sp ? me.app_sp.error : me.app_sp.user_name ?? me.configured_sp_application_id

  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-1 rounded-lg border border-line bg-surface px-4 py-2.5 text-sm">
      <div className="flex items-center gap-2">
        <span className="h-1.5 w-1.5 rounded-full bg-pass" />
        <span className="text-ink-dim">Grantor (OBO admin):</span>
        <span className="font-mono text-ink">{me.admin.user_name ?? '—'}</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-ink-dim">Tester (app SP):</span>
        <span className="font-mono text-ink">{spName}</span>
      </div>
    </div>
  )
}
