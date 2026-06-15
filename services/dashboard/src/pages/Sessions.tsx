import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { sessionsApi, testsApi } from '../api'
import { StatusBadge } from '../components/StatusBadge'
import { useWebSocket } from '../hooks/useWebSocket'
import type { AISession, AIMode, TestDefinition } from '../types'
import { format } from 'date-fns'

// Event types that should trigger a Sessions list refresh
const AI_LIST_EVENTS = new Set([
  'ai.session_created',
  'session_started',
  'session_completed',
  'session_failed',
  'ai.tool_call',
  'ai.tool_result',
  'ai.finding',
  'bootstrap_started',
  'bootstrap_ready',
])

const MODES: AIMode[] = ['autonomous', 'collaborative', 'interactive']

const MODELS = [
  { id: 'claude-opus-4-6',          label: 'Opus 4.6 (most capable)' },
  { id: 'claude-sonnet-4-6',        label: 'Sonnet 4.6 (balanced)' },
  { id: 'claude-haiku-4-5-20251001', label: 'Haiku 4.5 (fast)' },
] as const

// Mirrors the orchestrator's AI_MANUAL_MAX_PHASES default — server enforces too.
const MAX_PHASES_PER_SESSION = 2

function PhasePicker({ selectedPhases, onPhasesChange, excluded, onExcludedChange }: {
  selectedPhases: string[]
  onPhasesChange: (phases: string[]) => void
  excluded: string[]                       // per-test trim: slugs unticked within selected phases
  onExcludedChange: (slugs: string[]) => void
}) {
  const [defs, setDefs] = useState<TestDefinition[]>([])
  const [openPhase, setOpenPhase] = useState<string | null>(null)

  useEffect(() => {
    testsApi.list({ ai_allowed: true }).then(setDefs).catch(() => setDefs([]))
  }, [])

  // Same grouping as the Tests page: phase → tests (ai-runnable only).
  const phases = useMemo(() => {
    const m = new Map<string, TestDefinition[]>()
    for (const d of defs) {
      const p = d.phase || 'Unphased'
      if (!m.has(p)) m.set(p, [])
      m.get(p)!.push(d)
    }
    return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0], undefined, { numeric: true }))
  }, [defs])

  const togglePhase = (phase: string) => {
    if (selectedPhases.includes(phase)) {
      onPhasesChange(selectedPhases.filter(p => p !== phase))
      const phaseSlugs = new Set((phases.find(([p]) => p === phase)?.[1] ?? []).map(d => d.slug))
      onExcludedChange(excluded.filter(s => !phaseSlugs.has(s)))
      if (openPhase === phase) setOpenPhase(null)
    } else if (selectedPhases.length < MAX_PHASES_PER_SESSION) {
      onPhasesChange([...selectedPhases, phase])
    }
  }

  const toggleTest = (slug: string) =>
    onExcludedChange(excluded.includes(slug) ? excluded.filter(s => s !== slug) : [...excluded, slug])

  const selectedCount = useMemo(() => {
    let n = 0
    for (const [p, tests] of phases) {
      if (selectedPhases.includes(p)) n += tests.filter(t => !excluded.includes(t.slug)).length
    }
    return n
  }, [phases, selectedPhases, excluded])

  return (
    <div>
      <label className="text-xs text-gray-400 block mb-1">
        Test phases <span className="text-gray-500">
          ({selectedPhases.length}/{MAX_PHASES_PER_SESSION} phases · {selectedCount} tests selected)
        </span>
      </label>
      <div className="border border-rvp-border rounded max-h-56 overflow-y-auto divide-y divide-rvp-border/50">
        {phases.map(([phase, tests]) => {
          const isSelected = selectedPhases.includes(phase)
          const isOpen = openPhase === phase
          const atLimit = !isSelected && selectedPhases.length >= MAX_PHASES_PER_SESSION
          const kept = tests.filter(t => !excluded.includes(t.slug)).length
          return (
            <div key={phase}>
              <div className={`flex items-center gap-2 px-2 py-1.5 ${atLimit ? 'opacity-40' : 'hover:bg-white/5'}`}>
                <input type="checkbox" checked={isSelected} disabled={atLimit}
                  onChange={() => togglePhase(phase)} />
                <button type="button" className="flex-1 text-left min-w-0"
                  onClick={() => setOpenPhase(isOpen ? null : phase)}>
                  <span className="text-xs text-gray-200">{phase}</span>
                  <span className="text-[10px] text-gray-500 ml-2">
                    {isSelected ? `${kept}/${tests.length}` : tests.length} tests
                  </span>
                </button>
                <button type="button" className="text-gray-500 text-xs px-1"
                  onClick={() => setOpenPhase(isOpen ? null : phase)}>
                  {isOpen ? '▾' : '▸'}
                </button>
              </div>
              {isOpen && (
                <div className="bg-rvp-bg/50 max-h-36 overflow-y-auto divide-y divide-rvp-border/30">
                  {tests.map(d => (
                    <label key={d.slug}
                      className={`flex items-start gap-2 pl-7 pr-2 py-1 cursor-pointer hover:bg-white/5 ${!isSelected ? 'opacity-50' : ''}`}>
                      <input type="checkbox" className="mt-0.5" disabled={!isSelected}
                        checked={isSelected && !excluded.includes(d.slug)}
                        onChange={() => toggleTest(d.slug)} />
                      <span className="min-w-0">
                        <span className="block text-[11px] font-mono text-gray-300 truncate">{d.slug}</span>
                        <span className="block text-[10px] text-gray-500 truncate">{d.name}</span>
                      </span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          )
        })}
        {phases.length === 0 && (
          <div className="px-2 py-3 text-center text-xs text-gray-500">No runnable test definitions found</div>
        )}
      </div>
      <div className="text-[10px] text-gray-500 mt-1">
        Same phases as the Tests section (chaos phase excluded). Pick up to {MAX_PHASES_PER_SESSION} phases;
        expand a phase to trim individual tests. The agent chooses the execution order and its own inputs.
      </div>
    </div>
  )
}

function NewSessionModal({ onClose }: { onClose: () => void }) {
  const [form, setForm] = useState({
    mode: 'autonomous',
    run_id: '',
    sandbox_id: '',
    goal: '',
    execution_mode: 'runner',
    anthropic_api_key: '',
    model_id: 'claude-opus-4-6',
  })
  // 'bootstrap' = the platform provisions a dedicated sandbox first (contracts,
  // tokens and app pre-deployed); the agent starts only when it is ready.
  const [envMode, setEnvMode] = useState<'bootstrap' | 'existing'>('bootstrap')
  const [selectedPhases, setSelectedPhases] = useState<string[]>([])
  const [excludedTests, setExcludedTests] = useState<string[]>([])
  const [allDefs, setAllDefs] = useState<TestDefinition[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (form.execution_mode === 'ai_manual') {
      testsApi.list({ ai_allowed: true }).then(setAllDefs).catch(() => setAllDefs([]))
    }
  }, [form.execution_mode])

  // Final slug list = every runnable test in the selected phases minus trims,
  // ordered by phase then slug (the agent re-orders within its plan).
  const finalSlugs = useMemo(() => {
    if (selectedPhases.length === 0) return []
    return allDefs
      .filter(d => selectedPhases.includes(d.phase || 'Unphased') && !excludedTests.includes(d.slug))
      .sort((a, b) => (a.phase || '').localeCompare(b.phase || '', undefined, { numeric: true })
                      || a.slug.localeCompare(b.slug))
      .map(d => d.slug)
  }, [allDefs, selectedPhases, excludedTests])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.anthropic_api_key || form.anthropic_api_key.length < 20) {
      setError('Anthropic API key is required (sk-ant-…).')
      return
    }
    if (envMode === 'existing' && !form.sandbox_id) {
      setError('Enter a sandbox ID, or switch to "Bootstrap new sandbox".')
      return
    }
    if (form.execution_mode === 'ai_manual' && finalSlugs.length === 0) {
      setError('Select at least one phase (with at least one test kept) for manual execution.')
      return
    }
    setLoading(true)
    try {
      await sessionsApi.create({
        mode: form.mode,
        run_id: envMode === 'existing' ? (form.run_id || undefined) : undefined,
        sandbox_id: envMode === 'existing' ? (form.sandbox_id || undefined) : undefined,
        bootstrap: envMode === 'bootstrap' || undefined,
        goal: form.goal || undefined,
        execution_mode: form.execution_mode,
        selected_phases: form.execution_mode === 'ai_manual' ? selectedPhases : undefined,
        selected_tests: form.execution_mode === 'ai_manual' ? finalSlugs : undefined,
        anthropic_api_key: form.anthropic_api_key,
        model_id: form.model_id,
      })
      onClose()
    } catch (e) { setError(String(e)) } finally { setLoading(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="card w-full max-w-md p-6 space-y-4 max-h-[90vh] overflow-y-auto">
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
            <label className="text-xs text-gray-400 block mb-1">Test execution</label>
            <select className="input w-full" value={form.execution_mode}
              onChange={e => setForm(f => ({ ...f, execution_mode: e.target.value }))}>
              <option value="runner">Runner — agent delegates to the test-runner (trigger_test)</option>
              <option value="ai_manual">Manual — agent executes each test itself, step by step</option>
            </select>
            {form.execution_mode === 'ai_manual' && (
              <div className="text-[10px] text-gray-500 mt-1">
                The agent reads each definition, decides the inputs, runs every step with
                primitive tools and records its own verdicts.
              </div>
            )}
          </div>
          {form.execution_mode === 'ai_manual' && (
            <PhasePicker
              selectedPhases={selectedPhases} onPhasesChange={setSelectedPhases}
              excluded={excludedTests} onExcludedChange={setExcludedTests} />
          )}
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
            <label className="text-xs text-gray-400 block mb-1">Environment</label>
            <select className="input w-full" value={envMode}
              onChange={e => setEnvMode(e.target.value as 'bootstrap' | 'existing')}>
              <option value="bootstrap">Bootstrap new sandbox — provision first, then start the agent</option>
              <option value="existing">Use an existing sandbox (enter ID below)</option>
            </select>
            {envMode === 'bootstrap' && (
              <div className="text-[10px] text-gray-500 mt-1">
                Contracts, test tokens and the application are deployed before the agent
                starts (fast when the Anvil state cache is warm). Progress streams live below.
              </div>
            )}
          </div>
          {envMode === 'existing' && (
            <>
              <div>
                <label className="text-xs text-gray-400 block mb-1">Run ID (optional)</label>
                <input className="input w-full" placeholder="uuid" value={form.run_id}
                  onChange={e => setForm(f => ({ ...f, run_id: e.target.value }))} />
              </div>
              <div>
                <label className="text-xs text-gray-400 block mb-1">Sandbox ID</label>
                <input className="input w-full" placeholder="uuid" value={form.sandbox_id}
                  onChange={e => setForm(f => ({ ...f, sandbox_id: e.target.value }))} />
              </div>
            </>
          )}
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
                <td className="px-4 py-3">
                  <StatusBadge status={s.mode} />
                  {s.execution_mode === 'ai_manual' && (
                    <div className="text-[10px] text-rvp-info mt-0.5">manual ({s.selected_tests.length} tests)</div>
                  )}
                </td>
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
