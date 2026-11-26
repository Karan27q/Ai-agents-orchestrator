"""
Minimal Gemini client built directly on ``httpx``.

This replaces the ``google-generativeai`` SDK (which pulls in gRPC,
google-api-core and google-auth: roughly 22 MB of wheels) with plain REST
calls.  It also fixes the ``system_instruction`` mismatch: the SDK version
the project pinned (0.4.1) does not accept that argument, so every
research call used to raise ``TypeError`` before the model was ever called.

Public surface:
    is_configured()               -> bool
    generate_content(...)         -> str
    generate_content_stream(...)  -> Iterator[str]
    embed_texts(...)              -> List[List[float]]
    list_models()                 -> List[dict]
"""

import json
import os
import threading
from typing import Any, Dict, Iterator, List, Optional

import httpx

API_BASE = os.getenv("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta")
# Gemini 4 Hydrogen is the current default general-purpose model. Override with
# GEMINI_MODEL to pin a specific model (e.g. gemini-4-carbon for deep reasoning).
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-4-hydrogen")
# Gemini Embedding 2 is the current multimodal embedding model. Its embedding
# space is incompatible with older models, so re-index stored documents when
# switching between them.
EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-2")
# Output dimensionality. 768 keeps the existing DB schema (Vector(768)).
EMBED_DIM = int(os.getenv("GEMINI_EMBED_DIM", "768"))
DEFAULT_TIMEOUT = float(os.getenv("GEMINI_TIMEOUT", "120"))
EMBED_BATCH_SIZE = int(os.getenv("GEMINI_EMBED_BATCH_SIZE", "100"))

# gemini-embedding-2 does not accept `taskType`; instead the task is expressed
# as a prefix on the text. Documents and queries must use matching formats.
_EMBED2_TASK_PREFIXES = {
    "RETRIEVAL_DOCUMENT": "title: {title} | text: {text}",
    "RETRIEVAL_QUERY": "task: search result | query: {text}",
    "QUESTION_ANSWERING": "task: question answering | query: {text}",
    "FACT_VERIFICATION": "task: fact checking | query: {text}",
    "CODE_RETRIEVAL_QUERY": "task: code retrieval | query: {text}",
    "CLASSIFICATION": "task: classification | query: {text}",
    "CLUSTERING": "task: clustering | query: {text}",
    "SEMANTIC_SIMILARITY": "task: sentence similarity | query: {text}",
}

_client: Optional[httpx.Client] = None
_client_lock = threading.Lock()


