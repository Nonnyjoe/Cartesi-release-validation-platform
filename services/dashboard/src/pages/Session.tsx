import { useEffect, useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { sessionsApi } from '../api'
import { AgentStream } from '../components/AgentStream'
import { StatusBadge } from '../components/StatusBadge'
import { useWebSocket } from '../hooks/useWebSocket'
import type { AgentEvent } from '../components/AgentStream'
import type { AISession } from '../types'

export default function Session() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const [session, setSession] = useState<AISession | null>(null)
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const textRef = useRef<HTMLTextAreaElement>(null)

  const loadSession = () => { if (sessionId) sessionsApi.get(sessionId).then(setSession).catch(console.error) }

  useEffect(() => { loadSession() }, [sessionId])

  const { connected } = useWebSocket({
    channel: sessionId,
    onEvent: (ev) => {
      if (ev.event_type === 'ai.token') {
        setEvents(es => {
          // Merge consecutive token events into one
          const last = es[es.length - 1]
          if (last?.type === 'ai.token') {
            return [...es.slice(0, -1), { ...last, text: (last.text ?? '') + (ev.payload.text as string ?? '') }]
          }
          return [...es, { type: 'ai.token', ts: ev.ts, text: ev.payload.text as string }]
        })
      } else if (ev.event_type === 'ai.tool_call') {
        setEvents(es => [...es, {
          type: 'ai.tool_call', ts: ev.ts,
          tool: ev.payload.tool as string,
          input: ev.payload.input,
        }])
      } else if (ev.event_type === 'ai.tool_result') {
        setEvents(es => [...es, {
          type: 'ai.tool_result', ts: ev.ts,
          result: ev.payload.result,
        }])
      } else if (ev.event_type === 'ai.finding') {
        setEvents(es => [...es, {
          type: 'ai.finding', ts: ev.ts,
          severity: ev.payload.severity as string,
          title: ev.payload.title as string,
          text: ev.payload.description as string,
        }])
        loadSession()
      } else if (ev.event_type === 'ai.completed') {
        setEvents(es => [...es, { type: 'ai.completed', ts: ev.ts }])
        loadSession()
      }
    },
  })

  const sendMessage = async () => {
    if (!message.trim() || !sessionId) return
    const text = message.trim()
    setMessage('')
    setEvents(es => [...es, { type: 'user_message', ts: new Date().toISOString(), text }])
    setSending(true)
    try {
      await sessionsApi.sendMessage(sessionId, text)
    } catch (e) {
      console.error(e)
    } finally {
      setSending(false)
      textRef.current?.focus()
    }
  }

  const isInteractive = session?.mode === 'interactive' || session?.mode === 'collaborative'
  const isActive = session?.status === 'active'

  if (!session) return <div className="text-gray-500 text-sm">Loading…</div>

  return (
    <div className="flex flex-col h-full space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <Link to="/sessions" className="text-gray-500 hover:text-gray-300 text-sm">← Sessions</Link>
          <h1 className="text-xl font-semibold text-gray-100 mt-1 font-mono">{session.session_id.slice(0, 16)}</h1>
          <div className="flex items-center gap-2 mt-1">
            <StatusBadge status={session.mode} />
            <StatusBadge status={session.status} />
          </div>
        </div>
        <div className="text-right text-xs text-gray-500 space-y-1">
          <div>{session.tool_calls_used} tool calls</div>
          <div>{(session.input_tokens + session.output_tokens).toLocaleString()} tokens</div>
          {session.goal && (
            <div className="max-w-xs text-right text-gray-400 text-xs">{session.goal}</div>
          )}
        </div>
      </div>

      {/* WS indicator */}
      <div className="flex items-center gap-1.5 text-xs">
        <span className={`h-1.5 w-1.5 rounded-full ${connected ? 'bg-rvp-success' : 'bg-gray-600'}`} />
        <span className="text-gray-500">{connected ? 'Live' : 'Disconnected'}</span>
      </div>

      {/* Stream */}
      <div className="card flex-1 overflow-hidden min-h-[400px]">
        <AgentStream events={events} className="h-full" />
      </div>

      {/* Findings summary */}
      {session.findings.length > 0 && (
        <div className="card p-4">
          <h3 className="text-sm font-semibold text-gray-200 mb-2">Findings ({session.findings.length})</h3>
          <div className="space-y-2">
            {session.findings.map((f, i) => (
              <div key={i} className="flex gap-2 items-start text-xs">
                <span className={`badge shrink-0 ${
                  f.severity === 'critical' ? 'bg-rvp-error/20 text-rvp-error' :
                  f.severity === 'high' ? 'bg-red-900/40 text-red-300' :
                  f.severity === 'medium' ? 'bg-rvp-warning/20 text-rvp-warning' :
                  'bg-rvp-info/20 text-rvp-info'}`}>
                  {f.severity}
                </span>
                <div>
                  <div className="text-gray-200 font-medium">{f.title}</div>
                  <div className="text-gray-500 mt-0.5">{f.description}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Message input (interactive / collaborative only) */}
      {isInteractive && isActive && (
        <div className="card p-3 flex gap-2">
          <textarea
            ref={textRef}
            className="input flex-1 resize-none h-16"
            placeholder="Send a message to the agent…"
            value={message}
            onChange={e => setMessage(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) sendMessage() }}
          />
          <div className="flex flex-col gap-1">
            <button className="btn-primary" onClick={sendMessage} disabled={sending || !message.trim()}>
              Send
            </button>
            <button
              className="btn-ghost text-rvp-error border-rvp-error/30 text-xs"
              onClick={() => sessionsApi.cancel(session.session_id).then(() => loadSession())}
            >
              Stop
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
