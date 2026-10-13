import { memo, useCallback, useEffect, useRef, useState } from 'react'
import { browseCatalog, searchCatalog } from '../api'
import type { BrowseNode, NodeType, SearchHit } from '../types'
import { cn } from '../lib/cn'
import { CheckIcon, ChevronIcon, CopyIcon, NodeGlyph, SearchIcon, RetryIcon } from './icons'

interface CopyPathButtonProps {
  path: string
}

/** A hover-revealed button that copies a node's full path to the clipboard. */
function CopyPathButton({ path }: CopyPathButtonProps) {
  const [copied, setCopied] = useState(false)
  const timerRef = useRef<number | null>(null)

  const handleCopy = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation()
      if (timerRef.current) clearTimeout(timerRef.current)
      void navigator.clipboard
        .writeText(path)
        .then(() => {
          setCopied(true)
          timerRef.current = window.setTimeout(() => setCopied(false), 1200)
        })
        .catch(() => {
          // Silently fail on clipboard rejection
        })
    },
    [path],
  )

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [])

  return (
    <button
      onClick={handleCopy}
      aria-label={`Copy ${path}`}
      title="Copy full path"
      className={cn(
        'shrink-0 rounded p-1 transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-lava',
        copied ? 'text-pass' : 'pointer-events-none text-ink-faint opacity-0 group-hover:pointer-events-auto group-hover:opacity-100 group-hover:text-ink group-focus-within:pointer-events-auto group-focus-within:opacity-100 group-focus-within:text-ink focus-visible:pointer-events-auto focus-visible:opacity-100',
      )}
    >
      {copied ? <CheckIcon className="h-3 w-3" /> : <CopyIcon className="h-3 w-3" />}
    </button>
  )
}

interface CatalogExplorerProps {
  /** Called when the user picks any node (leaf or container). */
  onPick: (path: string, type: NodeType) => void
  /** Optional: highlight the currently-selected path. */
  selectedPath?: string
  /** Compact variant for the per-row scenario popover. */
  dense?: boolean
}

interface TreeState {
  [path: string]: { open: boolean; loading: boolean; children?: BrowseNode[]; error?: string }
}

// Module-level browse cache: Map<level+parent, BrowseNode[]>
const browseCache = new Map<string, BrowseNode[]>()

function cacheKey(level: 'catalog' | 'schema', parent: string): string {
  return `${level}:${parent}`
}

function levelFor(type: NodeType): 'catalog' | 'schema' | null {
  if (type === 'catalog') return 'catalog'
  if (type === 'schema') return 'schema'
  return null // leaves don't expand
}

/**
 * Unity-Catalog-style explorer with search, caching, and error handling.
 */
