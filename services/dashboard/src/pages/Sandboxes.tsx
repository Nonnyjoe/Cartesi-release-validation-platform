import { useEffect, useState } from 'react'
import { sandboxesApi } from '../api'
import { StatusBadge } from '../components/StatusBadge'
import { useWebSocket } from '../hooks/useWebSocket'
import type { Sandbox } from '../types'
import { format } from 'date-fns'

export default function Sandboxes() {
  const [sandboxes, setSandboxes] = useState<Sandbox[]>([])

  const load = () => sandboxesApi.list().then(setSandboxes).catch(console.error)
  useEffect(() => { load() }, [])
  useWebSocket({ onEvent: (ev) => { if (ev.event_type.startsWith('sandbox.')) load() } })

  const active = sandboxes.filter(s => ['provisioning', 'ready', 'in_use'].includes(s.status))
  const historical = sandboxes.filter(s => ['teardown', 'failed'].includes(s.status))

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold text-gray-100">Sandboxes</h1>

      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'Active', value: active.length, color: 'text-rvp-success' },
          { label: 'In Use', value: sandboxes.filter(s => s.status === 'in_use').length, color: 'text-rvp-warning' },
          { label: 'Failed', value: sandboxes.filter(s => s.status === 'failed').length, color: 'text-rvp-error' },
        ].map(stat => (
          <div key={stat.label} className="card px-4 py-3 text-center">
            <div className={`text-2xl font-bold ${stat.color}`}>{stat.value}</div>
            <div className="text-xs text-gray-500 mt-1">{stat.label}</div>
          </div>
        ))}
      </div>

      {sandboxes.length === 0 ? (
        <div className="text-gray-500 text-sm text-center py-8">No sandboxes found</div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-rvp-border text-xs text-gray-500 text-left">
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Version</th>
                <th className="px-4 py-3">Run</th>
                <th className="px-4 py-3">Ports</th>
                <th className="px-4 py-3">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-rvp-border/50">
              {sandboxes.map(sb => (
                <tr key={sb.sandbox_id} className="hover:bg-white/5 transition-colors">
                  <td className="px-4 py-3 font-mono text-xs text-gray-300">{sb.sandbox_id.slice(0, 12)}</td>
                  <td className="px-4 py-3"><StatusBadge status={sb.status} /></td>
                  <td className="px-4 py-3 font-mono text-xs text-gray-400">{sb.node_version ?? '—'}</td>
                  <td className="px-4 py-3 font-mono text-xs text-gray-500">{sb.run_id?.slice(0, 8) ?? '—'}</td>
                  <td className="px-4 py-3 text-xs text-gray-500">
                    {sb.anvil_port ? `${sb.anvil_port} · ${sb.node_port} · ${sb.graphql_port}` : '—'}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500">
                    {format(new Date(sb.created_at), 'MMM d, HH:mm:ss')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
