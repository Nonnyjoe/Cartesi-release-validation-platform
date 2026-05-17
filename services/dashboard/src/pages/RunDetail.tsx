import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { runsApi, releasesApi } from '../api'
import { StatusBadge } from '../components/StatusBadge'
import { TestResultCard } from '../components/TestResultCard'
import { SandboxSetupPanel } from '../components/SandboxSetupPanel'
import { useWebSocket } from '../hooks/useWebSocket'
import type { Run, TestResult, ReleaseEntry, RunEvent, RunLogLine } from '../types'
import type { StepEntry } from '../components/SandboxSetupPanel'
import { formatDistanceToNow, format } from 'date-fns'

// ─── helpers ──────────────────────────────────────────────────────────────────

const LIFECYCLE_LABELS: Record<string, string> = {
  'sandbox.provisioning': 'Sandbox provisioning started',
  'sandbox.ready':        'Sandbox ready — running tests',
  'sandbox.failed':       'Sandbox failed',
  'sandbox.closed':       'Sandbox closed',
  'run.queued':           'Run queued',
  'run.cancelled':        'Run cancelled',
}

function toStepEntry(
  step: string,
  status: string,
  ts: string,
  detail?: Record<string, unknown> | null,
  label?: string,
): StepEntry {
  return {
    step,
    status: (status as StepEntry['status']) ?? 'info',
    ts,
    detail: detail ?? undefined,
    label,
  }
}

function runEventToStepEntry(ev: RunEvent): StepEntry | null {
  const p = ev.payload ?? {}

  if (ev.event_type === 'sandbox.step') {
    return toStepEntry(
      String(p.step ?? ''),
      String(p.step_status ?? 'ok'),
      ev.ts,
      (p.detail as Record<string, unknown>) ?? null,
    )
  }

  const lifecycleLabel = LIFECYCLE_LABELS[ev.event_type]
  if (lifecycleLabel) {
    const status = ev.event_type.includes('failed') ? 'failed'
                 : ev.event_type.includes('cancelled') ? 'warn'
                 : 'ok'
    return toStepEntry(ev.event_type, status, ev.ts, null, lifecycleLabel)
  }

  return null
}

// ─── Log Viewer ───────────────────────────────────────────────────────────────

const LEVEL_COLORS: Record<string, string> = {
  error: 'text-red-400',
  warn:  'text-yellow-400',
  info:  'text-gray-300',
  debug: 'text-gray-500',
}

const SOURCE_PALETTE = [
  '#818cf8', '#34d399', '#fb923c', '#f472b6', '#60a5fa',
  '#a78bfa', '#4ade80', '#fbbf24', '#38bdf8', '#e879f9',
]
const sourceColorCache = new Map<string, string>()
let paletteIdx = 0

function sourceColor(source: string): string {
  if (!sourceColorCache.has(source)) {
    sourceColorCache.set(source, SOURCE_PALETTE[paletteIdx % SOURCE_PALETTE.length])
    paletteIdx++
  }
  return sourceColorCache.get(source)!
}

interface LogViewerProps {
  runId:    string
  isActive: boolean
}

