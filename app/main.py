from fastapi import FastAPI

from app.config import settings
from app.db import ping_db
from app.schemas import HealthResponse

app = FastAPI(title=settings.app_name)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(**ping_db())
