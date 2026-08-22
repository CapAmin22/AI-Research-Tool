import os
import json
import httpx
import re
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from openai import OpenAI
from api.config import get_settings
from api.routes.chat_linkedin import LINKEDIN_TOOLS

router = APIRouter(prefix="/chat", tags=["Chat"])

class ChatRequest(BaseModel):
    message: str
    channels: list[str] = []
    session_id: str | None = None

def get_nvidia_client():
    settings = get_settings()
    api_key = settings.nvidia_api_key or os.environ.get("NVIDIA_API_KEY") or os.environ.get("NVIDIA_API_KEY2")
    if not api_key:
        raise HTTPException(status_code=400, detail="NVIDIA API key not configured on Vercel.")
    return OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=api_key.strip()
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
    },
    {
        "type": "function",
        "function": {
            "name": "podcast_transcribe",
            "description": "Transcribe a podcast episode from a URL into searchable text. Works with YouTube, Spotify embeds, and direct audio URLs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The podcast episode URL"}
                },
                "required": ["url"],
            },
        },
    }
]

async def execute_search_web(query: str) -> str:
    try:
        # Bypass duckduckgo_search library which fails on Vercel IPs.
        # Use httpx to scrape the HTML endpoint directly.
        url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Origin": "https://duckduckgo.com",
            "Referer": "https://duckduckgo.com/",
        }
        data = {"q": query}
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, data=data, headers=headers, timeout=15.0)
            
            results = []
            import re
            pattern = r'<a class="result__url" href="([^"]+)".*?>(.*?)</a>.*?<a class="result__snippet[^>]*>(.*?)</a>'
            matches = re.findall(pattern, resp.text, re.IGNORECASE | re.DOTALL)
            
            for u, t, s in matches[:10]:
                u = u.strip()
                t = re.sub(r'<[^>]+>', '', t).strip()
                s = re.sub(r'<[^>]+>', '', s).strip()
                
                # Extract real URL from DDG redirect
                if u.startswith("//duckduckgo.com/l/?uddg="):
                    import urllib.parse
                    u = urllib.parse.unquote(u.split("uddg=")[1].split("&")[0])
                elif u.startswith("/l/?uddg="):
                    import urllib.parse
                    u = urllib.parse.unquote(u.split("uddg=")[1].split("&")[0])
                    
                results.append({"title": t, "url": u, "body": s})
                
            if not results:
                # Fallback to the VM if local Vercel execution fails entirely
                return await execute_tool_on_vm("search_web", {"query": query})
                
            return json.dumps(results)
    except Exception as e:
        # Fallback to VM on any network error
        return await execute_tool_on_vm("search_web", {"query": query})

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

