import { useMemo, useState } from 'react'
import { applyGrant, probe as runProbe, resetSp, revokeGrant } from '../api'
import { CatalogExplorer } from '../components/CatalogExplorer'
import { ConfigHeader } from '../components/ConfigHeader'
import { ResultStage } from '../components/ResultStage'
import { ChevronIcon } from '../components/icons'
import { useStore } from '../store'
import type { NodeType } from '../types'

/** Map a picked node type to the best-fit default action id, when present. */
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

function errStatus(e: unknown): number | undefined {
  if (e && typeof e === 'object' && 'response' in e) {
    return (e as { response?: { status?: number } }).response?.status
  }
  return undefined
}

/** The core Test canvas: sticky config header + result stage pipeline. */
export function TestSection() {
  const {
    actions,
    tab,
    setTab,
    securable,
    setSecurable,
    actionId,
    setActionId,
    negativeTest,
    setNegativeTest,
    result,
    setResult,
    busy,
    setBusy,
    logActivity,
  } = useStore()

  const tabActions = useMemo(() => actions.filter((a) => a.tab === tab), [actions, tab])
  const selected = useMemo(() => actions.find((a) => a.id === actionId) ?? null, [actions, actionId])
  const canGrant = Boolean(selected && selected.grant_sql)
  const ready = Boolean(actionId && securable.trim())
  const [explorerOpen, setExplorerOpen] = useState(true)

  function onPick(path: string, type: NodeType) {
    setSecurable(path)
    // best-fit action auto-select, only if it exists on the current tab
    const wanted = actionForType(type)
    if (wanted && tabActions.some((a) => a.id === wanted)) setActionId(wanted)
  }

  async function onApply() {
    if (!ready || !actionId) return
    setBusy(true)
    try {
      await applyGrant(actionId, securable)
      logActivity({ kind: 'apply', action_id: actionId, securable, detail: 'granted to SP' })
      setResult(null)
    } catch (e) {
      const status = errStatus(e) === 400 ? 'bad_input' : 'grant_failed'
      setResult({ status, detail: errMsg(e), raw_error: errMsg(e) })
    } finally {
      setBusy(false)
    }
  }

  async function onAttempt() {
    if (!ready || !actionId) return
    setBusy(true)
    try {
      const r = await runProbe(actionId, securable, { really_do: false, negative_test: negativeTest })
      setResult(r)
      logActivity({ kind: 'probe', action_id: actionId, securable, detail: r.status })
    } catch (e) {
      setResult({ status: 'error', detail: errMsg(e), raw_error: errMsg(e) })
    } finally {
      setBusy(false)
    }
  }

  async function onRevoke() {
    if (!ready || !actionId) return
    setBusy(true)
    try {
      await revokeGrant(actionId, securable)
      logActivity({ kind: 'revoke', action_id: actionId, securable, detail: 'revoked from SP' })
      setResult(null)
    } catch (e) {
      setResult({ status: 'error', detail: errMsg(e), raw_error: errMsg(e) })
    } finally {
      setBusy(false)
    }
  }

  async function onReset() {
    setBusy(true)
    try {
      await resetSp()
      logActivity({ kind: 'reset', action_id: '*', securable: '*', detail: 'reset SP grants' })
      setResult(null)
    } catch (e) {
      setResult({ status: 'error', detail: errMsg(e), raw_error: errMsg(e) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex gap-5">
      {/* collapsible catalog explorer */}
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
          <CatalogExplorer onPick={onPick} selectedPath={securable} />
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

      <div className="min-w-0 flex-1 space-y-5">
        <ConfigHeader
          tab={tab}
          onTab={setTab}
          securable={securable}
          onSecurable={setSecurable}
          actions={tabActions}
          actionId={actionId}
          onAction={setActionId}
          negativeTest={negativeTest}
          onNegativeTest={setNegativeTest}
          canGrant={canGrant}
          selected={selected}
          ready={ready}
          busy={busy}
          onApply={onApply}
          onAttempt={onAttempt}
          onRevoke={onRevoke}
          onReset={onReset}
        />
        <ResultStage
          tab={tab}
          result={result}
          busy={busy}
          securable={securable}
          actionId={actionId}
          ready={ready}
        />
      </div>
    </div>
  )
}
