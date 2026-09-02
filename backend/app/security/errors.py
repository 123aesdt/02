from dataclasses import dataclass


@dataclass
class SecurityHttpError(Exception):
    status_code: int
    code: str
    message: str
    headers: dict[str, str] | None = None
