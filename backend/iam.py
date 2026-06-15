"""
IAM (Identity & Access Management) - Authorization module
Provides RBAC (Role-Based Access Control) with resource-level permissions.
"""

import json
from enum import Enum
from typing import Optional, List, Callable, Any
from functools import wraps
from datetime import datetime

from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

import models
import auth
from database import get_db


class ResourceType(Enum):
    """Resource types that can be protected."""
    WORKFLOW = "workflow"
    DOCUMENT = "document"
    ORGANIZATION = "organization"
    USER = "user"


class Action(Enum):
    """Available actions on resources."""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXECUTE = "execute"
    SHARE = "share"


class Role(Enum):
    """Built-in roles."""
    ADMIN = "Admin"
    WORKFLOW_MANAGER = "Workflow Manager"
    EDITOR = "Editor"
    VIEWER = "Viewer"


# Default role permissions mapping
DEFAULT_ROLE_PERMISSIONS = {
    "Admin": [
        ("workflow", "create"),
        ("workflow", "read"),
        ("workflow", "update"),
        ("workflow", "delete"),
        ("workflow", "execute"),
        ("workflow", "share"),
        ("document", "create"),
        ("document", "read"),
        ("document", "update"),
        ("document", "delete"),
        ("document", "share"),
        ("organization", "read"),
        ("organization", "update"),
        ("organization", "share"),
        ("user", "read"),
        ("user", "create"),
        ("user", "update"),
        ("user", "delete"),
    ],
    "Workflow Manager": [
        ("workflow", "create"),
        ("workflow", "read"),
        ("workflow", "update"),
        ("workflow", "delete"),
        ("workflow", "execute"),
        ("workflow", "share"),
        ("document", "read"),
        ("document", "create"),
        ("organization", "read"),
    ],
    "Editor": [
        ("workflow", "create"),
        ("workflow", "read"),
        ("workflow", "update"),
        ("workflow", "execute"),
        ("document", "read"),
        ("document", "create"),
        ("organization", "read"),
    ],
    "Viewer": [
        ("workflow", "read"),
        ("workflow", "execute"),
        ("document", "read"),
        ("organization", "read"),
    ],
}


async def check_permission(
    user: models.User,
    resource_type: ResourceType,
    action: Action,
    resource_id: Optional[int] = None,
    db: Session = None,
) -> bool:
    """
    Check if user has permission to perform action on resource.
    
    Priority:
    1. Resource-level permissions (specific grants/denials)
    2. Role-based permissions (default role permissions)
    
    Returns: True if allowed, False otherwise
    """
    if not db:
        return False
    
    # Admin always has access
    if user.role == Role.ADMIN.value:
        return True
    
    # Check resource-level permissions first
    if resource_id:
        resource_perm = db.query(models.ResourcePermission).filter(
            models.ResourcePermission.user_id == user.id,
            models.ResourcePermission.resource_type == resource_type.value,
            models.ResourcePermission.resource_id == resource_id,
            models.ResourcePermission.permission == action.value,
        ).first()
        
        if resource_perm:
            # Check if expired
            if resource_perm.expires_at and datetime.utcnow() > resource_perm.expires_at:
                return False
            return True
    
    # Fall back to role-based permissions
    role_permissions = DEFAULT_ROLE_PERMISSIONS.get(user.role, [])
    for resource, action_name in role_permissions:
        if resource == resource_type.value and action_name == action.value:
            return True
    
    return False


def require_permission(
    resource_type: ResourceType,
    action: Action,
):
    """
    Decorator to protect endpoints with permission checks.
    
    Usage:
        @router.get("/workflows/{workflow_id}")
        @require_permission(ResourceType.WORKFLOW, Action.READ)
        async def get_workflow(workflow_id: int, current_user: models.User = Depends(auth.get_current_user)):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract current_user and db from dependency injection
            current_user: models.User = kwargs.get("current_user")
            db: Session = kwargs.get("db")
            
            if not current_user or not db:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated",
                )
            
            # Extract resource_id from route parameters if available
            resource_id = kwargs.get("workflow_id") or kwargs.get("document_id") or kwargs.get("resource_id")
            
            # Check permission
            has_permission = await check_permission(
                current_user,
                resource_type,
                action,
                resource_id,
                db,
            )
            
            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {resource_type.value}:{action.value}",
                )
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def require_role(*roles: str):
    """
    Decorator to restrict endpoints to specific roles.
    
    Usage:
        @router.post("/users")
        @require_role("Admin", "Workflow Manager")
        async def create_user(current_user: models.User = Depends(auth.get_current_user)):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user: models.User = kwargs.get("current_user")
            
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated",
                )
            
            if current_user.role not in roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"This action requires one of these roles: {', '.join(roles)}",
                )
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def require_organization_access(func: Callable):
    """
    Decorator to ensure user has access to organization.
    Primarily for checking if user is in the same organization.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        current_user: models.User = kwargs.get("current_user")
        org_id = kwargs.get("organization_id")
        
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )
        
        if org_id and current_user.organization_id != org_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this organization",
            )
        
        return await func(*args, **kwargs)
    
    return wrapper


async def log_audit(
    db: Session,
    user: Optional[models.User],
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
    status: str = "success",
    details: Optional[dict] = None,
    request: Optional[Request] = None,
):
    """
    Log an audit event for compliance and security tracking.
    
    Args:
        db: Database session
        user: User performing the action
        action: Action type (e.g., "workflow:create")
        resource_type: Type of resource affected
        resource_id: ID of resource affected
        status: "success" or "failure"
        details: Additional JSON context
        request: FastAPI Request for IP/User-Agent
    """
    try:
        audit_entry = models.AuditLog(
            user_id=user.id if user else None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            details=json.dumps(details) if details else None,
            ip_address=request.client.host if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
        )
        db.add(audit_entry)
        db.commit()
    except Exception as e:
        print(f"Error logging audit: {e}")


def get_user_role_permissions(db: Session, user: models.User) -> List[str]:
    """Get all permissions for a user based on their role."""
    role_permissions = DEFAULT_ROLE_PERMISSIONS.get(user.role, [])
    return [f"{resource}:{action}" for resource, action in role_permissions]


def can_user_perform_action(
    db: Session,
    user: models.User,
    resource_type: str,
    action: str,
) -> bool:
    """Check if user can perform action (simple string-based check)."""
    role_permissions = DEFAULT_ROLE_PERMISSIONS.get(user.role, [])
    return (resource_type, action) in role_permissions


async def get_current_user_with_permission(
    resource_type: ResourceType,
    action: Action,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
) -> models.User:
    """
    Dependency injection: Get current user and verify they have permission.
    """
    has_permission = await check_permission(current_user, resource_type, action, None, db)
    
    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {resource_type.value}:{action.value}",
        )
    
    return current_user
