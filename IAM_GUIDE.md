# IAM (Identity & Access Management) Implementation Guide

## Overview

Your application now has a complete **Role-Based Access Control (RBAC)** system with:

- **4 Built-in Roles**: Admin, Workflow Manager, Editor, Viewer
- **Role-Based Permissions**: Automatic permissions based on user role
- **Resource-Level Permissions**: Fine-grained control per resource (workflow, document, organization)
- **Audit Logging**: Complete audit trail of who did what, when
- **Admin APIs**: Manage roles, permissions, and view audit logs

---

## 🎯 Architecture

### Role Hierarchy

```
Admin (highest privileges)
├─ Can do everything
└─ Can manage users, roles, permissions

Workflow Manager
├─ Create, read, update, delete workflows
├─ Execute workflows
├─ Share workflows
└─ Manage documents

Editor
├─ Create, read, update workflows
├─ Execute workflows
├─ Read documents
└─ Create documents

Viewer (lowest privileges)
├─ Read workflows
├─ Execute workflows
└─ Read documents
```

### Default Role Permissions

| Action | Admin | Workflow Manager | Editor | Viewer |
|--------|:-----:|:----------------:|:------:|:------:|
| **Workflow: Create** | ✅ | ✅ | ✅ | ❌ |
| **Workflow: Read** | ✅ | ✅ | ✅ | ✅ |
| **Workflow: Update** | ✅ | ✅ | ✅ | ❌ |
| **Workflow: Delete** | ✅ | ✅ | ❌ | ❌ |
| **Workflow: Execute** | ✅ | ✅ | ✅ | ✅ |
| **Workflow: Share** | ✅ | ✅ | ❌ | ❌ |
| **Document: Create** | ✅ | ✅ | ✅ | ❌ |
| **Document: Read** | ✅ | ✅ | ✅ | ✅ |
| **Document: Update** | ✅ | ✅ | ❌ | ❌ |
| **Document: Delete** | ✅ | ✅ | ❌ | ❌ |
| **Organization: Read** | ✅ | ✅ | ✅ | ✅ |
| **Organization: Update** | ✅ | ❌ | ❌ | ❌ |
| **User: Manage** | ✅ | ❌ | ❌ | ❌ |

---

## 📚 API Endpoints

### User Permission Management

```bash
# Get user's permissions (role-based + resource-specific)
GET /api/v1/iam/users/{user_id}/permissions

# Assign a role to user (Admin only)
POST /api/v1/iam/users/{user_id}/role
{
  "role": "Workflow Manager"  # "Admin", "Workflow Manager", "Editor", "Viewer"
}
```

### Resource-Level Permissions

```bash
# Grant specific permission on a resource (Admin only)
POST /api/v1/iam/permissions/resource
{
  "user_id": 123,
  "resource_type": "workflow",
  "resource_id": 456,
  "permission": "read",
  "expires_in_days": 30  # Optional expiration
}

# List resource permissions (with filtering)
GET /api/v1/iam/permissions/resource?resource_type=workflow&resource_id=456

# Revoke a resource permission (Admin only)
DELETE /api/v1/iam/permissions/resource/{permission_id}
```

### Role & Permission Information

```bash
# List all available roles and their permissions
GET /api/v1/iam/roles
→ [
  {
    "name": "Admin",
    "permissions": ["workflow:create", "workflow:read", "workflow:update", ...]
  },
  ...
]

# List all available resource:action combinations
GET /api/v1/iam/permissions
→ [
  {"resource": "workflow", "action": "create"},
  {"resource": "workflow", "action": "read"},
  ...
]
```

### Audit Logging

```bash
# List audit logs (Admin only)
GET /api/v1/iam/audit-logs?action=workflow:create&limit=50

# Get audit statistics (Admin only)
GET /api/v1/iam/audit-logs/stats
→ {
  "total_actions": 1250,
  "failed_actions": 12,
  "success_rate": 99.04
}
```

---

## 🔒 Protecting Your Endpoints

### Method 1: Using `@require_permission` Decorator

