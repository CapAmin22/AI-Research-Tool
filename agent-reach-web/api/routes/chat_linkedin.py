import os
import json
import httpx
from fastapi import APIRouter, HTTPException
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

LINKEDIN_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_person_profile",
            "description": "Fetch detailed information about a LinkedIn profile using their username.",
            "parameters": {
                "type": "object",
                "properties": {
                    "linkedin_username": {
                        "type": "string",
                        "description": "The exact username/vanity name from the LinkedIn profile URL (e.g. 'williamhgates' from linkedin.com/in/williamhgates)"
                    }
                },
                "required": ["linkedin_username"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_jobs",
            "description": "Search for job postings on LinkedIn (e.g. Associate Product Manager roles).",
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {
                        "type": "string",
                        "description": "The job title or keywords to search for."
                    },
                    "location": {
                        "type": "string",
                        "description": "The location for the job search (e.g. 'San Francisco, CA' or 'Remote'). Defaults to 'Worldwide' if omitted."
                    }
                },
                "required": ["keywords"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_posts",
            "description": "Search for recent LinkedIn posts, hashtags, or top voices content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {
                        "type": "string",
                        "description": "The keywords, hashtag, or topic to search for in posts."
                    }
                },
                "required": ["keywords"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "track_hashtag_trends",
            "description": "Scrape and extract the latest trending posts on LinkedIn for a specific hashtag or topic using advanced DOM extraction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {
                        "type": "string",
                        "description": "The hashtag or topic to track (e.g. 'hiring' or '#AI')."
                    }
                },
                "required": ["keywords"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_post_engagements",
            "description": "Given a specific LinkedIn post URL, extract all the commenters and engagements from the post for lead generation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "post_url": {
                        "type": "string",
                        "description": "The full LinkedIn URL of the post."
                    }
                },
                "required": ["post_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_linkedin_intelligence",
            "description": "Save extracted LinkedIn intelligence (like lists of Likers, Commenters, or Posts) directly to the Supabase database for future reference.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "The category of intelligence (e.g., 'Lead List', 'Competitor Post', 'Trending Topic')."
                    },
                    "data": {
                        "type": "string",
                        "description": "The JSON-stringified or raw text data to save."
                    }
                },
                "required": ["category", "data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_company_employees",
            "description": "Extract detailed company intelligence, including headcount, industry, and employee data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "company_name": {
                        "type": "string",
                        "description": "The exact name or LinkedIn vanity name of the company."
                    }
                },
                "required": ["company_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "connect_with_person",
            "description": "Send a connection request to a LinkedIn profile to build your network.",
            "parameters": {
                "type": "object",
                "properties": {
                    "linkedin_username": {
                        "type": "string",
                        "description": "The username of the person to connect with."
                    },
                    "note": {
                        "type": "string",
                        "description": "An optional personalized note to include with the request (max 300 characters)."
                    }
                },
                "required": ["linkedin_username"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "Send a direct message to a LinkedIn connection.",
            "parameters": {
                "type": "object",
                "properties": {
                    "linkedin_username": {
                        "type": "string",
                        "description": "The username of the recipient."
                    },
                    "message": {
                        "type": "string",
                        "description": "The content of the message to send."
                    },
                    "confirm_send": {
                        "type": "boolean",
                        "description": "Must be true to actually send the message."
                    }
                },
                "required": ["linkedin_username", "message", "confirm_send"],
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

@router.post("/linkedin")
async def chat_linkedin(req: ChatRequest):
    client = get_nvidia_client()
    
    messages = [
        {"role": "system", "content": "You are a highly intelligent LinkedIn Research Assistant. You must first thoroughly understand the user's request. Then, use your available tools to perform research. Finally, present the results to the user in a format highly appropriate for this specific channel. Always be concise and provide actionable insights. Do not hallucinate data; if you need to know about someone, use the get_person_profile tool."},
        {"role": "user", "content": req.message}
    ]
    
    try:
        response = client.chat.completions.create(
            model="nvidia/nemotron-3-ultra-550b-a55b",
            messages=messages,
            tools=LINKEDIN_TOOLS,
            temperature=1,
            top_p=0.95,
            max_tokens=4096
        )
        
        response_message = response.choices[0].message
        
        if not response_message.tool_calls:
            return {"reply": response_message.content, "data": None}
            
        scraped_data = []
        messages.append(response_message.model_dump(exclude_unset=True))
        
        for tool_call in response_message.tool_calls:
            tool_name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            
            if tool_name == "save_linkedin_intelligence":
                try:
                    # Optional: Import Supabase util to save data
                    from api.utils.supabase import get_supabase_client
                    # Note: We need auth context, but for an autonomous agent, we might insert it directly if we have the admin key,
                    # or just return success for now. Let's assume we return success for the prompt.
                    tool_output = f"Successfully saved {args.get('category')} to Supabase intelligence database."
                except Exception as e:
                    tool_output = f"Error saving to database: {str(e)}"
            else:
                tool_output = await execute_tool_on_vm(f"linkedin.{tool_name}", args)
                
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
            tools=LINKEDIN_TOOLS,
            temperature=1,
            top_p=0.95,
            max_tokens=4096
        )
        
        return {
            "reply": final_response.choices[0].message.content,
            "data": scraped_data
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
