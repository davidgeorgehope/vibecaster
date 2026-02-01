#!/usr/bin/env python3
"""
Nox → Vibecaster bridge script v2.
Skips Vibecaster's search (can be slow/hang on large pages).
Accepts pre-searched content as input.

Usage:
  python whatsapp_post_v2.py generate '{"topic":"...","content":"...","source_url":"..."}'
  python whatsapp_post_v2.py post '{"topic":"...","content":"...","source_url":"..."}'

Input JSON:
  topic       - What the post is about
  content     - Pre-searched context/summary (provided by Nox)
  source_url  - URL to include in the post (optional)
  persona     - Override persona (optional, defaults to campaign persona)
  visual_style - Override visual style (optional)
  platforms   - List of platforms (optional, defaults to ["twitter","linkedin"])

Output: Last line is ---RESULT--- followed by JSON result
"""
import sys
import os
import json
import time

sys.path.insert(0, '/root/vibecaster/backend')
os.chdir('/root/vibecaster/backend')

from dotenv import load_dotenv
load_dotenv()

from agents_lib import agent_post_generator, generate_image
from agents_lib.social_media import post_to_twitter, post_to_linkedin
from database import get_campaign


def generate_posts(params: dict, user_id: int = 1):
    """Generate posts from pre-searched content."""
    result = {
        "success": False,
        "x_post": None,
        "linkedin_post": None,
        "source_url": params.get("source_url", ""),
        "image_path": None,
        "error": None
    }
    
    try:
        campaign = get_campaign(user_id)
        
        topic = params["topic"]
        content = params.get("content", topic)
        source_url = params.get("source_url", "")
        persona = params.get("persona", campaign.get("refined_persona", "observability enthusiast and tech builder") if campaign else "observability enthusiast and tech builder")
        visual_style = params.get("visual_style", campaign.get("visual_style", "clean modern tech illustration") if campaign else "clean modern tech illustration")
        user_prompt = campaign.get("user_prompt", "") if campaign else ""
        
        # Step 1: Generate posts
        print(json.dumps({"step": "generating_posts", "status": "running", "topic": topic}), flush=True)
        
        posts = agent_post_generator(
            persona=persona,
            topic=topic,
            content=content[:4000],
            visual_style=visual_style,
            source_url=source_url
        )
        
        if not posts.get("success"):
            result["error"] = posts.get("error", "Post generation failed")
            return result
        
        result["x_post"] = posts.get("x_post", "")
        result["linkedin_post"] = posts.get("linkedin_post", "")
        result["source_url"] = posts.get("source_url", source_url)
        
        print(json.dumps({"step": "generating_posts", "status": "done"}), flush=True)
        
        # Step 2: Generate image
        print(json.dumps({"step": "generating_image", "status": "running"}), flush=True)
        
        image_bytes = generate_image(
            post_text=result["x_post"],
            visual_style=posts.get("visual_style", visual_style),
            user_prompt=user_prompt,
            topic_context=content[:1000]
        )
        
        if image_bytes:
            image_path = f"/tmp/nox-post-{int(time.time())}.png"
            with open(image_path, "wb") as f:
                f.write(image_bytes)
            result["image_path"] = image_path
            print(json.dumps({"step": "generating_image", "status": "done", "path": image_path}), flush=True)
        else:
            print(json.dumps({"step": "generating_image", "status": "skipped"}), flush=True)
        
        result["success"] = True
        
    except Exception as e:
        result["error"] = str(e)
        import traceback
        traceback.print_exc()
    
    return result


def do_post(result: dict, user_id: int = 1, platforms=None):
    """Post generated content to social platforms."""
    if platforms is None:
        platforms = ["twitter", "linkedin"]
    
    posted = {}
    
    image_bytes = None
    if result.get("image_path") and os.path.exists(result["image_path"]):
        with open(result["image_path"], "rb") as f:
            image_bytes = f.read()
    
    if "twitter" in platforms and result.get("x_post"):
        print(json.dumps({"step": "posting_twitter", "status": "running"}), flush=True)
        posted["twitter"] = post_to_twitter(user_id, result["x_post"], image_bytes)
        print(json.dumps({"step": "posting_twitter", "status": "done", "result": posted["twitter"]}), flush=True)
    
    if "linkedin" in platforms and result.get("linkedin_post"):
        print(json.dumps({"step": "posting_linkedin", "status": "running"}), flush=True)
        posted["linkedin"] = post_to_linkedin(user_id, result["linkedin_post"], image_bytes)
        print(json.dumps({"step": "posting_linkedin", "status": "done", "result": posted["linkedin"]}), flush=True)
    
    result["posted"] = posted
    return result


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: whatsapp_post_v2.py <generate|post> '<json params>'"}))
        sys.exit(1)
    
    command = sys.argv[1]
    params = json.loads(sys.argv[2])
    platforms = params.get("platforms", ["twitter", "linkedin"])
    
    result = generate_posts(params)
    
    if command == "post" and result["success"]:
        result = do_post(result, platforms=platforms)
    
    print("---RESULT---")
    print(json.dumps(result, indent=2))
