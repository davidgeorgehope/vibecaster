import os
import time
from typing import Optional, Dict, Any, Tuple
from google import genai
from google.genai import types
import tweepy
import requests
from PIL import Image
from io import BytesIO
import base64
from dotenv import load_dotenv
from database import get_campaign, get_oauth_tokens, update_last_run

load_dotenv()

# Initialize Google GenAI client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Model configurations
LLM_MODEL = "gemini-2.0-flash-exp"  # Primary model
LLM_FALLBACK = "gemini-1.5-pro-002"  # Fallback model
IMAGE_MODEL = "imagen-3.0-generate-001"


def analyze_user_prompt(user_prompt: str) -> Tuple[str, str]:
    """
    Analyze user prompt to generate refined persona and visual style.

    Returns:
        Tuple of (refined_persona, visual_style)
    """
    try:
        analysis_prompt = f"""
Analyze this social media automation request and generate:

1. A REFINED PERSONA - A detailed system instruction describing the voice, tone, and personality this account should embody
2. A VISUAL STYLE - Art direction for image generation that matches the persona

User Request: "{user_prompt}"

Respond in this exact JSON format:
{{
    "refined_persona": "Your detailed persona description here",
    "visual_style": "Your visual style description here"
}}
"""

        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=analysis_prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                response_mime_type="application/json"
            )
        )

        result = response.text
        import json
        data = json.loads(result)

        return data.get("refined_persona", ""), data.get("visual_style", "")

    except Exception as e:
        print(f"Error analyzing prompt: {e}")
        # Fallback to simple defaults
        return (
            f"A social media account that posts about: {user_prompt}",
            "Modern, clean, professional visual style"
        )


def search_trending_topics(user_prompt: str, refined_persona: str) -> str:
    """
    Use Gemini with Google Search grounding to find trending topics.

    Returns:
        Search context as a string
    """
    try:
        search_prompt = f"""
Find the latest trending news, discussions, or technical developments related to: {user_prompt}

Focus on recent (last 24-48 hours) content that would be interesting to someone with this persona:
{refined_persona}

Provide a brief summary of the most interesting findings.
"""

        # Use Google Search grounding
        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=search_prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )

        return response.text

    except Exception as e:
        print(f"Error searching topics: {e}")
        return f"General discussion about {user_prompt}"


def generate_post_draft(search_context: str, refined_persona: str, user_prompt: str) -> str:
    """
    Generate a social media post draft based on search context and persona.

    Returns:
        Post text (under 280 characters)
    """
    try:
        draft_prompt = f"""
You are acting as this persona:
{refined_persona}

Based on this trending information:
{search_context}

Write a single social media post about {user_prompt}.

Requirements:
- Maximum 280 characters
- Engaging and authentic to the persona
- Include relevant insights from the trending information
- Can include 1-2 relevant hashtags if appropriate
- Natural, conversational tone

Write only the post text, nothing else.
"""

        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=draft_prompt,
            config=types.GenerateContentConfig(
                temperature=0.8,
                max_output_tokens=100
            )
        )

        return response.text.strip()

    except Exception as e:
        print(f"Error generating draft: {e}")
        return "Excited to share thoughts on this topic! #ai #automation"


def critique_and_refine_post(draft: str, refined_persona: str) -> str:
    """
    Critique the post draft and refine it if needed.

    Returns:
        Final refined post
    """
    try:
        critique_prompt = f"""
Review this social media post draft:
"{draft}"

Persona: {refined_persona}

Critique it for:
1. Engagement potential
2. Authenticity to persona
3. Safety (no controversial/harmful content)
4. Length (must be under 280 chars)

If the post has issues, rewrite it. Otherwise, return it unchanged.
Return only the final post text, nothing else.
"""

        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=critique_prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=100
            )
        )

        return response.text.strip()

    except Exception as e:
        print(f"Error critiquing post: {e}")
        return draft


def generate_image(post_text: str, visual_style: str) -> Optional[bytes]:
    """
    Generate an image using Imagen based on the post and visual style.

    Returns:
        Image bytes or None if generation fails
    """
    try:
        image_prompt = f"""
Create a visually appealing image for this social media post:
"{post_text}"

Art Style: {visual_style}

The image should be eye-catching, professional, and complement the post content.
"""

        response = client.models.generate_images(
            model=IMAGE_MODEL,
            prompt=image_prompt,
            config=types.GenerateImageConfig(
                number_of_images=1,
                aspect_ratio="1:1",  # Square format for social media
                safety_filter_level="block_some",
                person_generation="allow_adult"
            )
        )

        # Get the first generated image
        if response.generated_images:
            image = response.generated_images[0]
            # Convert PIL Image to bytes
            img_byte_arr = BytesIO()
            image.image.save(img_byte_arr, format='PNG')
            return img_byte_arr.getvalue()

        return None

    except Exception as e:
        print(f"Error generating image: {e}")
        return None


