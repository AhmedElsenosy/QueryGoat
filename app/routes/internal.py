from fastapi import APIRouter, Header, HTTPException, status

from app.agent.run_daily import run_daily
from app.config import settings
from app.schemas import DailyRunResponse

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/daily/run", response_model=DailyRunResponse)
def run_daily_job(
    x_daily_job_secret: str | None = Header(default=None, alias="X-Daily-Job-Secret"),
) -> DailyRunResponse:
    if not settings.daily_job_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DAILY_JOB_SECRET is not configured.",
        )
    if x_daily_job_secret != settings.daily_job_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid daily job secret.",
        )
    result = run_daily()
    puzzle_id = result.get("daily_puzzle_id")
    return DailyRunResponse(
        status=result.get("status") or "failed",
        puzzle_date=result.get("puzzle_date") or "",
        attempts=int(result.get("attempt") or 0),
        daily_puzzle_id=puzzle_id,
        error=result.get("error"),
    )
