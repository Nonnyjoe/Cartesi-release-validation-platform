import { useEffect, useState } from 'react'
import clsx from 'clsx'
import { sandboxesApi } from '../api'
import { StatusBadge } from './StatusBadge'
import type { Sandbox } from '../types'

const MAX_SANDBOXES = parseInt(import.meta.env.VITE_MAX_SANDBOXES ?? '3', 10)

function SandboxCard({ sb }: { sb: Sandbox }) {
  return (
    <div className="card px-3 py-2 text-xs space-y-1">
      <div className="flex items-center justify-between">
        <span className="font-mono text-gray-400">{sb.sandbox_id.slice(0, 8)}</span>
        <StatusBadge status={sb.status} />
      </div>
      {sb.node_version && <div className="text-gray-500">v{sb.node_version}</div>}
      {sb.run_id && <div className="text-gray-500 truncate">run: {sb.run_id.slice(0, 8)}</div>}
      {sb.anvil_port && (
        <div className="text-gray-600">
          anvil:{sb.anvil_port} · node:{sb.node_port} · gql:{sb.graphql_port}
        </div>
      )}
      {sb.error_message && (
        <div className="text-rvp-error truncate" title={sb.error_message}>{sb.error_message}</div>
      )}
    </div>
  )
}

export function SandboxPool() {
  const [sandboxes, setSandboxes] = useState<Sandbox[]>([])

  useEffect(() => {
    const load = () => sandboxesApi.list().then(setSandboxes).catch(console.error)
    load()
    const id = setInterval(load, 4000)
    return () => clearInterval(id)
  }, [])

  const active = sandboxes.filter((s) => ['provisioning', 'ready', 'in_use'].includes(s.status))
  const pct = Math.round((active.length / MAX_SANDBOXES) * 100)

  return (
    <div className="card p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-200">Sandbox Pool</h2>
        <span className="text-xs text-gray-500">{active.length} / {MAX_SANDBOXES}</span>
      </div>

      {/* Capacity bar */}
      <div className="h-2 bg-rvp-bg rounded-full overflow-hidden">
        <div
          className={clsx(
            'h-full rounded-full transition-all duration-500',
            pct >= 90 ? 'bg-rvp-error' : pct >= 60 ? 'bg-rvp-warning' : 'bg-rvp-success',
          )}
          style={{ width: `${pct}%` }}
        />
      </div>

      {active.length === 0 ? (
        <div className="text-xs text-gray-500 py-2 text-center">No active sandboxes</div>
      ) : (
        <div className="space-y-2">
          {active.map((sb) => <SandboxCard key={sb.sandbox_id} sb={sb} />)}
        </div>
      )}
    </div>
  )
}
