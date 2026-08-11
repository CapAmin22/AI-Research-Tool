import os
import json
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from groq import Groq
from api.config import get_settings

router = APIRouter(prefix="/chat", tags=["Chat"])

class ChatRequest(BaseModel):
    message: str

def get_groq_client():
    settings = get_settings()
    api_key = settings.groq_api_key or os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="Groq API key not configured on Vercel.")
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

async def execute_tool_on_vm(tool_name: str, args: dict) -> str:
    settings = get_settings()
    url = f"{settings.vm_host.rstrip('/')}/api/microservice/execute_tool"
    headers = {"x-api-key": settings.vm_api_key}
    payload = {
        "tool_name": tool_name,
        "args": args
    }
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload, headers=headers, timeout=120.0)
            if resp.status_code != 200:
                return f"VM execution error: {resp.text}"
            return resp.json().get("output", "")
        except Exception as e:
            return f"Error contacting VM: {str(e)}"

@router.post("/{channel}")
async def chat_public(channel: str, req: ChatRequest):
    if channel not in ["youtube", "read webpage", "rss/atom", "web search"]:
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
            
            tool_output = await execute_tool_on_vm(tool_name, args)
                
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