function LogViewer({ runId, isActive }: LogViewerProps) {
  const [lines,       setLines]       = useState<RunLogLine[]>([])
  const [nextCursor,  setNextCursor]  = useState<number | null>(null)
  const [loading,     setLoading]     = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [sources,     setSources]     = useState<Set<string>>(new Set())
  const [activeSrcs,  setActiveSrcs]  = useState<Set<string>>(new Set())
  const [levelFilter, setLevelFilter] = useState<'all' | 'warn' | 'error'>('all')
  const [search,      setSearch]      = useState('')
  const [autoScroll,  setAutoScroll]  = useState(true)

  const bottomRef = useRef<HTMLDivElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  // ── Initial load ──────────────────────────────────────────────────────────
  useEffect(() => {
    setLoading(true)
    runsApi.logs(runId, { limit: 200 }).then(res => {
      setLines(res.lines)
      setNextCursor(res.next_cursor)
      // Build source list from initial batch
      setSources(prev => {
        const next = new Set(prev)
        res.lines.forEach(l => next.add(l.source))
        return next
      })
    }).catch(console.error).finally(() => setLoading(false))
  }, [runId])

  // ── Load older (pagination) ────────────────────────────────────────────
  const loadNewer = useCallback(() => {
    if (!nextCursor || loadingMore) return
    setLoadingMore(true)
    runsApi.logs(runId, { afterId: nextCursor, limit: 200 })
      .then(res => {
        setLines(prev => [...prev, ...res.lines])
        setNextCursor(res.next_cursor)
        setSources(prev => {
          const next = new Set(prev)
          res.lines.forEach(l => next.add(l.source))
          return next
        })
      })
      .catch(console.error)
      .finally(() => setLoadingMore(false))
  }, [runId, nextCursor, loadingMore])

  // ── Live WebSocket log_batch events ───────────────────────────────────
  useWebSocket({
    channel: runId,
    onEvent: (ev) => {
      if (ev.event_type !== 'log_batch') return
      const batch = (ev.lines ?? (ev.fields as Record<string, unknown>)?.lines ?? []) as RunLogLine[]
      if (!Array.isArray(batch) || batch.length === 0) return
      setLines(prev => [...prev, ...batch])
      setSources(prev => {
        const next = new Set(prev)
        batch.forEach((l: RunLogLine) => next.add(l.source))
        return next
      })
    },
  })

  // ── Auto-scroll ───────────────────────────────────────────────────────
  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [lines, autoScroll])

  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60
    if (!atBottom && autoScroll) setAutoScroll(false)
    if (atBottom && !autoScroll) setAutoScroll(true)
  }

  // ── Filtered view (client-side) ───────────────────────────────────────
  const LEVEL_RANKS: Record<string, number> = { error: 0, warn: 1, info: 2, debug: 3 }
  const minRank = levelFilter === 'error' ? 0 : levelFilter === 'warn' ? 1 : 99

  const filtered = useMemo(() => {
    return lines.filter(l => {
      if (activeSrcs.size > 0 && !activeSrcs.has(l.source)) return false
      if ((LEVEL_RANKS[l.level] ?? 2) > minRank) return false
      if (search && !l.message.toLowerCase().includes(search.toLowerCase())) return false
      return true
    })
  }, [lines, activeSrcs, levelFilter, search, minRank])

  const toggleSource = (src: string) => {
    setActiveSrcs(prev => {
      const next = new Set(prev)
      if (next.has(src)) next.delete(src); else next.add(src)
      return next
    })
  }

  const sortedSources = useMemo(() => [...sources].sort(), [sources])

  if (loading) return <div className="text-sm text-gray-500 py-8 text-center">Loading logs…</div>

  if (lines.length === 0) return (
    <div className="card p-8 text-center space-y-2">
      <div className="text-3xl">📋</div>
      <p className="text-sm text-gray-500">
        {isActive ? 'Waiting for log lines…' : 'No logs captured for this run.'}
      </p>
    </div>
  )

  return (
    <div className="flex gap-3 h-[600px]">
      {/* ── Source sidebar ── */}
      <aside className="w-44 shrink-0 flex flex-col gap-1 overflow-y-auto">
        <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1 px-1">Sources</div>
        <button
          className={`text-left text-xs px-2 py-1.5 rounded transition-colors ${
            activeSrcs.size === 0 ? 'bg-rvp-primary/20 text-rvp-primary' : 'text-gray-400 hover:bg-white/5'
          }`}
          onClick={() => setActiveSrcs(new Set())}
        >
          All sources
        </button>
        {sortedSources.map(src => (
          <button
            key={src}
            onClick={() => toggleSource(src)}
            className={`text-left text-xs px-2 py-1.5 rounded transition-colors truncate ${
              activeSrcs.has(src) ? 'bg-white/10 font-medium' : 'text-gray-500 hover:bg-white/5'
            }`}
            style={{ color: activeSrcs.has(src) ? sourceColor(src) : undefined }}
            title={src}
          >
            {src}
          </button>
        ))}

        <div className="mt-3 text-[10px] text-gray-500 uppercase tracking-wider px-1">Level</div>
        {(['all', 'warn', 'error'] as const).map(lvl => (
          <button
            key={lvl}
            onClick={() => setLevelFilter(lvl)}
            className={`text-left text-xs px-2 py-1.5 rounded transition-colors ${
              levelFilter === lvl ? 'bg-rvp-primary/20 text-rvp-primary' : 'text-gray-500 hover:bg-white/5'
            }`}
          >
            {lvl === 'all' ? 'All levels' : lvl === 'warn' ? '≥ warn' : 'Error only'}
          </button>
        ))}
      </aside>

      {/* ── Log pane ── */}
      <div className="flex-1 flex flex-col min-w-0 card overflow-hidden">
        {/* Controls bar */}
        <div className="flex items-center gap-2 px-3 py-2 border-b border-rvp-border shrink-0">
          <input
            className="input flex-1 h-7 text-xs py-0 placeholder-gray-600"
            placeholder="Search logs…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          <span className="text-xs text-gray-600 whitespace-nowrap">
            {filtered.length.toLocaleString()} lines
          </span>
          <button
            title={autoScroll ? 'Auto-scroll on' : 'Auto-scroll off'}
            onClick={() => setAutoScroll(v => !v)}
            className={`text-xs px-2 py-1 rounded transition-colors ${
              autoScroll ? 'bg-rvp-success/20 text-rvp-success' : 'text-gray-500 hover:bg-white/5'
            }`}
          >
            ⬇ Live
          </button>
          {nextCursor && (
            <button
              onClick={loadNewer}
              disabled={loadingMore}
              className="btn-ghost text-xs py-1 px-2"
            >
              {loadingMore ? '…' : 'Load more'}
            </button>
          )}
          <a
            href={runsApi.logsDownloadUrl(
              runId,
              activeSrcs.size === 1 ? [...activeSrcs][0] : undefined,
            )}
            download
            className="text-xs text-gray-500 hover:text-gray-300 transition-colors px-1"
            title="Download logs"
          >
            📥
          </a>
        </div>

        {/* Log lines — virtual-ish: render only what's here (DOM is manageable at ≤2000 lines) */}
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto font-mono text-xs leading-relaxed p-3 space-y-0.5"
        >
          {filtered.map((line, i) => {
            const ts   = line.ts ? format(new Date(line.ts), 'HH:mm:ss') : ''
            const color = LEVEL_COLORS[line.level] ?? 'text-gray-300'
            const sColor = sourceColor(line.source)
            return (
              <div
                key={line.id ?? i}
                className={`flex gap-2 hover:bg-white/[0.03] rounded px-1 py-0.5 ${color}`}
              >
                <span className="text-gray-600 shrink-0 w-16">{ts}</span>
                <span className="shrink-0 w-28 truncate" style={{ color: sColor }} title={line.source}>
                  [{line.source}]
                </span>
                <span className={`shrink-0 w-10 ${color}`}>{line.level.toUpperCase().slice(0, 4)}</span>
                <span className="flex-1 break-all whitespace-pre-wrap">{line.message}</span>
              </div>
            )
          })}
          {filtered.length === 0 && (
            <div className="text-gray-600 text-center py-4">No lines match current filters.</div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  )
}

// ─── Main RunDetail component ─────────────────────────────────────────────────

export default function RunDetail() {
  const { runId } = useParams<{ runId: string }>()

  const [run, setRun]           = useState<Run | null>(null)
  const [results, setResults]   = useState<TestResult[]>([])
  const [passRate, setPassRate] = useState<number | null>(null)
  const [steps, setSteps]       = useState<StepEntry[]>([])
  const [tab, setTab]           = useState<'tests' | 'logs' | 'setup'>('tests')
  const [release, setRelease]   = useState<ReleaseEntry | null>(null)

  const seenStepTsRef = useRef<Set<string>>(new Set())

  const loadRun = () => {
    if (runId) runsApi.get(runId).then(setRun).catch(console.error)
  }
  const loadResults = () => {
    if (!runId) return
    runsApi.report(runId).then(report => {
      setResults(report.results)
      setPassRate(report.pass_rate ?? null)
    }).catch(console.error)
  }

  useEffect(() => { loadRun(); loadResults() }, [runId])

  useEffect(() => {
    if (!run?.release_tag) return
    releasesApi.list().then(list => {
      setRelease(list.find(r => r.tag === run.release_tag) ?? null)
    }).catch(console.error)
  }, [run?.release_tag])

  // Hydrate setup panel from stored run events
  useEffect(() => {
    if (!runId) return
    runsApi.events(runId).then(evs => {
      const newSteps: StepEntry[] = []
      evs.forEach(ev => {
        const entry = runEventToStepEntry(ev)
        if (!entry) return
        const key = `${ev.ts}-${entry.step}`
        if (seenStepTsRef.current.has(key)) return
        seenStepTsRef.current.add(key)
        newSteps.push(entry)
      })
      if (newSteps.length) setSteps(newSteps)
    }).catch(console.error)
  }, [runId])

  // Real-time WebSocket — milestone events only (log lines go to LogViewer)
  useWebSocket({
    channel: runId,
    onEvent: (ev) => {
      if (ev.event_type === 'log_batch') return  // handled by LogViewer directly

      if (ev.event_type.startsWith('run.') || ev.event_type.startsWith('test.')
          || ev.event_type === 'sandbox.ready' || ev.event_type === 'sandbox.failed') {
        loadRun()
        loadResults()
      }

      if (ev.event_type === 'sandbox.step') {
        const fields     = (ev.fields ?? {}) as Record<string, unknown>
        const step       = String(fields.step ?? '')
        const stepStatus = String(fields.step_status ?? 'ok')
        if (step === 'service_log') return  // handled by LogViewer

        const detail = fields.detail
          ? (fields.detail as Record<string, unknown>)
          : Object.fromEntries(
              Object.entries(fields).filter(([k]) =>
                !['step', 'step_status', 'run_id', 'sandbox_id', 'event_id',
                  'service', 'title', 'event_type'].includes(k)
              )
            )
        const key = `${ev.ts}-${step}`
        if (!seenStepTsRef.current.has(key)) {
          seenStepTsRef.current.add(key)
          setSteps(ss => [...ss, toStepEntry(step, stepStatus, ev.ts, detail)])
        }
        return
      }

      const lifecycleLabel = LIFECYCLE_LABELS[ev.event_type]
      if (lifecycleLabel) {
        const status = ev.event_type.includes('failed') ? 'failed'
                     : ev.event_type.includes('cancelled') ? 'warn'
                     : 'ok'
        const key = `${ev.ts}-${ev.event_type}`
        if (!seenStepTsRef.current.has(key)) {
          seenStepTsRef.current.add(key)
          setSteps(ss => [...ss, toStepEntry(ev.event_type, status, ev.ts, null, lifecycleLabel)])
        }
      }
    },
  })

  if (!run) {
    return <div className="text-gray-500 text-sm">Loading…</div>
  }

  const duration = run.started_at && run.completed_at
    ? Math.round(
        (new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()) / 1000
      )
    : null

  const passedCount = results.filter(r => r.status === 'passed').length
  const failedCount = results.filter(r => r.status === 'failed' || r.status === 'error').length
  const isActive    = ['queued', 'provisioning', 'running'].includes(run.status)

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Link to="/runs" className="text-gray-500 hover:text-gray-300 text-sm">← Runs</Link>
          </div>
          <h1 className="text-xl font-semibold text-gray-100 font-mono">{run.id.slice(0, 16)}</h1>
          <span className="text-sm text-gray-400 mt-0.5 block">{run.release_tag}</span>
        </div>
        <div className="flex items-center gap-3">
          <StatusBadge status={run.status} />
          {isActive && (
            <button
              className="btn-ghost text-rvp-error border-rvp-error/30 hover:bg-rvp-error/10"
              onClick={() => runsApi.cancel(run.id).then(() => loadRun())}
            >
              Cancel
            </button>
          )}
        </div>
      </div>

      {/* Stats strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'Image',     value: run.image_tag,  mono: true },
          { label: 'Pass Rate', value: passRate != null ? `${passRate.toFixed(1)}%` : '—' },
          { label: 'Tests',     value: `${passedCount} pass · ${failedCount} fail · ${results.length} total` },
          { label: 'Duration',  value: duration != null ? `${duration}s` : '—' },
        ].map(stat => (
          <div key={stat.label} className="card px-4 py-3">
            <div className="text-xs text-gray-500 mb-1">{stat.label}</div>
            <div
              className={`text-sm font-semibold text-gray-200 truncate ${stat.mono ? 'font-mono' : ''}`}
              title={stat.mono ? String(stat.value) : undefined}
            >
              {stat.value}
            </div>
          </div>
        ))}
      </div>

      {/* Toolchain panel */}
      {release && (
        <div className="card px-4 py-3">
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            Toolchain
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: 'SDK',       value: release.sdk_version },
              { label: 'CLI',       value: release.cli_version },
              { label: 'Devnet',    value: release.devnet_version },
              { label: 'Contracts', value: release.contracts_version },
            ].map(({ label, value }) => (
              <div key={label}>
                <div className="text-[10px] text-gray-600 mb-0.5">{label}</div>
                {value ? (
                  <div className="font-mono text-xs text-rvp-info truncate">{value}</div>
                ) : (
                  <div className="text-xs text-gray-600 italic">unknown</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Meta */}
      <div className="text-xs text-gray-500 flex gap-4 flex-wrap">
        <span>Triggered by: <span className="text-gray-400">{run.triggered_by}</span></span>
        <span>Priority: <span className="text-gray-400">{run.priority}</span></span>
        <span>Queued: <span className="text-gray-400">{format(new Date(run.queued_at), 'MMM d yyyy, HH:mm:ss')}</span></span>
        {run.started_at && (
          <span>Started: <span className="text-gray-400">{formatDistanceToNow(new Date(run.started_at), { addSuffix: true })}</span></span>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-4 border-b border-rvp-border">
        {([
          { key: 'tests', label: `Tests (${results.length})` },
          { key: 'setup', label: `Setup (${steps.length})` },
          { key: 'logs',  label: 'Logs' },
        ] as const).map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`pb-2 text-sm font-medium capitalize transition-colors border-b-2 -mb-px ${
              tab === t.key
                ? 'border-rvp-primary text-rvp-primary'
                : 'border-transparent text-gray-500 hover:text-gray-300'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'tests' && (
        <div className="space-y-2">
          {results.length === 0
            ? <div className="text-gray-500 text-sm py-4 text-center">No test results yet</div>
            : results.map(r => <TestResultCard key={r.id} result={r} />)
          }
        </div>
      )}

      {tab === 'setup' && (
        <SandboxSetupPanel steps={steps} isActive={isActive} />
      )}

      {tab === 'logs' && runId && (
        <LogViewer runId={runId} isActive={isActive} />
      )}
    </div>
  )
}
