# ──────────────────────────────────────────────────────────────────────
# services/agent_reach.py — High-level service wrapping Agent Reach CLI
# ──────────────────────────────────────────────────────────────────────
"""
Business-logic layer between the API routes and the raw CLI runner.

Each public function maps to one Agent Reach capability and returns
clean, parsed data ready for the API to serialise as JSON.
"""
from __future__ import annotations

import json
import re
import logging
from enum import Enum
from dataclasses import dataclass

import httpx

from config import get_settings
from services.runner import run, CommandResult

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────

JINA_READER_BASE = "https://r.jina.ai"
JINA_SEARCH_BASE = "https://s.jina.ai"

# ANSI escape code stripper
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]|\[/?[a-z ]+\]")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes and Rich markup from CLI output."""
    return _ANSI_RE.sub("", text)


# ── Data Models ──────────────────────────────────────────────────────


class ChannelStatus(str, Enum):
    OK = "ok"
    NEEDS_CONFIG = "needs_config"
    NOT_INSTALLED = "not_installed"
    UNKNOWN = "unknown"


@dataclass
class Channel:
    """Parsed representation of a single Agent Reach channel."""

    name: str
    description: str
    status: ChannelStatus
    hint: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "hint": self.hint,
        }


# ── Agent Reach CLI Wrappers ────────────────────────────────────────


async def doctor() -> dict:
    """Run ``agent-reach doctor`` and parse the output into structured data."""
    settings = get_settings()
    result = await run(
        settings.resolved_bin,
        ("doctor",),
        timeout=settings.command_timeout,
    )

    channels = _parse_doctor_output(result.stdout)
    active = sum(1 for c in channels if c.status == ChannelStatus.OK)

    return {
        "ok": result.ok,
        "active_channels": active,
        "total_channels": len(channels),
        "channels": [c.to_dict() for c in channels],
        "raw_output": _strip_ansi(result.stdout),
    }


async def doctor_raw() -> CommandResult:
    """Run ``agent-reach doctor`` and return the raw result."""
    settings = get_settings()
    return await run(
        settings.resolved_bin,
        ("doctor",),
        timeout=settings.command_timeout,
    )


async def check_update() -> dict:
    """Run ``agent-reach check-update`` and return the result."""
    settings = get_settings()
    result = await run(
        settings.resolved_bin,
        ("check-update",),
        timeout=30,
    )
    return {
        "ok": result.ok,
        "output": _strip_ansi(result.stdout),
        "error": result.stderr if not result.ok else "",
    }


# ── Web / Jina Reader ───────────────────────────────────────────────


async def read_webpage(url: str) -> dict:
    """Read any webpage via Jina Reader and return the markdown content."""
    jina_url = f"{JINA_READER_BASE}/{url}"
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(jina_url)
        return {
            "ok": resp.status_code == 200,
            "url": url,
            "content": resp.text,
            "status_code": resp.status_code,
        }


async def search_web(query: str, num_results: int = 5) -> dict:
    """Search the web via Jina Search and return results."""
    jina_url = f"{JINA_SEARCH_BASE}/{query}"
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(jina_url, headers={"Accept": "application/json"})
        if resp.status_code == 200:
            try:
                data = resp.json()
            except Exception:
                data = resp.text
        else:
            data = resp.text
        return {
            "ok": resp.status_code == 200,
            "query": query,
            "results": data,
            "status_code": resp.status_code,
        }


# ── GitHub ───────────────────────────────────────────────────────────


async def github_search(query: str, search_type: str = "repos", limit: int = 10) -> dict:
    """Search GitHub using the ``gh`` CLI."""
    result = await run(
        "gh",
        ("search", search_type, query, "--limit", str(limit), "--json",
         "fullName,description,url,stargazersCount,updatedAt"),
        timeout=30,
    )
    parsed = []
    if result.ok:
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError:
            parsed = []

    return {
        "ok": result.ok,
        "query": query,
        "type": search_type,
        "results": parsed,
        "error": result.stderr if not result.ok else "",
    }


# ── YouTube (yt-dlp) ────────────────────────────────────────────────


async def youtube_info(url: str) -> dict:
    """Fetch YouTube video metadata using ``yt-dlp``."""
    settings = get_settings()
    result = await run(
        "yt-dlp",
        ("--dump-json", "--no-download", url),
        timeout=settings.command_timeout,
    )
    parsed = {}
    if result.ok:
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError:
            parsed = {}

    # Return only the useful fields
    clean = {}
    if parsed:
        clean = {
            "title": parsed.get("title", ""),
            "description": parsed.get("description", "")[:500],
            "uploader": parsed.get("uploader", ""),
            "duration_string": parsed.get("duration_string", ""),
            "view_count": parsed.get("view_count", 0),
            "like_count": parsed.get("like_count", 0),
            "upload_date": parsed.get("upload_date", ""),
            "thumbnail": parsed.get("thumbnail", ""),
            "webpage_url": parsed.get("webpage_url", url),
        }

    return {
        "ok": result.ok,
        "url": url,
        "info": clean,
        "error": result.stderr if not result.ok else "",
    }


