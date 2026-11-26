import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, LargeBinary, Index
from sqlalchemy.orm import relationship
from database import Base, DATABASE_URL
from gemini_client import EMBED_DIM

if DATABASE_URL.startswith("sqlite"):
    EMBEDDING_TYPE = LargeBinary
else:
    from pgvector.sqlalchemy import Vector
    EMBEDDING_TYPE = lambda: Vector(EMBED_DIM)

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    plan = Column(String, default="Free")
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    users = relationship("User", back_populates="organization")
    workflows = relationship("Workflow", back_populates="organization")

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="Viewer", index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    email_verified = Column(Boolean, default=False, index=True)
    mfa_enabled = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    organization = relationship("Organization", back_populates="users")
    notifications = relationship("Notification", back_populates="user")
    tokens = relationship("UserToken", back_populates="user", cascade="all, delete-orphan")
    
    # Composite indexes for common queries
    __table_args__ = (
        Index('ix_user_org_role', 'organization_id', 'role'),
        Index('ix_user_org_created', 'organization_id', 'created_at'),
    )

class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    workflow_json = Column(Text, nullable=False)
    status = Column(String, default="draft", index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, index=True)

    organization = relationship("Organization", back_populates="workflows")
    runs = relationship("WorkflowRun", back_populates="workflow", cascade="all, delete-orphan")
    
    # Composite indexes for common queries
    __table_args__ = (
        Index('ix_workflow_org_status', 'organization_id', 'status'),
        Index('ix_workflow_org_created', 'organization_id', 'created_at'),
    )

class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String, default="pending", index=True)
    started_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True, index=True)
    logs = Column(Text, default="")
    results = Column(Text, nullable=True)

    workflow = relationship("Workflow", back_populates="runs")
    
    # Composite indexes for common queries
    __table_args__ = (
        Index('ix_run_workflow_status', 'workflow_id', 'status'),
        Index('ix_run_started', 'started_at'),
    )

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False, index=True)
    file_type = Column(String, nullable=False)
    embedding_status = Column(String, default="pending", index=True)
    content = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    
    # Composite indexes
    __table_args__ = (
        Index('ix_doc_owner_status', 'owner_id', 'embedding_status'),
    )

class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_text = Column(Text, nullable=False)
    embedding = Column(EMBEDDING_TYPE() if not DATABASE_URL.startswith("sqlite") else EMBEDDING_TYPE(), nullable=False)

    document = relationship("Document", back_populates="chunks")

class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_type = Column(String, nullable=False, index=True)
    payload = Column(Text, nullable=False)
    status = Column(String, default="pending", index=True)
    retries = Column(Integer, default=0)
    result = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, index=True)
    
    # Composite indexes
    __table_args__ = (
        Index('ix_task_status_created', 'status', 'created_at'),
    )

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    message = Column(String, nullable=False)
    is_read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    user = relationship("User", back_populates="notifications")
    
    # Composite indexes
    __table_args__ = (
        Index('ix_notif_user_read', 'user_id', 'is_read'),
    )

