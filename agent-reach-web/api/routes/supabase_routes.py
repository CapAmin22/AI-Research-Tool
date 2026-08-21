from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from api.utils.supabase import get_supabase_client

router = APIRouter(prefix="/user", tags=["User"])

class VaultData(BaseModel):
    linkedin_li_at: str | None = None
    twitter_auth_token: str | None = None
    twitter_ct0: str | None = None
    reddit_cookie: str | None = None
    instagram_sessionid: str | None = None
    facebook_cookies: str | None = None
    github_token: str | None = None

def get_auth_client(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        supabase = get_supabase_client(token)
        user = supabase.auth.get_user(token)
        return supabase, user.user.id
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

@router.get("/sessions")
async def get_sessions(request: Request):
    supabase, user_id = get_auth_client(request)
    res = supabase.table("research_sessions").select("id, title, created_at").eq("user_id", user_id).order("created_at", desc=True).execute()
    return {"sessions": res.data}

@router.get("/sessions/{session_id}")
async def get_session_history(session_id: str, request: Request):
    supabase, user_id = get_auth_client(request)
    # RLS ensures they can only read their own session messages
    res = supabase.table("messages").select("*").eq("session_id", session_id).order("created_at").execute()
    return {"messages": res.data}

@router.get("/vault")
async def get_vault(request: Request):
    supabase, user_id = get_auth_client(request)
    res = supabase.table("user_vault").select("*").eq("user_id", user_id).execute()
    if not res.data:
        return {}
    return res.data[0]

@router.post("/vault")
async def update_vault(data: VaultData, request: Request):
    supabase, user_id = get_auth_client(request)
    payload = {k: v for k, v in data.model_dump().items() if v is not None}
    payload["user_id"] = user_id
    
    # Upsert the vault data
    res = supabase.table("user_vault").upsert(payload).execute()
    return {"success": True}
