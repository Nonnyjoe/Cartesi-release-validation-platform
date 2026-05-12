// ─── Enums ────────────────────────────────────────────────────────────────────
export type RunStatus = 'pending' | 'provisioning' | 'running' | 'completed' | 'failed' | 'cancelled'
export type TestStatus = 'pending' | 'running' | 'passed' | 'failed' | 'error' | 'skipped'
export type SandboxStatus = 'provisioning' | 'ready' | 'in_use' | 'teardown' | 'failed'
export type AISessionStatus = 'active' | 'completed' | 'failed' | 'cancelled'
export type AIMode = 'autonomous' | 'collaborative' | 'interactive'

// ─── Core domain types ────────────────────────────────────────────────────────
export interface Run {
  run_id: string
  pr_number?: number
  repo_url?: string
  node_version: string
  status: RunStatus
  triggered_by: string
  pass_rate?: number
  total_tests: number
  passed_tests: number
  failed_tests: number
  created_at: string
  started_at?: string
  completed_at?: string
  sandbox_id?: string
}

export interface TestResult {
  result_id: string
  run_id: string
  definition_id: string
  definition_name: string
  status: TestStatus
  duration_ms?: number
  error_message?: string
  assertions: AssertionResult[]
  created_at: string
  completed_at?: string
}

export interface AssertionResult {
  assertion_id: string
  assertion_type: string
  description: string
  passed: boolean
  actual?: unknown
  expected?: unknown
  error?: string
  duration_ms?: number
}

export interface TestDefinition {
  definition_id: string
  name: string
  description: string
  category: string
  priority: number
  enabled: boolean
  tags: string[]
  created_at: string
  updated_at: string
}

export interface Sandbox {
  sandbox_id: string
  run_id?: string
  status: SandboxStatus
  node_version?: string
  docker_network?: string
  anvil_port?: number
  node_port?: number
  graphql_port?: number
  created_at: string
  ready_at?: string
  released_at?: string
  error_message?: string
}

export interface AISession {
  session_id: string
  run_id?: string
  mode: AIMode
  status: AISessionStatus
  goal?: string
  model: string
  tool_calls_used: number
  input_tokens: number
  output_tokens: number
  findings: Finding[]
  created_at: string
  completed_at?: string
}

export interface Finding {
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info'
  title: string
  description: string
  evidence?: string
  recommendation?: string
}

export interface SuggestedAction {
  action_id: string
  session_id: string
  action_type: string
  description: string
  rationale: string
  status: 'pending' | 'approved' | 'rejected'
  test_definition_yaml?: string
  created_at: string
}

// ─── WebSocket event types ────────────────────────────────────────────────────
export type WSEventType =
  | 'sandbox.provisioning' | 'sandbox.ready' | 'sandbox.failed' | 'sandbox.released'
  | 'test.started' | 'test.completed' | 'test.failed'
  | 'run.started' | 'run.completed' | 'run.failed' | 'run.cancelled'
  | 'ai.token' | 'ai.tool_call' | 'ai.tool_result' | 'ai.finding' | 'ai.completed'

export interface WSEvent {
  event_type: WSEventType
  run_id?: string
  session_id?: string
  ts: string
  payload: Record<string, unknown>
}

// ─── API response wrappers ────────────────────────────────────────────────────
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface QueueInfo {
  name: string
  messages: number
  consumers: number
  message_stats?: {
    publish_details?: { rate: number }
    deliver_details?: { rate: number }
  }
}

export interface QueueDepths {
  queues: QueueInfo[]
  fetched_at: string
}
