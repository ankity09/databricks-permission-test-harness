import { useState } from 'react'
import type { ProbeResult, Tab } from '../types'
import { PromotePanel } from './PromotePanel'
import { QueryRunner } from './QueryRunner'
import { ReachSweep } from './ReachSweep'
import { ResultPanel } from './ResultPanel'

type Stage = 'result' | 'query' | 'sweep' | 'promote'

interface ResultStageProps {
  tab: Tab
  result: ProbeResult | null
  busy: boolean
  securable: string
  actionId: string | null
  ready: boolean
}

/**
 * The result stage of the Test pipeline. In-stage tabs let the user move
 * between the probe verdict, the "see what the SP sees" query runner, the
 * adversarial reach sweep, and the promote panel — without leaving the canvas.
 * Query + Sweep are UC-data-only (they operate on securables).
 */
export function ResultStage({ tab, result, busy, securable, actionId, ready }: ResultStageProps) {
  const [stage, setStage] = useState<Stage>('result')
  const ucData = tab === 'uc-data'

  const tabs: { id: Stage; label: string; show: boolean }[] = [
    { id: 'result', label: 'Result', show: true },
    { id: 'query', label: 'Query as SP', show: ucData },
    { id: 'sweep', label: 'Reach sweep', show: ucData },
    { id: 'promote', label: 'Promote', show: true },
  ]

  // If the mode flips to workspace while on a UC-only tab, fall back to result.
  const activeStage = !ucData && (stage === 'query' || stage === 'sweep') ? 'result' : stage

  return (
    <div className="space-y-4">
      <div className="flex gap-1 border-b border-line" role="tablist" aria-label="Result stage">
        {tabs
          .filter((t) => t.show)
          .map((t) => {
            const active = t.id === activeStage
            return (
              <button
                key={t.id}
                role="tab"
                aria-selected={active}
                onClick={() => setStage(t.id)}
                className={
                  'relative px-3 py-2 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-lava ' +
                  (active ? 'text-ink' : 'text-ink-faint hover:text-ink-dim')
                }
              >
                {t.label}
                {active && (
                  <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-lava" />
                )}
              </button>
            )
          })}
      </div>

      {activeStage === 'result' && <ResultPanel result={result} busy={busy} />}
      {activeStage === 'query' && ucData && <QueryRunner securable={securable} />}
      {activeStage === 'sweep' && ucData && <ReachSweep securable={securable} />}
      {activeStage === 'promote' && (
        <PromotePanel actionId={actionId} securable={securable} disabled={!ready} />
      )}
    </div>
  )
}
