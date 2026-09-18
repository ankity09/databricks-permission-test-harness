import type { ReactNode } from 'react'
import { useStore } from '../store'
import type { MeResponse } from '../types'
import { CountUp } from '../components/motion/CountUp'
import { ActivityIcon, ScenariosIcon, TestIcon } from '../components/icons'

interface HomeSectionProps {
  me: MeResponse | null
  meError: string | null
}

/**
 * Landing overview — the front door of the console. Shows OBO health, the
 * trust-model one-liner, quick counts, and quick-launch cards into the three
 * working surfaces.
 */
export function HomeSection({ me, meError }: HomeSectionProps) {
  const { activity, setSection } = useStore()

  const obGood = !meError && !!me
  const admin = me?.admin.user_name ?? '—'
  const spName = me
    ? 'error' in me.app_sp
      ? me.app_sp.error
      : me.app_sp.user_name ?? me.configured_sp_application_id
    : '—'

  const applies = activity.filter((a) => a.kind === 'apply').length
  const probes = activity.filter((a) => a.kind === 'probe').length

  const cards: { id: 'test' | 'scenarios' | 'activity'; title: string; sub: string; Icon: (p: { className?: string }) => ReactNode }[] = [
    { id: 'test', title: 'Run a permission test', sub: 'Apply → attempt as SP → verdict', Icon: TestIcon },
    { id: 'scenarios', title: 'Test a role scenario', sub: 'Batch pass/fail matrix', Icon: ScenariosIcon },
    { id: 'activity', title: 'Review activity', sub: 'Durable Lakebase history', Icon: ActivityIcon },
  ]

  return (
    <div className="space-y-6">
      {/* hero / trust model */}
      <div className="rounded-lg border border-line bg-surface p-6">
        <div className="flex items-center gap-2.5">
          <span className="h-6 w-1.5 rounded-full bg-lava" />
          <h2 className="text-xl font-bold tracking-tight text-ink">Permission Test Harness</h2>
        </div>
        <p className="mt-2 max-w-3xl font-mono text-xs leading-relaxed text-ink-faint">
          Apply a candidate permission to the app service principal (signed by your admin identity
          via OBO) → the SP attempts the action itself → see pass / fail with the real Databricks
          error. Real grants to users happen only in Unity Catalog.
        </p>
      </div>

      {/* status tiles */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className={'rounded-lg border p-5 ' + (obGood ? 'border-pass/40 bg-pass/5' : meError ? 'border-fail/40 bg-fail/5' : 'border-line bg-surface')}>
          <div className="flex items-center gap-2">
            <span className={'h-2 w-2 rounded-full ' + (obGood ? 'bg-pass' : meError ? 'bg-fail' : 'bg-ink-faint')} />
            <span className="font-mono text-[10px] uppercase tracking-wide text-ink-faint">OBO status</span>
          </div>
          <div className={'mt-2 text-lg font-bold ' + (obGood ? 'text-pass' : meError ? 'text-fail' : 'text-ink-dim')}>
            {obGood ? 'Healthy' : meError ? 'Not working' : 'Checking…'}
          </div>
          <div className="mt-1 truncate font-mono text-[11px] text-ink-dim">{admin}</div>
        </div>

        <div className="rounded-lg border border-line bg-surface p-5">
          <span className="font-mono text-[10px] uppercase tracking-wide text-ink-faint">Session applies</span>
          <div className="mt-2">
            <CountUp value={applies} className="font-mono text-3xl font-bold text-ink" />
          </div>
          <div className="mt-1 font-mono text-[11px] text-ink-faint">grants applied to SP</div>
        </div>

        <div className="rounded-lg border border-line bg-surface p-5">
          <span className="font-mono text-[10px] uppercase tracking-wide text-ink-faint">Session probes</span>
          <div className="mt-2">
            <CountUp value={probes} className="font-mono text-3xl font-bold text-ink" />
          </div>
          <div className="mt-1 truncate font-mono text-[11px] text-ink-faint">tester: {spName}</div>
        </div>
      </div>

      {/* quick launch */}
      <div>
        <h3 className="mb-3 font-mono text-[11px] uppercase tracking-wide text-ink-faint">Quick launch</h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {cards.map(({ id, title, sub, Icon }) => (
            <button
              key={id}
              onClick={() => setSection(id)}
              className="group flex flex-col gap-3 rounded-lg border border-line bg-surface p-5 text-left transition-colors hover:border-lava/50 focus:outline-none focus-visible:ring-1 focus-visible:ring-lava"
            >
              <Icon className="h-6 w-6 text-lava" />
              <div>
                <div className="text-sm font-semibold text-ink">{title}</div>
                <div className="mt-0.5 font-mono text-[11px] text-ink-faint">{sub}</div>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
