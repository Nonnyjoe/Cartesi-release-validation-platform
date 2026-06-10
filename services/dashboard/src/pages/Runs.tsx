import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { runsApi, releasesApi, appsApi, testsApi } from '../api'
import { StatusBadge } from '../components/StatusBadge'
import type { Run, RunStatus, ReleaseEntry, Application, PhaseGroup } from '../types'
import { useWebSocket } from '../hooks/useWebSocket'
import { format } from 'date-fns'

const STATUSES: RunStatus[] = ['queued', 'provisioning', 'running', 'completed', 'failed', 'cancelled']
const PAGE_SIZE = 20


// ─── Category picker (inside trigger modal) ───────────────────────────────────

function CategoryPicker({
  phases,
  selected,
  onChange,
}: {
  phases:   PhaseGroup[]
  selected: Set<string>
  onChange: (s: Set<string>) => void
}) {
  const [openPhases, setOpenPhases] = useState<Set<string>>(new Set())

  const togglePhase = (phase: string) =>
    setOpenPhases(s => { const n = new Set(s); n.has(phase) ? n.delete(phase) : n.add(phase); return n })

  const toggleCategory = (cat: string) => {
    const n = new Set(selected)
    n.has(cat) ? n.delete(cat) : n.add(cat)
    onChange(n)
  }

  const toggleAllInPhase = (pg: PhaseGroup, checked: boolean) => {
    const n = new Set(selected)
    for (const c of pg.categories) {
      checked ? n.add(c.category) : n.delete(c.category)
    }
    onChange(n)
  }

  return (
    <div className="border border-rvp-border rounded-lg overflow-hidden max-h-52 overflow-y-auto text-xs">
      {phases.map(pg => {
        const allChecked = pg.categories.every(c => selected.has(c.category))
        const someChecked = pg.categories.some(c => selected.has(c.category))
        const phaseOpen = openPhases.has(pg.phase)
        return (
          <div key={pg.phase} className="border-b border-rvp-border/50 last:border-0">
            <div className="flex items-center gap-2 px-3 py-2 bg-rvp-bg/40 hover:bg-white/3">
              <input
                type="checkbox"
                checked={allChecked}
                ref={el => { if (el) el.indeterminate = someChecked && !allChecked }}
                onChange={e => toggleAllInPhase(pg, e.target.checked)}
                className="accent-rvp-primary"
              />
              <button
                type="button"
                className="flex-1 text-left text-gray-300 font-medium flex items-center gap-1.5"
                onClick={() => togglePhase(pg.phase)}
              >
                <span className="text-gray-600">{phaseOpen ? '▼' : '▶'}</span>
                {pg.phase}
              </button>
              <span className="text-gray-600">
                {pg.categories.filter(c => selected.has(c.category)).length}/{pg.categories.length}
              </span>
            </div>
            {phaseOpen && pg.categories.map(c => (
              <label key={c.category}
                className="flex items-center gap-2 px-4 py-1.5 hover:bg-white/3 cursor-pointer text-gray-400">
                <input
                  type="checkbox"
                  checked={selected.has(c.category)}
                  onChange={() => toggleCategory(c.category)}
                  className="accent-rvp-primary"
                />
                <span className="flex-1">{c.category}</span>
                <span className="text-gray-600">{c.active_count}</span>
              </label>
            ))}
          </div>
        )
      })}
    </div>
  )
}


// ─── Trigger modal ────────────────────────────────────────────────────────────

