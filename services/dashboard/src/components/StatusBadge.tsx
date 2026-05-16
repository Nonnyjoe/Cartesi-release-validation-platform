import clsx from 'clsx'
import type { RunStatus, TestStatus, SandboxStatus, AISessionStatus, AIMode } from '../types'

type Status = RunStatus | TestStatus | SandboxStatus | AISessionStatus | AIMode

const COLOR: Record<string, string> = {
  queued:       'bg-gray-700 text-gray-300',
  pending:      'bg-gray-700 text-gray-300',
  provisioning: 'bg-blue-900/60 text-blue-300',
  running:      'bg-rvp-info/20 text-rvp-info',
  completed:    'bg-rvp-success/20 text-rvp-success',
  passed:       'bg-rvp-success/20 text-rvp-success',
  ready:        'bg-rvp-success/20 text-rvp-success',
  active:       'bg-rvp-info/20 text-rvp-info',
  in_use:       'bg-rvp-warning/20 text-rvp-warning',
  warning:      'bg-rvp-warning/20 text-rvp-warning',
  failed:       'bg-rvp-error/20 text-rvp-error',
  error:        'bg-rvp-error/20 text-rvp-error',
  cancelled:    'bg-gray-700 text-gray-400',
  skipped:      'bg-gray-700 text-gray-400',
  teardown:     'bg-orange-900/40 text-orange-300',
  collaborative:'bg-purple-900/40 text-purple-300',
  autonomous:   'bg-indigo-900/40 text-indigo-300',
  interactive:  'bg-teal-900/40 text-teal-300',
  chaos:        'bg-red-900/40 text-red-300',
}

const DOT_PULSE = new Set(['running', 'provisioning', 'active', 'in_use'])

interface Props { status: Status; className?: string }

export function StatusBadge({ status, className }: Props) {
  return (
    <span className={clsx('badge gap-1.5', COLOR[status] ?? 'bg-gray-700 text-gray-300', className)}>
      {DOT_PULSE.has(status) && (
        <span className="relative flex h-1.5 w-1.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 bg-current" />
          <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-current" />
        </span>
      )}
      {status}
    </span>
  )
}