class GeminiError(RuntimeError):
    """Raised for transport failures and any non-2xx Gemini response."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def get_api_key() -> Optional[str]:
    return os.getenv("GEMINI_API_KEY") or None


def is_configured() -> bool:
    return bool(get_api_key())


def _get_client() -> httpx.Client:
    global _client
    with _client_lock:
        if _client is None or _client.is_closed:
            _client = httpx.Client(
                base_url=API_BASE,
                timeout=DEFAULT_TIMEOUT,
                headers={"Content-Type": "application/json"},
            )
        return _client


def _model_path(model: str) -> str:
    """REST paths take ``models/<id>``; callers may pass either form."""
    return model[len("models/"):] if model.startswith("models/") else model


def _headers(api_key: Optional[str] = None) -> Dict[str, str]:
    key = api_key or get_api_key()
    if not key:
        raise GeminiError("GEMINI_API_KEY is not set")
    return {"x-goog-api-key": key}


def _raise_for_response(response: httpx.Response) -> None:
    if response.is_success:
        return

    try:
        payload = response.json()
        message = (payload.get("error") or {}).get("message") or response.text
    except Exception:
        message = response.text

    # Include the status code in the text: error_handler.categorize_gemini_error
    # classifies errors by inspecting str(error) for 401/403/404/429/timeout.
    raise GeminiError(
        f"Gemini API error {response.status_code}: {message}",
        status_code=response.status_code,
    )


def _build_payload(
    prompt: str,
    system_instruction: str = "",
    generation_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
    }
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
    if generation_config:
        payload["generationConfig"] = generation_config
    return payload


def _extract_text(payload: Dict[str, Any], strict: bool = False) -> str:
    parts: List[str] = []
    candidates = payload.get("candidates") or []
    for candidate in candidates:
        content = candidate.get("content") or {}
        for part in content.get("parts") or []:
            # Gemini 4 emits internal reasoning as parts flagged `thought`;
            # never surface those in the final answer.
            if part.get("thought"):
                continue
            text = part.get("text")
            if text:
                parts.append(text)

    if not parts:
        block_reason = (payload.get("promptFeedback") or {}).get("blockReason")
        if block_reason:
            raise GeminiError(f"Gemini blocked the request: {block_reason}")
        if strict:
            finish_reason = candidates[0].get("finishReason") if candidates else None
            raise GeminiError(
                f"Gemini returned no text (finishReason={finish_reason or 'unknown'})"
            )

    return "".join(parts)


def generate_content(
    prompt: str,
    model: str = DEFAULT_MODEL,
    system_instruction: str = "",
    generation_config: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
) -> str:
    """Single-shot text generation. Blocking; call it from a thread."""
    response = _get_client().post(
        f"/models/{_model_path(model)}:generateContent",
        headers=_headers(api_key),
        json=_build_payload(prompt, system_instruction, generation_config),
    )
    _raise_for_response(response)
    return _extract_text(response.json(), strict=True)


def generate_content_stream(
    prompt: str,
    model: str = DEFAULT_MODEL,
    system_instruction: str = "",
    generation_config: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
) -> Iterator[str]:
    """Yield text deltas from ``streamGenerateContent`` (SSE)."""
    body = _build_payload(prompt, system_instruction, generation_config)
    with _get_client().stream(
        "POST",
        f"/models/{_model_path(model)}:streamGenerateContent",
        params={"alt": "sse"},
        headers=_headers(api_key),
        json=body,
    ) as response:
        if not response.is_success:
            # Drain the body so the error message is available.
            response.read()
            _raise_for_response(response)

        for line in response.iter_lines():
            if not line:
                continue
            if line.startswith("data:"):
                line = line[len("data:"):].strip()
            if not line or line == "[DONE]":
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue

            text = _extract_text(chunk)
            if text:
                yield text


def _is_embedding_2(model_path: str) -> bool:
    return model_path.startswith("gemini-embedding-2")


def _format_embedding_input(text: str, task_type: str, title: Optional[str]) -> str:
    """Apply the task prefix format required by gemini-embedding-2."""
    template = _EMBED2_TASK_PREFIXES.get(task_type.upper())
    if not template:
        return text
    return template.format(title=title or "none", text=text)


def embed_texts(
    texts: List[str],
    model: str = EMBED_MODEL,
    task_type: str = "RETRIEVAL_DOCUMENT",
    dimensions: Optional[int] = None,
    batch_size: int = EMBED_BATCH_SIZE,
    api_key: Optional[str] = None,
) -> List[List[float]]:
    """Embed a list of strings via ``batchEmbedContents``."""
    if not texts:
        return []

    model_path = _model_path(model)
    embedding_2 = _is_embedding_2(model_path)
    dims = EMBED_DIM if dimensions is None else dimensions
    headers = _headers(api_key)
    vectors: List[List[float]] = []

    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        requests = []
        for text in batch:
            item: Dict[str, Any] = {
                "model": f"models/{model_path}",
                "content": {
                    "parts": [
                        {
                            "text": _format_embedding_input(text, task_type, None)
                            if embedding_2
                            else text
                        }
                    ]
                },
            }
            if embedding_2:
                item["outputDimensionality"] = dims
            else:
                item["taskType"] = task_type.upper()
                if model_path.startswith("gemini-embedding"):
                    item["outputDimensionality"] = dims
            requests.append(item)

        response = _get_client().post(
            f"/models/{model_path}:batchEmbedContents",
            headers=headers,
            json={"requests": requests},
        )
        _raise_for_response(response)

        embeddings = response.json().get("embeddings") or []
        if len(embeddings) != len(batch):
            raise GeminiError(
                f"Gemini returned {len(embeddings)} embeddings for {len(batch)} inputs"
            )
        vectors.extend(item["values"] for item in embeddings)

    return vectors


def list_models(api_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """List models available to the configured API key."""
    response = _get_client().get(
        "/models",
        headers=_headers(api_key),
        params={"pageSize": 1000},
    )
    _raise_for_response(response)
    return response.json().get("models") or []
