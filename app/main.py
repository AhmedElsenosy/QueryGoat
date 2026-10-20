from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.extension import _rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.db import init_db, ping_db
from app.rate_limit import limiter
from app.routes.auth import router as auth_router
from app.routes.internal import router as internal_router
from app.routes.leaderboard import router as leaderboard_router
from app.routes.puzzles import router as puzzles_router
from app.routes.users import router as users_router
from app.schemas import HealthResponse


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


def _frontends() -> list[str]:
    """Allowed browser origins: local Next.js + any configured domain(s)."""
    origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
    if settings.app_frontend_url.startswith("http"):
        origins.append(settings.app_frontend_url.rstrip("/"))
    return origins


app = FastAPI(title=settings.app_name, lifespan=lifespan)

# CORS must be added FIRST so it is the outermost middleware (slowapi must
# still see requests after it, and 429 responses need CORS headers too).
app.add_middleware(
    CORSMiddleware,
    allow_origins=_frontends(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.include_router(leaderboard_router)
app.include_router(auth_router)
app.include_router(puzzles_router)
app.include_router(users_router)
app.include_router(internal_router)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(**ping_db())
