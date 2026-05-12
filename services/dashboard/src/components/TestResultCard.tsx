import { useState } from 'react'
import clsx from 'clsx'
import { StatusBadge } from './StatusBadge'
import type { TestResult } from '../types'

interface Props { result: TestResult }

export function TestResultCard({ result }: Props) {
  const [open, setOpen] = useState(false)

  return (
    <div className="card overflow-hidden">
      <button
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-white/5 transition-colors"
        onClick={() => setOpen(!open)}
      >
        <StatusBadge status={result.status} />
        <span className="flex-1 text-sm font-medium text-gray-200">{result.definition_name}</span>
        {result.duration_ms != null && (
          <span className="text-xs text-gray-500">{(result.duration_ms / 1000).toFixed(1)}s</span>
        )}
        <span className="text-gray-500 text-xs">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="border-t border-rvp-border divide-y divide-rvp-border/50">
          {result.error_message && (
            <div className="px-4 py-2 text-xs text-rvp-error bg-rvp-error/5 font-mono">
              {result.error_message}
            </div>
          )}
          {result.assertions.map((a, i) => (
            <div key={i} className={clsx('px-4 py-2 flex gap-3 text-xs', a.passed ? '' : 'bg-rvp-error/5')}>
              <span className={a.passed ? 'text-rvp-success' : 'text-rvp-error'}>
                {a.passed ? '✓' : '✗'}
              </span>
              <div className="flex-1 min-w-0">
                <div className="text-gray-300">{a.description}</div>
                <div className="text-gray-500 mt-0.5">type: {a.assertion_type}</div>
                {!a.passed && a.error && (
                  <div className="text-rvp-error mt-1 font-mono break-all">{a.error}</div>
                )}
                {!a.passed && a.expected != null && (
                  <div className="mt-1 grid grid-cols-2 gap-2">
                    <div>
                      <div className="text-gray-500 mb-0.5">expected</div>
                      <pre className="text-gray-300 text-xs overflow-auto">{JSON.stringify(a.expected, null, 2)}</pre>
                    </div>
                    <div>
                      <div className="text-gray-500 mb-0.5">actual</div>
                      <pre className="text-rvp-error text-xs overflow-auto">{JSON.stringify(a.actual, null, 2)}</pre>
                    </div>
                  </div>
                )}
              </div>
              {a.duration_ms != null && (
                <span className="text-gray-600 shrink-0">{a.duration_ms}ms</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