def post_to_twitter(user_id: int, post_text: str, image_bytes: Optional[bytes] = None) -> bool:
    """
    Post to Twitter/X with optional image.

    Returns:
        True if successful, False otherwise
    """
    try:
        tokens = get_oauth_tokens(user_id, "twitter")
        if not tokens:
            print("No Twitter tokens found")
            return False

        # Create Twitter client
        client = tweepy.Client(
            bearer_token=tokens["access_token"]
        )

        # If image is provided, we need to use the v1.1 API for media upload
        media_id = None
        if image_bytes:
            # Create API v1.1 client for media upload
            auth = tweepy.OAuth2UserHandler(
                client_id=os.getenv("X_CLIENT_ID"),
                client_secret=os.getenv("X_CLIENT_SECRET")
            )
            auth.token = {"access_token": tokens["access_token"]}
            api = tweepy.API(auth)

            # Upload media
            media = api.media_upload(filename="image.png", file=BytesIO(image_bytes))
            media_id = media.media_id

        # Create tweet
        if media_id:
            response = client.create_tweet(text=post_text, media_ids=[media_id])
        else:
            response = client.create_tweet(text=post_text)

        print(f"Posted to Twitter: {response.data['id']}")
        return True

    except Exception as e:
        print(f"Error posting to Twitter: {e}")
        return False


def post_to_linkedin(user_id: int, post_text: str, image_bytes: Optional[bytes] = None) -> bool:
    """
    Post to LinkedIn with optional image.

    Returns:
        True if successful, False otherwise
    """
    try:
        tokens = get_oauth_tokens(user_id, "linkedin")
        if not tokens:
            print("No LinkedIn tokens found")
            return False

        headers = {
            "Authorization": f"Bearer {tokens['access_token']}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0"
        }

        # Get user URN
        user_response = requests.get(
            "https://api.linkedin.com/v2/userinfo",
            headers=headers
        )
        user_response.raise_for_status()
        user_id = user_response.json()["sub"]

        # Prepare post data
        post_data = {
            "author": f"urn:li:person:{user_id}",
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": post_text
                    },
                    "shareMediaCategory": "NONE"
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            }
        }

        # TODO: Image upload for LinkedIn (requires additional API calls)
        # For MVP, posting text only

        # Create post
        response = requests.post(
            "https://api.linkedin.com/v2/ugcPosts",
            headers=headers,
            json=post_data
        )
        response.raise_for_status()

        print(f"Posted to LinkedIn: {response.json()['id']}")
        return True

    except Exception as e:
        print(f"Error posting to LinkedIn: {e}")
        return False


def run_agent_cycle(user_id: int):
    """
    Main agent cycle that runs the complete workflow:
    1. Fetch campaign configuration
    2. Search for trending topics
    3. Generate post draft
    4. Critique and refine
    5. Generate image
    6. Post to connected platforms
    """
    try:
        print(f"\n{'='*60}")
        print(f"Starting agent cycle for user {user_id} at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        # Get campaign configuration
        campaign = get_campaign(user_id)
        if not campaign or not campaign.get("user_prompt"):
            print(f"No campaign configured for user {user_id}. Skipping cycle.")
            return

        user_prompt = campaign["user_prompt"]
        refined_persona = campaign.get("refined_persona", "")
        visual_style = campaign.get("visual_style", "")

        print(f"Campaign: {user_prompt}")
        print(f"Persona: {refined_persona[:100]}...")

        # Step 1: Search for trending topics
        print("\n[1/5] Searching for trending topics...")
        search_context = search_trending_topics(user_prompt, refined_persona)
        print(f"Found context: {search_context[:200]}...")

        # Step 2: Generate draft
        print("\n[2/5] Generating post draft...")
        draft = generate_post_draft(search_context, refined_persona, user_prompt)
        print(f"Draft: {draft}")

        # Step 3: Critique and refine
        print("\n[3/5] Critiquing and refining...")
        final_post = critique_and_refine_post(draft, refined_persona)
        print(f"Final post: {final_post}")

        # Step 4: Generate image
        print("\n[4/5] Generating image...")
        image_bytes = generate_image(final_post, visual_style)
        if image_bytes:
            print(f"Image generated ({len(image_bytes)} bytes)")
        else:
            print("No image generated")

        # Step 5: Post to platforms
        print("\n[5/5] Posting to platforms...")
        twitter_success = post_to_twitter(user_id, final_post, image_bytes)
        linkedin_success = post_to_linkedin(user_id, final_post, image_bytes)

        # Update last run timestamp
        update_last_run(user_id, int(time.time()))

        print(f"\nResults:")
        print(f"  Twitter: {'✓' if twitter_success else '✗'}")
        print(f"  LinkedIn: {'✓' if linkedin_success else '✗'}")
        print(f"\n{'='*60}\n")

    except Exception as e:
        print(f"Error in agent cycle for user {user_id}: {e}")
        import traceback
        traceback.print_exc()
