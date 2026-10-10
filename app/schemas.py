from pydantic import BaseModel


class HealthResponse(BaseModel):
    ok: bool
    user: str
    database: str
