from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

WORKER_RECOVERY_SLA_MS = 5_000


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True)

    app_env: str = "development"
    app_name: str = "CountyFlow AI"
    runtime_profile: Literal["local", "test", "docker-dev", "production"] = "local"
    authentication_provider: Literal["disabled", "development_jwt", "oidc_jwt"] = "disabled"
    auth_issuer: str = "countyflow-dev"
    auth_audience: str = "countyflow-api"
    auth_jwks_url: str = ""
    auth_algorithms: str = "RS256,ES256"
    auth_clock_skew_seconds: int = 30
    auth_access_token_ttl_seconds: int = 600
    auth_revocation_namespace: str = "countyflow:auth:revoked"
    development_jwt_secret: SecretStr = SecretStr("")
    security_audit_retention_days: int = 180
    rate_limit_namespace: str = "countyflow:ratelimit"
    rate_limit_dispatch_submit_capacity: int = 30
    rate_limit_dispatch_submit_refill_per_minute: int = 120
    rate_limit_runtime_override_capacity: int = 3
    rate_limit_runtime_override_refill_per_minute: int = 12
    rate_limit_memory_mutation_capacity: int = 5
    rate_limit_memory_mutation_refill_per_minute: int = 30
    rate_limit_observability_read_capacity: int = 60
    rate_limit_observability_read_refill_per_minute: int = 300
    rate_limit_ws_ticket_capacity: int = 10
    rate_limit_ws_ticket_refill_per_minute: int = 60
    rate_limit_authentication_invalid_capacity: int = 10
    rate_limit_authentication_invalid_refill_per_minute: int = 60
    rate_limit_emergency_read_capacity: int = 10
    rate_limit_emergency_read_window_seconds: int = 60
    ws_ticket_namespace: str = "countyflow:auth:ws-ticket"
    ws_ticket_ttl_seconds: int = 45
    security_hsts_enabled: bool = False
    request_body_default_max_bytes: int = 65_536
    request_body_dispatch_max_bytes: int = 16_384
    request_body_runtime_override_max_bytes: int = 8_192
    request_body_memory_mutation_max_bytes: int = 32_768
    request_body_ws_ticket_max_bytes: int = 2_048
    cors_allowed_origins: str = "http://localhost:5173,http://localhost:5174"
    database_url: str = "sqlite+pysqlite:///countyflow.db"
    redis_url: str = "redis://localhost:6379/0"
    runtime_checkpoint_backend: Literal["redis"] = "redis"
    runtime_checkpoint_namespace: str = "countyflow"
    runtime_checkpoint_retention_minutes: int = 10_080
    runtime_checkpoint_refresh_on_read: bool = False
    runtime_checkpoint_max_bytes: int = 1_048_576
    runtime_checkpoint_reconciliation_scan_limit: int = 10
    runtime_checkpoint_interrupt_after: Literal[
        "", "intake", "entity_memory", "graph_memory", "environment", "capacity", "routing", "dispatch", "audit"
    ] = ""
    runtime_thread_api_enabled: bool = False
    runtime_thread_history_limit: int = 20
    runtime_thread_history_max_limit: int = 100
    runtime_override_api_enabled: bool = False
    runtime_override_timeout_seconds: float = 5.0
    runtime_override_lock_ttl_ms: int = 8_000
    redis_stream_name: str = "countyflow:dispatch:tasks"
    redis_consumer_group: str = "countyflow-workers"
    redis_consumer_name: str = "worker-1"
    worker_consumer_name: str = "worker-1"
    worker_read_count: int = 1
    worker_block_ms: int = 1000
    worker_pending_min_idle_ms: int = 5000
    worker_recovery_count: int = 10
    worker_max_delivery_attempts: int = 3
    worker_retry_base_delay_ms: int = 1000
    worker_retry_max_delay_ms: int = 30000
    worker_idempotency_lock_ttl_ms: int = 30000
    redis_dlq_stream_name: str = "countyflow:dispatch:dlq"
    task_event_broker: str = "memory"
    task_event_stream_prefix: str = "countyflow:events:task"
    task_event_history_maxlen: int = 100
    task_event_block_ms: int = 1000
    qdrant_url: str = "http://localhost:6333"
    llm_provider: str = "openai_compatible"
    llm_base_url: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = ""
    embedding_provider: str = "openai_compatible"
    embedding_base_url: str = ""
    embedding_api_key: SecretStr = SecretStr("")
    embedding_model: str = ""
    embedding_dimension: int = Field(default=128, gt=0)
    environment_provider: Literal["development", "docker-development", "http"] = "development"
    capacity_provider: Literal["in-memory", "real"] = "in-memory"
    routing_provider: Literal["in-memory", "real"] = "in-memory"
    amap_web_service_key: SecretStr = SecretStr("")
    amap_route_api_base_url: str = "https://restapi.amap.com/v5/direction/driving"
    amap_route_timeout_seconds: float = 0.8
    amap_route_cb_failure_threshold: int = 3
    amap_route_cb_recovery_seconds: float = 5.0
    database_backend: Literal["sqlite", "mysql"] = "sqlite"
    redis_backend: Literal["fake", "server"] = "server"
    qdrant_backend: Literal["memory", "server"] = "server"
    graph_memory_backend: Literal["disabled", "fake", "neo4j"] = "disabled"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("")
    neo4j_database: str = "neo4j"
    neo4j_query_timeout_seconds: float = 1.0
    graph_memory_max_hops: int = 2
    graph_memory_result_limit: int = 25
    environment_api_base_url: str = ""
    environment_api_timeout_seconds: float = 0.8
    environment_cb_failure_threshold: int = 3
    environment_cb_recovery_seconds: float = 5.0
    capacity_limited_threshold: float = 0.8
    capacity_unavailable_threshold: float = 1.0
    memory_adoption_threshold: float = 0.75
    memory_auto_apply_min_confidence: float = 0.75
    memory_lower_confidence_reject_delta: float = 0.15
    memory_mutation_timeout_seconds: float = 5.0
    memory_mutation_lock_ttl_ms: int = 10000
    memory_mutation_api_enabled: bool = False
    metrics_enabled: bool = False
    metrics_host: str = "0.0.0.0"
    metrics_port: int = 9100
    backend_processes: int = 1
    prometheus_multiproc_dir: str = ""
    observability_api_enabled: bool = False
    prometheus_url: str = "http://prometheus:9090"
    grafana_public_url: str = ""
    observability_sample_interval_seconds: float = 15.0
    observability_probe_timeout_seconds: float = 0.8

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def worker_recovery_budget_ms(self) -> int:
        first_redelivery_backoff_ms = self.worker_retry_base_delay_ms * 2
        return self.worker_pending_min_idle_ms + self.worker_block_ms + first_redelivery_backoff_ms

    @model_validator(mode="after")
    def validate_runtime_profile(self) -> "Settings":
        if self.runtime_profile == "docker-dev":
            expected = {
                "embedding_provider": "fake",
                "capacity_provider": "in-memory",
                "routing_provider": "in-memory",
                "database_backend": "mysql",
                "redis_backend": "server",
                "qdrant_backend": "server",
                "graph_memory_backend": "neo4j",
            }
            mismatches = [f"{name}={getattr(self, name)}" for name, value in expected.items() if getattr(self, name) != value]
            if mismatches:
                raise ValueError(f"docker-dev runtime configuration mismatch: {', '.join(mismatches)}")
            if self.environment_provider not in {"docker-development", "http"}:
                raise ValueError(f"docker-dev runtime configuration mismatch: environment_provider={self.environment_provider}")
            if self.environment_provider == "http" and not self.environment_api_base_url:
                raise ValueError("docker-dev HTTP environment provider requires environment_api_base_url")
            if self.worker_pending_min_idle_ms <= self.worker_idempotency_lock_ttl_ms:
                raise ValueError("docker-dev worker_pending_min_idle_ms must exceed worker_idempotency_lock_ttl_ms")
            if self.worker_recovery_budget_ms >= WORKER_RECOVERY_SLA_MS:
                raise ValueError("docker-dev configured worker recovery budget must be below 5000ms")
            if self.authentication_provider != "development_jwt":
                raise ValueError("docker-dev requires authentication_provider=development_jwt")
            if len(self.development_jwt_secret.get_secret_value()) < 32:
                raise ValueError("docker-dev development JWT secret must be at least 32 characters")
        if self.runtime_profile == "production":
            unsafe = []
            if self.authentication_provider == "development_jwt":
                unsafe.append("development authentication is forbidden")
            elif self.authentication_provider != "oidc_jwt":
                unsafe.append("production authentication provider must be oidc_jwt")
            if not self.auth_issuer.strip():
                unsafe.append("authentication issuer is required")
            if not self.auth_audience.strip():
                unsafe.append("authentication audience is required")
            if not self.auth_jwks_url.strip():
                unsafe.append("authentication JWKS URL is required")
            algorithms = {value.strip() for value in self.auth_algorithms.split(",") if value.strip()}
            if not algorithms or not algorithms <= {"RS256", "ES256"}:
                unsafe.append("production authentication requires an asymmetric algorithm allowlist")
            origins = self.cors_allowed_origins_list
            if "*" in origins:
                unsafe.append("production wildcard CORS origin is forbidden")
            if any(not origin.startswith("https://") for origin in origins):
                unsafe.append("production requires HTTPS CORS origins")
            if self.runtime_checkpoint_interrupt_after and not (
                self.runtime_override_api_enabled and self.runtime_checkpoint_interrupt_after == "environment"
            ):
                unsafe.append("checkpoint interrupt injection")
            if self.embedding_provider == "fake":
                unsafe.append("embedding_provider=fake")
            if self.environment_provider != "http":
                unsafe.append(f"environment_provider={self.environment_provider}")
            if self.capacity_provider != "real":
                unsafe.append(f"capacity_provider={self.capacity_provider}")
            if self.routing_provider != "real":
                unsafe.append(f"routing_provider={self.routing_provider}")
            if self.database_backend != "mysql":
                unsafe.append(f"database_backend={self.database_backend}")
            if self.redis_backend != "server":
                unsafe.append(f"redis_backend={self.redis_backend}")
            if self.qdrant_backend != "server":
                unsafe.append(f"qdrant_backend={self.qdrant_backend}")
            if self.graph_memory_backend != "neo4j":
                unsafe.append(f"graph_memory_backend={self.graph_memory_backend}")
            if unsafe:
                raise ValueError(f"production runtime rejects development or fake providers: {', '.join(unsafe)}")
        if self.graph_memory_backend == "neo4j" and not all(
            (self.neo4j_uri, self.neo4j_user, self.neo4j_password.get_secret_value(), self.neo4j_database)
        ):
            raise ValueError("Neo4j connection settings are required when graph_memory_backend=neo4j")
        if self.auth_clock_skew_seconds < 0 or self.auth_clock_skew_seconds > 120:
            raise ValueError("authentication clock skew must be between 0 and 120 seconds")
        if self.auth_access_token_ttl_seconds <= 0 or self.auth_access_token_ttl_seconds > 900:
            raise ValueError("authentication access token TTL must be between 1 and 900 seconds")
        if not self.auth_revocation_namespace.strip():
            raise ValueError("authentication revocation namespace must not be empty")
        if not 30 <= self.security_audit_retention_days <= 365:
            raise ValueError("security audit retention must be between 30 and 365 days")
        rate_limit_values = {
            name: value
            for name, value in vars(self).items()
            if name.startswith("rate_limit_") and name != "rate_limit_namespace"
        }
        if not self.rate_limit_namespace.strip() or any(value <= 0 for value in rate_limit_values.values()):
            raise ValueError("rate-limit namespace and policy values must be positive")
        if not self.ws_ticket_namespace.strip() or not 15 <= self.ws_ticket_ttl_seconds <= 120:
            raise ValueError("WebSocket ticket namespace and TTL must be configured safely")
        body_limits = (
            self.request_body_default_max_bytes,
            self.request_body_dispatch_max_bytes,
            self.request_body_runtime_override_max_bytes,
            self.request_body_memory_mutation_max_bytes,
            self.request_body_ws_ticket_max_bytes,
        )
        if any(value <= 0 for value in body_limits) or any(
            value > self.request_body_default_max_bytes for value in body_limits[1:]
        ):
            raise ValueError("request body limits must be positive and bounded by the default")
        if not 1 <= self.graph_memory_max_hops <= 3:
            raise ValueError("graph_memory_max_hops must be between 1 and 3")
        if self.graph_memory_result_limit <= 0:
            raise ValueError("graph_memory_result_limit must be positive")
        if self.neo4j_query_timeout_seconds <= 0:
            raise ValueError("neo4j_query_timeout_seconds must be positive")
        if self.runtime_checkpoint_retention_minutes <= 0:
            raise ValueError("runtime checkpoint retention must be positive")
        if self.runtime_checkpoint_max_bytes <= 0:
            raise ValueError("runtime checkpoint max bytes must be positive")
        if self.runtime_checkpoint_reconciliation_scan_limit <= 0:
            raise ValueError("runtime checkpoint reconciliation scan limit must be positive")
        if not self.runtime_checkpoint_namespace.strip():
            raise ValueError("runtime checkpoint namespace must not be empty")
        if not 1 <= self.runtime_thread_history_limit <= self.runtime_thread_history_max_limit:
            raise ValueError("runtime thread history limit must not exceed its positive maximum")
        if self.runtime_override_timeout_seconds <= 0:
            raise ValueError("runtime override timeout must be positive")
        if self.runtime_override_lock_ttl_ms < int(self.runtime_override_timeout_seconds * 1000) + 2_000:
            raise ValueError("runtime override lock TTL must include a 2000ms safety margin")
        if self.runtime_override_api_enabled and self.runtime_checkpoint_interrupt_after != "environment":
            raise ValueError("runtime override API requires the environment checkpoint boundary")
        if not 0 <= self.memory_auto_apply_min_confidence <= 1:
            raise ValueError("memory_auto_apply_min_confidence must be between 0 and 1")
        if not 0 <= self.memory_lower_confidence_reject_delta <= 1:
            raise ValueError("memory_lower_confidence_reject_delta must be between 0 and 1")
        if self.memory_mutation_timeout_seconds <= 0:
            raise ValueError("memory_mutation_timeout_seconds must be positive")
        timeout_ms = int(self.memory_mutation_timeout_seconds * 1000)
        if self.memory_mutation_lock_ttl_ms < timeout_ms + 1000:
            raise ValueError(
                "memory_mutation_lock_ttl_ms must exceed memory_mutation_timeout_seconds by at least 1000ms"
            )
        if self.metrics_port <= 0 or self.metrics_port > 65535:
            raise ValueError("metrics_port must be a valid TCP port")
        if self.observability_sample_interval_seconds <= 0:
            raise ValueError("observability sample interval must be positive")
        if self.observability_probe_timeout_seconds <= 0:
            raise ValueError("observability probe timeout must be positive")
        if self.amap_route_timeout_seconds <= 0 or self.amap_route_timeout_seconds >= 1:
            raise ValueError("AMap route timeout must be greater than 0 and below 1 second")
        if self.amap_route_cb_failure_threshold <= 0 or self.amap_route_cb_recovery_seconds <= 0:
            raise ValueError("AMap route circuit-breaker settings must be positive")
        if self.backend_processes <= 0:
            raise ValueError("backend_processes must be positive")
        if self.runtime_profile == "production" and self.metrics_enabled and self.backend_processes > 1 and not self.prometheus_multiproc_dir:
            raise ValueError("PROMETHEUS_MULTIPROC_DIR is required when metrics use multiple backend processes")
        return self

    def runtime_summary(self) -> dict[str, str]:
        return {
            "runtime_profile": self.runtime_profile,
            "embedding_provider": self.embedding_provider,
            "environment_provider": self.environment_provider,
            "capacity_provider": self.capacity_provider,
            "routing_provider": self.routing_provider,
            "database": self.database_backend,
            "redis": self.redis_backend,
            "qdrant": self.qdrant_backend,
            "graph_memory": self.graph_memory_backend,
            "metrics": "enabled" if self.metrics_enabled else "disabled",
            "observability_api": "enabled" if self.observability_api_enabled else "disabled",
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
