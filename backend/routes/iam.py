"""
IAM Routes - Role and Permission Management
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta

from database import get_db
import models
import auth
import iam
from rate_limiter import limiter

router = APIRouter(prefix="/iam", tags=["iam"])


# ============================================================================
# Pydantic Models for Request/Response
# ============================================================================

class PermissionResponse(BaseModel):
    id: int
    resource: str
    action: str
    description: Optional[str]
    
    class Config:
        from_attributes = True


class RoleResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    permissions: List[PermissionResponse]
    
    class Config:
        from_attributes = True


class RoleAssignRequest(BaseModel):
    user_id: int
    role: str  # one of auth.ALL_ROLES


class ResourcePermissionRequest(BaseModel):
    user_id: int
    resource_type: str  # "workflow", "document", "organization"
    resource_id: int
    permission: str  # "read", "write", "delete", "share"
    expires_in_days: Optional[int] = None  # Optional expiration


class ResourcePermissionResponse(BaseModel):
    id: int
    user_id: int
    resource_type: str
    resource_id: int
    permission: str
    granted_by: Optional[int]
    granted_at: datetime
    expires_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class UserPermissionResponse(BaseModel):
    user_id: int
    email: str
    role: str
    permissions: List[str]  # e.g., ["workflow:create", "workflow:read", ...]
    resource_permissions: List[ResourcePermissionResponse]
    
    class Config:
        from_attributes = True


class AuditLogResponse(BaseModel):
    id: int
    user_id: Optional[int]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[int]
    status: str
    details: Optional[str]
    ip_address: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


# ============================================================================
# User Permission Management Endpoints
# ============================================================================

@router.get("/users/{user_id}/permissions", response_model=UserPermissionResponse)
async def get_user_permissions(
    user_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get all permissions for a user (role-based + resource-specific).
    Only Admin or the user themselves can view this.
    """
    if not auth.is_admin(current_user) and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own permissions",
        )
    
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    permissions = iam.get_user_role_permissions(db, user)
    resource_permissions = db.query(models.ResourcePermission).filter(
        models.ResourcePermission.user_id == user_id
    ).all()
    
    return {
        "user_id": user.id,
        "email": user.email,
        "role": user.role,
        "permissions": permissions,
        "resource_permissions": resource_permissions,
    }


