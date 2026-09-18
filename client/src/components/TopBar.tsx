import { useStore } from '../store'
import type { MeResponse } from '../types'
import { IdentityChip } from './IdentityChip'
import { MoonIcon, SearchIcon, SunIcon } from './icons'

interface TopBarProps {
  me: MeResponse | null
  meError: string | null
}

const SECTION_TITLE: Record<string, string> = {
  home: 'Overview',
  test: 'Permission Test',
  scenarios: 'Role Scenarios',
  activity: 'Activity Log',
}

/**
 * Thin top context bar: section title, a global securable jump (routes to the
 * Test canvas with the entered object), the identity chip, and theme toggle.
 */
export function TopBar({ me, meError }: TopBarProps) {
  const { theme, toggleTheme, section, securable, setSecurable, setSection } = useStore()

  function onJump(e: React.FormEvent) {
    e.preventDefault()
    if (securable.trim()) setSection('test')
  }

  return (
    <header className="sticky top-0 z-20 flex items-center gap-4 border-b border-line bg-base/80 px-6 py-3 backdrop-blur">
      <h1 className="text-sm font-semibold tracking-tight text-ink">
        {SECTION_TITLE[section] ?? 'Permission Test Harness'}
      </h1>

      <form onSubmit={onJump} className="ml-2 hidden items-center md:flex">
        <div className="flex items-center gap-2 rounded-md border border-line bg-surface px-2.5 py-1.5 focus-within:border-ink-faint">
          <SearchIcon className="h-3.5 w-3.5 text-ink-faint" />
          <input
            value={securable}
            onChange={(e) => setSecurable(e.target.value)}
            placeholder="jump to catalog.schema.object"
            spellCheck={false}
            className="w-64 bg-transparent font-mono text-xs text-ink placeholder:text-ink-faint focus:outline-none"
          />
        </div>
      </form>

      <div className="ml-auto flex items-center gap-3">
        <IdentityChip me={me} error={meError} />
        <button
          onClick={toggleTheme}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          className="flex items-center gap-1.5 rounded-md border border-line bg-surface px-2.5 py-1.5 text-xs font-medium text-ink-dim hover:border-ink-faint hover:text-ink"
        >
          {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
        </button>
      </div>
    </header>
  )
}
