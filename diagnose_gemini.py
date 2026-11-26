#!/usr/bin/env python3
"""
Gemini API Configuration Diagnostic Tool

Uses the project's httpx-based Gemini client (no google-generativeai / gRPC).
Run from the repository root:

    python diagnose_gemini.py
"""

import os
import sys
from typing import List, Optional

# Windows consoles default to cp1252 and crash on the emoji below.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# The client lives in backend/; make it importable when run from the repo root.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))

# Load the same .env files the app uses (backend/.env first, then repo root)
# before importing the client, which reads model settings at import time.
try:
    from dotenv import load_dotenv

    repo_root = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(repo_root, "backend", ".env"))
    load_dotenv(os.path.join(repo_root, ".env"))
except ImportError:
    pass

try:
    import gemini_client
except ImportError as exc:  # pragma: no cover - only hit on a broken checkout
    print(f"❌ Could not import gemini_client: {exc}")
    sys.exit(1)


def test_api_key(api_key: Optional[str] = None) -> bool:
    """Test if an API key is present and accepted by the API."""
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        print("❌ GEMINI_API_KEY not set in environment")
        return False

    print(f"✅ API key found (length: {len(key)})")
    try:
        gemini_client.list_models(api_key=key)
        print("✅ API key accepted by the Gemini API")
        return True
    except Exception as e:
        print(f"❌ API key rejected or API unreachable: {e}")
        return False


def list_available_models(api_key: Optional[str] = None) -> List[str]:
    """List all available Gemini models that support generateContent."""
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        print("❌ Cannot list models - API key not available")
        return []

    try:
        models = gemini_client.list_models(api_key=key)
    except Exception as e:
        print(f"❌ Failed to list models: {e}")
        return []

    available: List[str] = []
    print("\n📦 Available Models:")
    print("-" * 60)
    for model in models:
        name = (model.get("name") or "").replace("models/", "")
        if not name:
            continue

        methods = model.get("supportedGenerationMethods") or []
        supports_generate = "generateContent" in methods
        if supports_generate:
            available.append(name)

        status = "✅" if supports_generate else "⚠️"
        print(f"{status} {name:<30} (v{model.get('version', 'unknown')})")

    return available


def test_model(model_name: str, api_key: Optional[str] = None) -> bool:
    """Test if a specific model works."""
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        print("❌ API key not available")
        return False

    try:
        text = gemini_client.generate_content(
            "Say 'Hello' in one word.",
            model=model_name,
            api_key=key,
        )
        print(f"✅ Model '{model_name}' works!")
        print(f"   Response: {text[:100]}")
        return True

    except Exception as e:
        error_str = str(e).lower()

        if "404" in error_str or "not found" in error_str:
            print(f"❌ Model '{model_name}' not found or not supported in v1beta")
            print("   Try one of the available models listed above")
        elif "429" in error_str or "quota" in error_str:
            print(f"⚠️  Model '{model_name}' rate limited or quota exceeded")
        elif "401" in error_str or "403" in error_str or "unauthorized" in error_str:
            print("❌ Unauthorized - check API key")
        else:
            print(f"❌ Error testing model '{model_name}': {e}")

        return False


def main():
    """Run full diagnostic."""
    print("=" * 60)
    print("🔧 Gemini API Configuration Diagnostic")
    print("=" * 60)

    # Check API key
    print("\n1️⃣  Checking API Key...")
    api_key = os.getenv("GEMINI_API_KEY")
    if not test_api_key(api_key):
        print("\n📝 Set API key with:")
        print("   export GEMINI_API_KEY='your-key-here'")
        return

    # List available models
    print("\n2️⃣  Checking Available Models...")
    models = list_available_models(api_key)

    if not models:
        print("\n❌ No models available. Check your API key or quota.")
        return

    # Test current configuration models
    print("\n3️⃣  Testing Current Configuration Models...")
    from error_handler import GEMINI_MODEL_FALLBACKS

    working_models = []
    for model_name in GEMINI_MODEL_FALLBACKS:
        print(f"\n   Testing: {model_name}")
        if test_model(model_name, api_key):
            working_models.append(model_name)

    # Recommendations
    print("\n" + "=" * 60)
    print("💡 Recommendations:")
    print("=" * 60)

    if working_models:
        print(f"\n✅ Working models: {', '.join(working_models)}")
        print("\n   Pin the default model with:")
        print(f"   GEMINI_MODEL={working_models[0]}")
    else:
        available_short = [
            m for m in models if "hydrogen" in m or "flash" in m or "pro" in m
        ]
        if available_short:
            print(f"\n✅ Recommended to try: {available_short[0]}")
            print("\n   Pin the default model with:")
            print(f"   GEMINI_MODEL={available_short[0]}")
        else:
            print("\n⚠️  No recommended models found")
            print(f"   Available: {models[:3]}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
