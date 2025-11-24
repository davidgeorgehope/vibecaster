#!/usr/bin/env python3
"""
Test script for Gemini 3 Pro Image generation.
Run with: python test_image_gen.py
"""
import os
from google import genai
from google.genai import types
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()

# Initialize client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Model to test
IMAGE_MODEL = "gemini-3-pro-image-preview"

def extract_image_bytes(response):
    """
    Extract image bytes from response using the same logic as agents.py.
    Returns (bytes, method_used) or (None, None) if no image found.
    """
    if hasattr(response, 'candidates'):
        for candidate in response.candidates:
            if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                for part in candidate.content.parts:
                    # Try inline_data first (raw bytes - most reliable)
                    if hasattr(part, 'inline_data') and part.inline_data:
                        if hasattr(part.inline_data, 'data') and part.inline_data.data:
                            return part.inline_data.data, 'inline_data'

                    # Try as_image method as fallback
                    if hasattr(part, 'as_image'):
                        try:
                            image = part.as_image()
                            if image and hasattr(image, 'save'):
                                img_byte_arr = BytesIO()
                                image.save(img_byte_arr, format='PNG')
                                return img_byte_arr.getvalue(), 'as_image'
                        except Exception as e:
                            print(f"  Warning: as_image() failed: {e}")
    return None, None


def test_image_generation():
    """Test basic image generation."""
    print("=" * 60)
    print("Testing Gemini 3 Pro Image Generation")
    print("=" * 60)

    prompt = """
Create a kawaii anime girl character pointing at an OpenTelemetry architecture diagram.
She should have a cheerful expression and be drawn in a simple, cute style.
The diagram should show distributed tracing concepts.
"""

    print(f"\nPrompt: {prompt[:100]}...")
    print(f"\nModel: {IMAGE_MODEL}")
    print("\nAttempting image generation...")

    try:
        # Method 1: Dict-based config
        print("\n[Test 1] Using dict-based config...")
        response = client.models.generate_content(
            model=IMAGE_MODEL,
            contents=prompt,
            config={
                "response_modalities": ["IMAGE"],
                "image_config": {
                    "aspect_ratio": "1:1",
                    "image_size": "1K"
                }
            }
        )

        print(f"Response received!")
        print(f"Response type: {type(response)}")
        print(f"Has candidates: {hasattr(response, 'candidates')}")

        # Debug: show structure
        if hasattr(response, 'candidates'):
            print(f"Number of candidates: {len(response.candidates)}")
            for i, candidate in enumerate(response.candidates):
                print(f"\nCandidate {i}:")
                print(f"  Type: {type(candidate)}")
                if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    print(f"  Number of parts: {len(candidate.content.parts)}")
                    for j, part in enumerate(candidate.content.parts):
                        print(f"    Part {j}:")
                        print(f"      Type: {type(part)}")
                        print(f"      Has as_image: {hasattr(part, 'as_image')}")
                        print(f"      Has inline_data: {hasattr(part, 'inline_data')}")
                        if hasattr(part, 'inline_data') and part.inline_data:
                            print(f"      inline_data type: {type(part.inline_data)}")
                            if hasattr(part.inline_data, 'data'):
                                print(f"      inline_data.data length: {len(part.inline_data.data) if part.inline_data.data else 0}")
                            if hasattr(part.inline_data, 'mime_type'):
                                print(f"      inline_data.mime_type: {part.inline_data.mime_type}")

        # Try extraction using same logic as agents.py
        print("\n--- Testing extraction (agents.py logic) ---")
        image_bytes, method = extract_image_bytes(response)

        if image_bytes:
            print(f"✓ Image extracted successfully via {method}!")
            print(f"  Bytes length: {len(image_bytes)}")

            # Save to verify it's valid
            output_path = "/tmp/test_output.png"
            with open(output_path, 'wb') as f:
                f.write(image_bytes)
            print(f"  ✓ Image saved to: {output_path}")

            # Verify it's a valid image
            try:
                from PIL import Image
                img = Image.open(BytesIO(image_bytes))
                print(f"  ✓ Valid image: {img.format} {img.size}")
            except Exception as e:
                print(f"  Warning: Could not verify image with PIL: {e}")

            return True
        else:
            print("✗ No image extracted")
            return False

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_with_types_config():
    """Test using types.GenerateContentConfig if it works."""
    print("\n" + "=" * 60)
    print("[Test 2] Using types.GenerateContentConfig...")
    print("=" * 60)

    prompt = "A simple kawaii anime girl waving hello"

    try:
        response = client.models.generate_content(
            model=IMAGE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=['IMAGE']
            )
        )

        print(f"✓ Response received with types.GenerateContentConfig!")
        print(f"Response type: {type(response)}")

        # Use same extraction logic as agents.py
        image_bytes, method = extract_image_bytes(response)

        if image_bytes:
            print(f"✓ Image extracted successfully via {method}!")
            print(f"  Bytes length: {len(image_bytes)}")

            output_path = "/tmp/test_output_2.png"
            with open(output_path, 'wb') as f:
                f.write(image_bytes)
            print(f"  ✓ Image saved to: {output_path}")
            return True

        print("✗ No image extracted")
        return False

    except Exception as e:
        print(f"✗ Error with types.GenerateContentConfig: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\nStarting image generation tests...\n")

    success1 = test_image_generation()

    if not success1:
        print("\nFirst test failed, trying alternative method...")
        success2 = test_with_types_config()
    else:
        success2 = True

    print("\n" + "=" * 60)
    print("Test Results:")
    print(f"  Dict-based config: {'✓ PASS' if success1 else '✗ FAIL'}")
    print(f"  Types config: {'✓ PASS' if success2 else '✗ FAIL'}")
    print("=" * 60)
