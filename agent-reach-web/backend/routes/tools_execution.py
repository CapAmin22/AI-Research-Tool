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
async def execute_tool(req: ToolExecutionRequest):
    tool_name = req.tool_name
    args = req.args
    
    try:
        if tool_name.startswith("linkedin."):
            output = run_mcporter(tool_name, args)
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
            
        else:
            raise HTTPException(status_code=400, detail=f"Unknown tool: {tool_name}")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
