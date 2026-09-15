import type { ProbeResult } from '../types'

interface ResultPanelProps {
  result: ProbeResult | null
  busy: boolean
}

const META: Record<
  ProbeResult['status'],
  { label: string; ring: string; dot: string; text: string }
> = {
  pass: { label: 'PASS', ring: 'border-pass/50 bg-pass/5', dot: 'bg-pass', text: 'text-pass' },
  fail_denied: {
    label: 'FAIL — DENIED',
    ring: 'border-fail/50 bg-fail/5',
    dot: 'bg-fail',
    text: 'text-fail',
  },
  grant_failed: {
    label: 'GRANT FAILED',
    ring: 'border-warn/50 bg-warn/5',
    dot: 'bg-warn',
    text: 'text-warn',
  },
  bad_input: {
    label: 'CHECK INPUT',
    ring: 'border-warn/50 bg-warn/5',
    dot: 'bg-warn',
    text: 'text-warn',
  },
  error: {
    label: 'ERROR',
    ring: 'border-ink-faint/40 bg-surface-2',
    dot: 'bg-ink-faint',
    text: 'text-ink-dim',
  },
}

export function ResultPanel({ result, busy }: ResultPanelProps) {
  if (busy) {
    return (
      <div className="animate-pulse rounded-lg border border-line bg-surface p-5">
        <div className="mb-3 h-4 w-32 rounded bg-surface-2" />
        <div className="h-16 rounded bg-surface-2" />
      </div>
    )
  }
  if (!result) {
    return (
      <div className="rounded-lg border border-dashed border-line bg-surface/50 p-5 text-sm text-ink-faint">
        Apply a grant to the SP, then attempt the action. The result — including the verbatim
        Databricks error — shows here.
      </div>
    )
  }

  const meta = META[result.status]
  return (
    <div className={'rounded-lg border p-5 ' + meta.ring}>
      <div className="flex items-center gap-2">
        <span className={'h-2.5 w-2.5 rounded-full ' + meta.dot} />
        <span className={'font-mono text-sm font-semibold tracking-wide ' + meta.text}>
          {meta.label}
        </span>
      </div>

      {result.detail && <p className="mt-2 text-sm text-ink">{result.detail}</p>}

      {result.status === 'grant_failed' && (
        <p className="mt-1 text-xs text-warn/80">
          This is your account failing to <em>issue</em> the grant — not the SP being denied the
          action. Check that your logged-in identity owns the securable.
        </p>
      )}

      {result.status === 'bad_input' && (
        <p className="mt-1 text-xs text-warn/80">
          The object name doesn't match this action's level (e.g. <em>USE CATALOG</em> needs a
          catalog-level name, not <span className="font-mono">catalog.schema.table</span>). No grant
          was attempted — fix the object name and retry.
        </p>
      )}

      {result.raw_error && (
        <div className="mt-3">
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-dim">
            Raw Databricks error
          </div>
          <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-md border border-line bg-base p-3 font-mono text-xs text-ink-dim">
            {result.raw_error}
          </pre>
        </div>
      )}

      {result.rows && result.rows.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-dim">
            Returned rows ({result.rows.length})
          </div>
          <pre className="max-h-48 overflow-auto rounded-md border border-line bg-base p-3 font-mono text-xs text-ink-dim">
            {JSON.stringify(result.rows, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}
