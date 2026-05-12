import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { sessionsApi } from '../api'
import { StatusBadge } from '../components/StatusBadge'
import type { AISession, AIMode } from '../types'
import { format } from 'date-fns'

const MODES: AIMode[] = ['autonomous', 'collaborative', 'interactive']

function NewSessionModal({ onClose }: { onClose: () => void }) {
  const [form, setForm] = useState({ mode: 'autonomous', run_id: '', sandbox_id: '', goal: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      await sessionsApi.create({
        mode: form.mode,
        run_id: form.run_id || undefined,
        sandbox_id: form.sandbox_id || undefined,
        goal: form.goal || undefined,
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
  const PAGE_SIZE = 20

  const load = () => sessionsApi.list(page, PAGE_SIZE).then(r => { setSessions(r.items); setTotal(r.total) })
  useEffect(() => { load() }, [page])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-100">AI Sessions</h1>
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
