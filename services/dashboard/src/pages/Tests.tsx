import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { testsApi } from '../api'
import type { TestDefinition } from '../types'

const PRIORITY_BADGE: Record<string, string> = {
  critical: 'bg-rvp-error/20 text-rvp-error',
  high:     'bg-rvp-warning/20 text-rvp-warning',
  medium:   'bg-rvp-info/20 text-rvp-info',
  low:      'bg-gray-700 text-gray-400',
}

const YAML_TEMPLATE = `---
id: my-test-slug
name: My Test Name
version: 1
priority: medium
component: node
tags: [smoke]
timeout_seconds: 120
assertions:
  - type: http_status
    url: /health
    expected_status: 200
---
Describe what this test validates.
`

function CreateModal({ onClose, onCreated }: { onClose: () => void; onCreated: (d: TestDefinition) => void }) {
  const [content, setContent] = useState(YAML_TEMPLATE)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const def = await testsApi.create(content)
      onCreated(def)
      onClose()
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="card w-full max-w-2xl p-6 space-y-4">
        <h2 className="text-lg font-semibold text-gray-100">Create Test Definition</h2>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="text-xs text-gray-400 block mb-1">YAML Frontmatter + Description</label>
            <textarea
              className="input w-full font-mono text-xs"
              rows={20}
              value={content}
              onChange={e => setContent(e.target.value)}
              spellCheck={false}
            />
          </div>
          {error && <div className="text-xs text-rvp-error">{error}</div>}
          <div className="flex gap-2 pt-1">
            <button type="submit" className="btn-primary flex-1" disabled={loading}>
              {loading ? 'Creating…' : 'Create'}
            </button>
            <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function Tests() {
  const navigate = useNavigate()
  const [defs, setDefs]         = useState<TestDefinition[]>([])
  const [loading, setLoading]   = useState(true)
  const [showCreate, setCreate] = useState(false)
  const [filter, setFilter]     = useState<'all' | 'active' | 'inactive'>('all')
  const [toggling, setToggling] = useState<Set<string>>(new Set())

  const load = async () => {
    try { setDefs(await testsApi.list()) }
    catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const handleToggle = async (def: TestDefinition) => {
    setToggling(s => new Set(s).add(def.id))
    try {
      const updated = await testsApi.toggle(def.id, !def.is_active)
      setDefs(ds => ds.map(d => d.id === updated.id ? updated : d))
    } catch (e) { console.error(e) }
    finally { setToggling(s => { const n = new Set(s); n.delete(def.id); return n }) }
  }

  const visible = defs.filter(d =>
    filter === 'all'      ? true :
    filter === 'active'   ? d.is_active :
                            !d.is_active
  )
  const activeCount   = defs.filter(d => d.is_active).length
  const inactiveCount = defs.length - activeCount

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-100">Test Definitions</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            {activeCount} active · {inactiveCount} inactive · {defs.length} total
          </p>
        </div>
        <button className="btn-primary" onClick={() => setCreate(true)}>+ New Definition</button>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-2">
        {(['all', 'active', 'inactive'] as const).map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={`badge cursor-pointer capitalize ${filter === f ? 'bg-rvp-primary text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
            {f}
          </button>
        ))}
      </div>

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-rvp-border text-xs text-gray-500 text-left">
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Slug</th>
              <th className="px-4 py-3">Priority</th>
              <th className="px-4 py-3">Component</th>
              <th className="px-4 py-3">Tags</th>
              <th className="px-4 py-3">Ver</th>
              <th className="px-4 py-3">Active</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-rvp-border/50">
            {loading ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-500 text-sm">Loading…</td></tr>
            ) : visible.length === 0 ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-500 text-sm">No definitions found</td></tr>
            ) : visible.map(def => (
              <tr
                key={def.id}
                className="hover:bg-white/5 transition-colors cursor-pointer"
                onClick={e => {
                  // don't navigate when the toggle button is clicked
                  if ((e.target as HTMLElement).closest('button')) return
                  navigate(`/tests/${def.id}`)
                }}
              >
                <td className="px-4 py-3">
                  <span className="text-gray-200 font-medium">{def.name}</span>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-gray-400">{def.slug}</td>
                <td className="px-4 py-3">
                  <span className={`badge text-xs ${PRIORITY_BADGE[def.priority] ?? 'bg-gray-700 text-gray-400'}`}>
                    {def.priority}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-gray-500">{def.component ?? '—'}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {def.tags.map(t => (
                      <span key={t} className="badge text-xs bg-gray-800 text-gray-400">{t}</span>
                    ))}
                  </div>
                </td>
                <td className="px-4 py-3 text-xs text-gray-500">v{def.version}</td>
                <td className="px-4 py-3">
                  <button
                    onClick={() => handleToggle(def)}
                    disabled={toggling.has(def.id)}
                    className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none ${
                      def.is_active ? 'bg-rvp-success' : 'bg-gray-600'
                    } ${toggling.has(def.id) ? 'opacity-50 cursor-wait' : 'cursor-pointer'}`}
                    title={def.is_active ? 'Deactivate' : 'Activate'}
                  >
                    <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                      def.is_active ? 'translate-x-4' : 'translate-x-1'
                    }`} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showCreate && (
        <CreateModal
          onClose={() => setCreate(false)}
          onCreated={def => { setDefs(ds => [...ds, def]); setCreate(false) }}
        />
      )}
    </div>
  )
}
