"""
Author Bio Module - Character/author reference image management.

Provides functionality for:
- Generating character reference images from descriptions (Nano Banana Pro)
- Searching for author images online (Google Search grounding)
- Managing author bio data
"""

import os
import base64
from typing import Optional, Dict, Any, List
from io import BytesIO
from google import genai
from google.genai import types
from dotenv import load_dotenv
from logger_config import agent_logger as logger

load_dotenv()

# Initialize Google GenAI client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Models
IMAGE_MODEL = "gemini-3-pro-image-preview"  # Nano Banana Pro
LLM_MODEL = "gemini-3-pro-preview"


def generate_character_reference(
    description: str,
    style: str = "real_person",
    additional_context: str = ""
) -> Optional[bytes]:
    """
    Generate a character reference image from a text description.

    Uses Nano Banana Pro (gemini-3-pro-image-preview) to create a consistent
    character portrait that can be used as reference for other generations.

    Args:
        description: Text description of the character/author
        style: Visual style ('real_person', 'cartoon', 'anime', 'avatar', '3d_render')
        additional_context: Extra context about the character's role/purpose

    Returns:
        Image bytes (PNG) or None if generation fails
    """
    style_prompts = {
        "real_person": "photorealistic portrait photograph, professional headshot, natural lighting, high quality",
        "cartoon": "cartoon style illustration, colorful, expressive, clean lines, character design",
        "anime": "anime style portrait, detailed eyes, expressive face, professional illustration",
        "avatar": "3D avatar style, stylized proportions, clean design, suitable for profile picture",
        "3d_render": "3D rendered character portrait, cinematic lighting, high detail, professional quality"
    }

    style_description = style_prompts.get(style, style_prompts["real_person"])

    prompt = f"""Create a character reference portrait:

Character Description: {description}

Style: {style_description}

Requirements:
- Clear, well-lit portrait showing the face and upper body
- Neutral background that doesn't distract
- The character should be looking at the camera with a friendly expression
- High quality, detailed image suitable for use as a reference
- Consistent, memorable character design

{f'Additional Context: {additional_context}' if additional_context else ''}

Generate a single, high-quality portrait image."""

    try:
        logger.info(f"🎨 Generating character reference in {style} style...")

        response = client.models.generate_content(
            model=IMAGE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"]
            )
        )

        # Extract image from response
        if hasattr(response, 'candidates'):
            for candidate in response.candidates:
                if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    for part in candidate.content.parts:
                        # Try inline_data first (raw bytes - most reliable)
                        if hasattr(part, 'inline_data') and part.inline_data:
                            if hasattr(part.inline_data, 'data') and part.inline_data.data:
                                logger.info(f"Character reference generated successfully ({len(part.inline_data.data)} bytes)")
                                return part.inline_data.data

                        # Try as_image method as fallback
                        if hasattr(part, 'as_image'):
                            try:
                                image = part.as_image()
                                if image and hasattr(image, 'save'):
                                    img_byte_arr = BytesIO()
                                    image.save(img_byte_arr, format='PNG')
                                    logger.info(f"Character reference generated via as_image() ({len(img_byte_arr.getvalue())} bytes)")
                                    return img_byte_arr.getvalue()
                            except Exception as e:
                                logger.warning(f"as_image() method failed: {e}")

        logger.warning("No image found in response candidates")
        return None

    except Exception as e:
        logger.error(f"Error generating character reference: {e}", exc_info=True)
        return None


