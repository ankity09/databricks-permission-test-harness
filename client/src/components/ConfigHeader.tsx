import type { ActionDescriptor, Tab } from '../types'
import { ActionPicker } from './ActionPicker'
import { NegativeTestToggle } from './NegativeTestToggle'
import { ObjectPicker } from './ObjectPicker'

interface ConfigHeaderProps {
  tab: Tab
  onTab: (t: Tab) => void
  securable: string
  onSecurable: (s: string) => void
  actions: ActionDescriptor[]
  actionId: string | null
  onAction: (id: string) => void
  negativeTest: boolean
  onNegativeTest: (v: boolean) => void
  canGrant: boolean
  selected: ActionDescriptor | null
  ready: boolean
  busy: boolean
  onApply: () => void
  onAttempt: () => void
  onRevoke: () => void
  onReset: () => void
}

const MODES: { id: Tab; label: string; sub: string }[] = [
  { id: 'uc-data', label: 'Unity Catalog Data', sub: 'SP runs a real, safe probe' },
  { id: 'workspace', label: 'Workspace Objects', sub: 'effective permission check' },
]

/**
 * Sticky configuration header for the Test canvas. Holds the mode segmented
 * control, object + action pickers, negative-test toggle, and the 1·2·3 action
 * buttons that drive the loop. Everything below it is the result stage.
 */
export function ConfigHeader(props: ConfigHeaderProps) {
  const {
    tab,
    onTab,
    securable,
    onSecurable,
    actions,
    actionId,
    onAction,
    negativeTest,
    onNegativeTest,
    canGrant,
    selected,
    ready,
    busy,
    onApply,
    onAttempt,
    onRevoke,
    onReset,
  } = props

  return (
    <div className="sticky top-[57px] z-10 space-y-5 rounded-lg border border-line bg-surface/95 p-6 backdrop-blur">
      {/* mode segmented control */}
      <div className="inline-flex rounded-md border border-line bg-base p-0.5" role="tablist">
        {MODES.map((m) => {
          const active = m.id === tab
          return (
            <button
              key={m.id}
              role="tab"
              aria-selected={active}
              onClick={() => onTab(m.id)}
              className={
                'rounded px-3 py-1.5 text-left transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-lava ' +
                (active ? 'bg-surface-2 text-ink' : 'text-ink-dim hover:text-ink')
              }
            >
              <span className="flex items-center gap-1.5 text-xs font-semibold">
                {active && <span className="h-1.5 w-1.5 rounded-full bg-lava" />}
                {m.label}
              </span>
            </button>
          )
        })}
      </div>

      {/* securable gets its own full-width row so long 3-part names never truncate */}
      <ObjectPicker tab={tab} value={securable} onChange={onSecurable} />

      <ActionPicker actions={actions} selectedId={actionId} onSelect={onAction} />

      <NegativeTestToggle value={negativeTest} onChange={onNegativeTest} />

      {!canGrant && selected && (
        <p className="rounded-md border border-line bg-base px-3 py-2 text-xs text-ink-faint">
          Workspace-object ACLs aren't set via SQL GRANT. This action only runs the effective
          permission-level check as the SP.
        </p>
      )}

      {/* 1·2·3 action flow */}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        <button
          onClick={onApply}
          disabled={!ready || busy || !canGrant}
          className="rounded-md bg-lava px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-lava-dim disabled:opacity-40"
        >
          1 · Apply to SP
        </button>
        <span className="text-ink-faint" aria-hidden="true">→</span>
        <button
          onClick={onAttempt}
          disabled={!ready || busy}
          className="rounded-md border border-line bg-surface-2 px-4 py-2 text-sm font-semibold text-ink transition-colors hover:border-ink-faint disabled:opacity-40"
        >
          2 · Attempt as SP
        </button>
        <span className="text-ink-faint" aria-hidden="true">→</span>
        <button
          onClick={onRevoke}
          disabled={!ready || busy || !canGrant}
          className="rounded-md border border-line bg-surface px-4 py-2 text-sm font-medium text-ink-dim transition-colors hover:text-ink disabled:opacity-40"
        >
          3 · Revoke
        </button>
        <button
          onClick={onReset}
          disabled={busy}
          className="ml-auto rounded-md px-3 py-2 text-xs font-medium text-ink-faint hover:text-ink disabled:opacity-40"
        >
          Reset SP
        </button>
      </div>
    </div>
  )
}
