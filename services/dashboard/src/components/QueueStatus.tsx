import { useEffect, useState } from 'react'
import { queuesApi } from '../api'
import type { QueueInfo } from '../types'

const FRIENDLY: Record<string, string> = {
  'sandbox.queue':       'Sandbox Requests',
  'test.commands':       'Test Commands',
  'test.results':        'Test Results',
  'ai.sessions':         'AI Sessions',
  'releases.ai-agent':   'PR Analysis',
  'releases.github':     'GitHub Events',
  'notifications.slack': 'Slack Notifs',
  'rvp.dlq':             'Dead Letters',
}

function QueueRow({ q }: { q: QueueInfo }) {
  const publishRate = q.message_stats?.publish_details?.rate ?? 0
  const deliverRate = q.message_stats?.deliver_details?.rate ?? 0
  const hasActivity = publishRate > 0 || deliverRate > 0

  return (
    <div className="flex items-center gap-3 py-2 text-sm border-b border-rvp-border/50 last:border-0">
      <div className="flex-1 min-w-0">
        <div className="text-gray-200 truncate">{FRIENDLY[q.name] ?? q.name}</div>
        {hasActivity && (
          <div className="text-xs text-gray-500 mt-0.5">
            ↑ {publishRate.toFixed(1)}/s · ↓ {deliverRate.toFixed(1)}/s
          </div>
        )}
      </div>
      <div className="flex items-center gap-2">
        <span className={`text-xs px-2 py-0.5 rounded font-mono ${
          q.messages > 0 ? 'bg-rvp-warning/20 text-rvp-warning' : 'bg-gray-800 text-gray-500'
        }`}>
          {q.messages}
        </span>
        <span className="text-xs text-gray-600">{q.consumers}c</span>
      </div>
    </div>
  )
}

export function QueueStatus() {
  const [queues, setQueues] = useState<QueueInfo[]>([])
  const [fetchedAt, setFetchedAt] = useState<string>()
  const [error, setError] = useState<string>()

  const refresh = async () => {
    try {
      const data = await queuesApi.depths()
      setQueues(data.queues)
      setFetchedAt(data.fetched_at)
      setError(undefined)
    } catch (e) {
      setError(String(e))
    }
  }

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 5000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-gray-200">Queue Depths</h2>
        {fetchedAt && (
          <span className="text-xs text-gray-500">
            {new Date(fetchedAt).toLocaleTimeString()}
          </span>
        )}
      </div>
      {error ? (
        <div className="text-xs text-rvp-error">{error}</div>
      ) : queues.length === 0 ? (
        <div className="text-xs text-gray-500 py-4 text-center">Loading…</div>
      ) : (
        <div>{queues.map((q) => <QueueRow key={q.name} q={q} />)}</div>
      )}
    </div>
  )
}
