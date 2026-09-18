import { useEffect } from 'react'
import { getActions, getMe } from './api'
import { AppRail } from './components/AppRail'
import { ChatDock } from './components/ChatDock'
import { TopBar } from './components/TopBar'
import { ActivityTab } from './components/ActivityTab'
import { ScenariosTab } from './components/ScenariosTab'
import { HomeSection } from './sections/HomeSection'
import { TestSection } from './sections/TestSection'
import { useStore } from './store'

function errMsg(e: unknown): string {
  if (e && typeof e === 'object' && 'response' in e) {
    const anyE = e as { response?: { data?: { detail?: string } }; message?: string }
    return anyE.response?.data?.detail ?? anyE.message ?? 'Request failed'
  }
  return e instanceof Error ? e.message : 'Request failed'
}

export default function App() {
  const { me, meError, setMe, setActions, section, dockWidth, dockCollapsed } = useStore()

  useEffect(() => {
    getActions()
      .then(setActions)
      .catch(() => setActions([]))
    getMe()
      .then((m) => setMe(m))
      .catch((e) => setMe(null, errMsg(e)))
  }, [setActions, setMe])

  return (
    <div className="min-h-full">
      <AppRail />
      <ChatDock />

      {/* main column sits between the rail (left) and the dock (right) */}
      <div
        className="pl-14 transition-[padding] duration-200"
        style={{ paddingRight: dockCollapsed ? 0 : dockWidth }}
      >
        <TopBar me={me} meError={meError} />

        <main className="mx-auto max-w-6xl px-6 py-6">
          {section === 'home' && <HomeSection me={me} meError={meError} />}
          {section === 'test' && <TestSection />}
          {section === 'scenarios' && <ScenariosTab />}
          {section === 'activity' && <ActivityTab />}
        </main>
      </div>
    </div>
  )
}
