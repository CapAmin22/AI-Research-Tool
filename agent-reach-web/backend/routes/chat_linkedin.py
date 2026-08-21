import os
import json
import subprocess
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI
from config import get_settings

router = APIRouter(prefix="/api/chat", tags=["Chat"])

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
    }
]

def run_mcporter(tool_name: str, args: dict) -> str:
    """Run an mcporter command and return the output."""
    try:
        # e.g. mcporter call linkedin.get_person_profile linkedin_username="xxx"
        cmd = ["mcporter", "call", f"linkedin.{tool_name}"]
        for k, v in args.items():
            cmd.append(f"{k}={v}")
            
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if res.returncode != 0:
            return f"Error executing {tool_name}: {res.stderr}"
            
        return res.stdout
    except Exception as e:
        return f"System error calling {tool_name}: {str(e)}"

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
            max_tokens=4096,
            extra_body={"chat_template_kwargs":{"enable_thinking":True},"reasoning_budget":4096}
        )
        
        response_message = response.choices[0].message
        
        # If no tool calls, return response directly
        if not response_message.tool_calls:
            return {"reply": response_message.content, "data": None}
            
        # Execute tool calls
        scraped_data = []
        messages.append(response_message.model_dump(exclude_unset=True))
        
        for tool_call in response_message.tool_calls:
            if tool_call.function.name == "get_person_profile":
                args = json.loads(tool_call.function.arguments)
                tool_output = run_mcporter("get_person_profile", args)
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.function.name,
                    "content": tool_output
                })
                
                scraped_data.append({"tool": tool_call.function.name, "output": tool_output})
                
        # Send back to LLM for final response
        final_response = client.chat.completions.create(
            model="nvidia/nemotron-3-ultra-550b-a55b",
            messages=messages,
            tools=LINKEDIN_TOOLS,
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
