import type { MeResponse } from '../types'

interface NotAuthorizedPageProps {
  me: MeResponse | null
  error?: string
}

export function NotAuthorizedPage({ me, error }: NotAuthorizedPageProps) {
  const admin = me?.admin.user_name ?? '(unknown)'
  const requiredGroup = me?.allowed_group ?? '(no group specified)'

  return (
    <div className="min-h-dvh flex items-center justify-center bg-base px-4">
      <div className="max-w-md space-y-6 rounded-lg border border-line bg-surface p-8 text-center">
        <div>
          <div className="mb-3 inline-block rounded-full bg-warn/10 p-3">
            <div className="h-6 w-6 text-warn">⚠</div>
          </div>
          <h1 className="text-lg font-bold text-ink">Not Authorized</h1>
        </div>

        <div className="space-y-3 text-sm text-ink-dim">
          <p>
            Signed in as <span className="font-mono font-semibold text-ink">{admin}</span>
          </p>
          <p>
            This application requires membership in the group{' '}
            <span className="font-mono font-semibold text-ink">{requiredGroup}</span>
          </p>
          {error && <p className="font-mono text-[11px] text-warn">{error}</p>}
        </div>

        <div className="border-t border-line/50 pt-4">
          <p className="text-[12px] leading-relaxed text-ink-faint">
            Ask your workspace administrator to add you to the required group, then refresh this page.
          </p>
        </div>
      </div>
    </div>
  )
}
