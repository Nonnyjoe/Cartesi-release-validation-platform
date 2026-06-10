import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { sessionsApi } from '../api'
import { StatusBadge } from '../components/StatusBadge'
import { useWebSocket } from '../hooks/useWebSocket'
import type { AISession, AIMode } from '../types'
import { format } from 'date-fns'

// Event types that should trigger a Sessions list refresh
const AI_LIST_EVENTS = new Set([
  'ai.session_created',
  'session_started',
  'session_completed',
  'ai.tool_call',
  'ai.tool_result',
  'ai.finding',
])

const MODES: AIMode[] = ['autonomous', 'collaborative', 'interactive']

const MODELS = [
  { id: 'claude-opus-4-6',          label: 'Opus 4.6 (most capable)' },
  { id: 'claude-sonnet-4-6',        label: 'Sonnet 4.6 (balanced)' },
  { id: 'claude-haiku-4-5-20251001', label: 'Haiku 4.5 (fast)' },
] as const

function NewSessionModal({ onClose }: { onClose: () => void }) {
  const [form, setForm] = useState({
    mode: 'autonomous',
    run_id: '',
    sandbox_id: '',
    goal: '',
    anthropic_api_key: '',
    model_id: 'claude-opus-4-6',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.anthropic_api_key || form.anthropic_api_key.length < 20) {
      setError('Anthropic API key is required (sk-ant-…).')
      return
    }
    setLoading(true)
    try {
      await sessionsApi.create({
        mode: form.mode,
        run_id: form.run_id || undefined,
        sandbox_id: form.sandbox_id || undefined,
        goal: form.goal || undefined,
        anthropic_api_key: form.anthropic_api_key,
        model_id: form.model_id,
      })
      onClose()
    } catch (e) { setError(String(e)) } finally { setLoading(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="card w-full max-w-md p-6 space-y-4">
        <h2 className="text-lg font-semibold text-gray-100">New AI Session</h2>
        <form onSubmit={submit} className="space-y-3">
          <div>
            <label className="text-xs text-gray-400 block mb-1">Mode</label>
            <select className="input w-full" value={form.mode}
              onChange={e => setForm(f => ({ ...f, mode: e.target.value }))}>
              {MODES.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">Anthropic API Key</label>
            <input className="input w-full font-mono text-xs" placeholder="sk-ant-…" type="password"
              value={form.anthropic_api_key}
              onChange={e => setForm(f => ({ ...f, anthropic_api_key: e.target.value }))} />
            <div className="text-[10px] text-gray-500 mt-1">
              Stored encrypted on the server; used only for this session.
            </div>
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">Model</label>
            <select className="input w-full" value={form.model_id}
              onChange={e => setForm(f => ({ ...f, model_id: e.target.value }))}>
              {MODELS.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">Run ID (optional)</label>
            <input className="input w-full" placeholder="uuid" value={form.run_id}
              onChange={e => setForm(f => ({ ...f, run_id: e.target.value }))} />
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">Sandbox ID (optional)</label>
            <input className="input w-full" placeholder="uuid" value={form.sandbox_id}
              onChange={e => setForm(f => ({ ...f, sandbox_id: e.target.value }))} />
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">Goal / Instructions</label>
            <textarea className="input w-full h-20 resize-none" placeholder="Investigate voucher execution…"
              value={form.goal} onChange={e => setForm(f => ({ ...f, goal: e.target.value }))} />
          </div>
          {error && <div className="text-xs text-rvp-error">{error}</div>}
          <div className="flex gap-2 pt-1">
            <button type="submit" className="btn-primary flex-1" disabled={loading}>
              {loading ? 'Creating…' : 'Start Session'}
            </button>
            <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function Sessions() {
  const [sessions, setSessions] = useState<AISession[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [showModal, setShowModal] = useState(false)
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const PAGE_SIZE = 20

  const load = () => sessionsApi.list(page, PAGE_SIZE).then(r => { setSessions(r.items); setTotal(r.total) })
  useEffect(() => { load() }, [page])

  // Live updates: subscribe globally, debounce refresh on session-related events.
  const { connected } = useWebSocket({
    onEvent: (ev) => {
      if (!ev.event_type || !AI_LIST_EVENTS.has(ev.event_type)) return
      if (refreshTimer.current) clearTimeout(refreshTimer.current)
      refreshTimer.current = setTimeout(load, 500)
    },
  })
  useEffect(() => () => { if (refreshTimer.current) clearTimeout(refreshTimer.current) }, [])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold text-gray-100">AI Sessions</h1>
          <span className="flex items-center gap-1.5 text-xs text-gray-500">
            <span className={`h-1.5 w-1.5 rounded-full ${connected ? 'bg-rvp-success' : 'bg-gray-600'}`} />
            {connected ? 'Live' : 'Offline'}
          </span>
        </div>
        <button className="btn-primary" onClick={() => setShowModal(true)}>+ New Session</button>
      </div>

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-rvp-border text-xs text-gray-500 text-left">
              <th className="px-4 py-3">Session</th>
              <th className="px-4 py-3">Mode</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Tool Calls</th>
              <th className="px-4 py-3">Tokens</th>
              <th className="px-4 py-3">Findings</th>
              <th className="px-4 py-3">Created</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-rvp-border/50">
            {sessions.map(s => (
              <tr key={s.session_id} className="hover:bg-white/5 transition-colors">
                <td className="px-4 py-3">
                  <Link to={`/sessions/${s.session_id}`} className="text-rvp-primary hover:underline font-mono text-xs">
                    {s.session_id.slice(0, 8)}
                  </Link>
                  {s.goal && <div className="text-xs text-gray-500 truncate max-w-xs">{s.goal}</div>}
                </td>
                <td className="px-4 py-3"><StatusBadge status={s.mode} /></td>
                <td className="px-4 py-3"><StatusBadge status={s.status} /></td>
                <td className="px-4 py-3 text-xs text-gray-400">{s.tool_calls_used}</td>
                <td className="px-4 py-3 text-xs text-gray-400">
                  {(s.input_tokens + s.output_tokens).toLocaleString()}
                </td>
                <td className="px-4 py-3 text-xs">
                  {s.findings.length > 0 ? (
                    <span className="badge bg-rvp-warning/20 text-rvp-warning">{s.findings.length}</span>
                  ) : '—'}
                </td>
                <td className="px-4 py-3 text-xs text-gray-500">
                  {format(new Date(s.created_at), 'MMM d, HH:mm')}
                </td>
              </tr>
            ))}
            {sessions.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-500 text-sm">No sessions yet</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-gray-500">{total} total</span>
          <div className="flex gap-2">
            <button className="btn-ghost" disabled={page === 1} onClick={() => setPage(p => p - 1)}>← Prev</button>
            <span className="text-gray-400 px-2 py-1">Page {page}</span>
            <button className="btn-ghost" disabled={page * PAGE_SIZE >= total} onClick={() => setPage(p => p + 1)}>Next →</button>
          </div>
        </div>
      )}

      {showModal && <NewSessionModal onClose={() => { setShowModal(false); load() }} />}
    </div>
  )
}
