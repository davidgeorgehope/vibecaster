"""Vibecaster CLI - Main entry point."""

import sys
import json
import click

from .config import load_config, save_config
from .api import VibecasterClient, ApiError


def format_timestamp(ts):
    """Format a unix timestamp for display."""
    if not ts:
        return "Never"
    from datetime import datetime
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def handle_api_error(e: ApiError):
    """Display an API error and exit."""
    click.echo(click.style(f"API Error ({e.status_code}): {e.detail}", fg="red"))
    sys.exit(1)


def display_job_result(job: dict):
    """Display the result of a completed job."""
    result = job.get("result", {})
    if not result:
        return

    x_post = result.get("x_post", "")
    linkedin_post = result.get("linkedin_post", "")
    has_image = result.get("has_image", False)
    posted = result.get("posted", [])
    errors = result.get("errors", {})

    if x_post:
        click.echo(click.style("\n  [TWITTER/X]", fg="cyan", bold=True))
        click.echo(click.style("  " + "─" * 40, fg="bright_black"))
        for line in x_post.split("\n"):
            click.echo(f"  {line}")

    if linkedin_post:
        click.echo(click.style("\n  [LINKEDIN]", fg="blue", bold=True))
        click.echo(click.style("  " + "─" * 40, fg="bright_black"))
        for line in linkedin_post.split("\n"):
            click.echo(f"  {line}")

    if has_image:
        click.echo(f"\n  {click.style('🖼', fg='green')}  Image generated")

    if posted:
        click.echo()
        for p in posted:
            click.echo(f"  {click.style('✓', fg='green')} Posted to {p}")

    if errors:
        for platform, error in errors.items():
            click.echo(f"  {click.style('✗', fg='red')} {platform}: {error}")

    click.echo()


@click.group()
@click.version_option(package_name="vibecaster-cli")
def cli():
    """Vibecaster - AI-powered social media automation CLI."""
    pass


# ===== LOGIN =====

@cli.command()
@click.option("--api-url", prompt="API URL", default="https://vibecaster.ai/api",
              help="Vibecaster API base URL")
@click.option("--api-key", prompt="API Key", hide_input=True,
              help="Your Vibecaster API key (vb_...)")
def login(api_url, api_key):
    """Configure API credentials."""
    api_url = api_url.rstrip("/")

    if not api_key.startswith("vb_"):
        click.echo(click.style("Warning: API key should start with 'vb_'", fg="yellow"))

    click.echo("Testing connection...")
    try:
        import requests
        response = requests.get(
            f"{api_url}/auth/status",
            headers={"X-API-Key": api_key},
            timeout=10,
        )
        if response.status_code == 401:
            click.echo(click.style("Error: Invalid API key", fg="red"))
            sys.exit(1)
        elif response.status_code >= 400:
            click.echo(click.style(f"Error: API returned {response.status_code}", fg="red"))
            sys.exit(1)
    except requests.ConnectionError:
        click.echo(click.style(f"Error: Could not connect to {api_url}", fg="red"))
        sys.exit(1)

    config = load_config()
    config["api_url"] = api_url
    config["api_key"] = api_key
    save_config(config)

    click.echo(click.style("Logged in successfully!", fg="green"))
    click.echo(f"Config saved to ~/.vibecaster/config.json")


# ===== STATUS =====

@cli.command()
def status():
    """Show campaign status and connected platforms."""
    client = VibecasterClient()

    try:
        connections = client.get("/auth/status")
    except ApiError as e:
        handle_api_error(e)

    click.echo(click.style("\n  Vibecaster Status", fg="cyan", bold=True))
    click.echo(click.style("  " + "─" * 30, fg="bright_black"))

    click.echo(click.style("\n  Connections:", fg="white", bold=True))
    for platform, info in connections.items():
        connected = info.get("connected", False)
        expired = info.get("expired", False)
        name = platform.capitalize()
        if platform == "youtube":
            name = "YouTube"

        if connected and not expired:
            click.echo(f"    {click.style('●', fg='green')} {name}")
        elif connected and expired:
            click.echo(f"    {click.style('●', fg='yellow')} {name} (expired)")
        else:
            click.echo(f"    {click.style('○', fg='bright_black')} {name}")

    try:
        campaign = client.get("/campaign")
        click.echo(click.style("\n  Campaign:", fg="white", bold=True))
        is_active = campaign.get("is_active", False)
        if is_active:
            click.echo(f"    Status: {click.style('Active', fg='green')}")
        else:
            click.echo(f"    Status: {click.style('Inactive', fg='yellow')}")
        schedule = campaign.get("schedule_cron", "Not set")
        click.echo(f"    Schedule: {schedule}")
        last_run = campaign.get("last_run", 0)
        click.echo(f"    Last run: {format_timestamp(last_run) if last_run else 'Never'}")
    except ApiError:
        click.echo(click.style("\n  Campaign: Not configured", fg="yellow"))

    click.echo()


