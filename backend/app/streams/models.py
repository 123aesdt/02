import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import NotRequired, TypedDict

from app.streams.errors import QueueMessageError


class DispatchTaskPayload(TypedDict):
    driver_id: str
    vehicle_id: str
    route_id: str
    anomaly_type: str
    anomaly_description: str
    vehicle_status: NotRequired[str]
    incident_node_id: NotRequired[str | None]
    affected_edge_id: NotRequired[str | None]


@dataclass(frozen=True)
class DispatchTaskMessage:
    schema_version: str
    task_id: str
    order_id: int
    anomaly_id: int | None
    idempotency_key: str
    created_at: str
    payload: DispatchTaskPayload
    correlation_id: str | None = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "schema_version": self.schema_version,
                "task_id": self.task_id,
                "order_id": self.order_id,
                "anomaly_id": self.anomaly_id,
                "idempotency_key": self.idempotency_key,
                "created_at": self.created_at,
                "payload": self.payload,
                "correlation_id": self.correlation_id,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, value: str | bytes) -> "DispatchTaskMessage":
        try:
            raw = json.loads(value.decode("utf-8") if isinstance(value, bytes) else value)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise QueueMessageError("Stream message is not valid JSON.") from error
        if not isinstance(raw, dict):
            raise QueueMessageError("Stream message must be a JSON object.")
        if raw.get("schema_version") != "1":
            raise QueueMessageError("Stream message schema version is unsupported.")
        try:
            task_id = cls._required_text(raw, "task_id")
            idempotency_key = cls._required_text(raw, "idempotency_key")
            order_id = cls._integer(raw.get("order_id"), "order_id")
            anomaly_id = raw.get("anomaly_id")
            if anomaly_id is not None:
                anomaly_id = cls._integer(anomaly_id, "anomaly_id")
            created_at = cls._utc_timestamp(raw.get("created_at"))
            payload = cls._payload(raw.get("payload"))
        except QueueMessageError:
            raise
        correlation_id = raw.get("correlation_id")
        if correlation_id is not None and (not isinstance(correlation_id, str) or not correlation_id):
            raise QueueMessageError("Stream message field correlation_id is invalid.")
        return cls("1", task_id, order_id, anomaly_id, idempotency_key, created_at, payload, correlation_id)

    @staticmethod
    def _required_text(raw: dict[object, object], field: str) -> str:
        value = raw.get(field)
        if not isinstance(value, str) or not value:
            raise QueueMessageError(f"Stream message field {field} is required.")
        return value

    @staticmethod
    def _integer(value: object, field: str) -> int:
        if not isinstance(value, int) or isinstance(value, bool):
            raise QueueMessageError(f"Stream message field {field} must be an integer.")
        return value

    @staticmethod
    def _utc_timestamp(value: object) -> str:
        if not isinstance(value, str):
            raise QueueMessageError("Stream message field created_at is required.")
        try:
            timestamp = datetime.fromisoformat(value)
        except ValueError as error:
            raise QueueMessageError("Stream message created_at must be ISO-8601 UTC.") from error
        if timestamp.tzinfo is None or timestamp.utcoffset() != UTC.utcoffset(timestamp):
            raise QueueMessageError("Stream message created_at must be ISO-8601 UTC.")
        return value

    @classmethod
    def _payload(cls, value: object) -> DispatchTaskPayload:
        if not isinstance(value, dict):
            raise QueueMessageError("Stream message payload is required.")
        vehicle_status = value.get("vehicle_status", "NORMAL")
        if not isinstance(vehicle_status, str) or not vehicle_status:
            raise QueueMessageError("Stream message field vehicle_status is invalid.")
        payload: DispatchTaskPayload = {
            "driver_id": cls._required_text(value, "driver_id"),
            "vehicle_id": cls._required_text(value, "vehicle_id"),
            "route_id": cls._required_text(value, "route_id"),
            "anomaly_type": cls._required_text(value, "anomaly_type"),
            "anomaly_description": cls._required_text(value, "anomaly_description"),
            "vehicle_status": vehicle_status,
        }
        if "incident_node_id" in value:
            payload["incident_node_id"] = cls._optional_text(value, "incident_node_id")
        if "affected_edge_id" in value:
            payload["affected_edge_id"] = cls._optional_text(value, "affected_edge_id")
        return payload

    @staticmethod
    def _optional_text(raw: dict[object, object], field: str) -> str | None:
        value = raw.get(field)
        if value is None:
            return None
        if not isinstance(value, str) or not value:
            raise QueueMessageError(f"Stream message field {field} is invalid.")
        return value


