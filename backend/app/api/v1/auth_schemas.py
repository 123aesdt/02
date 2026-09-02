from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.security.permissions import Role


class PrincipalResponse(BaseModel):
    subject_id: str
    display_name: str
    roles: list[str]
    permissions: list[str]
    auth_method: str
    issued_at: datetime
    expires_at: datetime


class DevelopmentSessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    principal: PrincipalResponse


class DevelopmentSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Role = Role.ADMIN


class DemoEmployeeResponse(BaseModel):
    employee_id: str
    display_name: str
    role: Role


class DemoEmployeeSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: str = Field(min_length=1, max_length=32)
