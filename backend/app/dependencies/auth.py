import structlog
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client, Client
from app.config import get_settings

log = structlog.get_logger(__name__)

security = HTTPBearer()

def verify_supabase_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> Client:
    """
    Dependency that extracts the JWT token from the Authorization header,
    creates a new Supabase client with the ANON key, and injects the user's JWT.
    This ensures all subsequent DB queries respect Row-Level Security (RLS) for that user.
    """
    settings = get_settings()
    token = credentials.credentials
    
    try:
        # We must create a new client per request to avoid leaking JWTs across concurrent requests
        client = create_client(settings.supabase_url, settings.supabase_anon_key)
        
        # Inject the JWT into the postgrest client
        client.postgrest.auth(token)
        
        return client
    except Exception as e:
        log.warning("Invalid Supabase token provided", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
