import { useEffect, useMemo, useState } from 'react'
import { getScenarios, runScenario, saveScenario } from '../api'
import { useStore } from '../store'
import type { MatrixResult, NodeType, Scenario, ScenarioItem } from '../types'
import { getGrantableActions } from '../lib/selectAction'
import { fillScenarioRowWithNode } from '../lib/fillScenarioRow'
import { ExplorerPanel } from './ExplorerPanel'
import { ResultMatrix } from './ResultMatrix'
import { ScenarioBuilder } from './ScenarioBuilder'

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
  const [explorerHint, setExplorerHint] = useState<string | null>(null)
  const [explorerOpen, setExplorerOpen] = useState(true)

  const grantable = useMemo(() => getGrantableActions(actions, 'uc-data'), [actions])

  useEffect(() => {
    getScenarios()
      .then((r) => setScenarios(r.scenarios))
      .catch(() => setScenarios([]))
  }, [setScenarios])

  function onExplorerPick(path: string, type: NodeType) {
    const { newItems, hint } = fillScenarioRowWithNode(items, path, type, grantable)
    setItems(newItems)
    if (hint) {
      setExplorerHint(hint)
      window.setTimeout(() => setExplorerHint(null), 3000)
    }
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
      <ExplorerPanel
        isOpen={explorerOpen}
        onToggle={() => setExplorerOpen(!explorerOpen)}
        onPick={onExplorerPick}
        hint="Click an object to add it as a privilege row."
      />

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
        {explorerHint && (
          <p className="rounded-md border border-warn/30 bg-warn/10 px-3 py-2 text-xs text-warn">
            {explorerHint}
          </p>
        )}
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
