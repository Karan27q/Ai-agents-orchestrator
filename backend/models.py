import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, LargeBinary, Index
from sqlalchemy.orm import relationship
from database import Base, DATABASE_URL

if DATABASE_URL.startswith("sqlite"):
    EMBEDDING_TYPE = LargeBinary
else:
    from pgvector.sqlalchemy import Vector
    EMBEDDING_TYPE = lambda: Vector(768)

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
