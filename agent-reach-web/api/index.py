from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes.chat_linkedin import router as chat_linkedin_router
from api.routes.chat_public import router as chat_public_router
from api.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    description="Vercel API for Agent Reach LLM Chat"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
app.include_router(chat_linkedin_router, prefix="/api")
app.include_router(chat_public_router, prefix="/api")

@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "Vercel LLM Gateway is running"}

import httpx
from fastapi import Request
from fastapi.responses import Response

@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_to_vm(path: str, request: Request):
    """Proxy non-chat requests directly to the VM."""
    vm_url = f"{settings.vm_host.rstrip('/')}/api/{path}"
    
    # We shouldn't send the Vercel host header to the VM
    headers = dict(request.headers)
    headers.pop("host", None)
    
    async with httpx.AsyncClient() as client:
        body = await request.body()
        resp = await client.request(
            method=request.method,
            url=vm_url,
            headers=headers,
            content=body,
            timeout=120.0
        )
        return Response(content=resp.content, status_code=resp.status_code, headers=dict(resp.headers))
