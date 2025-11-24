"""
Test script to check if Google Search grounding returns URLs that can be included in posts.
"""
import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

# Initialize client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Model configurations
LLM_MODEL = "gemini-3-pro-preview"

def test_search_with_urls():
    """Test if we can get URLs from Google Search grounding."""

    search_prompt = """
Find the latest trending news about artificial intelligence and machine learning.

Provide a brief summary of the most interesting findings, focusing on recent developments.
"""

    print("=" * 80)
    print("Testing Google Search Grounding - URL Extraction")
    print("=" * 80)
    print(f"\nSearch prompt: {search_prompt}\n")

    try:
        # Use Google Search grounding
        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=search_prompt,
            config={
                "temperature": 0.7,
                "tools": [
                    {"google_search": {}}
                ],
                "thinking_config": {
                    "thinking_level": "HIGH"
                }
            }
        )

        print("\n--- RESPONSE TEXT ---")
        print(response.text)
        print()

        # Check for grounding metadata
        print("\n--- CHECKING FOR GROUNDING METADATA ---")
        if hasattr(response, 'candidates') and len(response.candidates) > 0:
            candidate = response.candidates[0]
            print(f"✓ Found {len(response.candidates)} candidate(s)")

            if hasattr(candidate, 'grounding_metadata'):
                print("✓ Grounding metadata exists")
                metadata = candidate.grounding_metadata

                # Check for grounding chunks (the sources)
                if hasattr(metadata, 'grounding_chunks') and metadata.grounding_chunks:
                    print(f"✓ Found {len(metadata.grounding_chunks)} grounding chunk(s)\n")

                    print("\n--- EXTRACTED URLs ---")
                    for i, chunk in enumerate(metadata.grounding_chunks, 1):
                        if hasattr(chunk, 'web'):
                            web = chunk.web
                            uri = getattr(web, 'uri', 'N/A')
                            title = getattr(web, 'title', 'N/A')
                            print(f"\n{i}. Title: {title}")
                            print(f"   URL: {uri}")
                else:
                    print("✗ No grounding_chunks found")

                # Check for grounding supports (links text to sources)
                if hasattr(metadata, 'grounding_supports') and metadata.grounding_supports:
                    print(f"\n✓ Found {len(metadata.grounding_supports)} grounding support(s)")
                    print("\n--- GROUNDING SUPPORTS (Text -> Source mapping) ---")
                    for i, support in enumerate(metadata.grounding_supports, 1):
                        if hasattr(support, 'segment'):
                            segment = support.segment
                            text = getattr(segment, 'text', 'N/A')
                            start_idx = getattr(segment, 'start_index', 'N/A')
                            end_idx = getattr(segment, 'end_index', 'N/A')

                            chunk_indices = []
                            if hasattr(support, 'grounding_chunk_indices'):
                                chunk_indices = support.grounding_chunk_indices

                            print(f"\n{i}. Text segment [{start_idx}:{end_idx}]: \"{text[:100]}...\"")
                            print(f"   Linked to chunk(s): {chunk_indices}")
                else:
                    print("✗ No grounding_supports found")

                # Check for search entry point
                if hasattr(metadata, 'search_entry_point'):
                    print("\n✓ Search entry point exists")

            else:
                print("✗ No grounding_metadata attribute found")
        else:
            print("✗ No candidates found in response")

        print("\n" + "=" * 80)
        print("Test complete!")
        print("=" * 80)

        # Return summary
        if hasattr(response, 'candidates') and len(response.candidates) > 0:
            candidate = response.candidates[0]
            if hasattr(candidate, 'grounding_metadata'):
                metadata = candidate.grounding_metadata
                if hasattr(metadata, 'grounding_chunks') and metadata.grounding_chunks:
                    return True, len(metadata.grounding_chunks), metadata.grounding_chunks

        return False, 0, None

    except Exception as e:
        print(f"\n✗ Error during test: {e}")
        import traceback
        traceback.print_exc()
        return False, 0, None


def test_generate_post_with_link():
    """Test generating a short post with a link."""

    # First get search results
    has_urls, count, chunks = test_search_with_urls()

    if not has_urls or not chunks:
        print("\n⚠ Cannot test post generation - no URLs found")
        return

    # Extract first URL
    first_url = chunks[0].web.uri if hasattr(chunks[0], 'web') else None
    if not first_url:
        print("\n⚠ Cannot extract URL from chunk")
        return

    print("\n" + "=" * 80)
    print("Testing Post Generation with URL")
    print("=" * 80)

    # Test if we can fit a URL in a 280 char post
    sample_text = "Exciting developments in AI and machine learning this week! Check out this article:"
    test_post = f"{sample_text} {first_url}"

    print(f"\nSample post ({len(test_post)} chars):")
    print(test_post)

    if len(test_post) <= 280:
        print("\n✓ Post fits within Twitter's 280 character limit")
    else:
        print(f"\n✗ Post exceeds limit by {len(test_post) - 280} characters")
        print("  (May need URL shortening)")

    print("=" * 80)


if __name__ == "__main__":
    # Run the tests
    test_generate_post_with_link()
