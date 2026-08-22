from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from api.utils.supabase import get_supabase_client
import httpx
import json

router = APIRouter(prefix="/user", tags=["User"])

class VaultData(BaseModel):
    linkedin_li_at: str | None = None
    twitter_auth_token: str | None = None
    twitter_ct0: str | None = None
    reddit_cookie: str | None = None
    instagram_sessionid: str | None = None
    facebook_cookies: str | None = None
    github_token: str | None = None

class ValidateCredRequest(BaseModel):
    credential_type: str  # e.g. "linkedin", "twitter", "reddit", "instagram", "facebook"
    value: str            # The cookie/token value to test

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

@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    supabase, user_id = get_auth_client(request)
    # Delete messages first (child records), then the session
    supabase.table("messages").delete().eq("session_id", session_id).execute()
    res = supabase.table("research_sessions").delete().eq("id", session_id).eq("user_id", user_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Session not found or permission denied")
    return {"success": True}

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
    # Filter out None AND empty strings — only keep real values
    payload = {}
    for k, v in data.model_dump().items():
        if v is not None and v.strip() != "":
            payload[k] = v.strip()
    
    if not payload:
        return {"success": True, "message": "No credentials to save."}
    
    payload["user_id"] = user_id
    
    # Check if vault row exists
    existing = supabase.table("user_vault").select("user_id").eq("user_id", user_id).execute()
    if existing.data:
        # Update existing row — remove user_id from update payload
        update_payload = {k: v for k, v in payload.items() if k != "user_id"}
        supabase.table("user_vault").update(update_payload).eq("user_id", user_id).execute()
    else:
        # Insert new row
        supabase.table("user_vault").insert(payload).execute()
    
    return {"success": True}

# ── Credential Validation Endpoint ──
@router.post("/vault/validate")
async def validate_credential(data: ValidateCredRequest, request: Request):
    """Test if a credential (cookie/token) is valid by making a lightweight API call to the target platform."""
    get_auth_client(request)  # Ensure user is authenticated
    
    cred_type = data.credential_type.lower().strip()
    value = data.value.strip()
    
    if not value:
        return {"valid": False, "message": "Empty value provided."}
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            
            if cred_type == "linkedin":
                # Test li_at by hitting LinkedIn's own API
                resp = await client.get(
                    "https://www.linkedin.com/voyager/api/me",
                    headers={
                        "Cookie": f"li_at={value}",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "csrf-token": "ajax:0000000000000000000",
                        "x-li-lang": "en_US",
                        "x-restli-protocol-version": "2.0.0",
                    }
                )
                if resp.status_code == 200:
                    try:
                        profile = resp.json()
                        name = profile.get("miniProfile", {}).get("firstName", "Unknown")
                        return {"valid": True, "message": f"✅ Valid — Authenticated as '{name}'"}
                    except:
                        return {"valid": True, "message": "✅ Valid — LinkedIn session is active"}
                elif resp.status_code == 401 or resp.status_code == 403:
                    return {"valid": False, "message": "❌ Invalid or expired — LinkedIn rejected this cookie"}
                else:
                    return {"valid": False, "message": f"❌ Unexpected response (HTTP {resp.status_code})"}
            
            elif cred_type == "twitter":
                # Test auth_token by hitting Twitter's settings API
                resp = await client.get(
                    "https://api.x.com/1.1/account/settings.json",
                    headers={
                        "Cookie": f"auth_token={value}",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
                    }
                )
                if resp.status_code == 200:
                    try:
                        settings = resp.json()
                        screen_name = settings.get("screen_name", "Unknown")
                        return {"valid": True, "message": f"✅ Valid — Authenticated as @{screen_name}"}
                    except:
                        return {"valid": True, "message": "✅ Valid — Twitter session is active"}
                else:
                    return {"valid": False, "message": f"❌ Invalid or expired (HTTP {resp.status_code})"}
            
            elif cred_type == "reddit":
                resp = await client.get(
                    "https://www.reddit.com/api/me.json",
                    headers={
                        "Cookie": f"reddit_session={value}",
                        "User-Agent": "Mozilla/5.0 AgentReach/1.0",
                    }
                )
                if resp.status_code == 200:
                    try:
                        me = resp.json()
                        if me.get("data", {}).get("name"):
                            return {"valid": True, "message": f"✅ Valid — Authenticated as u/{me['data']['name']}"}
                    except:
                        pass
                    return {"valid": True, "message": "✅ Valid — Reddit session is active"}
                else:
                    return {"valid": False, "message": f"❌ Invalid or expired (HTTP {resp.status_code})"}
            
            elif cred_type == "instagram":
                resp = await client.get(
                    "https://www.instagram.com/accounts/edit/?__a=1&__d=dis",
                    headers={
                        "Cookie": f"sessionid={value}",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    }
                )
                if resp.status_code == 200:
                    return {"valid": True, "message": "✅ Valid — Instagram session is active"}
                else:
                    return {"valid": False, "message": f"❌ Invalid or expired (HTTP {resp.status_code})"}
            
            elif cred_type == "facebook":
                # Expect format: c_user;xs
                parts = value.split(";")
                if len(parts) < 2:
                    return {"valid": False, "message": "❌ Format error — expected 'c_user;xs'"}
                cookie_str = f"c_user={parts[0].strip()}; xs={parts[1].strip()}"
                resp = await client.get(
                    "https://www.facebook.com/me",
                    headers={
                        "Cookie": cookie_str,
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    },
                    follow_redirects=False
                )
                # If we get a redirect to a profile, it's valid
                if resp.status_code in [301, 302] and "/login" not in resp.headers.get("location", ""):
                    return {"valid": True, "message": "✅ Valid — Facebook session is active"}
                else:
                    return {"valid": False, "message": "❌ Invalid or expired — Facebook rejected these cookies"}
            
            else:
                return {"valid": False, "message": f"Unknown credential type: {cred_type}"}
                
    except httpx.TimeoutException:
        return {"valid": False, "message": "⏱ Validation timed out — platform may be blocking. Try saving and testing manually."}
    except Exception as e:
        return {"valid": False, "message": f"Validation error: {str(e)}"}


@router.post("/sessions/{session_id}/share")
async def share_session(session_id: str, request: Request):
    supabase, user_id = get_auth_client(request)
    # RLS ensures user can only update their own session
    res = supabase.table("research_sessions").update({"is_public": True}).eq("id", session_id).eq("user_id", user_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Session not found or permission denied")
    return {"success": True, "share_url": f"/?share={session_id}"}

@router.get("/public/sessions/{session_id}")
async def get_public_session(session_id: str):
    # This route bypasses the user JWT and uses the service/anon role
    # RLS policy must allow selecting messages where session is_public=true
    from api.utils.supabase import get_supabase_client
    supabase = get_supabase_client() # No token, acts as anon
    
    # First verify if session is public
    session_res = supabase.table("research_sessions").select("title, is_public").eq("id", session_id).execute()
    if not session_res.data or not session_res.data[0].get("is_public"):
        raise HTTPException(status_code=403, detail="This research session is private or does not exist.")
        
    res = supabase.table("messages").select("*").eq("session_id", session_id).order("created_at").execute()
    return {
        "title": session_res.data[0]["title"],
        "messages": res.data
    }
