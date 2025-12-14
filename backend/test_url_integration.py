"""
Test script to verify URL integration in the production code.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Import the functions from agents
from agents import search_trending_topics, generate_post_draft

def test_url_integration():
    """Test the URL integration end-to-end."""

    print("=" * 80)
    print("Testing URL Integration in Production Code")
    print("=" * 80)

    user_prompt = "artificial intelligence and machine learning"
    refined_persona = "A tech enthusiast who shares the latest AI developments with a casual, excited tone"

    # Test 1: Search with URL extraction
    print("\n[Test 1] Searching for trending topics with URL extraction...")
    try:
        search_context, source_urls, _html_content = search_trending_topics(user_prompt, refined_persona)

        print(f"✓ Search completed")
        print(f"✓ Found {len(source_urls)} URLs")
        print(f"\nSearch context preview: {search_context[:200]}...")

        if source_urls:
            print(f"\nFirst URL: {source_urls[0][:100]}...")
        else:
            print("\n⚠ No URLs found")
            return False

    except Exception as e:
        print(f"✗ Error in search: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Test 2: Generate post with URL
    print("\n[Test 2] Generating post draft with URL...")
    try:
        source_url = source_urls[0] if source_urls else None
        draft = generate_post_draft(search_context, refined_persona, user_prompt, source_url)

        print(f"✓ Draft generated")
        print(f"\nDraft post ({len(draft)} chars):")
        print(draft)

        # Check length
        if len(draft) <= 280:
            print(f"\n✓ Post is within Twitter's 280 character limit")
        else:
            print(f"\n⚠ Post exceeds 280 chars by {len(draft) - 280}")

        # Check if URL is included
        if source_url and source_url in draft:
            print(f"✓ URL is included in the post")
        elif source_url:
            print(f"⚠ URL was provided but not found in draft")
        else:
            print(f"⚠ No URL was available to include")

    except Exception as e:
        print(f"✗ Error in post generation: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n" + "=" * 80)
    print("Integration test complete!")
    print("=" * 80)

    return True


if __name__ == "__main__":
    test_url_integration()
