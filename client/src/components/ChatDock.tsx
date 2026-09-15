import { useCallback, useEffect, useRef, useState } from 'react'
import { agentChat } from '../api'
import { useStore } from '../store'

function errMsg(e: unknown): string {
  if (e && typeof e === 'object' && 'response' in e) {
    const anyE = e as { response?: { data?: { detail?: string } }; message?: string }
    return anyE.response?.data?.detail ?? anyE.message ?? 'Request failed'
  }
  return e instanceof Error ? e.message : 'Request failed'
}

export function ChatDock() {
  const {
    dockWidth,
    setDockWidth,
    dockCollapsed,
    toggleDock,
    chat,
    pushMessage,
    chatBusy,
    setChatBusy,
    tab,
    securable,
  } = useStore()
  const [input, setInput] = useState('')
  const dragging = useRef(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  const onMouseMove = useCallback(
    (e: MouseEvent) => {
      if (!dragging.current) return
      // dock is anchored to the right edge; width grows as the pointer moves left
      setDockWidth(window.innerWidth - e.clientX)
    },
    [setDockWidth],
  )

  useEffect(() => {
    const stop = () => {
      dragging.current = false
      document.body.style.userSelect = ''
    }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', stop)
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', stop)
    }
  }, [onMouseMove])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [chat, chatBusy])

  async function send() {
    const text = input.trim()
    if (!text || chatBusy) return
    setInput('')
    const context = `[context: tab=${tab}${securable ? `, securable=${securable}` : ''}]`
    pushMessage({ role: 'user', content: text })
    setChatBusy(true)
    try {
      const history = [...chat, { role: 'user' as const, content: `${text}\n${context}` }]
      const r = await agentChat(history)
      pushMessage({ role: 'assistant', content: r.content })
    } catch (e) {
      pushMessage({ role: 'assistant', content: `Error: ${errMsg(e)}` })
    } finally {
      setChatBusy(false)
    }
  }

  if (dockCollapsed) {
    return (
      <button
        onClick={toggleDock}
        aria-label="Open assistant"
        title="Open assistant"
        className="fixed right-0 top-1/2 z-20 -translate-y-1/2 rounded-l-md border border-r-0 border-line bg-surface px-2 py-4 text-xs font-medium text-ink-dim hover:text-ink"
      >
        <span className="[writing-mode:vertical-rl]">Assistant</span>
      </button>
    )
  }

  return (
    <aside
      className="fixed right-0 top-0 z-20 flex h-full flex-col border-l border-line bg-surface"
      style={{ width: dockWidth }}
    >
      {/* drag handle */}
      <div
        role="separator"
        aria-orientation="vertical"
        onMouseDown={() => {
          dragging.current = true
          document.body.style.userSelect = 'none'
        }}
        className="absolute left-0 top-0 h-full w-1 cursor-col-resize bg-transparent hover:bg-lava/40"
      />
      <header className="flex items-center gap-2 border-b border-line px-4 py-3">
        <span className="h-4 w-1 rounded-full bg-lava" />
        <h3 className="text-sm font-semibold text-ink">Permissions Assistant</h3>
        <button
          onClick={toggleDock}
          aria-label="Collapse assistant"
          title="Collapse"
          className="ml-auto rounded px-2 py-1 text-xs text-ink-faint hover:text-ink"
        >
          ✕
        </button>
      </header>

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {chat.length === 0 && (
          <p className="font-mono text-xs text-ink-faint">
            Ask about Unity Catalog permissions, or ask me to run a test on the app SP. I can
            never grant to a real user; I hand you Unity Catalog steps to promote.
          </p>
        )}
        {chat.map((m, i) => (
          <div
            key={i}
            className={
              m.role === 'user'
                ? 'ml-auto max-w-[85%] rounded-lg bg-surface-2 px-3 py-2 text-sm text-ink'
                : 'mr-auto max-w-[90%] rounded-lg border border-line bg-base px-3 py-2 text-sm text-ink-dim'
            }
          >
            <span className="whitespace-pre-wrap break-words">{m.content}</span>
          </div>
        ))}
        {chatBusy && <div className="mr-auto text-xs text-ink-faint">Thinking…</div>}
      </div>

      <div className="border-t border-line p-3">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void send()
              }
            }}
            rows={2}
            placeholder="Ask the assistant…"
            className="flex-1 resize-none rounded-md border border-line bg-base px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-lava focus:outline-none"
          />
          <button
            onClick={() => void send()}
            disabled={chatBusy || !input.trim()}
            className="self-end rounded-md bg-lava px-3 py-2 text-sm font-semibold text-white hover:bg-lava-dim disabled:opacity-40"
          >
            Send
          </button>
        </div>
      </div>
    </aside>
  )
}
