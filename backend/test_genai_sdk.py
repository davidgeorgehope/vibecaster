#!/usr/bin/env python3
"""
Quick test to verify Google GenAI SDK is working with thinking_config.
Run with: python test_genai_sdk.py
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_sdk_version():
    """Test that we have the correct SDK version installed."""
    import google.genai
    from importlib.metadata import version

    sdk_version = version('google-genai')
    print(f"[TEST] google-genai version: {sdk_version}")

    # Check version is >= 1.52.0
    major, minor, patch = map(int, sdk_version.split('.')[:3])
    assert major >= 1, f"SDK version too old: {sdk_version}"
    if major == 1:
        assert minor >= 52, f"SDK version too old: {sdk_version}"

    print("[PASS] SDK version is compatible")
    return True


def test_types_available():
    """Test that all required types are available."""
    from google.genai import types

    # Check ThinkingConfig exists
    assert hasattr(types, 'ThinkingConfig'), "ThinkingConfig not found in types"
    print("[PASS] types.ThinkingConfig available")

    # Check ThinkingLevel exists
    assert hasattr(types, 'ThinkingLevel'), "ThinkingLevel not found in types"
    print("[PASS] types.ThinkingLevel available")

    # Check GenerateContentConfig exists
    assert hasattr(types, 'GenerateContentConfig'), "GenerateContentConfig not found in types"
    print("[PASS] types.GenerateContentConfig available")

    # Check Tool and GoogleSearch exist
    assert hasattr(types, 'Tool'), "Tool not found in types"
    assert hasattr(types, 'GoogleSearch'), "GoogleSearch not found in types"
    print("[PASS] types.Tool and types.GoogleSearch available")

    return True


def test_config_creation():
    """Test that we can create configs with thinking_config."""
    from google.genai import types

    # Test creating ThinkingConfig
    thinking_config = types.ThinkingConfig(thinking_level="HIGH")
    assert thinking_config.thinking_level.value == "HIGH"
    print("[PASS] ThinkingConfig creation works")

    # Test creating GenerateContentConfig with thinking_config
    config = types.GenerateContentConfig(
        temperature=0.7,
        thinking_config=types.ThinkingConfig(thinking_level="HIGH")
    )
    assert config.thinking_config is not None
    assert config.temperature == 0.7
    print("[PASS] GenerateContentConfig with thinking_config works")

    # Test with response_mime_type
    config_json = types.GenerateContentConfig(
        temperature=0.5,
        response_mime_type="application/json",
        thinking_config=types.ThinkingConfig(thinking_level="HIGH")
    )
    assert config_json.response_mime_type == "application/json"
    print("[PASS] GenerateContentConfig with response_mime_type works")

    # Test with tools (Google Search)
    config_search = types.GenerateContentConfig(
        temperature=0.7,
        tools=[types.Tool(google_search=types.GoogleSearch())],
        thinking_config=types.ThinkingConfig(thinking_level="HIGH")
    )
    assert config_search.tools is not None
    assert len(config_search.tools) == 1
    print("[PASS] GenerateContentConfig with Google Search tools works")

    # Test with response_modalities for image generation
    config_image = types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        thinking_config=types.ThinkingConfig(thinking_level="HIGH")
    )
    assert config_image.response_modalities is not None
    print("[PASS] GenerateContentConfig with response_modalities works")

    return True


def test_api_call():
    """Test actual API calls with the production models."""
    from google import genai
    from google.genai import types

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[SKIP] GEMINI_API_KEY not set, skipping API call test")
        return True

    client = genai.Client(api_key=api_key)

    # Test 1: gemini-3-pro-preview with thinking_config
    print("[TEST] Testing gemini-3-pro-preview with thinking_config...")
    try:
        response = client.models.generate_content(
            model="gemini-3-pro-preview",
            contents="What is 2+2? Reply with just the number.",
            config=types.GenerateContentConfig(
                temperature=0.1,
                thinking_config=types.ThinkingConfig(
                    thinking_level="LOW"
                )
            )
        )
        result = response.text.strip()
        print(f"[TEST] Response: {result}")
        assert "4" in result, f"Unexpected response: {result}"
        print("[PASS] gemini-3-pro-preview with thinking_config works")
    except Exception as e:
        print(f"[FAIL] gemini-3-pro-preview failed: {e}")
        return False

    # Test 2: gemini-3-pro-preview with JSON response
    print("[TEST] Testing gemini-3-pro-preview with JSON response...")
    try:
        response = client.models.generate_content(
            model="gemini-3-pro-preview",
            contents='Return a JSON object with key "answer" and value 4',
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(
                    thinking_level="LOW"
                )
            )
        )
        result = response.text.strip()
        print(f"[TEST] JSON Response: {result}")
        assert "4" in result, f"Unexpected response: {result}"
        print("[PASS] gemini-3-pro-preview with JSON response works")
    except Exception as e:
        print(f"[FAIL] gemini-3-pro-preview JSON failed: {e}")
        return False

    # Test 3: gemini-3-pro-image-preview (just verify model exists)
    print("[TEST] Testing gemini-3-pro-image-preview availability...")
    try:
        # Just test that we can create a valid config for image generation
        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            thinking_config=types.ThinkingConfig(
                thinking_level="HIGH"
            )
        )
        print(f"[TEST] Image config created: {config.response_modalities}")
        print("[PASS] gemini-3-pro-image-preview config works")
        print("[INFO] Skipping actual image generation to save API costs")
    except Exception as e:
        print(f"[FAIL] gemini-3-pro-image-preview config failed: {e}")
        return False

    return True


def test_agents_import():
    """Test that agents.py imports without errors."""
    try:
        # Add the backend directory to path if needed
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)

        import agents
        print("[PASS] agents.py imports successfully")
        return True
    except Exception as e:
        print(f"[FAIL] agents.py import failed: {e}")
        return False


def main():
    print("=" * 60)
    print("Google GenAI SDK Test Suite")
    print("=" * 60)
    print()

    tests = [
        ("SDK Version", test_sdk_version),
        ("Types Available", test_types_available),
        ("Config Creation", test_config_creation),
        ("Agents Import", test_agents_import),
        ("API Call", test_api_call),
    ]

    results = []
    for name, test_func in tests:
        print(f"\n--- {name} ---")
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"[FAIL] {name}: {e}")
            results.append((name, False))

    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("All tests passed!")
        return 0
    else:
        print("Some tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
