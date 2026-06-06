import os
from sqlalchemy import create_engine, event, pool, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    # SQLAlchemy prefers the modern postgres URL scheme
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Fall back to a local SQLite file for development when no hosted DB is configured.
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./orchestrator.db"

# Connection pooling configuration - CRITICAL for throughput
connect_args = {}
pooling_config = {}

if DATABASE_URL.startswith("sqlite"):
    # SQLite: Use StaticPool with check_same_thread=False for better concurrency
    connect_args = {"check_same_thread": False, "timeout": 30}
    pooling_config = {
        "poolclass": pool.StaticPool,
        "pool_pre_ping": True,  # Verify connections before reuse
        "echo_pool": False,
    }
else:
    # PostgreSQL/MySQL: Use QueuePool with optimized settings
    pooling_config = {
        "pool_size": 20,           # Base connection pool size
        "max_overflow": 40,        # Additional overflow connections
        "pool_recycle": 3600,      # Recycle connections after 1 hour
        "pool_pre_ping": True,     # Test connections before use
        "echo_pool": False,
    }

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    **pooling_config,
    echo=False,
    query_cache_size=500,
)

# Configure SQLite specific settings: WAL mode and aggressive caching
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        # WAL mode for concurrent read/write
        cursor.execute("PRAGMA journal_mode=WAL")
        # NORMAL sync mode for better write throughput
        cursor.execute("PRAGMA synchronous=NORMAL")
        # Enforce foreign key constraints
        cursor.execute("PRAGMA foreign_keys=ON")
        # Increase cache to 64MB for faster queries
        cursor.execute("PRAGMA cache_size=262144")
        # Increase temp store for complex queries
        cursor.execute("PRAGMA temp_store=MEMORY")
        # Enable memory-mapped I/O
        cursor.execute("PRAGMA mmap_size=268435456")
        # Optimize write-ahead logging
        cursor.execute("PRAGMA wal_autocheckpoint=1000")
        cursor.close()

    def _sqlite_db_path() -> str:
        if DATABASE_URL.startswith("sqlite:///"):
            return os.path.abspath(DATABASE_URL.replace("sqlite:///", ""))
        return os.path.abspath(DATABASE_URL.replace("sqlite://", ""))

    def _sqlite_column_exists(connection, table_name: str, column_name: str) -> bool:
        result = connection.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()
        return any(row["name"] == column_name for row in result)

    def _ensure_sqlite_schema():
        db_path = _sqlite_db_path()
        if not os.path.exists(db_path):
            return

        with engine.begin() as conn:
            if conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='users' LIMIT 1")).fetchone():
                if not _sqlite_column_exists(conn, "users", "email_verified"):
                    conn.execute(text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT 0"))
                if not _sqlite_column_exists(conn, "users", "mfa_enabled"):
                    conn.execute(text("ALTER TABLE users ADD COLUMN mfa_enabled BOOLEAN DEFAULT 0"))
            if conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='agent_tasks' LIMIT 1")).fetchone():
                if not _sqlite_column_exists(conn, "agent_tasks", "updated_at"):
                    conn.execute(text("ALTER TABLE agent_tasks ADD COLUMN updated_at DATETIME"))

    _ensure_sqlite_schema()

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)

Base = declarative_base()

def get_db():
    """Dependency for FastAPI to inject database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@contextmanager
def get_db_context():
    """Context manager for manual session management."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
