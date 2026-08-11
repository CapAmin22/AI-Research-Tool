import os
import json
import subprocess
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from groq import Groq
from config import get_settings
from services import agent_reach

router = APIRouter(prefix="/api/chat", tags=["Chat"])

class ChatRequest(BaseModel):
    message: str

def get_groq_client():
    settings = get_settings()
    api_key = settings.groq_api_key
    if not api_key:
        try:
            with open(os.path.expanduser("~/.agent-reach/config.json"), "r") as f:
                data = json.load(f)
                api_key = data.get("groq-key") or data.get("groq_key")
        except:
            pass
    if not api_key:
        raise HTTPException(status_code=400, detail="Groq API key not configured. Please add it in Settings.")
    return Groq(api_key=api_key)

PUBLIC_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "youtube_info",
            "description": "Fetch metadata (title, description, views) for a YouTube video.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The full YouTube video URL"}
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "youtube_subtitles",
            "description": "Download transcripts/subtitles for a YouTube video.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The full YouTube video URL"}
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_webpage",
            "description": "Read any public webpage URL and extract its text content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The webpage URL"}
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_rss",
            "description": "Fetch the latest posts from an RSS or Atom feed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The RSS feed URL"}
                },
                "required": ["url"],
            },
        },
    }
]

@router.post("/{channel}")
async def chat_public(channel: str, req: ChatRequest):
    # Route only specific public channels here. LinkedIn is handled in chat_linkedin.py
    if channel not in ["youtube", "read webpage", "rss/atom", "web search"]:
        # If it's a channel we don't have python wrappers for yet, return generic response
        if channel != "linkedin":
            return {"reply": f"The {channel} agent is not fully implemented yet.", "data": []}
            
    client = get_groq_client()
    
    messages = [
        {"role": "system", "content": f"You are a highly intelligent {channel} Research Assistant. You can scrape data using your tools. Always be concise and provide actionable insights. Do not hallucinate data; use your tools to fetch real information."},
        {"role": "user", "content": req.message}
    ]
    
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            tools=PUBLIC_TOOLS,
            tool_choice="auto",
            max_tokens=4096
        )
        
        response_message = response.choices[0].message
        
        if not response_message.tool_calls:
            return {"reply": response_message.content, "data": None}
            
        scraped_data = []
        messages.append(response_message.model_dump(exclude_unset=True))
        
        for tool_call in response_message.tool_calls:
            args = json.loads(tool_call.function.arguments)
            tool_name = tool_call.function.name
            
            tool_output = ""
            if tool_name == "youtube_info":
                res = await agent_reach.youtube_info(args["url"])
                tool_output = json.dumps(res, indent=2)
            elif tool_name == "youtube_subtitles":
                res = await agent_reach.youtube_subtitles(args["url"], "en")
                tool_output = json.dumps(res, indent=2)
            elif tool_name == "read_webpage":
                res = await agent_reach.read_webpage(args["url"])
                tool_output = json.dumps(res, indent=2)
            elif tool_name == "read_rss":
                res = await agent_reach.read_rss(args["url"], limit=10)
                tool_output = json.dumps(res, indent=2)
            else:
                tool_output = f"Unknown tool {tool_name}"
                
            # Truncate output to avoid exceeding context window limits
            if len(tool_output) > 10000:
                tool_output = tool_output[:10000] + "... [TRUNCATED]"
                
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_name,
                "content": tool_output
            })
            
            scraped_data.append({"tool": tool_name, "output": tool_output})
            
        final_response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            tools=PUBLIC_TOOLS,
            max_tokens=4096
        )
        
        return {
            "reply": final_response.choices[0].message.content,
            "data": scraped_data
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