@router.post("/users/{user_id}/role", response_model=dict)
@limiter.limit("10/minute")
async def assign_user_role(
    request: Request,
    user_id: int,
    req: RoleAssignRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Assign a role to a user. Only Admin can do this.
    """
    if not auth.is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can assign roles",
        )
    
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Validate role
    valid_roles = list(auth.ALL_ROLES)
    if req.role not in valid_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}",
        )

    # Only a Super Admin may mint another Super Admin.
    if req.role == auth.ROLE_SUPER_ADMIN and current_user.role != auth.ROLE_SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a Super Admin can assign the Super Admin role",
        )

    old_role = user.role
    user.role = req.role
    db.commit()
    
    # Log audit
    await iam.log_audit(
        db,
        current_user,
        "user:role_assign",
        "user",
        user_id,
        details={"old_role": old_role, "new_role": req.role},
    )
    
    return {"message": f"User role updated to {req.role}", "user_id": user_id}


# ============================================================================
# Resource-Level Permission Management
# ============================================================================

@router.post("/permissions/resource", response_model=ResourcePermissionResponse)
@limiter.limit("20/minute")
async def grant_resource_permission(
    request: Request,
    req: ResourcePermissionRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Grant a user specific permission on a resource.
    Only Admin or resource owner can grant permissions.
    """
    if not auth.is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can grant resource permissions",
        )
    
    # Validate target user exists
    target_user = db.query(models.User).filter(models.User.id == req.user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found")
    
    # Check if permission already exists
    existing = db.query(models.ResourcePermission).filter(
        models.ResourcePermission.user_id == req.user_id,
        models.ResourcePermission.resource_type == req.resource_type,
        models.ResourcePermission.resource_id == req.resource_id,
        models.ResourcePermission.permission == req.permission,
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Permission already exists for this user/resource combination",
        )
    
    # Create permission
    expires_at = None
    if req.expires_in_days:
        expires_at = datetime.utcnow() + timedelta(days=req.expires_in_days)
    
    permission = models.ResourcePermission(
        user_id=req.user_id,
        resource_type=req.resource_type,
        resource_id=req.resource_id,
        permission=req.permission,
        granted_by=current_user.id,
        expires_at=expires_at,
    )
    db.add(permission)
    db.commit()
    db.refresh(permission)
    
    # Log audit
    await iam.log_audit(
        db,
        current_user,
        f"permission:grant",
        req.resource_type,
        req.resource_id,
        details={
            "user_id": req.user_id,
            "permission": req.permission,
            "expires_at": expires_at.isoformat() if expires_at else None,
        },
    )
    
    return permission


@router.delete("/permissions/resource/{permission_id}")
@limiter.limit("20/minute")
async def revoke_resource_permission(
    request: Request,
    permission_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Revoke a resource permission. Only Admin can do this.
    """
    if not auth.is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can revoke permissions",
        )
    
    permission = db.query(models.ResourcePermission).filter(
        models.ResourcePermission.id == permission_id
    ).first()
    
    if not permission:
        raise HTTPException(status_code=404, detail="Permission not found")
    
    # Log audit before deletion
    await iam.log_audit(
        db,
        current_user,
        "permission:revoke",
        permission.resource_type,
        permission.resource_id,
        details={"user_id": permission.user_id, "permission": permission.permission},
    )
    
    db.delete(permission)
    db.commit()
    
    return {"message": "Permission revoked successfully"}


@router.get("/permissions/resource", response_model=List[ResourcePermissionResponse])
async def list_resource_permissions(
    resource_type: Optional[str] = Query(None),
    resource_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    List resource permissions with optional filtering.
    Only Admin can list all; others can only see their own.
    """
    query = db.query(models.ResourcePermission)
    
    if not auth.is_admin(current_user):
        query = query.filter(models.ResourcePermission.user_id == current_user.id)
    
    if resource_type:
        query = query.filter(models.ResourcePermission.resource_type == resource_type)
    if resource_id:
        query = query.filter(models.ResourcePermission.resource_id == resource_id)
    if user_id:
        query = query.filter(models.ResourcePermission.user_id == user_id)
    
    return query.all()


# ============================================================================
# Audit Log Endpoints
# ============================================================================

@router.get("/audit-logs", response_model=List[AuditLogResponse])
async def list_audit_logs(
    action: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    resource_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    List audit logs with optional filtering.
    Only Admin can view audit logs.
    """
    if not auth.is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can view audit logs",
        )
    
    query = db.query(models.AuditLog)
    
    if action:
        query = query.filter(models.AuditLog.action == action)
    if user_id:
        query = query.filter(models.AuditLog.user_id == user_id)
    if resource_type:
        query = query.filter(models.AuditLog.resource_type == resource_type)
    
    total = query.count()
    logs = query.order_by(models.AuditLog.created_at.desc()).offset(offset).limit(limit).all()
    
    return logs


@router.get("/audit-logs/stats", response_model=dict)
async def get_audit_stats(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get audit statistics. Only Admin can view.
    """
    if not auth.is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can view audit statistics",
        )
    
    total_actions = db.query(models.AuditLog).count()
    failed_actions = db.query(models.AuditLog).filter(
        models.AuditLog.status == "failure"
    ).count()
    
    return {
        "total_actions": total_actions,
        "failed_actions": failed_actions,
        "success_rate": ((total_actions - failed_actions) / max(total_actions, 1)) * 100,
    }


# ============================================================================
# Role Management Endpoints
# ============================================================================

@router.get("/roles", response_model=List[dict])
async def list_roles(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    List all available roles and their permissions.
    """
    roles_info = []
    for role_name, permissions in iam.DEFAULT_ROLE_PERMISSIONS.items():
        roles_info.append({
            "name": role_name,
            "permissions": [f"{resource}:{action}" for resource, action in permissions],
        })
    return roles_info


@router.get("/permissions", response_model=List[dict])
async def list_all_permissions(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    List all available resource:action permission combinations.
    """
    all_permissions = set()
    for role_perms in iam.DEFAULT_ROLE_PERMISSIONS.values():
        for resource, action in role_perms:
            all_permissions.add((resource, action))
    
    return [{"resource": r, "action": a} for r, a in sorted(all_permissions)]
