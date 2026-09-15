import type { ActionDescriptor } from '../types'

interface ActionPickerProps {
  actions: ActionDescriptor[]
  selectedId: string | null
  onSelect: (id: string) => void
}

export function ActionPicker({ actions, selectedId, onSelect }: ActionPickerProps) {
  return (
    <div>
      <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-ink-dim">
        Action to test
      </span>
      <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
        {actions.map((a) => {
          const active = a.id === selectedId
          const guarded = a.side_effect === 'write-guarded'
          return (
            <button
              key={a.id}
              onClick={() => onSelect(a.id)}
              aria-pressed={active}
              className={
                'flex items-center justify-between rounded-md border px-3 py-2 text-left text-sm transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-lava ' +
                (active
                  ? 'border-lava bg-lava/10 text-ink'
                  : 'border-line bg-surface text-ink-dim hover:border-ink-faint hover:text-ink')
              }
            >
              <span className="font-medium">{a.label}</span>
              {guarded && (
                <span className="ml-2 shrink-0 rounded bg-warn/15 px-1.5 py-0.5 font-mono text-[10px] font-medium uppercase text-warn">
                  guarded
                </span>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}
