import type {
  Run, RunReport, RunEvent, RunLogLine, TestDefinition, Sandbox,
  AISession, SuggestedAction, PaginatedResponse, QueueDepths,
  ReleaseEntry, CliRelease, SdkRelease, ContractsRelease,
  Application,
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
  /** Returns the raw array from GET /runs (limit/offset based, no total). */
  list: (limit = 20, offset = 0, status?: string) => {
    const q = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    if (status) q.set('status', status)
    return request<Run[]>(`/runs?${q}`)
  },
  get: (runId: string) => request<Run>(`/runs/${runId}`),
  create: (payload: {
    release_tag:        string
    image_tag:          string
    priority?:          number
    triggered_by?:      string
    triggered_by_user?: string
    app_id?:            string
  }) =>
    request<Run>('/runs', {
      method: 'POST',
      body: JSON.stringify({
        triggered_by: 'user',
        priority: 5,
        ...payload,
      }),
    }),
  cancel: (runId: string) =>
    request<{ status: string; run_id: string }>(`/runs/${runId}/cancel`, { method: 'POST' }),
  /** Fetch full report with test results for a run. */
  report: (runId: string) => request<RunReport>(`/reports/${runId}`),
  /** Fetch stored run events (provisioning steps + lifecycle) in chronological order. */
  events: (runId: string) => request<RunEvent[]>(`/runs/${runId}/events`),
  /** Fetch persisted log lines for a run (cursor-paginated). */
  logs: (runId: string, opts?: { source?: string; level?: string; afterId?: number; limit?: number }) => {
    const q = new URLSearchParams()
    if (opts?.source)  q.set('source',   opts.source)
    if (opts?.level)   q.set('level',    opts.level)
    if (opts?.afterId !== undefined) q.set('after_id', String(opts.afterId))
    if (opts?.limit)   q.set('limit',    String(opts.limit))
    const qs = q.toString()
    return request<{ lines: RunLogLine[]; next_cursor: number | null }>(
      `/runs/${runId}/logs${qs ? `?${qs}` : ''}`
    )
  },
  /** Plain-text log download URL (used as href, not fetched by JS). */
  logsDownloadUrl: (runId: string, source?: string): string => {
    const q = source ? `?source=${encodeURIComponent(source)}` : ''
    return `/api/runs/${runId}/logs/download${q}`
  },
}

// ─── Test definitions ─────────────────────────────────────────────────────────
export const testsApi = {
  list: () => request<TestDefinition[]>('/tests'),
  get: (id: string) => request<TestDefinition>(`/tests/${id}`),
  /** content must be YAML-frontmatter + markdown body, e.g. "---\nid: ...\n---\nDescription" */
  create: (content: string) =>
    request<TestDefinition>('/tests', { method: 'POST', body: JSON.stringify({ content }) }),
  toggle: (id: string, is_active: boolean) =>
    request<TestDefinition>(`/tests/${id}`, { method: 'PATCH', body: JSON.stringify({ is_active }) }),
}

// ─── Sandboxes ────────────────────────────────────────────────────────────────
export const sandboxesApi = {
  list: () => request<Sandbox[]>('/sandboxes'),
  get: (id: string) => request<Sandbox>(`/sandboxes/${id}`),
}

// ─── AI Sessions ─────────────────────────────────────────────────────────────
export const sessionsApi = {
  list: (page = 1, pageSize = 20) =>
    request<PaginatedResponse<AISession>>(`/sessions?page=${page}&page_size=${pageSize}`),
  get: (id: string) => request<AISession>(`/sessions/${id}`),
  create: (payload: {
    mode:       string
    run_id?:    string
    goal?:      string
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

// ─── Release catalog ──────────────────────────────────────────────────────────
export const releasesApi = {
  list: () => request<ReleaseEntry[]>('/releases'),
  sync: () => request<{ synced: number }>('/releases/sync', { method: 'POST' }),
  add: (payload: { tag: string; image_tag?: string; channel?: string; label?: string }) =>
    request<ReleaseEntry>('/releases', { method: 'POST', body: JSON.stringify(payload) }),
  remove: (tag: string) => request<void>(`/releases/${encodeURIComponent(tag)}`, { method: 'DELETE' }),
  updateToolchain: (tag: string, payload: {
    sdk_version?: string
    cli_version?: string
    devnet_version?: string
    contracts_version?: string
  }) =>
    request<ReleaseEntry>(`/releases/${encodeURIComponent(tag)}/toolchain`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
}

// ─── CLI release catalog ──────────────────────────────────────────────────────
export const cliReleasesApi = {
  list: () => request<CliRelease[]>('/releases/cli'),
  sync: () => request<{ synced: number }>('/releases/cli/sync', { method: 'POST' }),
}

// ─── SDK release catalog ──────────────────────────────────────────────────────
export const sdkReleasesApi = {
  list: () => request<SdkRelease[]>('/releases/sdk'),
  sync: () => request<{ synced: number }>('/releases/sdk/sync', { method: 'POST' }),
}

// ─── Contracts release catalog ────────────────────────────────────────────────
export const contractsReleasesApi = {
  list: () => request<ContractsRelease[]>('/releases/contracts'),
  sync: () => request<{ synced: number }>('/releases/contracts/sync', { method: 'POST' }),
}

// ─── Queues ───────────────────────────────────────────────────────────────────
export const queuesApi = {
  depths: () => request<QueueDepths>('/queues'),
}

// ─── Applications ─────────────────────────────────────────────────────────────
export const appsApi = {
  list: (includeInactive = false) =>
    request<Application[]>(`/apps${includeInactive ? '?include_inactive=true' : ''}`),
  get: (id: string) => request<Application>(`/apps/${id}`),
  create: (payload: { name: string; github_url: string; description?: string; added_by?: string }) =>
    request<Application>('/apps', { method: 'POST', body: JSON.stringify(payload) }),
  update: (id: string, payload: { name?: string; github_url?: string; description?: string; is_active?: boolean }) =>
    request<Application>(`/apps/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  remove: (id: string) =>
    fetch(`/api/apps/${id}`, { method: 'DELETE' }).then(r => {
      if (!r.ok && r.status !== 204) throw new Error(`${r.status}`)
    }),
}
