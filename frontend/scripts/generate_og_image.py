#!/usr/bin/env python3
"""Generate OG image for Vibecaster (1200x630px)"""

from PIL import Image, ImageDraw, ImageFont
import os

# Image dimensions (standard OG image size)
WIDTH = 1200
HEIGHT = 630

# Colors
BG_COLOR = (13, 13, 20)  # Dark purple-gray
PURPLE = (147, 51, 234)  # Purple accent
PINK = (236, 72, 153)  # Pink accent
WHITE = (255, 255, 255)
GRAY = (156, 163, 175)

def create_gradient_background(draw, width, height):
    """Create a subtle gradient background"""
    for y in range(height):
        # Subtle purple tint that increases towards bottom
        r = int(13 + (20 * y / height))
        g = int(13 + (5 * y / height))
        b = int(20 + (30 * y / height))
        draw.line([(0, y), (width, y)], fill=(r, g, b))

def draw_gradient_text(image, text, position, font, color1, color2):
    """Draw text with a horizontal gradient"""
    # Create a temporary image for the text
    txt_img = Image.new('RGBA', image.size, (0, 0, 0, 0))
    txt_draw = ImageDraw.Draw(txt_img)
    txt_draw.text(position, text, font=font, fill=WHITE)

    # Create gradient overlay
    bbox = txt_draw.textbbox(position, text, font=font)
    text_width = bbox[2] - bbox[0]

    gradient = Image.new('RGBA', image.size, (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(gradient)

    for x in range(int(bbox[0]), int(bbox[2])):
        ratio = (x - bbox[0]) / text_width
        r = int(color1[0] + (color2[0] - color1[0]) * ratio)
        g = int(color1[1] + (color2[1] - color1[1]) * ratio)
        b = int(color1[2] + (color2[2] - color1[2]) * ratio)
        grad_draw.line([(x, 0), (x, image.size[1])], fill=(r, g, b, 255))

    # Composite
    txt_img = Image.composite(gradient, Image.new('RGBA', image.size, (0, 0, 0, 0)), txt_img)
    image.paste(txt_img, (0, 0), txt_img)

def main():
    # Create image
    img = Image.new('RGB', (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Draw gradient background
    create_gradient_background(draw, WIDTH, HEIGHT)

    # Add some decorative elements (circles/orbs)
    img_rgba = img.convert('RGBA')
    overlay = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    # Purple orb (top right)
    for i in range(100, 0, -1):
        alpha = int(30 * (1 - i/100))
        overlay_draw.ellipse(
            [900 - i*2, -50 - i*2, 900 + i*2, -50 + i*2],
            fill=(147, 51, 234, alpha)
        )

    # Pink orb (bottom left)
    for i in range(80, 0, -1):
        alpha = int(25 * (1 - i/80))
        overlay_draw.ellipse(
            [100 - i*2, 550 - i*2, 100 + i*2, 550 + i*2],
            fill=(236, 72, 153, alpha)
        )

    img_rgba = Image.alpha_composite(img_rgba, overlay)
    img = img_rgba.convert('RGB')
    draw = ImageDraw.Draw(img)

    # Try to load fonts, fall back to default if not available
    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
        subtitle_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
        tagline_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
    except OSError:
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf", 72)
            subtitle_font = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSans.ttf", 32)
            tagline_font = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSans.ttf", 28)
        except OSError:
            title_font = ImageFont.load_default()
            subtitle_font = ImageFont.load_default()
            tagline_font = ImageFont.load_default()

    # Draw lightning bolt icon (simplified)
    bolt_points = [
        (120, 250), (160, 250), (145, 295), (180, 295),
        (130, 380), (150, 320), (115, 320)
    ]
    draw.polygon(bolt_points, fill=PURPLE)

    # Draw title "VIBECASTER"
    title = "VIBECASTER"
    title_bbox = draw.textbbox((0, 0), title, font=title_font)
    title_width = title_bbox[2] - title_bbox[0]
    title_x = (WIDTH - title_width) // 2 + 20
    title_y = 230

    # Draw with gradient effect (simple version - just purple to pink)
    img_rgba = img.convert('RGBA')
    draw_gradient_text(img_rgba, title, (title_x, title_y), title_font, PURPLE, PINK)
    img = img_rgba.convert('RGB')
    draw = ImageDraw.Draw(img)

    # Draw subtitle
    subtitle = "AI-Powered Social Media Automation"
    subtitle_bbox = draw.textbbox((0, 0), subtitle, font=subtitle_font)
    subtitle_width = subtitle_bbox[2] - subtitle_bbox[0]
    subtitle_x = (WIDTH - subtitle_width) // 2
    subtitle_y = 330
    draw.text((subtitle_x, subtitle_y), subtitle, font=subtitle_font, fill=WHITE)

    # Draw tagline
    tagline = "Auto-post to X, LinkedIn & YouTube with Google Gemini"
    tagline_bbox = draw.textbbox((0, 0), tagline, font=tagline_font)
    tagline_width = tagline_bbox[2] - tagline_bbox[0]
    tagline_x = (WIDTH - tagline_width) // 2
    tagline_y = 390
    draw.text((tagline_x, tagline_y), tagline, font=tagline_font, fill=GRAY)

    # Draw bottom accent line
    line_y = 550
    draw.line([(400, line_y), (800, line_y)], fill=PURPLE, width=3)

    # Save
    output_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_path = os.path.join(output_dir, 'public', 'og-image.png')
    img.save(output_path, 'PNG', quality=95)
    print(f"OG image saved to: {output_path}")

if __name__ == '__main__':
    main()
