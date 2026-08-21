import os
import json
import httpx
import re
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from openai import OpenAI
from api.config import get_settings

router = APIRouter(prefix="/chat", tags=["Chat"])

class ChatRequest(BaseModel):
    message: str

def get_nvidia_client():
    settings = get_settings()
    api_key = settings.nvidia_api_key or os.environ.get("NVIDIA_API_KEY") or os.environ.get("NVIDIA_API_KEY2")
    if not api_key:
        raise HTTPException(status_code=400, detail="NVIDIA API key not configured on Vercel.")
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
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web for current information (e.g. trending videos, news). Always use this instead of read_webpage for dynamic search pages.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"}
                },
                "required": ["query"],
            },
        },
    }
]

async def execute_search_web(query: str) -> str:
    try:
        from duckduckgo_search import DDGS
        results = DDGS().text(query, max_results=5)
        if not results:
            return "Search failed: No results found."
        return json.dumps(results)
    except Exception as e:
        return f"Search error: {str(e)}"

async def execute_tool_on_vm(tool_name: str, args: dict, vault_cookies: str = "") -> str:
    settings = get_settings()
    url = f"{settings.vm_host.rstrip('/')}/api/microservice/execute_tool"
    headers = {"x-api-key": settings.vm_api_key}
    if vault_cookies:
        headers["x-vault-cookies"] = vault_cookies
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
async def chat_public(channel: str, req: ChatRequest, request: Request):
    vault_cookies = request.headers.get("x-vault-cookies", "")
    if channel not in ["youtube", "read webpage", "rss/atom", "web search"]:
        if channel != "linkedin":
            return {"reply": f"The {channel} agent is not fully implemented yet.", "data": []}
            
    nvidia_client = get_nvidia_client()
    
    messages = [
        {"role": "system", "content": f"You are a highly intelligent {channel} Research Assistant. You must first thoroughly understand the user's request. Then, use your available tools to perform research. Finally, present the results to the user in a format highly appropriate for this specific channel. You MUST strictly adhere to the following rules:\n1. Use Markdown tables wherever possible to display data.\n2. Use bullet points for takeaways.\n3. Never hallucinate data. If you cannot find the data, say so.\n4. To use a tool, use the standard tool calling API. DO NOT output XML tags like <function=...> in your text.\n5. If asked about trending videos or general YouTube searches, you MUST invoke the `search_web` tool immediately to search the web (e.g. 'top trending youtube videos today'). NEVER use `read_webpage` on youtube.com dynamic pages as they are blocked."},
        {"role": "user", "content": req.message}
    ]
    
    def call_llm(messages_list):
        try:
            response = nvidia_client.chat.completions.create(
                model="nvidia/nemotron-3-ultra-550b-a55b",
                messages=messages_list,
                tools=PUBLIC_TOOLS,
                temperature=1,
                top_p=0.95,
                max_tokens=4096,
                extra_body={"chat_template_kwargs":{"enable_thinking":True},"reasoning_budget":4096}
            )
            return response.choices[0].message
        except Exception as e:
            if "rate_limit" in str(e) or "429" in str(e):
                class MockMessageRateLimit:
                    def __init__(self):
                        self.content = "The AI is currently experiencing high traffic (Rate Limit Reached). Please try again in a few minutes."
                        self.tool_calls = None
                    def model_dump(self, **kwargs):
                        return {"role": "assistant", "content": self.content}
                return MockMessageRateLimit()
            else:
                raise e

    try:
        response_message = call_llm(messages)
        
        if not response_message.tool_calls:
            return {"reply": response_message.content, "data": None}
            
        scraped_data = []
        messages.append(response_message.model_dump(exclude_unset=True))
        
        for tool_call in response_message.tool_calls:
            args = json.loads(tool_call.function.arguments)
            tool_name = tool_call.function.name
            
            if tool_name == "search_web":
                tool_output = await execute_search_web(args.get("query", ""))
            else:
                tool_output = await execute_tool_on_vm(tool_name, args, vault_cookies)
                
                # Intercept authentication blockers from the VM
                if "AUTH_REQUIRED" in tool_output:
                    return {"auth_required": True, "reply": tool_output, "data": []}
                
            if len(tool_output) > 10000:
                tool_output = tool_output[:10000] + "... [TRUNCATED]"
                
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_name,
                "content": tool_output
            })
            
            scraped_data.append({"tool": tool_name, "output": tool_output})
            
        final_response_message = call_llm(messages)
        
        return {
            "reply": final_response_message.content or "The assistant returned empty text after using the tools. Please try again.",
            "data": scraped_data
        }
        
    except Exception as e:
        if "rate_limit" in str(e) or "429" in str(e):
            return {"reply": "The AI is currently experiencing high traffic (Rate Limit Reached). Please try again in a few minutes.", "data": []}
        raise HTTPException(status_code=500, detail=str(e))
