import { useEffect, useMemo, useState } from 'react'
import { getScenarios, runScenario, saveScenario } from '../api'
import { useStore } from '../store'
import type { MatrixResult, NodeType, Scenario, ScenarioItem } from '../types'
import { CatalogExplorer } from './CatalogExplorer'
import { ResultMatrix } from './ResultMatrix'
import { ScenarioBuilder } from './ScenarioBuilder'
import { ChevronIcon } from './icons'

/** Best-fit default action for a picked node type (matches the Test canvas). */
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

function errMsg(e: unknown): string {
  if (e && typeof e === 'object' && 'response' in e) {
    const anyE = e as { response?: { data?: { detail?: string } }; message?: string }
    return anyE.response?.data?.detail ?? anyE.message ?? 'Request failed'
  }
  return e instanceof Error ? e.message : 'Request failed'
}

export function ScenariosTab() {
  const { actions, scenarios, setScenarios } = useStore()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [items, setItems] = useState<ScenarioItem[]>([])
  const [matrix, setMatrix] = useState<MatrixResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [explorerOpen, setExplorerOpen] = useState(true)

  const grantable = useMemo(
    () => actions.filter((a) => a.tab === 'uc-data' && a.grant_sql),
    [actions],
  )

  useEffect(() => {
    getScenarios()
      .then((r) => setScenarios(r.scenarios))
      .catch(() => setScenarios([]))
  }, [setScenarios])

  // Picking a node from the side explorer appends a privilege row (or fills the
  // last empty row's securable) with the best-fit action for the node type.
  function onExplorerPick(path: string, type: NodeType) {
    const wanted = actionForType(type)
    const action_id = wanted && grantable.some((a) => a.id === wanted) ? wanted : grantable[0]?.id ?? ''
    setItems((prev) => {
      const lastEmpty = prev.length > 0 && !prev[prev.length - 1].securable.trim()
      if (lastEmpty) {
        return prev.map((it, i) =>
          i === prev.length - 1 ? { action_id: it.action_id || action_id, securable: path } : it,
        )
      }
      return [...prev, { action_id, securable: path }]
    })
  }

  const seeds = scenarios.filter((s) => s.is_seed)

  function loadSeed(s: Scenario) {
    setName(s.name)
    setDescription(s.description ?? '')
    setItems(s.items.map((it) => ({ ...it })))
    setMatrix(null)
    setNote(null)
  }

  async function onRun() {
    setBusy(true)
    setNote(null)
    try {
      const m = await runScenario(items)
      setMatrix(m)
    } catch (e) {
      setNote(errMsg(e))
    } finally {
      setBusy(false)
    }
  }

  async function onSave() {
    setBusy(true)
    setNote(null)
    try {
      await saveScenario({ name, description, items })
      const r = await getScenarios()
      setScenarios(r.scenarios)
      setNote(`Saved "${name}".`)
    } catch (e) {
      setNote(errMsg(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex gap-5">
      {/* persistent catalog explorer — picking a node adds a privilege row */}
      {explorerOpen ? (
        <aside className="sticky top-[73px] hidden h-[calc(100vh-96px)] w-64 shrink-0 flex-col rounded-lg border border-line bg-surface p-3 lg:flex">
          <div className="mb-2 flex items-center gap-2">
            <span className="h-4 w-1 rounded-full bg-lava" />
            <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-dim">Catalog</h3>
            <button
              onClick={() => setExplorerOpen(false)}
              aria-label="Collapse catalog explorer"
              title="Collapse"
              className="ml-auto rounded p-0.5 text-ink-faint hover:text-ink"
            >
              <ChevronIcon className="h-3.5 w-3.5 rotate-180" />
            </button>
          </div>
          <p className="mb-2 text-[11px] leading-snug text-ink-faint">
            Click an object to add it as a privilege row.
          </p>
          <CatalogExplorer onPick={onExplorerPick} />
        </aside>
      ) : (
        <button
          onClick={() => setExplorerOpen(true)}
          aria-label="Open catalog explorer"
          title="Open catalog explorer"
          className="sticky top-[73px] hidden h-9 shrink-0 items-center rounded-lg border border-line bg-surface px-2 text-ink-faint hover:text-ink lg:flex"
        >
          <ChevronIcon className="h-3.5 w-3.5" />
        </button>
      )}

      <div className="min-w-0 flex-1 space-y-4">
        <ScenarioBuilder
          actions={actions}
          seeds={seeds}
          name={name}
          description={description}
          items={items}
          busy={busy}
          onName={setName}
          onDescription={setDescription}
          onItems={setItems}
          onLoadSeed={loadSeed}
          onSave={onSave}
          onRun={onRun}
        />
        {note && (
          <p className="rounded-md border border-line bg-surface px-3 py-2 text-xs text-ink-dim">
            {note}
          </p>
        )}
        <ResultMatrix matrix={matrix} />
      </div>
    </div>
  )
}
