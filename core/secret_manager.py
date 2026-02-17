import os
import json
from typing import Optional, Dict
from core.supabase_client import get_supabase
from core.license_manager import get_license_manager
from core.logger import get_logger

logger = get_logger(__name__)

class SecretManager:
    """
    Securely fetches API keys and secrets from Supabase.
    Requires a valid license to access.
    """
    
    _secrets_cache: Dict[str, str] = {}
    
    @classmethod
    def get_secret(cls, key_name: str, use_cache: bool = True) -> Optional[str]:
        """
        Get a secret value.
        First checks env vars (dev), then cache, then remote DB.
        """
        # 1. Check local environment (for development or legacy)
        if os.environ.get(key_name):
            return os.environ.get(key_name)
            
        # 2. Check cache
        if use_cache and key_name in cls._secrets_cache:
            return cls._secrets_cache[key_name]
            
        # 3. Fetch from Supabase (requires license)
        try:
            val = cls._fetch_remote_secret(key_name)
            if val:
                cls._secrets_cache[key_name] = val
                return val
        except Exception as e:
            logger.error(f"Failed to fetch secret {key_name}: {e}")
            
        return None

    @classmethod
    def _fetch_remote_secret(cls, key_name: str) -> Optional[str]:
        client = get_supabase()
        if not client: return None
        
        lm = get_license_manager()
        if not lm._current_license:
            return None
            
        license_key = lm._current_license.key
        device_id = lm._current_license.hardware_fingerprint

        try:
            # RPC `get_app_config` takes (p_license_key, p_device_id)
            # Returns JSON { "TRIPO_KEY": "...", "HITEM_KEY": "..." }
            response = client.rpc("get_app_config", {
                "p_license_key": license_key,
                "p_device_id": device_id
            }).execute()
            
            data = response.data
            
            # If error returned (our RPC returns `{"error": "..."}` on failure)
            if isinstance(data, dict) and "error" in data:
                logger.error(f"Secret fetch error: {data['error']}")
                return None
                
            # Update cache with all returned secrets
            if isinstance(data, dict):
                cls._secrets_cache.update(data)
                return data.get(key_name)
                
        except Exception as e:
             logger.error(f"Error calling get_app_config RPC: {e}")
             
        return None

# Helper
def get_secret(key: str) -> Optional[str]:
    return SecretManager.get_secret(key)
