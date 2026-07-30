import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { StatusBar } from './StatusBar'

export function AppShell() {
  return (
    <div className="flex h-svh overflow-hidden bg-background">
      {/* Sidebar */}
      <Sidebar />

      {/* Main Area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />

        {/* Page Content */}
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>

        <StatusBar />
      </div>
    </div>
  )
}
