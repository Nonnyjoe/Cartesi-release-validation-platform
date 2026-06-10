// ─── Enums ────────────────────────────────────────────────────────────────────
export type RunStatus = 'queued' | 'provisioning' | 'running' | 'completed' | 'warning' | 'failed' | 'cancelled'
export type TestStatus = 'pending' | 'running' | 'passed' | 'failed' | 'error' | 'skipped'
export type SandboxStatus = 'provisioning' | 'ready' | 'failed' | 'closed'
export type AISessionStatus = 'active' | 'completed' | 'failed' | 'cancelled'
export type AIMode = 'autonomous' | 'collaborative' | 'interactive'

// ─── Core domain types ────────────────────────────────────────────────────────

/** Matches orchestrator RunResponse */
export interface Run {
  id:                string
  release_tag:       string
  image_tag:         string
  status:            RunStatus
  priority:          number
  triggered_by:      string
  triggered_by_user?: string
  suite_ids?:        string[]
  queued_at:         string
  started_at?:       string
  completed_at?:     string
  pass_rate?:        number
  app_id?:           string
  app_address?:      string
}

/** Registered Cartesi application (tests.applications) */
export interface Application {
  id:           string
  name:         string
  github_url:   string
  description?: string
  is_active:    boolean
  added_by?:    string
  added_at:     string
  updated_at:   string
}

/** One assertion result as stored in tests.results.assertion_results */
export interface AssertionResult {
  assertion_type: string
  passed:         boolean
  expected?:      unknown
  actual?:        unknown
  detail?:        string
  duration_ms?:   number
}

/** One row from tests.results joined with tests.definitions */
export interface TestResult {
  id:               string
  definition_id:    string
  test_slug:        string
  test_name:        string
  status:           TestStatus
  duration_ms?:     number
  assertion_results: AssertionResult[]
  error_message?:   string
  started_at?:      string
  completed_at?:    string
}

/** /reports/{run_id} response */
export interface RunReport {
  run_id:     string
  release_tag: string
  status:     string
  pass_rate?: number
  total:      number
  passed:     number
  failed:     number
  error:      number
  results:    TestResult[]
}

/** Matches tests.definitions row */
export interface TestDefinition {
  id:              string
  slug:            string
  name:            string
  version:         number
  priority:        string
  component?:      string
  is_active:       boolean
  ai_allowed:      boolean
  tags:            string[]
  timeout_seconds: number
  definition_raw:  string
  category?:       string
  phase?:          string
  created_at:      string
  updated_at:      string
}

/** One category within a phase, with test counts */
export interface CategoryEntry {
  category:     string
  count:        number
  active_count: number
}

/** A phase group returned by GET /tests/categories */
export interface PhaseGroup {
  phase:        string
  phase_number: number
  categories:   CategoryEntry[]
}

/** Matches sandbox.sandboxes row */
export interface Sandbox {
  id:             string
  run_id?:        string
  status:         SandboxStatus
  anvil_port?:    number
  node_port?:     number
  graphql_port?:  number
  docker_network?: string
  container_ids?: string[]
  failure_reason?: string
  provisioned_at?: string
  ready_at?:       string
  closed_at?:      string
}

/** Matches ai.sessions row */
export interface AISession {
  session_id:      string
  run_id?:         string
  mode:            AIMode
  status:          AISessionStatus
  goal?:           string
  model:           string
  tool_calls_used: number
  input_tokens:    number
  output_tokens:   number
  findings:        Finding[]
  created_at:      string
  completed_at?:   string
}

export interface Finding {
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info'
  title: string
  description: string
  evidence?: string
  recommendation?: string
}

/** Matches ai.tool_invocations row */
export interface ToolInvocation {
  id:           string
  tool_name:    string
  input:        Record<string, unknown>
  output:       unknown
  status:       'ok' | 'error' | 'denied'
  duration_ms:  number
  created_at:   string
}

export interface SuggestedAction {
  action_id:          string
  session_id:         string
  action_type:        string
  description:        string
  rationale:          string
  status:             'pending' | 'approved' | 'rejected'
  test_definition_yaml?: string
  created_at:         string
}

