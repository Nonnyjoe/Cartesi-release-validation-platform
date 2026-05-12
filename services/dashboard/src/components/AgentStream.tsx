import { useEffect, useRef } from 'react'
import clsx from 'clsx'
import type { WSEvent } from '../types'

export interface AgentEvent {
  type: WSEvent['event_type'] | 'user_message'
  ts: string
  text?: string
  tool?: string
  input?: unknown
  result?: unknown
  severity?: string
  title?: string
}

interface Props {
  events: AgentEvent[]
  className?: string
}

function EventRow({ ev }: { ev: AgentEvent }) {
  if (ev.type === 'user_message') {
    return (
      <div className="flex gap-2 items-start">
        <span className="shrink-0 text-xs text-gray-500 mt-0.5">{new Date(ev.ts).toLocaleTimeString()}</span>
        <div className="bg-rvp-primary/20 border border-rvp-primary/30 rounded-lg px-3 py-2 text-sm text-gray-200 max-w-prose">
          {ev.text}
        </div>
      </div>
    )
  }

  if (ev.type === 'ai.token') {
    return (
      <div className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap">{ev.text}</div>
    )
  }

  if (ev.type === 'ai.tool_call') {
    return (
      <div className="flex gap-2 items-start text-xs font-mono">
        <span className="shrink-0 text-gray-600 mt-0.5">{new Date(ev.ts).toLocaleTimeString()}</span>
        <div className="bg-rvp-surface border border-rvp-border rounded px-3 py-1.5">
          <span className="text-rvp-primary">⚙ {ev.tool}</span>
          {ev.input != null && (
            <pre className="text-gray-500 mt-1 overflow-auto max-h-24">
              {JSON.stringify(ev.input, null, 2)}
            </pre>
          )}
        </div>
      </div>
    )
  }

  if (ev.type === 'ai.tool_result') {
    return (
      <div className="text-xs font-mono ml-6 text-gray-500 border-l-2 border-rvp-border pl-3 py-0.5 max-h-20 overflow-auto">
        {typeof ev.result === 'string' ? ev.result : JSON.stringify(ev.result)}
      </div>
    )
  }

  if (ev.type === 'ai.finding') {
    const colors: Record<string, string> = {
      critical: 'border-rvp-error bg-rvp-error/10 text-rvp-error',
      high:     'border-rvp-error/60 bg-rvp-error/5 text-red-300',
      medium:   'border-rvp-warning bg-rvp-warning/10 text-rvp-warning',
      low:      'border-rvp-info bg-rvp-info/10 text-rvp-info',
      info:     'border-gray-600 bg-gray-800 text-gray-300',
    }
    return (
      <div className={clsx('border-l-4 rounded-r px-3 py-2 text-sm', colors[ev.severity ?? 'info'])}>
        <div className="font-semibold">{ev.severity?.toUpperCase()} — {ev.title}</div>
        {ev.text && <div className="mt-0.5 text-xs opacity-80">{ev.text}</div>}
      </div>
    )
  }

  if (ev.type === 'ai.completed') {
    return (
      <div className="text-xs text-rvp-success py-1">✓ Session completed</div>
    )
  }

  return null
}

export function AgentStream({ events, className }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events.length])

  return (
    <div className={clsx('overflow-y-auto space-y-3 p-4', className)}>
      {events.map((ev, i) => <EventRow key={i} ev={ev} />)}
      <div ref={bottomRef} />
    </div>
  )
}