async def youtube_subtitles(url: str, lang: str = "en") -> dict:
    """Download subtitles for a YouTube video using ``yt-dlp``."""
    settings = get_settings()
    result = await run(
        "yt-dlp",
        (
            "--write-sub", "--write-auto-sub",
            "--sub-lang", lang,
            "--sub-format", "json3",
            "--skip-download",
            "--print-to-file", "subtitle:%(subtitles)s",
            "-o", "-",
            url,
        ),
        timeout=settings.command_timeout,
    )
    return {
        "ok": result.ok,
        "url": url,
        "language": lang,
        "subtitles": result.stdout if result.ok else "",
        "error": result.stderr if not result.ok else "",
    }


# ── RSS ──────────────────────────────────────────────────────────────


async def read_rss(feed_url: str, limit: int = 10) -> dict:
    """Fetch and parse an RSS/Atom feed using the Jina Reader."""
    return await read_webpage(feed_url)


# ── Internal Helpers ─────────────────────────────────────────────────


def _parse_doctor_output(raw: str) -> list[Channel]:
    """Best-effort parser for ``agent-reach doctor`` output.

    The CLI output uses emoji/bracket indicators:
      ✅  = working
      [!] = installed but needs configuration
      [X] = not installed
    """
    cleaned = _strip_ansi(raw)
    channels: list[Channel] = []
    found_channels = set()

    # English Translations Mapping (defined once, used in loop + post-loop)
    translations = {
        "GitHub 仓库和代码": ("GitHub", "Search repositories and code. Run `gh auth login` if setup is needed."),
        "YouTube 视频和字幕": ("YouTube", "Fetch videos and subtitles. yt-dlp is required."),
        "V2EX 节点、主题与回复": ("V2EX", "Public API for topics and replies."),
        "RSS/Atom 订阅源": ("RSS/Atom", "Read RSS/Atom feeds."),
        "全网语义搜索": ("Web Search", "Semantic web search via Exa or Jina."),
        "任意网页": ("Read Webpage", "Read any webpage via Jina Reader."),
        "B站视频、字幕和搜索": ("Bilibili", "Bilibili video and subtitle search."),
        "Twitter/X 推文": ("Twitter / X", "Read and search tweets."),
        "Reddit 帖子和评论": ("Reddit", "Read Reddit posts and comments."),
        "Facebook 帖子、主页和群组": ("Facebook", "Facebook posts and groups."),
        "Instagram 用户、主页和指定用户帖子": ("Instagram", "Instagram profiles and posts."),
        "小红书笔记": ("XiaoHongShu", "Xiaohongshu notes and search."),
        "小宇宙播客转文字": ("Xiaoyuzhou Podcast", "Podcast transcription to text."),
        "雪球股票行情与社区动态": ("Xueqiu", "Stock quotes and community."),
        "LinkedIn 职业社交": ("LinkedIn", "Professional networking and profiles."),
    }

    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        status = ChannelStatus.UNKNOWN
        if "✅" in stripped:
            status = ChannelStatus.OK
        elif "[!]" in stripped:
            status = ChannelStatus.NEEDS_CONFIG
        elif "[X]" in stripped:
            status = ChannelStatus.NOT_INSTALLED
        else:
            continue  # not a channel line

        # Extract name and description
        # Pattern: "✅  Name — Description" or "[!]  Name — Description"
        parts = re.split(r"[—–\-]{1,2}", stripped, maxsplit=1)
        # Clean the name part of status indicators
        name_part = parts[0] if len(parts) > 0 else stripped
        for marker in ("✅", "[!]", "[X]"):
            name_part = name_part.replace(marker, "").strip()
            
        # Filter out headers that look like channels
        if name_part.startswith("图例") or name_part.startswith("装好即用") or name_part.startswith("可选渠道"):
            continue
            
        if len(parts) == 2:
            description = parts[1].strip()
        else:
            description = ""
        

        # Apply translation if found
        for zh_key, (en_name, en_desc) in translations.items():
            if zh_key in name_part:
                name_part = en_name
                if not description:  # Only override if it wasn't parsed properly
                    description = en_desc
                found_channels.add(zh_key)
                break

        # Extract hint text (after period or colon) if it wasn't translated
        hint = ""
        if status in (ChannelStatus.NEEDS_CONFIG, ChannelStatus.NOT_INSTALLED) and "未安装" in description:
            hint = "Requires installation or login"

        channels.append(
            Channel(
                name=name_part,
                description=description,
                status=status,
                hint=hint,
            )
        )

    # Append any optional channels that were not listed by the CLI at all
    for zh_key, (en_name, en_desc) in translations.items():
        if zh_key not in found_channels:
            channels.append(
                Channel(
                    name=en_name,
                    description=en_desc,
                    status=ChannelStatus.NOT_INSTALLED,
                    hint="Requires installation or login",
                )
            )

    return channels
