import { useEffect, useState } from 'react'
import { sessionsApi } from '../api'
import type { SuggestedAction } from '../types'
import { format } from 'date-fns'

function ActionCard({ action, onReview }: { action: SuggestedAction; onReview: () => void }) {
  const [loading, setLoading] = useState<'approved' | 'rejected' | null>(null)
  const [open, setOpen] = useState(false)

  const review = async (status: 'approved' | 'rejected') => {
    setLoading(status)
    try { await sessionsApi.reviewSuggestion(action.action_id, status); onReview() }
    catch (e) { console.error(e) } finally { setLoading(null) }
  }

  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className={`badge ${
              action.status === 'pending' ? 'bg-rvp-warning/20 text-rvp-warning' :
              action.status === 'approved' ? 'bg-rvp-success/20 text-rvp-success' :
              'bg-gray-700 text-gray-400'}`}>
              {action.status}
            </span>
            <span className="text-xs text-gray-500 font-mono">{action.action_type}</span>
          </div>
          <div className="text-sm text-gray-200 font-medium">{action.description}</div>
          <div className="text-xs text-gray-500 mt-1">{action.rationale}</div>
          <div className="text-xs text-gray-600 mt-1">
            Session: {action.session_id.slice(0, 8)} · {format(new Date(action.created_at), 'MMM d, HH:mm')}
          </div>
        </div>
        {action.status === 'pending' && (
          <div className="flex gap-2 shrink-0">
            <button className="btn-primary text-xs py-1" disabled={!!loading}
              onClick={() => review('approved')}>
              {loading === 'approved' ? '…' : '✓ Approve'}
            </button>
            <button className="btn-ghost text-xs py-1 text-rvp-error border-rvp-error/30 hover:bg-rvp-error/10"
              disabled={!!loading} onClick={() => review('rejected')}>
              {loading === 'rejected' ? '…' : '✗ Reject'}
            </button>
          </div>
        )}
      </div>

      {action.test_definition_yaml && (
        <div>
          <button onClick={() => setOpen(!open)}
            className="w-full px-4 py-2 text-left text-xs text-gray-500 hover:text-gray-300 border-t border-rvp-border bg-rvp-bg/50 hover:bg-white/5 transition-colors">
            {open ? '▲ Hide YAML' : '▼ View test definition YAML'}
          </button>
          {open && (
            <pre className="px-4 py-3 text-xs font-mono text-gray-300 overflow-auto max-h-60 border-t border-rvp-border bg-rvp-bg">
              {action.test_definition_yaml}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}

export default function AISuggestions() {
  const [actions, setActions] = useState<SuggestedAction[]>([])
  const [filter, setFilter] = useState<'all' | 'pending' | 'approved' | 'rejected'>('all')

  const load = () => sessionsApi.suggestions().then(setActions).catch(console.error)
  useEffect(() => { load() }, [])

  const filtered = filter === 'all' ? actions : actions.filter(a => a.status === filter)
  const pending = actions.filter(a => a.status === 'pending').length

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-100">
          AI Suggestions
          {pending > 0 && <span className="ml-2 badge bg-rvp-warning/20 text-rvp-warning">{pending} pending</span>}
        </h1>
      </div>

      <div className="flex gap-2">
        {(['all', 'pending', 'approved', 'rejected'] as const).map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={`badge cursor-pointer capitalize ${filter === f ? 'bg-rvp-primary text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
            {f}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div className="text-gray-500 text-sm text-center py-8">No suggestions</div>
      ) : (
        <div className="space-y-3">
          {filtered.map(a => <ActionCard key={a.action_id} action={a} onReview={load} />)}
        </div>
      )}
    </div>
  )
}