```python
from fastapi import APIRouter, Depends
import auth
import iam
import models
from database import get_db

router = APIRouter()

@router.get("/workflows/{workflow_id}")
@iam.require_permission(iam.ResourceType.WORKFLOW, iam.Action.READ)
async def get_workflow(
    workflow_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    # Only users with workflow:read permission can access this
    workflow = db.query(models.Workflow).filter(
        models.Workflow.id == workflow_id
    ).first()
    return workflow
```

### Method 2: Using `@require_role` Decorator

```python
@router.post("/users")
@iam.require_role("Admin", "Workflow Manager")
async def create_user(
    user_data: dict,
    current_user: models.User = Depends(auth.get_current_user),
):
    # Only Admins or Workflow Managers can create users
    ...
```

### Method 3: Manual Permission Check

```python
async def check_before_operation(
    current_user: models.User,
    db: Session,
):
    # Check permission manually
    has_permission = await iam.check_permission(
        current_user,
        iam.ResourceType.WORKFLOW,
        iam.Action.DELETE,
        resource_id=workflow_id,
        db=db,
    )
    
    if not has_permission:
        raise HTTPException(status_code=403, detail="Permission denied")
```

---

## 📝 Audit Logging

### Automatic Audit Logging

```python
# Log an action
await iam.log_audit(
    db=db,
    user=current_user,
    action="workflow:create",
    resource_type="workflow",
    resource_id=new_workflow.id,
    status="success",
    details={"name": workflow_name, "nodes_count": 5},
    request=request,  # Optional: captures IP + User-Agent
)
```

### Audit Log Structure

Each audit log entry contains:
- **user_id**: Who performed the action
- **action**: What was done (e.g., `workflow:create`)
- **resource_type**: Type of resource affected
- **resource_id**: ID of resource affected
- **status**: `"success"` or `"failure"`
- **details**: JSON with additional context
- **ip_address**: IP of requester
- **user_agent**: Browser/client info
- **created_at**: When the action occurred

---

## 🚀 Implementation Checklist

### Step 1: Database Setup ✅
- [x] IAM models added to `models.py`
  - `Role` - Define roles (Admin, Workflow Manager, etc.)
  - `Permission` - Fine-grained permissions (workflow:create, etc.)
  - `RolePermission` - Many-to-many relationship
  - `ResourcePermission` - Resource-level grants
  - `AuditLog` - Audit trail

### Step 2: Authorization Module ✅
- [x] `iam.py` created with:
  - `check_permission()` - Check if user has permission
  - `require_permission()` - Endpoint decorator
  - `require_role()` - Role-based endpoint protection
  - `log_audit()` - Log audit events
  - Default role permissions mapping

### Step 3: IAM Routes ✅
- [x] `routes/iam.py` created with endpoints:
  - User permission management
  - Resource permission granting/revocation
  - Audit log viewing
  - Role and permission information

### Step 4: Protect Existing Endpoints (TODO)
- [ ] Add `@require_permission` to workflow endpoints
- [ ] Add `@require_permission` to document endpoints
- [ ] Add `@require_permission` to organization endpoints
- [ ] Add audit logging to all mutation endpoints

### Step 5: Frontend Integration (TODO)
- [ ] Disable UI elements based on user permissions
- [ ] Show role/permission info to users
- [ ] Handle 403 Forbidden errors gracefully

---

## 📋 Protecting Existing Endpoints - Examples

### Workflow Routes

```python
# backend/routes/workflows.py

@router.post("/workflows")
@iam.require_permission(iam.ResourceType.WORKFLOW, iam.Action.CREATE)
async def create_workflow(
    workflow: WorkflowCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
    request: Request = None,
):
    new_workflow = models.Workflow(
        name=workflow.name,
        workflow_json=workflow.workflow_json,
        organization_id=current_user.organization_id,
        created_by=current_user.id,
    )
    db.add(new_workflow)
    db.commit()
    
    # Log the action
    await iam.log_audit(
        db, current_user, "workflow:create", "workflow",
        new_workflow.id, "success", request=request
    )
    
    return new_workflow

@router.get("/workflows/{workflow_id}")
@iam.require_permission(iam.ResourceType.WORKFLOW, iam.Action.READ)
async def get_workflow(
    workflow_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    workflow = db.query(models.Workflow).filter(
        models.Workflow.id == workflow_id
    ).first()
    return workflow

@router.delete("/workflows/{workflow_id}")
@iam.require_permission(iam.ResourceType.WORKFLOW, iam.Action.DELETE)
async def delete_workflow(
    workflow_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
    request: Request = None,
):
    workflow = db.query(models.Workflow).filter(
        models.Workflow.id == workflow_id
    ).first()
    
    db.delete(workflow)
    db.commit()
    
    await iam.log_audit(
        db, current_user, "workflow:delete", "workflow",
        workflow_id, "success", request=request
    )
    
    return {"message": "Workflow deleted"}
```