/** Entry in github.release_catalog */
export interface ReleaseEntry {
  tag:               string
  image_tag:         string
  sdk_version?:      string   // v2.x: @cartesi/sdk version == Docker image tag suffix
  cli_version?:      string   // v2.x: @cartesi/cli version that ships with this release
  devnet_version?:   string   // @cartesi/devnet version
  contracts_version?: string  // rollups-contracts version
  node_major_version?: number // 1 or 2
  channel:           string   // stable | alpha | beta
  label:             string
  is_active:         boolean
  added_at:          string
  published_at?:     string
  downloads?:        number
  body?:             string
  html_url?:         string
  // run stats (joined from orchestrator.runs)
  total_runs:        number
  avg_pass_rate?:    number
}

/** Entry in github.cli_catalog — @cartesi/cli releases (v2.x) */
export interface CliRelease {
  tag:              string
  channel:          string
  label?:           string
  is_active:        boolean
  added_at:         string
  published_at?:    string
  downloads?:       number
  body?:            string
  html_url?:        string
  node_release_tag?: string  // rollups-node release this CLI targets
  sdk_tag?:         string   // SDK release this CLI pairs with
  devnet_tag?:      string   // @cartesi/devnet version this CLI ships
  contracts_tag?:   string   // contracts version (via devnet)
}

/** Entry in github.contracts_catalog — rollups-contracts releases */
export interface ContractsRelease {
  tag:              string
  channel:          string
  label?:           string
  is_active:        boolean
  added_at:         string
  published_at?:    string
  downloads?:       number
  body?:            string
  html_url?:        string
  devnet_tag?:      string   // @cartesi/devnet version that bundles these contracts
  cli_tag?:         string   // CLI release that uses this devnet
  node_release_tag?: string  // rollups-node release
  sdk_tag?:         string   // SDK release
}

/** Entry in github.sdk_catalog — @cartesi/sdk releases (v0.x) */
export interface SdkRelease {
  tag:              string
  channel:          string
  label?:           string
  is_active:        boolean
  added_at:         string
  published_at?:    string
  downloads?:       number
  body?:            string
  html_url?:        string
  node_release_tag?: string  // rollups-node release this SDK targets
  cli_tag?:         string   // CLI release this SDK pairs with
  contracts_tag?:   string   // contracts version paired with this SDK
}

// ─── Run logs (orchestrator.run_logs) ────────────────────────────────────────

/** One row from orchestrator.run_logs */
export interface RunLogLine {
  id:      number
  source:  string
  level:   'info' | 'warn' | 'error' | 'debug' | string
  message: string
  ts:      string
}

// ─── Run events (orchestrator.run_events) ────────────────────────────────────

/** Provisioning step names emitted by sandbox-manager */
export type SandboxStep =
  | 'network_created'
  | 'anvil_started'
  | 'anvil_health_check'
  | 'anvil_healthy'
  | 'contracts_deploying'
  | 'deployer_image_building'
  | 'deployer_image_ready'
  | 'contracts_deployed'
  | 'contracts_fallback'
  | 'contracts_skipped'
  | 'node_starting'
  | 'node_started'

export type StepStatus = 'ok' | 'info' | 'warn' | 'failed'

export interface RunEvent {
  id:         string
  run_id:     string
  event_type: string   // e.g. 'sandbox.step', 'sandbox.ready', 'run.queued'
  payload:    Record<string, unknown>
  ts:         string
}

// ─── WebSocket event types ────────────────────────────────────────────────────
export type WSEventType =
  | 'sandbox.provisioning' | 'sandbox.ready' | 'sandbox.failed' | 'sandbox.closed'
  | 'sandbox.step'
  | 'test.started' | 'test.completed' | 'test.failed'
  | 'run.queued' | 'run.started' | 'run.completed' | 'run.failed' | 'run.cancelled'
  | 'ai.token' | 'ai.tool_call' | 'ai.tool_result' | 'ai.finding' | 'ai.completed'

export interface WSEvent {
  event_type:  WSEventType | string
  run_id?:     string
  session_id?: string
  ts:          string
  payload:     Record<string, unknown>
  fields?:     Record<string, unknown>
  [key: string]: unknown
}

// ─── API response wrappers ────────────────────────────────────────────────────
export interface PaginatedResponse<T> {
  items:     T[]
  total:     number
  page:      number
  page_size: number
}

export interface QueueInfo {
  name:      string
  messages:  number
  consumers: number
  message_stats?: {
    publish_details?: { rate: number }
    deliver_details?: { rate: number }
  }
}

export interface QueueDepths {
  queues:     QueueInfo[]
  fetched_at: string
}