@dataclass(frozen=True)
class StreamMessage:
    message_id: str
    task: DispatchTaskMessage
    delivery_count: int | None
    metadata: dict[str, str]


@dataclass(frozen=True)
class PendingSummary:
    pending: int
    min_message_id: str | None
    max_message_id: str | None
    consumers: dict[str, int]


@dataclass(frozen=True)
class StreamOperationalState:
    pending_by_consumer: dict[str, int]
    stream_lag: int
    dlq_messages: int


@dataclass(frozen=True)
class DeadLetterMessage:
    schema_version: str
    original_message_id: str
    task_id: str
    order_id: int
    idempotency_key: str
    original_stream: str
    failure_reason: str
    error_code: str
    delivery_count: int
    failed_at: str
    payload: DispatchTaskPayload

    def to_json(self) -> str:
        return json.dumps(
            {
                "schema_version": self.schema_version,
                "original_message_id": self.original_message_id,
                "task_id": self.task_id,
                "order_id": self.order_id,
                "idempotency_key": self.idempotency_key,
                "original_stream": self.original_stream,
                "failure_reason": self.failure_reason,
                "error_code": self.error_code,
                "delivery_count": self.delivery_count,
                "failed_at": self.failed_at,
                "payload": self.payload,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def from_stream_message(
        cls,
        *,
        original_message_id: str,
        stream_message: DispatchTaskMessage,
        original_stream: str,
        failure_reason: str,
        error_code: str,
        delivery_count: int,
    ) -> "DeadLetterMessage":
        return cls(
            "1",
            cls._required_text(original_message_id, "original_message_id"),
            stream_message.task_id,
            stream_message.order_id,
            stream_message.idempotency_key,
            cls._required_text(original_stream, "original_stream"),
            cls._required_text(failure_reason, "failure_reason"),
            cls._required_text(error_code, "error_code"),
            cls._positive_integer(delivery_count, "delivery_count"),
            datetime.now(UTC).isoformat(),
            DispatchTaskMessage._payload(stream_message.payload),
        )

    @classmethod
    def from_json(cls, value: str | bytes) -> "DeadLetterMessage":
        try:
            raw = json.loads(value.decode("utf-8") if isinstance(value, bytes) else value)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise QueueMessageError("Dead-letter message is not valid JSON.") from error
        if not isinstance(raw, dict) or raw.get("schema_version") != "1":
            raise QueueMessageError("Dead-letter message schema version is unsupported.")
        return cls(
            "1",
            cls._required_text(raw.get("original_message_id"), "original_message_id"),
            cls._required_text(raw.get("task_id"), "task_id"),
            cls._integer(raw.get("order_id"), "order_id"),
            cls._required_text(raw.get("idempotency_key"), "idempotency_key"),
            cls._required_text(raw.get("original_stream"), "original_stream"),
            cls._required_text(raw.get("failure_reason"), "failure_reason"),
            cls._required_text(raw.get("error_code"), "error_code"),
            cls._positive_integer(raw.get("delivery_count"), "delivery_count"),
            cls._utc_timestamp(raw.get("failed_at")),
            DispatchTaskMessage._payload(raw.get("payload")),
        )

    @staticmethod
    def _required_text(value: object, field: str) -> str:
        if not isinstance(value, str) or not value:
            raise QueueMessageError(f"Dead-letter message field {field} is required.")
        return value

    @staticmethod
    def _integer(value: object, field: str) -> int:
        if not isinstance(value, int) or isinstance(value, bool):
            raise QueueMessageError(f"Dead-letter message field {field} must be an integer.")
        return value

    @classmethod
    def _positive_integer(cls, value: object, field: str) -> int:
        integer = cls._integer(value, field)
        if integer < 1:
            raise QueueMessageError(f"Dead-letter message field {field} must be positive.")
        return integer

    @staticmethod
    def _utc_timestamp(value: object) -> str:
        if not isinstance(value, str):
            raise QueueMessageError("Dead-letter message field failed_at is required.")
        try:
            timestamp = datetime.fromisoformat(value)
        except ValueError as error:
            raise QueueMessageError("Dead-letter message failed_at must be ISO-8601 UTC.") from error
        if timestamp.tzinfo is None or timestamp.utcoffset() != UTC.utcoffset(timestamp):
            raise QueueMessageError("Dead-letter message failed_at must be ISO-8601 UTC.")
        return value
