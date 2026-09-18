import { useCallback, useEffect, useRef, useState } from 'react'
import { browseCatalog, searchCatalog } from '../api'
import type { BrowseNode, NodeType, SearchHit } from '../types'
import { CheckIcon, ChevronIcon, CopyIcon, NodeGlyph, SearchIcon } from './icons'

/** A hover-revealed button that copies a node's full path to the clipboard. */
function CopyPathButton({ path }: { path: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={(e) => {
        e.stopPropagation()
        void navigator.clipboard.writeText(path).then(() => {
          setCopied(true)
          window.setTimeout(() => setCopied(false), 1200)
        })
      }}
      aria-label={`Copy ${path}`}
      title="Copy full path"
      className={
        'shrink-0 rounded p-1 transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-lava ' +
        (copied
          ? 'text-pass'
          : 'text-ink-faint opacity-0 hover:text-ink group-hover:opacity-100 focus-visible:opacity-100')
      }
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
  [path: string]: { open: boolean; loading: boolean; children?: BrowseNode[] }
}

function levelFor(type: NodeType): 'catalog' | 'schema' | null {
  if (type === 'catalog') return 'catalog'
  if (type === 'schema') return 'schema'
  return null // leaves don't expand
}

/**
 * Unity-Catalog-style explorer. Lazily browses catalog → schema → object under
 * the OBO admin's visibility, with server-side name search across all catalogs.
 * Picking a node reports its full path + type to the parent (fills a securable
 * field, etc.). Read-only: it never grants or runs anything as the SP.
 */
export function CatalogExplorer({ onPick, selectedPath, dense }: CatalogExplorerProps) {
  const [roots, setRoots] = useState<BrowseNode[] | null>(null)
  const [tree, setTree] = useState<TreeState>({})
  const [rootError, setRootError] = useState<string | null>(null)

  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<SearchHit[] | null>(null)
  const [searching, setSearching] = useState(false)
  const debounce = useRef<number | null>(null)

  // initial catalog load
  useEffect(() => {
    browseCatalog('root')
      .then(setRoots)
      .catch((e) => {
        setRoots([])
        setRootError(e instanceof Error ? e.message : 'Failed to list catalogs')
      })
  }, [])

  // debounced server-side search
  useEffect(() => {
    if (debounce.current) window.clearTimeout(debounce.current)
    const q = query.trim()
    if (q.length < 2) {
      setHits(null)
      setSearching(false)
      return
    }
    setSearching(true)
    debounce.current = window.setTimeout(() => {
      searchCatalog(q, 30)
        .then(setHits)
        .catch(() => setHits([]))
        .finally(() => setSearching(false))
    }, 300)
    return () => {
      if (debounce.current) window.clearTimeout(debounce.current)
    }
  }, [query])

  const toggle = useCallback(
    async (node: BrowseNode) => {
      const lvl = levelFor(node.type)
      if (!lvl) {
        onPick(node.path, node.type)
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
      setTree((t) => ({ ...t, [node.path]: { open: true, loading: true } }))
      try {
        const children = await browseCatalog(lvl, node.path)
        setTree((t) => ({ ...t, [node.path]: { open: true, loading: false, children } }))
      } catch {
        setTree((t) => ({ ...t, [node.path]: { open: true, loading: false, children: [] } }))
      }
    },
    [tree, onPick],
  )

  function renderNode(node: BrowseNode, depth: number) {
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
              onClick={() => onPick(node.path, node.type)}
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
            ) : (
              (st.children ?? []).map((c) => renderNode(c, depth + 1))
            )}
            {st.children && st.children.length === 0 && !st.loading && (
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
                    onClick={() => onPick(h.path, h.type)}
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
          roots.map((n) => renderNode(n, 0))
        )}
      </div>
    </div>
  )
}
