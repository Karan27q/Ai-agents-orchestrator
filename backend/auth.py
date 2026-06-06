import datetime
import os
import secrets
from typing import Optional, List
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
import bcrypt
from sqlalchemy.orm import Session
from functools import lru_cache
import threading
import time

from database import get_db
import models

# Secret key for JWT signing
SECRET_KEY = os.getenv("JWT_SECRET", "supersecretkeyforlocaldevelopmentonly")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
REFRESH_TOKEN_EXPIRE_DAYS = 14
PASSWORD_RESET_EXPIRE_HOURS = 2
EMAIL_VERIFICATION_EXPIRE_HOURS = 24

# User cache for fast lookups (thread-safe LRU cache)
_user_cache = {}
_cache_lock = threading.RLock()
USER_CACHE_TTL = 300  # 5 minutes

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")

class UserCache:
    @staticmethod
    def get_user(email: str, db: Session = None):
        """Get user from cache, fallback to database."""
        with _cache_lock:
            if email in _user_cache:
                user, timestamp = _user_cache[email]
                if time.time() - timestamp < USER_CACHE_TTL:
                    return user
                else:
                    del _user_cache[email]
        
        # Cache miss - fetch from DB
        if db:
            user = db.query(models.User).filter(models.User.email == email).first()
            if user:
                with _cache_lock:
                    _user_cache[email] = (user, time.time())
            return user
        return None
    
    @staticmethod
    def invalidate(email: str):
        """Invalidate user cache entry."""
        with _cache_lock:
            if email in _user_cache:
                del _user_cache[email]

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.utcnow() + expires_delta
    else:
        expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    to_encode.update({"sub": data.get("sub")})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def _create_token_string() -> str:
    return secrets.token_urlsafe(40)

def _create_user_token(db: Session, user_id: int, token_type: str, expires_delta: datetime.timedelta) -> models.UserToken:
    token_value = _create_token_string()
    expires_at = datetime.datetime.utcnow() + expires_delta
    token = models.UserToken(
        user_id=user_id,
        token=token_value,
        token_type=token_type,
        expires_at=expires_at,
        revoked=False
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return token

def create_refresh_token(db: Session, user_id: int) -> models.UserToken:
    return _create_user_token(db, user_id, "refresh", datetime.timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))

def create_email_verification_token(db: Session, user_id: int) -> models.UserToken:
    return _create_user_token(db, user_id, "email_verification", datetime.timedelta(hours=EMAIL_VERIFICATION_EXPIRE_HOURS))

def create_password_reset_token(db: Session, user_id: int) -> models.UserToken:
    return _create_user_token(db, user_id, "password_reset", datetime.timedelta(hours=PASSWORD_RESET_EXPIRE_HOURS))

def verify_user_token(db: Session, token_str: str, token_type: str) -> Optional[models.UserToken]:
    token = db.query(models.UserToken).filter(
        models.UserToken.token == token_str,
        models.UserToken.token_type == token_type,
        models.UserToken.revoked == False,
        models.UserToken.expires_at > datetime.datetime.utcnow()
    ).first()
    return token

def revoke_user_token(db: Session, token: models.UserToken):
    token.revoked = True
    db.commit()
    db.refresh(token)
    return token

def revoke_refresh_tokens_for_user(db: Session, user_id: int):
    tokens = db.query(models.UserToken).filter(
        models.UserToken.user_id == user_id,
        models.UserToken.token_type == "refresh",
        models.UserToken.revoked == False
    ).all()
    for token in tokens:
        token.revoked = True
    db.commit()


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.User:
    """Get current user with caching for faster authentication."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
    
    # Try cache first, then database
    user = UserCache.get_user(email, db)
    if user is None:
        raise credentials_exception
    return user

class RoleChecker:
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: models.User = Depends(get_current_user)) -> models.User:
        # Hierarchical roles or simple list checking
        role_hierarchy = {
            "Super Admin": 4,
            "Org Admin": 3,
            "Research Manager": 2,
            "Workflow Developer": 1,
            "Viewer": 0
        }
        
        user_role_level = role_hierarchy.get(current_user.role, 0)
        
        if current_user.role == "Super Admin":
            return current_user
            
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Required roles: {self.allowed_roles}. Current role: {current_user.role}"
            )
        return current_user

# Helper dependency injections
def require_admin(current_user: models.User = Depends(RoleChecker(["Super Admin", "Org Admin"]))):
    return current_user

def require_developer(current_user: models.User = Depends(RoleChecker(["Super Admin", "Org Admin", "Workflow Developer"]))):
    return current_user

def require_manager(current_user: models.User = Depends(RoleChecker(["Super Admin", "Org Admin", "Research Manager"]))):
    return current_user
