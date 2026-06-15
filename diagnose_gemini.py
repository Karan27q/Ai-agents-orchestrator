#!/usr/bin/env python3
"""
Gemini API Configuration Diagnostic Tool
Helps identify and fix Gemini API issues.
"""

import os
import sys
from typing import Optional, List

try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False
    print("❌ google-generativeai not installed. Install with: pip install google-generativeai")
    sys.exit(1)


def test_api_key(api_key: Optional[str] = None) -> bool:
    """Test if API key is valid and accessible."""
    if not api_key:
        api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        print("❌ GEMINI_API_KEY not set in environment")
        return False
    
    try:
        genai.configure(api_key=api_key)
        print(f"✅ API Key configured (length: {len(api_key)})")
        return True
    except Exception as e:
        print(f"❌ API Key configuration failed: {e}")
        return False


def list_available_models(api_key: Optional[str] = None) -> List[str]:
    """List all available Gemini models."""
    if not api_key:
        api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        print("❌ Cannot list models - API key not available")
        return []
    
    try:
        genai.configure(api_key=api_key)
        models = genai.list_models()
        
        available = []
        print("\n📦 Available Models:")
        print("-" * 60)
        for model in models:
            name = model.name.replace("models/", "")
            available.append(name)
            
            # Check if supports generateContent
            supports_generate = any(
                method.name == "generateContent" 
                for method in model.supported_generation_methods
            )
            
            status = "✅" if supports_generate else "⚠️"
            print(f"{status} {name:<30} (v{getattr(model, 'version', 'unknown')})")
        
        return available
    except Exception as e:
        print(f"❌ Failed to list models: {e}")
        return []


def test_model(model_name: str, api_key: Optional[str] = None) -> bool:
    """Test if a specific model works."""
    if not api_key:
        api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        print("❌ API key not available")
        return False
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        
        # Simple test prompt
        response = model.generate_content("Say 'Hello' in one word.")
        
        print(f"✅ Model '{model_name}' works!")
        print(f"   Response: {response.text[:100]}")
        return True
    
    except Exception as e:
        error_str = str(e).lower()
        
        if "404" in error_str or "not found" in error_str:
            print(f"❌ Model '{model_name}' not found or not supported in v1beta")
            print(f"   Try one of the available models listed above")
        elif "429" in error_str or "quota" in error_str:
            print(f"⚠️  Model '{model_name}' rate limited or quota exceeded")
        elif "401" in error_str or "unauthorized" in error_str:
            print(f"❌ Unauthorized - check API key")
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
    
    for model_name in GEMINI_MODEL_FALLBACKS:
        print(f"\n   Testing: {model_name}")
        test_model(model_name, api_key)
    
    # Recommendations
    print("\n" + "=" * 60)
    print("💡 Recommendations:")
    print("=" * 60)
    
    working_models = []
    for model in GEMINI_MODEL_FALLBACKS:
        try:
            genai.configure(api_key=api_key)
            genai.GenerativeModel(model)
            working_models.append(model)
        except:
            pass
    
    if working_models:
        print(f"\n✅ Working models: {', '.join(working_models)}")
        print(f"\n   Update error_handler.py:")
        print(f"   GEMINI_MODEL_FALLBACKS = {working_models}")
    else:
        available_short = [m for m in models if "flash" in m or "pro" in m]
        if available_short:
            print(f"\n✅ Recommended to try: {available_short[0]}")
            print(f"\n   Update error_handler.py:")
            print(f"   GEMINI_MODEL_FALLBACKS = ['{available_short[0]}']")
        else:
            print(f"\n⚠️  No recommended models found")
            print(f"   Available: {models[:3]}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
