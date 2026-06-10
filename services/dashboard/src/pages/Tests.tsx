import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { testsApi } from '../api'
import type { TestDefinition, PhaseGroup } from '../types'

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
phase: ""
category: ""
tags: [smoke, v2]
timeout_seconds: 120
min_node_major_version: 2
assertions:
  - type: http_status
    url: /health
    expected_status: 200
---
Describe what this test validates.
`

/** Replace or insert a key:value line inside the YAML frontmatter block. */
function setYamlField(content: string, key: string, value: string): string {
  const frontmatterRe = /^(---\n)([\s\S]*?)(\n---\n)/
  const m = content.match(frontmatterRe)
  if (!m) return content

  const body  = m[2]
  const lineRe = new RegExp(`^(${key}:).*$`, 'm')
  const newLine = `${key}: "${value}"`

  const newBody = lineRe.test(body)
    ? body.replace(lineRe, newLine)
    : `${body}\n${newLine}`

  return content.replace(frontmatterRe, `${m[1]}${newBody}${m[3]}`)
}

function CreateModal({ onClose, onCreated }: { onClose: () => void; onCreated: (d: TestDefinition) => void }) {
  const [content,       setContent]       = useState(YAML_TEMPLATE)
  const [loading,       setLoading]       = useState(false)
  const [error,         setError]         = useState('')
  const [phases,        setPhases]        = useState<PhaseGroup[]>([])
  const [selectedPhase, setSelectedPhase] = useState('')
  const [selectedCat,   setSelectedCat]   = useState('')

  useEffect(() => {
    testsApi.categories().then(setPhases).catch(console.error)
  }, [])

  const phaseCategories = useMemo(
    () => phases.find(p => p.phase === selectedPhase)?.categories ?? [],
    [phases, selectedPhase],
  )

  const handlePhaseChange = (phase: string) => {
    setSelectedPhase(phase)
    setSelectedCat('')
    setContent(c => setYamlField(setYamlField(c, 'phase', phase), 'category', ''))
  }

  const handleCatChange = (cat: string) => {
    setSelectedCat(cat)
    setContent(c => setYamlField(c, 'category', cat))
  }

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
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="card w-full max-w-2xl p-6 space-y-4 max-h-[92vh] overflow-y-auto">
        <h2 className="text-lg font-semibold text-gray-100">Create Test Definition</h2>
        <form onSubmit={submit} className="space-y-4">

          {/* Phase / Category pickers */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-400 block mb-1">Phase</label>
              <select
                className="input w-full text-sm"
                value={selectedPhase}
                onChange={e => handlePhaseChange(e.target.value)}
              >
                <option value="">— select phase —</option>
                {phases.map(p => (
                  <option key={p.phase} value={p.phase}>{p.phase}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-400 block mb-1">Category</label>
              <select
                className="input w-full text-sm"
                value={selectedCat}
                onChange={e => handleCatChange(e.target.value)}
                disabled={!selectedPhase}
              >
                <option value="">— select category —</option>
                {phaseCategories.map(c => (
                  <option key={c.category} value={c.category}>
                    {c.category} ({c.active_count})
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* YAML editor */}
          <div>
            <label className="text-xs text-gray-400 block mb-1">
              YAML Frontmatter + Description
              <span className="ml-2 text-gray-600">
                — phase &amp; category are synced from the pickers above
              </span>
            </label>
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

// ─── Test row ─────────────────────────────────────────────────────────────────

function TestRow({
  def,
  toggling,
  aiToggling,
  onToggle,
  onToggleAi,
  onClick,
}: {
  def:         TestDefinition
  toggling:    Set<string>
  aiToggling:  Set<string>
  onToggle:    (def: TestDefinition) => void
  onToggleAi:  (def: TestDefinition) => void
  onClick:     (def: TestDefinition) => void
}) {
  return (
    <tr
      className="hover:bg-white/5 transition-colors cursor-pointer"
      onClick={e => {
        if ((e.target as HTMLElement).closest('button')) return
        onClick(def)
      }}
    >
      <td className="px-4 py-2.5 pl-8">
        <div className="text-gray-200 font-medium text-sm">{def.name}</div>
        <div className="font-mono text-xs text-gray-500 mt-0.5">{def.slug}</div>
      </td>
      <td className="px-4 py-2.5">
        <span className={`badge text-xs ${PRIORITY_BADGE[def.priority] ?? 'bg-gray-700 text-gray-400'}`}>
          {def.priority}
        </span>
      </td>
      <td className="px-4 py-2.5 text-xs text-gray-500">{def.component ?? '—'}</td>
      <td className="px-4 py-2.5">
        <div className="flex flex-wrap gap-1">
          {def.tags.slice(0, 4).map(t => (
            <span key={t} className="badge text-xs bg-gray-800 text-gray-400">{t}</span>
          ))}
          {def.tags.length > 4 && (
            <span className="badge text-xs bg-gray-800 text-gray-500">+{def.tags.length - 4}</span>
          )}
        </div>
      </td>
      <td className="px-4 py-2.5 text-xs text-gray-500">v{def.version}</td>
      <td className="px-4 py-2.5">
        <button
          onClick={() => onToggle(def)}
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
      <td className="px-4 py-2.5">
        <button
          onClick={() => onToggleAi(def)}
          disabled={aiToggling.has(def.id)}
          className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none ${
            def.ai_allowed ? 'bg-rvp-primary' : 'bg-gray-600'
          } ${aiToggling.has(def.id) ? 'opacity-50 cursor-wait' : 'cursor-pointer'}`}
          title={def.ai_allowed ? 'Disable AI access' : 'Allow AI to invoke this test'}
        >
          <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
            def.ai_allowed ? 'translate-x-4' : 'translate-x-1'
          }`} />
        </button>
      </td>
    </tr>
  )
}

// ─── Category section (within a phase) ───────────────────────────────────────

function CategorySection({
  category,
  tests,
  toggling,
  aiToggling,
  onToggle,
  onToggleAi,
  onClick,
}: {
  category:    string
  tests:       TestDefinition[]
  toggling:    Set<string>
  aiToggling:  Set<string>
  onToggle:    (def: TestDefinition) => void
  onToggleAi:  (def: TestDefinition) => void
  onClick:     (def: TestDefinition) => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <tbody>
      <tr
        className="cursor-pointer select-none hover:bg-white/3 transition-colors"
        onClick={() => setOpen(o => !o)}
      >
        <td colSpan={7} className="px-4 py-2 pl-6 text-xs font-medium text-gray-400">
          <span className="mr-1.5 text-gray-600">{open ? '▼' : '▶'}</span>
          {category}
          <span className="ml-2 text-gray-600">({tests.length})</span>
        </td>
      </tr>
      {open && tests.map(def => (
        <TestRow
          key={def.id}
          def={def}
          toggling={toggling}
          aiToggling={aiToggling}
          onToggle={onToggle}
          onToggleAi={onToggleAi}
          onClick={onClick}
        />
      ))}
    </tbody>
  )
}

// ─── Phase section ────────────────────────────────────────────────────────────

function PhaseSection({
  phase,
  tests,
  toggling,
  aiToggling,
  onToggle,
  onToggleAi,
  onClick,
  defaultOpen,
}: {
  phase:       string
  tests:       TestDefinition[]
  toggling:    Set<string>
  aiToggling:  Set<string>
  onToggle:    (def: TestDefinition) => void
  onToggleAi:  (def: TestDefinition) => void
  onClick:     (def: TestDefinition) => void
  defaultOpen: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)

  const byCategory = useMemo(() => {
    const map = new Map<string, TestDefinition[]>()
    for (const t of tests) {
      const key = t.category ?? 'Uncategorized'
      const arr = map.get(key) ?? []
      arr.push(t)
      map.set(key, arr)
    }
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b))
  }, [tests])

  const activeCount = tests.filter(t => t.is_active).length

  return (
    <div className="border border-rvp-border rounded-lg overflow-hidden mb-3">
      <button
        className="w-full flex items-center gap-3 px-4 py-3 bg-rvp-surface hover:bg-white/5 transition-colors text-left"
        onClick={() => setOpen(o => !o)}
      >
        <span className="text-gray-500 text-xs w-3">{open ? '▼' : '▶'}</span>
        <span className="font-medium text-gray-200 flex-1">{phase}</span>
        <span className="text-xs text-gray-500">
          {activeCount}/{tests.length} active
        </span>
        <span className="badge bg-gray-800 text-gray-400 text-xs ml-2">
          {tests.length} tests
        </span>
      </button>

      {open && (
        <table className="w-full text-sm border-t border-rvp-border">
          <thead>
            <tr className="text-xs text-gray-500 text-left border-b border-rvp-border/50 bg-rvp-bg/40">
              <th className="px-4 py-2 pl-8">Name / Slug</th>
              <th className="px-4 py-2">Priority</th>
              <th className="px-4 py-2">Component</th>
              <th className="px-4 py-2">Tags</th>
              <th className="px-4 py-2">Ver</th>
              <th className="px-4 py-2">Active</th>
              <th className="px-4 py-2" title="AI agent may invoke this test">AI</th>
            </tr>
          </thead>
          {byCategory.map(([cat, catTests]) => (
            <CategorySection
              key={cat}
              category={cat}
              tests={catTests}
              toggling={toggling}
              aiToggling={aiToggling}
              onToggle={onToggle}
              onToggleAi={onToggleAi}
              onClick={onClick}
            />
          ))}
        </table>
      )}
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function Tests() {
  const navigate = useNavigate()
  const [defs, setDefs]         = useState<TestDefinition[]>([])
  const [phases, setPhases]     = useState<PhaseGroup[]>([])
  const [loading, setLoading]   = useState(true)
  const [showCreate, setCreate] = useState(false)
  const [filter, setFilter]     = useState<'all' | 'active' | 'inactive'>('all')
  const [search, setSearch]     = useState('')
  const [toggling, setToggling] = useState<Set<string>>(new Set())
  const [aiToggling, setAiToggling] = useState<Set<string>>(new Set())

  const load = async () => {
    try {
      const [allDefs, allPhases] = await Promise.all([testsApi.list(), testsApi.categories()])
      setDefs(allDefs)
      setPhases(allPhases)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleToggle = async (def: TestDefinition) => {
    setToggling(s => new Set(s).add(def.id))
    try {
      const updated = await testsApi.toggle(def.id, !def.is_active)
      setDefs(ds => ds.map(d => d.id === updated.id ? updated : d))
    } catch (e) {
      console.error(e)
    } finally {
      setToggling(s => { const n = new Set(s); n.delete(def.id); return n })
    }
  }

  const handleToggleAi = async (def: TestDefinition) => {
    setAiToggling(s => new Set(s).add(def.id))
    try {
      const updated = await testsApi.toggleAiAllowed(def.id, !def.ai_allowed)
      setDefs(ds => ds.map(d => d.id === updated.id ? updated : d))
    } catch (e) {
      console.error(e)
    } finally {
      setAiToggling(s => { const n = new Set(s); n.delete(def.id); return n })
    }
  }

  const handleClick = (def: TestDefinition) => navigate(`/tests/${def.id}`)

  // Apply global filter and search to definitions
  const visibleDefs = useMemo(() => {
    const q = search.toLowerCase()
    return defs.filter(d => {
      if (filter === 'active'   && !d.is_active)  return false
      if (filter === 'inactive' &&  d.is_active)  return false
      if (q && !d.name.toLowerCase().includes(q) && !d.slug.includes(q)) return false
      return true
    })
  }, [defs, filter, search])

  // Build phase → test map from visible defs, preserving phase order from categories endpoint
  const visibleByPhase = useMemo(() => {
    const phaseMap = new Map<string, TestDefinition[]>()
    for (const def of visibleDefs) {
      const key = def.phase ?? '__uncategorized__'
      const arr = phaseMap.get(key) ?? []
      arr.push(def)
      phaseMap.set(key, arr)
    }
    // Ordered by phase_number from /tests/categories
    const ordered: Array<{ phase: string; tests: TestDefinition[] }> = []
    for (const pg of phases) {
      if (phaseMap.has(pg.phase)) {
        ordered.push({ phase: pg.phase, tests: phaseMap.get(pg.phase)! })
      }
    }
    // Uncategorized at the end
    if (phaseMap.has('__uncategorized__')) {
      ordered.push({ phase: 'Uncategorized', tests: phaseMap.get('__uncategorized__')! })
    }
    return ordered
  }, [visibleDefs, phases])

  const activeCount   = defs.filter(d => d.is_active).length
  const inactiveCount = defs.length - activeCount

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-gray-100">Test Definitions</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            {activeCount} active · {inactiveCount} inactive · {defs.length} total
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Search */}
          <input
            type="text"
            placeholder="Search tests…"
            className="input text-sm py-1.5 w-52"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          <button className="btn-primary whitespace-nowrap" onClick={() => setCreate(true)}>+ New Definition</button>
        </div>
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

      {/* Content */}
      {loading ? (
        <div className="text-center text-gray-500 py-12">Loading…</div>
      ) : visibleByPhase.length === 0 ? (
        <div className="text-center text-gray-500 py-12">No tests match your filter</div>
      ) : (
        <div>
          {visibleByPhase.map(({ phase, tests }, i) => (
            <PhaseSection
              key={phase}
              phase={phase}
              tests={tests}
              toggling={toggling}
              aiToggling={aiToggling}
              onToggle={handleToggle}
              onToggleAi={handleToggleAi}
              onClick={handleClick}
              defaultOpen={i === 0}
            />
          ))}
        </div>
      )}

      {showCreate && (
        <CreateModal
          onClose={() => setCreate(false)}
          onCreated={def => { setDefs(ds => [...ds, def]); setCreate(false) }}
        />
      )}
    </div>
  )
}