def generate_character_references_batch(
    characters: List[Dict[str, Any]],
    global_style: str = "storybook"
) -> Dict[str, bytes]:
    """
    Generate reference images for multiple characters (up to 3).

    Creates consistent reference portraits for each character that can be
    passed to Veo 3.1 for visual consistency across video scenes.

    Args:
        characters: List of character dicts with:
            - id: unique identifier
            - name: display name
            - description: visual description
            - style: character-specific style (pixar_3d, storybook_human, etc.)
            - priority: 1-3 (lower = higher priority)
        global_style: Overall video style for consistency

    Returns:
        Dict mapping character_id -> image bytes
    """
    # Style prompts for different character types
    style_prompts = {
        "photorealistic": "photorealistic portrait photograph, professional headshot, natural lighting, high quality",
        "storybook_human": "storybook illustration style, warm lighting, slightly stylized but recognizable human, painterly quality",
        "pixar_3d": "Pixar-style 3D animated character, expressive features, professional CG quality, soft lighting",
        "anime": "anime style portrait, detailed expressive eyes, clean lines, professional illustration",
        "cartoon_2d": "2D cartoon character, clean lines, expressive, suitable for animation",
    }

    # Global style hints to maintain visual consistency
    global_hints = {
        "storybook": "warm cozy lighting, painterly illustration quality",
        "pixar": "Pixar/Disney 3D animation quality, soft shadows",
        "photorealistic": "cinematic lighting, photorealistic quality",
        "anime": "anime aesthetic, clean cel-shaded look",
        "cartoon": "bright colors, clean cartoon style",
    }

    references = {}

    # Generate references for ALL characters (each scene will use up to 3)
    # Sort by priority for generation order, but don't limit total count
    sorted_chars = sorted(characters, key=lambda c: c.get('priority', 99))

    for char in sorted_chars:
        char_id = char.get('id', '')
        char_name = char.get('name', 'Character')
        char_desc = char.get('description', '')
        char_style = char.get('style', 'storybook_human')

        if not char_id or not char_desc:
            logger.warning(f"Skipping character with missing id or description: {char}")
            continue

        style_desc = style_prompts.get(char_style, style_prompts['storybook_human'])
        global_hint = global_hints.get(global_style, global_hints['storybook'])

        prompt = f"""Create a character reference portrait for video generation:

Character Name: {char_name}
Character Description: {char_desc}

Visual Style: {style_desc}
Overall Aesthetic: {global_hint}

Requirements:
- Clear, well-lit view showing the character's full design and distinctive features
- Neutral background that doesn't distract from the character
- Character facing slightly toward camera with a natural expression
- High quality, detailed image suitable for use as a video generation reference
- Maintain all specific visual details mentioned in the description (clothing, accessories, colors)

Generate a single, high-quality character reference portrait."""

        try:
            logger.info(f"🎨 Generating reference for {char_name} ({char_style})...")

            response = client.models.generate_content(
                model=IMAGE_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"]
                )
            )

            # Extract image from response
            image_bytes = None
            if hasattr(response, 'candidates'):
                for candidate in response.candidates:
                    if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                        for part in candidate.content.parts:
                            if hasattr(part, 'inline_data') and part.inline_data:
                                if hasattr(part.inline_data, 'data') and part.inline_data.data:
                                    image_bytes = part.inline_data.data
                                    break
                            if hasattr(part, 'as_image'):
                                try:
                                    image = part.as_image()
                                    if image and hasattr(image, 'save'):
                                        img_byte_arr = BytesIO()
                                        image.save(img_byte_arr, format='PNG')
                                        image_bytes = img_byte_arr.getvalue()
                                        break
                                except Exception:
                                    pass
                    if image_bytes:
                        break

            if image_bytes:
                references[char_id] = image_bytes
                logger.info(f"✅ Reference generated for {char_name} ({len(image_bytes)} bytes)")
            else:
                logger.warning(f"❌ No image generated for {char_name}")

        except Exception as e:
            logger.error(f"Error generating reference for {char_name}: {e}", exc_info=True)

    logger.info(f"Generated {len(references)}/{len(characters)} character references")
    return references


def generate_image_with_reference(
    prompt: str,
    reference_image: bytes,
    style: str = "real_person"
) -> Optional[bytes]:
    """
    Generate an image using a character reference for consistency.

    Uses Nano Banana Pro's ability to maintain character consistency
    across multiple images using reference images.

    Args:
        prompt: Description of the scene/image to generate
        reference_image: Reference image bytes of the character
        style: Visual style to maintain

    Returns:
        Image bytes (PNG) or None if generation fails
    """
    from PIL import Image

    style_hints = {
        "real_person": "photorealistic, consistent with reference photo",
        "cartoon": "cartoon style, matching the reference character design",
        "anime": "anime style, consistent with reference character",
        "avatar": "3D avatar style, matching reference design",
        "3d_render": "3D rendered, consistent with reference character"
    }

    style_hint = style_hints.get(style, style_hints["real_person"])

    full_prompt = f"""{prompt}

Important: Maintain exact visual consistency with the provided reference image.
The character should look identical to the reference - same face, features, and style.
Style: {style_hint}"""

    try:
        logger.info(f"🎨 Generating image with character reference...")

        # Load reference image
        ref_image = Image.open(BytesIO(reference_image))

        response = client.models.generate_content(
            model=IMAGE_MODEL,
            contents=[
                full_prompt,
                ref_image
            ],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"]
            )
        )

        # Extract image from response
        if hasattr(response, 'candidates'):
            for candidate in response.candidates:
                if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    for part in candidate.content.parts:
                        if hasattr(part, 'inline_data') and part.inline_data:
                            if hasattr(part.inline_data, 'data') and part.inline_data.data:
                                logger.info(f"Image with reference generated successfully ({len(part.inline_data.data)} bytes)")
                                return part.inline_data.data

                        if hasattr(part, 'as_image'):
                            try:
                                image = part.as_image()
                                if image and hasattr(image, 'save'):
                                    img_byte_arr = BytesIO()
                                    image.save(img_byte_arr, format='PNG')
                                    return img_byte_arr.getvalue()
                            except Exception as e:
                                logger.warning(f"as_image() method failed: {e}")

        logger.warning("No image found in response candidates")
        return None

    except Exception as e:
        logger.error(f"Error generating image with reference: {e}", exc_info=True)
        return None


