"""
Enhanced error handling and categorization for workflow execution.
Distinguishes between transient and permanent errors for smart retry logic.
"""

import json
from enum import Enum
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime


class ErrorCategory(Enum):
    """Error classification for retry logic."""
    TRANSIENT = "transient"      # Retry-able (network, timeout, rate-limit)
    PERMANENT = "permanent"      # Non-retry-able (invalid model, bad request)
    MODEL_UNAVAILABLE = "model_unavailable"  # Model not found/deprecated
    AUTH_ERROR = "auth_error"    # API key, permissions
    RATE_LIMITED = "rate_limited"  # Quota exceeded
    TIMEOUT = "timeout"          # Connection/execution timeout
    UNKNOWN = "unknown"          # Unknown error


class WorkflowError:
    """Structured error information for workflow nodes."""
    
    def __init__(
        self,
        message: str,
        category: ErrorCategory,
        original_error: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.category = category
        self.original_error = original_error
        self.context = context or {}
        self.timestamp = datetime.utcnow().isoformat()
    
    def is_retryable(self) -> bool:
        """Check if this error should trigger a retry."""
        return self.category in [
            ErrorCategory.TRANSIENT,
            ErrorCategory.RATE_LIMITED,
            ErrorCategory.TIMEOUT,
        ]
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for logging/storage."""
        return {
            "message": self.message,
            "category": self.category.value,
            "is_retryable": self.is_retryable(),
            "timestamp": self.timestamp,
            "context": self.context,
            "original_error": str(self.original_error) if self.original_error else None,
        }


def categorize_gemini_error(error: Exception) -> Tuple[ErrorCategory, str]:
    """
    Categorize Gemini API errors for intelligent retry logic.
    
    Returns: (ErrorCategory, human_readable_message)
    """
    error_str = str(error).lower()
    error_full = str(error)
    
    # Model not found / not supported
    if "404" in error_str or "not found" in error_str:
        if "model" in error_str:
            return (
                ErrorCategory.MODEL_UNAVAILABLE,
                f"Model not available in v1beta. Try gemini-pro or gemini-1.5-pro. Error: {error_full}",
            )
        return ErrorCategory.PERMANENT, f"404 Resource not found: {error_full}"
    
    # Authentication errors
    if "401" in error_str or "403" in error_str or "unauthorized" in error_str or "permission" in error_str:
        return ErrorCategory.AUTH_ERROR, f"Invalid API key or permissions: {error_full}"
    
    # Rate limiting
    if "429" in error_str or "rate" in error_str or "quota" in error_str:
        return ErrorCategory.RATE_LIMITED, f"Rate limited. Retry later: {error_full}"
    
    # Timeout errors
    if "timeout" in error_str or "deadline" in error_str:
        return ErrorCategory.TIMEOUT, f"Request timeout (retry expected): {error_full}"
    
    # Network errors
    if any(x in error_str for x in ["connection", "network", "socket", "refused"]):
        return ErrorCategory.TRANSIENT, f"Network error (transient): {error_full}"
    
    # Default: unknown transient error (safer to retry)
    return ErrorCategory.UNKNOWN, f"Unknown error (will retry): {error_full}"


def categorize_http_error(status_code: int, error_body: str = "") -> Tuple[ErrorCategory, str]:
    """
    Categorize HTTP error codes for retry logic.
    
    Returns: (ErrorCategory, human_readable_message)
    """
    if status_code == 404:
        return ErrorCategory.PERMANENT, f"Resource not found (404)"
    elif status_code == 400:
        return ErrorCategory.PERMANENT, f"Bad request (400): {error_body}"
    elif status_code == 401:
        return ErrorCategory.AUTH_ERROR, f"Unauthorized (401)"
    elif status_code == 403:
        return ErrorCategory.AUTH_ERROR, f"Forbidden (403)"
    elif status_code == 429:
        return ErrorCategory.RATE_LIMITED, f"Rate limited (429) - retry later"
    elif 500 <= status_code < 600:
        return ErrorCategory.TRANSIENT, f"Server error ({status_code}) - retry expected"
    elif 300 <= status_code < 400:
        return ErrorCategory.TRANSIENT, f"Redirect ({status_code}) - may be transient"
    else:
        return ErrorCategory.TRANSIENT, f"HTTP error {status_code}"


# Available Gemini models in priority order (most recent first)
GEMINI_MODEL_FALLBACKS = [
    "gemini-1.5-pro",       # Recommended
    "gemini-1.5-flash",     # Fallback (free tier)
    "gemini-pro",           # Legacy
]


def get_available_gemini_models() -> List[str]:
    """Get list of Gemini models to try, in order."""
    return GEMINI_MODEL_FALLBACKS


def format_error_context(
    error: Exception,
    node_id: str,
    node_type: str,
    attempt: int = 1,
    max_attempts: int = 3,
) -> Dict[str, Any]:
    """
    Create detailed error context for logging and monitoring.
    
    Returns:
        Dictionary with full error context for debugging
    """
    category, description = categorize_gemini_error(error) if "gemini" in node_type.lower() else (ErrorCategory.UNKNOWN, str(error))
    
    return {
        "node_id": node_id,
        "node_type": node_type,
        "error_category": category.value,
        "error_message": description,
        "attempt": attempt,
        "max_attempts": max_attempts,
        "is_retryable": category in [
            ErrorCategory.TRANSIENT,
            ErrorCategory.RATE_LIMITED,
            ErrorCategory.TIMEOUT,
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }
