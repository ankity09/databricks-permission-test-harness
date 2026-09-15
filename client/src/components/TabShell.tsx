import type { Tab } from '../types'

interface TabShellProps {
  tab: Tab
  onChange: (t: Tab) => void
}

const TABS: { id: Tab; label: string; sub: string }[] = [
  { id: 'uc-data', label: 'Unity Catalog Data', sub: 'SP runs a real, safe probe' },
  { id: 'workspace', label: 'Workspace Objects', sub: 'effective permission check' },
  { id: 'scenarios', label: 'Scenarios', sub: 'batch role pass/fail matrix' },
  { id: 'activity', label: 'Activity', sub: 'durable history log' },
]

export function TabShell({ tab, onChange }: TabShellProps) {
  return (
    <div className="flex gap-1 rounded-lg border border-line bg-surface p-1" role="tablist">
      {TABS.map((t) => {
        const active = t.id === tab
        return (
          <button
            key={t.id}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(t.id)}
            className={
              'flex-1 rounded-md px-4 py-2.5 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-lava ' +
              (active
                ? 'bg-surface-2 text-ink'
                : 'text-ink-dim hover:text-ink hover:bg-surface-2/50')
            }
          >
            <div className="flex items-center gap-2 text-sm font-semibold">
              {active && <span className="h-1.5 w-1.5 rounded-full bg-lava" />}
              {t.label}
            </div>
            <div className="mt-0.5 font-mono text-[11px] text-ink-faint">{t.sub}</div>
          </button>
        )
      })}
    </div>
  )
}
