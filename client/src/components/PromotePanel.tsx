import { useState } from 'react'
import { promote } from '../api'
import type { PromoteInfo } from '../types'

interface PromotePanelProps {
  actionId: string | null
  securable: string
  disabled: boolean
}

export function PromotePanel({ actionId, securable, disabled }: PromotePanelProps) {
  const [principal, setPrincipal] = useState('')
  const [info, setInfo] = useState<PromoteInfo | null>(null)
  const [copied, setCopied] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function build() {
    if (!actionId || !securable || !principal) return
    setErr(null)
    try {
      setInfo(await promote(actionId, securable, principal))
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to build promote info')
    }
  }

  async function copy() {
    if (!info) return
    await navigator.clipboard.writeText(info.grant_sql)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="rounded-lg border border-line bg-surface p-5">
      <h3 className="text-sm font-semibold text-ink">Promote to a real user / group</h3>
      <p className="mt-1 text-xs text-ink-faint">
        This app never grants to real principals. Once a test passes, promote in Unity Catalog:
        copy the validated SQL, or open UC and grant it natively.
      </p>

      <div className="mt-3 flex gap-2">
        <input
          type="text"
          value={principal}
          disabled={disabled}
          onChange={(e) => setPrincipal(e.target.value)}
          placeholder="analyst@corp.com  or  group-name"
          spellCheck={false}
          className="flex-1 rounded-md border border-line bg-base px-3 py-2 font-mono text-sm text-ink placeholder:text-ink-faint focus:border-lava focus:outline-none disabled:opacity-50"
        />
        <button
          onClick={build}
          disabled={disabled || !principal}
          className="rounded-md border border-line bg-surface-2 px-3 py-2 text-sm font-medium text-ink hover:border-ink-faint disabled:opacity-40"
        >
          Build grant
        </button>
      </div>

      {err && <p className="mt-2 text-xs text-fail">{err}</p>}

      {info && (
        <div className="mt-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wide text-ink-dim">
              Validated GRANT SQL
            </span>
            <button
              onClick={copy}
              className="rounded bg-surface-2 px-2 py-1 font-mono text-[11px] text-ink-dim hover:text-ink"
            >
              {copied ? 'copied ✓' : 'copy'}
            </button>
          </div>
          <pre className="overflow-auto rounded-md border border-line bg-base p-3 font-mono text-xs text-ink">
            {info.grant_sql}
          </pre>
          <a
            href={info.uc_deep_link}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-md bg-lava px-3 py-2 text-sm font-semibold text-white hover:bg-lava-dim"
          >
            Open in Unity Catalog →
          </a>
        </div>
      )}
    </div>
  )
}
