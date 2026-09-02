"""Low-cardinality label contracts shared by every process."""

METRIC_LABEL_ALLOWLIST = frozenset(
    {
        "method",
        "route_template",
        "status_class",
        "agent",
        "result",
        "decision",
        "operation",
        "dependency",
        "worker",
        "event_type",
        "runtime_profile",
        "projection",
        "store",
        "reason_code",
        "route_class",
    }
)

SECURITY_ROUTE_CLASSES = frozenset(
    {"auth", "dispatch", "runtime", "memory", "observability", "audit", "websocket", "other"}
)

FORBIDDEN_HIGH_CARDINALITY_LABELS = frozenset(
    {
        "task_id",
        "thread_id",
        "order_id",
        "dispatch_id",
        "memory_id",
        "mutation_id",
        "override_id",
        "checkpoint_id",
        "driver_id",
        "vehicle_id",
        "route_id",
        "operator_id",
        "user_id",
        "reason",
        "error_message",
        "raw_url",
    }
)

AGENTS = frozenset({"intake", "entity_memory", "graph_memory", "environment", "capacity", "routing", "dispatch", "audit"})
WORKERS = frozenset({"worker-1", "worker-2"})
DEPENDENCIES = frozenset({"mysql", "redis", "qdrant", "neo4j"})
