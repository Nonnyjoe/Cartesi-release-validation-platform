"""
shared/constants.py
All RabbitMQ exchange names, queue names, routing keys, and priority levels.
Single source of truth — import from here in every service.
"""

# ─── Exchanges ────────────────────────────────────────────────────────────────

class Exchange:
    RELEASES = "rvp.releases"   # fanout
    SANDBOX  = "rvp.sandbox"    # direct
    TESTS    = "rvp.tests"      # direct
    AI       = "rvp.ai"         # direct
    NOTIFY   = "rvp.notify"     # fanout
    DLX      = "rvp.dlx"        # direct (dead-letter)


# ─── Queues ───────────────────────────────────────────────────────────────────

class Queue:
    # Releases (fanout → multiple consumers)
    RELEASES_ORCHESTRATOR = "releases.orchestrator"
    RELEASES_AI_AGENT     = "releases.ai-agent"

    # Sandbox
    SANDBOX_QUEUE         = "sandbox.queue"       # priority queue
    SANDBOX_QUEUE_DLQ     = "sandbox.queue.dlq"
    SANDBOX_EVENTS        = "sandbox.events"

    # Tests
    TESTS_COMMANDS        = "tests.commands"
    TESTS_RESULTS         = "tests.results"
    TESTS_RESULTS_DLQ     = "tests.results.dlq"

    # AI
    AI_REQUESTS           = "ai.requests"
    AI_RESULTS            = "ai.results"

    # Notifications
    NOTIFY_DISCORD        = "notify.discord"
    NOTIFY_DASHBOARD      = "notify.dashboard"


# ─── Routing Keys ─────────────────────────────────────────────────────────────

class RoutingKey:
    SANDBOX_QUEUE    = "sandbox.queue"
    SANDBOX_EVENTS   = "sandbox.events"
    TESTS_COMMANDS   = "tests.commands"
    TESTS_RESULTS    = "tests.results"
    AI_REQUESTS      = "ai.requests"
    AI_RESULTS       = "ai.results"
    # DLQ routing keys
    SANDBOX_DLQ      = "sandbox.queue.dlq"
    TESTS_DLQ        = "tests.results.dlq"


# ─── Priority Levels ──────────────────────────────────────────────────────────

class Priority:
    GITHUB_RELEASE = 9   # automated release trigger (highest)
    USER_TRIGGERED = 5   # user-triggered from dashboard
    SCHEDULED      = 1   # scheduled / recurring (lowest)


# ─── Service Names ────────────────────────────────────────────────────────────

class Service:
    ORCHESTRATOR    = "orchestrator"
    SANDBOX_MANAGER = "sandbox-manager"
    TEST_RUNNER     = "test-runner"
    AI_AGENT        = "ai-agent"
    GITHUB_WATCHER  = "github-watcher"
    NOTIFIER        = "notifier"
    DASHBOARD       = "dashboard"


# ─── Sandbox Lifecycle States ─────────────────────────────────────────────────

class SandboxStatus:
    REQUESTED    = "requested"
    QUEUED       = "queued"
    PROVISIONING = "provisioning"
    READY        = "ready"
    RUNNING      = "running"
    TEARDOWN     = "teardown"
    CLOSED       = "closed"
    FAILED       = "failed"


# ─── Run Status ───────────────────────────────────────────────────────────────

class RunStatus:
    QUEUED       = "queued"
    PROVISIONING = "provisioning"
    RUNNING      = "running"
    COMPLETED    = "completed"
    FAILED       = "failed"
    CANCELLED    = "cancelled"


# ─── Test Status ──────────────────────────────────────────────────────────────

class TestStatus:
    PENDING  = "pending"
    RUNNING  = "running"
    PASSED   = "passed"
    FAILED   = "failed"
    ERROR    = "error"
    SKIPPED  = "skipped"
    TIMEOUT  = "timeout"


# ─── AI Session Modes & Status ───────────────────────────────────────────────

class AIMode:
    AUTONOMOUS    = "autonomous"
    COLLABORATIVE = "collaborative"
    INTERACTIVE   = "interactive"


class AISessionStatus:
    STARTING   = "starting"
    ACTIVE     = "active"
    PAUSED     = "paused"
    COMPLETED  = "completed"
    FAILED     = "failed"
    ABORTED    = "aborted"


# ─── Tool Call Limits ────────────────────────────────────────────────────────

class AgentLimits:
    MAX_TOOL_CALLS_AUTONOMOUS  = 50
    MAX_TOOL_CALLS_INTERACTIVE = 200
    MAX_DURATION_AUTONOMOUS    = 600    # seconds
    MAX_DURATION_INTERACTIVE   = 3600   # seconds
    CONTEXT_COMPRESS_THRESHOLD = 0.80   # compress when 80% of window used