function CatalogExplorerImpl({ onPick, selectedPath, dense }: CatalogExplorerProps) {
  const [roots, setRoots] = useState<BrowseNode[] | null>(null)
  const [tree, setTree] = useState<TreeState>({})
  const [rootError, setRootError] = useState<string | null>(null)

  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<SearchHit[] | null>(null)
  const [searching, setSearching] = useState(false)
  const debounceRef = useRef<number | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  // Stable onPick callback via useCallback
  const stableOnPick = useCallback(
    (path: string, type: NodeType) => onPick(path, type),
    [onPick],
  )

  // initial catalog load (use cache)
  useEffect(() => {
    const key = cacheKey('catalog', 'root')
    const cached = browseCache.get(key)
    if (cached) {
      // Defer to avoid setState-in-effect warning
      const timer = window.setTimeout(() => setRoots(cached), 0)
      return () => window.clearTimeout(timer)
    }

    browseCatalog('root')
      .then((nodes) => {
        browseCache.set(key, nodes)
        setRoots(nodes)
      })
      .catch((e) => {
        setRoots([])
        setRootError(e instanceof Error ? e.message : 'Failed to list catalogs')
      })
  }, [])

  // debounced server-side search with AbortController
  useEffect(() => {
    if (debounceRef.current) window.clearTimeout(debounceRef.current)
    if (abortControllerRef.current) abortControllerRef.current.abort()

    const q = query.trim()
    if (q.length < 2) {
      const timer = window.setTimeout(() => {
        setHits(null)
        setSearching(false)
      }, 0)
      return () => {
        window.clearTimeout(timer)
      }
    }

    debounceRef.current = window.setTimeout(() => {
      // Each request checks its OWN controller: a newer search aborts this one,
      // so a slow, stale response can never overwrite newer results.
      const controller = new AbortController()
      abortControllerRef.current = controller
      setSearching(true)
      searchCatalog(q, 30, controller.signal)
        .then((results) => {
          if (!controller.signal.aborted) setHits(results)
        })
        .catch(() => {
          if (!controller.signal.aborted) setHits([])
        })
        .finally(() => {
          if (!controller.signal.aborted) setSearching(false)
        })
    }, 300)

    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current)
      if (abortControllerRef.current) abortControllerRef.current.abort()
    }
  }, [query])

  const toggle = useCallback(
    async (node: BrowseNode) => {
      const lvl = levelFor(node.type)
      if (!lvl) {
        stableOnPick(node.path, node.type)
        return
      }

      const cur = tree[node.path]
      if (cur?.open) {
        setTree((t) => ({ ...t, [node.path]: { ...cur, open: false } }))
        return
      }
      if (cur?.children) {
        setTree((t) => ({ ...t, [node.path]: { ...cur, open: true } }))
        return
      }

      // Load from cache or fetch
      const key = cacheKey(lvl, node.path)
      const cached = browseCache.get(key)
      if (cached) {
        setTree((t) => ({ ...t, [node.path]: { open: true, loading: false, children: cached } }))
        return
      }

      setTree((t) => ({ ...t, [node.path]: { open: true, loading: true } }))
      try {
        const children = await browseCatalog(lvl, node.path)
        browseCache.set(key, children)
        setTree((t) => ({ ...t, [node.path]: { open: true, loading: false, children } }))
      } catch (e) {
        const errorMsg = e instanceof Error ? e.message : 'Failed to load'
        setTree((t) => ({ ...t, [node.path]: { open: true, loading: false, error: errorMsg } }))
      }
    },
    [tree, stableOnPick],
  )

  // Render tree node recursively - define as regular function to avoid initialization issues
  const renderNodeFn = (node: BrowseNode, depth: number) => {
    const st = tree[node.path]
    const isSelected = selectedPath === node.path
    return (
      <div key={node.path}>
        <div className="flex items-center">
          {node.expandable ? (
            <button
              onClick={() => void toggle(node)}
              aria-label={st?.open ? `Collapse ${node.name}` : `Expand ${node.name}`}
              className="shrink-0 rounded p-0.5 text-ink-faint hover:text-ink"
              style={{ marginLeft: depth * 12 }}
            >
              <ChevronIcon className={'h-3 w-3 transition-transform ' + (st?.open ? 'rotate-90' : '')} />
            </button>
          ) : (
            <span className="shrink-0" style={{ marginLeft: depth * 12 + 18 }} />
          )}
          <div
            className={
              'group flex min-w-0 flex-1 items-center gap-1.5 rounded pr-1 ' +
              (isSelected ? 'bg-lava/10' : 'hover:bg-surface-2/60')
            }
          >
            <button
              onClick={() => stableOnPick(node.path, node.type)}
              title={node.path}
              className={
                'flex min-w-0 flex-1 items-center gap-1.5 rounded px-1.5 py-1 text-left text-xs transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-lava ' +
                (isSelected ? 'text-ink' : 'text-ink-dim group-hover:text-ink')
              }
            >
              <NodeGlyph type={node.type} className={'h-3.5 w-3.5 shrink-0 ' + (isSelected ? 'text-lava' : 'text-ink-faint')} />
              <span className="truncate font-mono">{node.name}</span>
            </button>
            <CopyPathButton path={node.path} />
          </div>
        </div>
        {st?.open && (
          <div>
            {st.loading ? (
              <div className="py-1 pl-6 text-[11px] text-ink-faint" style={{ marginLeft: depth * 12 }}>
                loading…
              </div>
            ) : st.error ? (
              <div
                className="my-1 rounded-md border border-warn/30 bg-warn/5 py-1 pl-6 pr-2 text-[11px] text-warn"
                style={{ marginLeft: depth * 12 }}
              >
                <div className="mb-1">{st.error}</div>
                <button
                  onClick={() => void toggle(node)}
                  className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] hover:bg-warn/10"
                >
                  <RetryIcon className="h-2.5 w-2.5" />
                  Retry
                </button>
              </div>
            ) : (
              (st.children ?? []).map((c) => renderNodeFn(c, depth + 1))
            )}
            {st.children && st.children.length === 0 && !st.loading && !st.error && (
              <div className="py-1 text-[11px] text-ink-faint" style={{ marginLeft: (depth + 1) * 12 + 18 }}>
                empty
              </div>
            )}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className={'flex flex-col ' + (dense ? 'max-h-72' : 'h-full')}>
      {/* search */}
      <div className="mb-2 flex items-center gap-2 rounded-md border border-line bg-base px-2.5 py-1.5 focus-within:border-ink-faint">
        <SearchIcon className="h-3.5 w-3.5 text-ink-faint" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search all catalogs…"
          spellCheck={false}
          className="w-full bg-transparent font-mono text-xs text-ink placeholder:text-ink-faint focus:outline-none"
        />
      </div>

      <div className="min-h-0 flex-1 overflow-auto pr-1">
        {hits !== null ? (
          // search results
          <div>
            {searching && <div className="px-1.5 py-1 text-[11px] text-ink-faint">searching…</div>}
            {!searching && hits.length === 0 && (
              <div className="px-1.5 py-1 text-[11px] text-ink-faint">No matches.</div>
            )}
            {hits.map((h) => {
              const isSelected = selectedPath === h.path
              return (
                <div
                  key={h.path}
                  className={
                    'group flex w-full min-w-0 items-center gap-1.5 rounded pr-1 ' +
                    (isSelected ? 'bg-lava/10' : 'hover:bg-surface-2/60')
                  }
                >
                  <button
                    onClick={() => stableOnPick(h.path, h.type)}
                    title={h.path}
                    className={
                      'flex min-w-0 flex-1 items-center gap-1.5 rounded px-1.5 py-1 text-left text-xs transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-lava ' +
                      (isSelected ? 'text-ink' : 'text-ink-dim group-hover:text-ink')
                    }
                  >
                    <NodeGlyph type={h.type} className="h-3.5 w-3.5 shrink-0 text-ink-faint" />
                    <span className="truncate font-mono">{h.name}</span>
                    <span className="ml-auto truncate pl-2 font-mono text-[10px] text-ink-faint">{h.path}</span>
                  </button>
                  <CopyPathButton path={h.path} />
                </div>
              )
            })}
          </div>
        ) : roots === null ? (
          <div className="space-y-1.5">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-5 animate-pulse rounded bg-surface-2" />
            ))}
          </div>
        ) : rootError ? (
          <div className="px-1.5 py-1 text-[11px] text-warn">{rootError}</div>
        ) : (
          roots.map((n) => renderNodeFn(n, 0))
        )}
      </div>
    </div>
  )
}

export const CatalogExplorer = memo(CatalogExplorerImpl)
