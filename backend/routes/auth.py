from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional

from database import get_db
import models
import auth
from rate_limiter import limiter

router = APIRouter(prefix="/auth", tags=["auth"])

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    organization_name: str
    role: str = "Viewer" # Default role, can be customized or default to Workflow Developer/Viewer

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    role: str
    organization_id: int

class UserResponse(BaseModel):
    id: int
    email: str
    role: str
    organization_id: int

    class Config:
        from_attributes = True

class RefreshRequest(BaseModel):
    refresh_token: str

class LogoutRequest(BaseModel):
    refresh_token: str

class PasswordForgotRequest(BaseModel):
    email: EmailStr

class PasswordResetRequest(BaseModel):
    token: str
    new_password: str

class VerifyEmailRequest(BaseModel):
    token: str

class OAuthRequest(BaseModel):
    provider: str
    code: Optional[str] = None
    redirect_uri: Optional[str] = None

@router.post("/register", response_model=UserResponse)
def register(user_in: UserRegister, db: Session = Depends(get_db)):
    # Check if user already exists
    existing_user = db.query(models.User).filter(models.User.email == user_in.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email is already registered."
        )

    # 1. Create Organization
    org = models.Organization(name=user_in.organization_name)
    db.add(org)
    db.commit()
    db.refresh(org)

    # 2. Hash Password and Create User
    hashed_pwd = auth.get_password_hash(user_in.password)
    user = models.User(
        email=user_in.email,
        password_hash=hashed_pwd,
        role=user_in.role,
        organization_id=org.id,
        email_verified=False
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    verification_token = auth.create_email_verification_token(db, user.id)
    # In production, this token should be emailed to the user.
    print(f"Email verification token for {user.email}: {verification_token.token}")

    return user

@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(user_in: UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == user_in.email).first()
    if not user or not auth.verify_password(user_in.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect email or password."
        )

    access_token = auth.create_access_token(data={"sub": user.email})
    refresh_token_obj = auth.create_refresh_token(db, user.id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token_obj.token,
        "token_type": "bearer",
        "role": user.role,
        "organization_id": user.organization_id
    }

@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
def refresh_token(req: RefreshRequest, db: Session = Depends(get_db)):
    token_obj = auth.verify_user_token(db, req.refresh_token, "refresh")
    if not token_obj:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token."
        )

    user = db.query(models.User).filter(models.User.id == token_obj.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    # Revoke old refresh token and issue a new one
    auth.revoke_user_token(db, token_obj)
    new_refresh_token = auth.create_refresh_token(db, user.id)
    access_token = auth.create_access_token(data={"sub": user.email})

    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token.token,
        "token_type": "bearer",
        "role": user.role,
        "organization_id": user.organization_id
    }

@router.post("/logout")
def logout(req: LogoutRequest, db: Session = Depends(get_db)):
    token_obj = auth.verify_user_token(db, req.refresh_token, "refresh")
    if token_obj:
        auth.revoke_user_token(db, token_obj)
    return {"message": "Logged out successfully."}

@router.post("/forgot-password")
def forgot_password(req: PasswordForgotRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == req.email).first()
    if not user:
        return {"message": "If the email exists, a reset token has been generated."}

    reset_token = auth.create_password_reset_token(db, user.id)
    # In production, send this token over email. For the repo, return it for local testing.
    return {"message": "Password reset token created.", "reset_token": reset_token.token}

@router.post("/reset-password")
def reset_password(req: PasswordResetRequest, db: Session = Depends(get_db)):
    token_obj = auth.verify_user_token(db, req.token, "password_reset")
    if not token_obj:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired password reset token.")

    user = db.query(models.User).filter(models.User.id == token_obj.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    user.password_hash = auth.get_password_hash(req.new_password)
    auth.revoke_user_token(db, token_obj)
    db.commit()

    return {"message": "Password successfully reset."}

@router.post("/verify-email")
def verify_email(req: VerifyEmailRequest, db: Session = Depends(get_db)):
    token_obj = auth.verify_user_token(db, req.token, "email_verification")
    if not token_obj:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification token.")

    user = db.query(models.User).filter(models.User.id == token_obj.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    user.email_verified = True
    auth.revoke_user_token(db, token_obj)
    db.commit()

    return {"message": "Email successfully verified."}

@router.post("/oauth/{provider}")
def oauth_login(provider: str, req: OAuthRequest = None):
    """OAuth login placeholder. Implement provider-specific redirect + callback logic here."""
    return {
        "message": f"OAuth login for provider '{provider}' is available as a placeholder.",
        "instructions": "Configure OAuth provider keys and implement callback handling for full support."
    }

@router.get("/me", response_model=UserResponse)
def get_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user
