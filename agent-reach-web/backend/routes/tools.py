# ──────────────────────────────────────────────────────────────────────
# routes/tools.py — Endpoints for individual Agent Reach tools
# ──────────────────────────────────────────────────────────────────────
from fastapi import APIRouter, Query

from services import agent_reach

router = APIRouter(prefix="/api/tools", tags=["Tools"])


# ── Web ──────────────────────────────────────────────────────────────


@router.get("/web/read")
async def read_webpage(
    url: str = Query(..., description="Full URL of the webpage to read"),
):
    """Read any webpage via Jina Reader and return the content as markdown."""
    return await agent_reach.read_webpage(url)


@router.get("/web/search")
async def search_web(
    q: str = Query(..., description="Search query"),
    num: int = Query(5, ge=1, le=20, description="Number of results"),
):
    """Search the web using Jina Search."""
    return await agent_reach.search_web(q, num)


# ── GitHub ───────────────────────────────────────────────────────────


@router.get("/github/search")
async def github_search(
    q: str = Query(..., description="Search query"),
    type: str = Query("repos", description="Search type: repos, issues, prs, code"),
    limit: int = Query(10, ge=1, le=50, description="Max results"),
):
    """Search GitHub repositories, issues, or PRs via ``gh`` CLI."""
    return await agent_reach.github_search(q, type, limit)


# ── YouTube ──────────────────────────────────────────────────────────


@router.get("/youtube/info")
async def youtube_info(
    url: str = Query(..., description="YouTube video URL"),
):
    """Fetch metadata for a YouTube video using ``yt-dlp``."""
    return await agent_reach.youtube_info(url)


@router.get("/youtube/subtitles")
async def youtube_subtitles(
    url: str = Query(..., description="YouTube video URL"),
    lang: str = Query("en", description="Subtitle language code"),
):
    """Download subtitles for a YouTube video using ``yt-dlp``."""
    return await agent_reach.youtube_subtitles(url, lang)


# ── RSS ──────────────────────────────────────────────────────────────


@router.get("/rss/read")
async def read_rss(
    url: str = Query(..., description="RSS / Atom feed URL"),
    limit: int = Query(10, ge=1, le=50, description="Max items"),
):
    """Fetch and read an RSS/Atom feed."""
    return await agent_reach.read_rss(url, limit)
