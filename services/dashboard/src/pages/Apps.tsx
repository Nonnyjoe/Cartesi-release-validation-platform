import { useEffect, useState } from 'react'
import { appsApi } from '../api'
import type { Application } from '../types'
import { format } from 'date-fns'

// ── AddAppModal ───────────────────────────────────────────────────────────────

function AddAppModal({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: (a: Application) => void
}) {
  const [name,        setName]        = useState('')
  const [githubUrl,   setGithubUrl]   = useState('')
  const [description, setDescription] = useState('')
  const [addedBy,     setAddedBy]     = useState('')
  const [loading,     setLoading]     = useState(false)
  const [error,       setError]       = useState('')

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim())      { setError('Name is required'); return }
    if (!githubUrl.trim()) { setError('GitHub URL is required'); return }
    setLoading(true)
    setError('')
    try {
      const app = await appsApi.create({
        name:        name.trim(),
        github_url:  githubUrl.trim().replace(/\/+$/, ''),
        description: description.trim() || undefined,
        added_by:    addedBy.trim()  || undefined,
      })
      onCreated(app)
      onClose()
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="card w-full max-w-lg p-6 space-y-4">
        <h2 className="text-lg font-semibold text-gray-100">Register Application</h2>
        <p className="text-xs text-gray-400">
          The sandbox-manager will clone this repository, run <code className="font-mono bg-gray-800 px-1 rounded">cartesi build</code>,
          deploy the application, and register it against the node during each run.
        </p>

        <form onSubmit={submit} className="space-y-3">
          <div>
            <label className="text-xs text-gray-400 block mb-1">Application name *</label>
            <input
              className="input w-full"
              placeholder="my-dapp"
              value={name}
              onChange={e => setName(e.target.value)}
              required
            />
          </div>

          <div>
            <label className="text-xs text-gray-400 block mb-1">GitHub URL *</label>
            <input
              className="input w-full font-mono text-sm"
              placeholder="https://github.com/owner/repo"
              value={githubUrl}
              onChange={e => setGithubUrl(e.target.value)}
              required
            />
            <p className="text-xs text-gray-500 mt-1">Must be a publicly accessible git URL.</p>
          </div>

          <div>
            <label className="text-xs text-gray-400 block mb-1">Description</label>
            <textarea
              className="input w-full resize-none"
              rows={2}
              placeholder="Optional notes about this application"
              value={description}
              onChange={e => setDescription(e.target.value)}
            />
          </div>

          <div>
            <label className="text-xs text-gray-400 block mb-1">Added by</label>
            <input
              className="input w-full"
              placeholder="your name (optional)"
              value={addedBy}
              onChange={e => setAddedBy(e.target.value)}
            />
          </div>

          {error && (
            <div className="text-xs text-red-400 bg-red-900/20 border border-red-800 rounded px-3 py-2">
              {error}
            </div>
          )}

          <div className="flex gap-2 pt-1">
            <button type="submit" className="btn-primary flex-1" disabled={loading}>
              {loading ? 'Registering…' : 'Register Application'}
            </button>
            <button type="button" className="btn-secondary" onClick={onClose} disabled={loading}>
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── EditAppModal ──────────────────────────────────────────────────────────────

function EditAppModal({
  app,
  onClose,
  onUpdated,
}: {
  app: Application
  onClose: () => void
  onUpdated: (a: Application) => void
}) {
  const [name,        setName]        = useState(app.name)
  const [githubUrl,   setGithubUrl]   = useState(app.github_url)
  const [description, setDescription] = useState(app.description ?? '')
  const [loading,     setLoading]     = useState(false)
  const [error,       setError]       = useState('')

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const updated = await appsApi.update(app.id, {
        name:        name.trim()        || undefined,
        github_url:  githubUrl.trim()   || undefined,
        description: description.trim() || undefined,
      })
      onUpdated(updated)
      onClose()
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="card w-full max-w-lg p-6 space-y-4">
        <h2 className="text-lg font-semibold text-gray-100">Edit Application</h2>
        <form onSubmit={submit} className="space-y-3">
          <div>
            <label className="text-xs text-gray-400 block mb-1">Application name</label>
            <input className="input w-full" value={name} onChange={e => setName(e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">GitHub URL</label>
            <input className="input w-full font-mono text-sm" value={githubUrl}
              onChange={e => setGithubUrl(e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">Description</label>
            <textarea className="input w-full resize-none" rows={2} value={description}
              onChange={e => setDescription(e.target.value)} />
          </div>
          {error && (
            <div className="text-xs text-red-400 bg-red-900/20 border border-red-800 rounded px-3 py-2">
              {error}
            </div>
          )}
          <div className="flex gap-2 pt-1">
            <button type="submit" className="btn-primary flex-1" disabled={loading}>
              {loading ? 'Saving…' : 'Save Changes'}
            </button>
            <button type="button" className="btn-secondary" onClick={onClose} disabled={loading}>
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Apps() {
  const [apps,         setApps]         = useState<Application[]>([])
  const [loading,      setLoading]      = useState(true)
  const [showAdd,      setShowAdd]      = useState(false)
  const [editTarget,   setEditTarget]   = useState<Application | null>(null)
  const [showInactive, setShowInactive] = useState(false)
  const [error,        setError]        = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const list = await appsApi.list(showInactive)
      setApps(list)
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [showInactive])  // eslint-disable-line react-hooks/exhaustive-deps

  const handleDeactivate = async (app: Application) => {
    if (!confirm(`Deactivate "${app.name}"? Existing runs will not be affected.`)) return
    try {
      await appsApi.remove(app.id)
      setApps(prev => prev.map(a => a.id === app.id ? { ...a, is_active: false } : a))
    } catch (err) {
      alert(`Failed to deactivate: ${err}`)
    }
  }

  const handleReactivate = async (app: Application) => {
    try {
      const updated = await appsApi.update(app.id, { is_active: true })
      setApps(prev => prev.map(a => a.id === app.id ? updated : a))
    } catch (err) {
      alert(`Failed to reactivate: ${err}`)
    }
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-100">Applications</h1>
          <p className="text-sm text-gray-400 mt-0.5">
            Cartesi dApps available for validation runs. One app is built, deployed, and
            registered per run.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-gray-400 cursor-pointer select-none">
            <input
              type="checkbox"
              className="accent-rvp-primary"
              checked={showInactive}
              onChange={e => setShowInactive(e.target.checked)}
            />
            Show inactive
          </label>
          <button className="btn-primary" onClick={() => setShowAdd(true)}>
            + Register App
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="text-sm text-red-400 bg-red-900/20 border border-red-800 rounded px-4 py-3">
          {error}
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div className="text-sm text-gray-500">Loading applications…</div>
      ) : apps.length === 0 ? (
        <div className="card p-8 text-center text-gray-500 space-y-3">
          <div className="text-3xl">📦</div>
          <p className="text-sm">No applications registered yet.</p>
          <button className="btn-primary" onClick={() => setShowAdd(true)}>Register your first app</button>
        </div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-rvp-border text-xs text-gray-400 uppercase tracking-wide">
                <th className="text-left px-4 py-3">Name</th>
                <th className="text-left px-4 py-3">GitHub URL</th>
                <th className="text-left px-4 py-3">Description</th>
                <th className="text-left px-4 py-3">Added by</th>
                <th className="text-left px-4 py-3">Added</th>
                <th className="text-left px-4 py-3">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-rvp-border">
              {apps.map(app => (
                <tr
                  key={app.id}
                  className={`hover:bg-white/5 transition-colors ${!app.is_active ? 'opacity-50' : ''}`}
                >
                  <td className="px-4 py-3 font-medium text-gray-200">{app.name}</td>
                  <td className="px-4 py-3 max-w-xs truncate">
                    <a
                      href={app.github_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-rvp-primary hover:underline font-mono text-xs"
                    >
                      {app.github_url.replace('https://github.com/', '')}
                    </a>
                  </td>
                  <td className="px-4 py-3 text-gray-400 text-xs max-w-xs truncate">
                    {app.description || <span className="text-gray-600 italic">—</span>}
                  </td>
                  <td className="px-4 py-3 text-gray-400 text-xs">
                    {app.added_by || <span className="text-gray-600 italic">—</span>}
                  </td>
                  <td className="px-4 py-3 text-gray-400 text-xs whitespace-nowrap">
                    {format(new Date(app.added_at), 'MMM d, yyyy')}
                  </td>
                  <td className="px-4 py-3">
                    {app.is_active ? (
                      <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-green-900/50 text-green-400">
                        active
                      </span>
                    ) : (
                      <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-gray-800 text-gray-500">
                        inactive
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2 justify-end">
                      {app.is_active && (
                        <button
                          className="text-xs text-gray-400 hover:text-gray-200 transition-colors"
                          onClick={() => setEditTarget(app)}
                        >
                          Edit
                        </button>
                      )}
                      {app.is_active ? (
                        <button
                          className="text-xs text-red-500 hover:text-red-400 transition-colors"
                          onClick={() => handleDeactivate(app)}
                        >
                          Deactivate
                        </button>
                      ) : (
                        <button
                          className="text-xs text-rvp-primary hover:text-rvp-primary/80 transition-colors"
                          onClick={() => handleReactivate(app)}
                        >
                          Reactivate
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Modals */}
      {showAdd && (
        <AddAppModal
          onClose={() => setShowAdd(false)}
          onCreated={app => setApps(prev => [app, ...prev])}
        />
      )}
      {editTarget && (
        <EditAppModal
          app={editTarget}
          onClose={() => setEditTarget(null)}
          onUpdated={updated => setApps(prev => prev.map(a => a.id === updated.id ? updated : a))}
        />
      )}
    </div>
  )
}
