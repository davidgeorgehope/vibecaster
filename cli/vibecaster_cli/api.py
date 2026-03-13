"""API client for Vibecaster CLI."""

import sys
import time
import click
import requests

from .config import load_config


class ApiError(Exception):
    """Raised when an API call fails."""
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")


class VibecasterClient:
    """HTTP client for the Vibecaster API."""

    def __init__(self):
        config = load_config()
        self.api_url = config.get("api_url", "https://vibecaster.ai/api")
        self.api_key = config.get("api_key")

    def _ensure_auth(self):
        if not self.api_key:
            click.echo(click.style("Error: Not logged in. Run 'vibecaster login' first.", fg="red"))
            sys.exit(1)

    def _headers(self) -> dict:
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs) -> dict:
        """Make an authenticated API request."""
        self._ensure_auth()
        url = f"{self.api_url}{path}"
        headers = self._headers()

        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        try:
            response = requests.request(method, url, headers=headers, timeout=30, **kwargs)
        except requests.ConnectionError:
            click.echo(click.style(f"Error: Could not connect to {self.api_url}", fg="red"))
            sys.exit(1)
        except requests.Timeout:
            click.echo(click.style("Error: Request timed out", fg="red"))
            sys.exit(1)

        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise ApiError(response.status_code, detail)

        if response.status_code == 204 or not response.text:
            return {}

        return response.json()

    def get(self, path: str, **kwargs) -> dict:
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> dict:
        return self._request("POST", path, **kwargs)

    def put(self, path: str, **kwargs) -> dict:
        return self._request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs) -> dict:
        return self._request("DELETE", path, **kwargs)

    def submit_and_poll(self, endpoint: str, payload: dict, timeout: int = 300) -> dict:
        """Submit an async job and poll until complete. Shows progress spinner."""
        result = self.post(endpoint, json=payload)
        job_id = result.get("job_id")
        if not job_id:
            return result

        status_labels = {
            "pending": "Queued",
            "generating_text": "Generating post text",
            "generating_image": "Generating image",
            "generating": "Generating content",
            "posting": "Posting to platforms",
            "complete": "Done",
            "failed": "Failed",
        }
        spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

        start = time.time()
        idx = 0
        last_status = ""

        while time.time() - start < timeout:
            try:
                job = self.get(f"/cli/jobs/{job_id}")
            except ApiError:
                time.sleep(2)
                continue

            job_status = job.get("status", "unknown")
            label = status_labels.get(job_status, job_status)

            if job_status != last_status:
                if last_status:
                    click.echo()  # newline after previous spinner
                last_status = job_status

            if job_status == "complete":
                click.echo(f"\r  {click.style('✓', fg='green')} {label}   ")
                return job
            elif job_status == "failed":
                click.echo(f"\r  {click.style('✗', fg='red')} {label}: {job.get('error', 'Unknown error')}   ")
                return job

            # Show spinner
            click.echo(f"\r  {spinner[idx % len(spinner)]} {label}...", nl=False)
            idx += 1
            time.sleep(1.5)

        click.echo(f"\n  {click.style('⏱', fg='yellow')} Timed out after {timeout}s. Job ID: {job_id}")
        click.echo(f"  Check later: vibecaster job {job_id}")
        return {"job_id": job_id, "status": "timeout"}
