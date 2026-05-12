import type {
  Run, TestResult, TestDefinition, Sandbox,
  AISession, SuggestedAction, PaginatedResponse, QueueDepths,
} from './types'

const BASE = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status} ${body}`)
  }
  return res.json() as Promise<T>
}

// ─── Runs ─────────────────────────────────────────────────────────────────────
export const runsApi = {
  list: (page = 1, pageSize = 20, status?: string) => {
    const q = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
    if (status) q.set('status', status)
    return request<PaginatedResponse<Run>>(`/runs?${q}`)
  },
  get: (runId: string) => request<Run>(`/runs/${runId}`),
  create: (payload: {
    node_version: string
    pr_number?: number
    repo_url?: string
    triggered_by?: string
    priority?: number
  }) => request<Run>('/runs', { method: 'POST', body: JSON.stringify(payload) }),
  cancel: (runId: string) => request<Run>(`/runs/${runId}/cancel`, { method: 'POST' }),
  results: (runId: string) => request<TestResult[]>(`/runs/${runId}/results`),
}

// ─── Test definitions ─────────────────────────────────────────────────────────
export const testsApi = {
  list: () => request<TestDefinition[]>('/tests'),
  get: (id: string) => request<TestDefinition>(`/tests/${id}`),
  create: (payload: { name: string; content: string }) =>
    request<TestDefinition>('/tests', { method: 'POST', body: JSON.stringify(payload) }),
  update: (id: string, payload: { enabled?: boolean; content?: string }) =>
    request<TestDefinition>(`/tests/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
}

// ─── Sandboxes ────────────────────────────────────────────────────────────────
export const sandboxesApi = {
  list: (status?: string) => {
    const q = status ? `?status=${status}` : ''
    return request<Sandbox[]>(`/sandboxes${q}`)
  },
  get: (id: string) => request<Sandbox>(`/sandboxes/${id}`),
}

// ─── AI Sessions ─────────────────────────────────────────────────────────────
export const sessionsApi = {
  list: (page = 1, pageSize = 20) =>
    request<PaginatedResponse<AISession>>(`/sessions?page=${page}&page_size=${pageSize}`),
  get: (id: string) => request<AISession>(`/sessions/${id}`),
  create: (payload: {
    mode: string
    run_id?: string
    goal?: string
    sandbox_id?: string
  }) => request<AISession>('/sessions', { method: 'POST', body: JSON.stringify(payload) }),
  sendMessage: (id: string, message: string) =>
    request<{ ok: boolean }>(`/sessions/${id}/message`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),
  cancel: (id: string) =>
    request<{ ok: boolean }>(`/sessions/${id}/cancel`, { method: 'POST' }),
  suggestions: (sessionId?: string) => {
    const q = sessionId ? `?session_id=${sessionId}` : ''
    return request<SuggestedAction[]>(`/sessions/suggestions${q}`)
  },
  reviewSuggestion: (actionId: string, status: 'approved' | 'rejected') =>
    request<SuggestedAction>(`/sessions/suggestions/${actionId}/review`, {
      method: 'POST',
      body: JSON.stringify({ status }),
    }),
}

// ─── Queues ───────────────────────────────────────────────────────────────────
export const queuesApi = {
  depths: () => request<QueueDepths>('/queues'),
}