@router.post("/multi")
async def chat_multi(req: ChatRequest, request: Request):
    vault_cookies = request.headers.get("x-vault-cookies", "")
    access_token = request.headers.get("Authorization", "").replace("Bearer ", "")
    
    supabase = None
    user_id = None
    if access_token:
        try:
            from api.utils.supabase import get_supabase_client
            supabase = get_supabase_client(access_token)
            user_response = supabase.auth.get_user(access_token)
            user_id = user_response.user.id
        except Exception as e:
            print(f"Supabase init error: {e}")
            
    # Ensure session_id exists if authenticated
    if supabase and user_id and not req.session_id:
        title = req.message[:50] + "..." if len(req.message) > 50 else req.message
        try:
            res = supabase.table("research_sessions").insert({"user_id": user_id, "title": title}).execute()
            req.session_id = res.data[0]["id"]
        except Exception as e:
            print(f"Failed to create session: {e}")
            
    # Fetch vault credentials from Supabase
    if supabase and user_id:
        try:
            vault_res = supabase.table("user_vault").select("*").eq("user_id", user_id).execute()
            if vault_res.data:
                vault_cookies = json.dumps(vault_res.data[0])
        except Exception as e:
            print(f"Failed to fetch vault: {e}")
    
    # ALL channels are now active — social channels route through search_web with site-specific queries
    ALL_CHANNELS = [
        "youtube", "github", "podcast transcription", "linkedin",
        "twitter / x", "reddit", "facebook", "instagram", "no-web chat"
    ]
    
    # Filter selected channels
    selected_channels = [c.lower().strip() for c in req.channels if c.lower().strip() in ALL_CHANNELS]
    no_web = "no-web chat" in selected_channels
    
    # ── Dynamic Tools Logic ──
    tool_names_added = set()
    tools_to_use = []
    
    def add_tool(name):
        if name not in tool_names_added:
            for t in PUBLIC_TOOLS:
                if t["function"]["name"] == name:
                    tools_to_use.append(t)
                    tool_names_added.add(name)
                    break
    
    # Determine if any specialized agent is selected
    special_agents = [c for c in selected_channels if c != "no-web chat"]
    is_special_agent_active = len(special_agents) > 0
    
    # Universal Base Tools — always present UNLESS no-web chat is selected OR a special agent is active
    if not no_web and not is_special_agent_active:
        add_tool("search_web")
        add_tool("read_webpage")
        add_tool("read_rss")
        
    # Agentic Memory Tool - always present if authenticated
    if supabase and user_id:
        # Define the tool manually since it's not in public_tools list yet
        MEMORY_TOOL = {
            "type": "function",
            "function": {
                "name": "save_to_memory",
                "description": "CRITICAL: You MUST use this tool to save important research findings (like prices, stats, dates) or user preferences to your long-term memory. This allows you to remember them across different chat sessions.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "fact": {"type": "string", "description": "The specific fact, price, or data point to remember."},
                        "category": {"type": "string", "description": "Category (e.g., 'Commodity Price', 'Startup Info', 'Preference')"}
                    },
                    "required": ["fact"]
                }
            }
        }
        tools_to_use.append(MEMORY_TOOL)
    
    # Channel-specific tools
    if "youtube" in selected_channels:
        add_tool("youtube_info")
        add_tool("youtube_subtitles")
    if "podcast transcription" in selected_channels:
        add_tool("podcast_transcribe")
    if "linkedin" in selected_channels:
        tools_to_use.extend(LINKEDIN_TOOLS)
    if "twitter / x" in selected_channels:
        tools_to_use.append({"type": "function", "function": {"name": "search_twitter", "description": "Search Twitter/X for posts or profiles.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}})
    if "reddit" in selected_channels:
        tools_to_use.append({"type": "function", "function": {"name": "search_reddit", "description": "Search Reddit for posts or subreddits.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}})
    if "facebook" in selected_channels:
        tools_to_use.append({"type": "function", "function": {"name": "search_facebook", "description": "Search Facebook for posts or pages.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}})
    if "instagram" in selected_channels:
        tools_to_use.append({"type": "function", "function": {"name": "search_instagram", "description": "Search Instagram for posts or profiles.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}})
            
    nvidia_client = get_nvidia_client()
    
    # ── System prompt logic ──
    if no_web:
        system_content = "You are a highly intelligent AI. You have access to long-term memory. DO NOT say you cannot remember past interactions; if you do not see past memories in your prompt, just say you haven't saved any yet. Answer using your internal knowledge."
        tools_to_use = None
    else:
        # Default system prompt
        system_content = "You are a highly intelligent AI Research Assistant. You have a long-term memory system. DO NOT say you cannot remember past interactions; if relevant memories exist, they will be provided to you. You MUST proactively use the `save_to_memory` tool to store important facts like prices or stats that the user might ask about later."
        
        # Try to fetch dynamic prompt from DB
        if supabase:
            try:
                prompt_res = supabase.table("system_prompts").select("prompt_text").eq("is_active", True).execute()
                if prompt_res.data and len(prompt_res.data) > 0:
                    system_content = prompt_res.data[0]["prompt_text"]
            except Exception as e:
                print(f"Failed to fetch system prompt: {e}")
                
        # Force memory instructions
        system_content += "\n\nCRITICAL DIRECTIVE: You have a long-term memory system via the `save_to_memory` tool. DO NOT say you cannot remember past interactions; if relevant memories exist, they are provided to you. You MUST proactively use the `save_to_memory` tool to store important facts like prices, startup stats, or user preferences that might be asked about later."
        
        # Build platform-specific instructions for social channels
        social_instructions = ""
        special_channels = [c.title() for c in selected_channels if c != "no-web chat"]
        channels_str = ", ".join(special_channels) if special_channels else "Web Search, Reading, and RSS"
        
        if "reddit" in selected_channels:
            social_instructions += "\n\nREDDIT RESEARCH: Use `search_web` with queries like 'site:reddit.com <topic>' to find Reddit discussions, threads, and community opinions. Use `read_webpage` to read specific Reddit thread URLs for deeper context."
        if "twitter / x" in selected_channels:
            social_instructions += "\n\nTWITTER/X RESEARCH: Use `search_web` with queries like 'site:x.com <topic>' or 'site:twitter.com <topic>' to find tweets, threads, and trending discussions. Include the tweet author handle and date."
        if "instagram" in selected_channels:
            social_instructions += "\n\nINSTAGRAM RESEARCH: Use `search_web` with queries like 'site:instagram.com <topic>' to find public Instagram posts and profiles. Note: Instagram content is limited to public profiles."
        if "facebook" in selected_channels:
            social_instructions += "\n\nFACEBOOK RESEARCH: Use `search_web` with queries like 'site:facebook.com <topic>' to find public Facebook posts, pages, and groups."
        
        system_content = f"""You are a highly intelligent Research Assistant with access to the following specialized domains: {channels_str}. You must first thoroughly understand the user's request. Then, use your available tools to perform research across these domains. Finally, present the results to the user.

You MUST strictly adhere to the following rules:
1. Use Markdown tables wherever possible to display data.
2. Use bullet points for takeaways.
3. Never hallucinate data. If you cannot find the data, say so.
4. To use a tool, use the standard tool calling API. DO NOT output XML tags like <function=...> in your text.
5. If asked about trending videos or general YouTube searches, you MUST invoke the `search_web` tool immediately.
6. EVERY fact or news item you present MUST include a verifiable source URL. Use `read_webpage` to verify and extract details from URLs found via `search_web`.

DEEP RESEARCH WORKFLOW:
When performing research, follow this workflow:
Step 1: Use `search_web` to find relevant results with verifiable URLs.
Step 2: Use `read_webpage` on the most relevant URLs to extract full article content and verify facts.
Step 3: Synthesize the verified information into a well-structured response with clickable source links.

NEWS & RESEARCH SOURCING GUIDELINES:
When asked for news or current events, gather information from the widest possible range of credible sources:
- For India: Times of India, NDTV, The Hindu, Indian Express, Hindustan Times, Economic Times, Mint, Business Standard, Deccan Herald.
- For USA: AP News, Reuters, CNN, NYT, Washington Post, Fox News, NPR, Bloomberg, WSJ.
- For UK: BBC, The Guardian, The Telegraph, Sky News, Financial Times.
- For Global: Reuters, AP, BBC World, Al Jazeera, France24, DW News.
- For Technology: TechCrunch, The Verge, Ars Technica, Wired.
- For Business/Finance: Bloomberg, Reuters, CNBC, Financial Times.

When using `search_web` for news, make MULTIPLE search queries to triangulate coverage. Then synthesize with source attribution and verifiable links.

When using `read_rss`, if a feed returns a 403 error, immediately fall back to `search_web` to find the same information.

ALWAYS include the source name, publication time, and a clickable URL alongside each item.{social_instructions}"""
        if len(tools_to_use) == 0:
            tools_to_use = None

    # -- Inject Agentic Memory --
    memory_context = ""
    if supabase and user_id:
        try:
            from api.utils.rag import search_memory
            memories = await search_memory(req.message, access_token, limit=3)
            if memories:
                memory_context = "\n\n### PAST MEMORIES (LONG-TERM)\nYou have retrieved the following relevant facts from your long-term memory about the user or their research topics:\n"
                for m in memories:
                    memory_context += f"- {m['content']}\n"
                memory_context += "Use these memories to inform your answer if they are relevant."
                system_content += memory_context
        except Exception as e:
            print(f"Memory search error: {e}")

    messages = [
        {"role": "system", "content": system_content}
    ]
    
    # Load past messages from Supabase if session exists
    if supabase and req.session_id:
        try:
            res = supabase.table("messages").select("*").eq("session_id", req.session_id).order("created_at").execute()
            for msg in res.data:
                # Basic mapping to OpenAI format
                messages.append({"role": msg["role"], "content": msg["content"]})
        except Exception as e:
            print(f"Error loading chat history: {e}")
            
    # Add the new user message
    messages.append({"role": "user", "content": req.message})
    
    # Save the user message to Supabase
    if supabase and req.session_id:
        try:
            supabase.table("messages").insert({
                "session_id": req.session_id,
                "role": "user",
                "content": req.message
            }).execute()
        except Exception as e:
            print(f"Error saving user message: {e}")
    
    def call_llm(messages_list, disable_tools=False):
        try:
            kwargs = {
                "model": "nvidia/nemotron-3-ultra-550b-a55b",
                "messages": messages_list,
                "temperature": 1,
                "top_p": 0.95,
                "max_tokens": 4096
            }
            if tools_to_use and not disable_tools:
                kwargs["tools"] = tools_to_use
                
            response = nvidia_client.chat.completions.create(**kwargs)
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
        scraped_data = []
        max_iterations = 5
        
        for iteration in range(max_iterations):
            # On the last iteration, disable tools to force a final text answer
            disable_tools = (iteration == max_iterations - 1)
            
            if disable_tools:
                messages.append({
                    "role": "system",
                    "content": "You have exhausted your tool call attempts. You MUST provide a final text summary to the user now based on the data gathered. Do NOT attempt to use tools."
                })
                
            response_message = call_llm(messages, disable_tools=disable_tools)
            
            if disable_tools or not response_message.tool_calls:
                # Agent provided a text response, or we forced it to stop
                final_reply = response_message.content or "The assistant reached the maximum tool attempts but returned empty text. Please view the raw data below."
                
                # Save assistant response to Supabase
                if supabase and req.session_id:
                    try:
                        supabase.table("messages").insert({
                            "session_id": req.session_id,
                            "role": "assistant",
                            "content": final_reply,
                            "raw_data": scraped_data
                        }).execute()
                    except Exception as e:
                        print(f"Error saving assistant message: {e}")
                        
                return {
                    "reply": final_reply,
                    "data": scraped_data if scraped_data else None,
                    "session_id": req.session_id
                }
                
            messages.append(response_message.model_dump(exclude_unset=True))
            
            for tool_call in response_message.tool_calls:
                args = {}
                try:
                    args = json.loads(tool_call.function.arguments)
                except:
                    pass
                
                tool_name = tool_call.function.name
                
                if tool_name == "search_web":
                    tool_output = await execute_search_web(args.get("query", ""))
                elif tool_name == "save_to_memory" and supabase and user_id:
                    try:
                        from api.utils.rag import store_document
                        success = await store_document(
                            content=args.get("fact", ""),
                            metadata={"category": args.get("category", "")},
                            token=access_token
                        )
                        tool_output = "Fact saved to long-term memory successfully." if success else "Failed to save to memory (OpenAI API key missing?)."
                    except Exception as e:
                        tool_output = f"Error saving memory: {e}"
                elif tool_name in ["get_person_profile", "search_linkedin_jobs", "search_linkedin_posts", "get_company_profile", "send_linkedin_connection", "send_linkedin_message"]:
                    tool_output = await execute_tool_on_vm(f"linkedin.{tool_name}", args, vault_cookies)
                elif tool_name in ["search_twitter", "search_reddit", "search_facebook", "search_instagram"]:
                    prefix = tool_name.split("_")[1] # e.g. "twitter"
                    tool_output = await execute_tool_on_vm(f"{prefix}.{tool_name}", args, vault_cookies)
                else:
                    tool_output = await execute_tool_on_vm(tool_name, args, vault_cookies)
                    
                    if "AUTH_REQUIRED" in tool_output:
                        return {"auth_required": True, "reply": tool_output, "data": scraped_data}
                    
                if len(tool_output) > 10000:
                    tool_output = tool_output[:10000] + "... [TRUNCATED]"
                    
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "content": tool_output
                })
                
                scraped_data.append({"tool": tool_name, "output": tool_output})
                
        # Fallback if loop exits
        final_reply = "The assistant reached the maximum number of tool execution steps."
        if supabase and req.session_id:
            try:
                supabase.table("messages").insert({
                    "session_id": req.session_id,
                    "role": "assistant",
                    "content": final_reply,
                    "raw_data": scraped_data
                }).execute()
            except Exception as e:
                pass
                
        return {
            "reply": final_reply,
            "data": scraped_data,
            "session_id": req.session_id
        }
        
    except Exception as e:
        if "rate_limit" in str(e) or "429" in str(e):
            return {"reply": "The AI is currently experiencing high traffic (Rate Limit Reached). Please try again in a few minutes.", "data": []}
        # Instead of throwing a 500, return the error gracefully so the UI displays it.
        return {"reply": f"**Backend Error:** {str(e)}", "data": []}
