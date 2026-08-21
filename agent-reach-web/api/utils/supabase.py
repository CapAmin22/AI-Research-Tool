import os
from supabase import create_client, Client
from api.config import get_settings

def get_supabase_client(token: str = None) -> Client:
    settings = get_settings()
    url = settings.supabase_url or os.environ.get("SUPABASE_URL")
    key = settings.supabase_key or os.environ.get("SUPABASE_KEY")
    
    if not url or not key:
        raise ValueError("Supabase URL or Key is not configured")
        
    client = create_client(url, key)
    
    # If a user JWT token is provided, set it on the client so RLS policies are applied
    if token:
        # We override the auth headers for this specific client instance
        client.postgrest.auth(token)
        
    return client
