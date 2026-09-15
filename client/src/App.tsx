import { useEffect, useMemo } from 'react'
import {
  applyGrant,
  getActions,
  getMe,
  probe as runProbe,
  resetSp,
  revokeGrant,
} from './api'
import { ActionPicker } from './components/ActionPicker'
import { ChatDock } from './components/ChatDock'
import { IdentityBanner } from './components/IdentityBanner'
import { NegativeTestToggle } from './components/NegativeTestToggle'
import { ObjectPicker } from './components/ObjectPicker'
import { PromotePanel } from './components/PromotePanel'
import { ResultPanel } from './components/ResultPanel'
import { ScenariosTab } from './components/ScenariosTab'
import { ActivityTab } from './components/ActivityTab'
import { TabShell } from './components/TabShell'
import { useStore } from './store'

function errMsg(e: unknown): string {
  if (e && typeof e === 'object' && 'response' in e) {
    // axios error
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

export default function App() {
  const {
    theme,
    toggleTheme,
    me,
    meError,
    setMe,
    actions,
    setActions,
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
    activity,
    logActivity,
    dockWidth,
    dockCollapsed,
  } = useStore()

  useEffect(() => {
    getActions().then(setActions).catch(() => setActions([]))
    getMe()
      .then((m) => setMe(m))
      .catch((e) => setMe(null, errMsg(e)))
  }, [setActions, setMe])

  const tabActions = useMemo(() => actions.filter((a) => a.tab === tab), [actions, tab])
  const selected = useMemo(
    () => actions.find((a) => a.id === actionId) ?? null,
    [actions, actionId],
  )
  const canGrant = Boolean(selected && selected.grant_sql)
  const ready = Boolean(actionId && securable.trim())

  async function onApply() {
    if (!ready || !actionId) return
    setBusy(true)
    try {
      await applyGrant(actionId, securable)
      logActivity({ kind: 'apply', action_id: actionId, securable, detail: 'granted to SP' })
      setResult(null)
    } catch (e) {
      // A 400 is an input error (wrong securable level), NOT a grant-authority
      // failure. Keep them distinct so the explanation is accurate.
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
      const r = await runProbe(actionId, securable, {
        really_do: selected?.side_effect === 'write-guarded' ? false : false,
        negative_test: negativeTest,
      })
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
    <div
      style={{ paddingRight: dockCollapsed ? 0 : dockWidth }}
      className="transition-[padding] duration-150"
    >
      <ChatDock />
      <div className="mx-auto max-w-6xl px-6 py-8">
      {/* Header */}
      <header className="mb-6">
        <div className="flex items-center gap-2.5">
          <span className="h-6 w-1 rounded-full bg-lava" />
          <h1 className="text-2xl font-bold tracking-tight text-ink">Permission Test Harness</h1>
          <button
            onClick={toggleTheme}
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
            className="ml-auto flex items-center gap-1.5 rounded-md border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink-dim hover:border-ink-faint hover:text-ink"
          >
            <span aria-hidden="true">{theme === 'dark' ? '☀️' : '🌙'}</span>
            {theme === 'dark' ? 'Light' : 'Dark'}
          </button>
        </div>
        <p className="mt-1 font-mono text-xs text-ink-faint">
          Apply a candidate permission to the app SP (signed by your admin identity) → the SP
          attempts the action → see pass / fail with the real error. Grants to real users happen
          only in Unity Catalog.
        </p>
      </header>

      <div className="mb-5">
        <IdentityBanner me={me} error={meError} />
      </div>

      <div className="mb-5">
        <TabShell tab={tab} onChange={setTab} />
      </div>

      {tab === 'scenarios' ? (
        <ScenariosTab />
      ) : tab === 'activity' ? (
        <ActivityTab />
      ) : (
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-5">
        {/* Left: configure + act */}
        <div className="space-y-4 lg:col-span-3">
          <div className="space-y-4 rounded-lg border border-line bg-surface p-5">
            <ObjectPicker tab={tab} value={securable} onChange={setSecurable} />
            <ActionPicker actions={tabActions} selectedId={actionId} onSelect={setActionId} />
            <NegativeTestToggle value={negativeTest} onChange={setNegativeTest} />

            {!canGrant && selected && (
              <p className="rounded-md border border-line bg-base px-3 py-2 text-xs text-ink-faint">
                Workspace-object ACLs aren't set via SQL GRANT. This action only runs the effective
                permission-level check as the SP.
              </p>
            )}

            <div className="flex flex-wrap gap-2 pt-1">
              <button
                onClick={onApply}
                disabled={!ready || busy || !canGrant}
                className="rounded-md bg-lava px-4 py-2 text-sm font-semibold text-white hover:bg-lava-dim disabled:opacity-40"
              >
                1 · Apply to SP
              </button>
              <button
                onClick={onAttempt}
                disabled={!ready || busy}
                className="rounded-md border border-line bg-surface-2 px-4 py-2 text-sm font-semibold text-ink hover:border-ink-faint disabled:opacity-40"
              >
                2 · Attempt as SP
              </button>
              <button
                onClick={onRevoke}
                disabled={!ready || busy || !canGrant}
                className="rounded-md border border-line bg-surface px-4 py-2 text-sm font-medium text-ink-dim hover:text-ink disabled:opacity-40"
              >
                Revoke
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

          <ResultPanel result={result} busy={busy} />

          <PromotePanel actionId={actionId} securable={securable} disabled={!ready} />
        </div>

        {/* Right: activity log */}
        <aside className="lg:col-span-2">
          <div className="rounded-lg border border-line bg-surface p-5">
            <h3 className="mb-3 text-sm font-semibold text-ink">Session activity</h3>
            {activity.length === 0 ? (
              <p className="text-xs text-ink-faint">No actions yet this session.</p>
            ) : (
              <ul className="space-y-2">
                {activity.map((e, i) => (
                  <li key={i} className="flex items-start gap-2 font-mono text-[11px]">
                    <span className="mt-0.5 w-14 shrink-0 text-ink-faint">
                      {e.ts.slice(11, 19)}
                    </span>
                    <span className="w-14 shrink-0 uppercase text-lava">{e.kind}</span>
                    <span className="min-w-0 flex-1 text-ink-dim">
                      {e.action_id}
                      <span className="block break-all text-ink-faint">{e.securable}</span>
                      <span className="text-ink-dim">· {e.detail}</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>
      </div>
      )}
      </div>
    </div>
  )
}
