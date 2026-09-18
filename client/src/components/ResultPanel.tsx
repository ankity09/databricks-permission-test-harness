import { useEffect, useRef } from 'react'
import anime from 'animejs'
import type { ProbeResult } from '../types'
import { usePrefersReducedMotion } from '../hooks/useReducedMotion'
import { CountUp } from './motion/CountUp'

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
    label: 'FAIL · DENIED',
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
  const stampRef = useRef<HTMLDivElement>(null)
  const reduced = usePrefersReducedMotion()

  useEffect(() => {
    const el = stampRef.current
    if (!el || !result || reduced) return
    const anim = anime({
      targets: el,
      opacity: [0, 1],
      scale: [0.9, 1],
      duration: 200,
      easing: 'easeOutBack',
    })
    return () => anim.pause()
  }, [result, reduced])

  if (busy) {
    return (
      <div className="animate-pulse rounded-lg border border-line bg-surface p-6">
        <div className="mb-3 h-6 w-40 rounded bg-surface-2" />
        <div className="h-20 rounded bg-surface-2" />
      </div>
    )
  }
  if (!result) {
    return (
      <div className="rounded-lg border border-dashed border-line bg-surface/50 p-6 text-sm text-ink-faint">
        Apply a grant to the SP, then attempt the action. The verdict — including the verbatim
        Databricks error — shows here.
      </div>
    )
  }

  const meta = META[result.status]
  const rowCount = result.rows?.length ?? 0
  const isPass = result.status === 'pass'

  return (
    <div className={'rounded-lg border p-6 ' + meta.ring}>
      {/* verdict stamp + big readout */}
      <div ref={stampRef} className="flex items-end justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <span className={'h-3 w-3 rounded-full ' + meta.dot} />
          <span className={'font-mono text-xl font-bold tracking-wide ' + meta.text}>
            {meta.label}
          </span>
        </div>
        {isPass && rowCount > 0 && (
          <div className="text-right">
            <CountUp value={rowCount} className="font-mono text-3xl font-bold leading-none text-ink" />
            <div className="mt-0.5 font-mono text-[10px] uppercase tracking-wide text-ink-faint">
              rows returned
            </div>
          </div>
        )}
      </div>

      {result.detail && <p className="mt-3 text-sm text-ink">{result.detail}</p>}

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
        <div className="mt-4">
          <div className="mb-1 font-mono text-[10px] font-semibold uppercase tracking-wide text-ink-dim">
            Raw Databricks error
          </div>
          <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-md border border-line bg-base p-3 font-mono text-xs text-ink-dim">
            {result.raw_error}
          </pre>
        </div>
      )}

      {result.rows && result.rows.length > 0 && (
        <div className="mt-4">
          <div className="mb-1 font-mono text-[10px] font-semibold uppercase tracking-wide text-ink-dim">
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