function TriggerModal({ onClose, onCreated }: { onClose: () => void; onCreated: (r: Run) => void }) {
  const [catalog,           setCatalog]           = useState<ReleaseEntry[]>([])
  const [apps,              setApps]              = useState<Application[]>([])
  const [phases,            setPhases]            = useState<PhaseGroup[]>([])
  const [selectedTag,       setSelectedTag]       = useState('')
  const [selectedAppId,     setSelectedAppId]     = useState('')
  const [triggeredByUser,   setTriggeredByUser]   = useState('')
  const [scopeMode,         setScopeMode]         = useState<'all' | 'categories'>('all')
  const [selectedCats,      setSelectedCats]      = useState<Set<string>>(new Set())
  const [loading,           setLoading]           = useState(false)
  const [error,             setError]             = useState('')

  useEffect(() => {
    releasesApi.list().then(entries => {
      setCatalog(entries)
      if (entries.length > 0) setSelectedTag(entries[0].tag)
    }).catch(console.error)

    appsApi.list().then(list => {
      setApps(list)
      const active = list.filter((a: Application) => a.is_active)
      if (active.length > 0) setSelectedAppId(active[0].id)
    }).catch(console.error)

    testsApi.categories().then(setPhases).catch(console.error)
  }, [])

  const selected    = catalog.find(e => e.tag === selectedTag) ?? null
  const selectedApp = apps.find(a => a.id === selectedAppId) ?? null
  const isV2        = (selected?.node_major_version ?? 1) >= 2

  const totalSelectedTests = useMemo(() => {
    if (scopeMode === 'all') return null
    let n = 0
    for (const pg of phases) {
      for (const c of pg.categories) {
        if (selectedCats.has(c.category)) n += c.active_count
      }
    }
    return n
  }, [scopeMode, selectedCats, phases])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selected) { setError('Select a release'); return }
    if (isV2 && !selectedAppId) { setError('An application is required to start a run'); return }
    setLoading(true)
    try {
      const run = await runsApi.create({
        release_tag:       selected.tag,
        image_tag:         selected.image_tag,
        priority:          5,
        triggered_by:      'user',
        triggered_by_user: triggeredByUser.trim() || undefined,
        app_id:            selectedAppId || undefined,
        category_filter:   scopeMode === 'categories' && selectedCats.size > 0
                             ? Array.from(selectedCats)
                             : undefined,
      })
      onCreated(run)
      onClose()
    } catch (e) { setError(String(e)) } finally { setLoading(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="card w-full max-w-md p-6 space-y-4 max-h-[90vh] overflow-y-auto">
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
                onChange={e => {
                  setSelectedTag(e.target.value)
                  const active = apps.filter(a => a.is_active)
                  setSelectedAppId(active.length > 0 ? active[0].id : '')
                }}
              >
                {catalog.map(entry => (
                  <option key={entry.tag} value={entry.tag}>
                    {entry.tag} ({entry.channel})
                  </option>
                ))}
              </select>
            )}
            {selected && (
              <div className="mt-1.5 text-xs text-gray-500 font-mono truncate">{selected.image_tag}</div>
            )}
          </div>

          {/* Application selector */}
          <div>
            <label className="text-xs text-gray-400 block mb-1">
              Application *
              {!isV2 && <span className="text-gray-600 ml-1">(v2.x node required)</span>}
            </label>
            {isV2 && apps.filter(a => a.is_active).length === 0 ? (
              <p className="text-xs text-rvp-error mt-1">
                No active applications registered. Add one in the Apps page before triggering a run.
              </p>
            ) : (
              <select
                className="input w-full"
                value={selectedAppId}
                onChange={e => setSelectedAppId(e.target.value)}
                disabled={!isV2}
              >
                {!isV2 && <option value="">— N/A for v1.x —</option>}
                {apps.filter(a => a.is_active).map(app => (
                  <option key={app.id} value={app.id}>{app.name}</option>
                ))}
              </select>
            )}
            {selectedApp && (
              <div className="mt-1.5 text-xs text-gray-500 font-mono truncate">{selectedApp.github_url}</div>
            )}
          </div>

          {/* Triggered by */}
          <div>
            <label className="text-xs text-gray-400 block mb-1">Your Name</label>
            <input className="input w-full" placeholder="optional" value={triggeredByUser}
              onChange={e => setTriggeredByUser(e.target.value)} />
          </div>

          {/* Test Scope */}
          <div>
            <label className="text-xs text-gray-400 block mb-2">Test Scope</label>
            <div className="flex flex-col gap-1.5 mb-2">
              <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
                <input type="radio" name="scope" value="all" checked={scopeMode === 'all'}
                  onChange={() => setScopeMode('all')} className="accent-rvp-primary" />
                All active tests
              </label>
              <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
                <input type="radio" name="scope" value="categories" checked={scopeMode === 'categories'}
                  onChange={() => setScopeMode('categories')} className="accent-rvp-primary" />
                Select categories
              </label>
            </div>

            {scopeMode === 'categories' && (
              <>
                {phases.length === 0 ? (
                  <div className="text-xs text-gray-500">Loading categories…</div>
                ) : (
                  <CategoryPicker
                    phases={phases}
                    selected={selectedCats}
                    onChange={setSelectedCats}
                  />
                )}
                <div className="flex items-center justify-between mt-1.5 text-xs text-gray-500">
                  <span>
                    {selectedCats.size > 0
                      ? `${selectedCats.size} categor${selectedCats.size === 1 ? 'y' : 'ies'} · ~${totalSelectedTests ?? 0} tests`
                      : 'No categories selected — will run all tests'}
                  </span>
                  {selectedCats.size > 0 && (
                    <button type="button" className="text-rvp-primary hover:underline"
                      onClick={() => setSelectedCats(new Set())}>
                      Clear
                    </button>
                  )}
                </div>
              </>
            )}
          </div>

          {error && <div className="text-xs text-rvp-error">{error}</div>}

          <div className="flex gap-2 pt-1">
            <button type="submit" className="btn-primary flex-1"
              disabled={loading || !selected || (isV2 && !selectedAppId)}>
              {loading ? 'Creating…' : 'Run Tests'}
            </button>
            <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ─── Runs list ────────────────────────────────────────────────────────────────

export default function Runs() {
  const [runs, setRuns]             = useState<Run[]>([])
  const [offset, setOffset]         = useState(0)
  const [hasMore, setHasMore]       = useState(false)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [showModal, setShowModal]   = useState(false)

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