# ===== CREATE (the hero command) =====

@cli.command()
@click.argument("prompt")
@click.option("--post", "-p", "platforms", multiple=True, type=click.Choice(["twitter", "linkedin", "all"]),
              help="Post to platform(s). Omit for preview only.")
@click.option("--no-image", is_flag=True, help="Skip image generation.")
def create(prompt, platforms, no_image):
    """Create a post from a text prompt.

    Examples:
      vibecaster create "post about OpenTelemetry collector anti-patterns"
      vibecaster create "something funny about SRE on-call" --post twitter
      vibecaster create "OTel + AI observability" --post all
    """
    client = VibecasterClient()

    # Expand "all" to both platforms
    platform_list = []
    for p in platforms:
        if p == "all":
            platform_list.extend(["twitter", "linkedin"])
        else:
            platform_list.append(p)
    platform_list = list(set(platform_list))

    mode = "Generating + posting" if platform_list else "Generating preview"
    click.echo(click.style(f"\n  {mode}", fg="cyan", bold=True))
    click.echo(f"  Prompt: {prompt}\n")

    job = client.submit_and_poll("/cli/create-post", {
        "prompt": prompt,
        "platforms": platform_list,
        "media_type": "none" if no_image else "image",
    })

    if job.get("status") == "complete":
        display_job_result(job)
    elif job.get("status") == "failed":
        click.echo(click.style(f"  Failed: {job.get('error', 'Unknown')}", fg="red"))


# ===== POST (direct, no AI) =====

@cli.command("post")
@click.argument("text")
@click.option("--media", "-m", type=click.Path(exists=True), help="Path to image or video file.")
@click.option("--platform", "-p", "platforms", multiple=True,
              type=click.Choice(["twitter", "linkedin", "all"]), default=["linkedin"],
              help="Platform(s) to post to.")
def post_direct(text, media, platforms):
    """Post directly with your own text + optional media. No AI generation.

    Examples:
      vibecaster post "Check out this demo!" --media video.mp4 --platform linkedin
      vibecaster post "Quick update" --platform all
      vibecaster post "Look at this" --media screenshot.png -p twitter -p linkedin
    """
    client = VibecasterClient()

    platform_list = []
    for p in platforms:
        if p == "all":
            platform_list.extend(["twitter", "linkedin"])
        else:
            platform_list.append(p)
    platform_list = list(set(platform_list))

    click.echo(click.style(f"\n  Direct post → {', '.join(platform_list)}", fg="cyan", bold=True))
    if media:
        click.echo(f"  Media: {media}")

    # Use multipart form upload for direct post
    import os
    files = {}
    if media:
        files["media"] = (os.path.basename(media), open(media, "rb"),
                         "video/mp4" if media.endswith(".mp4") else
                         "image/png" if media.endswith(".png") else
                         "image/jpeg")

    data = {
        "text": text,
        "platforms": ",".join(platform_list),
    }

    # Submit job via multipart form
    import requests
    client._ensure_auth()
    url = f"{client.api_url}/cli/direct-post"
    headers = {"X-API-Key": client.api_key}

    try:
        response = requests.post(url, data=data, files=files if files else None,
                                headers=headers, timeout=30)
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            click.echo(click.style(f"  Error: {detail}", fg="red"))
            return
        result = response.json()
    except requests.ConnectionError:
        click.echo(click.style(f"  Error: Could not connect to {client.api_url}", fg="red"))
        return

    job_id = result.get("job_id")
    if not job_id:
        click.echo(click.style("  Error: No job ID returned", fg="red"))
        return

    # Poll for completion
    import time
    spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    idx = 0
    start = time.time()

    while time.time() - start < 300:
        try:
            job = client.get(f"/cli/jobs/{job_id}")
        except Exception:
            time.sleep(2)
            continue

        status = job.get("status", "unknown")
        if status == "complete":
            click.echo(f"\r  {click.style('✓', fg='green')} Done!   ")
            job_result = job.get("result", {})
            posted = job_result.get("posted", [])
            errors = job_result.get("errors", {})
            for p in posted:
                click.echo(f"  {click.style('✓', fg='green')} Posted to {p}")
            for platform, error in errors.items():
                click.echo(f"  {click.style('✗', fg='red')} {platform}: {error}")
            click.echo()
            return
        elif status == "failed":
            click.echo(f"\r  {click.style('✗', fg='red')} Failed: {job.get('error', 'Unknown')}   ")
            return

        click.echo(f"\r  {spinner[idx % len(spinner)]} Posting...", nl=False)
        idx += 1
        time.sleep(1.5)

    click.echo(f"\n  Timed out. Job ID: {job_id}")


