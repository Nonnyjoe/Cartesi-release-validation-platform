import { BrowserRouter, NavLink, Routes, Route, Navigate } from 'react-router-dom'
import { QueueStatus } from './components/QueueStatus'
import { SandboxPool } from './components/SandboxPool'
import { useWebSocket } from './hooks/useWebSocket'
import { useState } from 'react'
import Runs from './pages/Runs'
import RunDetail from './pages/RunDetail'
import Sandboxes from './pages/Sandboxes'
import Sessions from './pages/Sessions'
import Session from './pages/Session'
import AISuggestions from './pages/AISuggestions'

const NAV = [
  { to: '/runs',        label: '⚡ Runs' },
  { to: '/sandboxes',   label: '📦 Sandboxes' },
  { to: '/sessions',    label: '🤖 AI Sessions' },
  { to: '/suggestions', label: '💡 Suggestions' },
]

function Sidebar() {
  return (
    <aside className="w-64 shrink-0 flex flex-col bg-rvp-surface border-r border-rvp-border h-screen sticky top-0 overflow-y-auto">
      {/* Logo */}
      <div className="px-5 py-4 border-b border-rvp-border">
        <div className="text-rvp-primary font-bold text-lg tracking-tight">Cartesi RVP</div>
        <div className="text-xs text-gray-500 mt-0.5">Release Validation Platform</div>
      </div>

      {/* Nav */}
      <nav className="px-3 py-4 flex-1 space-y-1">
        {NAV.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `block px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-rvp-primary/20 text-rvp-primary'
                  : 'text-gray-400 hover:bg-white/5 hover:text-gray-200'
              }`
            }
          >
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Widgets */}
      <div className="px-3 py-4 space-y-3 border-t border-rvp-border">
        <SandboxPool />
        <QueueStatus />
      </div>
    </aside>
  )
}

function LiveIndicator() {
  const [events, setEvents] = useState(0)
  const { connected } = useWebSocket({
    onEvent: () => setEvents(n => n + 1),
  })

  return (
    <div className="flex items-center gap-1.5 text-xs text-gray-500">
      <span className={`h-1.5 w-1.5 rounded-full transition-colors ${connected ? 'bg-rvp-success' : 'bg-gray-600'}`} />
      {connected ? `Live · ${events} events` : 'Connecting…'}
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex min-h-screen">
        <Sidebar />

        <main className="flex-1 flex flex-col min-w-0">
          {/* Top bar */}
          <header className="h-12 border-b border-rvp-border flex items-center px-6 gap-4 shrink-0">
            <div className="flex-1" />
            <LiveIndicator />
          </header>

          {/* Page content */}
          <div className="flex-1 p-6 overflow-auto">
            <Routes>
              <Route path="/" element={<Navigate to="/runs" replace />} />
              <Route path="/runs" element={<Runs />} />
              <Route path="/runs/:runId" element={<RunDetail />} />
              <Route path="/sandboxes" element={<Sandboxes />} />
              <Route path="/sessions" element={<Sessions />} />
              <Route path="/sessions/:sessionId" element={<Session />} />
              <Route path="/suggestions" element={<AISuggestions />} />
            </Routes>
          </div>
        </main>
      </div>
    </BrowserRouter>
  )
}
