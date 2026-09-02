from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RuntimeThreadDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thread_id: str
    task_id: str
    status: str
    terminal: bool
    current_checkpoint_id: str | None
    state_version: int = Field(ge=0)
    current_node: str | None
    next_node: str | None
    checkpoint_count: int = Field(ge=0)
    checkpoint_size_bytes: int | None = Field(default=None, ge=0)
    last_event_sequence: int | None = Field(default=None, ge=0)
    worker_consumer: str | None = None
    checkpoint_available: bool
    state: dict[str, object] | None
    created_at: datetime
    updated_at: datetime
    terminal_at: datetime | None


class RuntimeCheckpointHistoryItem(BaseModel):
    checkpoint_id: str
    state_version: int = Field(ge=0)
    parent_checkpoint_id: str | None = None
    node: str | None = None
    next_node: str | None = None
    checkpoint_size_bytes: int | None = Field(default=None, ge=0)
    checkpoint_available: bool | None = None
    state: dict[str, object] | None = None
    created_at: datetime | None = None


class RuntimeThreadHistoryResponse(BaseModel):
    thread_id: str
    items: list[RuntimeCheckpointHistoryItem]
