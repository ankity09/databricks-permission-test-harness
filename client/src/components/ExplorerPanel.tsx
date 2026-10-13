import { useMediaQuery } from '../hooks/useMediaQuery'
import { CatalogExplorer } from './CatalogExplorer'
import { ChevronIcon } from './icons'
import type { NodeType } from '../types'

interface ExplorerPanelProps {
  isOpen: boolean
  onToggle: () => void
  onPick: (path: string, type: NodeType) => void
  selectedPath?: string
  hint?: string
}

export function ExplorerPanel({ isOpen, onToggle, onPick, selectedPath, hint }: ExplorerPanelProps) {
  // Only show at lg+ breakpoint (1024px)
  const isLg = useMediaQuery('(min-width: 1024px)')

  if (!isLg) return null

  if (!isOpen) {
    return (
      <button
        onClick={onToggle}
        aria-label="Open catalog explorer"
        title="Open catalog explorer"
        className="sticky top-[73px] h-9 shrink-0 items-center rounded-lg border border-line bg-surface px-2 text-ink-faint hover:text-ink"
      >
        <ChevronIcon className="h-3.5 w-3.5" />
      </button>
    )
  }

  return (
    <aside className="sticky top-[73px] h-[calc(100vh-96px)] w-64 shrink-0 flex-col rounded-lg border border-line bg-surface p-3">
      <div className="mb-2 flex items-center gap-2">
        <span className="h-4 w-1 rounded-full bg-lava" />
        <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-dim">Catalog</h3>
        <button
          onClick={onToggle}
          aria-label="Collapse catalog explorer"
          title="Collapse"
          className="ml-auto rounded p-0.5 text-ink-faint hover:text-ink"
        >
          <ChevronIcon className="h-3.5 w-3.5 rotate-180" />
        </button>
      </div>
      {hint && <p className="mb-2 text-[11px] leading-snug text-ink-faint">{hint}</p>}
      <div className="min-h-0 flex-1 overflow-hidden">
        <CatalogExplorer onPick={onPick} selectedPath={selectedPath} />
      </div>
    </aside>
  )
}
