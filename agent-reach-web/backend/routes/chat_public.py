import os
import json
import subprocess
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI
from config import get_settings
from services import agent_reach

router = APIRouter(prefix="/api/chat", tags=["Chat"])

class ChatRequest(BaseModel):
    message: str

def get_nvidia_client():
    settings = get_settings()
    api_key = settings.nvidia_api_key or os.environ.get("NVIDIA_API_KEY") or os.environ.get("NVIDIA_API_KEY2")
    if not api_key:
        raise HTTPException(status_code=400, detail="NVIDIA API key not configured on VM.")
    return OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=api_key
    )

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
            
    client = get_nvidia_client()
    
    messages = [
        {"role": "system", "content": f"You are a highly intelligent {channel} Research Assistant. You must first thoroughly understand the user's request. Then, use your available tools to perform research. Finally, present the results to the user in a format highly appropriate for this specific channel. You MUST strictly adhere to the following rules:\n1. Use Markdown tables wherever possible to display data.\n2. Use bullet points for takeaways.\n3. Never hallucinate data. If you cannot find the data, say so.\n4. To use a tool, use the standard tool calling API. DO NOT output XML tags like <function=...> in your text."},
        {"role": "user", "content": req.message}
    ]
    
    try:
        response = client.chat.completions.create(
            model="nvidia/nemotron-3-ultra-550b-a55b",
            messages=messages,
            tools=PUBLIC_TOOLS,
            temperature=1,
            top_p=0.95,
            max_tokens=4096,
            extra_body={"chat_template_kwargs":{"enable_thinking":True},"reasoning_budget":4096}
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
            model="nvidia/nemotron-3-ultra-550b-a55b",
            messages=messages,
            tools=PUBLIC_TOOLS,
            temperature=1,
            top_p=0.95,
            max_tokens=4096,
            extra_body={"chat_template_kwargs":{"enable_thinking":True},"reasoning_budget":4096}
        )
        
        return {
            "reply": final_response.choices[0].message.content,
            "data": scraped_data
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
