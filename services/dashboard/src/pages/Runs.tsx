import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { runsApi } from '../api'
import { StatusBadge } from '../components/StatusBadge'
import type { Run, RunStatus } from '../types'
import { useWebSocket } from '../hooks/useWebSocket'
import { format } from 'date-fns'

const STATUSES: RunStatus[] = ['pending', 'provisioning', 'running', 'completed', 'failed', 'cancelled']

function TriggerModal({ onClose, onCreated }: { onClose: () => void; onCreated: (r: Run) => void }) {
  const [form, setForm] = useState({ node_version: '', pr_number: '', repo_url: '', priority: '5' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.node_version.trim()) { setError('Node version is required'); return }
    setLoading(true)
    try {
      const run = await runsApi.create({
        node_version: form.node_version.trim(),
        pr_number: form.pr_number ? parseInt(form.pr_number) : undefined,
        repo_url: form.repo_url || undefined,
        triggered_by: 'dashboard',
        priority: parseInt(form.priority),
      })
      onCreated(run)
      onClose()
    } catch (e) { setError(String(e)) } finally { setLoading(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="card w-full max-w-md p-6 space-y-4">
        <h2 className="text-lg font-semibold text-gray-100">Trigger New Run</h2>
        <form onSubmit={submit} className="space-y-3">
          <div>
            <label className="text-xs text-gray-400 block mb-1">Node Version *</label>
            <input className="input w-full" placeholder="1.5.0" value={form.node_version}
              onChange={e => setForm(f => ({ ...f, node_version: e.target.value }))} />
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">PR Number</label>
            <input className="input w-full" type="number" placeholder="123" value={form.pr_number}
              onChange={e => setForm(f => ({ ...f, pr_number: e.target.value }))} />
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">Repo URL</label>
            <input className="input w-full" placeholder="https://github.com/..." value={form.repo_url}
              onChange={e => setForm(f => ({ ...f, repo_url: e.target.value }))} />
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">Priority (1–10)</label>
            <input className="input w-full" type="number" min="1" max="10" value={form.priority}
              onChange={e => setForm(f => ({ ...f, priority: e.target.value }))} />
          </div>
          {error && <div className="text-xs text-rvp-error">{error}</div>}
          <div className="flex gap-2 pt-1">
            <button type="submit" className="btn-primary flex-1" disabled={loading}>
              {loading ? 'Creating…' : 'Create Run'}
            </button>
            <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function Runs() {
  const [runs, setRuns] = useState<Run[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [showModal, setShowModal] = useState(false)
  const PAGE_SIZE = 20

  const load = async () => {
    const res = await runsApi.list(page, PAGE_SIZE, statusFilter || undefined)
    setRuns(res.items)
    setTotal(res.total)
  }

  useEffect(() => { load() }, [page, statusFilter])

  useWebSocket({
    onEvent: (ev) => {
      if (ev.event_type.startsWith('run.') || ev.event_type.startsWith('sandbox.')) load()
    },
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-100">Runs</h1>
        <button className="btn-primary" onClick={() => setShowModal(true)}>+ New Run</button>
      </div>

      {/* Filters */}
      <div className="flex gap-2 flex-wrap">
        <button onClick={() => setStatusFilter('')}
          className={`badge cursor-pointer ${!statusFilter ? 'bg-rvp-primary text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
          All
        </button>
        {STATUSES.map(s => (
          <button key={s} onClick={() => setStatusFilter(s)}
            className={`badge cursor-pointer ${statusFilter === s ? 'bg-rvp-primary text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
            {s}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-rvp-border text-xs text-gray-500 text-left">
              <th className="px-4 py-3">Run</th>
              <th className="px-4 py-3">Version</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Pass Rate</th>
              <th className="px-4 py-3">Tests</th>
              <th className="px-4 py-3">Triggered</th>
              <th className="px-4 py-3">Created</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-rvp-border/50">
            {runs.map(r => (
              <tr key={r.run_id} className="hover:bg-white/5 transition-colors">
                <td className="px-4 py-3">
                  <Link to={`/runs/${r.run_id}`} className="text-rvp-primary hover:underline font-mono text-xs">
                    {r.run_id.slice(0, 8)}
                  </Link>
                  {r.pr_number && (
                    <span className="ml-2 text-xs text-gray-500">PR #{r.pr_number}</span>
                  )}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-gray-300">{r.node_version}</td>
                <td className="px-4 py-3"><StatusBadge status={r.status} /></td>
                <td className="px-4 py-3">
                  {r.pass_rate != null ? (
                    <span className={r.pass_rate >= 90 ? 'text-rvp-success' : r.pass_rate >= 70 ? 'text-rvp-warning' : 'text-rvp-error'}>
                      {r.pass_rate.toFixed(1)}%
                    </span>
                  ) : '—'}
                </td>
                <td className="px-4 py-3 text-gray-400 text-xs">
                  {r.total_tests > 0 ? `${r.passed_tests}/${r.total_tests}` : '—'}
                </td>
                <td className="px-4 py-3 text-xs text-gray-500">{r.triggered_by}</td>
                <td className="px-4 py-3 text-xs text-gray-500">
                  {format(new Date(r.created_at), 'MMM d, HH:mm')}
                </td>
              </tr>
            ))}
            {runs.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-500 text-sm">No runs found</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
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

      {showModal && (
        <TriggerModal onClose={() => setShowModal(false)} onCreated={(r) => setRuns(rs => [r, ...rs])} />
      )}
    </div>
  )
}
