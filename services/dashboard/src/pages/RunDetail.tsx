import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { runsApi } from '../api'
import { StatusBadge } from '../components/StatusBadge'
import { TestResultCard } from '../components/TestResultCard'
import { LiveLogs } from '../components/LiveLogs'
import { useWebSocket } from '../hooks/useWebSocket'
import type { Run, TestResult } from '../types'
import type { LogLine } from '../components/LiveLogs'
import { formatDistanceToNow, format } from 'date-fns'

export default function RunDetail() {
  const { runId } = useParams<{ runId: string }>()
  const [run, setRun] = useState<Run | null>(null)
  const [results, setResults] = useState<TestResult[]>([])
  const [logs, setLogs] = useState<LogLine[]>([])
  const [tab, setTab] = useState<'tests' | 'logs'>('tests')

  const loadRun = () => runId && runsApi.get(runId).then(setRun).catch(console.error)
  const loadResults = () => runId && runsApi.results(runId).then(setResults).catch(console.error)

  useEffect(() => { loadRun(); loadResults() }, [runId])

  useWebSocket({
    channel: runId,
    onEvent: (ev) => {
      if (ev.event_type.startsWith('run.') || ev.event_type.startsWith('test.')) {
        loadRun(); loadResults()
      }
      if (ev.event_type === 'test.started' || ev.event_type === 'test.completed') {
        const p = ev.payload
        setLogs(ls => [...ls, {
          ts: ev.ts,
          level: 'info',
          text: `[${ev.event_type}] ${p.definition_name ?? p.result_id ?? ''}`,
          source: 'test-runner',
        }])
      }
    },
  })

  if (!run) {
    return <div className="text-gray-500 text-sm">Loading…</div>
  }

  const duration = run.started_at && run.completed_at
    ? Math.round((new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()) / 1000)
    : null

  const passedCount = results.filter(r => r.status === 'passed').length
  const failedCount = results.filter(r => r.status === 'failed' || r.status === 'error').length

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Link to="/runs" className="text-gray-500 hover:text-gray-300 text-sm">← Runs</Link>
          </div>
          <h1 className="text-xl font-semibold text-gray-100 font-mono">{run.run_id.slice(0, 16)}</h1>
          {run.pr_number && <span className="text-sm text-gray-400 mt-0.5 block">PR #{run.pr_number}</span>}
        </div>
        <div className="flex items-center gap-3">
          <StatusBadge status={run.status} />
          {['pending', 'provisioning', 'running'].includes(run.status) && (
            <button
              className="btn-ghost text-rvp-error border-rvp-error/30 hover:bg-rvp-error/10"
              onClick={() => runsApi.cancel(run.run_id).then(loadRun)}
            >
              Cancel
            </button>
          )}
        </div>
      </div>

      {/* Stats strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'Version', value: run.node_version, mono: true },
          { label: 'Pass Rate', value: run.pass_rate != null ? `${run.pass_rate.toFixed(1)}%` : '—' },
          { label: 'Tests', value: `${passedCount} pass · ${failedCount} fail · ${results.length} total` },
          { label: 'Duration', value: duration != null ? `${duration}s` : '—' },
        ].map(stat => (
          <div key={stat.label} className="card px-4 py-3">
            <div className="text-xs text-gray-500 mb-1">{stat.label}</div>
            <div className={`text-sm font-semibold text-gray-200 ${stat.mono ? 'font-mono' : ''}`}>{stat.value}</div>
          </div>
        ))}
      </div>

      {/* Meta */}
      <div className="text-xs text-gray-500 flex gap-4 flex-wrap">
        <span>Triggered by: <span className="text-gray-400">{run.triggered_by}</span></span>
        <span>Created: <span className="text-gray-400">{format(new Date(run.created_at), 'MMM d yyyy, HH:mm:ss')}</span></span>
        {run.started_at && (
          <span>Started: <span className="text-gray-400">{formatDistanceToNow(new Date(run.started_at), { addSuffix: true })}</span></span>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-4 border-b border-rvp-border">
        {(['tests', 'logs'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`pb-2 text-sm font-medium capitalize transition-colors border-b-2 -mb-px ${
              tab === t ? 'border-rvp-primary text-rvp-primary' : 'border-transparent text-gray-500 hover:text-gray-300'
            }`}>
            {t} {t === 'tests' ? `(${results.length})` : `(${logs.length})`}
          </button>
        ))}
      </div>

      {tab === 'tests' && (
        <div className="space-y-2">
          {results.length === 0
            ? <div className="text-gray-500 text-sm py-4 text-center">No test results yet</div>
            : results.map(r => <TestResultCard key={r.result_id} result={r} />)
          }
        </div>
      )}

      {tab === 'logs' && (
        <LiveLogs lines={logs} className="h-[500px]" />
      )}
    </div>
  )
}
