import { useEffect, useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { sessionsApi } from '../api'
import { AgentStream } from '../components/AgentStream'
import { StatusBadge } from '../components/StatusBadge'
import { useWebSocket } from '../hooks/useWebSocket'
import type { AgentEvent } from '../components/AgentStream'
import type { AISession, ToolInvocation, TestVerdict, TestPlan, TrailStep } from '../types'

const VERDICT_COLORS: Record<string, string> = {
  passed:       'bg-rvp-success/20 text-rvp-success',
  failed:       'bg-rvp-error/20 text-rvp-error',
  blocked:      'bg-rvp-warning/20 text-rvp-warning',
  skipped:      'bg-gray-700/40 text-gray-400',
  inconclusive: 'bg-rvp-info/20 text-rvp-info',
}

export default function Session() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const [session, setSession] = useState<AISession | null>(null)
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [tools, setTools] = useState<ToolInvocation[]>([])
  const [verdicts, setVerdicts] = useState<TestVerdict[]>([])
  const [plans, setPlans] = useState<TestPlan[]>([])
  const [showToolPanel, setShowToolPanel] = useState(true)
  const [expandedTool, setExpandedTool] = useState<string | null>(null)
  const [expandedVerdict, setExpandedVerdict] = useState<string | null>(null)
  const textRef = useRef<HTMLTextAreaElement>(null)

  const loadSession = () => { if (sessionId) sessionsApi.get(sessionId).then(setSession).catch(console.error) }
  const loadTools = () => {
    if (!sessionId) return
    sessionsApi.tools(sessionId).then(setTools).catch(console.error)
  }
  const loadVerdicts = () => {
    if (!sessionId) return
    sessionsApi.verdicts(sessionId).then(setVerdicts).catch(console.error)
    sessionsApi.plans(sessionId).then(setPlans).catch(() => setPlans([]))
  }

  useEffect(() => { loadSession(); loadTools(); loadVerdicts() }, [sessionId])

  // Refresh the tool audit list + header counters whenever a tool event streams in
  useEffect(() => {
    const recent = events[events.length - 1]
    if (recent?.type === 'ai.tool_call' || recent?.type === 'ai.tool_result') {
      loadTools()
      loadSession()
    }
  }, [events.length])

  // Polling fallback so the audit panel stays live even if a WS event is dropped
  // (e.g. brief disconnect, redis pub/sub miss). Stops once the session terminates.
  // 'starting' = environment bootstrap in progress — keep polling so the header
  // flips to active and the sandbox id appears without a reload.
  useEffect(() => {
    if (!sessionId || !session) return
    if (session.status !== 'active' && session.status !== 'starting') return
    const iv = setInterval(() => { loadTools(); loadSession(); loadVerdicts() }, 4000)
    return () => clearInterval(iv)
  }, [sessionId, session?.status])

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
      } else if (ev.event_type === 'ai.verdict') {
        loadVerdicts()
      } else if (typeof ev.event_type === 'string' && ev.event_type.startsWith('bootstrap')) {
        // bootstrap_started / bootstrap_log / bootstrap_progress / bootstrap_ready
        setEvents(es => [...es, {
          type: ev.event_type, ts: ev.ts,
          text: (ev.payload.message
                 ?? (ev.payload.sandbox_status
                     ? `sandbox: ${ev.payload.sandbox_status}`
                     : '')) as string,
          source: ev.payload.source as string | undefined,
        }])
        if (ev.event_type === 'bootstrap_ready' || ev.event_type === 'bootstrap_progress') {
          loadSession()
        }
      } else if (ev.event_type === 'ai.completed' || ev.event_type === 'session_completed') {
        setEvents(es => [...es, { type: 'ai.completed', ts: ev.ts }])
        loadSession(); loadTools(); loadVerdicts()
      } else if (ev.event_type === 'session_failed' || ev.event_type === 'ai.limit_reached') {
        setEvents(es => [...es, {
          type: ev.event_type, ts: ev.ts,
          text: (ev.payload.error ?? ev.payload.reason ?? '') as string,
        }])
        loadSession(); loadTools()
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
            {session.execution_mode === 'ai_manual' && (
              <span className="badge bg-rvp-info/20 text-rvp-info">manual execution</span>
            )}
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

      {/* Tool audit panel */}
      <div className="card">
        <button
          className="w-full flex items-center justify-between px-4 py-3 text-sm font-semibold text-gray-200 hover:bg-white/5"
          onClick={() => setShowToolPanel(o => !o)}
        >
          <span>Tool invocations ({tools.length})</span>
          <span className="text-gray-500">{showToolPanel ? '▼' : '▶'}</span>
        </button>
        {showToolPanel && (
          <div className="border-t border-rvp-border max-h-[400px] overflow-y-auto">
            {tools.length === 0 ? (
              <div className="px-4 py-6 text-center text-xs text-gray-500">
                No tool calls recorded yet.
              </div>
            ) : (
              <ul className="divide-y divide-rvp-border/50 text-xs">
                {tools.map(t => {
                  const isOpen = expandedTool === t.id
                  const statusColor =
                    t.status === 'ok'     ? 'bg-rvp-success/20 text-rvp-success' :
                    t.status === 'denied' ? 'bg-rvp-warning/20 text-rvp-warning' :
                                            'bg-rvp-error/20 text-rvp-error'
                  return (
                    <li key={t.id}>
                      <button
                        className="w-full text-left px-4 py-2 hover:bg-white/3 flex items-start gap-3"
                        onClick={() => setExpandedTool(isOpen ? null : t.id)}
                      >
                        <span className="text-gray-500 w-20 shrink-0 font-mono">
                          {new Date(t.created_at).toLocaleTimeString()}
                        </span>
                        <span className={`badge shrink-0 ${statusColor}`}>{t.status}</span>
                        <span className="font-mono text-gray-200 flex-1 truncate">
                          {t.tool_name}
                          {t.definition_slug && (
                            <span className="ml-2 text-[10px] text-rvp-info/80">{t.definition_slug}</span>
                          )}
                        </span>
                        <span className="text-gray-500 shrink-0">{t.duration_ms}ms</span>
                      </button>
                      {isOpen && (
                        <div className="px-6 pb-3 space-y-2">
                          <div>
                            <div className="text-gray-500 text-[10px] uppercase mb-1">input</div>
                            <pre className="font-mono text-[11px] bg-rvp-bg/60 p-2 rounded overflow-x-auto">
                              {JSON.stringify(t.input, null, 2)}
                            </pre>
                          </div>
                          <div>
                            <div className="text-gray-500 text-[10px] uppercase mb-1">output</div>
                            <pre className="font-mono text-[11px] bg-rvp-bg/60 p-2 rounded overflow-x-auto max-h-64">
                              {JSON.stringify(t.output, null, 2)}
                            </pre>
                          </div>
                        </div>
                      )}
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        )}
      </div>

      {/* Manual execution: per-test verdicts */}
      {session.execution_mode === 'ai_manual' && (
        <div className="card p-4">
          <h3 className="text-sm font-semibold text-gray-200 mb-2">
            Test verdicts ({verdicts.length}{session.selected_tests.length > 0 ? ` / ${session.selected_tests.length}` : ''})
          </h3>
          {verdicts.length === 0 ? (
            <div className="text-xs text-gray-500">No verdicts recorded yet.</div>
          ) : (
            <ul className="divide-y divide-rvp-border/50 text-xs">
              {verdicts.map(v => {
                const isOpen = expandedVerdict === v.verdict_id
                return (
                  <li key={v.verdict_id}>
                    <button
                      className="w-full text-left py-2 hover:bg-white/3 flex items-start gap-3"
                      onClick={() => setExpandedVerdict(isOpen ? null : v.verdict_id)}
                    >
                      <span className={`badge shrink-0 ${VERDICT_COLORS[v.verdict] ?? 'bg-gray-700/40 text-gray-400'}`}>
                        {v.verdict}
                      </span>
                      <span className="font-mono text-gray-200 flex-1 truncate">
                        {v.definition_slug}
                        {v.auto_downgraded_from && (
                          <span className="ml-2 badge bg-rvp-warning/20 text-rvp-warning"
                            title={v.validation_notes ?? ''}>↓ from {v.auto_downgraded_from}</span>
                        )}
                        {(v.verdict === 'passed' || v.verdict === 'failed') && v.evidence_validated === false && (
                          <span className="ml-2 badge bg-rvp-warning/20 text-rvp-warning"
                            title="No cited value was found in the captured trail">evidence unverified</span>
                        )}
                        {v.trail_truncated && (
                          <span className="ml-2 badge bg-rvp-warning/20 text-rvp-warning">trail truncated</span>
                        )}
                      </span>
                      {typeof v.confidence === 'number' && (
                        <span className={`shrink-0 ${v.confidence < 0.6 ? 'text-rvp-warning' : 'text-gray-400'}`}
                          title="Agent confidence (sub-0.6 → human review)">
                          {Math.round(v.confidence * 100)}%
                        </span>
                      )}
                      <span className="text-gray-500 shrink-0">
                        {new Date(v.created_at).toLocaleTimeString()}
                      </span>
                    </button>
                    {isOpen && (() => {
                      const { execution_trail: trail, ...restEvidence } =
                        (v.evidence ?? {}) as { execution_trail?: TrailStep[] } & Record<string, unknown>
                      const hasRest = Object.keys(restEvidence).length > 0
                      const plan = plans.find(p => p.definition_slug === v.definition_slug)
                      const obs = Array.isArray(v.observations) ? v.observations as string[] : null
                      return (
                        <div className="pb-3 pl-2 space-y-2">
                          <div className="text-gray-400">{v.reasoning}</div>
                          {v.validation_notes && (
                            <div className="text-[11px] text-rvp-warning bg-rvp-warning/10 border border-rvp-warning/30 rounded px-2 py-1">
                              ⚠ validation: {v.validation_notes}
                            </div>
                          )}
                          {obs && obs.length > 0 && (
                            <div>
                              <div className="text-gray-500 text-[10px] uppercase mb-1">observations</div>
                              <ul className="list-disc list-inside text-gray-300 space-y-0.5">
                                {obs.map((o, i) => <li key={i}>{o}</li>)}
                              </ul>
                            </div>
                          )}
                          {plan && (
                            <details className="text-[11px]">
                              <summary className="text-gray-500 cursor-pointer">
                                plan &amp; understanding
                              </summary>
                              <div className="mt-1 pl-2 space-y-1 text-gray-400">
                                {plan.objective && <div><span className="text-gray-500">objective:</span> {plan.objective}</div>}
                                {plan.success_criteria && <div><span className="text-gray-500">pass when:</span> {plan.success_criteria}</div>}
                                {plan.failure_criteria && <div><span className="text-gray-500">fail when:</span> {plan.failure_criteria}</div>}
                                {plan.planned_steps != null && (
                                  <pre className="font-mono text-[10px] bg-rvp-bg/60 p-1.5 rounded overflow-x-auto">
                                    {JSON.stringify(plan.planned_steps, null, 2)}
                                  </pre>
                                )}
                              </div>
                            </details>
                          )}
                          <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-gray-500">
                            {v.model_id && <span>model: <span className="text-gray-400 font-mono">{v.model_id}</span></span>}
                            {v.model_params?.temperature != null && <span>temp: {String(v.model_params.temperature)}</span>}
                            {v.release_tag && <span>release: <span className="text-gray-400">{v.release_tag}</span></span>}
                            {v.image_tag && <span>image: <span className="text-gray-400 font-mono">{v.image_tag}</span></span>}
                            {v.contracts_version && <span>contracts: {v.contracts_version}</span>}
                            {v.trail_step_count != null && <span>steps: {v.trail_step_count} ({v.trail_mutating_count ?? 0} mutating)</span>}
                          </div>
                          {v.inputs_used && (
                            <div>
                              <div className="text-gray-500 text-[10px] uppercase mb-1">inputs used</div>
                              <pre className="font-mono text-[11px] bg-rvp-bg/60 p-2 rounded overflow-x-auto">
                                {JSON.stringify(v.inputs_used, null, 2)}
                              </pre>
                            </div>
                          )}
                          {trail && trail.length > 0 && (
                            <div>
                              <div className="text-gray-500 text-[10px] uppercase mb-1">
                                execution trail ({trail.length} steps — auto-captured)
                              </div>
                              <ol className="space-y-1 max-h-72 overflow-y-auto">
                                {trail.map((s, i) => (
                                  <li key={s.invocation_id ?? i}
                                    className={`bg-rvp-bg/60 rounded px-2 py-1.5 border-l-2 ${
                                      s.status === 'ok' ? 'border-rvp-success/40' : 'border-rvp-error/60'}`}>
                                    <div className="flex items-center gap-2">
                                      <span className="text-gray-600 w-4 shrink-0">{i + 1}</span>
                                      <span className="font-mono text-gray-200">{s.tool}</span>
                                      <span className="badge bg-rvp-info/15 text-rvp-info">{s.target}</span>
                                      <span className={`ml-auto shrink-0 ${
                                        s.status === 'ok' ? 'text-rvp-success' : 'text-rvp-error'}`}>
                                        {s.status}{s.duration_ms != null ? ` · ${s.duration_ms}ms` : ''}
                                      </span>
                                    </div>
                                    {s.input != null && (
                                      <div className="font-mono text-[10px] text-gray-400 mt-0.5 break-all">
                                        → {typeof s.input === 'string' ? s.input : JSON.stringify(s.input)}
                                      </div>
                                    )}
                                    {s.output != null && (
                                      <div className="font-mono text-[10px] text-gray-500 mt-0.5 break-all">
                                        ← {typeof s.output === 'string' ? s.output : JSON.stringify(s.output)}
                                      </div>
                                    )}
                                  </li>
                                ))}
                              </ol>
                            </div>
                          )}
                          {hasRest && (
                            <div>
                              <div className="text-gray-500 text-[10px] uppercase mb-1">evidence</div>
                              <pre className="font-mono text-[11px] bg-rvp-bg/60 p-2 rounded overflow-x-auto max-h-64">
                                {JSON.stringify(restEvidence, null, 2)}
                              </pre>
                            </div>
                          )}
                        </div>
                      )
                    })()}
                  </li>
                )
              })}
            </ul>
          )}
          {session.selected_tests.length > 0 && verdicts.length < session.selected_tests.length && (
            <div className="text-[10px] text-gray-500 mt-2">
              Pending: {session.selected_tests.filter(s => !verdicts.some(v => v.definition_slug === s)).join(', ')}
            </div>
          )}
        </div>
      )}

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
