import json
import os
import subprocess
import zipfile
import shutil
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/settings", tags=["Settings"])

CONFIG_PATH = os.path.expanduser("~/.agent-reach/config.json")

class SettingsPayload(BaseModel):
    groq_key: Optional[str] = None
    twitter_auth_token: Optional[str] = None
    twitter_ct0: Optional[str] = None
    reddit_cookie: Optional[str] = None
    github_token: Optional[str] = None
    proxy: Optional[str] = None

@router.get("/")
async def get_settings():
    """Return which settings are configured (boolean flags) without leaking secrets."""
    status = {
        "groq_key": False,
        "twitter_auth_token": False,
        "twitter_ct0": False,
        "reddit_cookie": False,
        "github_token": False,
        "proxy": False
    }
    
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
                if data.get("groq-key"):
                    status["groq_key"] = True
                if data.get("twitter_auth_token"):
                    status["twitter_auth_token"] = True
                if data.get("twitter_ct0"):
                    status["twitter_ct0"] = True
                if data.get("reddit_cookie"):
                    status["reddit_cookie"] = True
                if data.get("proxy"):
                    status["proxy"] = True
        except:
            pass
            
    # Check GitHub auth status
    try:
        res = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
        if "Logged in to github.com" in res.stdout or "Logged in to github.com" in res.stderr:
            status["github_token"] = True
    except:
        pass
        
    return status

@router.post("/")
async def update_settings(payload: SettingsPayload):
    """Save new settings securely."""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    
    data = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
        except:
            pass
            
    # Update values if provided
    if payload.groq_key:
        data["groq-key"] = payload.groq_key
    if payload.twitter_auth_token:
        data["twitter_auth_token"] = payload.twitter_auth_token
    if payload.twitter_ct0:
        data["twitter_ct0"] = payload.twitter_ct0
    if payload.reddit_cookie:
        data["reddit_cookie"] = payload.reddit_cookie
    if payload.proxy:
        data["proxy"] = payload.proxy
        
    # Write back config
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write config: {str(e)}")
        
    # Handle GitHub separately
    if payload.github_token:
        try:
            # Login to GitHub using the provided token
            process = subprocess.Popen(
                ["gh", "auth", "login", "--with-token"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = process.communicate(input=payload.github_token)
            if process.returncode != 0:
                raise Exception(stderr)
        except Exception as e:
            # We don't fail the whole request, but we could log it
            pass
            
    return {"status": "success"}

@router.post("/upload-linkedin")
async def upload_linkedin_profile(file: UploadFile = File(...)):
    """Accept a ZIP file containing the ~/.linkedin-mcp/profile folder and extract it."""
    if not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="Must be a .zip file")
        
    temp_zip_path = f"/tmp/{file.filename}"
    target_dir = os.path.expanduser("~/.linkedin-mcp/profile")
    
    # Save zip
    with open(temp_zip_path, "wb") as f:
        content = await file.read()
        f.write(content)
        
    # Create target dir
    os.makedirs(target_dir, exist_ok=True)
    
    # Extract
    try:
        with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
            zip_ref.extractall(target_dir)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract: {str(e)}")
        
    # Clean up
    os.remove(temp_zip_path)
    
    return {"status": "success", "message": "LinkedIn profile synced successfully."}