class UserToken(Base):
    __tablename__ = "user_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String, unique=True, nullable=False, index=True)
    token_type = Column(String, nullable=False, default="refresh", index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

    user = relationship("User", back_populates="tokens")
    
    __table_args__ = (
        Index('ix_user_token_type', 'user_id', 'token_type'),
        Index('ix_user_token_expires', 'expires_at'),
    )

class QueueTask(Base):
    """Persistent task queue with retry logic, timeouts, and dead-letter handling."""
    __tablename__ = "queue_tasks"

    id = Column(Integer, primary_key=True, index=True)
    
    # Task identification
    task_type = Column(String, nullable=False, index=True)  # e.g., "workflow_run", "document_embed"
    payload = Column(Text, nullable=False)  # JSON-serialized task data
    
    # Status tracking
    status = Column(String, default="pending", index=True)  # pending, running, completed, failed, dead_letter
    
    # Retry logic
    retry_count = Column(Integer, default=0, index=True)
    max_retries = Column(Integer, default=3)
    
    # Timing
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    timeout_seconds = Column(Integer, default=300)  # 5 minutes default
    
    # Results & error handling
    result = Column(Text, nullable=True)  # JSON-serialized result
    error_message = Column(Text, nullable=True)
    error_traceback = Column(Text, nullable=True)
    
    # Progress tracking
    progress_percent = Column(Integer, default=0)
    progress_message = Column(String, nullable=True)
    
    # Webhook callback for progress/completion
    webhook_url = Column(String, nullable=True)  # URL to POST progress/completion updates
    
    # Relationship context
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Composite indexes for efficient queries
    __table_args__ = (
        Index('ix_queue_status_created', 'status', 'created_at'),
        Index('ix_queue_status_retry', 'status', 'retry_count'),
        Index('ix_queue_workflow_run', 'workflow_run_id'),
    )


# ============================================================================
# IAM (Identity & Access Management) Models - Role-Based Access Control
# ============================================================================

class Role(Base):
    """System roles for RBAC."""
    __tablename__ = "roles"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)  # e.g., "Super Admin", "Org Admin", "Research Manager", "Workflow Developer", "Viewer"
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    
    permissions = relationship("Permission", secondary="role_permissions", back_populates="roles")
    
    __table_args__ = (
        Index('ix_role_name', 'name'),
    )


class Permission(Base):
    """Fine-grained permissions (e.g., "workflow:create", "file:read")."""
    __tablename__ = "permissions"
    
    id = Column(Integer, primary_key=True, index=True)
    resource = Column(String, nullable=False, index=True)  # e.g., "workflow", "file", "organization"
    action = Column(String, nullable=False, index=True)     # e.g., "create", "read", "update", "delete"
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    roles = relationship("Role", secondary="role_permissions", back_populates="permissions")
    
    __table_args__ = (
        Index('ix_permission_resource_action', 'resource', 'action'),
    )


class RolePermission(Base):
    """Junction table: roles <-> permissions (many-to-many)."""
    __tablename__ = "role_permissions"
    
    id = Column(Integer, primary_key=True, index=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    permission_id = Column(Integer, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    __table_args__ = (
        Index('ix_role_permission', 'role_id', 'permission_id'),
    )


class ResourcePermission(Base):
    """
    Resource-level permissions (e.g., User A can access Workflow B).
    Allows overriding default role-based permissions for specific resources.
    """
    __tablename__ = "resource_permissions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    resource_type = Column(String, nullable=False, index=True)  # e.g., "workflow", "document"
    resource_id = Column(Integer, nullable=False, index=True)
    permission = Column(String, nullable=False)  # e.g., "read", "write", "delete"
    granted_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # Who granted this permission
    granted_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    expires_at = Column(DateTime, nullable=True)  # Optional expiration
    
    user = relationship("User", foreign_keys=[user_id], backref="resource_permissions")
    granted_by_user = relationship("User", foreign_keys=[granted_by])
    
    __table_args__ = (
        Index('ix_resource_permission_user', 'user_id', 'resource_type', 'resource_id'),
        Index('ix_resource_permission_resource', 'resource_type', 'resource_id'),
    )


class AuditLog(Base):
    """
    Audit trail for compliance and security: who did what, when, and the result.
    """
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String, nullable=False, index=True)  # e.g., "workflow:create", "user:login", "permission:grant"
    resource_type = Column(String, nullable=True, index=True)  # e.g., "workflow", "user", "document"
    resource_id = Column(Integer, nullable=True)
    status = Column(String, default="success", index=True)  # success, failure
    details = Column(Text, nullable=True)  # JSON: additional context
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    
    user = relationship("User")
    
    __table_args__ = (
        Index('ix_audit_user_created', 'user_id', 'created_at'),
        Index('ix_audit_action_created', 'action', 'created_at'),
    )
