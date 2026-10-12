from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.db import init_db, ping_db
from app.routes.auth import router as auth_router
from app.schemas import HealthResponse


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(auth_router)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(**ping_db())
