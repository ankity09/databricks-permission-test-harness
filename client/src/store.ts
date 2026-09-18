import { create } from 'zustand'
import type {
  ActionDescriptor,
  ActivityEntry,
  ActivityRow,
  ChatMessage,
  MeResponse,
  ProbeResult,
  Scenario,
  Tab,
} from './types'

type Theme = 'dark' | 'light'
export type Section = 'home' | 'test' | 'scenarios' | 'activity'

const THEME_KEY = 'pth-theme'
const DOCK_WIDTH_KEY = 'pth-dock-width'
const DEFAULT_DOCK_WIDTH = 380

function initialDockWidth(): number {
  if (typeof window === 'undefined') return DEFAULT_DOCK_WIDTH
  const stored = Number(window.localStorage.getItem(DOCK_WIDTH_KEY))
  return Number.isFinite(stored) && stored >= 280 && stored <= 720
    ? stored
    : DEFAULT_DOCK_WIDTH
}

function initialTheme(): Theme {
  if (typeof window === 'undefined') return 'dark'
  const stored = window.localStorage.getItem(THEME_KEY)
  if (stored === 'light' || stored === 'dark') return stored
  return 'dark'
}

function applyTheme(theme: Theme) {
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('data-theme', theme)
  }
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(THEME_KEY, theme)
  }
}

interface HarnessState {
  // theme
  theme: Theme
  toggleTheme: () => void

  // identity / OBO
  me: MeResponse | null
  meError: string | null
  setMe: (me: MeResponse | null, error?: string | null) => void

  // catalog
  actions: ActionDescriptor[]
  setActions: (a: ActionDescriptor[]) => void

  // primary navigation (left rail)
  section: Section
  setSection: (s: Section) => void
  railExpanded: boolean
  setRailExpanded: (v: boolean) => void

  // Test-canvas mode segmented control (UC data vs workspace objects)
  tab: Tab
  setTab: (t: Tab) => void
  securable: string
  setSecurable: (s: string) => void
  actionId: string | null
  setActionId: (id: string | null) => void
  negativeTest: boolean
  setNegativeTest: (v: boolean) => void

  // result
  result: ProbeResult | null
  setResult: (r: ProbeResult | null) => void
  busy: boolean
  setBusy: (b: boolean) => void

  // in-session activity log
  activity: ActivityEntry[]
  logActivity: (e: Omit<ActivityEntry, 'ts'>) => void

  // ---- v2 ----
  // chat dock
  dockWidth: number
  setDockWidth: (w: number) => void
  dockCollapsed: boolean
  toggleDock: () => void
  chat: ChatMessage[]
  pushMessage: (m: ChatMessage) => void
  chatBusy: boolean
  setChatBusy: (b: boolean) => void

  // scenarios
  scenarios: Scenario[]
  setScenarios: (s: Scenario[]) => void

  // durable activity feed
  activityRows: ActivityRow[]
  setActivityRows: (r: ActivityRow[]) => void
}

export const useStore = create<HarnessState>((set) => ({
  theme: initialTheme(),
  toggleTheme: () =>
    set((s) => {
      const next: Theme = s.theme === 'dark' ? 'light' : 'dark'
      applyTheme(next)
      return { theme: next }
    }),

  me: null,
  meError: null,
  setMe: (me, error = null) => set({ me, meError: error }),

  actions: [],
  setActions: (actions) => set({ actions }),

  section: 'home',
  setSection: (section) => set({ section }),
  railExpanded: false,
  setRailExpanded: (railExpanded) => set({ railExpanded }),

  tab: 'uc-data',
  setTab: (tab) => set({ tab, actionId: null, result: null }),
  securable: '',
  setSecurable: (securable) => set({ securable }),
  actionId: null,
  setActionId: (actionId) => set({ actionId, result: null }),
  negativeTest: false,
  setNegativeTest: (negativeTest) => set({ negativeTest }),

  result: null,
  setResult: (result) => set({ result }),
  busy: false,
  setBusy: (busy) => set({ busy }),

  activity: [],
  logActivity: (e) =>
    set((s) => ({
      activity: [{ ...e, ts: new Date().toISOString() }, ...s.activity].slice(0, 50),
    })),

  dockWidth: initialDockWidth(),
  setDockWidth: (w) => {
    const clamped = Math.min(720, Math.max(280, Math.round(w)))
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(DOCK_WIDTH_KEY, String(clamped))
    }
    set({ dockWidth: clamped })
  },
  dockCollapsed: false,
  toggleDock: () => set((s) => ({ dockCollapsed: !s.dockCollapsed })),
  chat: [],
  pushMessage: (m) => set((s) => ({ chat: [...s.chat, m] })),
  chatBusy: false,
  setChatBusy: (chatBusy) => set({ chatBusy }),

  scenarios: [],
  setScenarios: (scenarios) => set({ scenarios }),

  activityRows: [],
  setActivityRows: (activityRows) => set({ activityRows }),
}))