def search_author_images(
    author_name: str,
    limit: int = 5
) -> List[Dict[str, str]]:
    """
    Search for author/character images online using Google Search grounding.

    Args:
        author_name: Name of the author/person to search for
        limit: Maximum number of results to return

    Returns:
        List of dicts with 'url', 'title', and 'description' keys
    """
    search_query = f"{author_name} portrait photo"

    try:
        logger.info(f"🔍 Searching for images of: {author_name}")

        # Use Gemini with Google Search grounding
        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=f"""Find portrait images or photos of {author_name}.

Return a JSON array of image search results with the following format:
[
    {{
        "url": "direct URL to the image",
        "title": "title or caption",
        "description": "brief description of the image",
        "source": "source website"
    }}
]

Return up to {limit} results. Focus on clear, high-quality portrait photos suitable for use as a reference image.
Only return the JSON array, no other text.""",
            config=types.GenerateContentConfig(
                temperature=0.3,
                tools=[types.Tool(google_search=types.GoogleSearch())],
                response_mime_type="application/json"
            )
        )

        # Extract search results from grounding metadata
        results = []

        # Try to parse the response text as JSON first
        if hasattr(response, 'text') and response.text:
            try:
                import json
                parsed = json.loads(response.text)
                if isinstance(parsed, list):
                    results = parsed[:limit]
            except json.JSONDecodeError:
                logger.warning("Could not parse search results as JSON")

        # Also extract URLs from grounding metadata if available
        if hasattr(response, 'candidates'):
            for candidate in response.candidates:
                if hasattr(candidate, 'grounding_metadata'):
                    metadata = candidate.grounding_metadata
                    if hasattr(metadata, 'grounding_chunks') and metadata.grounding_chunks:
                        for chunk in metadata.grounding_chunks:
                            if hasattr(chunk, 'web') and hasattr(chunk.web, 'uri'):
                                # Add grounded URLs to results if not already present
                                url = chunk.web.uri
                                if not any(r.get('url') == url for r in results):
                                    results.append({
                                        "url": url,
                                        "title": getattr(chunk.web, 'title', 'Search Result'),
                                        "description": "",
                                        "source": urlparse(url).netloc if url else ""
                                    })

        logger.info(f"Found {len(results)} image results")
        return results[:limit]

    except Exception as e:
        logger.error(f"Error searching for author images: {e}", exc_info=True)
        return []


def download_image_from_url(url: str) -> Optional[bytes]:
    """
    Download an image from a URL.

    Args:
        url: URL of the image to download

    Returns:
        Image bytes or None if download fails
    """
    import requests

    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; Vibecaster/1.0)',
        'Accept': 'image/*'
    }

    try:
        logger.info(f"📥 Downloading image from: {url[:60]}...")

        response = requests.get(url, headers=headers, timeout=15, stream=True)
        response.raise_for_status()

        # Check content type
        content_type = response.headers.get('content-type', '')
        if not content_type.startswith('image/'):
            logger.warning(f"URL does not return an image: {content_type}")
            return None

        # Read image data
        image_data = response.content

        # Validate it's actually an image by trying to open it
        from PIL import Image
        img = Image.open(BytesIO(image_data))
        img.verify()

        logger.info(f"Image downloaded successfully ({len(image_data)} bytes)")
        return image_data

    except Exception as e:
        logger.error(f"Error downloading image: {e}")
        return None


def validate_image(image_bytes: bytes) -> Dict[str, Any]:
    """
    Validate an image and return its properties.

    Args:
        image_bytes: Raw image bytes

    Returns:
        Dict with 'valid', 'width', 'height', 'format', 'mime_type' keys
    """
    from PIL import Image

    try:
        img = Image.open(BytesIO(image_bytes))

        # Map PIL format to MIME type
        mime_types = {
            'PNG': 'image/png',
            'JPEG': 'image/jpeg',
            'GIF': 'image/gif',
            'WEBP': 'image/webp'
        }

        return {
            'valid': True,
            'width': img.width,
            'height': img.height,
            'format': img.format,
            'mime_type': mime_types.get(img.format, f'image/{img.format.lower()}')
        }
    except Exception as e:
        logger.error(f"Invalid image: {e}")
        return {
            'valid': False,
            'error': str(e)
        }


# Import for URL parsing
from urllib.parse import urlparse
