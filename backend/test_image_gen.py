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
        print(f"Has parts: {hasattr(response, 'parts')}")

        if hasattr(response, 'parts'):
            print(f"Number of parts: {len(response.parts)}")

            for i, part in enumerate(response.parts):
                print(f"\nPart {i}:")
                print(f"  Type: {type(part)}")
                print(f"  Has as_image: {hasattr(part, 'as_image')}")
                print(f"  Has inline_data: {hasattr(part, 'inline_data')}")
                print(f"  Has text: {hasattr(part, 'text')}")

                # Try to extract image
                if hasattr(part, 'as_image'):
                    image = part.as_image()
                    if image:
                        print(f"  ✓ Image extracted successfully!")
                        print(f"  Image type: {type(image)}")
                        print(f"  Image size: {image.size if hasattr(image, 'size') else 'unknown'}")

                        # Save image
                        output_path = "/Users/davidhope/IdeaProjects/vibecaster/test_output.png"
                        image.save(output_path)
                        print(f"  ✓ Image saved to: {output_path}")
                        return True
                    else:
                        print(f"  ✗ as_image() returned None")

                if hasattr(part, 'inline_data') and part.inline_data:
                    print(f"  Has inline_data: {part.inline_data}")

                if hasattr(part, 'text') and part.text:
                    print(f"  Text content: {part.text[:100]}")

        print("\n✗ No image found in response")
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
        print(f"Response attributes: {dir(response)}")

        # Try different ways to access the response
        if hasattr(response, 'candidates'):
            print(f"\nHas candidates: {len(response.candidates)}")
            for i, candidate in enumerate(response.candidates):
                print(f"Candidate {i} type: {type(candidate)}")
                if hasattr(candidate, 'content'):
                    print(f"  Has content: {candidate.content}")
                    if hasattr(candidate.content, 'parts'):
                        print(f"  Content has parts: {len(candidate.content.parts)}")
                        for j, part in enumerate(candidate.content.parts):
                            print(f"    Part {j}: {type(part)}")
                            if hasattr(part, 'as_image'):
                                image = part.as_image()
                                if image:
                                    output_path = "/Users/davidhope/IdeaProjects/vibecaster/test_output_2.png"
                                    image.save(output_path)
                                    print(f"    ✓ Image saved to: {output_path}")
                                    return True

        if hasattr(response, 'text'):
            print(f"\nResponse text: {response.text}")

        if hasattr(response, 'parts'):
            print(f"\nDirect parts access: {response.parts}")

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
