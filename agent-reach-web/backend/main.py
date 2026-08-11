# ──────────────────────────────────────────────────────────────────────
# main.py — FastAPI application entry-point
# ──────────────────────────────────────────────────────────────────────
"""
Agent Reach Web — Backend API

A lightweight FastAPI server that wraps Agent Reach CLI tools and
exposes them as a clean REST API for the web frontend.

Run locally:
    uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from routes.status import router as status_router
from routes.tools import router as tools_router
from routes.settings import router as settings_router
from routes.chat_linkedin import router as chat_linkedin_router
from routes.chat_public import router as chat_public_router
from routes.tools_execution import router as tools_execution_router

# ── Logging ──────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("agent-reach")

# ── FastAPI App ──────────────────────────────────────────────────────

settings = get_settings()

app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    description="Backend for the Agent Reach Web Console",
)

# ── Middleware ────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow vercel to hit this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ───────────────────────────────────────────────────────────

app.include_router(status_router)
app.include_router(tools_router)
app.include_router(settings_router)
app.include_router(chat_linkedin_router)
app.include_router(chat_public_router)
app.include_router(tools_execution_router)

# Mount static files (the vanilla JS frontend)
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", tags=["Root"])
async def root():
    """Serve the single-page Vanilla JS frontend."""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
