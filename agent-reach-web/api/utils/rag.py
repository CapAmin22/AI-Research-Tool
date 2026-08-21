from api.utils.supabase import get_supabase_client
from openai import OpenAI
from api.config import get_settings
import os

def get_openai_client():
    settings = get_settings()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)

async def store_document(content: str, metadata: dict, token: str):
    """
    Generate an embedding for the document and store it in Supabase pgvector.
    Requires OPENAI_API_KEY to be set for embeddings.
    """
    client = get_openai_client()
    if not client:
        print("Skipping document storage: OPENAI_API_KEY not found for embeddings.")
        return False
        
    try:
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=content[:8000] # truncate to avoid token limits
        )
        embedding = response.data[0].embedding
        
        supabase = get_supabase_client(token)
        user = supabase.auth.get_user(token)
        
        supabase.table("documents").insert({
            "user_id": user.user.id,
            "content": content,
            "metadata": metadata,
            "embedding": embedding
        }).execute()
        return True
    except Exception as e:
        print(f"Failed to store document: {e}")
        return False

async def search_memory(query: str, token: str, limit: int = 3):
    """
    Search past documents using pgvector.
    Note: Requires a match_documents Postgres function to be created in Supabase.
    """
    client = get_openai_client()
    if not client:
        return []
        
    try:
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=query
        )
        query_embedding = response.data[0].embedding
        
        supabase = get_supabase_client(token)
        # Call the Postgres RPC function (must be created in Supabase SQL editor)
        res = supabase.rpc("match_documents", {
            "query_embedding": query_embedding,
            "match_threshold": 0.7,
            "match_count": limit
        }).execute()
        
        return res.data
    except Exception as e:
        print(f"Failed to search memory: {e}")
        return []
