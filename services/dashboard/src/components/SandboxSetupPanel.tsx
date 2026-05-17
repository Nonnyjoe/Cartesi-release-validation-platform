import { useState } from 'react'
import clsx from 'clsx'
import type { StepStatus } from '../types'

// ─── Step metadata ─────────────────────────────────────────────────────────────

const STEP_LABEL: Record<string, string> = {
  network_created:       'Network created',
  anvil_started:         'Anvil started',
  anvil_health_check:    'Anvil health check',
  anvil_healthy:         'Anvil healthy',
  deployer_image_building: 'Building cannon deployer image',
  deployer_image_ready:  'Cannon deployer image ready',
  contracts_deploying:   'Deploying rollups contracts',
  contracts_deployed:    'Contracts deployed',
  contracts_fallback:    'Contract deploy failed — using devnet addresses',
  contracts_skipped:     'Skipping contract deployment',
  node_starting:         'Starting node services',
  node_started:          'Node services started',
}

// ─── Types ─────────────────────────────────────────────────────────────────────

export interface StepEntry {
  step:       string
  status:     StepStatus
  ts:         string
  detail?:    Record<string, unknown>
  /** Extra lifecycle events (provisioning, ready, failed, closed) */
  isLifecycle?: boolean
  label?:     string
}

// ─── Status icons ─────────────────────────────────────────────────────────────

function StatusIcon({ status, spin }: { status: StepStatus; spin?: boolean }) {
  if (status === 'ok') {
    return <span className="text-rvp-success text-xs">✓</span>
  }
  if (status === 'failed') {
    return <span className="text-rvp-error text-xs">✗</span>
  }
  if (status === 'warn') {
    return <span className="text-rvp-warning text-xs">⚠</span>
  }
  // info / in-progress
  return (
    <span className={clsx('text-rvp-info text-xs', spin && 'animate-spin inline-block')}>
      ◌
    </span>
  )
}

// ─── Detail renderer ─────────────────────────────────────────────────────────

function DetailChips({ detail }: { detail: Record<string, unknown> }) {
  const entries = Object.entries(detail).filter(([, v]) => v != null && v !== '')
  if (entries.length === 0) return null
  return (
    <div className="mt-1 flex flex-wrap gap-2">
      {entries.map(([k, v]) => (
        <span key={k} className="font-mono text-[10px] bg-rvp-surface rounded px-1.5 py-0.5 text-gray-400">
          <span className="text-gray-600">{k}=</span>
          <span className="text-gray-300 break-all">{String(v).slice(0, 80)}</span>
        </span>
      ))}
    </div>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

interface Props {
  steps: StepEntry[]
  isActive: boolean
  className?: string
}

export function SandboxSetupPanel({ steps, isActive, className }: Props) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  if (steps.length === 0) {
    return (
      <div className={clsx('card px-4 py-3', className)}>
        <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">
          Setup Log
        </div>
        <div className="text-xs text-gray-600 italic">
          {isActive ? 'Waiting for provisioning to start…' : 'No setup events recorded.'}
        </div>
      </div>
    )
  }

  const toggle = (i: number) => {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(i) ? next.delete(i) : next.add(i)
      return next
    })
  }

  return (
    <div className={clsx('card px-4 py-3', className)}>
      <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
        Setup Log
        <span className="ml-2 text-gray-600 font-normal normal-case">{steps.length} events</span>
      </div>

      <div className="space-y-px">
        {steps.map((entry, i) => {
          const label = entry.label ?? STEP_LABEL[entry.step] ?? entry.step
          const hasDetail = entry.detail && Object.keys(entry.detail).length > 0
          const open = expanded.has(i)

          return (
            <div
              key={i}
              className={clsx(
                'rounded px-2 py-1.5 transition-colors',
                hasDetail && 'cursor-pointer hover:bg-rvp-surface',
                entry.status === 'failed' && 'bg-rvp-error/10',
                entry.status === 'warn'   && 'bg-rvp-warning/5',
              )}
              onClick={() => hasDetail && toggle(i)}
            >
              <div className="flex items-start gap-2">
                {/* timestamp */}
                <span className="text-[10px] text-gray-600 shrink-0 mt-px font-mono">
                  {new Date(entry.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                </span>

                {/* icon */}
                <span className="shrink-0 w-4 text-center">
                  <StatusIcon
                    status={entry.status}
                    spin={entry.status === 'info' && isActive}
                  />
                </span>

                {/* label */}
                <span className={clsx(
                  'text-xs flex-1',
                  entry.status === 'ok'     && 'text-gray-300',
                  entry.status === 'info'   && 'text-gray-400',
                  entry.status === 'warn'   && 'text-rvp-warning',
                  entry.status === 'failed' && 'text-rvp-error',
                )}>
                  {label}
                  {entry.step === 'contracts_deploying' && entry.detail?.contracts_version != null && (
                    <span className="ml-1 text-gray-500 font-mono">
                      ({String(entry.detail.contracts_version)})
                    </span>
                  )}
                  {entry.step === 'anvil_started' && entry.detail?.port != null && (
                    <span className="ml-1 text-gray-500 font-mono">
                      :{String(entry.detail.port)}
                    </span>
                  )}
                  {entry.step === 'node_started' && entry.detail?.container_count != null && (
                    <span className="ml-1 text-gray-500">
                      ({String(entry.detail.container_count)} containers)
                    </span>
                  )}
                </span>

                {/* expand toggle */}
                {hasDetail && (
                  <span className="text-gray-600 text-[10px] shrink-0">{open ? '▲' : '▼'}</span>
                )}
              </div>

              {/* expanded detail */}
              {open && hasDetail && entry.detail && (
                <div className="ml-10 mt-1">
                  <DetailChips detail={entry.detail} />
                </div>
              )}
            </div>
          )
        })}

        {/* Pulsing "in progress" indicator when run is active */}
        {isActive && (
          <div className="flex items-center gap-2 px-2 py-1.5">
            <span className="text-[10px] text-gray-700 shrink-0 font-mono w-[52px]" />
            <span className="shrink-0 w-4 text-center">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-rvp-info animate-pulse" />
            </span>
            <span className="text-xs text-gray-600 italic">In progress…</span>
          </div>
        )}
      </div>
    </div>
  )
}
