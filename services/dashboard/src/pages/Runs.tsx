import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { runsApi, releasesApi, appsApi } from '../api'
import { StatusBadge } from '../components/StatusBadge'
import type { Run, RunStatus, ReleaseEntry, Application } from '../types'
import { useWebSocket } from '../hooks/useWebSocket'
import { format } from 'date-fns'

const STATUSES: RunStatus[] = ['queued', 'provisioning', 'running', 'completed', 'failed', 'cancelled']
const PAGE_SIZE = 20


function TriggerModal({ onClose, onCreated }: { onClose: () => void; onCreated: (r: Run) => void }) {
  const [catalog,         setCatalog]         = useState<ReleaseEntry[]>([])
  const [apps,            setApps]            = useState<Application[]>([])
  const [selectedTag,     setSelectedTag]     = useState('')
  const [selectedAppId,   setSelectedAppId]   = useState('')    // '' = no app (raw node tests)
  const [triggeredByUser, setTriggeredByUser] = useState('')
  const [loading,         setLoading]         = useState(false)
  const [error,           setError]           = useState('')

  useEffect(() => {
    releasesApi.list().then(entries => {
      setCatalog(entries)
      if (entries.length > 0) setSelectedTag(entries[0].tag)
    }).catch(console.error)

    appsApi.list().then(setApps).catch(console.error)
  }, [])

  const selected    = catalog.find(e => e.tag === selectedTag) ?? null
  const selectedApp = apps.find(a => a.id === selectedAppId) ?? null

  // Only v2.x releases (node_major_version >= 2) can run with an application
  const isV2 = (selected?.node_major_version ?? 1) >= 2

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selected) { setError('Select a release'); return }
    setLoading(true)
    try {
      const run = await runsApi.create({
        release_tag:       selected.tag,
        image_tag:         selected.image_tag,
        priority:          5,
        triggered_by:      'user',
        triggered_by_user: triggeredByUser.trim() || undefined,
        app_id:            (isV2 && selectedAppId) ? selectedAppId : undefined,
      })
      onCreated(run)
      onClose()
    } catch (e) { setError(String(e)) } finally { setLoading(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="card w-full max-w-md p-6 space-y-4">
        <h2 className="text-lg font-semibold text-gray-100">Trigger New Run</h2>
        <form onSubmit={submit} className="space-y-4">

          {/* Release dropdown */}
          <div>
            <label className="text-xs text-gray-400 block mb-1">Select Release *</label>
            {catalog.length === 0 ? (
              <div className="text-xs text-gray-500">Loading releases…</div>
            ) : (
              <select
                className="input w-full"
                value={selectedTag}
                onChange={e => { setSelectedTag(e.target.value); setSelectedAppId('') }}
              >
                {catalog.map(entry => (
                  <option key={entry.tag} value={entry.tag}>
                    {entry.tag} ({entry.channel})
                  </option>
                ))}
              </select>
            )}
            {selected && (
              <div className="mt-1.5 text-xs text-gray-500 font-mono truncate">
                {selected.image_tag}
              </div>
            )}
          </div>

          {/* Application selector (v2.x only) */}
          <div>
            <label className="text-xs text-gray-400 block mb-1">
              Application
              {!isV2 && <span className="text-gray-600 ml-1">(v2.x node required)</span>}
            </label>
            <select
              className="input w-full"
              value={selectedAppId}
              onChange={e => setSelectedAppId(e.target.value)}
              disabled={!isV2}
            >
              <option value="">— None (raw node tests only) —</option>
              {apps.filter(a => a.is_active).map(app => (
                <option key={app.id} value={app.id}>{app.name}</option>
              ))}
            </select>
            {selectedApp && (
              <div className="mt-1.5 text-xs text-gray-500 font-mono truncate">
                {selectedApp.github_url}
              </div>
            )}
            {isV2 && !selectedAppId && (
              <p className="text-xs text-yellow-600 mt-1">
                Without an application the node starts without a machine snapshot. Health-check
                tests pass; input/inspect tests will not.
              </p>
            )}
          </div>

          <div>
            <label className="text-xs text-gray-400 block mb-1">Your Name</label>
            <input className="input w-full" placeholder="optional" value={triggeredByUser}
              onChange={e => setTriggeredByUser(e.target.value)} />
          </div>

          {error && <div className="text-xs text-rvp-error">{error}</div>}

          <div className="flex gap-2 pt-1">
            <button type="submit" className="btn-primary flex-1" disabled={loading || !selected}>
              {loading ? 'Creating…' : 'Run Tests'}
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
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [showModal, setShowModal] = useState(false)

  const load = async (off = offset, filter = statusFilter) => {
    try {
      const res = await runsApi.list(PAGE_SIZE, off, filter || undefined)
      setRuns(res)
      setHasMore(res.length === PAGE_SIZE)
    } catch (e) { console.error(e) }
  }

  useEffect(() => {
    setOffset(0)
    load(0, statusFilter)
  }, [statusFilter])

  useWebSocket({
    onEvent: (ev) => {
      if (ev.event_type.startsWith('run.') || ev.event_type.startsWith('sandbox.')) load()
    },
  })

  const page = Math.floor(offset / PAGE_SIZE) + 1

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
              <th className="px-4 py-3">Run ID</th>
              <th className="px-4 py-3">Release</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Pass Rate</th>
              <th className="px-4 py-3">Triggered By</th>
              <th className="px-4 py-3">Queued</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-rvp-border/50">
            {runs.map(r => (
              <tr key={r.id} className="hover:bg-white/5 transition-colors">
                <td className="px-4 py-3">
                  <Link to={`/runs/${r.id}`} className="text-rvp-primary hover:underline font-mono text-xs">
                    {r.id.slice(0, 8)}
                  </Link>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-gray-300">{r.release_tag}</td>
                <td className="px-4 py-3"><StatusBadge status={r.status} /></td>
                <td className="px-4 py-3">
                  {r.pass_rate != null ? (
                    <span className={r.pass_rate >= 90 ? 'text-rvp-success' : r.pass_rate >= 70 ? 'text-rvp-warning' : 'text-rvp-error'}>
                      {r.pass_rate.toFixed(1)}%
                    </span>
                  ) : '—'}
                </td>
                <td className="px-4 py-3 text-xs text-gray-500">{r.triggered_by}</td>
                <td className="px-4 py-3 text-xs text-gray-500">
                  {format(new Date(r.queued_at), 'MMM d, HH:mm')}
                </td>
              </tr>
            ))}
            {runs.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-500 text-sm">No runs found</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between text-sm">
        <span className="text-gray-500">Page {page}</span>
        <div className="flex gap-2">
          <button className="btn-ghost" disabled={offset === 0}
            onClick={() => { const o = Math.max(0, offset - PAGE_SIZE); setOffset(o); load(o) }}>
            ← Prev
          </button>
          <button className="btn-ghost" disabled={!hasMore}
            onClick={() => { const o = offset + PAGE_SIZE; setOffset(o); load(o) }}>
            Next →
          </button>
        </div>
      </div>

      {showModal && (
        <TriggerModal onClose={() => setShowModal(false)} onCreated={(r) => setRuns(rs => [r, ...rs])} />
      )}
    </div>
  )
}
