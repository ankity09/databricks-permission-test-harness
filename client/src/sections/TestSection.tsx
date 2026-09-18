import { useMemo } from 'react'
import { applyGrant, probe as runProbe, resetSp, revokeGrant } from '../api'
import { ConfigHeader } from '../components/ConfigHeader'
import { ResultStage } from '../components/ResultStage'
import { useStore } from '../store'

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
    <div className="space-y-5">
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
  )
}
