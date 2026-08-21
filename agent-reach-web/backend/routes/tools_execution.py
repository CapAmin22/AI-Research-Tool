import os
import json
import subprocess
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import Any, Dict
from config import get_settings
from services import agent_reach

router = APIRouter(prefix="/api/microservice", tags=["Microservice"])

class ToolExecutionRequest(BaseModel):
    tool_name: str
    args: Dict[str, Any]
    
def verify_api_key(x_api_key: str = Header(None)):
    settings = get_settings()
    # Use the api_secret_key from config as the auth token
    if not x_api_key or x_api_key != settings.api_secret_key:
        raise HTTPException(status_code=401, detail="Unauthorized")

def run_mcporter(tool_name: str, args: dict) -> str:
    try:
        cmd = ["mcporter", "call", tool_name]
        for k, v in args.items():
            cmd.append(f"{k}={v}")
            
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if res.returncode != 0:
            return f"Error executing {tool_name}: {res.stderr}"
            
        return res.stdout
    except Exception as e:
        return f"System error calling {tool_name}: {str(e)}"

@router.post("/execute_tool", dependencies=[Depends(verify_api_key)])
async def execute_tool(req: ToolExecutionRequest, x_vault_cookies: str = Header(None, alias="X-Vault-Cookies")):
    tool_name = req.tool_name
    args = req.args
    
    cookies = {}
    if x_vault_cookies:
        try:
            cookies = json.loads(x_vault_cookies)
        except:
            pass
            
    try:
        if tool_name.startswith("linkedin."):
            li_at = cookies.get("linkedin_li_at")
            if not li_at:
                return {"output": "AUTH_REQUIRED: LinkedIn session cookie (li_at) is missing. Please authenticate."}
                
            args["cookie"] = li_at
            output = run_mcporter(tool_name, args)
            if "unauthorized" in output.lower() or "captcha" in output.lower() or "401" in output:
                return {"output": "AUTH_REQUIRED: LinkedIn cookie is expired or a CAPTCHA was triggered."}
            return {"output": output}
            
        elif tool_name == "youtube_info":
            res = await agent_reach.youtube_info(args["url"])
            return {"output": json.dumps(res, indent=2)}
            
        elif tool_name == "youtube_subtitles":
            res = await agent_reach.youtube_subtitles(args["url"], "en")
            return {"output": json.dumps(res, indent=2)}
            
        elif tool_name == "read_webpage":
            res = await agent_reach.read_webpage(args["url"])
            return {"output": json.dumps(res, indent=2)}
            
        elif tool_name == "read_rss":
            res = await agent_reach.read_rss(args["url"], limit=10)
            return {"output": json.dumps(res, indent=2)}
            
        elif tool_name == "search_web":
            try:
                from duckduckgo_search import DDGS
                results = DDGS().text(args.get("query", ""), max_results=5)
                if not results:
                    return {"output": "Search returned no results."}
                return {"output": json.dumps(results, indent=2)}
            except Exception as e:
                return {"output": f"Search error: {str(e)}"}
            
        elif tool_name == "podcast_transcribe":
            # Use yt-dlp to extract subtitles/transcript from a podcast or audio URL
            podcast_url = args.get("url", "")
            try:
                res = subprocess.run(
                    ["yt-dlp", "--write-auto-sub", "--skip-download", "--sub-lang", "en",
                     "--print", "%(subtitles)j", podcast_url],
                    capture_output=True, text=True, timeout=120
                )
                if res.returncode == 0 and res.stdout.strip():
                    return {"output": res.stdout.strip()}
                # Fallback: just get info
                res2 = subprocess.run(
                    ["yt-dlp", "-j", podcast_url],
                    capture_output=True, text=True, timeout=120
                )
                if res2.returncode == 0:
                    return {"output": res2.stdout.strip()}
                return {"output": f"Could not transcribe podcast. yt-dlp error: {res.stderr}"}
            except Exception as e:
                return {"output": f"Podcast transcription error: {str(e)}"}
            
        else:
            raise HTTPException(status_code=400, detail=f"Unknown tool: {tool_name}")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