---

## 🔧 Configuration & Customization

### Add New Role

Edit `iam.py` `DEFAULT_ROLE_PERMISSIONS`:

```python
DEFAULT_ROLE_PERMISSIONS = {
    "Your New Role": [
        ("workflow", "create"),
        ("workflow", "read"),
        ("document", "read"),
    ],
}
```

### Add New Permission

Add to role definition:
```python
DEFAULT_ROLE_PERMISSIONS = {
    "Admin": [
        ("new_resource", "new_action"),  # Add here
    ],
}
```

### Extend AuditLog Details

Include more context in audit logs:
```python
await iam.log_audit(
    db, current_user, "workflow:execute",
    "workflow", workflow_id,
    details={
        "execution_time": 125.5,
        "nodes_executed": 12,
        "status": "success",
        "user_email": current_user.email,
    }
)
```

---

## 🎓 Usage Examples

### Example 1: Create Workflow as Editor

```bash
# User with "Editor" role
POST /api/v1/workflows
{
  "name": "My Workflow",
  "workflow_json": {...}
}

# ✅ Allowed (Editors can create workflows)
```

### Example 2: Delete User as Viewer

```bash
# User with "Viewer" role
DELETE /api/v1/users/123

# ❌ Denied (Viewers cannot delete users - only Admins)
```

### Example 3: Grant Special Permission

```bash
# Admin grants Viewer special read access to a workflow
POST /api/v1/iam/permissions/resource
{
  "user_id": 99,
  "resource_type": "workflow",
  "resource_id": 456,
  "permission": "read",
  "expires_in_days": 7
}

# Now user 99 can read workflow 456 for 7 days, even though Viewers normally can't
```

### Example 4: View Audit Trail

```bash
# Admin views all actions in past 24 hours
GET /api/v1/iam/audit-logs?limit=100

# Shows: who logged in, what workflows were created/deleted, errors, etc.
```

---

## 🚨 Security Considerations

1. **Always check permissions** - Use decorators or manual checks on all sensitive endpoints
2. **Log everything** - Enable audit logging on all mutations
3. **Principle of least privilege** - Assign minimal required role to users
4. **Expire temporary permissions** - Use `expires_in_days` for temporary access
5. **Regularly review audit logs** - Check for suspicious activity
6. **Protect Admin role** - Only trusted admins should assign this role

---

## 📊 Monitoring IAM Health

### Check Audit Statistics

```bash
GET /api/v1/iam/audit-logs/stats

Response:
{
  "total_actions": 2500,
  "failed_actions": 15,
  "success_rate": 99.4
}
```

### Identify Suspicious Activity

```bash
# Failed actions (potential attacks)
GET /api/v1/iam/audit-logs?filter[status]=failure&limit=50

# User behavior (too many failed logins?)
GET /api/v1/iam/audit-logs?user_id=123&limit=100
```

---

## 📝 Next Steps

1. **✅ Core IAM implemented** - Models, authorization, routes
2. **⏭️ Protect existing endpoints** - Add decorators to workflows, files, organization routes
3. **⏭️ Frontend integration** - Show/hide UI based on permissions
4. **⏭️ Service accounts (Future)** - API keys for programmatic access
5. **⏭️ Advanced policies (Future)** - Custom rules, time-based access, etc.

---

## 📚 Files Reference

- **[backend/iam.py](backend/iam.py)** - Core IAM module with authorization logic
- **[backend/routes/iam.py](backend/routes/iam.py)** - IAM management API endpoints
- **[backend/models.py](backend/models.py)** - IAM database models
- **[backend/main.py](backend/main.py)** - IAM routes registration

