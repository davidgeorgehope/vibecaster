#!/usr/bin/env python3
"""
Nox → Vibecaster bridge script.
Drives Vibecaster's AI pipeline directly from the command line.

Usage:
  python whatsapp_post.py generate "topic or instruction"
  python whatsapp_post.py post "topic or instruction"
  python whatsapp_post.py post-url "https://example.com/article"

Commands:
  generate  — Generate posts + image preview (no posting)
  post      — Generate and post to X + LinkedIn
  post-url  — Generate from URL and post

Output: JSON with x_post, linkedin_post, source_url, image_path, posted status
"""
import sys
import os
import json
import base64
import time

# Add vibecaster backend to path
sys.path.insert(0, '/root/vibecaster/backend')
os.chdir('/root/vibecaster/backend')

from dotenv import load_dotenv
load_dotenv()

from agents_lib import (
    agent_intent_parser,
    agent_search,
    agent_post_generator,
    generate_image,
    post_to_twitter,
    post_to_linkedin,
    generate_from_url,
)
from agents_lib.social_media import post_to_twitter, post_to_linkedin
from database import get_campaign


def generate_posts(topic: str, user_id: int = 1):
    """Generate posts about a topic using Vibecaster's AI pipeline."""
    result = {
        "success": False,
        "x_post": None,
        "linkedin_post": None,
        "source_url": None,
        "image_path": None,
        "error": None
    }
    
    try:
        # Step 1: Parse intent
        print(json.dumps({"step": "intent_parsing", "status": "running"}), flush=True)
        intent = agent_intent_parser(topic, [])
        
        persona = intent.get("persona", "observability expert and tech builder")
        search_query = intent.get("search_query", topic)
        visual_style = intent.get("visual_style", "clean, modern tech illustration")
        parsed_topic = intent.get("topic", topic)
        
        print(json.dumps({"step": "intent_parsing", "status": "done", "persona": persona, "query": search_query}), flush=True)
        
        # Step 2: Search with grounding
        print(json.dumps({"step": "searching", "status": "running", "query": search_query}), flush=True)
        search_result = agent_search(search_query, persona)
        
        content = search_result.get("content", "")
        source_url = search_result.get("selected_url", "")
        
        print(json.dumps({"step": "searching", "status": "done", "url": source_url}), flush=True)
        
        # Step 3: Generate platform-specific posts
        print(json.dumps({"step": "generating_posts", "status": "running"}), flush=True)
        posts = agent_post_generator(
            persona=persona,
            topic=parsed_topic,
            content=content,
            visual_style=visual_style,
            source_url=source_url
        )
        
        if not posts.get("success"):
            result["error"] = posts.get("error", "Post generation failed")
            print(json.dumps(result), flush=True)
            return result
        
        result["x_post"] = posts.get("x_post", "")
        result["linkedin_post"] = posts.get("linkedin_post", "")
        result["source_url"] = posts.get("source_url", source_url)
        
        print(json.dumps({"step": "generating_posts", "status": "done"}), flush=True)
        
        # Step 4: Generate image
        print(json.dumps({"step": "generating_image", "status": "running"}), flush=True)
        campaign = get_campaign(user_id)
        user_prompt = campaign.get("user_prompt", "") if campaign else ""
        
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
    
    return result


def generate_from_url_posts(url: str, user_id: int = 1):
    """Generate posts from a URL."""
    result = {
        "success": False,
        "x_post": None,
        "linkedin_post": None,
        "source_url": url,
        "image_path": None,
        "error": None
    }
    
    try:
        print(json.dumps({"step": "generating_from_url", "status": "running", "url": url}), flush=True)
        
        campaign = get_campaign(user_id)
        user_prompt = campaign.get("user_prompt", "") if campaign else ""
        refined_persona = campaign.get("refined_persona", "") if campaign else ""
        visual_style = campaign.get("visual_style", "") if campaign else ""
        
        gen_result = generate_from_url(url, user_prompt, refined_persona, visual_style)
        
        if gen_result:
            result["x_post"] = gen_result.get("x_post", "")
            result["linkedin_post"] = gen_result.get("linkedin_post", "")
            
            image_bytes = gen_result.get("image_bytes")
            if image_bytes:
                image_path = f"/tmp/nox-post-{int(time.time())}.png"
                with open(image_path, "wb") as f:
                    f.write(image_bytes)
                result["image_path"] = image_path
            
            result["success"] = True
        else:
            result["error"] = "URL generation returned no results"
            
        print(json.dumps({"step": "generating_from_url", "status": "done"}), flush=True)
        
    except Exception as e:
        result["error"] = str(e)
    
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
        posted["twitter"] = post_to_twitter(user_id, result["x_post"], image_bytes)
    
    if "linkedin" in platforms and result.get("linkedin_post"):
        posted["linkedin"] = post_to_linkedin(user_id, result["linkedin_post"], image_bytes)
    
    result["posted"] = posted
    return result


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: whatsapp_post.py <generate|post|post-url> <topic or url>"}))
        sys.exit(1)
    
    command = sys.argv[1]
    topic = " ".join(sys.argv[2:])
    
    if command == "generate":
        result = generate_posts(topic)
    elif command == "post":
        result = generate_posts(topic)
        if result["success"]:
            result = do_post(result)
    elif command == "post-url":
        result = generate_from_url_posts(topic)
        if result["success"]:
            result = do_post(result)
    else:
        result = {"error": f"Unknown command: {command}. Use generate, post, or post-url"}
    
    # Final output — last line is always the result JSON
    print("---RESULT---")
    print(json.dumps(result, indent=2))
