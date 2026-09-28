import os
from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

bearer = HTTPBearer(auto_error=False)

@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str
    user_metadata: dict
    app_metadata: dict

@lru_cache(maxsize=1)
def jwks_client(url: str):
    return PyJWKClient(f"{url.rstrip('/')}/auth/v1/.well-known/jwks.json", cache_keys=True, lifespan=600)

def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> AuthUser:
    if credentials is None:
        raise HTTPException(401, "Please sign in to continue.", headers={"WWW-Authenticate": "Bearer"})
    project_url = os.getenv("SUPABASE_URL", "").strip()
    if not project_url:
        raise HTTPException(503, "Supabase authentication is not configured on this server.")
    token = credentials.credentials
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") == "HS256" and os.getenv("SUPABASE_JWT_SECRET"):
            claims = jwt.decode(token, os.environ["SUPABASE_JWT_SECRET"], algorithms=["HS256"], audience="authenticated", issuer=f"{project_url.rstrip('/')}/auth/v1")
        else:
            key = jwks_client(project_url).get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["ES256", "RS256"], audience="authenticated", issuer=f"{project_url.rstrip('/')}/auth/v1")
        subject = str(UUID(claims["sub"]))
        return AuthUser(subject, claims.get("email", ""), claims.get("user_metadata") or {}, claims.get("app_metadata") or {})
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(401, "Your session expired. Please sign in again.", headers={"WWW-Authenticate": "Bearer"})

def require_admin(user: AuthUser = Depends(current_user)) -> AuthUser:
    allowed = {x.strip() for x in os.getenv("ADMIN_USER_IDS", "").split(",") if x.strip()}
    if user.app_metadata.get("role") != "admin" and user.id not in allowed:
        raise HTTPException(403, "Content ingestion is restricted to administrators.")
    return user
