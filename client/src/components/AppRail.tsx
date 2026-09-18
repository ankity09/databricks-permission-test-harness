import type { ReactNode } from 'react'
import type { Section } from '../store'
import { useStore } from '../store'
import { ActivityIcon, HomeIcon, ScenariosIcon, TestIcon } from './icons'

const ITEMS: { id: Section; label: string; Icon: (p: { className?: string }) => ReactNode }[] = [
  { id: 'home', label: 'Home', Icon: HomeIcon },
  { id: 'test', label: 'Test', Icon: TestIcon },
  { id: 'scenarios', label: 'Scenarios', Icon: ScenariosIcon },
  { id: 'activity', label: 'Activity', Icon: ActivityIcon },
]

/**
 * Slim left icon rail — the app's primary navigation. Expands on hover to
 * reveal labels. Active section is marked with a lava tick + accent.
 */
export function AppRail() {
  const { section, setSection, railExpanded, setRailExpanded } = useStore()

  return (
    <nav
      aria-label="Primary"
      onMouseEnter={() => setRailExpanded(true)}
      onMouseLeave={() => setRailExpanded(false)}
      className={
        'fixed left-0 top-0 z-30 flex h-full flex-col border-r border-line bg-surface py-3 transition-[width] duration-200 ease-out ' +
        (railExpanded ? 'w-52' : 'w-14')
      }
    >
      {/* brand mark */}
      <div className="mb-4 flex items-center gap-2.5 px-3.5">
        <span className="h-6 w-1.5 shrink-0 rounded-full bg-lava" />
        <span
          className={
            'whitespace-nowrap text-sm font-bold tracking-tight text-ink transition-opacity duration-150 ' +
            (railExpanded ? 'opacity-100' : 'opacity-0')
          }
        >
          Harness
        </span>
      </div>

      <ul className="flex flex-col gap-1 px-2">
        {ITEMS.map(({ id, label, Icon }) => {
          const active = id === section
          return (
            <li key={id}>
              <button
                onClick={() => setSection(id)}
                aria-current={active ? 'page' : undefined}
                aria-label={label}
                className={
                  'group relative flex w-full items-center gap-3 rounded-md px-2.5 py-2.5 text-left transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-lava ' +
                  (active
                    ? 'bg-surface-2 text-ink'
                    : 'text-ink-dim hover:bg-surface-2/60 hover:text-ink')
                }
              >
                {active && (
                  <span className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-lava" />
                )}
                <Icon className={'h-5 w-5 shrink-0 ' + (active ? 'text-lava' : '')} />
                <span
                  className={
                    'whitespace-nowrap text-sm font-medium transition-opacity duration-150 ' +
                    (railExpanded ? 'opacity-100' : 'pointer-events-none opacity-0')
                  }
                >
                  {label}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
