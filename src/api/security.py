import hmac
from typing import Optional

from fastapi import Header, HTTPException, status

from src.config import settings


async def require_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> None:
    """
    FastAPI dependency enforcing the X-API-Key header.

    - API_KEY configured: header must match (constant-time compare).
    - API_KEY not configured: allowed only outside production (Settings refuses to boot
      in production without API_KEY, so this is dev/test convenience only).
    """
    expected = settings.API_KEY
    if not expected:
        if settings.is_production:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="API key not configured")
        return
    if not x_api_key or not hmac.compare_digest(x_api_key.encode(), expected.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
