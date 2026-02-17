import os
from supabase import create_client, Client

class SupabaseClient:
    _instance = None
    _client = None

    @classmethod
    def get_client(cls) -> Client:
        if cls._client is None:
            url = os.environ.get("SUPABASE_URL")
            key = os.environ.get("SUPABASE_KEY")
            
            if not url or not key:
                # In development/frozen app, these should be loaded from .env or compiled configuration
                # If running frozen, os.environ might not have them if not passed, but we'll assume .env loader runs first
                pass
            
            if url and key:
                cls._client = create_client(url, key)
            
        return cls._client

# Helper to easily get client
def get_supabase() -> Client:
    return SupabaseClient.get_client()