# ===== GENERATE (async) =====

@cli.command()
@click.argument("url")
def generate(url):
    """Generate posts from a URL (preview only)."""
    client = VibecasterClient()

    click.echo(click.style(f"\n  Generating from URL", fg="cyan", bold=True))
    click.echo(f"  {url}\n")

    job = client.submit_and_poll("/cli/generate-from-url", {
        "url": url,
        "platforms": [],
    })

    if job.get("status") == "complete":
        display_job_result(job)
    elif job.get("status") == "failed":
        click.echo(click.style(f"  Failed: {job.get('error', 'Unknown')}", fg="red"))


# ===== POST (async, from URL) =====

@cli.command("post-url")
@click.argument("url")
@click.option("--platform", "-p", "platforms", multiple=True,
              type=click.Choice(["twitter", "linkedin", "all"]), default=["all"],
              help="Platform(s) to post to.")
def post_url(url, platforms):
    """Generate and post content from a URL."""
    client = VibecasterClient()

    platform_list = []
    for p in platforms:
        if p == "all":
            platform_list.extend(["twitter", "linkedin"])
        else:
            platform_list.append(p)
    platform_list = list(set(platform_list))

    click.echo(click.style(f"\n  Generating + posting from URL", fg="cyan", bold=True))
    click.echo(f"  {url}\n")

    job = client.submit_and_poll("/cli/generate-from-url", {
        "url": url,
        "platforms": platform_list,
    })

    if job.get("status") == "complete":
        display_job_result(job)
    elif job.get("status") == "failed":
        click.echo(click.style(f"  Failed: {job.get('error', 'Unknown')}", fg="red"))


# ===== CAMPAIGN =====

@cli.group(invoke_without_command=True)
@click.pass_context
def campaign(ctx):
    """View or manage campaign settings."""
    if ctx.invoked_subcommand is None:
        client = VibecasterClient()
        try:
            data = client.get("/campaign")
        except ApiError as e:
            if e.status_code == 404:
                click.echo(click.style("No campaign configured. Use 'vibecaster campaign setup <prompt>' to create one.", fg="yellow"))
                return
            handle_api_error(e)

        click.echo(click.style("\n  Campaign Details", fg="cyan", bold=True))
        click.echo(click.style("  " + "─" * 40, fg="bright_black"))

        is_active = data.get("is_active", False)
        click.echo(f"\n  Status:    {click.style('Active', fg='green') if is_active else click.style('Inactive', fg='yellow')}")
        click.echo(f"  Schedule:  {data.get('schedule_cron', 'Not set')}")
        click.echo(f"  Media:     {data.get('media_type', 'image')}")
        click.echo(f"  Last run:  {format_timestamp(data.get('last_run', 0))}")

        prompt = data.get("user_prompt", "")
        if prompt:
            display = prompt if len(prompt) <= 200 else prompt[:200] + "..."
            click.echo(f"\n  Prompt:\n    {display}")

        click.echo()


@campaign.command("setup")
@click.argument("prompt")
def campaign_setup(prompt):
    """Create or update campaign with a prompt."""
    client = VibecasterClient()

    click.echo("Analyzing prompt and setting up campaign...")
    try:
        result = client.post("/setup", json={"prompt": prompt})
    except ApiError as e:
        handle_api_error(e)

    click.echo(click.style("Campaign configured!", fg="green"))
    if result.get("schedule_cron"):
        click.echo(f"  Schedule: {result['schedule_cron']}")
    if result.get("media_type"):
        click.echo(f"  Media type: {result['media_type']}")
    click.echo("\nUse 'vibecaster campaign activate' to start posting.")


