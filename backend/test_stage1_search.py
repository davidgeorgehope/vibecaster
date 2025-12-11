#!/usr/bin/env python3
"""
Test for Stage 1: search_trending_topics function.
This test helps diagnose issues with Gemini API responses returning None.

Run with: python test_stage1_search.py
"""

import os
import sys
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add backend to path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)


def test_raw_gemini_search():
    """Test Gemini API with Google Search grounding directly."""
    from google import genai
    from google.genai import types

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[SKIP] GEMINI_API_KEY not set")
        return None

    client = genai.Client(api_key=api_key)

    # Use the same model as agents.py
    model = "gemini-3-pro-preview"

    test_prompt = """
USER'S FULL INSTRUCTIONS: Find recent Elastic Security content from the last week.

YOUR TASK: Find content that FITS this creative format while STRICTLY RESPECTING any source restrictions above.

Provide:
1. A summary of content found
2. Key concepts or topics
3. Source URLs
"""

    print(f"[TEST] Calling Gemini with Google Search grounding...")
    print(f"[TEST] Model: {model}")

    try:
        response = client.models.generate_content(
            model=model,
            contents=test_prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                tools=[types.Tool(google_search=types.GoogleSearch())],
                thinking_config=types.ThinkingConfig(
                    thinking_level="HIGH"
                )
            )
        )

        print("\n" + "=" * 60)
        print("RESPONSE ANALYSIS")
        print("=" * 60)

        # Check response.text
        print(f"\n[1] response.text is None: {response.text is None}")
        print(f"[2] response.text is empty string: {response.text == ''}")
        print(f"[3] response.text value: {repr(response.text)[:200] if response.text else 'None'}")

        # Check candidates
        print(f"\n[4] Has candidates: {hasattr(response, 'candidates')}")
        if hasattr(response, 'candidates'):
            print(f"[5] Number of candidates: {len(response.candidates) if response.candidates else 0}")

            if response.candidates:
                for i, candidate in enumerate(response.candidates):
                    print(f"\n--- Candidate {i} ---")
                    print(f"  finish_reason: {getattr(candidate, 'finish_reason', 'N/A')}")

                    if hasattr(candidate, 'safety_ratings') and candidate.safety_ratings:
                        print(f"  safety_ratings: {candidate.safety_ratings}")

                    if hasattr(candidate, 'content'):
                        content = candidate.content
                        print(f"  content.role: {getattr(content, 'role', 'N/A')}")
                        if hasattr(content, 'parts') and content.parts:
                            print(f"  content.parts count: {len(content.parts)}")
                            for j, part in enumerate(content.parts):
                                part_type = type(part).__name__
                                print(f"    part[{j}] type: {part_type}")
                                if hasattr(part, 'text'):
                                    text_preview = part.text[:100] if part.text else 'None'
                                    print(f"    part[{j}].text: {repr(text_preview)}")
                                if hasattr(part, 'thought') and part.thought:
                                    print(f"    part[{j}] is THOUGHT (thinking output)")

                    # Check grounding metadata
                    if hasattr(candidate, 'grounding_metadata'):
                        metadata = candidate.grounding_metadata
                        print(f"  grounding_metadata present: True")
                        if hasattr(metadata, 'grounding_chunks') and metadata.grounding_chunks:
                            print(f"    grounding_chunks count: {len(metadata.grounding_chunks)}")
                            for k, chunk in enumerate(metadata.grounding_chunks[:3]):  # First 3
                                if hasattr(chunk, 'web'):
                                    print(f"      chunk[{k}].web.uri: {getattr(chunk.web, 'uri', 'N/A')[:60]}")

        # Check usage metadata
        if hasattr(response, 'usage_metadata'):
            usage = response.usage_metadata
            print(f"\n[6] Usage metadata:")
            print(f"    prompt_tokens: {getattr(usage, 'prompt_token_count', 'N/A')}")
            print(f"    candidates_tokens: {getattr(usage, 'candidates_token_count', 'N/A')}")
            print(f"    total_tokens: {getattr(usage, 'total_token_count', 'N/A')}")
            if hasattr(usage, 'thoughts_token_count'):
                print(f"    thoughts_tokens: {usage.thoughts_token_count}")

        return response

    except Exception as e:
        print(f"[ERROR] API call failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_search_trending_topics():
    """Test the actual search_trending_topics function."""
    print("\n" + "=" * 60)
    print("TESTING search_trending_topics FUNCTION")
    print("=" * 60)

    try:
        from agents import search_trending_topics

        user_prompt = "Elastic Security concepts, recent developments"
        persona = "Technical educator specializing in Elastic Security"
        recent_topics = []

        print(f"[TEST] Calling search_trending_topics...")
        print(f"  user_prompt: {user_prompt}")
        print(f"  persona: {persona[:50]}...")
        print(f"  validate_urls: False")

        search_context, source_urls, html_content = search_trending_topics(
            user_prompt=user_prompt,
            refined_persona=persona,
            recent_topics=recent_topics,
            validate_urls=False  # Skip URL validation for speed
        )

        print(f"\n[RESULT]")
        print(f"  search_context is None: {search_context is None}")
        print(f"  search_context type: {type(search_context)}")
        if search_context:
            print(f"  search_context length: {len(search_context)}")
            print(f"  search_context preview: {search_context[:300]}...")
        else:
            print(f"  search_context value: {repr(search_context)}")

        print(f"\n  source_urls count: {len(source_urls) if source_urls else 0}")
        if source_urls:
            for url in source_urls[:3]:
                print(f"    - {url[:80]}")

        print(f"\n  html_content is None: {html_content is None}")

        return search_context, source_urls, html_content

    except Exception as e:
        print(f"[ERROR] search_trending_topics failed: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None


def test_response_text_property():
    """Test how response.text property works with thinking models."""
    from google import genai
    from google.genai import types

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[SKIP] GEMINI_API_KEY not set")
        return

    client = genai.Client(api_key=api_key)

    print("\n" + "=" * 60)
    print("TESTING response.text PROPERTY BEHAVIOR")
    print("=" * 60)

    # Test without Google Search (simpler case)
    print("\n[TEST 1] Simple prompt without Google Search...")
    try:
        response = client.models.generate_content(
            model="gemini-3-pro-preview",
            contents="Say hello in one word.",
            config=types.GenerateContentConfig(
                temperature=0.1,
                thinking_config=types.ThinkingConfig(thinking_level="LOW")
            )
        )
        print(f"  response.text: {repr(response.text)}")

        # Also check parts manually
        if response.candidates and response.candidates[0].content.parts:
            print(f"  Parts breakdown:")
            for i, part in enumerate(response.candidates[0].content.parts):
                if hasattr(part, 'thought') and part.thought:
                    print(f"    part[{i}]: THOUGHT")
                elif hasattr(part, 'text'):
                    print(f"    part[{i}]: TEXT = {repr(part.text[:50] if part.text else None)}")
    except Exception as e:
        print(f"  Error: {e}")

    # Test with Google Search
    print("\n[TEST 2] Prompt with Google Search grounding...")
    try:
        response = client.models.generate_content(
            model="gemini-3-pro-preview",
            contents="What is the current date? Just tell me today's date.",
            config=types.GenerateContentConfig(
                temperature=0.1,
                tools=[types.Tool(google_search=types.GoogleSearch())],
                thinking_config=types.ThinkingConfig(thinking_level="LOW")
            )
        )
        print(f"  response.text: {repr(response.text)[:100] if response.text else 'None'}")

        if response.candidates and response.candidates[0].content.parts:
            print(f"  Parts breakdown:")
            for i, part in enumerate(response.candidates[0].content.parts):
                if hasattr(part, 'thought') and part.thought:
                    print(f"    part[{i}]: THOUGHT")
                elif hasattr(part, 'text'):
                    print(f"    part[{i}]: TEXT = {repr(part.text[:50] if part.text else None)}")
    except Exception as e:
        print(f"  Error: {e}")


def main():
    print("=" * 60)
    print("Stage 1 Search Test Suite")
    print("=" * 60)

    # Test 1: Raw Gemini API
    print("\n\n>>> TEST 1: Raw Gemini API with Google Search <<<")
    response = test_raw_gemini_search()

    # Test 2: response.text property behavior
    print("\n\n>>> TEST 2: response.text property behavior <<<")
    test_response_text_property()

    # Test 3: Actual function
    print("\n\n>>> TEST 3: search_trending_topics function <<<")
    context, urls, html = test_search_trending_topics()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    if context is None:
        print("[FAIL] search_context is None - this is the bug!")
        print("\nPossible causes:")
        print("  1. response.text returns None when using thinking models")
        print("  2. The API returned no candidates")
        print("  3. Safety filter blocked the response")
        print("  4. All content is in 'thought' parts, not 'text' parts")
    else:
        print("[PASS] search_context has content")
        print(f"  Length: {len(context)} chars")
        print(f"  URLs found: {len(urls)}")


if __name__ == "__main__":
    main()
