# ──────────────────────────────────────────────────────────────────────
# routes/status.py — Health & status endpoints
# ──────────────────────────────────────────────────────────────────────
from fastapi import APIRouter

from services import agent_reach

router = APIRouter(prefix="/api/status", tags=["Status"])


@router.get("/health")
async def health_check():
    """Lightweight liveness probe — always returns 200."""
    return {"status": "healthy"}


@router.get("/doctor")
async def run_doctor():
    """Run ``agent-reach doctor`` and return structured channel status."""
    return await agent_reach.doctor()


@router.get("/updates")
async def check_updates():
    """Check if a newer version of Agent Reach is available."""
    return await agent_reach.check_update()
