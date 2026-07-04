import React from 'react'
import { Outlet } from 'react-router-dom'
import AppSidebar from './AppSidebar'
import AppTopbar from './AppTopbar'

const AppShell: React.FC = () => {
  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'var(--color-bg-alt)' }}>
      {/* Sidebar */}
      <AppSidebar />

      {/* Coluna direita */}
      <div className="flex flex-col flex-1 min-w-0">
        <AppTopbar />
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

export default AppShell