@campaign.command("activate")
def campaign_activate():
    """Activate the campaign scheduler."""
    client = VibecasterClient()

    try:
        result = client.post("/campaign/activate")
    except ApiError as e:
        handle_api_error(e)

    click.echo(click.style("Campaign activated!", fg="green"))
    if result.get("schedule_cron"):
        click.echo(f"  Schedule: {result['schedule_cron']}")


@campaign.command("deactivate")
def campaign_deactivate():
    """Deactivate the campaign scheduler."""
    client = VibecasterClient()

    try:
        client.post("/campaign/deactivate")
    except ApiError as e:
        handle_api_error(e)

    click.echo(click.style("Campaign deactivated.", fg="yellow"))


# ===== RUN =====

@cli.command("run")
def run_now():
    """Trigger a campaign run immediately."""
    client = VibecasterClient()

    click.echo("Triggering campaign run...")
    try:
        client.post("/run-now")
    except ApiError as e:
        handle_api_error(e)

    click.echo(click.style("Campaign run started! Check connected platforms for new posts.", fg="green"))


# ===== JOB =====

@cli.command()
@click.argument("job_id")
def job(job_id):
    """Check status of an async job."""
    client = VibecasterClient()

    try:
        data = client.get(f"/cli/jobs/{job_id}")
    except ApiError as e:
        handle_api_error(e)

    status = data.get("status", "unknown")
    click.echo(click.style(f"\n  Job {job_id}", fg="cyan", bold=True))
    click.echo(f"  Status: {status}")

    if status == "complete":
        display_job_result(data)
    elif status == "failed":
        click.echo(click.style(f"  Error: {data.get('error', 'Unknown')}", fg="red"))
    else:
        click.echo(f"  Created: {format_timestamp(data.get('created_at'))}")
        click.echo(f"  Updated: {format_timestamp(data.get('updated_at'))}")
        click.echo("  Still running... check again shortly.")

    click.echo()


# ===== KEYS =====

@cli.group()
def keys():
    """Manage API keys."""
    pass


@keys.command("list")
def keys_list():
    """List all API keys."""
    client = VibecasterClient()

    try:
        api_keys = client.get("/api-keys")
    except ApiError as e:
        handle_api_error(e)

    if not api_keys:
        click.echo("No API keys found.")
        return

    click.echo(click.style("\n  API Keys", fg="cyan", bold=True))
    click.echo(click.style("  " + "─" * 50, fg="bright_black"))

    for key in api_keys:
        active = key.get("is_active", False)
        status_dot = click.style("●", fg="green") if active else click.style("●", fg="red")
        name = key.get("name", "Unnamed")
        prefix = key.get("key_prefix", "")
        created = format_timestamp(key.get("created_at"))
        last_used = format_timestamp(key.get("last_used_at"))

        click.echo(f"\n  {status_dot} {click.style(name, bold=True)}  (ID: {key['id']})")
        click.echo(f"    Prefix: {prefix}...")
        click.echo(f"    Created: {created}  |  Last used: {last_used}")
        if not active:
            click.echo(f"    {click.style('REVOKED', fg='red')}")

    click.echo()


@keys.command("create")
@click.argument("name")
def keys_create(name):
    """Create a new API key (requires web UI login)."""
    client = VibecasterClient()

    try:
        result = client.post("/api-keys", json={"name": name})
    except ApiError as e:
        if e.status_code == 403:
            click.echo(click.style("API key creation requires web UI login (JWT auth).", fg="yellow"))
            click.echo("Create keys at: https://vibecaster.ai → Dashboard → API Keys")
            sys.exit(1)
        handle_api_error(e)

    click.echo(click.style("\n  API Key Created!", fg="green", bold=True))
    click.echo(click.style("  " + "─" * 50, fg="bright_black"))
    click.echo(f"\n  Name:   {result.get('name')}")
    click.echo(f"  Prefix: {result.get('key_prefix')}...")
    click.echo(f"\n  {click.style('Full Key (save this now, it will not be shown again):', fg='yellow')}")
    click.echo(f"  {click.style(result.get('key', ''), fg='green', bold=True)}")
    click.echo()


@keys.command("revoke")
@click.argument("key_id", type=int)
@click.confirmation_option(prompt="Are you sure you want to revoke this API key?")
def keys_revoke(key_id):
    """Revoke an API key by ID."""
    client = VibecasterClient()

    try:
        client.delete(f"/api-keys/{key_id}")
    except ApiError as e:
        handle_api_error(e)

    click.echo(click.style("API key revoked.", fg="yellow"))


def main():
    cli()


if __name__ == "__main__":
    main()
