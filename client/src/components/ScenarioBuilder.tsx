import { useMemo, useState } from 'react'
import type { ActionDescriptor, NodeType, Scenario, ScenarioItem } from '../types'
import { CatalogExplorer } from './CatalogExplorer'
import { SearchIcon } from './icons'

interface Props {
  actions: ActionDescriptor[]
  seeds: Scenario[]
  name: string
  description: string
  items: ScenarioItem[]
  busy: boolean
  onName: (v: string) => void
  onDescription: (v: string) => void
  onItems: (items: ScenarioItem[]) => void
  onLoadSeed: (s: Scenario) => void
  onSave: () => void
  onRun: () => void
}

export function ScenarioBuilder(props: Props) {
  const {
    actions,
    seeds,
    name,
    description,
    items,
    busy,
    onName,
    onDescription,
    onItems,
    onLoadSeed,
    onSave,
    onRun,
  } = props

  // Only UC-data actions are batch-runnable (workspace ACLs have no grant SQL).
  const grantable = useMemo(
    () => actions.filter((a) => a.tab === 'uc-data' && a.grant_sql),
    [actions],
  )

  const [browseRow, setBrowseRow] = useState<number | null>(null)

  function setItem(i: number, patch: Partial<ScenarioItem>) {
    onItems(items.map((it, idx) => (idx === i ? { ...it, ...patch } : it)))
  }

  function actionForType(type: NodeType): string | null {
    switch (type) {
      case 'catalog':
        return 'uc.catalog.use'
      case 'schema':
        return 'uc.schema.use'
      case 'table':
      case 'view':
        return 'uc.table.select'
      case 'function':
        return 'uc.function.execute'
      default:
        return null
    }
  }

  function pickForRow(i: number, path: string, type: NodeType) {
    const wanted = actionForType(type)
    const patch: Partial<ScenarioItem> = { securable: path }
    if (wanted && grantable.some((a) => a.id === wanted)) patch.action_id = wanted
    setItem(i, patch)
    setBrowseRow(null)
  }
  function addRow() {
    onItems([...items, { action_id: grantable[0]?.id ?? '', securable: '' }])
  }
  function removeRow(i: number) {
    onItems(items.filter((_, idx) => idx !== i))
  }

  const canRun = items.length > 0 && items.every((it) => it.action_id && it.securable.trim())

  return (
    <div className="space-y-4 rounded-lg border border-line bg-surface p-5">
      {/* seed templates */}
      <div>
        <label className="mb-1.5 block font-mono text-[11px] uppercase text-ink-faint">
          Start from a role template
        </label>
        <div className="flex flex-wrap gap-2">
          {seeds.map((s) => (
            <button
              key={s.id}
              onClick={() => onLoadSeed(s)}
              title={s.description}
              className="rounded-md border border-line bg-base px-3 py-1.5 text-xs font-medium text-ink-dim hover:border-ink-faint hover:text-ink"
            >
              {s.name}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label className="mb-1.5 block font-mono text-[11px] uppercase text-ink-faint">
            Scenario name
          </label>
          <input
            value={name}
            onChange={(e) => onName(e.target.value)}
            placeholder="e.g. Data Analyst"
            className="w-full rounded-md border border-line bg-base px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-lava focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1.5 block font-mono text-[11px] uppercase text-ink-faint">
            Description
          </label>
          <input
            value={description}
            onChange={(e) => onDescription(e.target.value)}
            placeholder="optional"
            className="w-full rounded-md border border-line bg-base px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-lava focus:outline-none"
          />
        </div>
      </div>

      <div className="space-y-2">
        <label className="block font-mono text-[11px] uppercase text-ink-faint">
          Privileges in this role
        </label>
        {items.map((it, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2">
            <select
              value={it.action_id}
              onChange={(e) => setItem(i, { action_id: e.target.value })}
              className="rounded-md border border-line bg-base px-2 py-2 text-sm text-ink focus:border-lava focus:outline-none"
            >
              {grantable.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.label}
                </option>
              ))}
            </select>
            <input
              value={it.securable}
              onChange={(e) => setItem(i, { securable: e.target.value })}
              placeholder="catalog.schema.table"
              className="min-w-0 flex-1 rounded-md border border-line bg-base px-3 py-2 font-mono text-sm text-ink placeholder:text-ink-faint focus:border-lava focus:outline-none"
            />
            <button
              onClick={() => setBrowseRow(browseRow === i ? null : i)}
              aria-label="Browse catalog for this privilege"
              aria-expanded={browseRow === i}
              title="Browse catalog"
              className={
                'rounded-md border px-2 py-2 transition-colors ' +
                (browseRow === i
                  ? 'border-lava bg-lava/10 text-lava'
                  : 'border-line bg-surface text-ink-dim hover:border-ink-faint hover:text-ink')
              }
            >
              <SearchIcon className="h-4 w-4" />
            </button>
            <button
              onClick={() => {
                removeRow(i)
                if (browseRow === i) setBrowseRow(null)
              }}
              aria-label="Remove"
              className="rounded px-2 py-1 text-ink-faint hover:text-lava"
            >
              ✕
            </button>
            {browseRow === i && (
              <div className="mt-2 w-full rounded-md border border-line bg-base p-2">
                <CatalogExplorer
                  dense
                  selectedPath={it.securable}
                  onPick={(path, type) => pickForRow(i, path, type)}
                />
              </div>
            )}
          </div>
        ))}
        <button
          onClick={addRow}
          disabled={grantable.length === 0}
          className="rounded-md border border-dashed border-line px-3 py-1.5 text-xs font-medium text-ink-dim hover:border-ink-faint hover:text-ink disabled:opacity-40"
        >
          + Add privilege
        </button>
      </div>

      <div className="flex flex-wrap gap-2 pt-1">
        <button
          onClick={onRun}
          disabled={!canRun || busy}
          className="rounded-md bg-lava px-4 py-2 text-sm font-semibold text-white hover:bg-lava-dim disabled:opacity-40"
        >
          Run scenario
        </button>
        <button
          onClick={onSave}
          disabled={!name.trim() || items.length === 0 || busy}
          className="rounded-md border border-line bg-surface-2 px-4 py-2 text-sm font-medium text-ink hover:border-ink-faint disabled:opacity-40"
        >
          Save scenario
        </button>
      </div>
      <p className="font-mono text-[11px] text-ink-faint">
        Runs as a batch: applies all grants to the SP, probes each, then revokes all. Real grants
        to users still happen only in Unity Catalog.
      </p>
    </div>
  )
}
