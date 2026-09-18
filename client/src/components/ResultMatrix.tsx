import type { MatrixResult, ProbeStatus } from '../types'
import { CountUp } from './motion/CountUp'

const STATUS_STYLES: Record<string, string> = {
  pass: 'bg-pass/15 text-pass border-pass/30',
  fail_denied: 'bg-lava/15 text-lava border-lava/30',
  grant_failed: 'bg-warn/15 text-warn border-warn/30',
  bad_input: 'bg-warn/15 text-warn border-warn/30',
  error: 'bg-lava/15 text-lava border-lava/30',
}

function badge(status: ProbeStatus | string) {
  return (
    <span
      className={
        'inline-block rounded border px-2 py-0.5 font-mono text-[11px] uppercase ' +
        (STATUS_STYLES[status] ?? 'bg-surface-2 text-ink-dim border-line')
      }
    >
      {status}
    </span>
  )
}

export function ResultMatrix({ matrix }: { matrix: MatrixResult | null }) {
  if (!matrix) return null
  const pass = matrix.overall === 'pass'
  const passed = matrix.results.filter((r) => r.status === 'pass').length
  return (
    <div className="space-y-3 rounded-lg border border-line bg-surface p-5">
      <div className="flex items-center gap-2">
        <span className={'h-2.5 w-2.5 rounded-full ' + (pass ? 'bg-pass' : 'bg-lava')} />
        <h3 className="text-sm font-semibold text-ink">
          Role verdict:{' '}
          <span className={pass ? 'text-pass' : 'text-lava'}>{pass ? 'PASS' : 'FAIL'}</span>
        </h3>
        <span className="ml-auto font-mono text-[11px] text-ink-faint">
          <CountUp value={passed} className="text-ink-dim" />/{matrix.results.length} actions passed
        </span>
      </div>
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-line font-mono text-[11px] uppercase text-ink-faint">
            <th className="py-2">Action</th>
            <th className="py-2">Securable</th>
            <th className="py-2">Verdict</th>
          </tr>
        </thead>
        <tbody>
          {matrix.results.map((r, i) => (
            <tr key={i} className="border-b border-line/50 align-top">
              <td className="py-2 pr-3 font-mono text-xs text-ink-dim">{r.action_id}</td>
              <td className="py-2 pr-3 font-mono text-xs text-ink-faint break-all">
                {r.securable}
              </td>
              <td className="py-2">
                {badge(r.status)}
                {r.detail && <span className="ml-2 text-xs text-ink-faint">{r.detail}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
